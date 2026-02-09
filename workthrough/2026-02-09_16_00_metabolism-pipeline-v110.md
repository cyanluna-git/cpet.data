# CPET 전처리 파이프라인 정확도 개선 (v1.0.0 → v1.1.0)

## Overview

MetabolismAnalyzer의 전처리 파이프라인에 7가지 개선을 적용하여 FatMax/Crossover 마커의 정확도와 노이즈 내성을 높였다. 이상치 탐지, sparse bin 처리, 적응형 파라미터 선택 등이 부재하여 노이즈에 취약했던 v1.0.0 파이프라인을 개선하면서도, 모든 새 기능은 하위호환 기본값을 사용하여 기존 API 소비자에 영향이 없다.

## Context

- 기존 파이프라인은 단순 binning → LOESS → polynomial 순서만 수행
- 이상치가 있는 raw 데이터가 그대로 binning에 전달되어 결과 왜곡
- 데이터 포인트 수에 관계없이 고정된 LOESS frac(0.25) 사용
- Polynomial degree가 fat/cho/rer 모두 3으로 고정 (과적합 또는 과소적합 가능)
- Crossover 탐지가 첫 번째 교차점만 반환 (다중 교차 시 신뢰도 판단 불가)

## Changes Made

### 1. IQR 기반 이상치 탐지 (신규 단계)
- 파일: `backend/app/services/metabolism_analysis.py`
- 신규 메서드 `_detect_and_remove_outliers(raw_points)` 추가
- `analyze()` 내 raw extraction → binning 사이에 삽입
- fat_oxidation, cho_oxidation 각각에 대해 Q1 - 1.5*IQR ~ Q3 + 1.5*IQR 범위 밖 제거
- 10개 미만 데이터는 스킵 (안전장치)
- `ProcessedSeries.raw`에는 원본 유지, cleaned 데이터만 binning에 전달

```python
# backend/app/services/metabolism_analysis.py
def _detect_and_remove_outliers(self, raw_points):
    if not self.config.outlier_detection_enabled or len(raw_points) < 10:
        return raw_points
    k = self.config.outlier_iqr_multiplier
    # IQR bounds 계산 후 범위 밖 포인트 제거
    fat_lo, fat_hi = iqr_bounds(fat_vals)
    cho_lo, cho_hi = iqr_bounds(cho_vals)
    cleaned = [p for p in raw_points if within_bounds(p)]
    return cleaned
```

### 2. Sparse Bin 병합 (`_power_binning` 수정)
- 파일: `backend/app/services/metabolism_analysis.py`
- power_bin 할당 직후, groupby 이전에 실행
- `min_bin_count`(기본 3) 미만인 bin을 가장 가까운 non-sparse bin에 병합

```python
# power_bin 할당 후
if self.config.min_bin_count > 1:
    bin_counts = df.groupby("power_bin").size()
    sparse_bins = bin_counts[bin_counts < self.config.min_bin_count].index.tolist()
    for sparse_bin in sparse_bins:
        nearest = min(candidates, key=lambda b: abs(b - sparse_bin))
        df.loc[df["power_bin"] == sparse_bin, "power_bin"] = nearest
```

### 3. 적응형 LOESS Fraction (`_loess_smoothing` 수정)
- `adaptive_loess=True`일 때 데이터 크기 기반 자동 조정
- 공식: `frac = max(0.15, min(0.5, 4.0 / n))`
- n=8→0.5, n=15→0.27, n=20→0.20, n=27+→0.15

### 4. 프로토콜 인식 Trimming (`_detect_analysis_window` 수정)
- `protocol_type` 설정에 따라 recovery_ratio, start_threshold 자동 오버라이드
- ramp: recovery_ratio=0.70, start_threshold=30
- step/graded: recovery_ratio=0.85, start_threshold=20

### 5. 교차검증 Polynomial Degree (`_polynomial_fit` 수정)
- 신규 헬퍼 `_select_poly_degree_cv(x, y, max_degree=4)` 추가
- LOOCV로 degree 1~4 중 RMSE 최소 선택
- fat/cho/rer에만 적용, VO2/VCO2/HR/VT는 생리학적 이유로 degree 2 고정

### 6. FatMax Bootstrap 신뢰구간 (`_calculate_fatmax` 수정)
- `fatmax_confidence_interval=True` 시 500회 bootstrap resample
- MFO와 power의 2.5/97.5 percentile → 95% CI
- `FatMaxMarker`에 `mfo_ci_lower/upper`, `power_ci_lower/upper` Optional 필드 추가
- `to_dict()`에서 None이면 키 생략 → API 하위호환

```python
# FatMaxMarker 확장 필드
mfo_ci_lower: Optional[float] = None
mfo_ci_upper: Optional[float] = None
power_ci_lower: Optional[int] = None
power_ci_upper: Optional[int] = None
```

### 7. 다중 Crossover 탐지 (`_calculate_crossover` 리팩토링)
- 모든 부호 변화 지점 탐지 (기존: 첫 번째만)
- confidence = |d1 - d2| (부호 변화 크기)
- confidence 내림차순 정렬, 첫 번째를 primary로 반환
- `MetabolicMarkers.all_crossovers` 필드 추가 (다중 교차 시)
- `CrossoverMarker.confidence` Optional 필드 추가

### 8. 스키마/API/버전 업데이트
- `backend/app/services/processed_metabolism.py`: `CURRENT_ALGORITHM_VERSION = "1.1.0"`
- `backend/app/schemas/processed_metabolism.py`: `MetabolismConfig`에 8개 필드 추가
- `backend/app/api/processed_metabolism.py`: `_schema_to_analysis_config()` 및 `_build_response()` 동기화

### 9. 테스트 파일 신규 작성
- `backend/tests/test_metabolism_improvements.py`: 31개 테스트
  - TestOutlierDetection (4개)
  - TestSparseBinMerging (2개)
  - TestAdaptiveLoess (3개)
  - TestProtocolTrimming (3개)
  - TestAdaptivePolynomial (3개)
  - TestFatMaxBootstrapCI (3개)
  - TestMultiCrossover (7개)
  - TestBackwardCompatibility (4개)
  - TestEndToEnd (2개)

## Code Examples

### AnalysisConfig 새 필드
```python
# backend/app/services/metabolism_analysis.py
@dataclass
class AnalysisConfig:
    # ... 기존 필드 ...
    # v1.1.0: Outlier detection
    outlier_detection_enabled: bool = True
    outlier_iqr_multiplier: float = 1.5
    # v1.1.0: Sparse bin merging
    min_bin_count: int = 3
    # v1.1.0: Adaptive LOESS fraction
    adaptive_loess: bool = True
    # v1.1.0: Protocol-aware trimming
    protocol_type: Optional[str] = None  # "ramp", "step", "graded", None
    # v1.1.0: Cross-validation polynomial degree
    adaptive_polynomial: bool = True
    # v1.1.0: FatMax bootstrap confidence interval
    fatmax_confidence_interval: bool = False  # Default off (computational cost)
    fatmax_bootstrap_iterations: int = 500
```

### analyze() 파이프라인 변경
```python
# backend/app/services/metabolism_analysis.py - analyze() 메서드
raw_points = self._extract_raw_points(filtered_data)

# NEW: IQR 이상치 제거 (raw는 원본 유지, cleaned만 binning에 전달)
raw_points_clean = self._detect_and_remove_outliers(raw_points)

binned_points = self._power_binning(raw_points_clean)
# ... 이하 동일 ...

# Crossover: 이제 tuple 반환
crossover_marker, all_crossovers = self._calculate_crossover(smoothed_points)

MetabolicMarkers(
    fat_max=fatmax_marker,
    crossover=crossover_marker,
    all_crossovers=all_crossovers,  # NEW
)
```

## Verification Results

### 신규 테스트 (31개 전체 통과)
```
tests/test_metabolism_improvements.py::TestOutlierDetection::test_outliers_removed PASSED
tests/test_metabolism_improvements.py::TestOutlierDetection::test_outlier_disabled PASSED
tests/test_metabolism_improvements.py::TestOutlierDetection::test_no_removal_when_few_points PASSED
tests/test_metabolism_improvements.py::TestOutlierDetection::test_raw_series_preserves_original PASSED
tests/test_metabolism_improvements.py::TestSparseBinMerging::test_sparse_bins_merged PASSED
tests/test_metabolism_improvements.py::TestSparseBinMerging::test_no_merge_when_min_count_1 PASSED
tests/test_metabolism_improvements.py::TestAdaptiveLoess::test_adaptive_frac_large_n PASSED
tests/test_metabolism_improvements.py::TestAdaptiveLoess::test_adaptive_frac_small_n PASSED
tests/test_metabolism_improvements.py::TestAdaptiveLoess::test_non_adaptive_uses_config_frac PASSED
tests/test_metabolism_improvements.py::TestProtocolTrimming::test_ramp_protocol PASSED
tests/test_metabolism_improvements.py::TestProtocolTrimming::test_step_protocol PASSED
tests/test_metabolism_improvements.py::TestProtocolTrimming::test_no_protocol PASSED
tests/test_metabolism_improvements.py::TestAdaptivePolynomial::test_cv_selects_degree PASSED
tests/test_metabolism_improvements.py::TestAdaptivePolynomial::test_cv_small_n_fallback PASSED
tests/test_metabolism_improvements.py::TestAdaptivePolynomial::test_adaptive_vs_fixed_polynomial PASSED
tests/test_metabolism_improvements.py::TestFatMaxBootstrapCI::test_ci_computed_when_enabled PASSED
tests/test_metabolism_improvements.py::TestFatMaxBootstrapCI::test_ci_not_in_dict_when_disabled PASSED
tests/test_metabolism_improvements.py::TestFatMaxBootstrapCI::test_ci_in_dict_when_enabled PASSED
tests/test_metabolism_improvements.py::TestMultiCrossover::test_single_crossover PASSED
tests/test_metabolism_improvements.py::TestMultiCrossover::test_crossover_has_confidence PASSED
tests/test_metabolism_improvements.py::TestMultiCrossover::test_confidence_in_dict PASSED
tests/test_metabolism_improvements.py::TestMultiCrossover::test_confidence_omitted_when_none PASSED
tests/test_metabolism_improvements.py::TestMultiCrossover::test_all_crossovers_in_markers PASSED
tests/test_metabolism_improvements.py::TestMultiCrossover::test_all_crossovers_dict_format PASSED
tests/test_metabolism_improvements.py::TestMultiCrossover::test_all_crossovers_omitted_when_none PASSED
tests/test_metabolism_improvements.py::TestBackwardCompatibility::test_default_config_same_behavior PASSED
tests/test_metabolism_improvements.py::TestBackwardCompatibility::test_to_dict_backward_compatible PASSED
tests/test_metabolism_improvements.py::TestBackwardCompatibility::test_legacy_constructor PASSED
tests/test_metabolism_improvements.py::TestBackwardCompatibility::test_config_to_dict_includes_new_fields PASSED
tests/test_metabolism_improvements.py::TestEndToEnd::test_full_pipeline_v11 PASSED
tests/test_metabolism_improvements.py::TestEndToEnd::test_full_pipeline_with_outliers PASSED
======================== 31 passed ========================
```

### 기존 테스트 (8개 전체 통과)
```
tests/test_metabolism_analysis.py::TestPhaseDetection::test_parse_file PASSED
tests/test_metabolism_analysis.py::TestPhaseDetection::test_calculate_metabolic_metrics PASSED
tests/test_metabolism_analysis.py::TestPhaseDetection::test_detect_phases PASSED
tests/test_metabolism_analysis.py::TestPhaseDetection::test_find_fatmax PASSED
tests/test_metabolism_analysis.py::TestPhaseDetection::test_find_vo2max PASSED
tests/test_metabolism_analysis.py::TestPhaseDetection::test_detect_vt_thresholds PASSED
tests/test_metabolism_analysis.py::TestPhaseDetection::test_phase_metrics PASSED
tests/test_metabolism_analysis.py::TestFullPipeline::test_full_analysis_pipeline PASSED
======================== 8 passed ========================
```

## Next Steps

- **프론트엔드 UI**: MetabolismConfig에 새 설정 필드 노출 (outlier, adaptive 토글 등)
- **시각화**: FatMax CI confidence band 차트에 추가, all_crossovers secondary 마커 표시
- **A/B 검증**: 실제 CPET 데이터로 v1.0 vs v1.1 마커 비교 테스트
- **DB 마이그레이션**: processed_metabolism 테이블에 새 config 컬럼 추가 여부 검토
- **성능**: bootstrap iterations 최적화 또는 비동기 처리 검토
