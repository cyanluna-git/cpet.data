# FATMAX 차트 VO2/kg 전처리 데이터 누락 수정

## 개요
FATMAX 차트에서 Smoothed/Trend 모드 선택 시 VO2/kg가 표시되지 않던 버그를 수정했다. 원인은 Pydantic 스키마에 `vo2_rel` 필드가 누락되어 API 응답에서 해당 값이 직렬화되지 않았던 것이다.

## 주요 변경사항
- **수정한 것**: `backend/app/schemas/test.py`의 `ProcessedDataPoint` 클래스에 `vo2_rel` 필드 추가

## 핵심 코드
```python
# backend/app/schemas/test.py - ProcessedDataPoint 클래스
vo2: Optional[float] = None  # VO2 for VO2 Kinetics chart
vo2_rel: Optional[float] = None  # VO2/kg for FATMAX chart  # ← 추가
vco2: Optional[float] = None  # VCO2 for VO2 Kinetics chart
```

## 데이터 흐름 (수정 후)
```
BreathData (vo2_rel ✅)
    ↓
ProcessedDataPoint dataclass (vo2_rel ✅)
    ↓
ProcessedDataPoint Pydantic schema (vo2_rel ✅) ← 수정됨
    ↓
Frontend (vo2_rel 표시됨)
```

## 결과
- ✅ Pydantic 스키마 수정 완료
- ✅ Smoothed/Trend 모드에서 VO2/kg 표시 가능

## 다음 단계
- 백엔드 서버 재시작 후 프론트엔드에서 검증 필요
- 기존 테스트 데이터로 Smoothed/Trend 모드 확인
