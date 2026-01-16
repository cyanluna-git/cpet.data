"""Tests API Router - CPET 테스트 관련 엔드포인트"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile, File, Form, status

from app.api.deps import CurrentUser, ResearcherUser, DBSession
from app.schemas import (
    CPETTestResponse,
    CPETTestListResponse,
    CPETTestUpdate,
    TestMetricsResponse,
    TestUploadResponse,
)
from app.schemas.test import TimeSeriesRequest, TimeSeriesResponse
from app.services import TestService

router = APIRouter(prefix="/tests", tags=["Tests"])


@router.post("/upload", response_model=TestUploadResponse, status_code=status.HTTP_201_CREATED)
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
    if not file.filename.endswith(('.xlsx', '.xls')):
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
    
    # 피험자는 본인 데이터만
    if current_user.role == "subject":
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
    
    # 피험자는 본인 테스트만
    if current_user.role == "subject":
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
    if current_user.role == "subject":
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
    if current_user.role == "subject":
        if test.subject_id != current_user.subject_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    
    metrics = await service.get_metrics(test_id)
    return TestMetricsResponse(test_id=test_id, subject_id=test.subject_id, **metrics)


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
    if current_user.role == "subject":
        if current_user.subject_id != subject_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
    
    tests, total = await service.list_tests(
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
