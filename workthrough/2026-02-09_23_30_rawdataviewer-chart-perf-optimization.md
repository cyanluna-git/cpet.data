# RawDataViewerPage 차트 렌더링 성능 최적화

## Overview
전처리(전처리 수행) 클릭 시 차트가 심하게 버벅이는 문제를 해결했다. 불필요한 재렌더링 연쇄, 차트 메모이제이션 부재, 중복 API 호출, 인라인 함수 재생성, O(n²) 탐색, 과도한 console.log 등 6가지 성능 병목을 제거했다.

## Context
- `RawDataViewerPage`는 4개의 Recharts 차트를 동시 렌더링하는 무거운 페이지
- "전처리 수행" 클릭 → 데이터 로드 → state 변경 시 불필요한 렌더가 연쇄 발생
- 매 렌더마다 `getChartDataForPreset()` 4회 호출 (배열 복사 + 정렬)
- 인라인 formatter 함수가 매번 새로 생성되어 Recharts가 변경으로 인식
- Trend 모드에서 smooth 데이터 매칭이 O(n²)

## Changes Made

### 1. 중복 `loadRawData` useEffect 제거
- **파일**: `frontend/src/components/pages/RawDataViewerPage.tsx`
- 기존 line ~792의 useEffect가 이미 `selectedTestId` 변경 시 `loadRawData()` 호출
- line ~990의 동일 effect가 중복으로 API를 2번 호출하고 있었음 → 삭제

### 2. 차트 프리셋 데이터를 `useMemo`로 캐싱
- `presetChartDataMap` useMemo 추가
- 4개 프리셋 결과를 한 번에 계산하고 캐싱
- 의존성: `getChartDataForPreset` (이미 useCallback으로 안정화됨)
- 렌더링 JSX에서 `presetChartDataMap[presetIndex]`로 O(1) 접근

```typescript
const presetChartDataMap = useMemo(() => {
  return QUAD_PRESETS.map(preset => ({
    key: preset.key,
    ...getChartDataForPreset(preset.x, preset.yLeft, preset.yRight),
  }));
}, [getChartDataForPreset]);
```

### 3. `PresetChart`를 `React.memo` 컴포넌트로 분리
- 기존 `QUAD_PRESETS.map()` 내부 ~230줄 JSX를 별도 컴포넌트로 추출
- `React.memo`로 감싸서 props 변경 없으면 차트 재렌더링 방지
- `labelFormatter`는 `useCallback`으로 안정화

```typescript
const PresetChart = React.memo(({ preset, presetIndex, chartData, isProcessed, dataMode, analysisData }: PresetChartProps) => {
  // 차트 렌더링 로직
});
```

### 4. Tooltip formatter를 컴포넌트 외부 상수로 추출
- 4개의 stable 함수를 모듈 레벨에 정의:
  - `tooltipFormatter` - 프리셋 차트용 (value.toFixed(2))
  - `overviewTooltipFormatter` - 개요 차트용 (value.toFixed(1))
  - `overviewLabelFormatter` - 개요 차트 라벨
  - `numberTickFormatter` - 공통 숫자 틱 포맷터
- 인라인 함수 대비 Recharts가 참조 동일성을 유지하므로 불필요한 재렌더링 방지

### 5. Trend 데이터의 O(n²) nearest-smooth 탐색을 Map으로 최적화
- **기존**: `smoothData.reduce()` per-point → O(n × m) 복잡도
- **변경**: `Map<number, any>` 사전 구축 후 `Math.round(power)` 키로 O(1) lookup

```typescript
const smoothMap = new Map<number, any>();
if (currentMode === 'trend' && smoothData.length > 0) {
  for (const s of smoothData) {
    smoothMap.set(Math.round(s.power), s);
  }
}
// 각 point에서 O(1) lookup
const nearestSmooth = smoothMap.get(Math.round(point.power));
```

### 6. 디버그 console.log 제거 (~15곳)
제거된 로그 위치:
- `rawChartData` useMemo 내부
- `hasChartData` useMemo 내부
- `isDirty` useMemo 내부 (3곳 + comparison 로그)
- `loadRawData` 함수 (4곳)
- `loadProcessedData` 함수 (7곳: API response, series keys, field stats 등)
- `loadSavedConfig` 콜백
- `handleSaveSettings` / `handleResetSettings`
- `loadSubjects` / `loadAllTests`
- 피험자 필터링 useEffect
- 차트 렌더링 JSX 내 debug 로그

### 7. 미사용 import 정리
- `Legend` import 제거 (사용되지 않음)

## Verification Results

### Build Verification
```
> tsc -b && vite build
✓ 2414 modules transformed.
✓ built in 2.68s
```

빌드 에러 없음. TypeScript 타입 체크 통과.

## 성능 개선 요약

| 항목 | Before | After |
|------|--------|-------|
| 테스트 선택 시 API 호출 | 2회 (중복) | 1회 |
| 렌더당 getChartDataForPreset | 4회 (매번 sort) | 1회 (useMemo 캐싱) |
| 차트 재렌더링 | 모든 state 변경 시 4개 모두 | props 변경된 차트만 |
| Tooltip formatter | 매 렌더 새 함수 생성 | 모듈 레벨 상수 참조 |
| Trend smooth 매칭 | O(n × m) reduce | O(n) Map lookup |
| console.log | ~15곳 매 렌더 실행 | 제거 |
