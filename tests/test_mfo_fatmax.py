"""
tests/test_mfo_fatmax.py — E2E tests for MFO/FatMax detection redesign (#2861–#2864).

Covers the complete redesign across four phases:
  #2861 — crossover hard cap (zone_max ≤ crossover_power)
  #2862 — PCHIP smooth curve argmax (FatMax ≠ noise spike)
  #2863 — plateau-aware gradient-based zone (_find_fatmax_zone)
  #2864 — precise Frayn 1983 coefficients (1.6946 / 1.7012)
"""

import numpy as np
import pandas as pd
import pytest

from pipeline.analysis import (
    _build_power_domain_substrate,
    _ensure_substrate_columns,
    analyze_substrate,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _plateau_bxb(
    peak_power: float = 145.0,
    crossover_power: float = 190.0,
    n_samples_per_bin: int = 5,
) -> pd.DataFrame:
    """Plateau-type fat curve (박용두형): wide high-fat plateau, sharp right drop.

    Fat stays ~1.3 g/min from 80–190W then drops steeply.
    CHO crosses fat near crossover_power.
    """
    rng = np.random.default_rng(0)
    rows = []
    for p in range(70, 251, 5):
        # Fat: plateau from 80–190W, falls steeply after
        if p <= 190:
            fat_base = 0.9 + 0.4 * float(np.exp(-(((p - peak_power) / 80.0) ** 2)))
        else:
            fat_base = max(0.05, 1.2 * float(np.exp(-(((p - 190.0) / 25.0) ** 2))))
        # CHO: rises monotonically, crosses fat near crossover_power
        cho_base = 0.1 + (p - 70) * 0.008
        for _ in range(n_samples_per_bin):
            rows.append({
                "bike_power_w": float(p),
                "fat_gmin": max(0.0, fat_base + float(rng.normal(0, 0.04))),
                "cho_gmin": max(0.0, cho_base + float(rng.normal(0, 0.03))),
                "hr_bpm": 90.0 + (p - 70) * 0.7,
                "vo2_kg": 12.0 + (p - 70) * 0.1,
                "t_s": float(p),
                "phase": "active",
            })
    return pd.DataFrame(rows)


def _parabolic_bxb(
    peak_power: float = 180.0,
    n_samples_per_bin: int = 5,
) -> pd.DataFrame:
    """Classic parabolic fat curve: sharp bell centred at peak_power."""
    rng = np.random.default_rng(1)
    rows = []
    for p in range(80, 301, 5):
        fat_base = 2.0 * float(np.exp(-(((p - peak_power) / 50.0) ** 2))) + 0.1
        cho_base = 0.5 + (p - 80) * 0.012
        for _ in range(n_samples_per_bin):
            rows.append({
                "bike_power_w": float(p),
                "fat_gmin": max(0.0, fat_base + float(rng.normal(0, 0.05))),
                "cho_gmin": max(0.0, cho_base + float(rng.normal(0, 0.03))),
                "hr_bpm": 100.0 + (p - 80) * 0.45,
                "vo2_kg": 14.0 + (p - 80) * 0.09,
                "t_s": float(p),
                "phase": "active",
            })
    return pd.DataFrame(rows)


def _no_crossover_bxb(n_samples_per_bin: int = 5) -> pd.DataFrame:
    """Fat always exceeds CHO — no crossover anywhere in the measurement range.

    Fat is anchored at 2.0+ g/min throughout; CHO is kept below 0.8 g/min max
    so fat > CHO at every power bin.
    """
    rng = np.random.default_rng(2)
    rows = []
    for p in range(80, 221, 5):
        # Fat: bell centred at 150W but floor keeps fat >> CHO
        fat_base = 2.0 * float(np.exp(-(((p - 150.0) / 60.0) ** 2))) + 1.5
        # CHO: rises only to ~0.7 g/min at 220W — always below fat
        cho_base = 0.1 + (p - 80) * 0.004
        for _ in range(n_samples_per_bin):
            rows.append({
                "bike_power_w": float(p),
                "fat_gmin": max(0.0, fat_base + float(rng.normal(0, 0.04))),
                "cho_gmin": max(0.0, cho_base + float(rng.normal(0, 0.02))),
                "hr_bpm": 100.0 + (p - 80) * 0.5,
                "vo2_kg": 14.0 + (p - 80) * 0.1,
                "t_s": float(p),
                "phase": "active",
            })
    return pd.DataFrame(rows)


def _short_bxb(n_bins: int = 3) -> pd.DataFrame:
    """< 4 distinct power bins — PCHIP cannot interpolate, uses raw fallback."""
    rows = []
    for i, p in enumerate([100.0, 150.0, 200.0][:n_bins]):
        for _ in range(4):
            rows.append({
                "bike_power_w": p,
                "fat_gmin": 1.2 - i * 0.2,
                "cho_gmin": 0.5 + i * 0.3,
                "hr_bpm": 120.0 + i * 20.0,
                "vo2_kg": 20.0 + i * 5.0,
                "t_s": float(p),
                "phase": "active",
            })
    return pd.DataFrame(rows)


def _noise_spike_bxb(
    true_peak: float = 145.0,
    spike_power: float = 80.0,
    n_samples: int = 7,
) -> pd.DataFrame:
    """Parabolic fat curve with a noisy spike at low power.

    Raw argmax would snap to the spike; PCHIP curve argmax should find true_peak.
    """
    rng = np.random.default_rng(3)
    rows = []
    for p in range(70, 261, 5):
        fat_base = 2.0 * float(np.exp(-(((p - true_peak) / 45.0) ** 2))) + 0.15
        cho_base = 0.3 + (p - 70) * 0.009
        count = n_samples
        if abs(p - spike_power) < 3:
            # Spike at low power: ONE row with very high fat, rest normal
            rows.append({
                "bike_power_w": float(p),
                "fat_gmin": fat_base + 3.0,  # single spike
                "cho_gmin": cho_base,
                "hr_bpm": 90.0,
                "vo2_kg": 15.0,
                "t_s": float(p),
                "phase": "active",
            })
            count -= 1
        for _ in range(count):
            rows.append({
                "bike_power_w": float(p),
                "fat_gmin": max(0.0, fat_base + float(rng.normal(0, 0.05))),
                "cho_gmin": max(0.0, cho_base + float(rng.normal(0, 0.02))),
                "hr_bpm": 90.0 + (p - 70) * 0.55,
                "vo2_kg": 12.0 + (p - 70) * 0.09,
                "t_s": float(p),
                "phase": "active",
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Crossover hard cap (Phase 1 — #2861)
# ---------------------------------------------------------------------------


class TestCrossoverHardCapE2E:
    """zone_max ≤ crossover_power in full pipeline context."""

    def test_plateau_zone_does_not_exceed_crossover(self) -> None:
        """Plateau-type curve: zone_max must stay ≤ crossover point."""
        bxb = _plateau_bxb()
        result = _build_power_domain_substrate(bxb)
        markers = result["metabolism_markers"]
        cx = markers.get("primary_crossover")
        if cx is None:
            pytest.skip("no crossover detected in this fixture")
        assert markers["fatmax_zone_max_w"] <= cx["power_w"] + 0.2, (
            f"zone_max {markers['fatmax_zone_max_w']} exceeds crossover {cx['power_w']}"
        )

    def test_parabolic_zone_does_not_exceed_crossover(self) -> None:
        """Parabolic curve: zone_max must stay ≤ crossover point."""
        bxb = _parabolic_bxb()
        result = _build_power_domain_substrate(bxb)
        markers = result["metabolism_markers"]
        cx = markers.get("primary_crossover")
        if cx is None:
            pytest.skip("no crossover detected in this fixture")
        assert markers["fatmax_zone_max_w"] <= cx["power_w"] + 0.2


# ---------------------------------------------------------------------------
# 2. PCHIP argmax — FatMax from smooth curve (Phase 2 — #2862)
# ---------------------------------------------------------------------------


class TestPchipArgmaxE2E:
    """FatMax point derived from PCHIP smooth curve, not raw row argmax."""

    def test_noise_spike_does_not_shift_fatmax(self) -> None:
        """A single high-fat outlier row at low power must not become FatMax."""
        true_peak = 145.0
        spike_power = 80.0
        bxb = _noise_spike_bxb(true_peak=true_peak, spike_power=spike_power)
        result = _build_power_domain_substrate(bxb)
        markers = result["metabolism_markers"]
        # PCHIP bin-median smoothing should resolve to true_peak, not spike_power
        assert markers["fatmax_power_w"] > spike_power + 30.0, (
            f"FatMax {markers['fatmax_power_w']} W too close to spike at {spike_power} W"
        )
        assert markers["fatmax_power_w"] == pytest.approx(true_peak, abs=20.0), (
            f"FatMax {markers['fatmax_power_w']} W should be near true peak {true_peak} W"
        )

    def test_smooth_peak_is_within_zone(self) -> None:
        """FatMax point must lie inside its own zone."""
        bxb = _parabolic_bxb(peak_power=180.0)
        result = _build_power_domain_substrate(bxb)
        markers = result["metabolism_markers"]
        assert markers["fatmax_zone_min_w"] <= markers["fatmax_power_w"] <= markers["fatmax_zone_max_w"], (
            f"FatMax {markers['fatmax_power_w']} outside zone "
            f"[{markers['fatmax_zone_min_w']}, {markers['fatmax_zone_max_w']}]"
        )


# ---------------------------------------------------------------------------
# 3. Plateau-type subject (Phase 3 — #2863)
# ---------------------------------------------------------------------------


class TestPlateauSubjectE2E:
    """Trained cyclist with wide fat plateau: zone ≤ 80W, FatMax in physiological range."""

    def test_zone_width_at_most_80w(self) -> None:
        """Plateau subject: gradient-based zone must not exceed 80W."""
        bxb = _plateau_bxb()
        result = _build_power_domain_substrate(bxb)
        markers = result["metabolism_markers"]
        width = markers["fatmax_zone_max_w"] - markers["fatmax_zone_min_w"]
        assert width <= 80.0 + 0.5, (
            f"zone width {width:.1f} W exceeds 80 W limit for plateau subject"
        )

    def test_fatmax_not_at_low_noise_spike(self) -> None:
        """Plateau subject: FatMax must not land at low-power noise spike."""
        bxb = _plateau_bxb(peak_power=145.0)
        result = _build_power_domain_substrate(bxb)
        markers = result["metabolism_markers"]
        assert markers["fatmax_power_w"] >= 100.0, (
            f"FatMax {markers['fatmax_power_w']} W too low for plateau-type subject"
        )

    def test_zone_min_above_data_start(self) -> None:
        """Zone minimum must be ≥ first data point (no underflow)."""
        bxb = _plateau_bxb()
        result = _build_power_domain_substrate(bxb)
        markers = result["metabolism_markers"]
        assert markers["fatmax_zone_min_w"] >= 65.0, (
            f"zone_min {markers['fatmax_zone_min_w']} below expected data start"
        )


# ---------------------------------------------------------------------------
# 4. Parabolic subject — regression check (Phase 3 — #2863)
# ---------------------------------------------------------------------------


class TestParabolicRegressionE2E:
    """Classic bell-curve fat profile: new algorithm should not regress FatMax location."""

    def test_fatmax_near_true_peak(self) -> None:
        """Parabolic fat curve: FatMax must be within ±20 W of true peak."""
        true_peak = 180.0
        bxb = _parabolic_bxb(peak_power=true_peak)
        result = _build_power_domain_substrate(bxb)
        markers = result["metabolism_markers"]
        assert markers["fatmax_power_w"] == pytest.approx(true_peak, abs=20.0), (
            f"FatMax regression: expected ~{true_peak} W, got {markers['fatmax_power_w']} W"
        )

    def test_zone_brackets_fatmax(self) -> None:
        """Zone min ≤ FatMax ≤ zone max for parabolic subject."""
        bxb = _parabolic_bxb()
        result = _build_power_domain_substrate(bxb)
        markers = result["metabolism_markers"]
        assert markers["fatmax_zone_min_w"] <= markers["fatmax_power_w"]
        assert markers["fatmax_power_w"] <= markers["fatmax_zone_max_w"]


# ---------------------------------------------------------------------------
# 5. No-crossover subject (Phase 1+3 — #2861 + #2863)
# ---------------------------------------------------------------------------


class TestNoCrossoverSubjectE2E:
    """Fat always > CHO — gradient-based zone still works, no exception raised."""

    def test_no_error_when_no_crossover(self) -> None:
        """Pipeline must not raise when fat never crosses CHO."""
        bxb = _no_crossover_bxb()
        result = _build_power_domain_substrate(bxb)
        assert "metabolism_markers" in result
        markers = result["metabolism_markers"]
        assert markers.get("primary_crossover") is None

    def test_zone_width_bounded_without_crossover(self) -> None:
        """Without crossover cap, gradient zone + 80W max must still bound the zone."""
        bxb = _no_crossover_bxb()
        result = _build_power_domain_substrate(bxb)
        markers = result["metabolism_markers"]
        width = markers["fatmax_zone_max_w"] - markers["fatmax_zone_min_w"]
        assert width <= 80.0 + 0.5, (
            f"zone width {width:.1f} W exceeds 80 W without crossover constraint"
        )

    def test_zone_is_valid_interval(self) -> None:
        """zone_min < zone_max always (collapse fallback applied if needed)."""
        bxb = _no_crossover_bxb()
        result = _build_power_domain_substrate(bxb)
        markers = result["metabolism_markers"]
        assert markers["fatmax_zone_min_w"] < markers["fatmax_zone_max_w"]


# ---------------------------------------------------------------------------
# 6. Sparse data — < 4 distinct bins (fallback path)
# ---------------------------------------------------------------------------


class TestSparseDataFallbackE2E:
    """< 4 bins: PCHIP skipped, raw fallback must still produce valid zone."""

    def test_short_data_no_exception(self) -> None:
        """Pipeline must not raise with only 3 distinct power bins."""
        bxb = _short_bxb(n_bins=3)
        try:
            result = _build_power_domain_substrate(bxb)
        except Exception as exc:
            pytest.fail(f"Pipeline raised with sparse data: {exc}")
        # Either returns valid markers or empty dict — not an exception
        if result and "metabolism_markers" in result:
            markers = result["metabolism_markers"]
            assert markers["fatmax_zone_min_w"] < markers["fatmax_zone_max_w"]

    def test_short_data_zone_minimum_width(self) -> None:
        """If markers are produced for sparse data, zone must be ≥ 10 W wide."""
        bxb = _short_bxb(n_bins=3)
        result = _build_power_domain_substrate(bxb)
        if not result or "metabolism_markers" not in result:
            pytest.skip("sparse data returns no markers — expected")
        markers = result["metabolism_markers"]
        width = markers["fatmax_zone_max_w"] - markers["fatmax_zone_min_w"]
        assert width >= 9.9, f"zone width {width:.1f} W below 10 W minimum"


# ---------------------------------------------------------------------------
# 7. Frayn 1983 precise coefficients (Phase 4 — #2864)
# ---------------------------------------------------------------------------


class TestFraynCoefficientsE2E:
    """Derived fat/CHO values reflect Frayn 1983 / Jeukendrup & Wallis 2005 precise values."""

    def test_fat_coefficient_1_6946(self) -> None:
        """fat = 1.6946 * VO2(L) - 1.7012 * VCO2(L)."""
        # RER = 0.80 (pure fat burn zone): VO2=2.0 L/min, VCO2=1.6 L/min
        vo2_l, vco2_l = 2.0, 1.6
        expected_fat = 1.6946 * vo2_l - 1.7012 * vco2_l
        bxb = pd.DataFrame({
            "t_s": [60.0, 120.0, 180.0, 240.0],
            "vo2_ml": [vo2_l * 1000] * 4,
            "vco2_ml": [vco2_l * 1000] * 4,
            "hr_bpm": [130.0] * 4,
            "bike_power_w": [150.0] * 4,
            "phase": ["active"] * 4,
        })
        result = _ensure_substrate_columns(bxb)
        actual_fat = result["fat_gmin"].dropna().mean()
        assert actual_fat == pytest.approx(expected_fat, abs=0.001), (
            f"fat_gmin {actual_fat:.4f} doesn't match Frayn 1.6946 formula: {expected_fat:.4f}"
        )

    def test_cho_coefficient_4_5503(self) -> None:
        """cho = 4.5503 * VCO2(L) - 3.2254 * VO2(L)."""
        vo2_l, vco2_l = 2.0, 1.6
        expected_cho = max(0.0, 4.5503 * vco2_l - 3.2254 * vo2_l)
        bxb = pd.DataFrame({
            "t_s": [60.0, 120.0, 180.0, 240.0],
            "vo2_ml": [vo2_l * 1000] * 4,
            "vco2_ml": [vco2_l * 1000] * 4,
            "hr_bpm": [130.0] * 4,
            "bike_power_w": [150.0] * 4,
            "phase": ["active"] * 4,
        })
        result = _ensure_substrate_columns(bxb)
        actual_cho = result["cho_gmin"].dropna().mean()
        assert actual_cho == pytest.approx(expected_cho, abs=0.001), (
            f"cho_gmin {actual_cho:.4f} doesn't match Frayn 4.5503 formula: {expected_cho:.4f}"
        )

    def test_not_using_old_1_67_coefficient(self) -> None:
        """Verify old simplified 1.67 coefficient is not in use."""
        # RER = 0.75: fat should differ between 1.67 and 1.6946 implementations
        vo2_l, vco2_l = 2.0, 1.5
        old_fat = 1.67 * vo2_l - 1.67 * vco2_l          # old simplified
        precise_fat = 1.6946 * vo2_l - 1.7012 * vco2_l  # precise
        bxb = pd.DataFrame({
            "t_s": [60.0, 120.0, 180.0, 240.0],
            "vo2_ml": [vo2_l * 1000] * 4,
            "vco2_ml": [vco2_l * 1000] * 4,
            "hr_bpm": [130.0] * 4,
            "bike_power_w": [140.0] * 4,
            "phase": ["active"] * 4,
        })
        result = _ensure_substrate_columns(bxb)
        actual_fat = result["fat_gmin"].dropna().mean()
        assert abs(actual_fat - precise_fat) < abs(actual_fat - old_fat), (
            f"fat_gmin={actual_fat:.4f} is closer to old 1.67 ({old_fat:.4f}) "
            f"than precise 1.6946 ({precise_fat:.4f})"
        )
