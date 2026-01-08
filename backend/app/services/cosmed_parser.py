"""COSMED K5 Excel File Parser - CPET 데이터 파싱"""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
import re

import pandas as pd
import numpy as np


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

        return result

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

        return result
