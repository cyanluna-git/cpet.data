"""CPET Test schemas - 테스트 관련 Pydantic 스키마"""

from datetime import datetime, time
from typing import Optional, Dict, Any, List
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, model_validator


# =========================================
# Data Validation Schemas
# =========================================


class ProtocolType(str, Enum):
    """프로토콜 타입 열거형"""

    RAMP = "RAMP"  # 선형 증가 프로토콜 (r >= 0.85)
    INTERVAL = "INTERVAL"  # 인터벌 트레이닝 (r < 0.85, 변동 심함)
    STEADY_STATE = "STEADY_STATE"  # 정상 상태 (r < 0.85, 변동 적음)
    UNKNOWN = "UNKNOWN"  # 분류 불가


class ValidationResult(BaseModel):
    """데이터 검증 결과 스키마"""

    is_valid: bool = Field(..., description="데이터 사용 가능 여부")
    protocol_type: ProtocolType = Field(
        default=ProtocolType.UNKNOWN, description="프로토콜 타입"
    )
    reason: List[str] = Field(default_factory=list, description="검증 실패 사유")
    quality_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="데이터 품질 점수 (0.0-1.0)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="검증 메타데이터"
    )

    # 검증 세부 정보
    has_essential_columns: bool = Field(default=False)
    duration_valid: bool = Field(default=False)
    intensity_valid: bool = Field(default=False)
    hr_integrity: bool = Field(default=False)
    gas_integrity: bool = Field(default=False)

    # 프로토콜 분류 메트릭
    power_time_correlation: Optional[float] = Field(
        None, description="Power-Time 상관계수 (r)"
    )

    model_config = {"from_attributes": True}


class CPETTestCreate(BaseModel):
    """테스트 생성 요청 스키마"""

    subject_id: UUID = Field(..., description="피험자 ID")
    test_date: datetime = Field(..., description="테스트 날짜")
    test_time: Optional[time] = Field(None, description="테스트 시간")
    protocol_name: Optional[str] = Field(
        None, max_length=100, description="프로토콜 이름"
    )
    protocol_type: Optional[str] = Field(
        None, max_length=10, description="프로토콜 타입 (BxB/MIX)"
    )
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
    is_valid: Optional[bool] = Field(
        None, description="데이터 유효성 (quality_score >= 0.7)"
    )

    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def compute_is_valid(self):
        """data_quality_score를 기반으로 is_valid 계산"""
        if self.data_quality_score is not None:
            self.is_valid = self.data_quality_score >= 0.7
        return self


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
        default=["vo2", "vco2", "hr", "rer"], description="조회할 신호 목록"
    )
    interval: str = Field(
        default="1s", pattern="^\\d+s$", description="다운샘플링 간격"
    )
    method: str = Field(
        default="mean", pattern="^(mean|median|max|min)$", description="집계 방식"
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


# =========================================
# 분석 결과 스키마 (Analysis)
# =========================================


class PhaseInfo(BaseModel):
    """구간 정보 스키마"""

    phase: str
    start_sec: float
    end_sec: float


class PhaseBoundaries(BaseModel):
    """구간 경계 스키마"""

    rest_end_sec: Optional[float] = None
    warmup_end_sec: Optional[float] = None
    exercise_end_sec: Optional[float] = None
    peak_sec: Optional[float] = None
    total_duration_sec: Optional[float] = None
    phases: List[PhaseInfo] = []


class PhaseMetrics(BaseModel):
    """구간별 메트릭 스키마"""

    duration_sec: Optional[float] = None
    data_points: Optional[int] = None
    avg_hr: Optional[float] = None
    max_hr: Optional[float] = None
    avg_vo2: Optional[float] = None
    max_vo2: Optional[float] = None
    avg_rer: Optional[float] = None
    max_rer: Optional[float] = None
    avg_fat_oxidation: Optional[float] = None
    max_fat_oxidation: Optional[float] = None
    avg_cho_oxidation: Optional[float] = None
    max_cho_oxidation: Optional[float] = None
    avg_bike_power: Optional[float] = None
    max_bike_power: Optional[float] = None


class FatMaxInfo(BaseModel):
    """FATMAX 정보 스키마"""

    fat_max_g_min: Optional[float] = None
    fat_max_hr: Optional[int] = None
    fat_max_watt: Optional[float] = None
    fat_max_vo2: Optional[float] = None
    fat_max_rer: Optional[float] = None
    fat_max_time_sec: Optional[float] = None


class VO2MaxInfo(BaseModel):
    """VO2MAX 정보 스키마"""

    vo2_max: Optional[float] = None
    vo2_max_rel: Optional[float] = None
    vco2_max: Optional[float] = None
    hr_max: Optional[int] = None
    rer_at_max: Optional[float] = None
    vo2_max_time_sec: Optional[float] = None


# =========================================
# 처리된 대사 데이터 스키마 (Processed Metabolism Data)
# =========================================


class ProcessedDataPoint(BaseModel):
    """처리된 데이터 포인트 스키마"""

    power: float
    fat_oxidation: Optional[float] = None
    cho_oxidation: Optional[float] = None
    rer: Optional[float] = None
    count: Optional[int] = None  # binned data only
    vo2: Optional[float] = None  # VO2 for VO2 Kinetics chart
    vco2: Optional[float] = None  # VCO2 for VO2 Kinetics chart
    hr: Optional[float] = None  # HR for VO2 Kinetics chart
    ve_vo2: Optional[float] = None  # VE/VO2 for VT Analysis chart
    ve_vco2: Optional[float] = None  # VE/VCO2 for VT Analysis chart


class ProcessedSeries(BaseModel):
    """처리된 시계열 데이터 스키마"""

    raw: List[ProcessedDataPoint] = []  # 원본 데이터
    binned: List[ProcessedDataPoint] = []  # 10W 구간 평균/중앙값
    smoothed: List[ProcessedDataPoint] = []  # LOESS smoothed
    trend: List[ProcessedDataPoint] = []  # Polynomial trend


class FatMaxMarker(BaseModel):
    """FatMax 마커 정보 스키마"""

    power: int = 0  # FatMax 지점 파워 (W)
    mfo: float = 0.0  # Maximum Fat Oxidation (g/min)
    zone_min: int = 0  # FatMax zone 하한 (W)
    zone_max: int = 0  # FatMax zone 상한 (W)


class CrossoverMarker(BaseModel):
    """Crossover 지점 마커 스키마"""

    power: Optional[int] = None  # Crossover 지점 파워 (W), 없으면 None
    fat_value: Optional[float] = None  # 교차 지점 FatOx 값
    cho_value: Optional[float] = None  # 교차 지점 CHOOx 값


class MetabolicMarkers(BaseModel):
    """대사 마커 정보 스키마"""

    fat_max: FatMaxMarker = FatMaxMarker()
    crossover: CrossoverMarker = CrossoverMarker()


class MetabolismDataPoint(BaseModel):
    """대사 차트 데이터 포인트"""

    time_sec: float
    power: Optional[float] = None
    hr: Optional[int] = None
    vo2: Optional[float] = None
    vco2: Optional[float] = None
    rer: Optional[float] = None
    fat_oxidation: Optional[float] = None
    cho_oxidation: Optional[float] = None
    fat_kcal_day: Optional[float] = None  # kcal/day 환산
    cho_kcal_day: Optional[float] = None  # kcal/day 환산
    phase: Optional[str] = None


class TrimRange(BaseModel):
    """Analysis window trimming range schema"""

    start_sec: float  # Trimmed start time (seconds)
    end_sec: float  # Trimmed end time (seconds)
    auto_detected: bool = True  # False if manually specified
    max_power_sec: Optional[float] = None  # Time of peak power (for reference)


class TestAnalysisResponse(BaseModel):
    """테스트 분석 결과 응답 스키마 (대사 프로파일 차트용)"""

    test_id: UUID
    subject_id: UUID
    test_date: datetime
    protocol_type: Optional[str] = None
    calc_method: str = "Frayn"

    # 구간 정보
    phase_boundaries: Optional[PhaseBoundaries] = None
    phase_metrics: Optional[Dict[str, PhaseMetrics]] = None

    # 주요 지표
    fatmax: Optional[FatMaxInfo] = None
    vo2max: Optional[VO2MaxInfo] = None

    # VT 정보 (옵션)
    vt1_hr: Optional[int] = None
    vt1_vo2: Optional[float] = None
    vt2_hr: Optional[int] = None
    vt2_vo2: Optional[float] = None

    # 시계열 데이터 (차트용)
    timeseries: List[MetabolismDataPoint] = []
    timeseries_interval: str = "5s"  # 다운샘플링 간격

    # 요약 통계
    total_fat_burned_g: Optional[float] = None
    total_cho_burned_g: Optional[float] = None
    avg_rer: Optional[float] = None
    exercise_duration_sec: Optional[float] = None

    # 처리된 데이터 (LOESS smoothing, binning)
    processed_series: Optional[ProcessedSeries] = None
    metabolic_markers: Optional[MetabolicMarkers] = None
    analysis_warnings: Optional[List[str]] = None

    # Trimming info (NEW)
    used_trim_range: Optional[TrimRange] = None  # Applied analysis window
    total_duration_sec: Optional[float] = None  # Total test duration for slider


class RawBreathDataRow(BaseModel):
    """Raw breath data 행 스키마"""

    id: Optional[int] = None
    time: datetime
    t_sec: Optional[float] = None
    rf: Optional[float] = None
    vt: Optional[float] = None
    vo2: Optional[float] = None
    vco2: Optional[float] = None
    ve: Optional[float] = None
    hr: Optional[int] = None
    vo2_hr: Optional[float] = None
    bike_power: Optional[int] = None
    bike_torque: Optional[float] = None
    cadence: Optional[int] = None
    feo2: Optional[float] = None
    feco2: Optional[float] = None
    feto2: Optional[float] = None
    fetco2: Optional[float] = None
    ve_vo2: Optional[float] = None
    ve_vco2: Optional[float] = None
    rer: Optional[float] = None
    fat_oxidation: Optional[float] = None
    cho_oxidation: Optional[float] = None
    vo2_rel: Optional[float] = None
    mets: Optional[float] = None
    ee_total: Optional[float] = None
    phase: Optional[str] = None
    data_source: Optional[str] = None
    is_valid: bool = True

    model_config = {"from_attributes": True}


class RawBreathDataResponse(BaseModel):
    """Raw breath data 응답 스키마"""

    test_id: UUID
    source_filename: Optional[str] = None
    test_date: datetime
    subject_name: Optional[str] = None
    total_rows: int
    data: List[RawBreathDataRow]
