"""Metabolic Analysis Service - 대사 데이터 분석 파이프라인

Power binning, LOESS smoothing, FatMax/Crossover 마커 계산을 수행합니다.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from scipy.optimize import brentq

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "power": self.power,
            "fat_oxidation": self.fat_oxidation,
            "cho_oxidation": self.cho_oxidation,
            "count": self.count
        }


@dataclass
class FatMaxMarker:
    """FatMax 마커 정보"""
    power: int           # FatMax 지점 파워 (W)
    mfo: float           # Maximum Fat Oxidation (g/min)
    zone_min: int        # FatMax zone 하한 (W)
    zone_max: int        # FatMax zone 상한 (W)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "power": self.power,
            "mfo": round(self.mfo, 4),
            "zone_min": self.zone_min,
            "zone_max": self.zone_max
        }


@dataclass
class CrossoverMarker:
    """Crossover 지점 마커 정보"""
    power: Optional[int]         # Crossover 지점 파워 (W), 없으면 None
    fat_value: Optional[float]   # 교차 지점 FatOx 값
    cho_value: Optional[float]   # 교차 지점 CHOOx 값

    def to_dict(self) -> Dict[str, Any]:
        return {
            "power": self.power,
            "fat_value": round(self.fat_value, 4) if self.fat_value is not None else None,
            "cho_value": round(self.cho_value, 4) if self.cho_value is not None else None
        }


@dataclass
class MetabolicMarkers:
    """대사 마커 정보"""
    fat_max: FatMaxMarker
    crossover: CrossoverMarker

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fat_max": self.fat_max.to_dict(),
            "crossover": self.crossover.to_dict()
        }


@dataclass
class ProcessedSeries:
    """처리된 시계열 데이터"""
    raw: List[ProcessedDataPoint]      # 원본 데이터
    binned: List[ProcessedDataPoint]   # 10W 구간 평균/중앙값
    smoothed: List[ProcessedDataPoint] # LOESS smoothed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw": [p.to_dict() for p in self.raw],
            "binned": [p.to_dict() for p in self.binned],
            "smoothed": [p.to_dict() for p in self.smoothed]
        }


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
            "warnings": self.warnings
        }


class MetabolismAnalyzer:
    """대사 데이터 분석기"""

    def __init__(
        self,
        loess_frac: float = 0.25,
        bin_size: int = 10,
        use_median: bool = True,
        fatmax_zone_threshold: float = 0.90
    ):
        """
        Args:
            loess_frac: LOESS smoothing fraction (0.1 ~ 0.5 권장)
            bin_size: Power binning 크기 (W)
            use_median: True면 중앙값, False면 평균 사용
            fatmax_zone_threshold: FatMax zone 임계값 (MFO의 비율)
        """
        self.loess_frac = loess_frac
        self.bin_size = bin_size
        self.use_median = use_median
        self.fatmax_zone_threshold = fatmax_zone_threshold
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

        # Exercise 구간만 필터링 (Rest, Warm-up, Recovery 제외)
        exercise_data = [
            bd for bd in breath_data
            if bd.phase in ("Exercise", "Peak")
            and bd.bike_power is not None
            and bd.fat_oxidation is not None
            and bd.cho_oxidation is not None
        ]

        if len(exercise_data) < 10:
            self.warnings.append(f"Insufficient exercise data for analysis: {len(exercise_data)} points")
            return None

        # 1. Raw 데이터 추출
        raw_points = self._extract_raw_points(exercise_data)

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

        # 4. FatMax & Zone 계산
        fatmax_marker = self._calculate_fatmax(smoothed_points)

        # 5. Crossover Point 계산
        crossover_marker = self._calculate_crossover(smoothed_points)

        return MetabolismAnalysisResult(
            processed_series=ProcessedSeries(
                raw=raw_points,
                binned=binned_points,
                smoothed=smoothed_points
            ),
            metabolic_markers=MetabolicMarkers(
                fat_max=fatmax_marker,
                crossover=crossover_marker
            ),
            warnings=self.warnings
        )

    def _extract_raw_points(self, breath_data: List[Any]) -> List[ProcessedDataPoint]:
        """호흡 데이터에서 raw 포인트 추출"""
        points = []
        for bd in breath_data:
            points.append(ProcessedDataPoint(
                power=float(bd.bike_power),
                fat_oxidation=float(bd.fat_oxidation) if bd.fat_oxidation else None,
                cho_oxidation=float(bd.cho_oxidation) if bd.cho_oxidation else None,
                count=1
            ))
        return points

    def _power_binning(self, raw_points: List[ProcessedDataPoint]) -> List[ProcessedDataPoint]:
        """
        Power 데이터를 bin_size W 단위로 그룹화하고 중앙값/평균 계산

        Args:
            raw_points: Raw 데이터 포인트 리스트

        Returns:
            Binned 데이터 포인트 리스트 (power 오름차순 정렬)
        """
        # DataFrame으로 변환
        df = pd.DataFrame([
            {
                "power": p.power,
                "fat_oxidation": p.fat_oxidation,
                "cho_oxidation": p.cho_oxidation
            }
            for p in raw_points
        ])

        # Power bin 할당
        df["power_bin"] = (df["power"] / self.bin_size).round() * self.bin_size

        # 그룹화 및 집계
        if self.use_median:
            agg_df = df.groupby("power_bin").agg({
                "fat_oxidation": "median",
                "cho_oxidation": "median",
                "power": "count"  # count
            }).reset_index()
        else:
            agg_df = df.groupby("power_bin").agg({
                "fat_oxidation": "mean",
                "cho_oxidation": "mean",
                "power": "count"
            }).reset_index()

        agg_df = agg_df.rename(columns={"power": "count"})
        agg_df = agg_df.sort_values("power_bin").reset_index(drop=True)

        # 결과 변환
        binned_points = []
        for _, row in agg_df.iterrows():
            binned_points.append(ProcessedDataPoint(
                power=float(row["power_bin"]),
                fat_oxidation=float(row["fat_oxidation"]) if pd.notna(row["fat_oxidation"]) else None,
                cho_oxidation=float(row["cho_oxidation"]) if pd.notna(row["cho_oxidation"]) else None,
                count=int(row["count"])
            ))

        return binned_points

    def _loess_smoothing(self, binned_points: List[ProcessedDataPoint]) -> List[ProcessedDataPoint]:
        """
        LOESS (Locally Estimated Scatterplot Smoothing) 적용

        Args:
            binned_points: Binned 데이터 포인트 리스트

        Returns:
            Smoothed 데이터 포인트 리스트
        """
        if not HAS_STATSMODELS:
            self.warnings.append("statsmodels not available, using binned data as smoothed")
            return binned_points

        if len(binned_points) < 4:
            self.warnings.append("Not enough data points for LOESS smoothing, using binned data")
            return binned_points

        # 데이터 추출
        powers = np.array([p.power for p in binned_points])
        fat_ox = np.array([p.fat_oxidation if p.fat_oxidation is not None else 0 for p in binned_points])
        cho_ox = np.array([p.cho_oxidation if p.cho_oxidation is not None else 0 for p in binned_points])

        # LOESS smoothing
        try:
            # frac 값 조정 (데이터 포인트가 적을 경우)
            frac = min(self.loess_frac, (len(powers) - 1) / len(powers))
            frac = max(frac, 0.15)  # 최소 0.15

            fat_smoothed = lowess(fat_ox, powers, frac=frac, return_sorted=True)
            cho_smoothed = lowess(cho_ox, powers, frac=frac, return_sorted=True)

            # 결과 생성 (물리적 제약: >= 0)
            smoothed_points = []
            for i in range(len(fat_smoothed)):
                smoothed_points.append(ProcessedDataPoint(
                    power=float(fat_smoothed[i, 0]),
                    fat_oxidation=max(0.0, float(fat_smoothed[i, 1])),
                    cho_oxidation=max(0.0, float(cho_smoothed[i, 1])),
                    count=None
                ))

            return smoothed_points

        except Exception as e:
            self.warnings.append(f"LOESS smoothing failed: {str(e)}, using binned data")
            return binned_points

    def _calculate_fatmax(self, smoothed_points: List[ProcessedDataPoint]) -> FatMaxMarker:
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
        threshold = max_fat * self.fatmax_zone_threshold
        zone_powers = [
            p.power for p in smoothed_points
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
            zone_max=int(round(zone_max))
        )

    def _calculate_crossover(self, smoothed_points: List[ProcessedDataPoint]) -> CrossoverMarker:
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
        fat_ox = np.array([p.fat_oxidation if p.fat_oxidation is not None else 0 for p in smoothed_points])
        cho_ox = np.array([p.cho_oxidation if p.cho_oxidation is not None else 0 for p in smoothed_points])

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
                cho_value=float(crossover_cho)
            )

        except Exception as e:
            self.warnings.append(f"Crossover calculation failed: {str(e)}")
            return CrossoverMarker(power=None, fat_value=None, cho_value=None)


def analyze_metabolism(
    breath_data: List[Any],
    loess_frac: float = 0.25,
    bin_size: int = 10,
    use_median: bool = True
) -> Optional[MetabolismAnalysisResult]:
    """
    호흡 데이터를 분석하여 처리된 시계열과 마커를 반환하는 편의 함수

    Args:
        breath_data: BreathData 객체 리스트
        loess_frac: LOESS smoothing fraction
        bin_size: Power binning 크기 (W)
        use_median: True면 중앙값, False면 평균 사용

    Returns:
        MetabolismAnalysisResult 또는 None
    """
    analyzer = MetabolismAnalyzer(
        loess_frac=loess_frac,
        bin_size=bin_size,
        use_median=use_median
    )
    return analyzer.analyze(breath_data)
