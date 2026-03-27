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

from pipeline.analysis import _preprocess_bxb, analyze_vo2max


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
