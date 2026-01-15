"""Cohorts API Router - 코호트 분석 관련 엔드포인트"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import ResearcherUser, DBSession
from app.schemas.cohort import (
    CohortFilter,
    CohortSummaryRequest,
    CohortSummaryResponse,
    DistributionRequest,
    DistributionResponse,
    PercentileRequest,
    PercentileResponse,
    ComparisonRequest,
    ComparisonResponse,
)
from app.services import CohortService

router = APIRouter(prefix="/cohorts", tags=["Cohort Analysis"])


@router.get("/summary", response_model=CohortSummaryResponse)
async def get_cohort_summary(
    db: DBSession,
    current_user: ResearcherUser,
    gender: Optional[str] = Query(None, description="성별 필터 (M/F/All)"),
    age_min: Optional[int] = Query(None, ge=0, description="최소 나이"),
    age_max: Optional[int] = Query(None, le=120, description="최대 나이"),
    training_level: Optional[str] = Query(None, description="훈련 수준"),
    metrics: str = Query(
        "vo2_max,vo2_max_rel,hr_max,fat_max_g_min",
        description="통계 계산할 지표 (콤마 구분)"
    ),
):
    """
    코호트 요약 통계 조회
    
    선택된 필터 조건에 맞는 피험자들의 주요 지표 통계를 반환합니다.
    """
    service = CohortService(db)
    
    filters = CohortFilter(
        gender=gender,
        age_min=age_min,
        age_max=age_max,
        training_level=training_level,
    )
    
    metric_list = [m.strip().lower() for m in metrics.split(",")]
    result = await service.get_summary(filters, metric_list)
    return CohortSummaryResponse(**result)


@router.post("/summary", response_model=CohortSummaryResponse)
async def get_cohort_summary_post(
    request: CohortSummaryRequest,
    db: DBSession,
    current_user: ResearcherUser,
):
    """코호트 요약 통계 조회 (POST)"""
    service = CohortService(db)
    result = await service.get_summary(request.filters, request.metrics)
    return CohortSummaryResponse(**result)


@router.get("/distribution", response_model=DistributionResponse)
async def get_distribution(
    db: DBSession,
    current_user: ResearcherUser,
    metric: str = Query(..., description="분포 조회할 지표"),
    bins: int = Query(20, ge=5, le=100, description="히스토그램 빈 개수"),
    gender: Optional[str] = Query(None),
    age_min: Optional[int] = Query(None, ge=0),
    age_max: Optional[int] = Query(None, le=120),
    training_level: Optional[str] = Query(None),
):
    """지표 분포 조회 (히스토그램)"""
    service = CohortService(db)
    
    filters = CohortFilter(
        gender=gender,
        age_min=age_min,
        age_max=age_max,
        training_level=training_level,
    )
    
    try:
        result = await service.get_distribution(metric.lower(), filters, bins)
        return DistributionResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/distribution", response_model=DistributionResponse)
async def get_distribution_post(
    request: DistributionRequest,
    db: DBSession,
    current_user: ResearcherUser,
):
    """지표 분포 조회 (POST)"""
    service = CohortService(db)
    try:
        result = await service.get_distribution(
            request.metric.lower(),
            request.filters,
            request.bins,
        )
        return DistributionResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/percentile", response_model=PercentileResponse)
async def get_percentile(
    db: DBSession,
    current_user: ResearcherUser,
    metric: str = Query(..., description="백분위 계산할 지표"),
    value: float = Query(..., description="백분위를 계산할 값"),
    gender: Optional[str] = Query(None),
    age_min: Optional[int] = Query(None, ge=0),
    age_max: Optional[int] = Query(None, le=120),
    training_level: Optional[str] = Query(None),
):
    """특정 값의 백분위 계산"""
    service = CohortService(db)
    
    filters = CohortFilter(
        gender=gender,
        age_min=age_min,
        age_max=age_max,
        training_level=training_level,
    )
    
    try:
        result = await service.get_percentile(metric.lower(), value, filters)
        return PercentileResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/percentile", response_model=PercentileResponse)
async def get_percentile_post(
    request: PercentileRequest,
    db: DBSession,
    current_user: ResearcherUser,
):
    """특정 값의 백분위 계산 (POST)"""
    service = CohortService(db)
    try:
        result = await service.get_percentile(
            request.metric.lower(),
            request.value,
            request.filters,
        )
        return PercentileResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/comparison", response_model=ComparisonResponse)
async def get_comparison(
    request: ComparisonRequest,
    db: DBSession,
    current_user: ResearcherUser,
):
    """피험자-코호트 비교 분석"""
    service = CohortService(db)
    try:
        result = await service.get_comparison(
            subject_id=request.subject_id,
            test_id=request.test_id,
            metrics=request.metrics,
            filters=request.filters,
        )
        return ComparisonResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats")
async def get_overall_stats(
    db: DBSession,
    current_user: ResearcherUser,
):
    """
    전체 데이터베이스 통계 조회
    
    총 피험자 수, 테스트 수 등 전체 현황 반환
    """
    service = CohortService(db)
    stats = await service.get_overall_stats()
    return stats
