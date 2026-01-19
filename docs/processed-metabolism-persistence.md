# Processed Metabolism Persistence (전처리 대사 데이터 영속성)

## 개요

CPET 테스트의 대사 분석 파라미터와 전처리된 데이터를 DB에 저장하여, 사용자가 설정한 분석 조건을 재현하고 빠르게 불러올 수 있도록 하는 기능입니다.

## 워크플로우

```
┌─────────────────────────────────────────────────────────────────┐
│                        사용자 워크플로우                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 테스트 선택                                                  │
│       ↓                                                         │
│  2. GET /api/tests/{id}/processed-metabolism                    │
│       ↓                                                         │
│  ┌─────────────────┐     ┌─────────────────┐                   │
│  │ DB에 저장된      │ Yes │ 저장된 설정과    │                   │
│  │ 데이터 있음?     │────→│ 데이터 반환      │                   │
│  └────────┬────────┘     │ is_persisted=true│                   │
│           │ No           └─────────────────┘                   │
│           ↓                                                     │
│  ┌─────────────────┐                                           │
│  │ 기본 파라미터로   │                                           │
│  │ 실시간 계산      │                                           │
│  │ is_persisted=false│                                          │
│  └─────────────────┘                                           │
│           ↓                                                     │
│  3. 사용자가 파라미터 조정 (LOESS, Bin Size, Min Power, Trim)    │
│       ↓                                                         │
│  4. "저장" 버튼 클릭                                             │
│       ↓                                                         │
│  5. POST /api/tests/{id}/processed-metabolism                   │
│       ↓                                                         │
│  ┌─────────────────┐                                           │
│  │ 계산 후 DB에     │                                           │
│  │ Upsert 저장      │                                           │
│  │ is_persisted=true│                                           │
│  └─────────────────┘                                           │
│                                                                 │
│  * "리셋" 버튼: DELETE → 저장된 데이터 삭제 → 기본값으로 복원     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 데이터베이스 스키마

### 테이블: `processed_metabolism`

```sql
CREATE TABLE processed_metabolism (
    -- Primary Key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cpet_test_id UUID NOT NULL REFERENCES cpet_tests(test_id) ON DELETE CASCADE,

    -- ═══════════════════════════════════════════════════════════════
    -- 분석 설정 (Configuration)
    -- ═══════════════════════════════════════════════════════════════
    bin_size INTEGER NOT NULL DEFAULT 10,           -- Power Bin 크기 (5-30W)
    aggregation_method VARCHAR(20) DEFAULT 'median', -- median | mean | trimmed_mean
    loess_frac FLOAT NOT NULL DEFAULT 0.25,         -- LOESS 스무딩 강도 (0.1-0.5)
    smoothing_method VARCHAR(20) DEFAULT 'loess',   -- loess | savgol | moving_avg

    -- Phase Trimming
    exclude_rest BOOLEAN DEFAULT TRUE,
    exclude_warmup BOOLEAN DEFAULT TRUE,
    exclude_recovery BOOLEAN DEFAULT TRUE,
    min_power_threshold INTEGER,                    -- 최소 파워 임계값 (0-200W)

    -- Time-based Trimming (Analysis Window)
    trim_start_sec FLOAT,                           -- 분석 시작 시점 (초)
    trim_end_sec FLOAT,                             -- 분석 종료 시점 (초)

    -- Manual Override Flag
    is_manual_override BOOLEAN DEFAULT FALSE,       -- 사용자가 직접 저장한 경우 TRUE

    -- ═══════════════════════════════════════════════════════════════
    -- 전처리된 데이터 시리즈 (JSONB)
    -- ═══════════════════════════════════════════════════════════════
    raw_series JSONB,       -- 필터링된 원본 데이터 (trim, min_power 적용)
    binned_series JSONB,    -- 1차 전처리: Power Bin 집계 (10W 단위)
    smoothed_series JSONB,  -- 1차 전처리: LOESS 스무딩
    trend_series JSONB,     -- 2차 전처리: 다항식 보간 (Polynomial Trend)

    -- ═══════════════════════════════════════════════════════════════
    -- 대사 마커 (Metabolic Markers)
    -- ═══════════════════════════════════════════════════════════════
    -- FatMax
    fatmax_power INTEGER,           -- FatMax 파워 (W)
    fatmax_mfo FLOAT,               -- Maximum Fat Oxidation (g/min)
    fatmax_zone_min INTEGER,        -- FatMax Zone 하한 (W)
    fatmax_zone_max INTEGER,        -- FatMax Zone 상한 (W)
    fatmax_zone_threshold FLOAT DEFAULT 0.90,  -- MFO 비율 임계값 (90%)

    -- Crossover Point
    crossover_power INTEGER,        -- Crossover 파워 (W)
    crossover_fat_value FLOAT,      -- Fat oxidation at crossover (g/min)
    crossover_cho_value FLOAT,      -- CHO oxidation at crossover (g/min)

    -- ═══════════════════════════════════════════════════════════════
    -- 통계 및 메타데이터
    -- ═══════════════════════════════════════════════════════════════
    total_data_points INTEGER,      -- 전체 데이터 포인트 수
    exercise_data_points INTEGER,   -- 운동 구간 데이터 포인트 수
    binned_data_points INTEGER,     -- Bin 처리된 데이터 포인트 수

    processing_warnings JSONB,      -- 처리 중 발생한 경고
    processing_status VARCHAR(20) DEFAULT 'pending',  -- pending | completed | failed
    processed_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_processed_metabolism_cpet_test_id ON processed_metabolism(cpet_test_id);
CREATE INDEX idx_processed_metabolism_status ON processed_metabolism(processing_status);
```

## 데이터 시리즈 구조

### 1. `raw_series` - 필터링된 원본 데이터

trim_start_sec ~ trim_end_sec 구간 내, min_power_threshold 이상의 데이터만 포함.

```json
[
  {
    "power": 99.0,
    "fat_oxidation": 1.097,
    "cho_oxidation": 0.0,
    "hr": 127.0,
    "vo2": 2225.22,
    "vco2": 1568.16,
    "rer": 0.7,
    "ve_vo2": 20.4,
    "ve_vco2": 29.0,
    "count": 1
  },
  // ... 437개 데이터 포인트
]
```

### 2. `binned_series` - 1차 전처리 (Power Bin 집계)

10W 단위로 그룹화하여 Median/Mean 집계.

```json
[
  {
    "power": 90.0,
    "fat_oxidation": 0.888,
    "cho_oxidation": 0.148,
    "hr": 126.0,
    "vo2": 1916.58,
    "vco2": 1384.70,
    "rer": 0.72,
    "ve_vo2": 22.5,
    "ve_vco2": 31.1,
    "count": 3  // 해당 bin에 포함된 데이터 수
  },
  // ... 18개 데이터 포인트 (90W ~ 260W)
]
```

### 3. `smoothed_series` - 1차 전처리 (LOESS 스무딩)

binned_series에 LOESS 스무딩 적용.

```json
[
  {
    "power": 90.0,
    "fat_oxidation": 0.897,
    "cho_oxidation": 0.148,
    "hr": 125.85,
    "vo2": 1916.58,
    "vco2": 1384.70,
    "rer": 0.719,
    "ve_vo2": 22.5,
    "ve_vco2": 31.1,
    "count": null
  },
  // ... 18개 데이터 포인트
]
```

### 4. `trend_series` - 2차 전처리 (다항식 보간)

2차 다항식(Polynomial) 피팅으로 트렌드 추출.

```json
[
  {
    "power": 90.0,
    "fat_oxidation": 0.822,
    "cho_oxidation": 0.216,
    "hr": 120.18,
    "vo2": 1773.16,
    "vco2": 1233.81,
    "rer": 0.722,
    "ve_vo2": 22.38,
    "ve_vco2": 31.98,
    "count": null
  },
  // ... 18개 데이터 포인트
]
```

## API 엔드포인트

### GET `/api/tests/{test_id}/processed-metabolism`

저장된 데이터가 있으면 반환, 없으면 기본 파라미터로 실시간 계산.

**Response:**
```json
{
  "id": "0d7259ac-ad36-4122-bf5e-fd74488868f8",
  "cpet_test_id": "c91339b9-c0ce-434d-b4ad-3c77452ed928",
  "config": {
    "bin_size": 10,
    "aggregation_method": "median",
    "loess_frac": 0.25,
    "smoothing_method": "loess",
    "exclude_rest": true,
    "exclude_warmup": true,
    "exclude_recovery": true,
    "min_power_threshold": 60,
    "trim_start_sec": 30,
    "trim_end_sec": 1400,
    "fatmax_zone_threshold": 0.90
  },
  "is_manual_override": true,
  "processed_series": {
    "raw": [...],      // 437개
    "binned": [...],   // 18개
    "smoothed": [...], // 18개
    "trend": [...]     // 18개
  },
  "metabolic_markers": {
    "fat_max": {
      "power": 170,
      "mfo": 1.1469,
      "zone_min": 150,
      "zone_max": 190
    },
    "crossover": {
      "power": 184,
      "fat_value": 0.95,
      "cho_value": 0.95
    }
  },
  "stats": {
    "total_data_points": 500,
    "exercise_data_points": 437,
    "binned_data_points": 18
  },
  "trim_range": {
    "start_sec": 30,
    "end_sec": 1400,
    "auto_detected": false
  },
  "processing_warnings": [],
  "processing_status": "completed",
  "processed_at": "2024-01-20T10:30:00Z",
  "is_persisted": true,
  "created_at": "2024-01-20T10:30:00Z",
  "updated_at": "2024-01-20T10:30:00Z"
}
```

### POST `/api/tests/{test_id}/processed-metabolism`

설정을 저장하고 전처리 데이터를 계산하여 DB에 저장 (Upsert).

**Request Body:**
```json
{
  "config": {
    "bin_size": 10,
    "aggregation_method": "median",
    "loess_frac": 0.25,
    "smoothing_method": "loess",
    "exclude_rest": true,
    "exclude_warmup": true,
    "exclude_recovery": true,
    "min_power_threshold": 60,
    "trim_start_sec": 30,
    "trim_end_sec": 1400,
    "fatmax_zone_threshold": 0.90
  },
  "is_manual_override": true
}
```

**권한:** Researcher 이상

### DELETE `/api/tests/{test_id}/processed-metabolism`

저장된 설정 삭제. 이후 GET 요청 시 기본값으로 계산됨.

**권한:** Researcher 이상

## 프론트엔드 상태 관리

### 상태 변수

```typescript
// 서버에 저장된 설정 (비교 기준)
const [serverConfig, setServerConfig] = useState<ServerConfig | null>(null);

// 서버에 데이터가 저장되어 있는지 여부
const [isServerPersisted, setIsServerPersisted] = useState(false);

// 로컬 설정이 서버와 다른지 (저장 필요 여부)
const isDirty = useMemo(() => {
  if (!persistenceLoaded) return false;
  if (!isServerPersisted) return true;  // 저장된 적 없으면 항상 dirty
  // serverConfig와 로컬 설정 비교
  return /* 비교 로직 */;
}, [serverConfig, analysisSettings, trimRange, persistenceLoaded, isServerPersisted]);
```

### UI 상태 배지

| 상태 | 배지 | 설명 |
|------|------|------|
| `isDirty && !isServerPersisted` | 🟡 저장 안됨 | 처음 저장하거나 변경사항 있음 |
| `!isDirty && isServerPersisted` | 🟢 저장됨 | 서버와 동기화됨 |
| `!isDirty && !isServerPersisted` | ⚪ 기본값 | 기본 설정 사용 중 |

## 데이터 처리 파이프라인

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         데이터 처리 파이프라인                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  breath_data (원본)                                                     │
│       │                                                                 │
│       ▼                                                                 │
│  ┌─────────────────────────────────────────┐                           │
│  │ 1. 필터링 (Filtering)                    │                           │
│  │    - Time trim: 30s ~ 1400s             │                           │
│  │    - Min power: >= 60W                  │                           │
│  │    - Exclude: rest, warmup, recovery    │                           │
│  └─────────────────────────────────────────┘                           │
│       │                                                                 │
│       ▼                                                                 │
│  raw_series (437개)                                                     │
│       │                                                                 │
│       ▼                                                                 │
│  ┌─────────────────────────────────────────┐                           │
│  │ 2. Power Binning (1차 전처리)            │                           │
│  │    - 10W 단위 그룹화                     │                           │
│  │    - Median 집계                        │                           │
│  └─────────────────────────────────────────┘                           │
│       │                                                                 │
│       ▼                                                                 │
│  binned_series (18개)                                                   │
│       │                                                                 │
│       ├───────────────────────────────────┐                            │
│       ▼                                   ▼                            │
│  ┌─────────────────────┐    ┌─────────────────────┐                    │
│  │ 3a. LOESS 스무딩     │    │ 3b. Polynomial Fit  │                    │
│  │     (frac=0.25)     │    │     (2차 다항식)     │                    │
│  └─────────────────────┘    └─────────────────────┘                    │
│       │                                   │                            │
│       ▼                                   ▼                            │
│  smoothed_series (18개)              trend_series (18개)                │
│       │                                   │                            │
│       └───────────────┬───────────────────┘                            │
│                       ▼                                                │
│              ┌─────────────────┐                                       │
│              │ 4. 마커 계산     │                                       │
│              │    - FatMax     │                                       │
│              │    - Crossover  │                                       │
│              └─────────────────┘                                       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 파일 구조

```
backend/
├── app/
│   ├── api/
│   │   └── processed_metabolism.py    # API 엔드포인트
│   ├── models/
│   │   └── processed_metabolism.py    # SQLAlchemy 모델
│   ├── schemas/
│   │   └── processed_metabolism.py    # Pydantic 스키마
│   └── services/
│       └── processed_metabolism.py    # 비즈니스 로직

frontend/
├── src/
│   ├── lib/
│   │   └── api.ts                     # API 클라이언트 메서드
│   ├── types/
│   │   └── metabolism.ts              # TypeScript 타입 정의
│   └── components/pages/
│       ├── RawDataViewerPage.tsx      # 저장/리셋 UI
│       └── MetabolismPage.tsx         # 저장/리셋 UI
```

## 검증 규칙

| 파라미터 | 범위 | 기본값 |
|---------|------|--------|
| bin_size | 5 - 30 W | 10 |
| loess_frac | 0.1 - 0.5 | 0.25 |
| min_power_threshold | 0 - 200 W | null |
| trim range | end > start, 최소 180초 | auto-detect |
| fatmax_zone_threshold | 0.5 - 1.0 | 0.90 |

## 사용 예시

### cURL로 테스트

```bash
# 1. GET - 저장된 데이터 또는 기본값 조회
curl -X GET "http://localhost:8100/api/tests/{test_id}/processed-metabolism" \
  -H "Authorization: Bearer {token}"

# 2. POST - 설정 저장
curl -X POST "http://localhost:8100/api/tests/{test_id}/processed-metabolism" \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "loess_frac": 0.25,
      "bin_size": 10,
      "min_power_threshold": 60,
      "trim_start_sec": 30,
      "trim_end_sec": 1400
    },
    "is_manual_override": true
  }'

# 3. DELETE - 저장된 설정 삭제 (기본값으로 복원)
curl -X DELETE "http://localhost:8100/api/tests/{test_id}/processed-metabolism" \
  -H "Authorization: Bearer {token}"
```

### DB 직접 조회

```sql
-- 저장된 설정 확인
SELECT
  cpet_test_id,
  bin_size, loess_frac, min_power_threshold,
  trim_start_sec, trim_end_sec,
  fatmax_power, fatmax_mfo, crossover_power,
  processing_status, is_manual_override
FROM processed_metabolism;

-- 시리즈 데이터 개수 확인
SELECT
  jsonb_array_length(raw_series) as raw_count,
  jsonb_array_length(binned_series) as binned_count,
  jsonb_array_length(smoothed_series) as smoothed_count,
  jsonb_array_length(trend_series) as trend_count
FROM processed_metabolism
WHERE cpet_test_id = '{test_id}';
```
