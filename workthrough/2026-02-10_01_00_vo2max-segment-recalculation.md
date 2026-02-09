# VO2max 세그먼트 데이터 기반 재계산 구현

## Overview

HYBRID CPET 프로토콜(Ramp 1: FATMAX + Ramp 2: VO2max)에서 사용자가 VO2max 세그먼트 윈도우를 지정했을 때, 해당 시간 범위 내의 breath_data만 필터링하여 VO2max 메트릭을 재계산하도록 구현했다.

### 문제
이전 v1.2.0에서 `vo2max_start_sec`/`vo2max_end_sec` 듀얼 세그먼트 윈도우를 추가했으나, `_find_vo2max_info()`가 **전체** breath_data에서 max VO2를 찾아 FATMAX ramp 구간의 데이터가 혼입되는 문제가 있었다.

### 해결
세그먼트 윈도우가 지정되면 해당 시간 범위로 breath_data를 필터링한 후 VO2max를 계산하고, 결과에 `vo2max_segment_applied: true` 플래그를 포함한다. 빈 세그먼트인 경우 전체 데이터로 fallback.

## Changes Made

### 1. Backend: `_find_vo2max_info()` 세그먼트 필터링
- File: `backend/app/services/test.py`

```python
# 시그니처에 세그먼트 파라미터 추가
def _find_vo2max_info(
    self,
    breath_data: List[BreathData],
    test: CPETTest,
    vo2max_start_sec: Optional[float] = None,
    vo2max_end_sec: Optional[float] = None,
) -> Dict[str, Any]:
    segment_applied = False
    data = breath_data

    # Filter by VO2max segment window if provided
    if vo2max_start_sec is not None and vo2max_end_sec is not None:
        filtered = [
            bd for bd in breath_data
            if bd.t_sec is not None
            and bd.t_sec >= vo2max_start_sec
            and bd.t_sec <= vo2max_end_sec
        ]
        if filtered:
            data = filtered
            segment_applied = True

    # ... max VO2 계산 (data 사용)
    return {
        ...,
        "vo2max_segment_applied": segment_applied,
    }
```

### 2. Backend: `get_analysis()` 호출부 수정
- File: `backend/app/services/test.py`

```python
# 기존: vo2max_info = self._find_vo2max_info(breath_data, test)
# 변경:
vo2max_info = self._find_vo2max_info(
    breath_data, test,
    vo2max_start_sec=vo2max_start_sec,
    vo2max_end_sec=vo2max_end_sec,
)
```

### 3. Backend: ProcessedMetabolism 모델 — VO2max 결과 컬럼 추가
- File: `backend/app/models/processed_metabolism.py`

```python
# v1.2.0: VO2max segment analysis results
vo2max_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)       # mL/min
vo2max_rel: Mapped[Optional[float]] = mapped_column(Float, nullable=True)         # mL/kg/min
vo2max_hr_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)      # bpm
vo2max_time_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)    # seconds
```

`to_dict()`에 `vo2max_metrics` 섹션 추가:

```python
"vo2max_metrics": {
    "vo2_max": self.vo2max_value,
    "vo2_max_rel": self.vo2max_rel,
    "hr_max": self.vo2max_hr_max,
    "time_sec": self.vo2max_time_sec,
},
```

### 4. Backend: ProcessedMetabolismService `save()` — VO2max 결과 저장
- File: `backend/app/services/processed_metabolism.py`

`save()` 메서드에서 vo2max 세그먼트 윈도우가 지정된 경우 breath_data를 필터링하여 VO2max 결과를 DB에 영속화. 미지정 시 결과 컬럼을 NULL로 초기화.

### 5. Migration: VO2max 결과 컬럼 추가
- File: `backend/migrations/add_vo2max_segment_fields.sql`

```sql
ALTER TABLE processed_metabolism ADD COLUMN IF NOT EXISTS vo2max_value FLOAT;
ALTER TABLE processed_metabolism ADD COLUMN IF NOT EXISTS vo2max_rel FLOAT;
ALTER TABLE processed_metabolism ADD COLUMN IF NOT EXISTS vo2max_hr_max INTEGER;
ALTER TABLE processed_metabolism ADD COLUMN IF NOT EXISTS vo2max_time_sec FLOAT;
```

### 6. Frontend: VO2max 세그먼트 결과 카드
- File: `frontend/src/components/pages/RawDataViewerPage.tsx`

VO2max 세그먼트 슬라이더 하단에 `vo2max_segment_applied: true`일 때만 표시되는 결과 요약 카드 추가 (VO2max, VO2max rel, HR max).

```tsx
{vo2maxRange && analysisData?.vo2max?.vo2max_segment_applied && (
  <div className="mt-2 p-3 bg-orange-50 border border-orange-200 rounded-lg">
    <h4 className="text-sm font-medium text-orange-800 mb-2">VO2max 세그먼트 결과</h4>
    <div className="grid grid-cols-3 gap-2 text-xs">
      <div>
        <span className="text-gray-500">VO2max</span>
        <p className="font-semibold">{analysisData.vo2max.vo2_max?.toFixed(0)} mL/min</p>
      </div>
      ...
    </div>
  </div>
)}
```

## Verification Results

### Backend Tests
```
115 passed, 672 warnings in 10.39s
```

### Frontend Build
```
✓ built in 2.46s
```

### DB Migration
```
ALTER TABLE ×6, COMMENT ×6 — 모두 성공
```

### 컬럼 확인
```
 vo2max_start_sec | double precision
 vo2max_end_sec   | double precision
 vo2max_value     | double precision
 vo2max_rel       | double precision
 vo2max_hr_max    | integer
 vo2max_time_sec  | double precision
```

## Next Steps

- E2E 테스트: HYBRID 프로토콜 실 데이터로 세그먼트 지정/미지정 시 VO2max 값 차이 검증
- VO2max 세그먼트 결과 카드에 VCO2max, RER at max 등 추가 메트릭 표시 고려
- CohortAnalysis에서 VO2max 세그먼트 결과 활용 (그룹 비교)
