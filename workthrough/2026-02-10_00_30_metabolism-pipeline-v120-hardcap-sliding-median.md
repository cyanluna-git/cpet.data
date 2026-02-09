# Metabolism 전처리 파이프라인 v1.2.0: Hard-cap + Sliding Window Median

## Overview

엘리트 선수(Youngsu Byeon) 데이터에서 FATMAX 차트가 정상적인 2차 포물선이 아닌 4차식처럼 왜곡되는 문제를 해결했다. Raw fat_oxidation이 최대 12 g/min(정상: 0~1.5, 엘리트: ~2.0)까지 튀는 breath-by-breath 노이즈가 기존 IQR 기반 outlier 제거만으로는 불충분하여, 생리학적 hard-cap과 sliding window median 필터 2단계를 추가했다.

## Context

- **문제**: Breath-by-breath 측정 시 극단적 노이즈(fat_oxidation 12 g/min 등)가 IQR 범위 내에서 제거되지 않음
- **영향**: 노이즈 → binning → LOESS → polynomial 전파 → 차트가 4차식 형태로 왜곡
- **해결**: 파이프라인에 2개 전처리 단계 추가
  1. Physiological hard-cap: 생리학적으로 불가능한 값(fat > 2.0, CHO > 8.0 g/min)을 None으로 무효화
  2. Sliding window median: IQR 후 남은 개별 spike를 주변 값의 중앙값으로 평활화

## 변경된 파이프라인

```
Raw BreathData → [0] Trim → [1] Fill Missing → [2] Phase Trim
→ [3] Extract Raw Points
→ [3.5] Physiological Hard-Cap (NEW v1.2.0)
→ [4] IQR Outlier
→ [4.5] Sliding Window Median (NEW v1.2.0)
→ [5] Power Binning → [6] LOESS → [7] Polynomial → [8] FatMax → [9] Crossover
```

## Changes Made

### 1. AnalysisConfig 설정 추가

파일: `backend/app/services/metabolism_analysis.py`

5개의 새 설정 필드를 `AnalysisConfig` dataclass에 추가하고, `to_dict()` 메서드도 업데이트했다.

```python
# v1.2.0: Physiological hard-cap
physiological_cap_enabled: bool = True
fat_oxidation_cap: float = 2.0        # g/min (엘리트 선수 상한)
cho_oxidation_cap: float = 8.0        # g/min
# v1.2.0: Sliding window median filter
sliding_median_enabled: bool = True
sliding_median_window: int = 5         # breath 수 (홀수)
```

### 2. `_apply_physiological_cap()` 메서드 구현

파일: `backend/app/services/metabolism_analysis.py`

- fat_oxidation > cap 또는 cho_oxidation > cap인 값을 **None으로 무효화** (제거가 아닌 무효화)
- 경고 로그 출력 (몇 개 capped 되었는지)
- 삽입 위치: Extract Raw Points 직후, IQR Outlier 전

### 3. `_apply_sliding_median()` 메서드 구현

파일: `backend/app/services/metabolism_analysis.py`

- Power 기준 정렬 후 윈도우 내 median으로 fat/cho oxidation 대체
- `np.median` 사용, None 값 안전 처리
- 데이터가 윈도우 크기 미만이면 스킵
- 삽입 위치: IQR Outlier 직후, Power Binning 전

### 4. `analyze()` 파이프라인 업데이트

파일: `backend/app/services/metabolism_analysis.py`

```python
# 1.3. 생리학적 hard-cap 적용 (IQR 전에 극단값 무효화)
if self.config.physiological_cap_enabled:
    raw_points = self._apply_physiological_cap(raw_points)

# 1.5. IQR 기반 이상치 제거
raw_points_clean = self._detect_and_remove_outliers(raw_points)

# 1.7. Sliding window median 필터 (IQR 후, binning 전)
if self.config.sliding_median_enabled:
    raw_points_clean = self._apply_sliding_median(raw_points_clean)
```

### 5. 테스트 추가

파일: `backend/tests/test_metabolism_improvements.py`

| 테스트 클래스 | 테스트 수 | 내용 |
|---|---|---|
| `TestPhysiologicalCap` | 5 | fat/CHO capping, 경고 생성, disabled 모드, 파이프라인 통합 |
| `TestSlidingMedian` | 5 | spike 평활화, power 정렬, None 처리, 소량 데이터 스킵, disabled 모드 |
| `TestV120Integration` | 4 | 두 기능 동시 동작, config 직렬화, 기본값, 전체 파이프라인 |

## Verification Results

### 새 테스트
```
tests/test_metabolism_improvements.py - 45 passed in 1.66s
```

### 전체 테스트 (회귀 없음)
```
115 passed, 0 failed in 11.67s
```

## 향후 개선 사항

- 프론트엔드에서 Youngsu Byeon 데이터의 Smooth/Trend 모드 차트가 정상 포물선 형태인지 실제 확인 필요
- `fat_oxidation_cap`, `cho_oxidation_cap` 값을 프론트엔드 설정 UI에서 조정 가능하게 할 수 있음
- `sliding_median_window` 크기도 사용자 설정으로 노출 가능
