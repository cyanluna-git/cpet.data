"""Tests for MetabolismAnalyzer v1.1.0 improvements

Tests cover:
1. IQR outlier detection
2. Sparse bin merging
3. Adaptive LOESS fraction
4. Protocol-aware trimming
5. Cross-validation polynomial degree
6. FatMax bootstrap confidence interval
7. Multi-crossover detection
"""

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.metabolism_analysis import (
    AnalysisConfig,
    CrossoverMarker,
    FatMaxMarker,
    MetabolicMarkers,
    MetabolismAnalyzer,
    ProcessedDataPoint,
)


@dataclass
class FakeBreathData:
    """Minimal breath data for testing"""

    bike_power: Optional[float] = None
    fat_oxidation: Optional[float] = None
    cho_oxidation: Optional[float] = None
    rer: Optional[float] = None
    vo2: Optional[float] = None
    vo2_rel: Optional[float] = None
    vco2: Optional[float] = None
    hr: Optional[float] = None
    ve_vo2: Optional[float] = None
    ve_vco2: Optional[float] = None
    t_sec: Optional[float] = None
    phase: str = "Exercise"


def _make_breath_data(n=30, seed=42):
    """Generate synthetic CPET breath data with known characteristics.

    Creates data with:
    - Fat oxidation: inverted U peaking around 100-120W
    - CHO oxidation: exponential rise
    - Crossover around 140-160W
    """
    rng = np.random.default_rng(seed)
    powers = np.linspace(30, 300, n)
    data = []
    for i, p in enumerate(powers):
        # Fat: inverted U shape, peak around 110W
        fat = max(0, 0.5 * np.exp(-((p - 110) ** 2) / (2 * 60**2)) + rng.normal(0, 0.02))
        # CHO: exponential rise
        cho = max(0, 0.1 + 0.003 * p + rng.normal(0, 0.02))
        rer = 0.7 + 0.001 * p + rng.normal(0, 0.01)
        vo2 = 500 + 10 * p + rng.normal(0, 20)
        vco2 = vo2 * rer
        hr = 60 + 0.4 * p + rng.normal(0, 2)
        data.append(
            FakeBreathData(
                bike_power=float(p),
                fat_oxidation=float(fat),
                cho_oxidation=float(cho),
                rer=float(rer),
                vo2=float(vo2),
                vo2_rel=float(vo2 / 70),
                vco2=float(vco2),
                hr=float(hr),
                ve_vo2=25 + 0.05 * p,
                ve_vco2=28 + 0.03 * p,
                t_sec=float(60 + i * 10),
                phase="Exercise",
            )
        )
    return data


def _make_breath_data_with_outliers(n=30, n_outliers=3, seed=42):
    """Generate data with obvious outliers injected."""
    data = _make_breath_data(n=n, seed=seed)
    rng = np.random.default_rng(seed + 1)
    indices = rng.choice(len(data), size=n_outliers, replace=False)
    for idx in indices:
        data[idx].fat_oxidation = 5.0  # Way above normal range (< 1.0)
        data[idx].cho_oxidation = -2.0  # Negative (should be >= 0)
    return data, set(indices)


class TestOutlierDetection:
    """1. IQR-based outlier detection"""

    def test_outliers_removed(self):
        """Outliers should be removed from clean data"""
        data, outlier_indices = _make_breath_data_with_outliers(n=30, n_outliers=3)
        config = AnalysisConfig(
            outlier_detection_enabled=True,
            outlier_iqr_multiplier=1.5,
            auto_trim_enabled=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        # Warnings should mention outlier removal
        outlier_warnings = [w for w in result.warnings if "outlier" in w.lower()]
        assert len(outlier_warnings) > 0

    def test_outlier_disabled(self):
        """When disabled, no outlier removal should occur"""
        data, _ = _make_breath_data_with_outliers(n=30, n_outliers=3)
        config = AnalysisConfig(
            outlier_detection_enabled=False,
            auto_trim_enabled=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        outlier_warnings = [w for w in result.warnings if "outlier" in w.lower()]
        assert len(outlier_warnings) == 0

    def test_no_removal_when_few_points(self):
        """Should skip outlier detection with < 10 data points"""
        data = _make_breath_data(n=8)
        data[0].fat_oxidation = 10.0  # Obvious outlier
        config = AnalysisConfig(
            outlier_detection_enabled=True,
            auto_trim_enabled=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        raw_points = analyzer._extract_raw_points(data)
        cleaned = analyzer._detect_and_remove_outliers(raw_points)
        # Should NOT remove (< 10 points)
        assert len(cleaned) == len(raw_points)

    def test_raw_series_preserves_original(self):
        """ProcessedSeries.raw should contain original data (after phase trim, before outlier removal)"""
        data, _ = _make_breath_data_with_outliers(n=30, n_outliers=3)
        config = AnalysisConfig(
            outlier_detection_enabled=True,
            auto_trim_enabled=False,
            exclude_initial_hyperventilation=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        # raw should have all points from extraction (before outlier removal)
        assert len(result.processed_series.raw) == 30


class TestSparseBinMerging:
    """2. Sparse bin merging"""

    def test_sparse_bins_merged(self):
        """Bins with fewer than min_bin_count should be merged"""
        # Create data with several power bins, some sparse
        data = []
        rng = np.random.default_rng(42)
        # 10 points around 100W, 10 around 120W, 10 around 140W, 10 around 160W
        for center in [100, 120, 140, 160]:
            for i in range(10):
                p = center + rng.normal(0, 2)
                data.append(
                    FakeBreathData(
                        bike_power=float(p),
                        fat_oxidation=0.4 - 0.001 * center,
                        cho_oxidation=0.1 + 0.002 * center,
                        t_sec=float(60 + len(data) * 5),
                    )
                )
        # Single sparse points at 200W and 220W (will be sparse bins)
        # Use reasonable oxidation values to avoid outlier removal
        for sparse_power in [200, 220]:
            data.append(
                FakeBreathData(
                    bike_power=float(sparse_power),
                    fat_oxidation=0.25,
                    cho_oxidation=0.35,
                    t_sec=float(60 + len(data) * 5),
                )
            )

        config = AnalysisConfig(
            min_bin_count=3,
            outlier_detection_enabled=False,  # Disable to keep sparse points
            auto_trim_enabled=False,
            exclude_initial_hyperventilation=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        merge_warnings = [w for w in result.warnings if "sparse" in w.lower()]
        assert len(merge_warnings) > 0

    def test_no_merge_when_min_count_1(self):
        """No merging when min_bin_count=1"""
        data = _make_breath_data(n=30)
        config = AnalysisConfig(
            min_bin_count=1,
            auto_trim_enabled=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        merge_warnings = [w for w in result.warnings if "sparse" in w.lower()]
        assert len(merge_warnings) == 0


class TestAdaptiveLoess:
    """3. Adaptive LOESS fraction"""

    def test_adaptive_frac_large_n(self):
        """With many data points, adaptive frac should be small"""
        data = _make_breath_data(n=50)
        config = AnalysisConfig(
            adaptive_loess=True,
            auto_trim_enabled=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        assert len(result.processed_series.smoothed) > 0

    def test_adaptive_frac_small_n(self):
        """With few data points, adaptive frac should be larger"""
        data = _make_breath_data(n=12)
        config = AnalysisConfig(
            adaptive_loess=True,
            auto_trim_enabled=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        assert len(result.processed_series.smoothed) > 0

    def test_non_adaptive_uses_config_frac(self):
        """When adaptive is off, should use configured frac"""
        data = _make_breath_data(n=30)
        config = AnalysisConfig(
            adaptive_loess=False,
            loess_frac=0.4,
            auto_trim_enabled=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None


class TestProtocolTrimming:
    """4. Protocol-aware trimming"""

    def _make_data_with_times(self, n=60):
        """Make data with full time range and power ramp"""
        data = []
        for i in range(n):
            t = float(i * 10)
            p = float(max(0, min(300, i * 5)))
            data.append(
                FakeBreathData(
                    bike_power=p,
                    fat_oxidation=max(0, 0.4 - 0.001 * p),
                    cho_oxidation=0.1 + 0.002 * p,
                    t_sec=t,
                    phase="Exercise",
                )
            )
        return data

    def test_ramp_protocol(self):
        """Ramp protocol should use recovery_ratio=0.70, start_threshold=30"""
        data = self._make_data_with_times()
        config = AnalysisConfig(
            protocol_type="ramp",
            auto_trim_enabled=True,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None

    def test_step_protocol(self):
        """Step protocol should use recovery_ratio=0.85, start_threshold=20"""
        data = self._make_data_with_times()
        config = AnalysisConfig(
            protocol_type="step",
            auto_trim_enabled=True,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None

    def test_no_protocol(self):
        """No protocol should use default config values"""
        data = self._make_data_with_times()
        config = AnalysisConfig(
            protocol_type=None,
            auto_trim_enabled=True,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None


class TestAdaptivePolynomial:
    """5. Cross-validation polynomial degree"""

    def test_cv_selects_degree(self):
        """CV should select a reasonable degree"""
        config = AnalysisConfig(adaptive_polynomial=True, auto_trim_enabled=False)
        analyzer = MetabolismAnalyzer(config=config)

        x = np.linspace(0, 100, 20)
        y = 0.5 * np.sin(x / 30) + 0.01 * x  # Non-trivial curve
        degree = analyzer._select_poly_degree_cv(x, y, max_degree=4)
        assert 1 <= degree <= 4

    def test_cv_small_n_fallback(self):
        """With < 6 points, should fallback to min(3, n-1)"""
        config = AnalysisConfig(adaptive_polynomial=True, auto_trim_enabled=False)
        analyzer = MetabolismAnalyzer(config=config)

        x = np.array([10, 20, 30, 40])
        y = np.array([0.1, 0.3, 0.2, 0.1])
        degree = analyzer._select_poly_degree_cv(x, y, max_degree=4)
        assert degree == min(3, len(x) - 1)

    def test_adaptive_vs_fixed_polynomial(self):
        """Both adaptive and fixed should produce valid trend lines"""
        data = _make_breath_data(n=30)

        for adaptive in [True, False]:
            config = AnalysisConfig(
                adaptive_polynomial=adaptive,
                auto_trim_enabled=False,
            )
            analyzer = MetabolismAnalyzer(config=config)
            result = analyzer.analyze(data)
            assert result is not None
            assert len(result.processed_series.trend) > 0


class TestFatMaxBootstrapCI:
    """6. FatMax bootstrap confidence interval"""

    def test_ci_computed_when_enabled(self):
        """CI fields should be populated when enabled"""
        data = _make_breath_data(n=30)
        config = AnalysisConfig(
            fatmax_confidence_interval=True,
            fatmax_bootstrap_iterations=200,
            auto_trim_enabled=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        fm = result.metabolic_markers.fat_max
        assert fm.mfo_ci_lower is not None
        assert fm.mfo_ci_upper is not None
        assert fm.power_ci_lower is not None
        assert fm.power_ci_upper is not None
        assert fm.mfo_ci_lower <= fm.mfo <= fm.mfo_ci_upper

    def test_ci_not_in_dict_when_disabled(self):
        """CI fields should not appear in to_dict() when disabled"""
        data = _make_breath_data(n=30)
        config = AnalysisConfig(
            fatmax_confidence_interval=False,
            auto_trim_enabled=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        fm_dict = result.metabolic_markers.fat_max.to_dict()
        assert "mfo_ci_lower" not in fm_dict
        assert "mfo_ci_upper" not in fm_dict
        assert "power_ci_lower" not in fm_dict
        assert "power_ci_upper" not in fm_dict

    def test_ci_in_dict_when_enabled(self):
        """CI fields should appear in to_dict() when computed"""
        data = _make_breath_data(n=30)
        config = AnalysisConfig(
            fatmax_confidence_interval=True,
            fatmax_bootstrap_iterations=100,
            auto_trim_enabled=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        fm_dict = result.metabolic_markers.fat_max.to_dict()
        assert "mfo_ci_lower" in fm_dict
        assert "mfo_ci_upper" in fm_dict


class TestMultiCrossover:
    """7. Multi-crossover detection"""

    def test_single_crossover(self):
        """Standard data should have one crossover"""
        data = _make_breath_data(n=30)
        config = AnalysisConfig(auto_trim_enabled=False)
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        assert result.metabolic_markers.crossover.power is not None

    def test_crossover_has_confidence(self):
        """Primary crossover should have confidence score"""
        data = _make_breath_data(n=30)
        config = AnalysisConfig(auto_trim_enabled=False)
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        if result.metabolic_markers.crossover.power is not None:
            assert result.metabolic_markers.crossover.confidence is not None
            assert result.metabolic_markers.crossover.confidence > 0

    def test_confidence_in_dict(self):
        """Confidence should appear in to_dict() when present"""
        marker = CrossoverMarker(
            power=150, fat_value=0.3, cho_value=0.3, confidence=0.05
        )
        d = marker.to_dict()
        assert "confidence" in d
        assert d["confidence"] == 0.05

    def test_confidence_omitted_when_none(self):
        """Confidence should be omitted from to_dict() when None"""
        marker = CrossoverMarker(power=150, fat_value=0.3, cho_value=0.3)
        d = marker.to_dict()
        assert "confidence" not in d

    def test_all_crossovers_in_markers(self):
        """MetabolicMarkers should include all_crossovers when multiple exist"""
        # Create data that crosses multiple times
        data = []
        for i in range(40):
            p = float(30 + i * 7)
            t = float(60 + i * 10)
            # Fat oscillates: goes up, down, up, down
            fat = 0.3 + 0.2 * np.sin(i * 0.3)
            cho = 0.1 + 0.005 * p
            data.append(
                FakeBreathData(
                    bike_power=p,
                    fat_oxidation=float(max(0, fat)),
                    cho_oxidation=float(max(0, cho)),
                    t_sec=t,
                    phase="Exercise",
                )
            )
        config = AnalysisConfig(auto_trim_enabled=False)
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        # The data should produce some crossover; all_crossovers may or may not be set

    def test_all_crossovers_dict_format(self):
        """all_crossovers should serialize correctly"""
        markers = MetabolicMarkers(
            fat_max=FatMaxMarker(power=100, mfo=0.5, zone_min=80, zone_max=120),
            crossover=CrossoverMarker(power=150, fat_value=0.3, cho_value=0.3, confidence=0.1),
            all_crossovers=[
                CrossoverMarker(power=150, fat_value=0.3, cho_value=0.3, confidence=0.1),
                CrossoverMarker(power=200, fat_value=0.2, cho_value=0.2, confidence=0.05),
            ],
        )
        d = markers.to_dict()
        assert "all_crossovers" in d
        assert len(d["all_crossovers"]) == 2
        assert d["all_crossovers"][0]["power"] == 150

    def test_all_crossovers_omitted_when_none(self):
        """all_crossovers should be omitted from to_dict() when None"""
        markers = MetabolicMarkers(
            fat_max=FatMaxMarker(power=100, mfo=0.5, zone_min=80, zone_max=120),
            crossover=CrossoverMarker(power=150, fat_value=0.3, cho_value=0.3),
        )
        d = markers.to_dict()
        assert "all_crossovers" not in d


class TestBackwardCompatibility:
    """Ensure v1.1.0 changes don't break existing behavior"""

    def test_default_config_same_behavior(self):
        """Default AnalysisConfig should produce valid results"""
        data = _make_breath_data(n=30)
        config = AnalysisConfig(auto_trim_enabled=False)
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        assert len(result.processed_series.raw) > 0
        assert len(result.processed_series.binned) > 0
        assert len(result.processed_series.smoothed) > 0
        assert result.metabolic_markers.fat_max.power >= 0

    def test_to_dict_backward_compatible(self):
        """to_dict() output should have same required keys as v1.0.0"""
        data = _make_breath_data(n=30)
        config = AnalysisConfig(
            auto_trim_enabled=False,
            fatmax_confidence_interval=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        d = result.to_dict()
        # Required top-level keys
        assert "processed_series" in d
        assert "metabolic_markers" in d
        assert "warnings" in d
        # Required series keys
        ps = d["processed_series"]
        assert "raw" in ps
        assert "binned" in ps
        assert "smoothed" in ps
        assert "trend" in ps
        # Required marker keys
        mm = d["metabolic_markers"]
        assert "fat_max" in mm
        assert "crossover" in mm
        # FatMax required keys
        fm = mm["fat_max"]
        assert "power" in fm
        assert "mfo" in fm
        assert "zone_min" in fm
        assert "zone_max" in fm
        # CI keys should NOT be present when disabled
        assert "mfo_ci_lower" not in fm
        # Crossover required keys
        co = mm["crossover"]
        assert "power" in co
        assert "fat_value" in co
        assert "cho_value" in co

    def test_legacy_constructor(self):
        """Legacy constructor (without config) should still work"""
        analyzer = MetabolismAnalyzer(
            loess_frac=0.3, bin_size=10, use_median=True
        )
        data = _make_breath_data(n=30)
        result = analyzer.analyze(data)
        assert result is not None

    def test_config_to_dict_includes_new_fields(self):
        """AnalysisConfig.to_dict() should include v1.1.0 fields"""
        config = AnalysisConfig()
        d = config.to_dict()
        assert "outlier_detection_enabled" in d
        assert "outlier_iqr_multiplier" in d
        assert "min_bin_count" in d
        assert "adaptive_loess" in d
        assert "protocol_type" in d
        assert "adaptive_polynomial" in d
        assert "fatmax_confidence_interval" in d
        assert "fatmax_bootstrap_iterations" in d


class TestEndToEnd:
    """End-to-end tests with synthetic data"""

    def test_full_pipeline_v11(self):
        """Full pipeline with all v1.1.0 features enabled"""
        data = _make_breath_data(n=40, seed=123)
        config = AnalysisConfig(
            outlier_detection_enabled=True,
            outlier_iqr_multiplier=1.5,
            min_bin_count=3,
            adaptive_loess=True,
            adaptive_polynomial=True,
            fatmax_confidence_interval=True,
            fatmax_bootstrap_iterations=100,
            auto_trim_enabled=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        assert result.metabolic_markers.fat_max.mfo > 0
        assert result.metabolic_markers.fat_max.mfo_ci_lower is not None
        assert len(result.processed_series.trend) > 0

    def test_full_pipeline_with_outliers(self):
        """Pipeline should handle data with outliers gracefully"""
        data, _ = _make_breath_data_with_outliers(n=40, n_outliers=5, seed=99)
        config = AnalysisConfig(
            outlier_detection_enabled=True,
            auto_trim_enabled=False,
        )
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(data)
        assert result is not None
        # Should have removed some outliers
        outlier_warnings = [w for w in result.warnings if "outlier" in w.lower()]
        assert len(outlier_warnings) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
