# [SRS] 대사 분석 데이터베이스 및 시각화 플랫폼 요구사항 정의서

## 1. 프로젝트 개요

### 1.1 목표
COSMED K5 장비에서 추출된 호흡 가스 분석 데이터(CPET)를 자동 수집, DB화하여, 피험자(일반인/선수)의 대사 프로파일(FATMAX, VO2MAX 등)을 분석하고 시각화하는 웹 기반 플랫폼 구축.

### 1.2 주요 사용자
- **관리자(교수/연구원)**: 데이터 업로드, 코호트 분석(통계), 그룹핑, 메타데이터 관리
- **피험자(선수/일반인)**: 본인의 대사 프로파일 대시보드 열람, 과거 기록 비교

### 1.3 핵심 설계 원칙
- **유지보수와 엔지니어링의 용이성** 최우선
- 단일 DB 인스턴스 관리로 복잡도 최소화
- 확장 가능한 아키텍처

---

## 2. 시스템 아키텍처 및 데이터 흐름

### 2.1 아키텍처 구성

```
┌─────────────────┐
│  K5 Device      │
│  (.xlsx, .csv)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Ingestion Layer │ ← Raw Data 파싱 및 전처리
│ (결측치, Smoothing)│
└────────┬────────┘
         │
         ▼
┌──────────────────┐
│ Calculation      │ ← FATMAX, VO2MAX, Zone 설정
│ Engine           │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────┐
│      Storage Layer           │
│                              │
│ • MetaData DB (RDB)          │
│   - 피험자 정보, 병력, 태깅   │
│                              │
│ • TimeSeries DB              │
│   - Breath-by-Breath 데이터  │
│   - PostgreSQL + TimescaleDB │
└────────┬─────────────────────┘
         │
         ▼
┌──────────────────┐
│ Presentation     │ ← 웹 대시보드
│ Layer            │   (React + Recharts)
└──────────────────┘
```

### 2.2 기술 스택
- **Backend**: Python FastAPI
- **Frontend**: React.js + Recharts
- **Database**: PostgreSQL with TimescaleDB Extension
- **Infrastructure**: AWS ECS/Elastic Beanstalk, RDS for PostgreSQL

---

## 3. 상세 기능 요구사항 (Functional Requirements)

### 3.1 데이터 수집 및 처리 (Data Ingestion)

#### 3.1.1 K5 포맷 파싱
**지원 파일 형식**: COSMED K5 Excel 파일 (`.xlsx`)

**파일 명명 규칙**:
```
[Name] [YYYYMMDD] CPET [Protocol]_[Timestamp].xlsx
예: Park Yongdoo 20241217 CPET BxB_20241218113618.xlsx
```

**프로토콜 타입**:
- **BxB (Breath-by-Breath)**: 호흡 단위 측정 (고해상도, ~600-700 데이터 포인트/테스트)
- **MIX (Mixed)**: 혼합 측정 방식 (~100-200 데이터 포인트/테스트)

**Excel 파일 구조**:
- **Data 시트**:
  - Row 1-10: 메타데이터 헤더
    - 피험자 정보: Name, Gender, Age, Height, Weight, D.O.B.
    - 테스트 정보: Test date, Test Time, Test Type (Maximal/Submaximal), Test Duration
    - 환경 조건: Barometric Pressure, Ambient Temperature, Humidity
  - Row 11: 컬럼 헤더 (t, Rf, VT, VE, VO2, VCO2, RQ, HR, Bike Power 등 50-85개 컬럼)
  - Row 12~: 시계열 Breath-by-Breath 데이터

- **Results 시트**:
  - 구간별 요약 데이터 (Rest, Warm-Up, FatMax, VT1/LT1, VT2/LT2, Max)
  - 예측값(Pred)과 실측값(Meas) 비교
  - % Pred (예상 대비 백분율)

**주요 측정 컬럼**:
- **시간**: t (시간, datetime.time 형식)
- **호흡**: Rf (호흡수, breaths/min), VT (일회 호흡량, L), VE (분당 환기량, L/min)
- **가스 교환**: VO2 (mL/min), VCO2 (mL/min), RQ/RER
- **심혈관**: HR (심박수, bpm), VO2/HR (산소 맥박, mL/beat)
- **운동 부하**: Bike Power (Watt), Bike Torque@crank (Nm), Cadence (RPM)
- **에너지 대사**: Fat (지방 연소, kcal/day), CHO (탄수화물, kcal/day), PRO (단백질, kcal/day)
- **기타**: Phase, Marker (대부분 'NONE' 또는 비어있음 - 자동 감지 필요)

**데이터 검증**:
- 필수 컬럼 존재 여부 확인 (t, VO2, VCO2, HR, Bike Power)
- 생리학적 범위 체크 (HR: 40-220 bpm, VO2 > 0, RER: 0.6-1.5)
- 결측치 및 이상치 감지

#### 3.1.2 자동 계산 (Derived Metrics)
Raw Data 기반 다음 지표 재계산/추출:

1. **RER (Respiratory Exchange Ratio)**
   - 계산식: $\text{RER} = \frac{VCO_2}{VO_2}$
   - 용도: 지방/탄수화물 대사 비율 추정

2. **Fat/Carb Oxidation Rate**
   - Frayn 공식 또는 Jeukendrup & Wallis 공식 적용
   - 운동 강도별 지방/탄수화물 연소량(g/min) 산출

3. **Smoothing**
   - 호흡 데이터 노이즈 제거
   - Moving Average 필터 (10초, 30초 등) 옵션 제공

#### 3.1.3 구간 자동 감지 (Phase Detection)
**중요**: COSMED K5 Excel 파일의 Phase/Marker 컬럼은 대부분 비어있거나 'NONE'으로 표시됨.  
따라서 **Bike Power 기반 자동 구간 감지**가 필수적.

**구간 정의**:
- **Rest (휴식)**: 
  - Bike Power = 0 또는 < 20W
  - 테스트 시작 후 초반 2-5분
  - HR 안정 상태 (변화율 < 5 bpm/min)
  
- **Warm-up (준비운동)**:
  - Bike Power: 낮고 일정 (20W ~ 100W)
  - 30초 이상 지속되는 첫 번째 일정한 부하 구간
  - RER < 0.85 (유산소 대사 우세)
  
- **Exercise (본운동)**:
  - Bike Power 계단식/선형 증가 (Ramp 프로토콜)
  - 또는 단계별 증가 (Step 프로토콜)
  - Warm-up 종료 지점부터 최대 부하 도달까지
  
- **Peak (최대 부하)**:
  - Bike Power 최대값 도달
  - VO2 plateau (30초 이상 변화 < 150 mL/min)
  - RER > 1.10 (무산소 대사 우세)
  
- **Recovery (회복)**:
  - Bike Power 급격히 감소 (피크의 50% 이하)
  - 또는 Bike Power = 0
  - Peak 이후 구간

**구간 감지 알고리즘 개선사항**:
- Moving Average 스무딩 (10-30초 윈도우)
- Bike Power 변화율 기반 구간 전환점 탐지
- HR 및 RER 보조 지표 활용
- 프로토콜별 맞춤 감지 (BxB vs MIX)

---

### 3.2 대사 프로파일링 (Profiling)

#### 3.2.1 FATMAX 분석
- 지방 연소량 최대 운동 강도(HR 또는 Watt) 자동 감지
- MFO (Maximal Fat Oxidation) 시점 마킹
- 그래프 상 시각적 표시

#### 3.2.2 VO2MAX 판별
- 테스트 구간 중 $VO_2$ 피크 값 자동 추출
- $VO_2/kg$ 환산 (체중 대비 상대값)
- 신뢰도 지표 제공

#### 3.2.3 Threshold 감지 (옵션)
- **VT1 (Ventilatory Threshold 1)**: 유산소 역치
- **VT2 (Ventilatory Threshold 2)**: 무산소 역치
- 그래프 상 자동 제안 + 연구자 수동 보정 기능 (드래그)

---

### 3.3 시각화 대시보드 (Visualization)

#### 3.3.1 Single Test View (단일 실험 분석)
- **X축**: 시간(Time) 또는 부하(Watt/Speed)
- **Y축(Multi-axis)**: HR, VO2, VCO2, RER, Fat Oxidation 중첩 표시
- **인터랙티브 기능**:
  - 특정 구간(Warm-up 제외) 선택
  - 확대/축소 (Zoom In/Out)
  - 마커 추가/제거
  - 데이터 포인트 툴팁

#### 3.3.2 Longitudinal View (시계열 변화 추적)
- 동일 피험자의 날짜별 테스트 결과 비교
  - VO2max 변화량 추이
  - FATMAX 지점 이동
  - HR Zone 변화
- **"Before & After" 비교 모드**
  - 훈련 프로그램 전후 비교
  - 2개 테스트 오버레이

#### 3.3.3 Cohort View (집단 비교)
- 그룹별 평균/중앙값 표시
- 백분위 범위 표시 (10%, 50%, 90%)
- 개인 데이터 + 그룹 평균 오버레이

---

### 3.4 연구 및 관리 기능 (Research Tools)

#### 3.4.1 메타데이터 태깅 시스템
- **피험자 정보 태깅**:
  - 성별, 나이, 직업군
  - 병력(고혈압, 당뇨, 기타)
  - 운동 경력, 훈련 수준
  - 사용자 정의 태그
- **태그 기반 필터링**:
  - 예: "40대 남성 중 고혈압이 있는 그룹의 평균 FATMAX 심박수 조회"
  - 다중 조건 필터링 지원

#### 3.4.2 데이터 내보내기
- 필터링된 코호트 데이터 일괄 다운로드
- 지원 형식: Excel (.xlsx), CSV
- 익명화 옵션 제공

#### 3.4.3 통계 분석 도구
- 그룹 간 T-test, ANOVA
- 상관관계 분석
- 회귀 분석 (선형/비선형)

---

## 4. 비기능 요구사항 (Non-Functional Requirements)

### 4.1 보안 및 개인정보 보호
- **데이터 암호화**:
  - DB 저장: AES-256 암호화
  - 전송: HTTPS/TLS 1.3
- **접근 제어**:
  - Role-based Access Control (RBAC)
  - Admin, Researcher, Subject 권한 분리
- **개인정보 마스킹**:
  - 실명과 research_id 분리
  - GDPR/HIPAA 준수

### 4.2 성능
- **API 응답 시간**: 95% 요청 < 500ms
- **대용량 데이터 처리**: 10,000+ 데이터 포인트/테스트 지원
- **동시 사용자**: 최소 100명 지원

### 4.3 확장성
- 수평적 확장 가능한 아키텍처
- 컨테이너 기반 배포 (Docker/Kubernetes)

### 4.4 유지보수성
- 단일 DB 인스턴스 관리
- 명확한 API 문서화 (OpenAPI/Swagger)
- 코드 품질: 80% 이상 테스트 커버리지

---## 5. 데이터베이스 설계

### 5.1 데이터베이스 아키텍처 선택
**PostgreSQL + TimescaleDB Extension** 사용 권장

**선택 이유**:
- 단일 DB 인스턴스(AWS RDS) 관리로 개발 복잡도 감소
- 관계형 데이터(사용자 정보)와 시계열 데이터(호흡 데이터)를 JOIN 쿼리로 통합 처리
- FastAPI 백엔드 구현 간소화
- 별도 NoSQL(InfluxDB 등) 불필요

### 5.2 시스템 아키텍처 구성 (AWS SaaS)
### 5.3 데이터베이스 스키마 설계

#### 5.3.1 사용자/피험자 테이블 (subjects)
실제 이름과 연구용 ID를 분리하여 보안 강화 (PII 마스킹 대상)

```sql
-- 사용자/피험자 테이블
CREATE TABLE subjects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_id VARCHAR(50) UNIQUE NOT NULL, -- 예: "SUB-2024-001" (익명화된 ID)
    encrypted_name VARCHAR(255), -- 실제 이름은 암호화하여 저장 (필요시에만 복호화)
    birth_year INT,
    gender VARCHAR(10), -- 'M', 'F', 'Other'
    job_category VARCHAR(50), -- 직업군
    medical_history JSONB, -- 병력 태그 (예: ["HTN", "DM"])
    training_level VARCHAR(20), -- 'Beginner', 'Intermediate', 'Advanced', 'Elite'
    weight_kg DOUBLE PRECISION,
    height_cm DOUBLE PRECISION,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_subjects_research_id ON subjects(research_id);
CREATE INDEX idx_subjects_gender_birth_year ON subjects(gender, birth_year);
```

#### 5.3.2 실험(Test) 메타데이터 테이블 (cpet_tests)
한 번의 실험에 대한 요약 결과 (COSMED K5 Results 시트 내용 포함)

```sql
-- 실험(Test) 메타데이터 테이블
CREATE TABLE cpet_tests (
    test_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id UUID REFERENCES subjects(id) ON DELETE CASCADE,
    test_date TIMESTAMP NOT NULL,
    test_time TIME, -- 테스트 시작 시간
    protocol_name VARCHAR(100), -- 예: "Ramp Protocol", "Step Protocol"
    protocol_type VARCHAR(10), -- 'BxB' (Breath-by-Breath) or 'MIX' (Mixed)
    test_type VARCHAR(20) DEFAULT 'Maximal', -- 'Maximal', 'Submaximal'
    maximal_effort VARCHAR(20), -- 'Confirmed', 'Unconfirmed'
    test_duration TIME, -- 총 테스트 시간 (HH:MM:SS)
    exercise_duration TIME, -- 실제 운동 시간
    
    -- 환경 조건 (COSMED K5 기록)
    barometric_pressure DOUBLE PRECISION, -- mmHg
    ambient_temp DOUBLE PRECISION, -- °C
    ambient_humidity DOUBLE PRECISION, -- %
    device_temp DOUBLE PRECISION, -- °C (Flowmeter 온도)
    
    -- 신체 정보 (테스트 당시)
    weight_kg DOUBLE PRECISION,
    bsa DOUBLE PRECISION, -- Body Surface Area (m²)
    bmi DOUBLE PRECISION, -- BMI (kg/m²)
    
    -- 주요 분석 결과 (Results.csv)
    vo2_max DOUBLE PRECISION, -- L/min
    vo2_max_rel DOUBLE PRECISION, -- mL/kg/min
    vco2_max DOUBLE PRECISION,
    hr_max INT,
    
    -- FATMAX 관련
    fat_max_hr INT,
    fat_max_watt DOUBLE PRECISION,
    fat_max_g_min DOUBLE PRECISION, -- g/min
    
    -- Threshold 관련
    vt1_hr INT,
    vt1_vo2 DOUBLE PRECISION,
    vt2_hr INT,
    vt2_vo2 DOUBLE PRECISION,
    
    -- 분석 설정 정보
    calc_method VARCHAR(20) DEFAULT 'Frayn', -- 'Frayn', 'Jeukendrup' 등
    smoothing_window INT DEFAULT 10, -- seconds
    
    -- 구간 정보
    warmup_end_sec INT,
    test_end_sec INT,
    
    -- 기타
    notes TEXT,
    data_quality_score DOUBLE PRECISION, -- 데이터 품질 점수 (0-100)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_cpet_tests_subject_id ON cpet_tests(subject_id);
CREATE INDEX idx_cpet_tests_test_date ON cpet_tests(test_date);
CREATE INDEX idx_cpet_tests_subject_date ON cpet_tests(subject_id, test_date);
```

#### 5.3.3 호흡 데이터 테이블 (breath_data) - TimescaleDB Hypertable
COSMED K5 Excel 파일의 Data 시트 시계열 데이터 저장

```sql
-- 호흡 데이터 (Raw Data) - Hypertable
CREATE TABLE breath_data (
    time TIMESTAMP NOT NULL, -- 측정 절대 시간
    test_id UUID NOT NULL, -- 파티셔닝 키 역할
    
    -- 주요 측정값 (Raw Data from COSMED K5)
    t_sec DOUBLE PRECISION, -- 실험 시작 후 경과 시간 (초)
    rf DOUBLE PRECISION, -- 호흡수 (breaths/min)
    vt DOUBLE PRECISION, -- 일회 호흡량 (L)
    vo2 DOUBLE PRECISION, -- 산소 섭취량 (mL/min)
    vco2 DOUBLE PRECISION, -- 이산화탄소 배출량 (mL/min)
    ve DOUBLE PRECISION, -- 분당 환기량 (L/min)
    hr INT, -- 심박수 (bpm)
    vo2_hr DOUBLE PRECISION, -- 산소 맥박 (mL/beat)
    
    -- 운동 부하 관련
    bike_power INT, -- Watt (구간 감지용 핵심 데이터)
    bike_torque DOUBLE PRECISION, -- Nm
    cadence INT, -- RPM (페달 회전수)
    
    -- 가스 분획
    feo2 DOUBLE PRECISION, -- 호기 산소 농도 (%)
    feco2 DOUBLE PRECISION, -- 호기 이산화탄소 농도 (%)
    feto2 DOUBLE PRECISION, -- End-tidal 산소 (%)
    fetco2 DOUBLE PRECISION, -- End-tidal 이산화탄소 (%)
    
    -- 환기 비율
    ve_vo2 DOUBLE PRECISION, -- 환기 당량 (VE/VO2)
    ve_vco2 DOUBLE PRECISION, -- 환기 당량 (VE/VCO2)
    
    -- 계산된 지표 (Backend에서 계산 후 저장)
    rer DOUBLE PRECISION, -- 호흡교환율 (VCO2/VO2)
    fat_oxidation DOUBLE PRECISION, -- 지방 연소 (g/min)
    cho_oxidation DOUBLE PRECISION, -- 탄수화물 연소 (g/min)
    pro_oxidation DOUBLE PRECISION, -- 단백질 연소 (g/min, 옵션)
    vo2_rel DOUBLE PRECISION, -- mL/kg/min (체중 대비)
    mets DOUBLE PRECISION, -- Metabolic Equivalents
    
    -- 에너지 소비 (from COSMED K5)
    ee_total DOUBLE PRECISION, -- 총 에너지 소비 (kcal)
    ee_kcal_day DOUBLE PRECISION, -- kcal/day
    
    -- 품질 지표
    is_valid BOOLEAN DEFAULT true, -- 데이터 유효성
    phase VARCHAR(20), -- 'Rest', 'Warmup', 'Exercise', 'Peak', 'Recovery' (자동 감지)
    
    PRIMARY KEY (time, test_id)
);

-- TimescaleDB Hypertable 변환 (자동 파티셔닝)
SELECT create_hypertable('breath_data', 'time');

-- 인덱스
CREATE INDEX idx_breath_data_test_id ON breath_data(test_id, time DESC);
CREATE INDEX idx_breath_data_phase ON breath_data(test_id, phase);
```

#### 5.3.4 코호트 통계 테이블 (cohort_stats)
배치 작업으로 계산된 그룹별 통계 저장

```sql
-- 코호트 통계 테이블
CREATE TABLE cohort_stats (
    stat_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gender VARCHAR(10),
    age_group VARCHAR(20), -- '20-29', '30-39', etc.
    training_level VARCHAR(20),
    
    -- 통계값
    metric_name VARCHAR(50), -- 'vo2_max', 'fat_max_hr', etc.
    mean_value DOUBLE PRECISION,
    median_value DOUBLE PRECISION,
    std_dev DOUBLE PRECISION,
    percentile_10 DOUBLE PRECISION,
    percentile_25 DOUBLE PRECISION,
    percentile_75 DOUBLE PRECISION,
    percentile_90 DOUBLE PRECISION,
    
    sample_size INT, -- 표본 크기
    last_updated TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(gender, age_group, training_level, metric_name)
);

-- 인덱스
CREATE INDEX idx_cohort_stats_lookup ON cohort_stats(gender, age_group, training_level, metric_name);
```

#### 5.3.5 사용자 계정 테이블 (users)
인증 및 권한 관리

```sql
-- 사용자 계정 테이블
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL, -- 'admin', 'researcher', 'subject'
    subject_id UUID REFERENCES subjects(id) ON DELETE SET NULL, -- subject인 경우 연결
    
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_subject_id ON users(subject_id);
```

---
## 6. 주요 기능 구현 전략

### 6.1 구간 자동 감지 (Phase Detection)
업로드된 CSV 데이터에서 Bike Power(와트)와 HR(심박수)를 이용한 자동 구간 분리

#### 6.1.1 구간 정의
- **Rest (휴식)**: Bike Power = 0, 초반 3분
- **Warm-up**: Bike Power 낮고 일정 (50W ~ 100W)
- **Exercise (본운동)**: Bike Power 계단식/선형 증가 (Ramp)
- **Recovery**: Bike Power 0 또는 급격 감소

#### 6.1.2 구현 예시 (Python/FastAPI)

```python
# FastAPI Service Layer Logic Example
import pandas as pd
import numpy as np

def detect_phases(df: pd.DataFrame) -> dict:
    """
    자동 구간 감지 알고리즘
    
    Args:
        df: CSV 데이터를 담은 Pandas DataFrame
        
    Returns:
        dict: 구간 정보 (warmup_end, test_end 인덱스)
    """
    # 1. 윈도우 스무딩으로 노이즈 제거
    df['power_smooth'] = df['Bike Power'].rolling(window=10).mean()
    
    # 2. 운동 시작 지점 찾기 (20W 이상이 30초 이상 지속)
    power_threshold = 20
    duration_threshold = 30  # seconds
    
    exercise_mask = df['power_smooth'] > power_threshold
    exercise_start_idx = None
    
    for idx in df[exercise_mask].index:
        if (df.loc[idx:idx+duration_threshold, 'power_smooth'] > power_threshold).all():
            exercise_start_idx = idx
            break
    
    # 3. 운동 종료 지점 찾기 (최대 부하 후 파워가 떨어지는 시점)
    peak_power_idx = df['power_smooth'].idxmax()
    
    # 피크 이후 파워가 50% 이하로 떨어지면 종료로 간주
    recovery_start_condition = (
        (df.index > peak_power_idx) & 
        (df['power_smooth'] < df['power_smooth'].max() * 0.5)
    )
    
    if recovery_start_condition.any():
        recovery_start_idx = df[recovery_start_condition].index[0]
    else:
        recovery_start_idx = df.index[-1]

    return {
        "rest_end": exercise_start_idx,
        "warmup_end": exercise_start_idx,  # 추가 로직으로 세분화 가능
        "test_end": recovery_start_idx,
        "recovery_start": recovery_start_idx
    }
```

---

### 6.2 대사 지표 계산

#### 6.2.1 RER (Respiratory Exchange Ratio) 계산

```python
def calculate_rer(df: pd.DataFrame) -> pd.DataFrame:
    """RER = VCO2 / VO2"""
    df['rer'] = df['vco2'] / df['vo2']
    # 이상치 제거 (RER은 일반적으로 0.7 ~ 1.3 범위)
    df.loc[(df['rer'] < 0.6) | (df['rer'] > 1.5), 'rer'] = np.nan
    return df
```

#### 6.2.2 Fat/Carb Oxidation Rate 계산 (Frayn 공식)

```python
def calculate_substrate_oxidation(df: pd.DataFrame, method: str = 'Frayn') -> pd.DataFrame:
    """
    지방/탄수화물 연소량 계산
    
    Frayn 공식:
    - Fat oxidation (g/min) = 1.67 * VO2 - 1.67 * VCO2
    - CHO oxidation (g/min) = 4.55 * VCO2 - 3.21 * VO2
    
    Args:
        df: 호흡 데이터
        method: 'Frayn' or 'Jeukendrup'
    """
    if method == 'Frayn':
        df['fat_oxidation'] = 1.67 * df['vo2'] - 1.67 * df['vco2']
        df['cho_oxidation'] = 4.55 * df['vco2'] - 3.21 * df['vo2']
    elif method == 'Jeukendrup':
        # Jeukendrup & Wallis 공식 (더 정밀)
        df['fat_oxidation'] = 1.695 * df['vo2'] - 1.701 * df['vco2']
        df['cho_oxidation'] = 4.585 * df['vco2'] - 3.226 * df['vo2']
    
    # 음수 값 처리 (생리학적으로 불가능)
    df.loc[df['fat_oxidation'] < 0, 'fat_oxidation'] = 0
    df.loc[df['cho_oxidation'] < 0, 'cho_oxidation'] = 0
    
    return df
```

#### 6.2.3 FATMAX 및 VO2MAX 자동 감지

```python
def detect_fatmax(df: pd.DataFrame, test_phases: dict) -> dict:
    """
    FATMAX 지점 감지
    
    Returns:
        dict: {
            'fatmax_hr': int,
            'fatmax_watt': float,
            'mfo': float  # Maximal Fat Oxidation (g/min)
        }
    """
    # 운동 구간만 추출
    exercise_df = df.loc[test_phases['warmup_end']:test_phases['test_end']]
    
    # 지방 연소량이 최대인 지점 찾기
    fatmax_idx = exercise_df['fat_oxidation'].idxmax()
    
    return {
        'fatmax_hr': int(exercise_df.loc[fatmax_idx, 'hr']),
        'fatmax_watt': float(exercise_df.loc[fatmax_idx, 'bike_power']),
        'mfo': float(exercise_df.loc[fatmax_idx, 'fat_oxidation'])
    }

def detect_vo2max(df: pd.DataFrame, weight_kg: float, test_phases: dict) -> dict:
    """
    VO2MAX 감지
    
    Returns:
        dict: {
            'vo2_max': float,  # L/min
            'vo2_max_rel': float,  # mL/kg/min
            'hr_max': int
        }
    """
    exercise_df = df.loc[test_phases['warmup_end']:test_phases['test_end']]
    
    # VO2 최대값 (마지막 30초 평균으로 안정화)
    vo2_max_window = exercise_df.nlargest(30, 'vo2')
    vo2_max = vo2_max_window['vo2'].mean()
    
    # 해당 시점의 심박수
    vo2_max_idx = exercise_df['vo2'].idxmax()
    hr_max = int(exercise_df.loc[vo2_max_idx, 'hr'])
    
    return {
        'vo2_max': float(vo2_max),
        'vo2_max_rel': float(vo2_max * 1000 / weight_kg),  # mL/kg/min
        'hr_max': hr_max
    }
```

---

### 6.3 데이터 보안 및 마스킹

#### 6.3.1 암호화 구현

```python
from cryptography.fernet import Fernet
import os

# 환경 변수에서 암호화 키 로드
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')
cipher = Fernet(ENCRYPTION_KEY)

def encrypt_name(name: str) -> str:
    """이름 암호화"""
    return cipher.encrypt(name.encode()).decode()

def decrypt_name(encrypted_name: str) -> str:
    """이름 복호화 (관리자 권한 필요)"""
    return cipher.decrypt(encrypted_name.encode()).decode()
```

#### 6.3.2 접근 제어 (RBAC)

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """관리자 권한 필수"""
    # JWT 토큰 검증 로직
    user = verify_jwt_token(credentials.credentials)
    if user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user

def require_researcher(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """연구자 이상 권한 필수"""
    user = verify_jwt_token(credentials.credentials)
    if user.role not in ['admin', 'researcher']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Researcher access required"
        )
    return user
```

---

### 6.4 코호트 분석 및 통계

#### 6.4.1 배치 작업 (Background Task)

```python
from fastapi_utils.tasks import repeat_every
from datetime import datetime

@repeat_every(seconds=86400)  # 매일 1회 실행
async def update_cohort_statistics():
    """
    성별/연령대별 평균, 백분위 계산 및 cohort_stats 테이블 갱신
    """
    # 모든 피험자 데이터 조회
    subjects = await db.fetch_all("SELECT * FROM subjects")
    
    for gender in ['M', 'F']:
        for age_group in ['20-29', '30-39', '40-49', '50-59', '60+']:
            # 해당 코호트의 테스트 데이터 조회
            cohort_tests = await get_cohort_tests(gender, age_group)
            
            # 통계 계산
            stats = calculate_cohort_statistics(cohort_tests)
            
            # DB 저장
            await save_cohort_stats(gender, age_group, stats)
```

#### 6.4.2 실시간 랭킹/백분위 제공

```python
async def get_user_percentile(subject_id: str, metric_name: str) -> dict:
    """
    사용자의 해당 지표에 대한 백분위 조회
    
    Returns:
        dict: {
            'user_value': float,
            'percentile': float,  # 0-100
            'cohort_mean': float,
            'cohort_median': float
        }
    """
    # 사용자 정보 조회
    subject = await get_subject(subject_id)
    age_group = calculate_age_group(subject.birth_year)
    
    # 최근 테스트 결과
    latest_test = await get_latest_test(subject_id)
    user_value = getattr(latest_test, metric_name)
    
    # 코호트 통계 조회
    cohort_stat = await get_cohort_stat(
        subject.gender, 
        age_group, 
        metric_name
    )
    
    # 백분위 계산
    percentile = calculate_percentile(
        user_value,
        cohort_stat.mean_value,
        cohort_stat.std_dev
    )
    
    return {
        'user_value': user_value,
        'percentile': percentile,
        'cohort_mean': cohort_stat.mean_value,
        'cohort_median': cohort_stat.median_value
    }
```

---

## 7. API 설계

### 7.1 주요 API 엔드포인트

#### 7.1.1 인증 관련

```
POST   /api/auth/login          # 로그인
POST   /api/auth/logout         # 로그아웃
POST   /api/auth/refresh        # 토큰 갱신
GET    /api/auth/me             # 현재 사용자 정보
```

#### 7.1.2 피험자 관리

```
GET    /api/subjects            # 피험자 목록 조회 (필터링 지원)
POST   /api/subjects            # 피험자 등록
GET    /api/subjects/{id}       # 피험자 상세 조회
PUT    /api/subjects/{id}       # 피험자 정보 수정
DELETE /api/subjects/{id}       # 피험자 삭제
```

#### 7.1.3 테스트 관리

```
GET    /api/tests                           # 테스트 목록
POST   /api/tests/upload                    # CSV 파일 업로드 및 분석
GET    /api/tests/{test_id}                 # 테스트 요약 정보
GET    /api/tests/{test_id}/raw-data        # 시계열 Raw 데이터
GET    /api/tests/{test_id}/metrics         # 계산된 지표 (차트용)
PUT    /api/tests/{test_id}                 # 테스트 정보 수정
DELETE /api/tests/{test_id}                 # 테스트 삭제
```

#### 7.1.4 분석 및 시각화

```
GET    /api/tests/{test_id}/chart-data      # 차트 렌더링용 데이터
GET    /api/subjects/{id}/comparison        # 시계열 비교 데이터
GET    /api/subjects/{id}/percentile        # 코호트 대비 백분위
```

#### 7.1.5 통계 및 코호트 분석

```
GET    /api/cohort/stats                    # 코호트 통계 조회
POST   /api/cohort/filter                   # 필터링된 코호트 데이터
POST   /api/cohort/export                   # 데이터 내보내기
```

### 7.2 API 응답 예시

#### 7.2.1 테스트 차트 데이터 API

```json
GET /api/tests/{test_id}/chart-data

Response:
{
  "test_id": "uuid",
  "subject_id": "uuid",
  "test_date": "2024-01-15T10:00:00Z",
  "phases": {
    "rest_end": 180,
    "warmup_end": 300,
    "test_end": 1200,
    "recovery_start": 1200
  },
  "summary": {
    "vo2_max": 4.5,
    "vo2_max_rel": 56.2,
    "fat_max_hr": 145,
    "fat_max_watt": 180,
    "mfo": 0.65
  },
  "timeseries": [
    {
      "time": 0,
      "hr": 65,
      "vo2": 0.8,
      "vco2": 0.65,
      "rer": 0.81,
      "bike_power": 0,
      "fat_oxidation": 0.35,
      "cho_oxidation": 0.12
    },
    ...
  ],
  "markers": {
    "fatmax": {
      "time": 720,
      "hr": 145,
      "watt": 180
    },
    "vo2max": {
      "time": 1100,
      "hr": 185,
      "watt": 320
    }
  }
}
```

---

## 8. 개발 로드맵

### Phase 1: Core Infrastructure (4주)
- [ ] FastAPI 프로젝트 세팅 및 구조 설계
- [ ] PostgreSQL + TimescaleDB 연동
- [ ] 기본 인증 시스템 (JWT)
- [ ] CSV 파일 업로드 및 파싱 (Pandas)
- [ ] 데이터베이스 스키마 구현

### Phase 2: Analysis Engine (4주)
- [ ] Frayn/Jeukendrup 공식 구현
- [ ] 구간 자동 감지 알고리즘
- [ ] FATMAX, VO2MAX 자동 탐지
- [ ] VT1/VT2 감지 (옵션)
- [ ] 데이터 품질 검증 로직

### Phase 3: API Development (3주)
- [ ] RESTful API 엔드포인트 구현
- [ ] 차트용 데이터 API 최적화
- [ ] 필터링 및 검색 기능
- [ ] 데이터 내보내기 기능
- [ ] API 문서화 (OpenAPI/Swagger)

### Phase 4: Frontend Development (6주)
- [ ] React 프로젝트 세팅
- [ ] 인증 및 권한 관리 UI
- [ ] Single Test View (인터랙티브 차트)
- [ ] Longitudinal View (시계열 비교)
- [ ] Cohort View (그룹 통계)
- [ ] 피험자/테스트 관리 대시보드
- [ ] 반응형 디자인

### Phase 5: Advanced Features (4주)
- [ ] 코호트 분석 배치 작업
- [ ] 백분위 계산 및 시각화
- [ ] 통계 분석 도구 (T-test, ANOVA)
- [ ] Before & After 비교 모드
- [ ] 데이터 품질 스코어링
- [ ] 사용자 정의 태그 시스템

### Phase 6: Security & Optimization (3주)
- [ ] 데이터 암호화 구현
- [ ] RBAC 강화
- [ ] API Rate Limiting
- [ ] 성능 최적화 (쿼리, 캐싱)
- [ ] 보안 감사 및 취약점 점검

### Phase 7: Deployment & Testing (3주)
- [ ] AWS 인프라 구축 (ECS/RDS)
- [ ] CI/CD 파이프라인
- [ ] 통합 테스트
- [ ] 부하 테스트
- [ ] 사용자 매뉴얼 작성
- [ ] 프로덕션 배포

---

## 9. 기술적 고려사항

### 9.1 데이터 품질 관리
- **이상치 감지**: Statistical outlier detection (Z-score, IQR)
- **결측치 처리**: 선형 보간법 또는 제외
- **데이터 검증**: 생리학적 범위 체크 (HR: 40-220, VO2 > 0)

### 9.2 성능 최적화
- **TimescaleDB 압축**: 오래된 데이터 자동 압축
- **쿼리 최적화**: 적절한 인덱스, 파티셔닝
- **캐싱**: Redis를 활용한 통계 데이터 캐싱
- **비동기 처리**: Celery를 통한 백그라운드 작업

### 9.3 확장성 고려
- **마이크로서비스 전환 가능성**: 분석 엔진 분리
- **다중 테넌시**: 여러 연구기관 지원 대비
- **API 버저닝**: `/api/v1/`, `/api/v2/`

### 9.4 모니터링 및 로깅
- **애플리케이션 로깅**: Structured logging (JSON)
- **성능 모니터링**: AWS CloudWatch, Datadog
- **에러 트래킹**: Sentry
- **사용자 분석**: 대시보드 사용 패턴 추적

---

## 10. 위험 요소 및 대응 방안

### 10.1 기술적 위험
| 위험 | 영향도 | 확률 | 대응 방안 |
|------|--------|------|-----------|
| TimescaleDB 학습 곡선 | 중 | 중 | 공식 문서, 튜토리얼 활용, 초기 POC 수행 |
| 대용량 데이터 처리 성능 | 고 | 중 | 부하 테스트, 쿼리 최적화, 캐싱 전략 |
| 복잡한 알고리즘 구현 오류 | 고 | 중 | 단위 테스트, 기존 연구 논문 검증 |
| COSMED K5 Excel 파싱 복잡도 | 중 | 높음 | 다양한 샘플 파일 테스트, 에러 처리 강화 |
| Phase/Marker 컬럼 부재 | 높음 | 확정 | Bike Power 기반 자동 감지 알고리즘 구현 필수 |
| 프로토콜별 차이 (BxB vs MIX) | 중 | 높음 | 프로토콜 자동 감지 및 적응형 파싱 로직 |
| 보안 취약점 | 고 | 낮 | 보안 감사, 정기 업데이트, 침투 테스트 |

### 10.2 비기술적 위험
| 위험 | 영향도 | 확률 | 대응 방안 |
|------|--------|------|-----------|
| 요구사항 변경 | 중 | 고 | Agile 방법론, 빈번한 커뮤니케이션 |
| 개발 일정 지연 | 중 | 중 | 마일스톤 관리, 버퍼 시간 확보 |
| 사용자 피드백 부족 | 중 | 중 | 조기 프로토타입, 베타 테스트 |

---

## 11. 참고 자료

### 11.1 과학적 근거
- **Frayn, K. N. (1983)**: "Calculation of substrate oxidation rates in vivo from gaseous exchange"
- **Jeukendrup, A. E., & Wallis, G. A. (2005)**: "Measurement of substrate oxidation during exercise"
- **ACSM Guidelines**: Exercise testing and prescription standards

### 11.2 기술 문서
- [PostgreSQL Official Documentation](https://www.postgresql.org/docs/)
- [TimescaleDB Documentation](https://docs.timescale.com/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)
- [Recharts Documentation](https://recharts.org/)

### 11.3 관련 표준
- **HL7 FHIR**: 의료 데이터 교환 표준
- **GDPR**: 유럽 개인정보 보호 규정
- **HIPAA**: 미국 건강보험 이동성 및 책임에 관한 법률 (해당 시)

---

## 12. 용어 정의

| 용어 | 정의 |
|------|------|
| **CPET** | Cardiopulmonary Exercise Testing (심폐운동부하검사) |
| **VO2MAX** | 최대 산소 섭취량 (L/min 또는 mL/kg/min) |
| **FATMAX** | 지방 연소량이 최대가 되는 운동 강도 |
| **MFO** | Maximal Fat Oxidation (최대 지방 연소량, g/min) |
| **RER** | Respiratory Exchange Ratio (VCO2/VO2) |
| **VT1** | Ventilatory Threshold 1 (유산소 역치) |
| **VT2** | Ventilatory Threshold 2 (무산소 역치) |
| **HR** | Heart Rate (심박수, bpm) |
| **Rf** | Respiratory Frequency (호흡수, breaths/min) |
| **VE** | Ventilation (환기량, L/min) |

---

## 부록 A: 환경 설정 가이드

### A.1 개발 환경 요구사항

**Backend**:
```
Python 3.11+
FastAPI 0.100+
PostgreSQL 15+
TimescaleDB 2.11+
Pandas, NumPy, SciPy
```

**Frontend**:
```
Node.js 18+
React 18+
Recharts 2.5+
TypeScript 5+
```

### A.2 로컬 개발 환경 구축

```bash
# 1. PostgreSQL + TimescaleDB 설치 (Docker)
docker run -d --name cpet-db \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  timescale/timescaledb:latest-pg15

# 2. Backend 설정
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env 파일 편집

# 3. Database 마이그레이션
alembic upgrade head

# 4. Backend 실행
uvicorn main:app --reload

# 5. Frontend 설정 (별도 터미널)
cd frontend
npm install
npm run dev
```

---

## 부록 B: 데이터 샘플

## 부록 B: 데이터 샘플

### B.1 Excel 업로드 예시

**파일명**: `Park Yongdoo 20241217 CPET BxB_20241218113618.xlsx`

**Data 시트 구조**:
```
[Row 1-10: 메타데이터]
Row 1: ID, Test date, 12/17/2024, Barometric Pressure, 764 mmHg
Row 2: Name, Park Yongdoo, Test Time, 11:09:24 AM
Row 3: Gender, Male, Subject Type, Clinical
Row 4: Age, 57.09
Row 5: Height (cm), 176
Row 6: Weight (kg), 70
Row 7: D.O.B., 11/12/1967, Test Type, Maximal
Row 8: Maximal Effort, Unconfirmed
Row 9: Test Duration, 00:23:59
Row 10: Exercise Duration, 00:00:00

[Row 11: 컬럼 헤더]
t, Rf, VT, VE, IV, VO2, VCO2, RQ, HR, VO2/HR, FeO2, FeCO2, ...
..., Bike Power, Bike Torque@crank, Cadence, Fat, CHO, PRO, ...

[Row 12~: 시계열 데이터]
00:00:00, 23.62, 1.111, 26.244, 1097, 805.4, 622.3, 0.77, 111, 7.3, ..., 73, ...
00:00:03, 22.56, 1.698, 38.301, 700, 1530.2, 1161.0, 0.76, 111, 13.8, ..., 81, ...
00:00:07, 15.27, 2.512, 38.351, 1961, 1430.3, 1093.8, 0.76, 113, 12.7, ..., 81, ...
...
[총 668행 - BxB 프로토콜, 23분 59초 테스트]
```

**Results 시트 예시**:
```
Parameter | um | Meas. | Rest | Warm-Up | FatMax | VT1\LT1 | VT2\LT2 | Max | Pred | % Pred
----------|-------|-------|------|---------|--------|---------|---------|-----|------|-------
VO2       | mL/min| ...   | 800  | 1200    | 1800   | 2400    | 3000    |3500 | 3200 | 109%
HR        | bpm   | ...   | 65   | 90      | 120    | 145     | 165     | 185 | 163  | 113%
...
```

**데이터 특징**:
- BxB 프로토콜: 약 600-700 행 (20-30분 테스트)
- MIX 프로토콜: 약 100-200 행 (10-15분 테스트)
- 컬럼 수: BxB 80-85개, MIX 50-60개
- 측정 간격: 약 2-5초 (breath-by-breath)

### B.2 API 요청 예시

```bash
# 테스트 업로드 (COSMED K5 Excel 파일)
curl -X POST http://localhost:8000/api/tests/upload \
  -H "Authorization: Bearer {token}" \
  -F "file=@Park_Yongdoo_20241217_CPET_BxB.xlsx" \
  -F "subject_id=uuid" \
  -F "auto_detect_protocol=true" \
  -F "auto_calculate_metrics=true"

# 차트 데이터 조회
curl -X GET http://localhost:8000/api/tests/{test_id}/chart-data \
  -H "Authorization: Bearer {token}"
```

---

**문서 버전**: 1.1  
**최종 수정일**: 2026년 1월 7일  
**작성자**: [작성자명]  
**검토자**: [검토자명]

---

## 부록 C: 실제 데이터 분석 결과 (2026.01.07)

### C.1 분석 대상
- **총 파일 수**: 38개 COSMED K5 Excel 파일
- **피험자**: 16명 (Park Yongdoo, Hong Changsun, Kim Dongwook 등)
- **테스트 기간**: 2022년 12월 ~ 2025년 1월
- **파일 위치**: `/CPET_data/` 및 `/CPET_data/Ramp test_YPark/`

### C.2 핵심 발견사항

#### 1. 파일 형식 및 명명 규칙
**확인된 패턴**:
```
[Name] [YYYYMMDD] CPET [Protocol]_[Timestamp].xlsx
예시:
- Park Yongdoo 20241217 CPET BxB_20241218113618.xlsx
- Hong Changsun 20240718 CPET MIX_20240718125243.xlsx
- Kim Dongwook 20240627 9P Panel_20240627113011.pdf (일부 PDF 리포트 포함)
```

**프로토콜 분포**:
- BxB (Breath-by-Breath): 약 55% (21개)
- MIX (Mixed): 약 45% (17개)

#### 2. Excel 파일 구조
**Data 시트**:
- **메타데이터 행**: Row 1-10 (피험자 정보, 환경 조건)
- **헤더 행**: Row 11 (측정 컬럼명)
- **데이터 행**: Row 12~ (시계열 breath-by-breath 데이터)
- **컬럼 수**: 
  - BxB: 80-85개 컬럼
  - MIX: 50-60개 컬럼
- **데이터 포인트**:
  - BxB: 600-700행 (20-30분 테스트)
  - MIX: 100-200행 (10-15분 테스트)

**Results 시트**:
- 구간별 요약 (Rest, Warm-Up, FatMax, VT1/LT1, VT2/LT2, Max)
- 예측값(Pred) vs 실측값(Meas)
- % Pred (예상치 대비 백분율)

#### 3. 중요한 파싱 고려사항
**Phase/Marker 컬럼 부재**:
- 모든 샘플 파일에서 Phase, Marker 컬럼이 'NONE' 또는 빈값
- **결론**: Bike Power 기반 자동 구간 감지 알고리즘이 필수

**메타데이터 위치**:
- 고정된 행 번호에 특정 정보가 위치
- Row 1: Test date, Barometric Pressure
- Row 2: Name, Test Time
- Row 3: Gender
- Row 4: Age
- Row 5: Height
- Row 6: Weight
- Row 7: D.O.B., Test Type

**시간 데이터 형식**:
- 't' 컬럼: `datetime.time` 객체 (00:00:00 형식)
- 초 단위로 증가 (대략 2-5초 간격)

#### 4. 추가 구현 권장사항

**1) Excel 파싱 로직**:
```python
# 메타데이터 추출 (Row 1-10)
metadata = {
    'test_date': df_meta.iloc[0, 4],
    'test_time': df_meta.iloc[1, 4],
    'name': df_meta.iloc[1, 1],
    'gender': df_meta.iloc[2, 1],
    'age': df_meta.iloc[3, 1],
    'height_cm': df_meta.iloc[4, 1],
    'weight_kg': df_meta.iloc[5, 1],
    'dob': df_meta.iloc[6, 1],
    'test_type': df_meta.iloc[6, 4],
    'test_duration': df_meta.iloc[8, 4],
}

# 시계열 데이터 추출 (Row 12~)
df_data = pd.read_excel(file, sheet_name='Data', skiprows=11)
```

**2) 프로토콜 자동 감지**:
```python
def detect_protocol(filename: str) -> str:
    if 'BxB' in filename:
        return 'BxB'
    elif 'MIX' in filename:
        return 'MIX'
    else:
        # 데이터 포인트 수로 추정
        if len(df_data) > 400:
            return 'BxB'
        else:
            return 'MIX'
```

**3) 구간 감지 개선**:
- Bike Power의 rolling mean (30초 윈도우) 사용
- HR 변화율 보조 지표 활용
- RER 값으로 유산소/무산소 구간 구분
- 프로토콜별 다른 임계값 적용

#### 5. 데이터베이스 스키마 수정 제안
실제 데이터 분석 결과를 반영하여 다음 컬럼 추가 권장:

**cpet_tests 테이블**:
- `source_filename VARCHAR(255)` - 원본 파일명 저장
- `file_upload_timestamp TIMESTAMP` - 업로드 시간
- `parsing_status VARCHAR(20)` - 'success', 'partial', 'failed'
- `parsing_errors JSONB` - 파싱 중 발생한 오류/경고

**breath_data 테이블**:
- `raw_t_value TIME` - 원본 time 값 보존
- `data_source VARCHAR(10)` - 'BxB' or 'MIX' 구분

### C.3 테스트 데이터 통계
**분석된 피험자 프로파일**:
- 성별: 남성 주로 (샘플 기준)
- 연령대: 20대~60대
- 테스트 유형: 대부분 Maximal 테스트
- 반복 테스트: 일부 피험자는 20회 이상 (예: Park Yongdoo)

**권장 개발 우선순위**:
1. ✅ COSMED K5 Excel 파싱 엔진 (BxB, MIX 지원)
2. ✅ Bike Power 기반 자동 구간 감지
3. ✅ 메타데이터 자동 추출 및 검증
4. ⭐ Results 시트 파싱 (FatMax, VT1/VT2 값 추출)
5. ⭐ 프로토콜별 데이터 품질 검증
6. ⭐ 에러 핸들링 및 부분 파싱 지원