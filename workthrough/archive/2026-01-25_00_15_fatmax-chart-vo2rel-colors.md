# FATMAX 차트 색상 변경 및 VO2/kg 추가

## 개요
FATMAX 차트의 색상을 교수님 차트와 동일하게 변경하고, RER 대신 VO2/kg(vo2_rel)을 우측 Y축에 표시하도록 수정.

## 주요 변경사항

### 1. FATMAX 차트 색상 변경 (RawDataViewerPage.tsx)
- **Fat (지방 산화)**: 빨간색 (#DC2626)
- **CHO (탄수화물 산화)**: 녹색 (#16A34A)
- **VO2/kg**: 파란색 (#2563EB) - 우측 Y축

### 2. VO2/kg 데이터 파이프라인 추가 (metabolism_analysis.py)
- `ProcessedDataPoint` 클래스에 `vo2_rel` 필드 추가
- `_to_processed_points()`: vo2_rel 계산 추가
- `_power_binning()`: vo2_rel 평균 계산 추가
- `_loess_smoothing()`: vo2_rel 스무딩 추가
- `_polynomial_fit()`: vo2_rel 트렌드 피팅 추가

### 3. 프론트엔드 데이터 매핑 (RawDataViewerPage.tsx)
- `DATA_KEY_COLORS` 상수로 일관된 색상 관리
- FATMAX 프리셋 yRight를 `['rer']`에서 `['vo2_rel']`로 변경
- Raw/Smoothed/Trend 모드 모두 vo2_rel 지원

## 핵심 코드

```typescript
// 색상 매핑
const DATA_KEY_COLORS: Record<string, string> = {
  fat_oxidation: '#DC2626', // red
  cho_oxidation: '#16A34A', // green
  vo2_rel: '#2563EB',       // blue
};
```

```python
# ProcessedDataPoint에 vo2_rel 추가
@dataclass
class ProcessedDataPoint:
    power: float
    fat_oxidation: Optional[float]
    cho_oxidation: Optional[float]
    vo2_rel: Optional[float] = None  # 추가됨
```

## 결과
- ✅ Raw 모드: VO2/kg 정상 표시
- ✅ 색상 변경 완료 (Fat=빨강, CHO=녹색, VO2/kg=파랑)
- ⚠️ Trend/Smoothed 모드: 기존 데이터 재분석 필요

## 다음 단계
- 기존 ProcessedMetabolism 데이터 재분석하여 vo2_rel 포함시키기
- Metabolism 페이지에서 "재분석" 버튼 클릭으로 해결 가능
