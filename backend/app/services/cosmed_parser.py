"""COSMED K5 Excel File Parser - CPET 데이터 파싱"""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
import re

import pandas as pd
import numpy as np


def to_native(value: Any) -> Any:
    """numpy/pandas 타입을 Python 기본 타입으로 변환 (JSON 직렬화 가능하게)"""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if not np.isnan(value) else None
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return value.isoformat() if pd.notna(value) else None
    if isinstance(value, float) and np.isnan(value):
        return None
    return value


def to_native_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """딕셔너리 내 모든 값을 Python 기본 타입으로 변환"""
    return {k: to_native(v) for k, v in d.items()}


@dataclass
class SubjectInfo:
    """피험자 정보"""
    research_id: str = ""
    last_name: str = ""
    first_name: str = ""
    gender: Optional[str] = None
    age: Optional[float] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    birth_date: Optional[str] = None


@dataclass
class TestInfo:
    """테스트 정보"""
    test_date: Optional[datetime] = None
    test_time: Optional[time] = None
    subject_type: Optional[str] = None
    test_type: Optional[str] = None
    maximal_effort: Optional[str] = None
    test_duration: Optional[time] = None
    exercise_duration: Optional[time] = None
    hr_source: Optional[str] = None
    protocol: Optional[str] = None
    ergometer: Optional[str] = None
    ecg_response: Optional[str] = None
    reason_for_test: Optional[str] = None
    reason_for_stopping: Optional[str] = None


@dataclass
class EnvironmentalConditions:
    """환경 조건"""
    barometric_pressure: Optional[float] = None
    ambient_temp: Optional[float] = None
    ambient_humidity: Optional[float] = None
    device_temp: Optional[float] = None
    device_humidity: Optional[float] = None
    stpd: Optional[float] = None
    btps_ins: Optional[float] = None
    btps_exp: Optional[float] = None
    bsa: Optional[float] = None
    bmi: Optional[float] = None
    hr_max: Optional[int] = None
    num_steps: Optional[int] = None


@dataclass
class ParsedCPETData:
    """파싱된 CPET 데이터"""
    subject: SubjectInfo
    test: TestInfo
    environment: EnvironmentalConditions
    protocol_type: str  # "BxB" or "MIX"
    time_series: pd.DataFrame
    source_filename: str
    parsing_errors: List[str] = field(default_factory=list)
    parsing_warnings: List[str] = field(default_factory=list)


class COSMEDParser:
    """COSMED K5 Excel 파일 파서"""

    # 표준 컬럼명 매핑 (COSMED -> 내부 이름)
    COLUMN_MAPPING = {
        't': 't_sec',
        'Rf': 'rf',
        'VT': 'vt',
        'VE': 've',
        'IV': 'iv',
        'VO2': 'vo2',
        'VCO2': 'vco2',
        'RQ': 'rer',
        'O2exp': 'o2_exp',
        'CO2exp': 'co2_exp',
        'VE/VO2': 've_vo2',
        'VE/VCO2': 've_vco2',
        'VO2/Kg': 'vo2_rel',
        'METS': 'mets',
        'HR': 'hr',
        'VO2/HR': 'vo2_hr',
        'FeO2': 'feo2',
        'FeCO2': 'feco2',
        'FetO2': 'feto2',
        'FetCO2': 'fetco2',
        'FiO2': 'fio2',
        'FiCO2': 'fico2',
        'PeO2': 'peo2',
        'PeCO2': 'peco2',
        'PetO2': 'peto2',
        'PetCO2': 'petco2',
        'Phase': 'phase',
        'Marker': 'marker',
        'Amb. Temp.': 'amb_temp',
        'RH Amb': 'rh_amb',
        'Device Temp.': 'device_temp',
        'Analyz. Press.': 'analyz_press',
        'PB': 'pb',
        'EEkc': 'ee_kcal',
        'EEh': 'ee_h',
        'EEm': 'ee_m',
        'Bike Power': 'bike_power',
        'Bike Torque': 'bike_torque',
        'Cadence': 'cadence',
        'Speed': 'speed',
        'Grade': 'grade',
    }

    # 생리학적 유효 범위
    VALID_RANGES = {
        'hr': (30, 250),
        'vo2': (100, 8000),  # ml/min
        'vco2': (100, 8000),
        'rer': (0.5, 1.5),
        've': (5, 250),  # L/min
        'rf': (5, 80),  # breaths/min
        'vt': (0.2, 5),  # L
    }

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def parse_file(self, file_path: str | Path) -> ParsedCPETData:
        """
        COSMED K5 Excel 파일을 파싱합니다.

        Args:
            file_path: Excel 파일 경로

        Returns:
            ParsedCPETData: 파싱된 데이터 객체
        """
        self.errors = []
        self.warnings = []
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.suffix.lower() in ['.xlsx', '.xls']:
            raise ValueError(f"Invalid file format: {file_path.suffix}")

        # 프로토콜 타입 감지
        protocol_type = self._detect_protocol_type(file_path.name)

        # Excel 파일 읽기
        df = pd.read_excel(file_path, header=None, sheet_name='Data')

        # 메타데이터 추출
        subject = self._extract_subject_info(df)
        test = self._extract_test_info(df)
        environment = self._extract_environmental_conditions(df)

        # 시계열 데이터 추출
        time_series = self._extract_time_series(df, protocol_type)

        return ParsedCPETData(
            subject=subject,
            test=test,
            environment=environment,
            protocol_type=protocol_type,
            time_series=time_series,
            source_filename=file_path.name,
            parsing_errors=self.errors.copy(),
            parsing_warnings=self.warnings.copy(),
        )

    def _detect_protocol_type(self, filename: str) -> str:
        """파일명에서 프로토콜 타입 감지 (BxB or MIX)"""
        filename_upper = filename.upper()
        if 'BXB' in filename_upper:
            return 'BxB'
        elif 'MIX' in filename_upper:
            return 'MIX'
        else:
            self.warnings.append(f"Protocol type not detected in filename: {filename}, defaulting to MIX")
            return 'MIX'

    def _safe_get_cell(self, df: pd.DataFrame, row: int, col: int) -> Any:
        """안전하게 셀 값 가져오기"""
        try:
            value = df.iloc[row, col]
            if pd.isna(value):
                return None
            return value
        except (IndexError, KeyError):
            return None

    def _parse_time_string(self, time_str: str) -> Optional[time]:
        """시간 문자열 파싱 (HH:MM:SS 형식)"""
        if not time_str or pd.isna(time_str):
            return None
        try:
            if isinstance(time_str, time):
                return time_str
            if isinstance(time_str, datetime):
                return time_str.time()
            parts = str(time_str).split(':')
            if len(parts) == 3:
                return time(int(parts[0]), int(parts[1]), int(parts[2]))
            elif len(parts) == 2:
                return time(0, int(parts[0]), int(parts[1]))
        except (ValueError, TypeError):
            pass
        return None

    def _parse_date(self, date_val: Any) -> Optional[datetime]:
        """날짜 파싱"""
        if date_val is None or pd.isna(date_val):
            return None
        if isinstance(date_val, datetime):
            return date_val
        try:
            # 다양한 날짜 형식 시도
            for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d']:
                try:
                    return datetime.strptime(str(date_val), fmt)
                except ValueError:
                    continue
        except Exception:
            pass
        return None

    def _extract_subject_info(self, df: pd.DataFrame) -> SubjectInfo:
        """피험자 정보 추출"""
        subject = SubjectInfo()

        # Row 0: ID1
        subject.research_id = str(self._safe_get_cell(df, 0, 1) or '')

        # Row 1: Last Name
        subject.last_name = str(self._safe_get_cell(df, 1, 1) or '')

        # Row 2: First Name
        subject.first_name = str(self._safe_get_cell(df, 2, 1) or '')

        # Row 3: Gender
        gender_val = self._safe_get_cell(df, 3, 1)
        if gender_val:
            gender_str = str(gender_val).lower()
            if 'male' in gender_str and 'female' not in gender_str:
                subject.gender = 'M'
            elif 'female' in gender_str:
                subject.gender = 'F'
            else:
                subject.gender = gender_str[:1].upper()

        # Row 4: Age
        age_val = self._safe_get_cell(df, 4, 1)
        if age_val is not None:
            try:
                subject.age = float(age_val)
            except (ValueError, TypeError):
                pass

        # Row 5: Height (cm)
        height_val = self._safe_get_cell(df, 5, 1)
        if height_val is not None:
            try:
                subject.height_cm = float(height_val)
            except (ValueError, TypeError):
                pass

        # Row 6: Weight (kg)
        weight_val = self._safe_get_cell(df, 6, 1)
        if weight_val is not None:
            try:
                subject.weight_kg = float(weight_val)
            except (ValueError, TypeError):
                pass

        # Row 7: D.O.B.
        dob_val = self._safe_get_cell(df, 7, 1)
        if dob_val is not None:
            subject.birth_date = str(dob_val)

        # research_id가 비어있으면 이름으로 생성
        if not subject.research_id:
            subject.research_id = f"{subject.last_name}_{subject.first_name}".strip('_')

        return subject

    def _extract_test_info(self, df: pd.DataFrame) -> TestInfo:
        """테스트 정보 추출"""
        test = TestInfo()

        # Column 3-4: Test info
        # Row 0: Test date
        test.test_date = self._parse_date(self._safe_get_cell(df, 0, 4))

        # Row 1: Test Time
        test_time_val = self._safe_get_cell(df, 1, 4)
        if test_time_val:
            try:
                if isinstance(test_time_val, time):
                    test.test_time = test_time_val
                elif isinstance(test_time_val, datetime):
                    test.test_time = test_time_val.time()
                else:
                    # Parse AM/PM format
                    time_str = str(test_time_val)
                    for fmt in ['%I:%M:%S %p', '%H:%M:%S', '%I:%M %p']:
                        try:
                            parsed = datetime.strptime(time_str, fmt)
                            test.test_time = parsed.time()
                            break
                        except ValueError:
                            continue
            except Exception:
                pass

        # Row 2: Subject Type
        test.subject_type = str(self._safe_get_cell(df, 2, 4) or '')

        # Row 3: ECG Response
        test.ecg_response = str(self._safe_get_cell(df, 3, 4) or '')

        # Row 4: Reason for Test
        test.reason_for_test = str(self._safe_get_cell(df, 4, 4) or '')

        # Row 5: Reason for Stopping Test
        test.reason_for_stopping = str(self._safe_get_cell(df, 5, 4) or '')

        # Row 7: Test Type
        test.test_type = str(self._safe_get_cell(df, 7, 4) or '')

        # Row 8: Maximal Effort
        test.maximal_effort = str(self._safe_get_cell(df, 8, 4) or '')

        # Row 9: Test Duration
        test.test_duration = self._parse_time_string(self._safe_get_cell(df, 9, 4))

        # Row 10: Exercise Duration
        test.exercise_duration = self._parse_time_string(self._safe_get_cell(df, 10, 4))

        # Row 11: HR Source
        test.hr_source = str(self._safe_get_cell(df, 11, 4) or '')

        # Row 12: Protocol
        test.protocol = str(self._safe_get_cell(df, 12, 4) or '')

        # Row 13: Ergometer
        test.ergometer = str(self._safe_get_cell(df, 13, 4) or '')

        return test

    def _extract_environmental_conditions(self, df: pd.DataFrame) -> EnvironmentalConditions:
        """환경 조건 추출"""
        env = EnvironmentalConditions()

        def safe_float(val) -> Optional[float]:
            if val is None or pd.isna(val):
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        def safe_int(val) -> Optional[int]:
            if val is None or pd.isna(val):
                return None
            try:
                return int(float(val))
            except (ValueError, TypeError):
                return None

        # Column 6-7: Environmental conditions
        # Row 0: Barometric Pressure
        env.barometric_pressure = safe_float(self._safe_get_cell(df, 0, 7))

        # Row 1: Ambient Temperature
        env.ambient_temp = safe_float(self._safe_get_cell(df, 1, 7))

        # Row 2: Ambient Humidity
        env.ambient_humidity = safe_float(self._safe_get_cell(df, 2, 7))

        # Row 3: Device Temperature
        env.device_temp = safe_float(self._safe_get_cell(df, 3, 7))

        # Row 4: Device Humidity
        env.device_humidity = safe_float(self._safe_get_cell(df, 4, 7))

        # Row 5: STPD
        env.stpd = safe_float(self._safe_get_cell(df, 5, 7))

        # Row 6: BTPS Ins
        env.btps_ins = safe_float(self._safe_get_cell(df, 6, 7))

        # Row 7: BTPS Exp
        env.btps_exp = safe_float(self._safe_get_cell(df, 7, 7))

        # Row 8: # steps
        env.num_steps = safe_int(self._safe_get_cell(df, 8, 7))

        # Row 9: BSA
        env.bsa = safe_float(self._safe_get_cell(df, 9, 7))

        # Row 10: BMI
        env.bmi = safe_float(self._safe_get_cell(df, 10, 7))

        # Row 11: HR Max
        env.hr_max = safe_int(self._safe_get_cell(df, 11, 7))

        return env

    def _extract_time_series(self, df: pd.DataFrame, protocol_type: str) -> pd.DataFrame:
        """시계열 데이터 추출"""
        # 컬럼 헤더 (Row 0, Column 9+)
        headers = df.iloc[0, 9:].tolist()
        headers = [str(h) if pd.notna(h) else f'col_{i}' for i, h in enumerate(headers)]

        # 데이터 (Row 3+, Column 9+)
        data = df.iloc[3:, 9:].copy()
        data.columns = headers

        # 빈 행 제거
        data = data.dropna(how='all')

        # 컬럼명 표준화
        rename_map = {}
        for orig_col in data.columns:
            if orig_col in self.COLUMN_MAPPING:
                rename_map[orig_col] = self.COLUMN_MAPPING[orig_col]

        data = data.rename(columns=rename_map)

        # 시간 컬럼 처리
        if 't_sec' in data.columns:
            data['t_sec'] = data['t_sec'].apply(self._time_to_seconds)

        # 숫자형 컬럼 변환
        numeric_cols = [col for col in data.columns if col not in ['phase', 'marker', 't_raw']]
        for col in numeric_cols:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors='coerce')

        # 데이터 검증
        data = self._validate_time_series(data)

        # 인덱스 리셋
        data = data.reset_index(drop=True)

        return data

    def _time_to_seconds(self, time_val: Any) -> Optional[float]:
        """시간 값을 초로 변환"""
        if time_val is None or pd.isna(time_val):
            return None

        # 이미 숫자인 경우
        if isinstance(time_val, (int, float)):
            return float(time_val)

        # 문자열 파싱 (HH:MM:SS 또는 MM:SS)
        time_str = str(time_val)
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
                return h * 3600 + m * 60 + s
            elif len(parts) == 2:
                m, s = int(parts[0]), int(parts[1])
                return m * 60 + s
        except (ValueError, TypeError):
            pass

        return None

    def _validate_time_series(self, df: pd.DataFrame) -> pd.DataFrame:
        """시계열 데이터 검증"""
        df = df.copy()

        # 유효 범위 체크
        for col, (min_val, max_val) in self.VALID_RANGES.items():
            if col in df.columns:
                mask = (df[col] < min_val) | (df[col] > max_val)
                out_of_range = mask.sum()
                if out_of_range > 0:
                    self.warnings.append(
                        f"Column '{col}': {out_of_range} values out of valid range [{min_val}, {max_val}]"
                    )
                    # 범위 밖의 값은 NaN으로 처리
                    df.loc[mask, col] = np.nan

        # 결측치 통계
        for col in df.columns:
            missing = df[col].isna().sum()
            total = len(df)
            if missing > 0:
                pct = (missing / total) * 100
                if pct > 10:
                    self.warnings.append(
                        f"Column '{col}': {missing}/{total} ({pct:.1f}%) missing values"
                    )

        return df

    def calculate_metabolic_metrics(
        self,
        data: ParsedCPETData,
        calc_method: str = 'Frayn',
        smoothing_window: int = 10
    ) -> pd.DataFrame:
        """
        대사 지표 계산 (지방/탄수화물 연소율)

        Args:
            data: 파싱된 CPET 데이터
            calc_method: 계산 방식 ('Frayn' or 'Jeukendrup')
            smoothing_window: 스무딩 윈도우 크기 (초)

        Returns:
            계산된 대사 지표가 추가된 DataFrame
        """
        df = data.time_series.copy()

        if 'vo2' not in df.columns or 'vco2' not in df.columns:
            self.errors.append("VO2 or VCO2 columns not found for metabolic calculation")
            return df

        # VO2, VCO2 in L/min으로 변환 (ml/min -> L/min)
        vo2_l = df['vo2'] / 1000
        vco2_l = df['vco2'] / 1000

        # RER 계산
        if 'rer' not in df.columns or df['rer'].isna().all():
            df['rer'] = vco2_l / vo2_l

        if calc_method == 'Frayn':
            # Frayn 공식 (1983)
            # Fat oxidation (g/min) = 1.67 × VO2 - 1.67 × VCO2
            # CHO oxidation (g/min) = 4.55 × VCO2 - 3.21 × VO2
            df['fat_oxidation'] = 1.67 * vo2_l - 1.67 * vco2_l
            df['cho_oxidation'] = 4.55 * vco2_l - 3.21 * vo2_l

        elif calc_method == 'Jeukendrup':
            # Jeukendrup & Wallis (2005)
            # Fat oxidation (g/min) = 1.695 × VO2 – 1.701 × VCO2
            # CHO oxidation (g/min) = 4.210 × VCO2 – 2.962 × VO2
            df['fat_oxidation'] = 1.695 * vo2_l - 1.701 * vco2_l
            df['cho_oxidation'] = 4.210 * vco2_l - 2.962 * vo2_l

        # 음수 값 처리 (생리학적으로 불가능)
        df['fat_oxidation'] = df['fat_oxidation'].clip(lower=0)
        df['cho_oxidation'] = df['cho_oxidation'].clip(lower=0)

        # 에너지 소비량 계산 (kcal/min)
        # Fat: 9.75 kcal/g, CHO: 4.07 kcal/g
        df['ee_fat'] = df['fat_oxidation'] * 9.75
        df['ee_cho'] = df['cho_oxidation'] * 4.07
        df['ee_total_calc'] = df['ee_fat'] + df['ee_cho']

        return df

    def find_fatmax(
        self,
        df: pd.DataFrame,
        hr_column: str = 'hr',
        power_column: str = 'bike_power'
    ) -> Dict[str, Any]:
        """
        FATMAX (최대 지방 연소) 지점 찾기

        Returns:
            FATMAX 관련 메트릭 딕셔너리
        """
        if 'fat_oxidation' not in df.columns:
            return {}

        # 유효한 데이터만 사용
        valid_mask = df['fat_oxidation'].notna()
        if not valid_mask.any():
            return {}

        # 최대 지방 연소 지점
        fatmax_idx = df.loc[valid_mask, 'fat_oxidation'].idxmax()
        fatmax_row = df.loc[fatmax_idx]

        result = {
            'fat_max_g_min': fatmax_row['fat_oxidation'],
            'fat_max_vo2': fatmax_row.get('vo2'),
            'fat_max_rer': fatmax_row.get('rer'),
        }

        if hr_column in df.columns:
            result['fat_max_hr'] = fatmax_row.get(hr_column)

        if power_column in df.columns and pd.notna(fatmax_row.get(power_column)):
            result['fat_max_watt'] = fatmax_row.get(power_column)

        return to_native_dict(result)

    def find_vo2max(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        VO2MAX 관련 메트릭 찾기

        Returns:
            VO2MAX 관련 메트릭 딕셔너리
        """
        if 'vo2' not in df.columns:
            return {}

        valid_mask = df['vo2'].notna()
        if not valid_mask.any():
            return {}

        vo2max_idx = df.loc[valid_mask, 'vo2'].idxmax()
        vo2max_row = df.loc[vo2max_idx]

        result = {
            'vo2_max': vo2max_row['vo2'],
        }

        if 'vco2' in df.columns:
            result['vco2_max'] = vo2max_row.get('vco2')

        if 'vo2_rel' in df.columns:
            result['vo2_max_rel'] = vo2max_row.get('vo2_rel')

        if 'hr' in df.columns:
            result['hr_max'] = df['hr'].max()

        return to_native_dict(result)

    def detect_phases(
        self,
        df: pd.DataFrame,
        power_column: str = 'bike_power',
        hr_column: str = 'hr',
        time_column: str = 't_sec',
    ) -> pd.DataFrame:
        """
        자동 운동 구간 감지 (Phase Detection)

        Bike Power 기반으로 다음 구간을 자동 감지:
        - Rest: Power < 20W (초기 안정기)
        - Warm-up: 일정한 낮은 부하 (20-80W 범위, 안정적)
        - Exercise: 계단식/선형 증가 (파워 증가 구간)
        - Peak: 최대 부하 도달 시점
        - Recovery: 부하 급감 (운동 종료 후)

        Args:
            df: 시계열 데이터프레임
            power_column: 파워 컬럼명
            hr_column: 심박수 컬럼명
            time_column: 시간 컬럼명

        Returns:
            'phase' 컬럼이 추가된 DataFrame
        """
        df = df.copy()

        # 기본값: Unknown
        df['phase'] = 'Unknown'

        # 파워 데이터 없으면 HR 기반으로 시도
        if power_column not in df.columns or df[power_column].isna().all():
            return self._detect_phases_by_hr(df, hr_column, time_column)

        power = df[power_column].fillna(0)

        # 스무딩 (노이즈 제거)
        window = min(30, len(power) // 10) if len(power) > 30 else 5
        power_smooth = power.rolling(window=window, center=True, min_periods=1).mean()

        # 파워 변화율 계산
        power_diff = power_smooth.diff().fillna(0)

        # 임계값 설정
        REST_THRESHOLD = 20  # W
        WARMUP_MIN = 20
        WARMUP_MAX = 100
        RECOVERY_DROP_THRESHOLD = -20  # W/breath 급격한 감소

        # 최대 파워 지점 찾기
        peak_idx = power_smooth.idxmax()
        peak_power = power_smooth.max()

        # 구간별 감지
        phases = []
        for idx, row in df.iterrows():
            p = power_smooth.get(idx, 0)
            p_diff = power_diff.get(idx, 0)

            if idx < peak_idx:
                # Peak 이전
                if p < REST_THRESHOLD:
                    phases.append('Rest')
                elif WARMUP_MIN <= p <= WARMUP_MAX and abs(p_diff) < 2:
                    phases.append('Warm-up')
                elif p_diff > 0.5 or p > WARMUP_MAX:
                    phases.append('Exercise')
                else:
                    phases.append('Warm-up')
            elif idx == peak_idx:
                phases.append('Peak')
            else:
                # Peak 이후
                if p_diff < RECOVERY_DROP_THRESHOLD or p < peak_power * 0.5:
                    phases.append('Recovery')
                else:
                    phases.append('Exercise')

        df['phase'] = phases

        # 구간 경계 부드럽게 처리 (짧은 구간 병합)
        df = self._smooth_phase_transitions(df)

        return df

    def _detect_phases_by_hr(
        self,
        df: pd.DataFrame,
        hr_column: str = 'hr',
        time_column: str = 't_sec',
    ) -> pd.DataFrame:
        """HR 기반 구간 감지 (파워 데이터 없을 때 대체)"""
        if hr_column not in df.columns or df[hr_column].isna().all():
            return df

        hr = df[hr_column].fillna(method='ffill').fillna(method='bfill')

        # 스무딩
        window = min(30, len(hr) // 10) if len(hr) > 30 else 5
        hr_smooth = hr.rolling(window=window, center=True, min_periods=1).mean()

        # HR 변화율
        hr_diff = hr_smooth.diff().fillna(0)

        hr_max = hr_smooth.max()
        hr_rest = hr_smooth.iloc[:min(60, len(hr_smooth))].mean()  # 초기 1분 평균

        # 임계값
        REST_HR_RATIO = 1.1  # 안정시 HR의 110%
        PEAK_HR_RATIO = 0.95  # 최대 HR의 95%

        phases = []
        peak_idx = hr_smooth.idxmax()

        for idx, row in df.iterrows():
            h = hr_smooth.get(idx, hr_rest)

            if idx < peak_idx:
                if h < hr_rest * REST_HR_RATIO:
                    phases.append('Rest')
                elif h < hr_rest * 1.3:
                    phases.append('Warm-up')
                else:
                    phases.append('Exercise')
            elif idx == peak_idx or h >= hr_max * PEAK_HR_RATIO:
                phases.append('Peak')
            else:
                phases.append('Recovery')

        df['phase'] = phases
        df = self._smooth_phase_transitions(df)
        return df

    def _smooth_phase_transitions(self, df: pd.DataFrame, min_phase_duration: int = 10) -> pd.DataFrame:
        """
        짧은 구간을 인접 구간에 병합하여 부드러운 전환 생성

        Args:
            df: phase 컬럼이 있는 DataFrame
            min_phase_duration: 최소 구간 길이 (행 수)
        """
        if 'phase' not in df.columns:
            return df

        df = df.copy()
        phases = df['phase'].tolist()

        # Run-length encoding으로 구간 찾기
        runs = []
        current_phase = phases[0]
        start_idx = 0

        for i, phase in enumerate(phases):
            if phase != current_phase:
                runs.append((start_idx, i - 1, current_phase))
                current_phase = phase
                start_idx = i
        runs.append((start_idx, len(phases) - 1, current_phase))

        # 짧은 구간 병합
        for i, (start, end, phase) in enumerate(runs):
            duration = end - start + 1
            if duration < min_phase_duration:
                # 이전 또는 다음 구간으로 병합
                if i > 0:
                    prev_phase = runs[i - 1][2]
                    for j in range(start, end + 1):
                        phases[j] = prev_phase
                elif i < len(runs) - 1:
                    next_phase = runs[i + 1][2]
                    for j in range(start, end + 1):
                        phases[j] = next_phase

        df['phase'] = phases
        return df

    def get_phase_boundaries(self, df: pd.DataFrame, time_column: str = 't_sec') -> Dict[str, Any]:
        """
        각 구간의 시작/종료 시간 추출

        Returns:
            {
                'rest_end_sec': float,
                'warmup_end_sec': float,
                'exercise_end_sec': float,
                'peak_sec': float,
                'total_duration_sec': float,
                'phases': [{'phase': str, 'start_sec': float, 'end_sec': float}, ...]
            }
        """
        if 'phase' not in df.columns or time_column not in df.columns:
            return {}

        boundaries = {
            'rest_end_sec': None,
            'warmup_end_sec': None,
            'exercise_end_sec': None,
            'peak_sec': None,
            'total_duration_sec': df[time_column].max(),
            'phases': []
        }

        # 각 구간의 경계 찾기
        phase_order = ['Rest', 'Warm-up', 'Exercise', 'Peak', 'Recovery']
        current_phase = None
        phase_start = None

        for idx, row in df.iterrows():
            phase = row['phase']
            t = row[time_column]

            if phase != current_phase:
                # 이전 구간 종료
                if current_phase is not None and phase_start is not None:
                    boundaries['phases'].append({
                        'phase': current_phase,
                        'start_sec': phase_start,
                        'end_sec': t
                    })

                    # 경계 시간 기록
                    if current_phase == 'Rest':
                        boundaries['rest_end_sec'] = t
                    elif current_phase == 'Warm-up':
                        boundaries['warmup_end_sec'] = t
                    elif current_phase == 'Exercise':
                        boundaries['exercise_end_sec'] = t

                # 새 구간 시작
                current_phase = phase
                phase_start = t

                if phase == 'Peak':
                    boundaries['peak_sec'] = t

        # 마지막 구간 추가
        if current_phase is not None and phase_start is not None:
            boundaries['phases'].append({
                'phase': current_phase,
                'start_sec': phase_start,
                'end_sec': df[time_column].max()
            })

        # numpy 타입 변환 (중첩 구조 포함)
        result = to_native_dict(boundaries)
        result['phases'] = [to_native_dict(p) for p in boundaries['phases']]
        return result

    def calculate_phase_metrics(
        self,
        df: pd.DataFrame,
        time_column: str = 't_sec'
    ) -> Dict[str, Dict[str, Any]]:
        """
        각 구간별 평균 메트릭 계산

        Returns:
            {
                'Rest': {'avg_hr': float, 'avg_vo2': float, ...},
                'Warm-up': {...},
                'Exercise': {...},
                'Peak': {...},
                'Recovery': {...}
            }
        """
        if 'phase' not in df.columns:
            return {}

        metrics_by_phase = {}
        metric_columns = ['hr', 'vo2', 'vco2', 'rer', 'fat_oxidation', 'cho_oxidation', 'bike_power', 've', 'vo2_rel']

        for phase in df['phase'].unique():
            phase_data = df[df['phase'] == phase]

            metrics = {
                'duration_sec': phase_data[time_column].max() - phase_data[time_column].min() if time_column in phase_data.columns else len(phase_data),
                'data_points': len(phase_data),
            }

            for col in metric_columns:
                if col in phase_data.columns:
                    valid_data = phase_data[col].dropna()
                    if len(valid_data) > 0:
                        metrics[f'avg_{col}'] = valid_data.mean()
                        metrics[f'max_{col}'] = valid_data.max()
                        metrics[f'min_{col}'] = valid_data.min()

            # numpy 타입을 Python 기본 타입으로 변환 (JSON 직렬화 가능하게)
            metrics_by_phase[phase] = to_native_dict(metrics)

        return metrics_by_phase

    def detect_ventilatory_thresholds(
        self,
        df: pd.DataFrame,
        method: str = 'v_slope'
    ) -> Dict[str, Any]:
        """
        환기 역치 (VT1, VT2) 자동 감지

        VT1 (Ventilatory Threshold 1 / Aerobic Threshold):
        - V-slope method: VCO2 vs VO2 그래프에서 기울기 변화점
        - 또는 VE/VO2가 증가하기 시작하면서 VE/VCO2는 아직 안정적인 지점

        VT2 (Ventilatory Threshold 2 / Respiratory Compensation Point):
        - VE/VCO2가 증가하기 시작하는 지점
        - 또는 RER이 1.0을 초과하기 시작하는 지점

        Args:
            df: 시계열 데이터프레임 (vo2, vco2, ve, ve_vo2, ve_vco2, rer 포함)
            method: 감지 방법 ('v_slope', 'ventilatory_equivalent', 'rer')

        Returns:
            {
                'vt1_hr': int, 'vt1_vo2': float, 'vt1_time_sec': float,
                'vt2_hr': int, 'vt2_vo2': float, 'vt2_time_sec': float,
                'detection_method': str, 'confidence': float
            }
        """
        result = {
            'vt1_hr': None, 'vt1_vo2': None, 'vt1_time_sec': None,
            'vt2_hr': None, 'vt2_vo2': None, 'vt2_time_sec': None,
            'detection_method': method, 'confidence': 0.0
        }

        # Exercise 구간만 사용 (Rest, Warm-up 제외)
        if 'phase' in df.columns:
            exercise_df = df[df['phase'].isin(['Exercise', 'Peak'])].copy()
        else:
            # phase 없으면 전체 데이터 사용 (워밍업 구간 추정해서 제외)
            start_idx = len(df) // 5  # 앞 20% 제외
            exercise_df = df.iloc[start_idx:].copy()

        if len(exercise_df) < 30:
            self.warnings.append("Not enough exercise data for VT detection")
            return to_native_dict(result)

        if method == 'v_slope':
            return to_native_dict(self._detect_vt_v_slope(exercise_df, result))
        elif method == 'ventilatory_equivalent':
            return to_native_dict(self._detect_vt_ventilatory_equivalent(exercise_df, result))
        elif method == 'rer':
            return to_native_dict(self._detect_vt_rer(exercise_df, result))
        else:
            return to_native_dict(result)

    def _detect_vt_v_slope(self, df: pd.DataFrame, result: Dict) -> Dict:
        """V-slope 방법으로 VT1 감지"""
        if 'vo2' not in df.columns or 'vco2' not in df.columns:
            return result

        vo2 = df['vo2'].dropna().values
        vco2 = df['vco2'].dropna().values

        if len(vo2) < 30 or len(vco2) < 30:
            return result

        # 스무딩
        window = min(15, len(vo2) // 5)
        vo2_smooth = pd.Series(vo2).rolling(window=window, center=True, min_periods=1).mean().values
        vco2_smooth = pd.Series(vco2).rolling(window=window, center=True, min_periods=1).mean().values

        # 기울기 변화 감지 (VCO2/VO2 ratio)
        ratios = vco2_smooth / np.maximum(vo2_smooth, 1)
        ratio_diff = np.diff(ratios)

        # 기울기가 급격히 증가하는 지점 찾기 (VT1)
        # 이동 평균 기울기와 비교
        avg_slope = np.mean(ratio_diff[:len(ratio_diff)//3])  # 초기 평균
        threshold = avg_slope + np.std(ratio_diff[:len(ratio_diff)//3]) * 2

        vt1_idx = None
        for i in range(len(ratio_diff)//3, len(ratio_diff)*2//3):
            if ratio_diff[i] > threshold:
                vt1_idx = i
                break

        if vt1_idx is not None:
            vt1_row = df.iloc[vt1_idx]
            result['vt1_vo2'] = vt1_row.get('vo2')
            result['vt1_hr'] = int(vt1_row.get('hr')) if vt1_row.get('hr') else None
            result['vt1_time_sec'] = vt1_row.get('t_sec')
            result['confidence'] = 0.7

        # VT2: RER이 1.0을 넘는 지점
        if 'rer' in df.columns:
            rer_values = df['rer'].values
            for i, rer in enumerate(rer_values):
                if rer and rer >= 1.0:
                    vt2_row = df.iloc[i]
                    result['vt2_vo2'] = vt2_row.get('vo2')
                    result['vt2_hr'] = int(vt2_row.get('hr')) if vt2_row.get('hr') else None
                    result['vt2_time_sec'] = vt2_row.get('t_sec')
                    break

        return result

    def _detect_vt_ventilatory_equivalent(self, df: pd.DataFrame, result: Dict) -> Dict:
        """Ventilatory Equivalent 방법으로 VT 감지"""
        if 've_vo2' not in df.columns or 've_vco2' not in df.columns:
            return result

        ve_vo2 = df['ve_vo2'].dropna()
        ve_vco2 = df['ve_vco2'].dropna()

        if len(ve_vo2) < 30:
            return result

        # VT1: VE/VO2가 증가하기 시작하면서 VE/VCO2는 아직 안정적인 지점
        # 이동 평균으로 스무딩
        window = min(15, len(ve_vo2) // 5)
        ve_vo2_smooth = ve_vo2.rolling(window=window, center=True, min_periods=1).mean()
        ve_vco2_smooth = ve_vco2.rolling(window=window, center=True, min_periods=1).mean()

        # 최소값 이후 증가 시작점
        min_ve_vo2_idx = ve_vo2_smooth.idxmin()
        for idx in ve_vo2_smooth.loc[min_ve_vo2_idx:].index:
            if ve_vo2_smooth.loc[idx] > ve_vo2_smooth.loc[min_ve_vo2_idx] * 1.05:  # 5% 증가
                vt1_row = df.loc[idx]
                result['vt1_vo2'] = vt1_row.get('vo2')
                result['vt1_hr'] = int(vt1_row.get('hr')) if vt1_row.get('hr') else None
                result['vt1_time_sec'] = vt1_row.get('t_sec')
                result['confidence'] = 0.6
                break

        # VT2: VE/VCO2도 증가하기 시작하는 지점
        min_ve_vco2_idx = ve_vco2_smooth.idxmin()
        for idx in ve_vco2_smooth.loc[min_ve_vco2_idx:].index:
            if ve_vco2_smooth.loc[idx] > ve_vco2_smooth.loc[min_ve_vco2_idx] * 1.05:
                vt2_row = df.loc[idx]
                result['vt2_vo2'] = vt2_row.get('vo2')
                result['vt2_hr'] = int(vt2_row.get('hr')) if vt2_row.get('hr') else None
                result['vt2_time_sec'] = vt2_row.get('t_sec')
                break

        return result

    def _detect_vt_rer(self, df: pd.DataFrame, result: Dict) -> Dict:
        """RER 기반 VT 감지 (간단한 방법)"""
        if 'rer' not in df.columns:
            return result

        rer = df['rer'].dropna()
        if len(rer) < 20:
            return result

        # VT1: RER이 0.85-0.90 구간에 처음 도달하는 지점
        for idx in rer.index:
            if 0.85 <= rer.loc[idx] <= 0.95:
                vt1_row = df.loc[idx]
                result['vt1_vo2'] = vt1_row.get('vo2')
                result['vt1_hr'] = int(vt1_row.get('hr')) if vt1_row.get('hr') else None
                result['vt1_time_sec'] = vt1_row.get('t_sec')
                result['confidence'] = 0.5
                break

        # VT2: RER이 1.0에 도달하는 지점
        for idx in rer.index:
            if rer.loc[idx] >= 1.0:
                vt2_row = df.loc[idx]
                result['vt2_vo2'] = vt2_row.get('vo2')
                result['vt2_hr'] = int(vt2_row.get('hr')) if vt2_row.get('hr') else None
                result['vt2_time_sec'] = vt2_row.get('t_sec')
                break

        return result
