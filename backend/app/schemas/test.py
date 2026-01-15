"""CPET Test schemas - 테스트 관련 Pydantic 스키마"""

from datetime import datetime, time
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field


class CPETTestCreate(BaseModel):
    """테스트 생성 요청 스키마"""
    subject_id: UUID = Field(..., description="피험자 ID")
    test_date: datetime = Field(..., description="테스트 날짜")
    test_time: Optional[time] = Field(None, description="테스트 시간")
    protocol_name: Optional[str] = Field(None, max_length=100, description="프로토콜 이름")
    protocol_type: Optional[str] = Field(None, max_length=10, description="프로토콜 타입 (BxB/MIX)")
    test_type: str = Field(default="Maximal", description="테스트 유형")
    notes: Optional[str] = Field(None, description="메모")


class CPETTestUpdate(BaseModel):
    """테스트 업데이트 요청 스키마"""
    test_date: Optional[datetime] = None
    test_time: Optional[time] = None
    protocol_name: Optional[str] = Field(None, max_length=100)
    test_type: Optional[str] = None
    notes: Optional[str] = None
    # Analysis thresholds (수동 입력 가능)
    vt1_hr: Optional[int] = Field(None, ge=50, le=250)
    vt1_vo2: Optional[float] = Field(None, ge=0)
    vt2_hr: Optional[int] = Field(None, ge=50, le=250)
    vt2_vo2: Optional[float] = Field(None, ge=0)


class CPETTestResponse(BaseModel):
    """테스트 응답 스키마"""
    test_id: UUID
    subject_id: UUID
    test_date: datetime
    test_time: Optional[time] = None
    protocol_name: Optional[str] = None
    protocol_type: Optional[str] = None
    test_type: str
    maximal_effort: Optional[str] = None

    # Environmental
    barometric_pressure: Optional[float] = None
    ambient_temp: Optional[float] = None
    ambient_humidity: Optional[float] = None

    # Body metrics
    weight_kg: Optional[float] = None
    bsa: Optional[float] = None
    bmi: Optional[float] = None

    # Results
    vo2_max: Optional[float] = None
    vo2_max_rel: Optional[float] = None
    vco2_max: Optional[float] = None
    hr_max: Optional[int] = None

    # FATMAX
    fat_max_hr: Optional[int] = None
    fat_max_watt: Optional[float] = None
    fat_max_g_min: Optional[float] = None

    # Thresholds
    vt1_hr: Optional[int] = None
    vt1_vo2: Optional[float] = None
    vt2_hr: Optional[int] = None
    vt2_vo2: Optional[float] = None

    # File info
    source_filename: Optional[str] = None
    parsing_status: Optional[str] = None
    data_quality_score: Optional[float] = None

    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CPETTestListResponse(BaseModel):
    """테스트 목록 응답 스키마"""
    items: List[CPETTestResponse]
    total: int
    page: int
    page_size: int


class BreathDataPoint(BaseModel):
    """호흡 데이터 포인트 스키마"""
    time: datetime
    t_sec: Optional[float] = None
    vo2: Optional[float] = None
    vco2: Optional[float] = None
    ve: Optional[float] = None
    hr: Optional[int] = None
    rer: Optional[float] = None
    fat_oxidation: Optional[float] = None
    cho_oxidation: Optional[float] = None
    bike_power: Optional[int] = None
    phase: Optional[str] = None


class TimeSeriesRequest(BaseModel):
    """시계열 데이터 요청 스키마"""
    signals: List[str] = Field(
        default=["vo2", "vco2", "hr", "rer"],
        description="조회할 신호 목록"
    )
    interval: str = Field(default="1s", pattern="^\\d+s$", description="다운샘플링 간격")
    method: str = Field(
        default="mean",
        pattern="^(mean|median|max|min)$",
        description="집계 방식"
    )
    start_sec: Optional[float] = Field(None, description="시작 시간 (초)")
    end_sec: Optional[float] = Field(None, description="종료 시간 (초)")


class TimeSeriesResponse(BaseModel):
    """시계열 데이터 응답 스키마"""
    test_id: UUID
    signals: List[str]
    interval: str
    data_points: List[Dict[str, Any]]
    total_points: int
    duration_sec: float


class TestMetricsResponse(BaseModel):
    """테스트 메트릭 요약 응답 스키마"""
    test_id: UUID
    subject_id: UUID

    # VO2 metrics
    vo2_max: Optional[float] = None
    vo2_max_rel: Optional[float] = None
    vo2_at_vt1: Optional[float] = None
    vo2_at_vt2: Optional[float] = None

    # HR metrics
    hr_max: Optional[int] = None
    hr_at_vt1: Optional[int] = None
    hr_at_vt2: Optional[int] = None
    hr_reserve: Optional[int] = None

    # FATMAX metrics
    fat_max_hr: Optional[int] = None
    fat_max_watt: Optional[float] = None
    fat_max_g_min: Optional[float] = None
    fat_max_zone_lower: Optional[int] = None
    fat_max_zone_upper: Optional[int] = None

    # VCO2 / RER
    vco2_max: Optional[float] = None
    rer_max: Optional[float] = None

    # Duration
    test_duration_sec: Optional[float] = None
    exercise_duration_sec: Optional[float] = None

    # Phases
    phases: Optional[Dict[str, Any]] = None


class TestUploadResponse(BaseModel):
    """테스트 파일 업로드 응답 스키마"""
    test_id: UUID
    subject_id: UUID
    source_filename: str
    parsing_status: str
    parsing_errors: Optional[List[str]] = None
    parsing_warnings: Optional[List[str]] = None
    data_points_count: int
    created_at: datetime
