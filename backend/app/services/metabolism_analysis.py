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
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from scipy.optimize import brentq
from scipy.stats import trim_mean

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
    rer: Optional[float] = None  # RER
    vco2: Optional[float] = None  # VCO2 for VO2 Kinetics chart
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "power": self.power,
            "mfo": round(self.mfo, 4),
            "zone_min": self.zone_min,
            "zone_max": self.zone_max,
        }


@dataclass
class CrossoverMarker:
    """Crossover 지점 마커 정보"""

    power: Optional[int]  # Crossover 지점 파워 (W), 없으면 None
    fat_value: Optional[float]  # 교차 지점 FatOx 값
    cho_value: Optional[float]  # 교차 지점 CHOOx 값

    def to_dict(self) -> Dict[str, Any]:
        return {
            "power": self.power,
            "fat_value": (
                round(self.fat_value, 4) if self.fat_value is not None else None
            ),
            "cho_value": (
                round(self.cho_value, 4) if self.cho_value is not None else None
            ),
        }


@dataclass
class MetabolicMarkers:
    """대사 마커 정보"""

    fat_max: FatMaxMarker
    crossover: CrossoverMarker

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fat_max": self.fat_max.to_dict(),
            "crossover": self.crossover.to_dict(),
        }


@dataclass
class ProcessedSeries:
    """처리된 시계열 데이터"""

    raw: List[ProcessedDataPoint]  # 원본 데이터
    binned: List[ProcessedDataPoint]  # 10W 구간 평균/중앙값
    smoothed: List[ProcessedDataPoint]  # LOESS smoothed
    trend: List[ProcessedDataPoint] = field(default_factory=list)  # Polynomial fit

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "raw": [p.to_dict() for p in self.raw],
            "binned": [p.to_dict() for p in self.binned],
            "smoothed": [p.to_dict() for p in self.smoothed],
        }
        if self.trend:
            result["trend"] = [p.to_dict() for p in self.trend]
        return result


@dataclass
class MetabolismAnalysisResult:
    """대사 분석 결과"""

    processed_series: ProcessedSeries
    metabolic_markers: MetabolicMarkers
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "processed_series": self.processed_series.to_dict(),
            "metabolic_markers": self.metabolic_markers.to_dict(),
            "warnings": self.warnings,
        }


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

        # 2. Power Binning
        binned_points = self._power_binning(raw_points)

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
        crossover_marker = self._calculate_crossover(smoothed_points)

        return MetabolismAnalysisResult(
            processed_series=ProcessedSeries(
                raw=raw_points,
                binned=binned_points,
                smoothed=smoothed_points,
                trend=trend_points,
            ),
            metabolic_markers=MetabolicMarkers(
                fat_max=fatmax_marker, crossover=crossover_marker
            ),
            warnings=self.warnings,
        )

    def _apply_phase_trimming(self, breath_data: List[Any]) -> List[Any]:
        """Phase trimming 적용: Rest, Warm-up, Recovery 구간 제외"""
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

        return filtered

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

        points = []
        for bd in breath_data:
            points.append(
                ProcessedDataPoint(
                    power=float(bd.bike_power) if bd.bike_power is not None else 0.0,
                    fat_oxidation=safe_float(bd.fat_oxidation),
                    cho_oxidation=safe_float(bd.cho_oxidation),
                    rer=safe_float(bd.rer),
                    vo2=safe_float(getattr(bd, 'vo2', None)),
                    vco2=safe_float(getattr(bd, 'vco2', None)),
                    hr=safe_float(getattr(bd, 'hr', None)),
                    ve_vo2=safe_float(getattr(bd, 've_vo2', None)),
                    ve_vco2=safe_float(getattr(bd, 've_vco2', None)),
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

        # 집계할 필드 목록
        numeric_fields = ["fat_oxidation", "cho_oxidation", "rer", "vo2", "vco2", "hr", "ve_vo2", "ve_vco2"]

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
            fat_ox = float(row["fat_oxidation"]) if pd.notna(row["fat_oxidation"]) else None
            cho_ox = float(row["cho_oxidation"]) if pd.notna(row["cho_oxidation"]) else None
            rer_val = float(row["rer"]) if pd.notna(row["rer"]) else None
            vo2_val = float(row["vo2"]) if pd.notna(row["vo2"]) else None
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
        fat_ox = np.array([p.fat_oxidation if p.fat_oxidation is not None else 0 for p in binned_points])
        cho_ox = np.array([p.cho_oxidation if p.cho_oxidation is not None else 0 for p in binned_points])
        rer_vals = np.array([p.rer if p.rer is not None else np.nan for p in binned_points])
        vo2_vals = np.array([p.vo2 if p.vo2 is not None else np.nan for p in binned_points])
        vco2_vals = np.array([p.vco2 if p.vco2 is not None else np.nan for p in binned_points])
        hr_vals = np.array([p.hr if p.hr is not None else np.nan for p in binned_points])
        ve_vo2_vals = np.array([p.ve_vo2 if p.ve_vo2 is not None else np.nan for p in binned_points])
        ve_vco2_vals = np.array([p.ve_vco2 if p.ve_vco2 is not None else np.nan for p in binned_points])

        # LOESS smoothing
        try:
            # frac 값 조정 (데이터 포인트가 적을 경우)
            frac = min(self.config.loess_frac, (len(powers) - 1) / len(powers))
            frac = max(frac, 0.15)  # 최소 0.15

            fat_smoothed = lowess(fat_ox, powers, frac=frac, return_sorted=True)
            cho_smoothed = lowess(cho_ox, powers, frac=frac, return_sorted=True)

            # Helper function for optional LOESS smoothing
            def smooth_optional(vals, powers, frac, min_points=4):
                if np.all(np.isnan(vals)):
                    return None
                valid_idx = ~np.isnan(vals)
                if np.sum(valid_idx) >= min_points:
                    return lowess(vals[valid_idx], powers[valid_idx], frac=frac, return_sorted=True)
                return None

            rer_smoothed = smooth_optional(rer_vals, powers, frac)
            vo2_smoothed = smooth_optional(vo2_vals, powers, frac)
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
            fat_ox = np.array([p.fat_oxidation if p.fat_oxidation is not None else 0 for p in binned_points])
            cho_ox = np.array([p.cho_oxidation if p.cho_oxidation is not None else 0 for p in binned_points])
            rer_vals = np.array([p.rer if p.rer is not None else np.nan for p in binned_points])
            vo2_vals = np.array([p.vo2 if p.vo2 is not None else np.nan for p in binned_points])
            vco2_vals = np.array([p.vco2 if p.vco2 is not None else np.nan for p in binned_points])
            hr_vals = np.array([p.hr if p.hr is not None else np.nan for p in binned_points])
            ve_vo2_vals = np.array([p.ve_vo2 if p.ve_vo2 is not None else np.nan for p in binned_points])
            ve_vco2_vals = np.array([p.ve_vco2 if p.ve_vco2 is not None else np.nan for p in binned_points])

            # Polynomial degrees per metric type
            DEGREE_FAT_CHO = 3  # Inverted U-shape for Fat, J-curve for CHO
            DEGREE_RER = 3      # Slight dip at start, exponential rise at end
            DEGREE_VO2_VCO2 = 2 # Linear efficiency (slight curve)
            DEGREE_HR = 2       # Linear response
            DEGREE_VT = 2       # U-shape for nadir detection

            # Helper function for fitting polynomial with NaN handling
            def fit_poly(vals, powers, degree, min_points=4):
                if np.all(np.isnan(vals)):
                    return None
                valid_idx = ~np.isnan(vals)
                if np.sum(valid_idx) >= min_points:
                    # Limit degree if not enough points
                    effective_degree = min(degree, np.sum(valid_idx) - 1)
                    coeffs = np.polyfit(powers[valid_idx], vals[valid_idx], effective_degree)
                    return np.poly1d(coeffs)
                return None

            # Fit polynomials
            fat_poly = np.poly1d(np.polyfit(powers, fat_ox, DEGREE_FAT_CHO))
            cho_poly = np.poly1d(np.polyfit(powers, cho_ox, DEGREE_FAT_CHO))
            rer_poly = fit_poly(rer_vals, powers, DEGREE_RER)
            vo2_poly = fit_poly(vo2_vals, powers, DEGREE_VO2_VCO2)
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
                        vco2=eval_poly(vco2_poly, p),
                        hr=eval_poly(hr_poly, p),
                        ve_vo2=eval_poly(ve_vo2_poly, p),
                        ve_vco2=eval_poly(ve_vco2_poly, p),
                        count=None,
                    )
                )

            print(f"✅ Polynomial fit complete: {len(trend_points)} trend points generated")
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

        return FatMaxMarker(
            power=int(round(max_fat_power)),
            mfo=max_fat,
            zone_min=int(round(zone_min)),
            zone_max=int(round(zone_max)),
        )

    def _calculate_crossover(
        self, smoothed_points: List[ProcessedDataPoint]
    ) -> CrossoverMarker:
        """
        Crossover Point (FatOx = CHOOx 지점) 계산

        Args:
            smoothed_points: Smoothed 데이터 포인트 리스트

        Returns:
            CrossoverMarker
        """
        if len(smoothed_points) < 3:
            return CrossoverMarker(power=None, fat_value=None, cho_value=None)

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

        # 부호 변화 지점 찾기 (양 → 음: Fat > CHO 에서 Fat < CHO로)
        sign_changes = []
        for i in range(len(diff) - 1):
            if diff[i] > 0 and diff[i + 1] <= 0:
                sign_changes.append(i)
            elif diff[i] >= 0 and diff[i + 1] < 0:
                sign_changes.append(i)

        if not sign_changes:
            # 교차점 없음
            return CrossoverMarker(power=None, fat_value=None, cho_value=None)

        try:
            # 첫 번째 교차점 사용 (일반적으로 운동 강도가 증가하면서 첫 교차)
            idx = sign_changes[0]

            # 선형 보간으로 정확한 교차점 계산
            # diff[idx] > 0, diff[idx+1] <= 0
            p1, p2 = powers[idx], powers[idx + 1]
            d1, d2 = diff[idx], diff[idx + 1]

            if d1 == d2:
                crossover_power = p1
            else:
                # 선형 보간: d1 + (d2 - d1) * t = 0 => t = -d1 / (d2 - d1)
                t = -d1 / (d2 - d1)
                crossover_power = p1 + t * (p2 - p1)

            # 교차점에서의 Fat/CHO 값 계산 (선형 보간)
            crossover_fat = fat_ox[idx] + t * (fat_ox[idx + 1] - fat_ox[idx])
            crossover_cho = cho_ox[idx] + t * (cho_ox[idx + 1] - cho_ox[idx])

            return CrossoverMarker(
                power=int(round(crossover_power)),
                fat_value=float(crossover_fat),
                cho_value=float(crossover_cho),
            )

        except Exception as e:
            self.warnings.append(f"Crossover calculation failed: {str(e)}")
            return CrossoverMarker(power=None, fat_value=None, cho_value=None)


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
