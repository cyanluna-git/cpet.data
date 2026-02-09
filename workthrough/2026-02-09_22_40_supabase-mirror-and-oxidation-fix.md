# Supabase -> Local DB 미러링 완료 & MIX 포맷 Oxidation 계산 수정

## 개요
Supabase 프로덕션 DB에서 로컬 개발 DB로 전체 데이터 미러링을 완료하고, MIX 포맷 데이터에서 fat/CHO oxidation이 NULL인 문제를 Frayn 공식 자동 계산으로 해결했다.

## 컨텍스트
- 로컬 개발 환경에 Supabase 데이터를 동기화하는 작업이 중단된 상태였음
- `mirror_via_api.py` 스크립트 실행 시 date/time 타입 변환, NaN 문자열, 중복 키 등의 에러로 일부 데이터 누락
- MIX 포맷(INTERVAL 프로토콜)으로 업로드된 6개 테스트에서 fat_oxidation/cho_oxidation이 모두 NULL → 전처리(processed-metabolism) 시 422 에러 발생

## 변경 사항

### 1. 미러링 스크립트 개선 (`scripts/mirror_via_api.py`)

**date 타입 변환 추가**
```python
# date 문자열 → date 객체 변환 (birth_date 등)
elif isinstance(val, str) and col_type == "date":
    val = date.fromisoformat(val[:10])
```

**time 타입 변환 추가**
```python
# time 문자열 → time 객체 변환 (test_time, test_duration 등)
elif isinstance(val, str) and col_type == "time without time zone":
    parts = val.split(":")
    val = time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
```

**NaN/Infinity 문자열 처리**
```python
# breath_data의 rer 등 숫자 컬럼에서 'NaN' 문자열 → None
if val == "NaN" or val == "Infinity" or val == "-Infinity":
    val = None
```

**중복 키 처리**
```python
# Supabase 원본 데이터의 중복 PK 행 무시
query = f'INSERT INTO {table} ({column_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
```

### 2. MIX 포맷 Oxidation 자동 계산 (`backend/app/services/metabolism_analysis.py`)

`_fill_missing_oxidation()` 메서드를 `MetabolismAnalyzer` 클래스에 추가:

```python
def _fill_missing_oxidation(self, breath_data: List[Any]) -> List[Any]:
    """VO2/VCO2에서 Frayn 공식으로 fat/cho oxidation 보정."""
    for bd in breath_data:
        if bd.fat_oxidation is not None and bd.cho_oxidation is not None:
            continue
        vo2_l = bd.vo2 / 1000.0   # mL/min → L/min
        vco2_l = bd.vco2 / 1000.0
        bd.fat_oxidation = max(0.0, 1.67 * vo2_l - 1.67 * vco2_l)  # Frayn (1983)
        bd.cho_oxidation = max(0.0, 4.55 * vco2_l - 3.21 * vo2_l)
    return breath_data
```

`analyze()` 메서드에서 phase trimming 전에 호출:
```python
breath_data = self._fill_missing_oxidation(breath_data)
filtered_data = self._apply_phase_trimming(breath_data)
```

## 검증 결과

### 미러링 결과
| 테이블 | Supabase | 로컬 DB | 상태 |
|--------|----------|---------|------|
| subjects | 18 | 18 | OK |
| users | 15 | 15 | OK |
| cpet_tests | 83 | 83 | OK |
| breath_data | 52,782 | 52,782 | OK |
| processed_metabolism | 60 | 60 | OK |
| cohort_stats | 0 | 0 | OK |

### 전처리 API 테스트
- 기존: `POST /tests/{id}/processed-metabolism` → 422 "Analysis failed - insufficient data"
- 수정 후: 정상 동작 (Frayn 공식으로 oxidation 자동 계산 후 분석 수행)

## 향후 개선
- RawDataViewerPage 차트 렌더링 성능 최적화 필요 (별도 workthrough 참조)
- MIX 포맷 업로드 시 파서 단계에서 oxidation을 미리 계산하도록 개선 검토
