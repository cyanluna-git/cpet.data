# CPET Database Schema

## 개요

CPET 플랫폼은 PostgreSQL + TimescaleDB를 사용하여 시계열 데이터를 효율적으로 저장합니다.

## ERD (Entity Relationship Diagram)

```
┌─────────────┐       ┌──────────────┐       ┌─────────────────┐
│   users     │       │   subjects   │       │   cpet_tests    │
│ (계정 정보)  │──────▶│  (피험자 정보) │◀──────│  (테스트 메타)   │
└─────────────┘  1:1  └──────────────┘  1:N  └────────┬────────┘
                                                      │ 1:N
                                                      ▼
                                              ┌─────────────────┐
                                              │  breath_data    │
                                              │ (시계열 Raw 데이터)│
                                              └─────────────────┘
```

## 테이블 상세

### 1. subjects (피험자 마스터)

피험자의 기본 정보를 저장합니다.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | Primary Key |
| research_id | VARCHAR(50) | 연구용 ID (예: SUB-PAR-YON) |
| encrypted_name | VARCHAR(255) | 암호화된 이름 |
| birth_year | INTEGER | 출생년도 |
| gender | VARCHAR(10) | 성별 (M/F) |
| weight_kg | DOUBLE | 체중 (kg) |
| height_cm | DOUBLE | 신장 (cm) |
| training_level | VARCHAR(20) | 훈련 수준 |
| medical_history | JSONB | 의료 기록 |
| created_at | TIMESTAMP | 생성일시 |
| updated_at | TIMESTAMP | 수정일시 |

**인덱스:**
- `subjects_pkey`: PRIMARY KEY (id)
- `subjects_research_id_key`: UNIQUE (research_id)
- `idx_subjects_gender_birth_year`: (gender, birth_year)

---

### 2. cpet_tests (테스트 레코드)

각 CPET 테스트의 메타데이터와 분석 결과 Summary를 저장합니다.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| test_id | UUID | Primary Key |
| subject_id | UUID | FK → subjects.id |
| test_date | TIMESTAMP | 테스트 날짜 |
| test_time | TIME | 테스트 시간 |
| protocol_name | VARCHAR(100) | 프로토콜명 |
| protocol_type | VARCHAR(10) | BxB / MIX |
| test_type | VARCHAR(20) | Maximal / Submaximal |

**환경 조건:**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| barometric_pressure | DOUBLE | 기압 (mmHg) |
| ambient_temp | DOUBLE | 실온 (°C) |
| ambient_humidity | DOUBLE | 습도 (%) |
| weight_kg | DOUBLE | 테스트 시 체중 |
| bmi | DOUBLE | BMI |
| bsa | DOUBLE | 체표면적 |

**분석 결과 Summary:**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| vo2_max | DOUBLE | 최대 산소 섭취량 (ml/min) |
| vo2_max_rel | DOUBLE | 상대 VO2max (ml/kg/min) |
| vco2_max | DOUBLE | 최대 CO2 배출량 |
| hr_max | INTEGER | 최대 심박수 |
| fat_max_hr | INTEGER | FATMAX 시 심박수 |
| fat_max_watt | DOUBLE | FATMAX 시 파워 (W) |
| fat_max_g_min | DOUBLE | 최대 지방 연소율 (g/min) |
| vt1_hr | INTEGER | VT1 역치 심박수 |
| vt1_vo2 | DOUBLE | VT1 시 VO2 |
| vt2_hr | INTEGER | VT2 역치 심박수 |
| vt2_vo2 | DOUBLE | VT2 시 VO2 |

**분석 설정:**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| calc_method | VARCHAR(20) | 대사 계산 방법 (Frayn, Peronnet, Jeukendrup) |
| smoothing_window | INTEGER | 평활화 윈도우 크기 |
| warmup_end_sec | INTEGER | 워밍업 종료 시점 (초) |
| test_end_sec | INTEGER | 테스트 종료 시점 (초) |
| phase_metrics | JSON | 구간별 메트릭 (평균, 최대, 최소) |

**분석 태깅 (계획):**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| analysis_tags | JSONB | 테스트 유형/패턴 태깅 (Ramp/Step/Mixed 등) |
| processed_version | INTEGER | 정제 데이터셋 버전 |

**파일 추적:**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| source_filename | VARCHAR(255) | 원본 파일명 |
| file_upload_timestamp | TIMESTAMP | 업로드 시간 |
| parsing_status | VARCHAR(20) | 파싱 상태 (success/warning/error) |
| parsing_errors | JSONB | 파싱 에러 목록 |

**인덱스:**
- `cpet_tests_pkey`: PRIMARY KEY (test_id)
- `idx_cpet_tests_subject_id`: (subject_id)
- `idx_cpet_tests_test_date`: (test_date)
- `idx_cpet_tests_subject_date`: (subject_id, test_date)

---

### 3. breath_data (시계열 Raw 데이터)

매 호흡 데이터를 저장합니다. **TimescaleDB 하이퍼테이블**로 시계열 최적화되어 있습니다.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| time | TIMESTAMP | Primary Key (파티션 키) |
| test_id | UUID | FK → cpet_tests.test_id |
| t_sec | DOUBLE | 테스트 시작 후 경과 시간 (초) |

**Raw 측정값 (COSMED K5):**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| rf | DOUBLE | 호흡 빈도 (breaths/min) |
| vt | DOUBLE | 1회 호흡량 (L) |
| vo2 | DOUBLE | 산소 섭취량 (ml/min) |
| vco2 | DOUBLE | CO2 배출량 (ml/min) |
| ve | DOUBLE | 분당 환기량 (L/min) |
| hr | INTEGER | 심박수 (bpm) |
| vo2_hr | DOUBLE | 산소맥 (ml/beat) |

**운동 부하:**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| bike_power | INTEGER | 자전거 파워 (W) |
| bike_torque | DOUBLE | 토크 (Nm) |
| cadence | INTEGER | 케이던스 (rpm) |

**가스 분획:**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| feo2 | DOUBLE | 호기 O2 분획 |
| feco2 | DOUBLE | 호기 CO2 분획 |
| feto2 | DOUBLE | 호기말 O2 분획 |
| fetco2 | DOUBLE | 호기말 CO2 분획 |

**환기 비율:**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| ve_vo2 | DOUBLE | 환기 당량 O2 |
| ve_vco2 | DOUBLE | 환기 당량 CO2 |

**계산된 메트릭:**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| rer | DOUBLE | 호흡교환비 (VCO2/VO2) |
| fat_oxidation | DOUBLE | 지방 연소율 (g/min) |
| cho_oxidation | DOUBLE | 탄수화물 연소율 (g/min) |
| vo2_rel | DOUBLE | 상대 VO2 (ml/kg/min) |
| mets | DOUBLE | 대사 당량 |

**에너지 소비:**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| ee_total | DOUBLE | 총 에너지 소비 (kcal) |
| ee_kcal_day | DOUBLE | 일일 환산 에너지 소비 |

**품질 지표:**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| is_valid | BOOLEAN | 유효 데이터 여부 |
| phase | VARCHAR(20) | 자동 감지된 구간 (Rest, Warm-up, Exercise, Peak, Recovery) |
| data_source | VARCHAR(10) | 데이터 소스 (BxB/MIX) |

**인덱스:**
- `breath_data_pkey`: PRIMARY KEY (time, test_id)
- `idx_breath_data_test_id`: (test_id, time DESC)
- `idx_breath_data_phase`: (test_id, phase)
- `breath_data_time_idx`: (time DESC)

**TimescaleDB 파티셔닝:**
- 하이퍼테이블로 자동 시간 기반 파티셔닝
- 5개 청크로 분할 (데이터량에 따라 자동 조정)

---

### 4. breath_data_processed (차트 전용 정제 데이터셋) — 계획

Raw 데이터에서 전처리/빈닝/보간을 거친 차트 전용 시계열을 저장합니다.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | UUID | Primary Key |
| test_id | UUID | FK → cpet_tests.test_id |
| power_bin | INTEGER | Power bin (W) |
| t_sec | DOUBLE | 대표 시간(초) |
| vo2 | DOUBLE | 보간/정제된 VO2 |
| vco2 | DOUBLE | 보간/정제된 VCO2 |
| fat_oxidation | DOUBLE | 정제된 지방 산화율 |
| cho_oxidation | DOUBLE | 정제된 탄수화물 산화율 |
| rer | DOUBLE | 정제된 RER |
| ve | DOUBLE | 정제된 VE |
| vt | DOUBLE | 정제된 VT |
| hr | DOUBLE | 정제된 HR |
| cadence | DOUBLE | 정제된 Cadence |
| meta | JSONB | 전처리 메타데이터 (bin_size, method 등) |

---

## 관계 (Foreign Keys)

```sql
-- subjects → cpet_tests (1:N)
cpet_tests.subject_id → subjects.id (ON DELETE CASCADE)

-- cpet_tests → breath_data (1:N)
breath_data.test_id → cpet_tests.test_id (ON DELETE CASCADE)

-- subjects → users (1:1, Optional)
users.subject_id → subjects.id (ON DELETE SET NULL)
```

---

## 데이터 저장 흐름

```
Excel 업로드
    │
    ▼
┌────────────────────────────────────────────────────────┐
│ 1. cpet_tests 1건 생성                                  │
│    - 테스트 메타데이터 (날짜, 프로토콜, 환경)             │
│    - 분석 결과 Summary (VO2max, FATMAX, VT1/VT2)        │
│    - phase_metrics (JSON: 구간별 평균값)                │
├────────────────────────────────────────────────────────┤
│ 2. breath_data N건 생성 (예: 150~500 rows)              │
│    - 매 호흡 Raw 데이터 (VO2, VCO2, HR, Power...)       │
│    - 계산된 값 (fat_oxidation, cho_oxidation)          │
│    - 자동 감지된 phase (Rest, Warm-up, Exercise...)     │
└────────────────────────────────────────────────────────┘
```

---

## 쿼리 예시

### 피험자의 모든 테스트 조회
```sql
SELECT t.test_date, t.vo2_max, t.fat_max_g_min, t.hr_max
FROM cpet_tests t
JOIN subjects s ON t.subject_id = s.id
WHERE s.encrypted_name ILIKE '%Park%'
ORDER BY t.test_date DESC;
```

### 특정 테스트의 시계열 데이터 조회
```sql
SELECT t_sec, hr, vo2, rer, fat_oxidation, phase
FROM breath_data
WHERE test_id = 'uuid-here'
ORDER BY t_sec;
```

### 구간별 평균 지표
```sql
SELECT phase, 
       AVG(hr) as avg_hr, 
       AVG(vo2) as avg_vo2,
       AVG(fat_oxidation) as avg_fat_ox
FROM breath_data
WHERE test_id = 'uuid-here'
GROUP BY phase;
```

---

## 설계 장점

1. **Raw 데이터 보존** → 알고리즘 변경 시 재분석 가능
2. **Summary 저장** → 대시보드 빠른 조회 (breath_data 스캔 불필요)
3. **Cascade Delete** → 테스트 삭제 시 관련 breath_data 자동 삭제
4. **TimescaleDB 최적화** → 수백만 row도 빠른 시계열 쿼리
5. **JSON 필드 활용** → phase_metrics, parsing_errors 등 유연한 저장
