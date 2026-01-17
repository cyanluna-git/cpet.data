"""Data Validator Service - CPET 데이터 검증 및 프로토콜 분류"""

from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

from app.schemas.test import ValidationResult, ProtocolType


class DataValidator:
    """CPET 데이터 검증 및 프로토콜 분류 서비스
    
    Features:
    1. 데이터 무결성 검증 (필수 컬럼, 시간, 강도, 센서 드롭아웃)
    2. 프로토콜 분류 (Ramp vs Interval/Steady-state)
    3. 품질 점수 계산
    """
    
    # Constants
    ESSENTIAL_COLUMNS = ['t', 'bike_power', 'hr', 'vo2', 'vco2']
    ALTERNATIVE_COLUMNS = {
        't': ['time', 't_sec', 'Time'],
        'bike_power': ['power', 'Power', 'Bike Power', 'watt'],
        'hr': ['HR', 'Heart Rate'],
        'vo2': ['VO2', 'vo2_ml_min'],
        'vco2': ['VCO2', 'vco2_ml_min']
    }
    
    MIN_EXERCISE_DURATION_SEC = 300  # 5 minutes
    MIN_MAX_POWER = 50  # Watts
    MAX_DROPOUT_RATE = 0.10  # 10%
    EXERCISE_POWER_THRESHOLD = 20  # Watts
    RAMP_CORRELATION_THRESHOLD = 0.85  # r >= 0.85 for Ramp
    
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
                metadata={}
            )
        
        # 단일 행 데이터 처리
        if len(df) < 2:
            return ValidationResult(
                is_valid=False,
                protocol_type=ProtocolType.UNKNOWN,
                reason=["Insufficient data points (< 2)"],
                quality_score=0.0,
                metadata={"row_count": len(df)}
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
                metadata={"available_columns": list(df.columns)}
            )
        
        # Exercise phase 추출
        exercise_df = df[df[power_col] > self.EXERCISE_POWER_THRESHOLD].copy()
        
        if exercise_df.empty:
            return ValidationResult(
                is_valid=False,
                protocol_type=ProtocolType.UNKNOWN,
                reason=reasons + [f"No exercise phase detected (Power > {self.EXERCISE_POWER_THRESHOLD}W)"],
                quality_score=0.0,
                has_essential_columns=has_essential,
                metadata={"max_power": float(df[power_col].max()) if power_col in df.columns else 0}
            )
        
        # 3. Duration 체크
        duration_sec = self._calculate_duration(exercise_df, time_col)
        duration_valid = duration_sec >= self.MIN_EXERCISE_DURATION_SEC
        if not duration_valid:
            reasons.append(f"Exercise duration too short: {duration_sec:.1f}s (< {self.MIN_EXERCISE_DURATION_SEC}s)")
        metadata["duration_sec"] = round(duration_sec, 1)
        metadata["duration_min"] = round(duration_sec / 60, 2)
        
        # 4. Intensity 체크
        max_power = float(exercise_df[power_col].max())
        intensity_valid = max_power > self.MIN_MAX_POWER
        if not intensity_valid:
            reasons.append(f"Max power too low: {max_power:.1f}W (< {self.MIN_MAX_POWER}W)")
        metadata["max_power"] = round(max_power, 1)
        
        # 5. HR Sensor Integrity
        hr_integrity, hr_dropout_rate = self._check_sensor_integrity(
            exercise_df, 'hr', 'HR'
        )
        if not hr_integrity:
            reasons.append(f"HR sensor dropout rate too high: {hr_dropout_rate:.1%} (> {self.MAX_DROPOUT_RATE:.0%})")
        metadata["hr_dropout_rate"] = round(hr_dropout_rate, 3)
        
        # 6. Gas Sensor Integrity (VO2/VCO2)
        vo2_integrity, vo2_dropout_rate = self._check_sensor_integrity(
            exercise_df, 'vo2', 'VO2'
        )
        vco2_integrity, vco2_dropout_rate = self._check_sensor_integrity(
            exercise_df, 'vco2', 'VCO2'
        )
        gas_integrity = vo2_integrity and vco2_integrity
        if not gas_integrity:
            reasons.append(
                f"Gas sensor dropout rate too high: VO2={vo2_dropout_rate:.1%}, "
                f"VCO2={vco2_dropout_rate:.1%} (> {self.MAX_DROPOUT_RATE:.0%})"
            )
        metadata["vo2_dropout_rate"] = round(vo2_dropout_rate, 3)
        metadata["vco2_dropout_rate"] = round(vco2_dropout_rate, 3)
        
        # 7. 프로토콜 분류 (Ramp vs Interval/Steady)
        protocol_type, correlation = self._classify_protocol(exercise_df, time_col, power_col)
        metadata["power_time_correlation"] = round(correlation, 4) if correlation is not None else None
        
        # 8. 품질 점수 계산
        quality_score = self._calculate_quality_score(
            has_essential=has_essential,
            duration_valid=duration_valid,
            intensity_valid=intensity_valid,
            hr_integrity=hr_integrity,
            gas_integrity=gas_integrity,
            hr_dropout_rate=hr_dropout_rate,
            vo2_dropout_rate=vo2_dropout_rate,
            vco2_dropout_rate=vco2_dropout_rate
        )
        metadata["quality_score"] = round(quality_score, 3)
        
        # 9. 최종 판정
        is_valid = (
            has_essential and
            duration_valid and
            intensity_valid and
            hr_integrity and
            gas_integrity
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
            power_time_correlation=correlation
        )
    
    def _normalize_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """컬럼명 정규화 (공백 제거, 소문자 변환)"""
        df = df.copy()
        # 공백 제거, 소문자 변환
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        return df
    
    def _check_essential_columns(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """필수 컬럼 존재 여부 체크
        
        Returns:
            Tuple[bool, List[str]]: (모두 존재하는가, 누락된 컬럼 리스트)
        """
        missing = []
        df_cols_lower = [col.lower().replace(' ', '_') for col in df.columns]
        
        for essential_col in self.ESSENTIAL_COLUMNS:
            # Alternative 이름들도 체크
            alternatives = self.ALTERNATIVE_COLUMNS.get(essential_col, [essential_col])
            alternatives_lower = [alt.lower().replace(' ', '_') for alt in alternatives]
            
            found = any(alt in df_cols_lower for alt in alternatives_lower)
            if not found:
                missing.append(essential_col)
        
        return len(missing) == 0, missing
    
    def _identify_columns(self, df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
        """시간 컬럼과 파워 컬럼 식별
        
        Returns:
            Tuple[Optional[str], Optional[str]]: (time_col, power_col)
        """
        df_cols_lower = {col.lower().replace(' ', '_'): col for col in df.columns}
        
        # Time 컬럼 찾기
        time_col = None
        for candidate in ['t_sec', 't', 'time', 'time_sec']:
            if candidate in df_cols_lower:
                time_col = df_cols_lower[candidate]
                break
        
        # Power 컬럼 찾기
        power_col = None
        for candidate in ['bike_power', 'power', 'watt', 'watts']:
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
        self, 
        df: pd.DataFrame, 
        col_name: str,
        display_name: str
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
        df_cols_lower = {col.lower().replace(' ', '_'): col for col in df.columns}
        
        # Alternative 이름들 체크
        alternatives = self.ALTERNATIVE_COLUMNS.get(col_name, [col_name])
        alternatives_lower = [alt.lower().replace(' ', '_') for alt in alternatives]
        
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
        self, 
        df: pd.DataFrame, 
        time_col: str, 
        power_col: str
    ) -> Tuple[ProtocolType, Optional[float]]:
        """프로토콜 분류 (Ramp vs Interval/Steady-state)
        
        Method: Pearson Correlation Coefficient (r) between Time and Power
        - r >= 0.85: RAMP (strong linear correlation)
        - r < 0.85 + high std: INTERVAL (fluctuating power)
        - r < 0.85 + low std: STEADY_STATE (constant power)
        
        Args:
            df: Exercise phase DataFrame
            time_col: 시간 컬럼명
            power_col: 파워 컬럼명
            
        Returns:
            Tuple[ProtocolType, Optional[float]]: (프로토콜 타입, 상관계수)
        """
        if df.empty or time_col not in df.columns or power_col not in df.columns:
            return ProtocolType.UNKNOWN, None
        
        # NaN 제거
        valid_df = df[[time_col, power_col]].dropna()
        
        if len(valid_df) < 3:  # 최소 3개 포인트 필요
            return ProtocolType.UNKNOWN, None
        
        time_data = valid_df[time_col].values
        power_data = valid_df[power_col].values
        
        # datetime 타입이면 초 단위로 변환
        if pd.api.types.is_datetime64_any_dtype(time_data):
            time_data = (pd.to_datetime(time_data) - pd.to_datetime(time_data).min()).total_seconds().values
        else:
            time_data = time_data.astype(float)
        
        power_data = power_data.astype(float)
        
        # Pearson 상관계수 계산
        try:
            correlation, p_value = pearsonr(time_data, power_data)
        except Exception:
            return ProtocolType.UNKNOWN, None
        
        # 프로토콜 분류
        if correlation >= self.RAMP_CORRELATION_THRESHOLD:
            protocol_type = ProtocolType.RAMP
        else:
            # Power의 변동성으로 Interval vs Steady-state 구분
            power_cv = power_data.std() / power_data.mean() if power_data.mean() > 0 else 0
            
            if power_cv > 0.3:  # Coefficient of Variation > 30%
                protocol_type = ProtocolType.INTERVAL
            else:
                protocol_type = ProtocolType.STEADY_STATE
        
        return protocol_type, correlation
    
    def _calculate_quality_score(
        self,
        has_essential: bool,
        duration_valid: bool,
        intensity_valid: bool,
        hr_integrity: bool,
        gas_integrity: bool,
        hr_dropout_rate: float,
        vo2_dropout_rate: float,
        vco2_dropout_rate: float
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
        lines.append(f"{'='*60}")
        lines.append(f"CPET Data Validation Report")
        lines.append(f"{'='*60}")
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
        lines.append(f"  Essential Columns: {'✓' if result.has_essential_columns else '✗'}")
        lines.append(f"  Duration: {'✓' if result.duration_valid else '✗'} "
                    f"({result.metadata.get('duration_min', 0):.2f} min)")
        lines.append(f"  Intensity: {'✓' if result.intensity_valid else '✗'} "
                    f"(Max Power: {result.metadata.get('max_power', 0):.1f}W)")
        lines.append(f"  HR Sensor: {'✓' if result.hr_integrity else '✗'} "
                    f"(Dropout: {result.metadata.get('hr_dropout_rate', 0):.1%})")
        lines.append(f"  Gas Sensor: {'✓' if result.gas_integrity else '✗'} "
                    f"(VO2: {result.metadata.get('vo2_dropout_rate', 0):.1%}, "
                    f"VCO2: {result.metadata.get('vco2_dropout_rate', 0):.1%})")
        
        if result.power_time_correlation is not None:
            lines.append(f"  Power-Time Correlation: r={result.power_time_correlation:.3f}")
        
        lines.append(f"{'='*60}")
        
        return '\n'.join(lines)
