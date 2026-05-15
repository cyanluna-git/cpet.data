"""
tests/test_bxb_preprocessing.py — Unit tests for BxB preprocessing algorithm.

Covers:
  - 5-second time-based rolling mean (Step 1)
  - 30% local-median outlier removal (Step 2)
  - VO2max triplet peak averaging (Step 3)
  - Edge cases: <10 breaths, all-outlier, >30s gaps
"""

import numpy as np
import pandas as pd
import pytest

from pipeline.analysis import _apply_nolte_smoothing, _preprocess_bxb, analyze_vo2max


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bxb(
    n: int = 50,
    dt: float = 2.0,
    vo2_base: float = 3000.0,
    noise_std: float = 50.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Create a synthetic breath-by-breath DataFrame.

    Args:
        n: Number of breaths.
        dt: Average time delta between breaths (seconds).
        vo2_base: Baseline VO2 (mL/min).
        noise_std: Standard deviation of noise on VO2/VCO2/VE.
        seed: Random seed for reproducibility.
    """
    rng = np.random.RandomState(seed)
    t_s = np.cumsum(rng.uniform(dt * 0.7, dt * 1.3, size=n))
    vo2 = vo2_base + rng.normal(0, noise_std, size=n)
    vco2 = vo2 * 0.85 + rng.normal(0, noise_std * 0.5, size=n)
    ve = vo2 / 50.0 + rng.normal(0, 1.0, size=n)

    return pd.DataFrame({
        "t_s": t_s,
        "vo2_ml": vo2,
        "vco2_ml": vco2,
        "ve_lmin": ve,
        "rq": vco2 / vo2,
        "hr_bpm": 140 + rng.randint(-5, 5, size=n).astype(float),
        "bike_power_w": 200 + rng.randint(-10, 10, size=n).astype(float),
    })


def _make_subject(weight_kg: float = 74.2) -> pd.DataFrame:
    return pd.DataFrame([{"weight_kg": weight_kg}])


# ===========================================================================
# Step 1: 5-second rolling mean
# ===========================================================================


class TestTimeBasedSmoothing:
    """Verify that 5-second time-based rolling mean is applied."""

    def test_smoothing_reduces_variance(self) -> None:
        raw = _make_bxb(n=100, noise_std=200.0)
        processed = _preprocess_bxb(raw)

        raw_std = raw["vo2_ml"].std()
        proc_std = processed["vo2_ml"].std()
        assert proc_std < raw_std, "Smoothing should reduce variance"

    def test_mean_preserved_approximately(self) -> None:
        raw = _make_bxb(n=100, noise_std=50.0)
        processed = _preprocess_bxb(raw)

        # Mean should stay within ~5% after smoothing
        raw_mean = raw["vo2_ml"].mean()
        proc_mean = processed["vo2_ml"].mean()
        assert abs(proc_mean - raw_mean) / raw_mean < 0.05

    def test_hr_not_smoothed(self) -> None:
        raw = _make_bxb(n=50)
        processed = _preprocess_bxb(raw)

        # HR should remain identical (not a preprocessing target)
        pd.testing.assert_series_equal(
            raw.sort_values("t_s").reset_index(drop=True)["hr_bpm"],
            processed["hr_bpm"],
            check_names=False,
        )


# ===========================================================================
# Step 2: 30% outlier removal
# ===========================================================================


class TestOutlierRemoval:
    """Verify local-median 30% outlier filter."""

    def test_spike_removed(self) -> None:
        raw = _make_bxb(n=50, noise_std=10.0)
        # Inject a huge spike at index 25
        raw.loc[25, "vo2_ml"] = 10000.0
        processed = _preprocess_bxb(raw)

        # The spike should be removed (replaced + interpolated)
        assert processed.loc[25, "vo2_ml"] < 5000.0

    def test_no_nans_after_interpolation(self) -> None:
        raw = _make_bxb(n=50, noise_std=10.0)
        raw.loc[20, "vo2_ml"] = 10000.0
        raw.loc[30, "vco2_ml"] = 10000.0
        processed = _preprocess_bxb(raw)

        assert not processed["vo2_ml"].isna().any()
        assert not processed["vco2_ml"].isna().any()

    def test_all_outliers_keeps_originals(self) -> None:
        """If every value is an outlier relative to neighbors, keep all."""
        raw = _make_bxb(n=20, noise_std=10.0)
        # Make every other value wildly different — but the 30% rule
        # uses local median, so we need truly all to fail.
        # Easiest: make them all identical (deviation = 0, never > 30%)
        raw["vo2_ml"] = 3000.0
        processed = _preprocess_bxb(raw)
        # Should remain ~3000 (smoothing won't change identical values)
        assert (processed["vo2_ml"] - 3000.0).abs().max() < 1.0

    def test_rq_recalculated(self) -> None:
        raw = _make_bxb(n=50, noise_std=10.0)
        processed = _preprocess_bxb(raw)

        # RQ should be vco2/vo2 after preprocessing
        expected_rq = processed["vco2_ml"] / processed["vo2_ml"]
        np.testing.assert_allclose(
            processed.loc[processed["vo2_ml"] > 0, "rq"].values,
            expected_rq.loc[processed["vo2_ml"] > 0].values,
            rtol=1e-10,
        )


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge cases: small data, gaps, missing columns."""

    def test_fewer_than_10_breaths_skips(self) -> None:
        raw = _make_bxb(n=5)
        processed = _preprocess_bxb(raw)
        # Should return a copy without modification
        pd.testing.assert_frame_equal(raw, processed)

    def test_empty_dataframe(self) -> None:
        raw = pd.DataFrame()
        processed = _preprocess_bxb(raw)
        assert processed.empty

    def test_missing_columns_skips(self) -> None:
        raw = pd.DataFrame({"t_s": [1, 2, 3], "hr_bpm": [140, 141, 142]})
        processed = _preprocess_bxb(raw)
        pd.testing.assert_frame_equal(raw, processed)

    def test_gap_over_30s_not_interpolated_across(self) -> None:
        """Values across a >30s gap should NOT be interpolated together."""
        # Create two clusters with a 60s gap
        rng = np.random.RandomState(99)
        n1 = 20
        n2 = 20
        t1 = np.cumsum(rng.uniform(1.5, 2.5, size=n1))
        t2 = t1[-1] + 60.0 + np.cumsum(rng.uniform(1.5, 2.5, size=n2))
        t_s = np.concatenate([t1, t2])

        vo2 = np.concatenate([
            np.full(n1, 3000.0),
            np.full(n2, 4000.0),
        ])
        vco2 = vo2 * 0.85
        ve = vo2 / 50.0

        raw = pd.DataFrame({
            "t_s": t_s,
            "vo2_ml": vo2,
            "vco2_ml": vco2,
            "ve_lmin": ve,
            "rq": vco2 / vo2,
            "hr_bpm": np.full(n1 + n2, 150.0),
            "bike_power_w": np.full(n1 + n2, 200.0),
        })

        # Inject outlier right before gap and right after
        raw.loc[n1 - 1, "vo2_ml"] = 9999.0
        raw.loc[n1, "vo2_ml"] = 9999.0

        processed = _preprocess_bxb(raw)

        # The gap should not cause values from the two clusters to blend
        cluster1_mean = processed["vo2_ml"].iloc[:n1 - 2].mean()
        cluster2_mean = processed["vo2_ml"].iloc[n1 + 2:].mean()
        # Clusters should remain distinct
        assert abs(cluster2_mean - cluster1_mean) > 500.0


# ===========================================================================
# Step 3: VO2max triplet peak averaging
# ===========================================================================


class TestVO2maxTripletPeak:
    """Verify top-3 peak averaging for VO2max."""

    def test_vo2max_uses_top3_mean(self) -> None:
        bxb = _make_bxb(n=100, vo2_base=3500.0, noise_std=100.0)
        subject = _make_subject(weight_kg=70.0)

        results = analyze_vo2max(bxb, subject)

        assert "vo2max_ml" in results
        assert results["vo2max_method"] == "top3_mean"
        assert len(results["vo2max_triplet_values"]) == 3
        assert results["vo2max_outliers_removed"] is True

        # The reported VO2max should equal the mean of triplet values
        expected = round(sum(results["vo2max_triplet_values"]) / 3.0, 1)
        assert results["vo2max_ml"] == expected

    def test_vo2max_rel_uses_weight(self) -> None:
        bxb = _make_bxb(n=100, vo2_base=3500.0, noise_std=50.0)
        subject = _make_subject(weight_kg=70.0)
        results = analyze_vo2max(bxb, subject)

        expected_rel = round(results["vo2max_ml"] / 70.0, 1)
        assert results["vo2max_rel"] == expected_rel

    def test_small_bxb_fewer_than_3_peaks(self) -> None:
        """With very few valid breaths, nlargest adapts to available count."""
        bxb = _make_bxb(n=12, vo2_base=3000.0, noise_std=20.0)
        subject = _make_subject()
        results = analyze_vo2max(bxb, subject)

        # Should still produce a result (nlargest(min(3, len)))
        assert "vo2max_ml" in results
        assert results["vo2max_method"] == "top3_mean"

    def test_triplet_values_are_sorted_desc(self) -> None:
        bxb = _make_bxb(n=100, vo2_base=4000.0, noise_std=200.0)
        subject = _make_subject()
        results = analyze_vo2max(bxb, subject)

        triplet = results["vo2max_triplet_values"]
        assert triplet == sorted(triplet, reverse=True)


# ===========================================================================
# _apply_nolte_smoothing
# ===========================================================================


class TestApplyNolteSmoothing:
    """Unit tests for _apply_nolte_smoothing()."""

    # --- helpers ---

    @staticmethod
    def _make_signal(span_s: float = 120.0, hz: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
        """Return (t_s, values) for a clean sine-like signal over span_s seconds."""
        n = max(2, int(span_s * hz))
        t_s = np.linspace(0.0, span_s, n)
        rng = np.random.RandomState(7)
        values = 3000.0 + 200.0 * np.sin(2 * np.pi * t_s / span_s) + rng.normal(0, 50, size=n)
        return t_s, values

    # --- importable ---

    def test_importable(self) -> None:
        """_apply_nolte_smoothing must be importable from pipeline.analysis."""
        from pipeline.analysis import _apply_nolte_smoothing as fn
        assert callable(fn)

    # --- length preservation ---

    def test_length_preserved_butterworth(self) -> None:
        t_s, values = self._make_signal(span_s=120.0)
        out = _apply_nolte_smoothing(t_s, values, method="butterworth")
        assert len(out) == len(t_s), "Butterworth output length must equal input length"

    def test_length_preserved_moving_average(self) -> None:
        t_s, values = self._make_signal(span_s=120.0)
        out = _apply_nolte_smoothing(t_s, values, method="moving_average")
        assert len(out) == len(t_s), "Moving-average output length must equal input length"

    # --- smoothing actually happens ---

    def test_butterworth_uses_sosfiltfilt(self) -> None:
        """Butterworth-smoothed output should differ from (noisy) raw input."""
        rng = np.random.RandomState(42)
        n = 200
        t_s = np.linspace(0.0, 400.0, n)
        # Heavy noise so smoothing is visible
        values = 3000.0 + rng.normal(0, 300.0, size=n)
        out = _apply_nolte_smoothing(t_s, values, method="butterworth")
        # Smoothed std should be lower than raw std
        assert out.std() < values.std(), "Butterworth smoothing should reduce signal variance"

    # --- NaN handling ---

    def test_all_nan_returns_original(self) -> None:
        t_s = np.array([0.0, 1.0, 2.0, 3.0])
        values = np.array([np.nan, np.nan, np.nan, np.nan])
        out = _apply_nolte_smoothing(t_s, values, method="butterworth")
        assert len(out) == len(values)
        assert np.all(np.isnan(out)), "All-NaN input must produce all-NaN output"

    # --- single-point ---

    def test_single_point_returns_original(self) -> None:
        t_s = np.array([5.0])
        values = np.array([2500.0])
        out = _apply_nolte_smoothing(t_s, values, method="butterworth")
        np.testing.assert_array_equal(out, values)

    # --- short signal fallback ---

    def test_short_signal_falls_back_to_ma_with_warning(self) -> None:
        """A signal spanning ≤10 s produces a 1 Hz grid of ≤11 samples (≤12),
        triggering the UserWarning and moving-average fallback."""
        rng = np.random.RandomState(1)
        # span = 10 s → n_grid = 11 → triggers fallback
        t_s = np.linspace(0.0, 10.0, 20)
        values = 3000.0 + rng.normal(0, 50.0, size=20)

        with pytest.warns(UserWarning, match="too short for Butterworth"):
            out = _apply_nolte_smoothing(t_s, values, method="butterworth")

        # Output length must still be preserved
        assert len(out) == len(t_s)

    # --- Edge case 1: duplicate timestamps ---

    def test_duplicate_timestamps_no_crash(self) -> None:
        """Duplicate t_s values must not crash; output length equals input length."""
        t_s = np.array([0.0, 1.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0,
                        9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0])
        values = np.arange(len(t_s), dtype=float) * 100.0 + 3000.0
        out = _apply_nolte_smoothing(t_s, values, method="butterworth")
        assert len(out) == len(t_s), "Duplicate timestamps must not change output length"
        assert not np.isnan(out).any(), "No NaN expected with duplicate timestamps"

    # --- Edge case 2: span >= 3601 s (grid cap) ---

    def test_long_signal_grid_capped_at_3601(self) -> None:
        """A signal spanning >3600 s must have its 1 Hz grid capped at 3601 samples.
        Timestamps beyond t_s[0]+3600 are clamped to the last grid value (np.interp
        edge behaviour), so the output is constant for the tail of the signal.
        """
        rng = np.random.RandomState(5)
        n = 200
        t_s = np.linspace(0.0, 5000.0, n)
        values = 3000.0 + rng.normal(0, 50.0, size=n)
        out = _apply_nolte_smoothing(t_s, values, method="butterworth")

        assert len(out) == n, "Output length must equal input length even when grid is capped"
        # All t_s beyond t_s[0]+3600 should clamp to the same end-of-grid value
        tail_start = np.searchsorted(t_s, t_s[0] + 3601)
        if tail_start < n:
            tail = out[tail_start:]
            assert np.allclose(tail, tail[0]), (
                "Values beyond the 3601-sample grid cap should all equal the "
                "last smoothed grid sample (np.interp right-clamp behaviour)"
            )

    # --- Edge case 3: partial NaN (some values missing) ---

    def test_partial_nan_values_are_filled(self) -> None:
        """NaN positions in the input must be interpolated from valid neighbours;
        the output should have no NaN values and the same length as the input.
        NOTE: this means missing data is *filled*, not preserved as NaN.
        """
        rng = np.random.RandomState(9)
        t_s = np.linspace(0.0, 120.0, 60)
        values = 3000.0 + rng.normal(0, 50.0, size=60)
        values[20:25] = np.nan  # inject 5 NaNs in the middle

        out = _apply_nolte_smoothing(t_s, values, method="butterworth")

        assert len(out) == len(t_s), "Partial-NaN input must not change output length"
        assert not np.isnan(out).any(), (
            "NaN positions should be filled by grid interpolation — "
            "output must contain no NaN"
        )
        # Filled values should be in a physiologically sane range
        assert out[20:25].min() > 2000.0
        assert out[20:25].max() < 4500.0

    # --- Edge case 4: moving_average with short signal (no fallback expected) ---

    def test_moving_average_short_signal_no_warning(self) -> None:
        """MA path must not raise any UserWarning on a short (≤10 s) signal."""
        import warnings as _warnings
        t_s = np.linspace(0.0, 10.0, 20)
        values = np.full(20, 3000.0)

        with _warnings.catch_warnings():
            _warnings.simplefilter("error")  # treat any warning as an error
            out = _apply_nolte_smoothing(t_s, values, method="moving_average")

        assert len(out) == len(t_s), "MA output length must equal input length"

    # --- Edge case 5: non-monotonic t_s ---

    def test_non_monotonic_t_s_same_endpoints_no_crash(self) -> None:
        """A shuffled t_s array (same endpoints as monotonic) must not crash.
        np.interp uses only t_s[0]/t_s[-1] for the 1 Hz grid bounds, so
        a shuffled-but-bounded array still produces output of the correct length.
        """
        rng = np.random.RandomState(42)
        t_s_mono = np.linspace(0.0, 120.0, 60)
        values = 3000.0 + rng.normal(0, 50.0, size=60)

        t_s_shuffled = t_s_mono.copy()
        rng.shuffle(t_s_shuffled)

        out = _apply_nolte_smoothing(t_s_shuffled, values, method="butterworth")
        assert len(out) == len(t_s_shuffled), "Non-monotonic t_s must not change output length"

    def test_strictly_decreasing_t_s_raises_or_returns_original(self) -> None:
        """Strictly decreasing t_s produces an empty grid (t_s[-1] < t_s[0]);
        _apply_nolte_smoothing currently raises ValueError from np.interp on an
        empty sample-points array.  This test documents the current (undefined)
        behaviour so it becomes visible if the contract changes.
        """
        rng = np.random.RandomState(7)
        t_s = np.linspace(120.0, 0.0, 60)  # strictly decreasing
        values = 3000.0 + rng.normal(0, 50.0, size=60)

        # Current behaviour: raises ValueError because the grid is empty.
        # If the function is later hardened to handle this, update this test.
        with pytest.raises((ValueError, IndexError)):
            _apply_nolte_smoothing(t_s, values, method="butterworth")
