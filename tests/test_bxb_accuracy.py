"""
tests/test_bxb_accuracy.py — E2E accuracy tests for BxB preprocessing algorithm.

Covers:
  1. Accuracy: hand-calculated 5s smoothing, spike removal + interpolation,
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
# 1. Accuracy Tests — 5s Smoothing
# ===========================================================================


class TestSmoothingAccuracy:
    """Verify exact 5s rolling mean output on hand-crafted synthetic data."""

    def test_exact_5s_smoothing_values(self) -> None:
        """Build a BxB where we know the exact 5s rolling mean result.

        Layout: 20 breaths at exactly 1s intervals (t=1,2,...,20).
        vo2_ml = [100, 200, 300, ...] (100*i).
        5s rolling window at t=10 captures breaths at t=6,7,8,9,10 -> mean(600,700,800,900,1000)=800.
        """
        n = 20
        t_s = np.arange(1.0, n + 1.0)  # 1s spacing
        vo2 = t_s * 100.0  # 100, 200, ..., 2000
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

        # After 5s rolling mean, the value at t=10 (index 9 after sort)
        # should be mean of breaths within [10-5, 10] = [5,10] seconds.
        # That's t=6,7,8,9,10 -> vo2 = 600,700,800,900,1000 -> mean = 800.
        # But after smoothing, outlier removal follows. With this linear data
        # no outliers should be flagged, so smoothed values stay.

        # For the first few breaths the window is smaller (min_periods=1).
        # At t=5 (index 4), window covers t=1..5 -> mean(100..500) = 300
        # At t=10 (index 9), window covers t=6..10 -> mean(600..1000) = 800

        # The smoothing uses pd.to_timedelta, so the "5s" window captures
        # all values within 5 seconds before each point.
        # At t=5.0s: window = [1.0, 5.0] -> indices 0-4 -> mean(100..500) = 300
        idx_5 = 4   # t=5s
        idx_10 = 9  # t=10s

        expected_at_5 = np.mean([100, 200, 300, 400, 500])  # 300
        expected_at_10 = np.mean([600, 700, 800, 900, 1000])  # 800

        # Allow tiny floating point tolerance
        np.testing.assert_allclose(
            processed.iloc[idx_5]["vo2_ml"], expected_at_5, rtol=1e-10,
            err_msg="5s smoothing at t=5s should equal mean of t=1..5"
        )
        np.testing.assert_allclose(
            processed.iloc[idx_10]["vo2_ml"], expected_at_10, rtol=1e-10,
            err_msg="5s smoothing at t=10s should equal mean of t=6..10"
        )

    def test_smoothing_with_uneven_breath_spacing(self) -> None:
        """Uneven breath timing: verify 5s window picks correct breaths."""
        # Breaths at t = [1, 2, 3, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
        # Gap between t=3 and t=8 means at t=10, window=[6,10] captures only t=8,9,10
        t_s = np.array([1, 2, 3, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
                       dtype=float)
        vo2 = np.array([100, 200, 300, 800, 900, 1000,
                        1100, 1200, 1300, 1400, 1500, 1600,
                        1700, 1800, 1900, 2000], dtype=float)
        vco2 = vo2 * 0.85
        ve = vo2 / 50.0

        df = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2,
            "vco2_ml": vco2,
            "ve_lmin": ve,
            "rq": vco2 / vo2,
            "hr_bpm": np.full(len(t_s), 140.0),
            "bike_power_w": np.full(len(t_s), 200.0),
        })

        processed = _preprocess_bxb(df)

        # At t=10 (index 5 in sorted df), 5s window = [5,10] -> t=8,9,10
        # mean(800,900,1000) = 900
        idx_t10 = 5
        expected_at_10 = np.mean([800, 900, 1000])

        np.testing.assert_allclose(
            processed.iloc[idx_t10]["vo2_ml"], expected_at_10, rtol=1e-10,
            err_msg="Uneven spacing: 5s window at t=10 should include t=8,9,10 only"
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
        """Build BxB with known peak values; compute expected VO2max by hand."""
        rng = np.random.RandomState(77)
        n = 100
        t_s = np.cumsum(rng.uniform(1.5, 2.5, size=n))

        # Ramp from 2000 to 4000, then add known peaks near the end
        vo2_base = np.linspace(2000, 4000, n)
        vo2 = vo2_base + rng.normal(0, 30, size=n)

        # Force 3 known high values near end (will dominate after rolling)
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

        # The result should use top-3 from a 10-breath rolling mean,
        # so compute manually
        from pipeline.analysis import _active_bxb_window

        valid = _active_bxb_window(df)
        window = min(10, len(valid))
        valid = valid.copy()
        valid["vo2_rolling"] = valid["vo2_ml"].rolling(window, min_periods=1).mean()

        n_peaks = min(3, len(valid))
        top3 = valid["vo2_rolling"].nlargest(n_peaks)
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
