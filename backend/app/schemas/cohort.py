"""Cohort Analysis schemas - 코호트 분석 관련 Pydantic 스키마"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field


class CohortFilter(BaseModel):
    """코호트 필터 스키마"""
    gender: Optional[str] = Field(None, pattern="^(M|F|All|all)$", description="성별")
    age_min: Optional[int] = Field(None, ge=0, le=120, description="최소 나이")
    age_max: Optional[int] = Field(None, ge=0, le=120, description="최대 나이")
    training_level: Optional[str] = Field(
        None,
        pattern="^(Sedentary|Recreational|Trained|Elite|All)$",
        description="훈련 수준"
    )
    job_category: Optional[str] = Field(None, description="직업 카테고리")


class CohortSummaryRequest(BaseModel):
    """코호트 요약 요청 스키마"""
    filters: CohortFilter = Field(default_factory=CohortFilter)
    metrics: List[str] = Field(
        default=["vo2_max", "vo2_max_rel", "hr_max", "fat_max_g_min"],
        description="조회할 메트릭 목록"
    )


class MetricStats(BaseModel):
    """메트릭 통계 스키마"""
    metric_name: str
    mean: Optional[float] = None
    median: Optional[float] = None
    std_dev: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    percentile_10: Optional[float] = None
    percentile_25: Optional[float] = None
    percentile_75: Optional[float] = None
    percentile_90: Optional[float] = None
    sample_size: int = 0


class CohortSummaryResponse(BaseModel):
    """코호트 요약 응답 스키마"""
    filters_applied: CohortFilter
    total_subjects: int
    total_tests: int
    metrics: List[MetricStats]
    last_updated: datetime


class DistributionRequest(BaseModel):
    """분포 요청 스키마"""
    metric: str = Field(..., description="분포를 조회할 메트릭")
    filters: CohortFilter = Field(default_factory=CohortFilter)
    bins: int = Field(default=20, ge=5, le=100, description="히스토그램 빈 개수")


class DistributionBin(BaseModel):
    """분포 빈 스키마"""
    bin_start: float
    bin_end: float
    count: int
    percentage: float


class DistributionResponse(BaseModel):
    """분포 응답 스키마"""
    metric: str
    filters_applied: CohortFilter
    total_count: int
    bins: List[DistributionBin]
    mean: Optional[float] = None
    median: Optional[float] = None
    std_dev: Optional[float] = None


class PercentileRequest(BaseModel):
    """백분위 요청 스키마"""
    metric: str = Field(..., description="백분위를 계산할 메트릭")
    value: float = Field(..., description="백분위를 계산할 값")
    filters: CohortFilter = Field(default_factory=CohortFilter)


class PercentileResponse(BaseModel):
    """백분위 응답 스키마"""
    metric: str
    value: float
    percentile: float
    filters_applied: CohortFilter
    total_count: int


class ComparisonRequest(BaseModel):
    """비교 분석 요청 스키마"""
    subject_id: UUID = Field(..., description="비교할 피험자 ID")
    test_id: Optional[UUID] = Field(None, description="특정 테스트 (없으면 최신 테스트)")
    metrics: List[str] = Field(
        default=["vo2_max_rel", "hr_max", "fat_max_g_min"],
        description="비교할 메트릭 목록"
    )
    filters: CohortFilter = Field(default_factory=CohortFilter)


class MetricComparison(BaseModel):
    """메트릭 비교 스키마"""
    metric_name: str
    subject_value: Optional[float] = None
    cohort_mean: Optional[float] = None
    cohort_median: Optional[float] = None
    percentile: Optional[float] = None
    rating: Optional[str] = None  # "Below Average", "Average", "Above Average", "Excellent"


class ComparisonResponse(BaseModel):
    """비교 분석 응답 스키마"""
    subject_id: UUID
    test_id: UUID
    test_date: datetime
    filters_applied: CohortFilter
    cohort_size: int
    comparisons: List[MetricComparison]
