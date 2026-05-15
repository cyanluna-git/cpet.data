"""
tests/test_bxb_accuracy.py — E2E accuracy tests for BxB preprocessing algorithm.

Covers:
  1. Accuracy: Nolte smoothing variance reduction, spike removal + interpolation,
     nlargest(3).mean() VO2max within +-1% of manual computation.
  2. Full pipeline integration on park_geunyun and hong_changsun fixtures:
     verify vo2max_method, triplet metadata, physiological range.
  3. Edge case integration: very short BxB (5 rows), all-NaN VO2.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from pipeline.analysis import _preprocess_bxb, analyze_vo2max, run_analysis

FIXTURES = Path(__file__).parent / "fixtures"
PARK_WS = FIXTURES / "park_geunyun"
HONG_WS = FIXTURES / "hong_changsun"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_pipeline(workspace: Path) -> dict[str, dict[str, Any]]:
    """Run full pipeline and return analysis results from DB."""
    from pipeline.parsers import parse_workspace
    from pipeline.schema import create_database

    parsed = parse_workspace(workspace)
    db_path = create_database(workspace, parsed)
    run_analysis(db_path)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT category, key, value FROM analysis_results"
    ).fetchall()
    conn.close()

    results: dict[str, dict[str, Any]] = {}
    for cat, key, val in rows:
        if cat not in results:
            results[cat] = {}
        try:
            results[cat][key] = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            results[cat][key] = val
    return results


def _make_subject(weight_kg: float = 74.2) -> pd.DataFrame:
    return pd.DataFrame([{"weight_kg": weight_kg}])


def _assert_within_pct(
    actual: float, expected: float, pct: float = 1.0, label: str = ""
) -> None:
    """Assert actual is within +/-pct% of expected."""
    if expected == 0:
        assert abs(actual) < 0.01, f"{label}: expected ~0, got {actual}"
        return
    diff_pct = abs(actual - expected) / abs(expected) * 100
    assert diff_pct <= pct, (
        f"{label}: {actual} is {diff_pct:.2f}% from expected {expected} "
        f"(tolerance: +/-{pct}%)"
    )


# ===========================================================================
# 1. Accuracy Tests — Nolte Smoothing
# ===========================================================================


class TestSmoothingAccuracy:
    """Verify Nolte smoothing (Butterworth low-pass) behaviour on hand-crafted data."""

    def test_nolte_smoothing_reduces_variance(self) -> None:
        """Nolte smoothing should reduce variance on noisy data.

        Layout: 60 breaths at ~2s intervals over 120s.
        Heavy noise (std=300) so smoothing effect is clearly visible.
        """
        rng = np.random.RandomState(0)
        n = 60
        t_s = np.linspace(1.0, 120.0, n)
        vo2 = 3000.0 + rng.normal(0, 300.0, size=n)
        vco2 = vo2 * 0.85
        ve = vo2 / 50.0

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2,
            "vco2_ml": vco2,
            "ve_lmin": ve,
            "rq": vco2 / vo2,
            "hr_bpm": np.full(n, 140.0),
            "bike_power_w": np.full(n, 200.0),
        })

        processed = _preprocess_bxb(df)

        # Nolte Butterworth smoothing must reduce variance
        assert processed["vo2_ml"].std() < vo2.std(), (
            "Nolte smoothing should reduce vo2_ml variance"
        )
        # Mean should be approximately preserved (within 5%)
        assert abs(processed["vo2_ml"].mean() - vo2.mean()) / vo2.mean() < 0.05, (
            "Nolte smoothing should preserve mean within 5%"
        )

    def test_smoothing_with_uneven_breath_spacing(self) -> None:
        """Nolte smoothing on unevenly-spaced breaths should reduce variance."""
        rng = np.random.RandomState(1)
        t_s = np.array([1, 2, 3, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
                        21, 22, 23, 24], dtype=float)
        n = len(t_s)
        base_vo2 = 3000.0
        vo2 = base_vo2 + rng.normal(0, 300.0, size=n)
        vco2 = vo2 * 0.85
        ve = vo2 / 50.0

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2,
            "vco2_ml": vco2,
            "ve_lmin": ve,
            "rq": vco2 / vo2,
            "hr_bpm": np.full(n, 140.0),
            "bike_power_w": np.full(n, 200.0),
        })

        processed = _preprocess_bxb(df)

        # Nolte smoothing reduces variance even with uneven spacing
        assert processed["vo2_ml"].std() < vo2.std(), (
            "Nolte smoothing should reduce variance on uneven spacing"
        )
        # Output length must be preserved
        assert len(processed) == len(df), (
            "Preprocessing must not change DataFrame length"
        )


# ===========================================================================
# 2. Accuracy Tests — Spike Removal + Interpolation
# ===========================================================================


class TestSpikeRemovalAccuracy:
    """Verify known spikes are removed and interpolated correctly."""

    def test_single_spike_interpolated(self) -> None:
        """Insert a 5x spike into smooth data; verify it is removed and
        the interpolated value falls between neighbors."""
        n = 30
        t_s = np.arange(1.0, n + 1.0)
        # Flat-ish data around 3000 to avoid triggering window-edge effects
        vo2 = np.full(n, 3000.0)
        vco2 = vo2 * 0.85
        ve = vo2 / 50.0

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2.copy(),
            "vco2_ml": vco2.copy(),
            "ve_lmin": ve.copy(),
            "rq": vco2 / vo2,
            "hr_bpm": np.full(n, 150.0),
            "bike_power_w": np.full(n, 200.0),
        })

        # Inject spike at index 15 (>30% of local median = 3000)
        df.loc[15, "vo2_ml"] = 9000.0

        processed = _preprocess_bxb(df)

        # After smoothing + outlier removal, the spike at index 15
        # should be replaced and interpolated back to ~3000
        spike_val = processed.iloc[15]["vo2_ml"]
        assert spike_val < 5000.0, f"Spike should be removed, got {spike_val}"
        # Should be close to the surrounding value (~3000)
        assert abs(spike_val - 3000.0) < 500.0, (
            f"Interpolated value should be near 3000, got {spike_val}"
        )

    def test_no_nans_remain_after_spike_removal(self) -> None:
        """After spike removal, no NaN values should remain in target columns."""
        n = 50
        rng = np.random.RandomState(123)
        t_s = np.cumsum(rng.uniform(1.5, 2.5, size=n))
        vo2 = 3500.0 + rng.normal(0, 50, size=n)
        vco2 = vo2 * 0.85 + rng.normal(0, 20, size=n)
        ve = vo2 / 50.0 + rng.normal(0, 1, size=n)

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2,
            "vco2_ml": vco2,
            "ve_lmin": ve,
            "rq": vco2 / vo2,
            "hr_bpm": np.full(n, 155.0),
            "bike_power_w": np.full(n, 250.0),
        })

        # Inject multiple spikes
        df.loc[10, "vo2_ml"] = 12000.0
        df.loc[20, "vo2_ml"] = 15000.0
        df.loc[30, "vco2_ml"] = 10000.0

        processed = _preprocess_bxb(df)

        for col in ["vo2_ml", "vco2_ml", "ve_lmin"]:
            assert not processed[col].isna().any(), (
                f"Column {col} still has NaN after preprocessing"
            )

    def test_multiple_consecutive_spikes_cleaned(self) -> None:
        """Three consecutive spikes should all be removed and interpolated."""
        n = 40
        t_s = np.arange(1.0, n + 1.0)
        vo2 = np.full(n, 3000.0)
        vco2 = vo2 * 0.85
        ve = vo2 / 50.0

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2.copy(),
            "vco2_ml": vco2.copy(),
            "ve_lmin": ve.copy(),
            "rq": vco2 / vo2,
            "hr_bpm": np.full(n, 145.0),
            "bike_power_w": np.full(n, 200.0),
        })

        # Inject 3 consecutive spikes at indices 18, 19, 20
        for i in [18, 19, 20]:
            df.loc[i, "vo2_ml"] = 8000.0

        processed = _preprocess_bxb(df)

        for i in [18, 19, 20]:
            val = processed.iloc[i]["vo2_ml"]
            assert val <= 5000.0, f"Spike at index {i} should be removed, got {val}"
            # Should be closer to baseline than to the spike value
            assert val < 6000.0, f"Spike at index {i} not sufficiently cleaned, got {val}"


# ===========================================================================
# 3. Accuracy Tests — VO2max Triplet Averaging
# ===========================================================================


class TestVO2maxTripletAccuracy:
    """Verify nlargest(3).mean() matches hand calculation within +-1%."""

    def test_hand_calculated_vo2max(self) -> None:
        """Build BxB with known peak values; compute expected VO2max by hand.

        Since #2823 removed in-function rolling smoothing (preprocessing via
        _preprocess_bxb already applies Nolte smoothing before analysis),
        VO2max is now top-3 nlargest on the raw vo2_ml column directly.
        """
        rng = np.random.RandomState(77)
        n = 100
        t_s = np.cumsum(rng.uniform(1.5, 2.5, size=n))

        # Ramp from 2000 to 4000, then add known peaks near the end
        vo2_base = np.linspace(2000, 4000, n)
        vo2 = vo2_base + rng.normal(0, 30, size=n)

        # Force 3 known high values near end — these are the dominant peaks
        vo2[-3] = 4500.0
        vo2[-2] = 4600.0
        vo2[-1] = 4700.0

        vco2 = vo2 * 0.85
        ve = vo2 / 50.0

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2,
            "vco2_ml": vco2,
            "ve_lmin": ve,
            "rq": vco2 / vo2,
            "hr_bpm": 140 + rng.randint(-5, 5, size=n).astype(float),
            "bike_power_w": 200 + rng.randint(-10, 10, size=n).astype(float),
        })

        subject = _make_subject(70.0)
        results = analyze_vo2max(df, subject)

        # Hand-calc: top-3 nlargest of raw vo2_ml (no in-function rolling)
        from pipeline.analysis import _active_bxb_window

        valid = _active_bxb_window(df)
        n_peaks = min(3, len(valid))
        top3 = valid["vo2_ml"].nlargest(n_peaks)
        expected_vo2max = round(float(top3.mean()), 1)

        assert results["vo2max_ml"] == expected_vo2max, (
            f"VO2max {results['vo2max_ml']} != hand-calculated {expected_vo2max}"
        )
        assert results["vo2max_method"] == "top3_mean"
        assert len(results["vo2max_triplet_values"]) == 3

        # Verify triplet values are consistent
        triplet_mean = round(sum(results["vo2max_triplet_values"]) / 3.0, 1)
        assert results["vo2max_ml"] == triplet_mean

    def test_vo2max_rel_accuracy(self) -> None:
        """Verify vo2max_rel = vo2max_ml / weight within +-1%."""
        rng = np.random.RandomState(55)
        n = 80
        t_s = np.cumsum(rng.uniform(1.5, 2.5, size=n))
        vo2 = 3500 + rng.normal(0, 100, size=n)
        vco2 = vo2 * 0.85
        ve = vo2 / 50.0

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2,
            "vco2_ml": vco2,
            "ve_lmin": ve,
            "rq": vco2 / vo2,
            "hr_bpm": np.full(n, 160.0),
            "bike_power_w": np.full(n, 250.0),
        })

        weight = 65.0
        subject = _make_subject(weight)
        results = analyze_vo2max(df, subject)

        expected_rel = round(results["vo2max_ml"] / weight, 1)
        assert results["vo2max_rel"] == expected_rel, (
            f"vo2max_rel {results['vo2max_rel']} != expected {expected_rel}"
        )

    def test_preprocessed_then_vo2max_consistency(self) -> None:
        """Preprocessing followed by analyze_vo2max should produce consistent
        results: vo2max_ml equals mean of triplet_values within 0.1."""
        rng = np.random.RandomState(99)
        n = 120
        t_s = np.cumsum(rng.uniform(1.5, 2.5, size=n))
        vo2 = 3000 + np.linspace(0, 1500, n) + rng.normal(0, 80, size=n)
        # Inject some spikes
        vo2[30] = 8000.0
        vo2[60] = 9000.0
        vco2 = vo2 * 0.85
        ve = vo2 / 50.0

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2,
            "vco2_ml": vco2,
            "ve_lmin": ve,
            "rq": vco2 / vo2,
            "hr_bpm": 150 + rng.randint(-5, 5, size=n).astype(float),
            "bike_power_w": 200 + rng.randint(-20, 20, size=n).astype(float),
        })

        # Preprocess first (as run_analysis does)
        preprocessed = _preprocess_bxb(df)
        results = analyze_vo2max(preprocessed, _make_subject())

        assert "vo2max_ml" in results
        assert results["vo2max_method"] == "top3_mean"

        triplet_mean = sum(results["vo2max_triplet_values"]) / 3.0
        _assert_within_pct(
            results["vo2max_ml"], triplet_mean, pct=0.1,
            label="preprocessed vo2max vs triplet mean"
        )

        # Spikes should have been cleaned — vo2max should be reasonable
        assert 2000.0 < results["vo2max_ml"] < 7000.0


# ===========================================================================
# 4. Full Pipeline Integration — Park Geunyun
# ===========================================================================


class TestPipelineIntegrationPark:
    """Run run_analysis() on park_geunyun and verify BxB preprocessing metadata."""

    @pytest.fixture(autouse=True)
    def results(self) -> dict[str, dict[str, Any]]:
        self._results = _run_pipeline(PARK_WS)
        return self._results

    def test_vo2max_method_top3_mean(self) -> None:
        assert self._results["vo2max"]["vo2max_method"] == "top3_mean"

    def test_vo2max_triplet_has_3_items(self) -> None:
        triplet = self._results["vo2max"]["vo2max_triplet_values"]
        assert isinstance(triplet, list)
        assert len(triplet) == 3

    def test_vo2max_triplet_sorted_desc(self) -> None:
        triplet = self._results["vo2max"]["vo2max_triplet_values"]
        assert triplet == sorted(triplet, reverse=True), (
            f"Triplet should be sorted descending: {triplet}"
        )

    def test_vo2max_equals_triplet_mean(self) -> None:
        """vo2max_ml should equal the mean of the triplet values within +-1%."""
        vo2max = self._results["vo2max"]["vo2max_ml"]
        triplet = self._results["vo2max"]["vo2max_triplet_values"]
        expected = sum(triplet) / 3.0
        _assert_within_pct(vo2max, expected, pct=1.0, label="park vo2max vs triplet mean")

    def test_vo2max_physiological_range(self) -> None:
        """VO2max should be within physiological range (2000-7000 mL/min)."""
        vo2max = self._results["vo2max"]["vo2max_ml"]
        assert 2000.0 <= vo2max <= 7000.0, (
            f"VO2max {vo2max} outside physiological range [2000, 7000]"
        )

    def test_vo2max_rel_physiological_range(self) -> None:
        """VO2max relative should be 20-100 mL/min/kg for trained athletes."""
        vo2max_rel = self._results["vo2max"]["vo2max_rel"]
        assert 20.0 <= vo2max_rel <= 100.0, (
            f"VO2max relative {vo2max_rel} outside plausible range [20, 100]"
        )

    def test_outliers_removed_flag(self) -> None:
        assert self._results["vo2max"]["vo2max_outliers_removed"] is True

    def test_bxb_series_present(self) -> None:
        """BxB time series should be in results for charting."""
        series = self._results["vo2max"]["bxb_series"]
        assert "t_s" in series
        assert "vo2" in series
        assert len(series["t_s"]) > 10


# ===========================================================================
# 5. Full Pipeline Integration — Hong Changsun
# ===========================================================================


class TestPipelineIntegrationHong:
    """Run run_analysis() on hong_changsun and verify BxB preprocessing doesn't crash."""

    @pytest.fixture(autouse=True)
    def results(self) -> dict[str, dict[str, Any]]:
        self._results = _run_pipeline(HONG_WS)
        return self._results

    def test_preprocessing_does_not_crash(self) -> None:
        """Pipeline should complete without error on hong_changsun."""
        assert "vo2max" in self._results
        assert "vo2max_ml" in self._results["vo2max"]

    def test_vo2max_method_top3_mean(self) -> None:
        assert self._results["vo2max"]["vo2max_method"] == "top3_mean"

    def test_vo2max_triplet_has_3_items(self) -> None:
        triplet = self._results["vo2max"]["vo2max_triplet_values"]
        assert isinstance(triplet, list)
        assert len(triplet) == 3

    def test_vo2max_physiological_range(self) -> None:
        vo2max = self._results["vo2max"]["vo2max_ml"]
        assert 2000.0 <= vo2max <= 7000.0, (
            f"Hong VO2max {vo2max} outside physiological range"
        )

    def test_vo2max_equals_triplet_mean(self) -> None:
        vo2max = self._results["vo2max"]["vo2max_ml"]
        triplet = self._results["vo2max"]["vo2max_triplet_values"]
        expected = sum(triplet) / 3.0
        _assert_within_pct(vo2max, expected, pct=1.0, label="hong vo2max vs triplet mean")

    def test_outliers_removed_flag(self) -> None:
        assert self._results["vo2max"]["vo2max_outliers_removed"] is True


# ===========================================================================
# 6. Edge Case Integration
# ===========================================================================


class TestEdgeCaseIntegration:
    """Edge cases: very short BxB, all-NaN VO2."""

    def test_very_short_bxb_skips_preprocessing(self) -> None:
        """5-row BxB should skip preprocessing but still allow analysis to run."""
        t_s = np.array([1.0, 3.0, 5.0, 7.0, 9.0])
        vo2 = np.array([3000.0, 3100.0, 3200.0, 3300.0, 3400.0])
        vco2 = vo2 * 0.85
        ve = vo2 / 50.0

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2,
            "vco2_ml": vco2,
            "ve_lmin": ve,
            "rq": vco2 / vo2,
            "hr_bpm": np.full(5, 140.0),
            "bike_power_w": np.full(5, 200.0),
        })

        # Preprocessing should return copy without modification (< 10 breaths)
        processed = _preprocess_bxb(df)
        pd.testing.assert_frame_equal(df, processed)

        # analyze_vo2max should still produce a result
        subject = _make_subject()
        results = analyze_vo2max(processed, subject)
        assert "vo2max_ml" in results
        assert results["vo2max_ml"] > 0

    def test_all_nan_vo2_graceful_failure(self) -> None:
        """BxB with all-NaN vo2_ml should not crash; analysis returns empty."""
        n = 30
        t_s = np.arange(1.0, n + 1.0)

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": np.full(n, np.nan),
            "vco2_ml": np.full(n, np.nan),
            "ve_lmin": np.full(n, np.nan),
            "rq": np.full(n, np.nan),
            "hr_bpm": np.full(n, 140.0),
            "bike_power_w": np.full(n, 200.0),
        })

        # Preprocessing should not crash
        processed = _preprocess_bxb(df)
        assert isinstance(processed, pd.DataFrame)

        # analyze_vo2max should return empty (no valid breaths)
        subject = _make_subject()
        results = analyze_vo2max(processed, subject)
        assert results == {} or "vo2max_ml" not in results

    def test_all_zero_vo2_graceful_failure(self) -> None:
        """BxB with all-zero vo2_ml should not crash; _active_bxb_window filters them."""
        n = 30
        t_s = np.arange(1.0, n + 1.0)

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": np.zeros(n),
            "vco2_ml": np.zeros(n),
            "ve_lmin": np.zeros(n),
            "rq": np.full(n, 0.85),
            "hr_bpm": np.full(n, 140.0),
            "bike_power_w": np.full(n, 200.0),
        })

        processed = _preprocess_bxb(df)
        subject = _make_subject()
        results = analyze_vo2max(processed, subject)
        # _active_bxb_window filters vo2_ml <= 100, so result should be empty
        assert results == {}

    def test_single_extreme_outlier_in_otherwise_clean_data(self) -> None:
        """One massive outlier (10x baseline) in clean data should be removed
        and the final VO2max should not be inflated by it."""
        rng = np.random.RandomState(42)
        n = 100
        t_s = np.cumsum(rng.uniform(1.5, 2.5, size=n))
        vo2 = np.full(n, 3500.0) + rng.normal(0, 30, size=n)
        vco2 = vo2 * 0.85
        ve = vo2 / 50.0

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2.copy(),
            "vco2_ml": vco2.copy(),
            "ve_lmin": ve.copy(),
            "rq": vco2 / vo2,
            "hr_bpm": np.full(n, 160.0),
            "bike_power_w": np.full(n, 250.0),
        })

        # Inject one extreme outlier
        df.loc[50, "vo2_ml"] = 35000.0  # 10x baseline

        processed = _preprocess_bxb(df)
        results = analyze_vo2max(processed, _make_subject(70.0))

        # VO2max should stay near 3500, not be inflated by the 35000 spike
        assert results["vo2max_ml"] < 5000.0, (
            f"VO2max {results['vo2max_ml']} inflated by outlier"
        )
        _assert_within_pct(
            results["vo2max_ml"], 3500.0, pct=15.0,
            label="vo2max after outlier removal"
        )


# ===========================================================================
# EC-#2823: Edge cases for rolling-removal refactor
# ===========================================================================


class TestRollingRemovalEdgeCases:
    """Verify correctness of the #2823 rolling-removal refactor across all
    analysis sites (analyze_vo2max, analyze_ventilatory_thresholds,
    analyze_cpm_indices nadir) for critical boundary conditions."""

    # -----------------------------------------------------------------------
    # EC-1: analyze_vo2max() with ve_vo2 column present must not crash
    # -----------------------------------------------------------------------
    def test_vo2max_with_ve_vo2_column_present(self) -> None:
        """analyze_vo2max() must not crash when BxB includes ve_vo2 column."""
        from pipeline.analysis import analyze_vo2max

        rng = np.random.RandomState(11)
        n = 50
        t_s = np.cumsum(rng.uniform(1.5, 2.5, size=n))
        vo2 = np.linspace(2000.0, 4000.0, n)
        vco2 = vo2 * 0.85
        ve = vo2 / 50.0

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2,
            "vco2_ml": vco2,
            "ve_lmin": ve,
            "rq": vco2 / vo2,
            "ve_vo2": ve / (vo2 / 1000.0),  # extra column — must not interfere
            "hr_bpm": np.full(n, 155.0),
            "bike_power_w": np.linspace(100.0, 300.0, n),
        })

        subject = _make_subject(70.0)
        results = analyze_vo2max(df, subject)

        assert "vo2max_ml" in results, "vo2max_ml missing when ve_vo2 column present"
        assert results["vo2max_ml"] > 0.0

    # -----------------------------------------------------------------------
    # EC-2: analyze_ventilatory_thresholds() with missing ve_vo2 — KeyError?
    # -----------------------------------------------------------------------
    def test_ventilatory_thresholds_missing_ve_vo2_raises(self) -> None:
        """analyze_ventilatory_thresholds() raises KeyError when ve_vo2 column
        is absent from BxB data with >= 20 rows.

        This documents the current contract: callers must ensure _preprocess_bxb
        has been run so that ve_vo2 is present before calling VT analysis.
        If this test ever starts PASSING without raising, it means a guard was
        added and the docstring / contract should be updated accordingly.
        """
        from pipeline.analysis import analyze_ventilatory_thresholds

        rng = np.random.RandomState(22)
        n = 30
        t_s = np.cumsum(rng.uniform(1.5, 2.5, size=n))
        vo2 = np.linspace(2000.0, 4000.0, n)
        vco2 = vo2 * 0.85
        ve = vo2 / 50.0

        # Intentionally omit ve_vo2 and ve_vco2 columns
        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2,
            "vco2_ml": vco2,
            "ve_lmin": ve,
            "rq": vco2 / vo2,
            "hr_bpm": np.full(n, 155.0),
            "bike_power_w": np.linspace(100.0, 300.0, n),
        })

        with pytest.raises(KeyError):
            analyze_ventilatory_thresholds(df)

    # -----------------------------------------------------------------------
    # EC-3: CPM nadir with 1-row active BxB (no >=30 guard)
    # -----------------------------------------------------------------------
    def test_cpm_nadir_with_single_row_active_bxb(self) -> None:
        """analyze_cpm_indices() ve_vco2_nadir must compute on 1-row active BxB.

        The >=30 row guard was removed in #2823; Series.min() on length-1 is
        valid and should return the single value, not be unsupported.
        """
        from pipeline.analysis import analyze_cpm_indices

        bxb = pd.DataFrame({
            "block": ["block_1"],
            "t_s": [5.0],
            "ve_lmin": [45.0],
            "vco2_ml": [2000.0],
            "vo2_ml": [2500.0],
            "ve_vo2": [18.0],
            "ve_vco2": [22.5],
            "rq": [0.80],
            "hr_bpm": [145.0],
            "bike_power_w": [200.0],
        })

        result = analyze_cpm_indices(
            bxb=bxb,
            vo2max_results={"vo2max_ml": 2500.0, "rer_max": 1.1},
            vt_results={"vt2_power_w": 200.0},
            substrate_results={},
            efficiency_results={},
            hr_results={},
        )

        # ve_vco2_nadir should be computed (not unsupported) with 1 row
        vmsi_entry = result.get("vmsi", {})
        assert vmsi_entry.get("supported") is True, (
            f"vmsi unsupported on 1-row BxB — nadir guard may have regressed. "
            f"blocker: {vmsi_entry.get('blocker')}"
        )

    # -----------------------------------------------------------------------
    # EC-4: VT detection on a noisy 10-minute ramp — VT1 still detected
    # -----------------------------------------------------------------------
    def test_vt_detection_on_noisy_ramp_still_finds_vt1(self) -> None:
        """analyze_ventilatory_thresholds() should detect VT1 on a realistic
        noisy 10-min ramp even without in-function rolling smoothing.

        The ramp has a V-shaped VE/VO2 nadir in the first 75% of the data;
        argmin should find it regardless of noise level that preprocessing
        (Nolte / Butterworth) would normally remove.
        """
        from pipeline.analysis import analyze_ventilatory_thresholds

        rng = np.random.RandomState(99)
        n = 120  # ~10 min at ~5s per breath
        t_s = np.cumsum(rng.uniform(4.5, 5.5, size=n))

        # Monotone VO2 ramp
        vo2 = np.linspace(1500.0, 4500.0, n)
        vco2 = vo2 * np.where(t_s < t_s[n // 2], 0.78, 0.95)
        ve = vo2 / 50.0 + rng.normal(0, 0.3, size=n)

        # Build a clear V-shaped VE/VO2: decreasing to ~row 40, then rising
        ve_vo2_base = np.concatenate([
            np.linspace(32.0, 24.0, 40),   # descend to nadir
            np.linspace(24.0, 48.0, n - 40),  # rise post-VT1
        ])
        ve_vo2 = ve_vo2_base + rng.normal(0, 0.5, size=n)  # mild noise

        ve_vco2_base = np.concatenate([
            np.linspace(28.0, 22.0, 60),
            np.linspace(22.0, 35.0, n - 60),
        ])
        ve_vco2 = ve_vco2_base + rng.normal(0, 0.4, size=n)

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2,
            "vco2_ml": vco2,
            "ve_lmin": ve,
            "rq": vco2 / vo2,
            "ve_vo2": ve_vo2,
            "ve_vco2": ve_vco2,
            "hr_bpm": np.linspace(80.0, 185.0, n),
            "bike_power_w": np.linspace(50.0, 350.0, n),
        })

        result = analyze_ventilatory_thresholds(df)

        assert "vt1_time_s" in result, (
            "VT1 not detected on 10-min noisy ramp — smoothing removal may have "
            "degraded nadir detection"
        )
        # VT1 should fall in the first half of the test
        assert result["vt1_time_s"] < t_s[n // 2], (
            f"VT1 detected too late: {result['vt1_time_s']:.1f}s vs midpoint {t_s[n // 2]:.1f}s"
        )
