"""Subjects API Router - 피험자 관련 엔드포인트"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import CurrentUser, ResearcherUser, DBSession
from app.schemas import (
    SubjectCreate,
    SubjectUpdate,
    SubjectResponse,
    SubjectListResponse,
    SubjectWithTests,
)
from app.services import SubjectService

router = APIRouter(prefix="/subjects", tags=["Subjects"])


@router.get("", response_model=SubjectListResponse)
async def list_subjects(
    db: DBSession,
    current_user: ResearcherUser,
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    search: Optional[str] = Query(None, description="검색어 (이름, 코드)"),
    gender: Optional[str] = Query(None, description="성별 필터 (M/F)"),
    training_level: Optional[str] = Query(None, description="훈련 수준 필터"),
):
    """
    피험자 목록 조회 (페이지네이션 + 검색/필터)
    
    - **page**: 페이지 번호 (1부터 시작)
    - **page_size**: 페이지당 항목 수 (최대 100)
    - **search**: 이름 또는 코드로 검색
    - **gender**: 성별 필터 (M: 남성, F: 여성)
    - **training_level**: 훈련 수준 필터
    """
    service = SubjectService(db)
    
    subjects, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        gender=gender,
        training_level=training_level,
    )
    
    total_pages = (total + page_size - 1) // page_size
    
    return SubjectListResponse(
        items=[SubjectResponse.model_validate(s) for s in subjects],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
async def create_subject(
    data: SubjectCreate,
    db: DBSession,
    current_user: ResearcherUser,
):
    """
    새 피험자 등록
    
    - **research_id**: 고유 연구 ID (필수)
    - **encrypted_name**: 암호화된 이름
    - **birth_year**: 출생 연도
    - **gender**: 성별 (M/F)
    - **height_cm/weight_kg**: 신체 정보
    """
    service = SubjectService(db)
    
    # 중복 체크
    existing = await service.get_by_research_id(data.research_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Research ID '{data.research_id}' already exists",
        )
    
    subject = await service.create(data)
    return SubjectResponse.model_validate(subject)


@router.get("/{subject_id}", response_model=SubjectWithTests)
async def get_subject(
    subject_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    피험자 상세 정보 조회 (테스트 목록 포함)
    
    피험자 본인이거나 연구자 이상 권한 필요
    """
    service = SubjectService(db)
    
    # 피험자 본인 확인 또는 연구자 권한 (user/subject role 체크)
    if current_user.role in ("user", "subject"):
        if current_user.subject_id != subject_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to other subject's data",
            )
    
    subject = await service.get_with_tests(subject_id)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found",
        )
    
    return SubjectWithTests.model_validate(subject)


@router.patch("/{subject_id}", response_model=SubjectResponse)
async def update_subject(
    subject_id: UUID,
    data: SubjectUpdate,
    db: DBSession,
    current_user: ResearcherUser,
):
    """
    피험자 정보 수정 (연구자 이상 권한 필요)
    """
    service = SubjectService(db)
    
    subject = await service.get_by_id(subject_id)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found",
        )
    
    # research_id 중복 체크 (변경 시)
    if data.research_id and data.research_id != subject.research_id:
        existing = await service.get_by_research_id(data.research_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Research ID '{data.research_id}' already exists",
            )
    
    updated = await service.update(subject_id, data)
    return SubjectResponse.model_validate(updated)


@router.delete(
    "/{subject_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_subject(
    subject_id: UUID,
    db: DBSession,
    current_user: ResearcherUser,
):
    """
    피험자 삭제 (연구자 이상 권한 필요)
    
    주의: 연관된 테스트 데이터도 함께 삭제됩니다.
    """
    service = SubjectService(db)
    
    subject = await service.get_by_id(subject_id)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found",
        )
    
    await service.delete(subject_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
