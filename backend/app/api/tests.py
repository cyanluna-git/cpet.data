"""Tests API Router - CPET 테스트 관련 엔드포인트"""

from typing import List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)

from app.api.deps import CurrentUser, DBSession, ResearcherUser
from app.schemas import (
    CPETTestListResponse,
    CPETTestResponse,
    CPETTestUpdate,
    TestMetricsResponse,
    TestUploadResponse,
)
from app.schemas.test import (
    RawBreathDataResponse,
    RawBreathDataRow,
    TestAnalysisResponse,
    TestUploadAutoResponse,
    TimeSeriesRequest,
    TimeSeriesResponse,
)
from app.services import TestService
from app.services.cosmed_parser import COSMEDParser
from app.utils.json_sanitizer import sanitize_for_json

router = APIRouter(prefix="/tests", tags=["Tests"])


@router.post(
    "/upload", response_model=TestUploadResponse, status_code=status.HTTP_201_CREATED
)
async def upload_test(
    db: DBSession,
    current_user: ResearcherUser,
    file: UploadFile = File(..., description="COSMED Excel 파일 (.xlsx)"),
    subject_id: UUID = Form(..., description="피험자 ID"),
    calc_method: str = Form("Frayn", description="대사 계산 방법"),
    smoothing_window: int = Form(10, description="평활화 윈도우"),
):
    """
    COSMED 테스트 파일 업로드 및 파싱

    - **file**: COSMED Excel 파일 (.xlsx)
    - **subject_id**: 연결할 피험자 ID
    - **calc_method**: 대사 계산 방법 (Frayn, Peronnet, Jeukendrup)
    - **smoothing_window**: 평활화 윈도우 크기

    파일을 파싱하여 테스트 정보와 호흡 데이터를 저장합니다.
    """
    # 파일 타입 검증
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Excel files (.xlsx, .xls) are supported",
        )

    # 파일 크기 제한 (50MB)
    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 50MB limit",
        )

    service = TestService(db)

    try:
        test, errors, warnings = await service.upload_and_parse(
            file_content=contents,
            filename=file.filename,
            subject_id=subject_id,
            calc_method=calc_method,
            smoothing_window=smoothing_window,
        )

        return TestUploadResponse(
            test_id=test.test_id,
            subject_id=test.subject_id,
            source_filename=file.filename,
            parsing_status=test.parsing_status or "success",
            parsing_errors=errors if errors else None,
            parsing_warnings=warnings if warnings else None,
            data_points_count=0,  # TODO: breath data 개수 계산
            created_at=test.created_at,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post(
    "/upload-auto",
    response_model=TestUploadAutoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_test_auto(
    db: DBSession,
    current_user: CurrentUser,
    file: UploadFile = File(..., description="COSMED Excel 파일 (.xlsx)"),
    calc_method: str = Form("Frayn", description="대사 계산 방법"),
    smoothing_window: int = Form(10, description="평활화 윈도우"),
):
    """
    피험자 자동 매칭/생성 후 테스트 업로드

    피험자를 자동으로 매칭하거나 새로 생성합니다:
    1. Excel 파일에서 피험자 정보 추출 (이름, research_id 등)
    2. 기존 피험자와 매칭 시도 (research_id → 이름 기반 ID → encrypted_name)
    3. 매칭 실패 시 새 피험자 생성 (연구자/관리자만)
    4. 테스트 파싱 및 저장

    **권한**:
    - 연구자/관리자: 모든 피험자에 대해 업로드 가능, 새 피험자 생성 가능
    - 일반 사용자(subject): 본인 프로필에만 업로드 가능

    - **file**: COSMED Excel 파일 (.xlsx, .xls)
    - **calc_method**: 대사 계산 방법 (Frayn, Jeukendrup)
    - **smoothing_window**: 평활화 윈도우 크기
    """
    import os
    import tempfile
    from pathlib import Path

    # 파일 타입 검증
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Excel files (.xlsx, .xls) are supported",
        )

    # 파일 크기 제한 (50MB)
    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 50MB limit",
        )

    service = TestService(db)

    try:
        # 1. 파일에서 피험자 정보만 먼저 추출
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        try:
            parser = COSMEDParser()
            parsed_data = parser.parse_file(tmp_path)
        finally:
            os.unlink(tmp_path)

        # 2. 피험자 자동 매칭/생성
        # 일반 사용자(subject)는 새 피험자 생성 불가
        if current_user.role in ("user", "subject"):
            # 본인 프로필에만 업로드 가능
            if current_user.subject_id is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No subject profile linked to your account",
                )
            # 자신의 subject_id로 강제 지정
            from sqlalchemy import select
            from app.models import Subject
            result = await db.execute(
                select(Subject).where(Subject.id == current_user.subject_id)
            )
            subject = result.scalar_one_or_none()
            if not subject:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Subject profile not found",
                )
            subject_created = False
        else:
            # 연구자/관리자: 자동 매칭/생성
            subject, subject_created = await service.find_or_create_subject(
                parsed_data.subject
            )

        # 피험자 이름 결정
        subject_name = subject.encrypted_name or subject.research_id

        # 3. 테스트 업로드 진행
        test, errors, warnings = await service.upload_and_parse(
            file_content=contents,
            filename=file.filename,
            subject_id=subject.id,
            calc_method=calc_method,
            smoothing_window=smoothing_window,
        )

        return TestUploadAutoResponse(
            test_id=test.test_id,
            subject_id=test.subject_id,
            subject_created=subject_created,
            subject_name=subject_name,
            source_filename=file.filename,
            parsing_status=test.parsing_status or "success",
            parsing_errors=errors if errors else None,
            parsing_warnings=warnings if warnings else None,
            data_points_count=0,  # TODO: breath data 개수 계산
            created_at=test.created_at,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        import traceback

        print(f"[ERROR] upload_test_auto failed: {e}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process file: {str(e)}",
        )


@router.get("", response_model=CPETTestListResponse)
async def list_tests(
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    subject_id: Optional[UUID] = Query(None, description="피험자 ID로 필터"),
):
    """
    테스트 목록 조회

    피험자는 본인 테스트만, 연구자는 전체 조회 가능
    """
    service = TestService(db)

    # 일반 유저(subject role)는 본인 데이터만 조회 가능
    # role이 'user' 또는 'subject'인 경우 subject_id로 필터링
    if current_user.role in ("user", "subject"):
        subject_id = current_user.subject_id

    tests, total = await service.get_list(
        page=page,
        page_size=page_size,
        subject_id=subject_id,
    )

    total_pages = (total + page_size - 1) // page_size

    return CPETTestListResponse(
        items=[CPETTestResponse.model_validate(t) for t in tests],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{test_id}", response_model=CPETTestResponse)
async def get_test(
    test_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    테스트 상세 정보 조회
    """
    service = TestService(db)

    test = await service.get_by_id(test_id)
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found",
        )

    # 일반 유저(user/subject role)는 본인 테스트만 조회 가능
    if current_user.role in ("user", "subject"):
        if test.subject_id != current_user.subject_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    return CPETTestResponse.model_validate(test)


@router.patch("/{test_id}", response_model=CPETTestResponse)
async def update_test(
    test_id: UUID,
    data: CPETTestUpdate,
    db: DBSession,
    current_user: ResearcherUser,
):
    """
    테스트 정보 수정 (연구자 이상 권한 필요)
    """
    service = TestService(db)

    test = await service.get_by_id(test_id)
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found",
        )

    updated = await service.update(test_id, data)
    return CPETTestResponse.model_validate(updated)


@router.delete(
    "/{test_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_test(
    test_id: UUID,
    db: DBSession,
    current_user: ResearcherUser,
):
    """
    테스트 삭제 (연구자 이상 권한 필요)
    """
    service = TestService(db)

    test = await service.get_by_id(test_id)
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found",
        )

    await service.delete(test_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{test_id}/raw-data", response_model=RawBreathDataResponse)
async def get_raw_breath_data(
    test_id: UUID,
    db: DBSession,
    current_user: ResearcherUser,  # Admin 또는 Researcher만 접근 가능
):
    """
    테스트의 Raw Breath Data 조회 (데이터 분석용)

    Admin 및 Researcher만 접근 가능.
    breath_data 테이블의 모든 컬럼을 반환합니다.
    """
    service = TestService(db)

    test = await service.get_by_id(test_id)
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found",
        )

    raw_data = await service.get_raw_breath_data(test_id)

    # 피험자 이름 조회
    subject_name = None
    if test.subject_id:
        from sqlalchemy import select

        from app.models import Subject

        result = await db.execute(select(Subject).where(Subject.id == test.subject_id))
        subject = result.scalar_one_or_none()
        if subject:
            subject_name = subject.encrypted_name

    # 각 row에 id 할당 (row index)
    data_rows = []
    for idx, row in enumerate(raw_data, start=1):
        row_dict = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        row_dict["id"] = idx
        # NaN/Inf 값을 None으로 변환
        row_dict = sanitize_for_json(row_dict)
        data_rows.append(RawBreathDataRow.model_validate(row_dict))

    return RawBreathDataResponse(
        test_id=test_id,
        source_filename=test.source_filename,
        test_date=test.test_date,
        subject_name=subject_name,
        total_rows=len(raw_data),
        data=data_rows,
    )


@router.get("/{test_id}/series", response_model=TimeSeriesResponse)
async def get_time_series(
    test_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
    signals: str = Query("vo2,vco2,hr", description="조회할 신호 (콤마 구분)"),
    interval: str = Query("1s", description="다운샘플 간격 (예: 1s, 5s, 10s, 30s)"),
    method: str = Query("mean", description="집계 방법 (mean, median, max, min)"),
    start_sec: Optional[float] = Query(None, description="시작 시간 (초)"),
    end_sec: Optional[float] = Query(None, description="종료 시간 (초)"),
):
    """
    테스트 시계열 데이터 조회 (다운샘플링 지원)

    - **signals**: 조회할 신호 목록 (vo2, vco2, ve, hr, rer 등)
    - **interval**: 다운샘플 간격 (1s, 5s, 10s, 30s)
    - **method**: 집계 방법 (mean, median, max, min)
    - **start_sec/end_sec**: 시간 범위 필터 (초 단위)
    """
    service = TestService(db)

    test = await service.get_by_id(test_id)
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found",
        )

    # 권한 확인
    if current_user.role in ("user", "subject"):
        if test.subject_id != current_user.subject_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    signal_list = [s.strip().lower() for s in signals.split(",")]

    request = TimeSeriesRequest(
        signals=signal_list,
        interval=interval,
        method=method,
        start_sec=start_sec,
        end_sec=end_sec,
    )

    result = await service.get_time_series(test_id, request)
    return TimeSeriesResponse(**result)


@router.get("/{test_id}/metrics", response_model=TestMetricsResponse)
async def get_test_metrics(
    test_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    테스트 주요 지표 조회

    VO2max, VT1, VT2, FatMax, RER 등 핵심 대사 지표 반환
    """
    service = TestService(db)

    test = await service.get_by_id(test_id)
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found",
        )

    # 권한 확인
    if current_user.role in ("user", "subject"):
        if test.subject_id != current_user.subject_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    metrics = await service.get_metrics(test_id)
    return TestMetricsResponse(test_id=test_id, subject_id=test.subject_id, **metrics)


@router.get(
    "/{test_id}/analysis",
    response_model=TestAnalysisResponse,
    response_model_exclude_none=False,
)
async def get_test_analysis(
    test_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
    interval: str = Query("5s", description="시계열 다운샘플 간격 (예: 1s, 5s, 10s)"),
    include_processed: bool = Query(
        True, description="처리된 시계열 데이터 포함 (LOESS, binning)"
    ),
    loess_frac: float = Query(
        0.25, ge=0.1, le=0.5, description="LOESS smoothing fraction (0.1~0.5)"
    ),
    bin_size: int = Query(10, ge=5, le=30, description="Power binning 크기 (W, 5~30)"),
    aggregation_method: str = Query(
        "median", description="집계 방법 (median, mean, trimmed_mean)"
    ),
    min_power_threshold: int = Query(
        0, ge=0, le=200, description="최소 파워 임계값 (W, 이하 데이터 제외)"
    ),
    trim_start_sec: Optional[float] = Query(
        None, description="Manual trim start time (seconds)"
    ),
    trim_end_sec: Optional[float] = Query(
        None, description="Manual trim end time (seconds)"
    ),
):
    """
    테스트 분석 결과 조회 (대사 프로파일 차트용)

    프론트엔드에서 대사 프로파일 차트를 그리기 위한 통합 분석 결과:
    - **phase_boundaries**: 구간 경계 (Rest, Warm-up, Exercise, Peak, Recovery)
    - **phase_metrics**: 구간별 평균/최대 메트릭
    - **fatmax**: FATMAX 상세 정보 (HR, Power, VO2, 시간)
    - **vo2max**: VO2MAX 상세 정보
    - **timeseries**: 다운샘플된 시계열 데이터 (차트용)
    - **통계 요약**: 총 지방/탄수화물 연소량, 평균 RER 등
    - **processed_series**: LOESS smoothing, Power binning 처리된 시계열
    - **metabolic_markers**: FatMax zone, Crossover point 마커
    - **used_trim_range**: Applied analysis window (auto-detected or manual)

    Processing Parameters:
    - **loess_frac**: LOESS 평활화 정도 (0.1=날카로움, 0.5=부드러움)
    - **bin_size**: 파워 구간 크기 (예: 10W → 0-10, 10-20, ...)
    - **aggregation_method**: 구간 집계 방법
      - median: 중앙값 (이상치에 강함, 기본값)
      - mean: 평균
      - trimmed_mean: 양쪽 10% 제거 후 평균
    - **min_power_threshold**: 최소 파워 임계값 (W, 이하 데이터 제외)
      - 0: 제외 없음 (기본값)
      - 80: 80W 미만 데이터 제외 (웜업 아티팩트 제거에 유용)

    Trim Parameters:
    - **trim_start_sec**: Manual trim start (seconds). If not provided, auto-detected.
    - **trim_end_sec**: Manual trim end (seconds). If not provided, auto-detected.
    """
    service = TestService(db)

    test = await service.get_by_id(test_id)
    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found",
        )

    # 권한 확인
    if current_user.role in ("user", "subject"):
        if test.subject_id != current_user.subject_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    # aggregation_method 검증
    valid_methods = ["median", "mean", "trimmed_mean"]
    if aggregation_method not in valid_methods:
        aggregation_method = "median"

    analysis = await service.get_analysis(
        test_id,
        interval=interval,
        include_processed=include_processed,
        loess_frac=loess_frac,
        bin_size=bin_size,
        aggregation_method=aggregation_method,
        min_power_threshold=min_power_threshold if min_power_threshold > 0 else None,
        trim_start_sec=trim_start_sec,
        trim_end_sec=trim_end_sec,
    )

    # NaN/Inf 값을 None으로 변환
    analysis = sanitize_for_json(analysis)

    return TestAnalysisResponse(**analysis)


# Subject 하위 경로로도 테스트 조회 가능
subject_tests_router = APIRouter(prefix="/subjects/{subject_id}/tests", tags=["Tests"])


@subject_tests_router.get("", response_model=CPETTestListResponse)
async def list_subject_tests(
    subject_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    특정 피험자의 테스트 목록 조회
    """
    service = TestService(db)

    # 권한 확인
    if current_user.role in ("user", "subject"):
        if current_user.subject_id != subject_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    tests, total = await service.get_list(
        page=page,
        page_size=page_size,
        subject_id=subject_id,
    )

    total_pages = (total + page_size - 1) // page_size

    return CPETTestListResponse(
        items=[CPETTestResponse.model_validate(t) for t in tests],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
