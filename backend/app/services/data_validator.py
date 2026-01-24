"""Data Validator Service - CPET 데이터 검증 및 프로토콜 분류"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import pearsonr

from app.schemas.test import HybridPhases, ProtocolType, SegmentInfo, ValidationResult


class DataValidator:
    """CPET 데이터 검증 및 프로토콜 분류 서비스

    Features:
    1. 데이터 무결성 검증 (필수 컬럼, 시간, 강도, 센서 드롭아웃)
    2. 프로토콜 분류 (Ramp vs Interval/Steady-state)
    3. 품질 점수 계산
    """

    # Constants
    ESSENTIAL_COLUMNS = ["t", "bike_power", "hr", "vo2", "vco2"]
    ALTERNATIVE_COLUMNS = {
        "t": ["time", "t_sec", "Time"],
        "bike_power": ["power", "Power", "Bike Power", "watt"],
        "hr": ["HR", "Heart Rate"],
        "vo2": ["VO2", "vo2_ml_min"],
        "vco2": ["VCO2", "vco2_ml_min"],
    }

    MIN_EXERCISE_DURATION_SEC = 300  # 5 minutes
    MIN_MAX_POWER = 50  # Watts
    MAX_DROPOUT_RATE = 0.10  # 10%
    EXERCISE_POWER_THRESHOLD = 20  # Watts
    RAMP_CORRELATION_THRESHOLD = 0.85  # r >= 0.85 for Ramp

    # HYBRID 프로토콜 감지 파라미터 (Gemini 피드백 반영)
    RECOVERY_POWER_RATIO = 0.30  # Recovery 판정: 최대 파워의 30% 이하
    RECOVERY_POWER_MIN = 50  # Recovery 판정 최소값 (W) - 최대파워가 낮을 때 대비
    MIN_RECOVERY_DURATION = 30  # 최소 Recovery 지속 시간 (초) - 노이즈 방지
    MIN_RAMP_SEGMENT_DURATION = 60  # 최소 RAMP 세그먼트 길이 (초) - 메타볼릭
    MIN_VO2MAX_SEGMENT_DURATION = 45  # 최소 VO2max 세그먼트 (초) - 짧은 검증 허용
    SEGMENT_RAMP_THRESHOLD = 0.70  # 세그먼트별 RAMP 판정 상관계수
    MIN_RAMP_SEGMENTS = 2  # HYBRID 판정을 위한 최소 RAMP 세그먼트 수
    POWER_SMOOTHING_WINDOW = 10  # 파워 스무딩 윈도우 (데이터 포인트 수)

    def __init__(self):
        pass

    def validate(self, df: pd.DataFrame) -> ValidationResult:
        """데이터 검증 및 프로토콜 분류

        Args:
            df: 파싱된 CPET 데이터 DataFrame

        Returns:
            ValidationResult: 검증 결과
        """
        if df is None or df.empty:
            return ValidationResult(
                is_valid=False,
                protocol_type=ProtocolType.UNKNOWN,
                reason=["Empty or None DataFrame"],
                quality_score=0.0,
                metadata={},
            )

        # 단일 행 데이터 처리
        if len(df) < 2:
            return ValidationResult(
                is_valid=False,
                protocol_type=ProtocolType.UNKNOWN,
                reason=["Insufficient data points (< 2)"],
                quality_score=0.0,
                metadata={"row_count": len(df)},
            )

        # 컬럼 정규화 (대소문자, 공백 처리)
        df = self._normalize_column_names(df)

        # 검증 단계별 실행
        reasons = []
        metadata = {}

        # 1. 필수 컬럼 체크
        has_essential, missing_cols = self._check_essential_columns(df)
        if not has_essential:
            reasons.append(f"Missing essential columns: {', '.join(missing_cols)}")

        # 2. 시간/구간 추출
        time_col, power_col = self._identify_columns(df)
        if time_col is None or power_col is None:
            return ValidationResult(
                is_valid=False,
                protocol_type=ProtocolType.UNKNOWN,
                reason=reasons + ["Cannot identify time or power columns"],
                quality_score=0.0,
                has_essential_columns=has_essential,
                metadata={"available_columns": list(df.columns)},
            )

        # Exercise phase 추출
        exercise_df = df[df[power_col] > self.EXERCISE_POWER_THRESHOLD].copy()

        if exercise_df.empty:
            return ValidationResult(
                is_valid=False,
                protocol_type=ProtocolType.UNKNOWN,
                reason=reasons
                + [
                    f"No exercise phase detected (Power > {self.EXERCISE_POWER_THRESHOLD}W)"
                ],
                quality_score=0.0,
                has_essential_columns=has_essential,
                metadata={
                    "max_power": float(df[power_col].max())
                    if power_col in df.columns
                    else 0
                },
            )

        # 3. Duration 체크
        duration_sec = self._calculate_duration(exercise_df, time_col)
        duration_valid = duration_sec >= self.MIN_EXERCISE_DURATION_SEC
        if not duration_valid:
            reasons.append(
                f"Exercise duration too short: {duration_sec:.1f}s (< {self.MIN_EXERCISE_DURATION_SEC}s)"
            )
        metadata["duration_sec"] = round(duration_sec, 1)
        metadata["duration_min"] = round(duration_sec / 60, 2)

        # 4. Intensity 체크
        max_power = float(exercise_df[power_col].max())
        intensity_valid = max_power > self.MIN_MAX_POWER
        if not intensity_valid:
            reasons.append(
                f"Max power too low: {max_power:.1f}W (< {self.MIN_MAX_POWER}W)"
            )
        metadata["max_power"] = round(max_power, 1)

        # 5. HR Sensor Integrity
        hr_integrity, hr_dropout_rate = self._check_sensor_integrity(
            exercise_df, "hr", "HR"
        )
        if not hr_integrity:
            reasons.append(
                f"HR sensor dropout rate too high: {hr_dropout_rate:.1%} (> {self.MAX_DROPOUT_RATE:.0%})"
            )
        metadata["hr_dropout_rate"] = round(hr_dropout_rate, 3)

        # 6. Gas Sensor Integrity (VO2/VCO2)
        vo2_integrity, vo2_dropout_rate = self._check_sensor_integrity(
            exercise_df, "vo2", "VO2"
        )
        vco2_integrity, vco2_dropout_rate = self._check_sensor_integrity(
            exercise_df, "vco2", "VCO2"
        )
        gas_integrity = vo2_integrity and vco2_integrity
        if not gas_integrity:
            reasons.append(
                f"Gas sensor dropout rate too high: VO2={vo2_dropout_rate:.1%}, "
                f"VCO2={vco2_dropout_rate:.1%} (> {self.MAX_DROPOUT_RATE:.0%})"
            )
        metadata["vo2_dropout_rate"] = round(vo2_dropout_rate, 3)
        metadata["vco2_dropout_rate"] = round(vco2_dropout_rate, 3)

        # 7. 프로토콜 분류 (Ramp vs Hybrid vs Interval/Steady)
        protocol_type, correlation, segments, hybrid_phases = self._classify_protocol(
            exercise_df, time_col, power_col
        )
        metadata["power_time_correlation"] = (
            round(correlation, 4) if correlation is not None else None
        )

        # 8. 품질 점수 계산
        quality_score = self._calculate_quality_score(
            has_essential=has_essential,
            duration_valid=duration_valid,
            intensity_valid=intensity_valid,
            hr_integrity=hr_integrity,
            gas_integrity=gas_integrity,
            hr_dropout_rate=hr_dropout_rate,
            vo2_dropout_rate=vo2_dropout_rate,
            vco2_dropout_rate=vco2_dropout_rate,
        )
        metadata["quality_score"] = round(quality_score, 3)

        # 9. 최종 판정
        is_valid = (
            has_essential
            and duration_valid
            and intensity_valid
            and hr_integrity
            and gas_integrity
        )

        # 추가 메타데이터
        metadata["total_data_points"] = len(df)
        metadata["exercise_data_points"] = len(exercise_df)

        return ValidationResult(
            is_valid=is_valid,
            protocol_type=protocol_type,
            reason=reasons,
            quality_score=quality_score,
            metadata=metadata,
            has_essential_columns=has_essential,
            duration_valid=duration_valid,
            intensity_valid=intensity_valid,
            hr_integrity=hr_integrity,
            gas_integrity=gas_integrity,
            power_time_correlation=correlation,
            segments=segments,
            hybrid_phases=hybrid_phases,
        )

    def _normalize_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """컬럼명 정규화 (공백 제거, 소문자 변환)"""
        df = df.copy()
        # 공백 제거, 소문자 변환
        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
        return df

    def _check_essential_columns(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """필수 컬럼 존재 여부 체크

        Returns:
            Tuple[bool, List[str]]: (모두 존재하는가, 누락된 컬럼 리스트)
        """
        missing = []
        df_cols_lower = [col.lower().replace(" ", "_") for col in df.columns]

        for essential_col in self.ESSENTIAL_COLUMNS:
            # Alternative 이름들도 체크
            alternatives = self.ALTERNATIVE_COLUMNS.get(essential_col, [essential_col])
            alternatives_lower = [alt.lower().replace(" ", "_") for alt in alternatives]

            found = any(alt in df_cols_lower for alt in alternatives_lower)
            if not found:
                missing.append(essential_col)

        return len(missing) == 0, missing

    def _identify_columns(
        self, df: pd.DataFrame
    ) -> Tuple[Optional[str], Optional[str]]:
        """시간 컬럼과 파워 컬럼 식별

        Returns:
            Tuple[Optional[str], Optional[str]]: (time_col, power_col)
        """
        df_cols_lower = {col.lower().replace(" ", "_"): col for col in df.columns}

        # Time 컬럼 찾기
        time_col = None
        for candidate in ["t_sec", "t", "time", "time_sec"]:
            if candidate in df_cols_lower:
                time_col = df_cols_lower[candidate]
                break

        # Power 컬럼 찾기
        power_col = None
        for candidate in ["bike_power", "power", "watt", "watts"]:
            if candidate in df_cols_lower:
                power_col = df_cols_lower[candidate]
                break

        return time_col, power_col

    def _calculate_duration(self, df: pd.DataFrame, time_col: str) -> float:
        """구간 지속 시간 계산 (초)

        Args:
            df: DataFrame
            time_col: 시간 컬럼명

        Returns:
            float: 지속 시간 (초)
        """
        if time_col not in df.columns or df.empty:
            return 0.0

        time_data = df[time_col].dropna()
        if time_data.empty:
            return 0.0

        # datetime 타입이면 초 단위로 변환
        if pd.api.types.is_datetime64_any_dtype(time_data):
            duration_sec = (time_data.max() - time_data.min()).total_seconds()
        else:
            # 숫자 타입이면 그대로 사용 (이미 초 단위)
            duration_sec = float(time_data.max() - time_data.min())

        return duration_sec

    def _check_sensor_integrity(
        self, df: pd.DataFrame, col_name: str, display_name: str
    ) -> Tuple[bool, float]:
        """센서 무결성 체크 (드롭아웃 비율)

        Args:
            df: DataFrame
            col_name: 컬럼명 (정규화된)
            display_name: 표시용 이름

        Returns:
            Tuple[bool, float]: (통과 여부, 드롭아웃 비율)
        """
        # 컬럼 찾기
        df_cols_lower = {col.lower().replace(" ", "_"): col for col in df.columns}

        # Alternative 이름들 체크
        alternatives = self.ALTERNATIVE_COLUMNS.get(col_name, [col_name])
        alternatives_lower = [alt.lower().replace(" ", "_") for alt in alternatives]

        actual_col = None
        for alt in alternatives_lower:
            if alt in df_cols_lower:
                actual_col = df_cols_lower[alt]
                break

        if actual_col is None or df.empty:
            return False, 1.0  # 컬럼 없으면 100% 드롭아웃

        # NaN 또는 0 값 카운트
        data = df[actual_col]
        total_count = len(data)

        if total_count == 0:
            return False, 1.0

        dropout_count = data.isna().sum() + (data == 0).sum()
        dropout_rate = dropout_count / total_count

        return dropout_rate < self.MAX_DROPOUT_RATE, dropout_rate

    def _classify_protocol(
        self, df: pd.DataFrame, time_col: str, power_col: str
    ) -> Tuple[
        ProtocolType,
        Optional[float],
        Optional[List[SegmentInfo]],
        Optional[HybridPhases],
    ]:
        """프로토콜 분류 (Ramp vs Hybrid vs Interval/Steady-state)

        개선된 알고리즘 (Gemini 피드백 반영):
        1단계: 전체 상관계수 체크 - r >= 0.85 → RAMP (빠른 판정)
        2단계: 세그먼트 분석 (r < 0.85인 경우)
               - Recovery 구간(저파워 지속)으로 세그먼트 분리
               - 각 세그먼트별 상관계수 계산
        3단계: HYBRID 판정
               - 2개 이상의 RAMP 세그먼트 (r >= 0.70)
               - 사이에 recovery 구간 존재
        4단계: INTERVAL vs STEADY_STATE (그 외)

        Args:
            df: Exercise phase DataFrame
            time_col: 시간 컬럼명
            power_col: 파워 컬럼명

        Returns:
            Tuple[ProtocolType, correlation, segments, hybrid_phases]
        """
        if df.empty or time_col not in df.columns or power_col not in df.columns:
            return ProtocolType.UNKNOWN, None, None, None

        # NaN 제거
        valid_df = df[[time_col, power_col]].dropna().copy()

        if len(valid_df) < 3:
            return ProtocolType.UNKNOWN, None, None, None

        time_data = valid_df[time_col].values
        power_data = valid_df[power_col].values

        # datetime 타입이면 초 단위로 변환
        if pd.api.types.is_datetime64_any_dtype(time_data):
            time_data = (
                (pd.to_datetime(time_data) - pd.to_datetime(time_data).min())
                .total_seconds()
                .values
            )
        else:
            time_data = time_data.astype(float)

        power_data = power_data.astype(float)

        # 1단계: 전체 상관계수 계산
        try:
            correlation, _ = pearsonr(time_data, power_data)
        except Exception:
            return ProtocolType.UNKNOWN, None, None, None

        # r >= 0.85 → 단순 RAMP (기존 로직)
        if correlation >= self.RAMP_CORRELATION_THRESHOLD:
            return ProtocolType.RAMP, correlation, None, None

        # 2단계: 세그먼트 분석 (r < 0.85)
        segments = self._detect_segments(
            valid_df, time_col, power_col, time_data, power_data
        )

        # 3단계: HYBRID 판정
        ramp_segments = [s for s in segments if s.segment_type == "ramp"]
        recovery_segments = [s for s in segments if s.segment_type == "recovery"]

        if len(ramp_segments) >= self.MIN_RAMP_SEGMENTS and len(recovery_segments) >= 1:
            # HYBRID 프로토콜 감지됨
            # Gemini 피드백: 스마트 Phase 선택
            # - metabolic_phase: 가장 긴 램프 (서브맥스 테스트 = 긴 지속시간)
            # - vo2max_phase: 가장 높은 피크 파워 (맥스 테스트)
            metabolic_phase = max(
                ramp_segments, key=lambda s: (s.end_sec - s.start_sec)
            )
            vo2max_phase = max(ramp_segments, key=lambda s: (s.max_power or 0))

            # 같은 세그먼트가 선택되면 시간순으로 첫번째/마지막 사용
            if metabolic_phase == vo2max_phase and len(ramp_segments) > 1:
                metabolic_phase = ramp_segments[0]
                vo2max_phase = ramp_segments[-1]

            hybrid_phases = HybridPhases(
                metabolic_phase=metabolic_phase,
                recovery_phase=recovery_segments[0] if recovery_segments else None,
                vo2max_phase=vo2max_phase,
            )
            return ProtocolType.HYBRID, correlation, segments, hybrid_phases

        # 4단계: INTERVAL vs STEADY_STATE (기존 로직)
        power_cv = power_data.std() / power_data.mean() if power_data.mean() > 0 else 0

        if power_cv > 0.3:
            protocol_type = ProtocolType.INTERVAL
        else:
            protocol_type = ProtocolType.STEADY_STATE

        return protocol_type, correlation, segments, None

    def _detect_segments(
        self,
        df: pd.DataFrame,
        time_col: str,
        power_col: str,
        time_data: np.ndarray,
        power_data: np.ndarray,
    ) -> List[SegmentInfo]:
        """Recovery 구간(저파워 지속)을 기준으로 세그먼트 분리

        Algorithm (State Machine):
        1. 파워 데이터 스무딩 (롤링 평균)
        2. 상대적 Recovery 임계값 계산 (최대 파워의 30%, 최소 50W)
        3. 상태 전이 감지:
           - ACTIVE: power > recovery_threshold
           - RECOVERY: power <= recovery_threshold가 30초 이상 지속
        4. 각 ACTIVE 세그먼트별 상관계수 계산

        Returns:
            List[SegmentInfo]: 감지된 세그먼트 목록
        """
        segments: List[SegmentInfo] = []

        # 파워 스무딩 (노이즈 제거)
        smoothed_power = (
            pd.Series(power_data)
            .rolling(window=self.POWER_SMOOTHING_WINDOW, min_periods=1, center=True)
            .mean()
            .values
        )

        # 상대적 Recovery 임계값 계산 (Gemini 피드백: 최대 파워의 30%)
        max_power = float(np.max(power_data))
        recovery_threshold = max(
            self.RECOVERY_POWER_MIN, max_power * self.RECOVERY_POWER_RATIO
        )

        # Recovery 구간 감지 (상태 머신)
        # 단, Recovery는 "이전에 높은 파워 후 저파워"를 의미
        # 시작부터 저파워인 구간은 warmup으로 처리
        is_low_power = smoothed_power <= recovery_threshold
        has_seen_high_power = np.zeros(len(power_data), dtype=bool)

        # 첫 번째 고파워 지점 찾기
        first_high_idx = (
            np.argmax(~is_low_power) if np.any(~is_low_power) else len(power_data)
        )
        has_seen_high_power[first_high_idx:] = True

        # Recovery = 저파워 AND 이전에 고파워를 본 적 있음
        is_recovery = is_low_power & has_seen_high_power

        # 연속된 구간 찾기
        current_state = "active" if not is_recovery[0] else "recovery"
        segment_start_idx = 0

        for i in range(1, len(is_recovery)):
            new_state = "recovery" if is_recovery[i] else "active"

            if new_state != current_state:
                # 상태 전이 발생 - 이전 세그먼트 저장
                segment_end_idx = i - 1
                segment = self._create_segment(
                    time_data,
                    power_data,
                    segment_start_idx,
                    segment_end_idx,
                    current_state,
                )
                if segment:
                    segments.append(segment)

                segment_start_idx = i
                current_state = new_state

        # 마지막 세그먼트 (is_last=True로 더 짧은 지속시간 허용)
        segment = self._create_segment(
            time_data,
            power_data,
            segment_start_idx,
            len(time_data) - 1,
            current_state,
            is_last=True,
        )
        if segment:
            segments.append(segment)

        return segments

    def _create_segment(
        self,
        time_data: np.ndarray,
        power_data: np.ndarray,
        start_idx: int,
        end_idx: int,
        state: str,
        is_last: bool = False,
    ) -> Optional[SegmentInfo]:
        """세그먼트 생성 및 분류

        Args:
            time_data: 시간 배열
            power_data: 파워 배열
            start_idx: 시작 인덱스
            end_idx: 종료 인덱스
            state: 상태 ("active" or "recovery")
            is_last: 마지막 세그먼트 여부 (VO2max 검증 구간은 짧을 수 있음)

        Returns:
            SegmentInfo or None (너무 짧은 경우)
        """
        if end_idx <= start_idx:
            return None

        seg_time = time_data[start_idx : end_idx + 1]
        seg_power = power_data[start_idx : end_idx + 1]

        start_sec = float(seg_time[0])
        end_sec = float(seg_time[-1])
        duration = end_sec - start_sec

        avg_power = float(np.mean(seg_power))
        max_power = float(np.max(seg_power))

        if state == "recovery":
            # Recovery 구간: 최소 지속 시간 체크
            if duration < self.MIN_RECOVERY_DURATION:
                return None
            return SegmentInfo(
                start_sec=start_sec,
                end_sec=end_sec,
                segment_type="recovery",
                correlation=None,
                avg_power=round(avg_power, 1),
                max_power=round(max_power, 1),
            )
        else:
            # Active 구간: RAMP 여부 판정
            # Gemini 피드백: 마지막 세그먼트(VO2max 검증)는 더 짧은 지속시간 허용
            min_duration = (
                self.MIN_VO2MAX_SEGMENT_DURATION
                if is_last
                else self.MIN_RAMP_SEGMENT_DURATION
            )
            if duration < min_duration:
                return None

            # 상관계수 계산
            correlation = None
            segment_type = "other"

            if len(seg_time) >= 3:
                try:
                    corr, _ = pearsonr(seg_time, seg_power)
                    correlation = round(corr, 3)

                    if corr >= self.SEGMENT_RAMP_THRESHOLD:
                        segment_type = "ramp"
                    elif avg_power < 100:  # 낮은 파워의 비RAMP = warmup
                        segment_type = "warmup"
                except Exception:
                    pass

            return SegmentInfo(
                start_sec=start_sec,
                end_sec=end_sec,
                segment_type=segment_type,
                correlation=correlation,
                avg_power=round(avg_power, 1),
                max_power=round(max_power, 1),
            )

    def _calculate_quality_score(
        self,
        has_essential: bool,
        duration_valid: bool,
        intensity_valid: bool,
        hr_integrity: bool,
        gas_integrity: bool,
        hr_dropout_rate: float,
        vo2_dropout_rate: float,
        vco2_dropout_rate: float,
    ) -> float:
        """데이터 품질 점수 계산 (0.0 - 1.0)

        Scoring:
        - Essential columns: 0.20
        - Duration: 0.15
        - Intensity: 0.15
        - HR integrity: 0.20
        - Gas integrity: 0.30

        Args:
            각 검증 항목 결과

        Returns:
            float: 품질 점수 (0.0 - 1.0)
        """
        score = 0.0

        # 1. Essential columns (20%)
        if has_essential:
            score += 0.20

        # 2. Duration (15%)
        if duration_valid:
            score += 0.15

        # 3. Intensity (15%)
        if intensity_valid:
            score += 0.15

        # 4. HR Integrity (20%)
        if hr_integrity:
            score += 0.20
        else:
            # Partial credit based on dropout rate
            hr_quality = max(0, 1 - (hr_dropout_rate / self.MAX_DROPOUT_RATE))
            score += 0.20 * hr_quality

        # 5. Gas Integrity (30% - VO2: 15%, VCO2: 15%)
        if gas_integrity:
            score += 0.30
        else:
            # Partial credit
            vo2_quality = max(0, 1 - (vo2_dropout_rate / self.MAX_DROPOUT_RATE))
            vco2_quality = max(0, 1 - (vco2_dropout_rate / self.MAX_DROPOUT_RATE))
            score += 0.15 * vo2_quality + 0.15 * vco2_quality

        return min(1.0, max(0.0, score))  # Clamp to [0.0, 1.0]

    def get_validation_summary(self, result: ValidationResult) -> str:
        """검증 결과 요약 문자열 생성

        Args:
            result: ValidationResult

        Returns:
            str: 요약 문자열
        """
        lines = []
        lines.append(f"{'=' * 60}")
        lines.append(f"CPET Data Validation Report")
        lines.append(f"{'=' * 60}")
        lines.append(f"Valid: {'✓ YES' if result.is_valid else '✗ NO'}")
        lines.append(f"Protocol: {result.protocol_type.value}")
        lines.append(f"Quality Score: {result.quality_score:.2f}/1.00")
        lines.append(f"")

        if result.reason:
            lines.append(f"Issues:")
            for i, reason in enumerate(result.reason, 1):
                lines.append(f"  {i}. {reason}")
            lines.append(f"")

        lines.append(f"Details:")
        lines.append(
            f"  Essential Columns: {'✓' if result.has_essential_columns else '✗'}"
        )
        lines.append(
            f"  Duration: {'✓' if result.duration_valid else '✗'} "
            f"({result.metadata.get('duration_min', 0):.2f} min)"
        )
        lines.append(
            f"  Intensity: {'✓' if result.intensity_valid else '✗'} "
            f"(Max Power: {result.metadata.get('max_power', 0):.1f}W)"
        )
        lines.append(
            f"  HR Sensor: {'✓' if result.hr_integrity else '✗'} "
            f"(Dropout: {result.metadata.get('hr_dropout_rate', 0):.1%})"
        )
        lines.append(
            f"  Gas Sensor: {'✓' if result.gas_integrity else '✗'} "
            f"(VO2: {result.metadata.get('vo2_dropout_rate', 0):.1%}, "
            f"VCO2: {result.metadata.get('vco2_dropout_rate', 0):.1%})"
        )

        if result.power_time_correlation is not None:
            lines.append(
                f"  Power-Time Correlation: r={result.power_time_correlation:.3f}"
            )

        lines.append(f"{'=' * 60}")

        return "\n".join(lines)
