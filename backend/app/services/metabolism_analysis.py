"""Metabolic Analysis Service - 대사 데이터 분석 파이프라인

Power binning, LOESS smoothing, FatMax/Crossover 마커 계산을 수행합니다.

Features:
- Configurable 10W Power Binning (Median/Mean/Trimmed Mean)
- LOESS smoothing with adjustable fraction
- Phase trimming (Rest/Warm-up/Recovery 제외)
- FatMax (Peak fat oxidation) + Zone (90% MFO) 계산
- Crossover Point (Fat = CHO intersection) 계산
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any, Literal
import math
import logging
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from scipy.optimize import brentq
from scipy.stats import trim_mean

logger = logging.getLogger(__name__)

try:
    from statsmodels.nonparametric.smoothers_lowess import lowess

    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False
    lowess = None


@dataclass
class ProcessedDataPoint:
    """처리된 데이터 포인트"""

    power: float
    fat_oxidation: Optional[float]
    cho_oxidation: Optional[float]
    count: Optional[int] = None  # binned data only
    vo2: Optional[float] = None  # VO2 for relative calculations and VO2 Kinetics chart
    vo2_rel: Optional[float] = None  # VO2/kg (ml/min/kg) for FATMAX chart
    rer: Optional[float] = None  # RER
    vco2: Optional[float] = None  # lrmad VCO2 for VO2 Kinetics chart
    hr: Optional[float] = None  # HR for VO2 Kinetics chart
    ve_vo2: Optional[float] = None  # VE/VO2 for VT Analysis chart
    ve_vco2: Optional[float] = None  # VE/VCO2 for VT Analysis chart

    def to_dict(self) -> Dict[str, Any]:
        """모든 필드를 항상 포함하여 프론트엔드에서 키 존재 여부 체크가 가능하도록 함"""
        return {
            "power": self.power,
            "fat_oxidation": self.fat_oxidation,
            "cho_oxidation": self.cho_oxidation,
            "count": self.count,
            "vo2": self.vo2,
            "vo2_rel": self.vo2_rel,
            "vco2": self.vco2,
            "rer": self.rer,
            "hr": self.hr,
            "ve_vo2": self.ve_vo2,
            "ve_vco2": self.ve_vco2,
        }


@dataclass
class FatMaxMarker:
    """FatMax 마커 정보"""

    power: int  # FatMax 지점 파워 (W)
    mfo: float  # Maximum Fat Oxidation (g/min)
    zone_min: int  # FatMax zone 하한 (W)
    zone_max: int  # FatMax zone 상한 (W)
    mfo_ci_lower: Optional[float] = None  # Bootstrap 95% CI lower bound (g/min)
    mfo_ci_upper: Optional[float] = None  # Bootstrap 95% CI upper bound (g/min)
    power_ci_lower: Optional[int] = None  # Bootstrap 95% CI lower bound (W)
    power_ci_upper: Optional[int] = None  # Bootstrap 95% CI upper bound (W)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "power": self.power,
            "mfo": round(self.mfo, 4),
            "zone_min": self.zone_min,
            "zone_max": self.zone_max,
        }
        # Only include CI fields when computed (backward compatible)
        if self.mfo_ci_lower is not None:
            result["mfo_ci_lower"] = round(self.mfo_ci_lower, 4)
        if self.mfo_ci_upper is not None:
            result["mfo_ci_upper"] = round(self.mfo_ci_upper, 4)
        if self.power_ci_lower is not None:
            result["power_ci_lower"] = self.power_ci_lower
        if self.power_ci_upper is not None:
            result["power_ci_upper"] = self.power_ci_upper
        return result


@dataclass
class CrossoverMarker:
    """Crossover 지점 마커 정보"""

    power: Optional[int]  # Crossover 지점 파워 (W), 없으면 None
    fat_value: Optional[float]  # 교차 지점 FatOx 값
    cho_value: Optional[float]  # 교차 지점 CHOOx 값
    confidence: Optional[float] = None  # 부호 변화 크기 (|d1 - d2|)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "power": self.power,
            "fat_value": (
                round(self.fat_value, 4) if self.fat_value is not None else None
            ),
            "cho_value": (
                round(self.cho_value, 4) if self.cho_value is not None else None
            ),
        }
        if self.confidence is not None:
            result["confidence"] = round(self.confidence, 4)
        return result


@dataclass
class MetabolicMarkers:
    """대사 마커 정보"""

    fat_max: FatMaxMarker
    crossover: CrossoverMarker
    all_crossovers: Optional[List[CrossoverMarker]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "fat_max": self.fat_max.to_dict(),
            "crossover": self.crossover.to_dict(),
        }
        if self.all_crossovers is not None:
            result["all_crossovers"] = [c.to_dict() for c in self.all_crossovers]
        return result


@dataclass
class ProcessedSeries:
    """처리된 시계열 데이터"""

    raw: List[ProcessedDataPoint]  # 원본 데이터
    binned: List[ProcessedDataPoint]  # 10W 구간 평균/중앙값
    smoothed: List[ProcessedDataPoint]  # LOESS smoothed
    trend: List[ProcessedDataPoint] = field(default_factory=list)  # Polynomial fit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw": [p.to_dict() for p in self.raw],
            "binned": [p.to_dict() for p in self.binned],
            "smoothed": [p.to_dict() for p in self.smoothed],
            "trend": [p.to_dict() for p in self.trend],  # 항상 포함 (빈 리스트도 포함)
        }


@dataclass
class TrimRange:
    """Analysis window trimming range (time-based)"""

    start_sec: float  # Trimmed start time (seconds)
    end_sec: float  # Trimmed end time (seconds)
    auto_detected: bool = True  # False if manually specified
    max_power_sec: Optional[float] = None  # Time of peak power (for reference)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_sec": round(self.start_sec, 1),
            "end_sec": round(self.end_sec, 1),
            "auto_detected": self.auto_detected,
            "max_power_sec": (
                round(self.max_power_sec, 1) if self.max_power_sec else None
            ),
        }


@dataclass
class MetabolismAnalysisResult:
    """대사 분석 결과"""

    processed_series: ProcessedSeries
    metabolic_markers: MetabolicMarkers
    warnings: List[str]
    trim_range: Optional[TrimRange] = None  # Analysis window trimming info

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "processed_series": self.processed_series.to_dict(),
            "metabolic_markers": self.metabolic_markers.to_dict(),
            "warnings": self.warnings,
        }
        if self.trim_range:
            result["trim_range"] = self.trim_range.to_dict()
        return result


@dataclass
class AnalysisConfig:
    """분석 설정 dataclass"""

    loess_frac: float = 0.25
    bin_size: int = 10
    aggregation_method: Literal["median", "mean", "trimmed_mean"] = "median"
    trimmed_mean_proportiontocut: float = 0.1  # trimmed_mean 사용시 양쪽 10% 절삭
    fatmax_zone_threshold: float = 0.90
    exclude_rest: bool = True
    exclude_warmup: bool = True
    exclude_recovery: bool = True
    min_power_threshold: Optional[int] = None  # e.g., 50W 미만 제외
    max_power_threshold: Optional[int] = None  # e.g., 400W 초과 제외
    non_negative_constraint: bool = True  # 음수 값 0으로 클램핑
    # Initial hyperventilation filtering (RER spike at start)
    exclude_initial_hyperventilation: bool = True
    initial_time_threshold: float = 120.0  # seconds - first 2 minutes
    initial_power_threshold: int = 40  # watts - exclude low power data during startup
    # Time-based analysis window trimming (excludes Rest/Recovery phases)
    auto_trim_enabled: bool = True  # Enable auto-detection of analysis window
    trim_start_sec: Optional[float] = None  # Manual override for start (seconds)
    trim_end_sec: Optional[float] = None  # Manual override for end (seconds)
    start_power_threshold: int = 20  # Watts - first power above this starts window
    start_time_buffer: float = 30.0  # Seconds buffer after first power >= threshold
    recovery_power_ratio: float = 0.8  # End when power drops below this * max_power
    # v1.1.0: Outlier detection
    outlier_detection_enabled: bool = True
    outlier_iqr_multiplier: float = 1.5
    # v1.1.0: Sparse bin merging
    min_bin_count: int = 3
    # v1.1.0: Adaptive LOESS fraction
    adaptive_loess: bool = True
    # v1.1.0: Protocol-aware trimming
    protocol_type: Optional[str] = None  # "ramp", "step", "graded", None
    # v1.1.0: Cross-validation polynomial degree
    adaptive_polynomial: bool = True
    # v1.1.0: FatMax bootstrap confidence interval
    fatmax_confidence_interval: bool = False  # Default off (computational cost)
    fatmax_bootstrap_iterations: int = 500

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loess_frac": self.loess_frac,
            "bin_size": self.bin_size,
            "aggregation_method": self.aggregation_method,
            "fatmax_zone_threshold": self.fatmax_zone_threshold,
            "exclude_rest": self.exclude_rest,
            "exclude_warmup": self.exclude_warmup,
            "exclude_recovery": self.exclude_recovery,
            "min_power_threshold": self.min_power_threshold,
            "max_power_threshold": self.max_power_threshold,
            "non_negative_constraint": self.non_negative_constraint,
            "exclude_initial_hyperventilation": self.exclude_initial_hyperventilation,
            "initial_time_threshold": self.initial_time_threshold,
            "initial_power_threshold": self.initial_power_threshold,
            "auto_trim_enabled": self.auto_trim_enabled,
            "trim_start_sec": self.trim_start_sec,
            "trim_end_sec": self.trim_end_sec,
            "start_power_threshold": self.start_power_threshold,
            "start_time_buffer": self.start_time_buffer,
            "recovery_power_ratio": self.recovery_power_ratio,
            "outlier_detection_enabled": self.outlier_detection_enabled,
            "outlier_iqr_multiplier": self.outlier_iqr_multiplier,
            "min_bin_count": self.min_bin_count,
            "adaptive_loess": self.adaptive_loess,
            "protocol_type": self.protocol_type,
            "adaptive_polynomial": self.adaptive_polynomial,
            "fatmax_confidence_interval": self.fatmax_confidence_interval,
            "fatmax_bootstrap_iterations": self.fatmax_bootstrap_iterations,
        }


class MetabolismAnalyzer:
    """대사 데이터 분석기

    Features:
    - Configurable power binning (5W~30W)
    - Multiple aggregation methods (median, mean, trimmed_mean)
    - LOESS smoothing with adjustable fraction
    - Phase trimming options
    - FatMax and Crossover calculation
    """

    def __init__(
        self,
        loess_frac: float = 0.25,
        bin_size: int = 10,
        use_median: bool = True,
        fatmax_zone_threshold: float = 0.90,
        config: Optional[AnalysisConfig] = None,
    ):
        """
        Args:
            loess_frac: LOESS smoothing fraction (0.1 ~ 0.5 권장)
            bin_size: Power binning 크기 (W), 5~30W 범위
            use_median: True면 중앙값, False면 평균 사용 (deprecated, use config)
            fatmax_zone_threshold: FatMax zone 임계값 (MFO의 비율)
            config: AnalysisConfig 객체 (제공시 다른 파라미터 무시)
        """
        if config:
            self.config = config
        else:
            self.config = AnalysisConfig(
                loess_frac=loess_frac,
                bin_size=max(5, min(30, bin_size)),  # 5~30W 범위 제한
                aggregation_method="median" if use_median else "mean",
                fatmax_zone_threshold=fatmax_zone_threshold,
            )
        self.warnings: List[str] = []

    def analyze(self, breath_data: List[Any]) -> Optional[MetabolismAnalysisResult]:
        """
        호흡 데이터를 분석하여 처리된 시계열과 마커를 반환합니다.

        Args:
            breath_data: BreathData 객체 리스트 (bike_power, fat_oxidation, cho_oxidation 필수)

        Returns:
            MetabolismAnalysisResult 또는 None (데이터 부족 시)
        """
        self.warnings = []
        trim_range = None

        # 0. Time-based analysis window trimming (before phase filtering)
        if (
            self.config.auto_trim_enabled
            or self.config.trim_start_sec is not None
            or self.config.trim_end_sec is not None
        ):
            breath_data, trim_range = self._detect_analysis_window(breath_data)
            if trim_range:
                logger.info(
                    f"🔧 [TRIM] Applied window: {trim_range.start_sec:.1f}s - {trim_range.end_sec:.1f}s (auto={trim_range.auto_detected})"
                )

        # Phase trimming: 구간별 제외 옵션 적용
        filtered_data = self._apply_phase_trimming(breath_data)

        if len(filtered_data) < 10:
            self.warnings.append(
                f"Insufficient exercise data for analysis: {len(filtered_data)} points"
            )
            return None

        # 1. Raw 데이터 추출
        raw_points = self._extract_raw_points(filtered_data)

        if len(raw_points) < 5:
            self.warnings.append("Insufficient raw data points after extraction")
            return None

        # 1.5. IQR 기반 이상치 제거 (raw는 원본 유지, cleaned만 binning에 전달)
        raw_points_clean = self._detect_and_remove_outliers(raw_points)

        # 2. Power Binning
        binned_points = self._power_binning(raw_points_clean)

        if len(binned_points) < 3:
            self.warnings.append("Insufficient binned data points")
            return None

        # 3. LOESS Smoothing
        smoothed_points = self._loess_smoothing(binned_points)

        # 4. Polynomial Trend Fit (binned 데이터에서 직접 계산하여 깔끔한 포물선 생성)
        trend_points = self._polynomial_fit(binned_points)

        # 5. FatMax & Zone 계산
        fatmax_marker = self._calculate_fatmax(smoothed_points)

        # 6. Crossover Point 계산
        crossover_marker, all_crossovers = self._calculate_crossover(smoothed_points)

        return MetabolismAnalysisResult(
            processed_series=ProcessedSeries(
                raw=raw_points,
                binned=binned_points,
                smoothed=smoothed_points,
                trend=trend_points,
            ),
            metabolic_markers=MetabolicMarkers(
                fat_max=fatmax_marker,
                crossover=crossover_marker,
                all_crossovers=all_crossovers,
            ),
            warnings=self.warnings,
            trim_range=trim_range,
        )

    def _detect_analysis_window(
        self, breath_data: List[Any]
    ) -> Tuple[List[Any], Optional[TrimRange]]:
        """
        Auto-detect or apply manual analysis window, excluding Rest/Recovery.

        Algorithm:
        1. If manual trim_start_sec/trim_end_sec provided, use those
        2. Otherwise auto-detect:
           - End Point: Find max power index, scan forward until power < 0.8 * max
           - Start Point: Find first power >= 20W, add 30s buffer

        Returns:
            Tuple of (trimmed_data, TrimRange)
        """
        if not breath_data:
            return breath_data, None

        # Extract t_sec and power values
        data_with_time = []
        for bd in breath_data:
            t_sec = getattr(bd, "t_sec", None)
            power = getattr(bd, "bike_power", None) or 0
            if t_sec is not None:
                data_with_time.append((t_sec, power, bd))

        if not data_with_time:
            logger.warning("🔧 [TRIM] No t_sec data found, skipping trimming")
            return breath_data, None

        # Sort by time
        data_with_time.sort(key=lambda x: x[0])
        times = [d[0] for d in data_with_time]
        powers = [d[1] for d in data_with_time]

        # Determine start and end times
        manual_start = self.config.trim_start_sec
        manual_end = self.config.trim_end_sec
        auto_detected = manual_start is None and manual_end is None

        # Protocol-aware parameter overrides
        effective_recovery_ratio = self.config.recovery_power_ratio
        effective_start_threshold = self.config.start_power_threshold
        if self.config.protocol_type:
            ptype = self.config.protocol_type.lower()
            if ptype == "ramp":
                effective_recovery_ratio = 0.70
                effective_start_threshold = 30
            elif ptype in ("step", "graded"):
                effective_recovery_ratio = 0.85
                effective_start_threshold = 20

        # ========== AUTO-DETECT END POINT ==========
        if manual_end is not None:
            end_sec = manual_end
            max_power_sec = None
        else:
            # Find max power and its index
            max_power = max(powers) if powers else 0
            max_power_idx = (
                powers.index(max_power) if max_power > 0 else len(powers) - 1
            )
            max_power_sec = times[max_power_idx]

            # Scan forward from max power to find recovery start
            recovery_threshold = max_power * effective_recovery_ratio
            end_idx = max_power_idx

            for i in range(max_power_idx + 1, len(powers)):
                if powers[i] < recovery_threshold:
                    end_idx = i
                    break
            else:
                end_idx = len(powers) - 1

            end_sec = times[end_idx]
            logger.debug(
                f"🔧 [TRIM] Auto-detected end: {end_sec:.1f}s (max_power={max_power:.0f}W at {max_power_sec:.1f}s)"
            )

        # ========== AUTO-DETECT START POINT ==========
        if manual_start is not None:
            start_sec = manual_start
        else:
            # Find first power >= threshold
            start_threshold = effective_start_threshold
            start_idx = 0

            for i, power in enumerate(powers):
                if power >= start_threshold:
                    start_idx = i
                    break

            # Add time buffer
            initial_start_sec = times[start_idx]
            start_sec = initial_start_sec + self.config.start_time_buffer

            # Ensure start doesn't exceed end
            if start_sec >= end_sec:
                start_sec = initial_start_sec  # Fallback to first valid point

            logger.debug(
                f"🔧 [TRIM] Auto-detected start: {start_sec:.1f}s (first {start_threshold}W at {initial_start_sec:.1f}s)"
            )

        # ========== APPLY TRIMMING ==========
        trimmed_data = [bd for t, p, bd in data_with_time if start_sec <= t <= end_sec]

        logger.info(
            f"🔧 [TRIM] Trimmed {len(breath_data)} -> {len(trimmed_data)} points ({start_sec:.1f}s - {end_sec:.1f}s)"
        )

        trim_range = TrimRange(
            start_sec=start_sec,
            end_sec=end_sec,
            auto_detected=auto_detected,
            max_power_sec=max_power_sec if auto_detected else None,
        )

        return trimmed_data, trim_range

    def _apply_phase_trimming(self, breath_data: List[Any]) -> List[Any]:
        """Phase trimming 적용: Rest, Warm-up, Recovery 구간 제외"""
        # Debug: Check input data before filtering
        if breath_data:
            first = breath_data[0]
            logger.warning(
                f"🔍 [PHASE_TRIM] Input: {len(breath_data)} points, first.vo2={getattr(first, 'vo2', 'MISSING')}"
            )

        filtered = []

        for bd in breath_data:
            # 필수 필드 체크
            if (
                bd.bike_power is None
                or bd.fat_oxidation is None
                or bd.cho_oxidation is None
            ):
                continue

            # Initial hyperventilation filtering (RER spike at start)
            # Exclude data points where both time < threshold AND power < threshold
            if self.config.exclude_initial_hyperventilation:
                t_sec = getattr(bd, "t_sec", None)
                if t_sec is not None and t_sec < self.config.initial_time_threshold:
                    if bd.bike_power < self.config.initial_power_threshold:
                        continue

            phase = getattr(bd, "phase", None) or ""

            # Phase 기반 필터링
            if self.config.exclude_rest and phase.lower() in ("rest", "resting"):
                continue
            if self.config.exclude_warmup and phase.lower() in (
                "warmup",
                "warm-up",
                "warm_up",
            ):
                continue
            if self.config.exclude_recovery and phase.lower() in (
                "recovery",
                "cooldown",
                "cool-down",
            ):
                continue

            # Exercise/Peak 구간만 포함 (기본)
            if phase and phase not in ("Exercise", "Peak", "exercise", "peak", ""):
                continue

            # Power threshold 필터링
            if self.config.min_power_threshold is not None:
                if bd.bike_power < self.config.min_power_threshold:
                    continue
            if self.config.max_power_threshold is not None:
                if bd.bike_power > self.config.max_power_threshold:
                    continue

            filtered.append(bd)

        # Debug: Check output data after filtering
        if filtered:
            first = filtered[0]
            logger.warning(
                f"🔍 [PHASE_TRIM] Output: {len(filtered)} points, first.vo2={getattr(first, 'vo2', 'MISSING')}"
            )
        else:
            logger.warning(f"🔍 [PHASE_TRIM] Output: 0 points (all filtered out)")

        return filtered

    def _detect_and_remove_outliers(
        self, raw_points: List[ProcessedDataPoint]
    ) -> List[ProcessedDataPoint]:
        """
        IQR 기반 이상치 탐지 및 제거

        fat_oxidation, cho_oxidation에 대해 IQR 계산 후
        Q1 - k*IQR ~ Q3 + k*IQR 범위를 벗어나는 포인트 제거.
        10개 미만이면 스킵 (데이터 부족 시 제거하면 안 됨).

        Args:
            raw_points: 원본 raw 데이터 포인트 리스트

        Returns:
            이상치가 제거된 데이터 포인트 리스트
        """
        if not self.config.outlier_detection_enabled:
            return raw_points

        if len(raw_points) < 10:
            return raw_points

        k = self.config.outlier_iqr_multiplier
        fat_vals = np.array([
            p.fat_oxidation for p in raw_points if p.fat_oxidation is not None
        ])
        cho_vals = np.array([
            p.cho_oxidation for p in raw_points if p.cho_oxidation is not None
        ])

        def iqr_bounds(vals):
            if len(vals) < 4:
                return -np.inf, np.inf
            q1, q3 = np.percentile(vals, [25, 75])
            iqr = q3 - q1
            return q1 - k * iqr, q3 + k * iqr

        fat_lo, fat_hi = iqr_bounds(fat_vals)
        cho_lo, cho_hi = iqr_bounds(cho_vals)

        cleaned = []
        removed = 0
        for p in raw_points:
            fat_ok = p.fat_oxidation is None or (fat_lo <= p.fat_oxidation <= fat_hi)
            cho_ok = p.cho_oxidation is None or (cho_lo <= p.cho_oxidation <= cho_hi)
            if fat_ok and cho_ok:
                cleaned.append(p)
            else:
                removed += 1

        if removed > 0:
            self.warnings.append(
                f"Removed {removed} outlier(s) via IQR method (k={k})"
            )
            logger.info(
                f"🔧 [OUTLIER] Removed {removed}/{len(raw_points)} points "
                f"(fat: [{fat_lo:.3f}, {fat_hi:.3f}], cho: [{cho_lo:.3f}, {cho_hi:.3f}])"
            )

        return cleaned

    def _extract_raw_points(self, breath_data: List[Any]) -> List[ProcessedDataPoint]:
        """호흡 데이터에서 raw 포인트 추출"""

        # Helper to safely convert to float (handles None, NaN, and 0 correctly)
        def safe_float(val):
            if val is None:
                return None
            try:
                f = float(val)
                if math.isnan(f) or math.isinf(f):
                    return None
                return f
            except (ValueError, TypeError):
                return None

        # Debug: Check first data point for vo2/vco2/hr fields
        if breath_data:
            first = breath_data[0]
            logger.warning(f"🔍 [DEBUG] First breath_data point type: {type(first)}")
            logger.warning(
                f"🔍 [DEBUG] vo2={getattr(first, 'vo2', 'MISSING')}, vco2={getattr(first, 'vco2', 'MISSING')}, hr={getattr(first, 'hr', 'MISSING')}"
            )
            logger.warning(
                f"🔍 [DEBUG] ve_vo2={getattr(first, 've_vo2', 'MISSING')}, ve_vco2={getattr(first, 've_vco2', 'MISSING')}"
            )

        points = []
        for bd in breath_data:
            points.append(
                ProcessedDataPoint(
                    power=float(bd.bike_power) if bd.bike_power is not None else 0.0,
                    fat_oxidation=safe_float(bd.fat_oxidation),
                    cho_oxidation=safe_float(bd.cho_oxidation),
                    rer=safe_float(bd.rer),
                    vo2=safe_float(getattr(bd, "vo2", None)),
                    vo2_rel=safe_float(getattr(bd, "vo2_rel", None)),
                    vco2=safe_float(getattr(bd, "vco2", None)),
                    hr=safe_float(getattr(bd, "hr", None)),
                    ve_vo2=safe_float(getattr(bd, "ve_vo2", None)),
                    ve_vco2=safe_float(getattr(bd, "ve_vco2", None)),
                    count=1,
                )
            )
        return points

    def _power_binning(
        self, raw_points: List[ProcessedDataPoint]
    ) -> List[ProcessedDataPoint]:
        """
        Power 데이터를 bin_size W 단위로 그룹화하고 중앙값/평균 계산

        Args:
            raw_points: Raw 데이터 포인트 리스트

        Returns:
            Binned 데이터 포인트 리스트 (power 오름차순 정렬)
        """
        # DataFrame으로 변환
        df = pd.DataFrame(
            [
                {
                    "power": p.power,
                    "fat_oxidation": p.fat_oxidation,
                    "cho_oxidation": p.cho_oxidation,
                    "rer": p.rer,
                    "vo2": p.vo2,
                    "vo2_rel": p.vo2_rel,
                    "vco2": p.vco2,
                    "hr": p.hr,
                    "ve_vo2": p.ve_vo2,
                    "ve_vco2": p.ve_vco2,
                }
                for p in raw_points
            ]
        )

        # Power bin 할당
        bin_size = self.config.bin_size
        df["power_bin"] = (df["power"] / bin_size).round() * bin_size

        # Sparse bin 병합: min_bin_count 미만인 bin을 가장 가까운 bin에 병합
        if self.config.min_bin_count > 1:
            bin_counts = df.groupby("power_bin").size()
            sparse_bins = bin_counts[bin_counts < self.config.min_bin_count].index.tolist()
            all_bins = sorted(bin_counts.index.tolist())
            for sparse_bin in sparse_bins:
                candidates = [b for b in all_bins if b != sparse_bin and b not in sparse_bins]
                if not candidates:
                    candidates = [b for b in all_bins if b != sparse_bin]
                if candidates:
                    nearest = min(candidates, key=lambda b: abs(b - sparse_bin))
                    df.loc[df["power_bin"] == sparse_bin, "power_bin"] = nearest
            if sparse_bins:
                self.warnings.append(
                    f"Merged {len(sparse_bins)} sparse bins (< {self.config.min_bin_count} points)"
                )

        # 집계할 필드 목록
        numeric_fields = [
            "fat_oxidation",
            "cho_oxidation",
            "rer",
            "vo2",
            "vo2_rel",
            "vco2",
            "hr",
            "ve_vo2",
            "ve_vco2",
        ]

        # 집계 방법에 따른 그룹화
        agg_method = self.config.aggregation_method

        if agg_method == "median":
            agg_dict = {field: "median" for field in numeric_fields}
            agg_dict["power"] = "count"
            agg_df = df.groupby("power_bin").agg(agg_dict).reset_index()
        elif agg_method == "mean":
            agg_dict = {field: "mean" for field in numeric_fields}
            agg_dict["power"] = "count"
            agg_df = df.groupby("power_bin").agg(agg_dict).reset_index()
        elif agg_method == "trimmed_mean":
            # Trimmed mean: 양쪽 10% 제거 후 평균
            proportiontocut = self.config.trimmed_mean_proportiontocut

            def safe_trim_mean(x):
                if len(x) < 4:  # 데이터가 너무 적으면 일반 평균
                    return x.mean()
                return trim_mean(x, proportiontocut)

            agg_dict = {field: safe_trim_mean for field in numeric_fields}
            agg_dict["power"] = "count"
            agg_df = df.groupby("power_bin").agg(agg_dict).reset_index()
        else:
            # 기본값: median
            agg_dict = {field: "median" for field in numeric_fields}
            agg_dict["power"] = "count"
            agg_df = df.groupby("power_bin").agg(agg_dict).reset_index()

        agg_df = agg_df.rename(columns={"power": "count"})
        agg_df = agg_df.sort_values("power_bin").reset_index(drop=True)

        # 결과 변환
        binned_points = []
        for _, row in agg_df.iterrows():
            fat_ox = (
                float(row["fat_oxidation"]) if pd.notna(row["fat_oxidation"]) else None
            )
            cho_ox = (
                float(row["cho_oxidation"]) if pd.notna(row["cho_oxidation"]) else None
            )
            rer_val = float(row["rer"]) if pd.notna(row["rer"]) else None
            vo2_val = float(row["vo2"]) if pd.notna(row["vo2"]) else None
            vo2_rel_val = float(row["vo2_rel"]) if pd.notna(row["vo2_rel"]) else None
            vco2_val = float(row["vco2"]) if pd.notna(row["vco2"]) else None
            hr_val = float(row["hr"]) if pd.notna(row["hr"]) else None
            ve_vo2_val = float(row["ve_vo2"]) if pd.notna(row["ve_vo2"]) else None
            ve_vco2_val = float(row["ve_vco2"]) if pd.notna(row["ve_vco2"]) else None

            # Non-negative constraint (for oxidation values only)
            if self.config.non_negative_constraint:
                if fat_ox is not None:
                    fat_ox = max(0.0, fat_ox)
                if cho_ox is not None:
                    cho_ox = max(0.0, cho_ox)

            binned_points.append(
                ProcessedDataPoint(
                    power=float(row["power_bin"]),
                    fat_oxidation=fat_ox,
                    cho_oxidation=cho_ox,
                    rer=rer_val,
                    vo2=vo2_val,
                    vo2_rel=vo2_rel_val,
                    vco2=vco2_val,
                    hr=hr_val,
                    ve_vo2=ve_vo2_val,
                    ve_vco2=ve_vco2_val,
                    count=int(row["count"]),
                )
            )

        return binned_points

    def _loess_smoothing(
        self, binned_points: List[ProcessedDataPoint]
    ) -> List[ProcessedDataPoint]:
        """
        LOESS (Locally Estimated Scatterplot Smoothing) 적용

        Args:
            binned_points: Binned 데이터 포인트 리스트

        Returns:
            Smoothed 데이터 포인트 리스트
        """
        if not HAS_STATSMODELS:
            self.warnings.append(
                "statsmodels not available, using binned data as smoothed"
            )
            return binned_points

        if len(binned_points) < 4:
            self.warnings.append(
                "Not enough data points for LOESS smoothing, using binned data"
            )
            return binned_points

        # 데이터 추출
        powers = np.array([p.power for p in binned_points])
        fat_ox = np.array(
            [
                p.fat_oxidation if p.fat_oxidation is not None else 0
                for p in binned_points
            ]
        )
        cho_ox = np.array(
            [
                p.cho_oxidation if p.cho_oxidation is not None else 0
                for p in binned_points
            ]
        )
        rer_vals = np.array(
            [p.rer if p.rer is not None else np.nan for p in binned_points]
        )
        vo2_vals = np.array(
            [p.vo2 if p.vo2 is not None else np.nan for p in binned_points]
        )
        vo2_rel_vals = np.array(
            [p.vo2_rel if p.vo2_rel is not None else np.nan for p in binned_points]
        )
        vco2_vals = np.array(
            [p.vco2 if p.vco2 is not None else np.nan for p in binned_points]
        )
        hr_vals = np.array(
            [p.hr if p.hr is not None else np.nan for p in binned_points]
        )
        ve_vo2_vals = np.array(
            [p.ve_vo2 if p.ve_vo2 is not None else np.nan for p in binned_points]
        )
        ve_vco2_vals = np.array(
            [p.ve_vco2 if p.ve_vco2 is not None else np.nan for p in binned_points]
        )

        # LOESS smoothing
        try:
            # frac 값 조정
            if self.config.adaptive_loess:
                n = len(powers)
                # n=8→0.5, n=15→0.27, n=20→0.20, n=27+→0.15
                frac = max(0.15, min(0.5, 4.0 / n))
            else:
                frac = self.config.loess_frac
            frac = min(frac, (len(powers) - 1) / len(powers))
            frac = max(frac, 0.15)

            fat_smoothed = lowess(fat_ox, powers, frac=frac, return_sorted=True)
            cho_smoothed = lowess(cho_ox, powers, frac=frac, return_sorted=True)

            # Helper function for optional LOESS smoothing
            def smooth_optional(vals, powers, frac, min_points=4):
                if np.all(np.isnan(vals)):
                    return None
                valid_idx = ~np.isnan(vals)
                if np.sum(valid_idx) >= min_points:
                    return lowess(
                        vals[valid_idx],
                        powers[valid_idx],
                        frac=frac,
                        return_sorted=True,
                    )
                return None

            rer_smoothed = smooth_optional(rer_vals, powers, frac)
            vo2_smoothed = smooth_optional(vo2_vals, powers, frac)
            vo2_rel_smoothed = smooth_optional(vo2_rel_vals, powers, frac)
            vco2_smoothed = smooth_optional(vco2_vals, powers, frac)
            hr_smoothed = smooth_optional(hr_vals, powers, frac)
            ve_vo2_smoothed = smooth_optional(ve_vo2_vals, powers, frac)
            ve_vco2_smoothed = smooth_optional(ve_vco2_vals, powers, frac)

            # Helper to interpolate smoothed values
            def get_interpolated_val(smoothed, power_val, constraint=None):
                if smoothed is None:
                    return None
                idx = np.argmin(np.abs(smoothed[:, 0] - power_val))
                val = float(smoothed[idx, 1])
                if constraint and not (constraint[0] <= val <= constraint[1]):
                    return None
                return val

            # 결과 생성
            smoothed_points = []
            for i in range(len(fat_smoothed)):
                power_val = fat_smoothed[i, 0]
                fat_val = float(fat_smoothed[i, 1])
                cho_val = float(cho_smoothed[i, 1])

                # NaN 체크 및 처리
                if math.isnan(fat_val) or math.isinf(fat_val):
                    fat_val = 0.0
                if math.isnan(cho_val) or math.isinf(cho_val):
                    cho_val = 0.0

                # Non-negative constraint for oxidation values
                if self.config.non_negative_constraint:
                    fat_val = max(0.0, fat_val)
                    cho_val = max(0.0, cho_val)

                smoothed_points.append(
                    ProcessedDataPoint(
                        power=float(power_val),
                        fat_oxidation=fat_val,
                        cho_oxidation=cho_val,
                        rer=get_interpolated_val(rer_smoothed, power_val, (0.5, 1.5)),
                        vo2=get_interpolated_val(vo2_smoothed, power_val),
                        vo2_rel=get_interpolated_val(vo2_rel_smoothed, power_val),
                        vco2=get_interpolated_val(vco2_smoothed, power_val),
                        hr=get_interpolated_val(hr_smoothed, power_val),
                        ve_vo2=get_interpolated_val(ve_vo2_smoothed, power_val),
                        ve_vco2=get_interpolated_val(ve_vco2_smoothed, power_val),
                        count=None,
                    )
                )

            return smoothed_points

        except Exception as e:
            self.warnings.append(f"LOESS smoothing failed: {str(e)}, using binned data")
            return binned_points

    def _select_poly_degree_cv(self, x: np.ndarray, y: np.ndarray, max_degree: int = 4) -> int:
        """
        LOOCV로 최적 polynomial degree 선택

        Args:
            x: independent variable array
            y: dependent variable array
            max_degree: 테스트할 최대 degree

        Returns:
            RMSE가 최소인 degree
        """
        n = len(x)
        if n < 6:
            return min(3, n - 1)

        best_degree = 1
        best_rmse = np.inf

        for degree in range(1, min(max_degree, n - 1) + 1):
            errors = []
            for i in range(n):
                x_train = np.delete(x, i)
                y_train = np.delete(y, i)
                try:
                    coeffs = np.polyfit(x_train, y_train, degree)
                    poly = np.poly1d(coeffs)
                    pred = poly(x[i])
                    errors.append((y[i] - pred) ** 2)
                except (np.linalg.LinAlgError, ValueError):
                    errors.append(np.inf)
            rmse = np.sqrt(np.mean(errors))
            if rmse < best_rmse:
                best_rmse = rmse
                best_degree = degree

        return best_degree

    def _polynomial_fit(
        self, binned_points: List[ProcessedDataPoint]
    ) -> List[ProcessedDataPoint]:
        """
        Polynomial Regression을 사용한 Trend Line 계산 (깔끔한 곡선 생성)

        Polynomial Degrees by Metric Type (physiological standard models):
        - Fat & CHO (FatMax): Degree 3 - inverted U-shape / J-curve
        - RER: Degree 3 - slight dip at start, exponential rise at end
        - VO2, VCO2: Degree 2 - linear efficiency (slight curve)
        - HR: Degree 2 - linear response
        - VT Equivalents (VE/VO2, VE/VCO2): Degree 2 - U-shape for nadir detection

        Note: binned 데이터에서 직접 계산하여 smooth 데이터보다 더 단순한 패턴 생성

        Args:
            binned_points: Binned 데이터 포인트 리스트

        Returns:
            Trend 데이터 포인트 리스트 (10W 간격)
        """
        if len(binned_points) < 4:
            self.warnings.append("Not enough data points for polynomial fit")
            print(f"⚠️ Polynomial fit skipped: only {len(binned_points)} points")
            return []

        try:
            print(f"🔬 Starting polynomial fit with {len(binned_points)} binned points")

            # 데이터 추출
            powers = np.array([p.power for p in binned_points])
            fat_ox = np.array(
                [
                    p.fat_oxidation if p.fat_oxidation is not None else 0
                    for p in binned_points
                ]
            )
            cho_ox = np.array(
                [
                    p.cho_oxidation if p.cho_oxidation is not None else 0
                    for p in binned_points
                ]
            )
            rer_vals = np.array(
                [p.rer if p.rer is not None else np.nan for p in binned_points]
            )
            vo2_vals = np.array(
                [p.vo2 if p.vo2 is not None else np.nan for p in binned_points]
            )
            vo2_rel_vals = np.array(
                [p.vo2_rel if p.vo2_rel is not None else np.nan for p in binned_points]
            )
            vco2_vals = np.array(
                [p.vco2 if p.vco2 is not None else np.nan for p in binned_points]
            )
            hr_vals = np.array(
                [p.hr if p.hr is not None else np.nan for p in binned_points]
            )
            ve_vo2_vals = np.array(
                [p.ve_vo2 if p.ve_vo2 is not None else np.nan for p in binned_points]
            )
            ve_vco2_vals = np.array(
                [p.ve_vco2 if p.ve_vco2 is not None else np.nan for p in binned_points]
            )

            # Polynomial degrees per metric type
            if self.config.adaptive_polynomial:
                DEGREE_FAT = self._select_poly_degree_cv(powers, fat_ox, max_degree=4)
                DEGREE_CHO = self._select_poly_degree_cv(powers, cho_ox, max_degree=4)
                # RER: only use CV if enough valid data
                rer_valid = ~np.isnan(rer_vals)
                if np.sum(rer_valid) >= 6:
                    DEGREE_RER = self._select_poly_degree_cv(
                        powers[rer_valid], rer_vals[rer_valid], max_degree=4
                    )
                else:
                    DEGREE_RER = 3
            else:
                DEGREE_FAT = 3
                DEGREE_CHO = 3
                DEGREE_RER = 3
            DEGREE_VO2_VCO2 = 2  # Linear efficiency (slight curve) - also for VO2/kg
            DEGREE_HR = 2  # Linear response
            DEGREE_VT = 2  # U-shape for nadir detection

            # Helper function for fitting polynomial with NaN handling
            def fit_poly(vals, powers, degree, min_points=4):
                if np.all(np.isnan(vals)):
                    return None
                valid_idx = ~np.isnan(vals)
                if np.sum(valid_idx) >= min_points:
                    # Limit degree if not enough points
                    effective_degree = min(degree, np.sum(valid_idx) - 1)
                    coeffs = np.polyfit(
                        powers[valid_idx], vals[valid_idx], effective_degree
                    )
                    return np.poly1d(coeffs)
                return None

            # Fit polynomials
            fat_poly = np.poly1d(np.polyfit(powers, fat_ox, DEGREE_FAT))
            cho_poly = np.poly1d(np.polyfit(powers, cho_ox, DEGREE_CHO))
            rer_poly = fit_poly(rer_vals, powers, DEGREE_RER)
            vo2_poly = fit_poly(vo2_vals, powers, DEGREE_VO2_VCO2)
            vo2_rel_poly = fit_poly(vo2_rel_vals, powers, DEGREE_VO2_VCO2)
            vco2_poly = fit_poly(vco2_vals, powers, DEGREE_VO2_VCO2)
            hr_poly = fit_poly(hr_vals, powers, DEGREE_HR)
            ve_vo2_poly = fit_poly(ve_vo2_vals, powers, DEGREE_VT)
            ve_vco2_poly = fit_poly(ve_vco2_vals, powers, DEGREE_VT)

            # Trend 포인트 생성 (10W 간격)
            power_min = int(np.floor(powers.min() / 10) * 10)
            power_max = int(np.ceil(powers.max() / 10) * 10)
            trend_powers = np.arange(power_min, power_max + 1, 10)

            # Helper to safely evaluate polynomial
            def eval_poly(poly, p, constraint=None, default=None):
                if poly is None:
                    return default
                val = float(poly(p))
                if math.isnan(val) or math.isinf(val):
                    return default
                if constraint and not (constraint[0] <= val <= constraint[1]):
                    return default
                return val

            trend_points = []
            for p in trend_powers:
                fat_val = eval_poly(fat_poly, p, default=0.0)
                cho_val = eval_poly(cho_poly, p, default=0.0)

                # Non-negative constraint for oxidation values
                if self.config.non_negative_constraint:
                    fat_val = max(0.0, fat_val)
                    cho_val = max(0.0, cho_val)

                trend_points.append(
                    ProcessedDataPoint(
                        power=float(p),
                        fat_oxidation=fat_val,
                        cho_oxidation=cho_val,
                        rer=eval_poly(rer_poly, p, constraint=(0.5, 1.5)),
                        vo2=eval_poly(vo2_poly, p),
                        vo2_rel=eval_poly(vo2_rel_poly, p),
                        vco2=eval_poly(vco2_poly, p),
                        hr=eval_poly(hr_poly, p),
                        ve_vo2=eval_poly(ve_vo2_poly, p),
                        ve_vco2=eval_poly(ve_vco2_poly, p),
                        count=None,
                    )
                )

            print(
                f"✅ Polynomial fit complete: {len(trend_points)} trend points generated"
            )
            # Debug: Check first trend point values
            if trend_points:
                tp = trend_points[0]
                print(
                    f"🔍 [TREND] First point: vo2={tp.vo2}, vco2={tp.vco2}, hr={tp.hr}, ve_vo2={tp.ve_vo2}, ve_vco2={tp.ve_vco2}"
                )
                print(
                    f"🔍 [TREND] Polys: vo2_poly={vo2_poly is not None}, vco2_poly={vco2_poly is not None}, hr_poly={hr_poly is not None}"
                )
            return trend_points

        except Exception as e:
            self.warnings.append(f"Polynomial fit failed: {str(e)}")
            print(f"❌ Polynomial fit failed: {str(e)}")
            return []

    def _calculate_fatmax(
        self, smoothed_points: List[ProcessedDataPoint]
    ) -> FatMaxMarker:
        """
        FatMax (Maximum Fat Oxidation) 및 Zone 계산

        Args:
            smoothed_points: Smoothed 데이터 포인트 리스트

        Returns:
            FatMaxMarker
        """
        if not smoothed_points:
            return FatMaxMarker(power=0, mfo=0, zone_min=0, zone_max=0)

        # MFO (Maximum Fat Oxidation) 찾기
        max_fat = 0.0
        max_fat_power = 0.0
        for p in smoothed_points:
            if p.fat_oxidation is not None and p.fat_oxidation > max_fat:
                max_fat = p.fat_oxidation
                max_fat_power = p.power

        if max_fat == 0:
            return FatMaxMarker(power=0, mfo=0, zone_min=0, zone_max=0)

        # FatMax Zone 계산 (MFO의 90% 이상 유지 구간)
        threshold = max_fat * self.config.fatmax_zone_threshold
        zone_powers = [
            p.power
            for p in smoothed_points
            if p.fat_oxidation is not None and p.fat_oxidation >= threshold
        ]

        if zone_powers:
            zone_min = min(zone_powers)
            zone_max = max(zone_powers)
        else:
            zone_min = max_fat_power
            zone_max = max_fat_power

        marker = FatMaxMarker(
            power=int(round(max_fat_power)),
            mfo=max_fat,
            zone_min=int(round(zone_min)),
            zone_max=int(round(zone_max)),
        )

        # Bootstrap confidence interval
        if self.config.fatmax_confidence_interval and len(smoothed_points) >= 5:
            try:
                rng = np.random.default_rng(42)
                n = len(smoothed_points)
                mfo_samples = []
                power_samples = []
                for _ in range(self.config.fatmax_bootstrap_iterations):
                    indices = rng.choice(n, size=n, replace=True)
                    sample = [smoothed_points[i] for i in indices]
                    sample_max_fat = 0.0
                    sample_max_power = 0.0
                    for p in sample:
                        if p.fat_oxidation is not None and p.fat_oxidation > sample_max_fat:
                            sample_max_fat = p.fat_oxidation
                            sample_max_power = p.power
                    mfo_samples.append(sample_max_fat)
                    power_samples.append(sample_max_power)
                mfo_arr = np.array(mfo_samples)
                power_arr = np.array(power_samples)
                marker.mfo_ci_lower = float(np.percentile(mfo_arr, 2.5))
                marker.mfo_ci_upper = float(np.percentile(mfo_arr, 97.5))
                marker.power_ci_lower = int(round(np.percentile(power_arr, 2.5)))
                marker.power_ci_upper = int(round(np.percentile(power_arr, 97.5)))
            except Exception as e:
                self.warnings.append(f"FatMax bootstrap CI failed: {str(e)}")

        return marker

    def _calculate_crossover(
        self, smoothed_points: List[ProcessedDataPoint]
    ) -> Tuple[CrossoverMarker, Optional[List[CrossoverMarker]]]:
        """
        Crossover Point (FatOx = CHOOx 지점) 계산 - 다중 교차점 탐지

        모든 부호 변화 지점을 탐지하고 confidence(|d1 - d2|) 내림차순으로 정렬.
        가장 confidence가 높은 교차점을 primary로 반환.

        Args:
            smoothed_points: Smoothed 데이터 포인트 리스트

        Returns:
            Tuple of (primary CrossoverMarker, all_crossovers list or None)
        """
        empty = CrossoverMarker(power=None, fat_value=None, cho_value=None)
        if len(smoothed_points) < 3:
            return empty, None

        # 데이터 추출
        powers = np.array([p.power for p in smoothed_points])
        fat_ox = np.array(
            [
                p.fat_oxidation if p.fat_oxidation is not None else 0
                for p in smoothed_points
            ]
        )
        cho_ox = np.array(
            [
                p.cho_oxidation if p.cho_oxidation is not None else 0
                for p in smoothed_points
            ]
        )

        # FatOx - CHOOx 차이
        diff = fat_ox - cho_ox

        # 모든 부호 변화 지점 찾기 (양 → 음: Fat > CHO 에서 Fat < CHO로)
        sign_changes = []
        for i in range(len(diff) - 1):
            if diff[i] > 0 and diff[i + 1] <= 0:
                sign_changes.append(i)
            elif diff[i] >= 0 and diff[i + 1] < 0:
                sign_changes.append(i)

        if not sign_changes:
            return empty, None

        try:
            all_markers = []
            for idx in sign_changes:
                p1, p2 = powers[idx], powers[idx + 1]
                d1, d2 = diff[idx], diff[idx + 1]

                if d1 == d2:
                    crossover_power = p1
                    t = 0.0
                else:
                    t = -d1 / (d2 - d1)
                    crossover_power = p1 + t * (p2 - p1)

                crossover_fat = fat_ox[idx] + t * (fat_ox[idx + 1] - fat_ox[idx])
                crossover_cho = cho_ox[idx] + t * (cho_ox[idx + 1] - cho_ox[idx])
                conf = abs(d1 - d2)

                all_markers.append(
                    CrossoverMarker(
                        power=int(round(crossover_power)),
                        fat_value=float(crossover_fat),
                        cho_value=float(crossover_cho),
                        confidence=float(conf),
                    )
                )

            # Sort by confidence descending
            all_markers.sort(key=lambda m: m.confidence or 0, reverse=True)
            primary = all_markers[0]

            return primary, all_markers if len(all_markers) > 1 else None

        except Exception as e:
            self.warnings.append(f"Crossover calculation failed: {str(e)}")
            return empty, None


def analyze_metabolism(
    breath_data: List[Any],
    loess_frac: float = 0.25,
    bin_size: int = 10,
    use_median: bool = True,
    aggregation_method: Optional[str] = None,
    exclude_rest: bool = True,
    exclude_warmup: bool = True,
    exclude_recovery: bool = True,
    min_power_threshold: Optional[int] = None,
    fatmax_zone_threshold: float = 0.90,
) -> Optional[MetabolismAnalysisResult]:
    """
    호흡 데이터를 분석하여 처리된 시계열과 마커를 반환하는 편의 함수

    Args:
        breath_data: BreathData 객체 리스트
        loess_frac: LOESS smoothing fraction (0.1~0.5, default: 0.25)
        bin_size: Power binning 크기 (W, default: 10)
        use_median: True면 중앙값, False면 평균 사용 (deprecated)
        aggregation_method: 집계 방법 ("median", "mean", "trimmed_mean")
        exclude_rest: Rest 구간 제외 여부
        exclude_warmup: Warm-up 구간 제외 여부
        exclude_recovery: Recovery 구간 제외 여부
        min_power_threshold: 최소 파워 임계값 (e.g., 50W 미만 제외)
        fatmax_zone_threshold: FatMax zone 임계값 (MFO의 비율)

    Returns:
        MetabolismAnalysisResult 또는 None
    """
    # aggregation_method가 제공되면 우선, 아니면 use_median 기반
    if aggregation_method is None:
        aggregation_method = "median" if use_median else "mean"

    config = AnalysisConfig(
        loess_frac=loess_frac,
        bin_size=bin_size,
        aggregation_method=aggregation_method,
        fatmax_zone_threshold=fatmax_zone_threshold,
        exclude_rest=exclude_rest,
        exclude_warmup=exclude_warmup,
        exclude_recovery=exclude_recovery,
        min_power_threshold=min_power_threshold,
    )

    analyzer = MetabolismAnalyzer(config=config)
    return analyzer.analyze(breath_data)
