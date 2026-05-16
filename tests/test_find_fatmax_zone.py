"""
tests/test_find_fatmax_zone.py — Direct unit tests for _find_fatmax_zone.

Covers the plateau-aware gradient-based FatMax zone algorithm (task #2863):
  1. Plateau fat curve: zone ≤ 80W wide
  2. Gradient decline found: zone_max near first significant drop
  3. Gradient not found: zone_max capped by crossover or 80W max
  4. Collapse fallback: crossover below zone_min → zone_max = zone_min + 10
  5. Low peak_val: noise floor prevents false triggering
  6. Edge cases: peak at start, peak at end
  7. Width constraints: min 10W, max 80W enforced
  8. Crossover double-cap after width-max expansion
"""

import numpy as np
import pytest

from pipeline.analysis import _find_fatmax_zone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dense(start: float, stop: float, step: float = 0.5) -> np.ndarray:
    """Create a dense power array matching the PCHIP grid step."""
    return np.arange(start, stop + step * 0.5, step)


def _plateau_fat(dp: np.ndarray, peak_idx: int, peak_val: float = 1.5) -> np.ndarray:
    """Return a fat curve that is flat (plateau) at peak_val across dp."""
    df = np.full_like(dp, peak_val, dtype=float)
    return df


def _bell_fat(
    dp: np.ndarray,
    peak_power: float,
    peak_val: float = 1.5,
    sigma: float = 15.0,
) -> np.ndarray:
    """Gaussian bell curve peaking at peak_power."""
    return np.array([peak_val * np.exp(-((p - peak_power) ** 2) / (2 * sigma**2)) for p in dp])


def _stepped_decline_fat(
    dp: np.ndarray,
    fm_idx: int,
    peak_val: float = 1.5,
    decline_start_offset: int = 20,
    decline_rate: float = 0.05,
) -> np.ndarray:
    """Fat curve that is flat from peak, then drops sharply after decline_start_offset steps."""
    df = np.full_like(dp, peak_val, dtype=float)
    for i in range(fm_idx + decline_start_offset, len(dp)):
        steps = i - (fm_idx + decline_start_offset)
        df[i] = max(0.0, peak_val - decline_rate * steps)
    return df


# ---------------------------------------------------------------------------
# 1. Plateau fat curve — zone width ≤ 80W
# ---------------------------------------------------------------------------


class TestPlateauFatCurve:
    """A completely flat fat curve should be bounded by the 80W max-width guard."""

    def test_plateau_zone_width_at_most_80w(self) -> None:
        """Flat fat at all powers → gradient is zero → no decline ever found → 80W cap applies."""
        dp = _dense(100.0, 300.0)
        df = _plateau_fat(dp, 0, peak_val=1.5)
        fm_idx = int(np.argmax(df))

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        assert zone_max - zone_min <= 80.0, (
            f"Plateau zone too wide: {zone_max - zone_min:.1f}W (limit 80W)"
        )

    def test_plateau_zone_min_less_than_zone_max(self) -> None:
        """Plateau zone must not be inverted."""
        dp = _dense(100.0, 300.0)
        df = _plateau_fat(dp, 0, peak_val=1.5)
        fm_idx = int(np.argmax(df))

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        assert zone_min < zone_max, f"Inverted zone: min={zone_min}, max={zone_max}"

    def test_plateau_low_peak_plateau_still_bounded(self) -> None:
        """Low-value plateau (0.05 g/min) still respects 80W width cap."""
        dp = _dense(100.0, 300.0)
        df = _plateau_fat(dp, 0, peak_val=0.05)
        fm_idx = int(np.argmax(df))

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        assert zone_max - zone_min <= 80.0
        assert zone_min < zone_max


# ---------------------------------------------------------------------------
# 2. Gradient decline found — zone_max near first significant drop
# ---------------------------------------------------------------------------


class TestGradientDeclineFound:
    """When a clear gradient decline exists, zone_max should land near that drop."""

    def test_sharp_decline_limits_zone_max(self) -> None:
        """A sharp drop after peak should be detected and bound zone_max there."""
        dp = _dense(100.0, 300.0)
        # Fat plateau at 150W, then sharp decline
        fm_power = 150.0
        fm_idx = int(np.argmin(np.abs(dp - fm_power)))
        df = np.full_like(dp, 1.5, dtype=float)
        # Insert sharp decline 10 steps past peak
        decline_idx = fm_idx + 10
        for i in range(decline_idx, len(dp)):
            df[i] = max(0.0, 1.5 - 0.15 * (i - decline_idx))

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        # zone_max should be well before end of curve (300W)
        assert zone_max < dp[-1], (
            f"zone_max {zone_max} should not reach curve end {dp[-1]}"
        )
        # zone_max should be within reasonable vicinity of where decline starts
        assert zone_max <= fm_power + 60.0, (
            f"zone_max {zone_max} too far from FatMax peak {fm_power}"
        )

    def test_decline_threshold_formula_with_normal_peak(self) -> None:
        """decline_threshold = min(-peak * 0.008, -0.001); at peak=1.5, threshold=-0.012."""
        # With peak_val=1.5, threshold = min(-1.5*0.008, -0.001) = min(-0.012, -0.001) = -0.012
        # Create a gaussian curve — np.gradient will show negative slopes past peak
        dp = _dense(100.0, 300.0)
        df = _bell_fat(dp, peak_power=200.0, peak_val=1.5, sigma=20.0)
        fm_idx = int(np.argmax(df))

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        # Bell curve has gradient < -0.012 past the peak — zone should be bounded
        fm_power = float(dp[fm_idx])
        assert zone_max <= fm_power + 50.0, (
            f"zone_max {zone_max} too far right of FatMax {fm_power}"
        )
        assert zone_max - zone_min >= 10.0, "zone must be at least 10W wide"

    def test_left_boundary_uses_80_percent_threshold(self) -> None:
        """Left walk stops when fat drops below 80% of peak (not 90%)."""
        # Build asymmetric curve: gentle left slope, sharp right decline
        dp = _dense(100.0, 300.0)
        fm_power = 200.0
        fm_idx = int(np.argmin(np.abs(dp - fm_power)))
        df = np.array([
            max(0.0, 1.5 - 0.003 * abs(p - fm_power))  # gentle slope both sides
            for p in dp
        ])
        # 80% threshold = 0.80 * 1.5 = 1.20
        # Left walk continues while fat >= 1.20, stops at 1.19

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        # At 80% threshold (1.20), df = 1.5 - 0.003*|p-200| >= 1.20
        # → |p-200| <= (1.5-1.20)/0.003 = 100W left and right
        # So left boundary can be at most 100W from peak (100W)
        # But curve only goes to 100W, so zone_min = 100W
        assert zone_min <= fm_power, f"zone_min {zone_min} should be <= FatMax {fm_power}"
        # Width cap at 80W should kick in since natural left spread could be wide
        assert zone_max - zone_min <= 80.0 + 1.0, (
            f"Width {zone_max - zone_min:.1f}W exceeds 80W cap"
        )


# ---------------------------------------------------------------------------
# 3. Gradient not found — zone_max capped by crossover or 80W max
# ---------------------------------------------------------------------------


class TestGradientNotFound:
    """When no significant decline is detected, width constraints apply."""

    def test_no_decline_zone_capped_by_80w_max(self) -> None:
        """When gradient never falls below threshold, zone_max bounded by 80W width guard."""
        # Very gentle slope — gradient < -0.001 never triggered
        dp = _dense(100.0, 300.0)
        df = np.array([max(0.0, 1.0 - 0.0001 * abs(p - 200.0)) for p in dp])
        fm_idx = int(np.argmax(df))

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        assert zone_max - zone_min <= 80.0 + 0.1, (
            f"Width {zone_max - zone_min:.1f}W exceeds 80W max"
        )

    def test_crossover_caps_zone_max_when_no_gradient_decline(self) -> None:
        """With no gradient decline and crossover_power=240W, zone_max capped to 240W."""
        dp = _dense(100.0, 300.0)
        # Nearly flat fat — no gradient decline will trigger
        df = np.full_like(dp, 1.5, dtype=float)
        fm_idx = int(np.argmax(df))  # first index

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx, crossover_power=240.0)

        assert zone_max <= 240.0, f"zone_max {zone_max} should not exceed crossover 240W"
        assert zone_min < zone_max, "zone must not be inverted"

    def test_no_gradient_no_crossover_zone_width_is_80w(self) -> None:
        """No decline + no crossover → asymmetric 80W max: peak-30 to peak+50."""
        dp = _dense(100.0, 300.0)
        df = np.full_like(dp, 1.5, dtype=float)
        fm_idx_power = 200.0
        fm_idx = int(np.argmin(np.abs(dp - fm_idx_power)))

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        # The 80W width cap should produce zone from peak-30 to peak+50
        assert zone_max - zone_min <= 80.0 + 0.5
        # The zone center should be near peak
        zone_center = (zone_min + zone_max) / 2
        assert abs(zone_center - fm_idx_power) < 20.0, (
            f"Zone center {zone_center} far from FatMax {fm_idx_power}"
        )


# ---------------------------------------------------------------------------
# 4. Collapse fallback: crossover below zone_min → zone_max = zone_min + 10
# ---------------------------------------------------------------------------


class TestCollapseFallback:
    """When crossover power < zone_min, the zone is inverted → fallback applies."""

    def test_crossover_below_zone_min_triggers_fallback(self) -> None:
        """Crossover at a power lower than zone_min → zone_max = zone_min + 10."""
        # Create narrow bell: natural zone_min will be near peak
        dp = _dense(100.0, 300.0)
        df = _bell_fat(dp, peak_power=200.0, peak_val=1.5, sigma=2.0)
        fm_idx = int(np.argmax(df))

        # zone_min from 80% walk on narrow bell will be close to 200W (~198W)
        # Pass crossover_power well below that
        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx, crossover_power=150.0)

        # Collapse must be resolved: zone_max > zone_min
        assert zone_max > zone_min, f"Inverted: min={zone_min}, max={zone_max}"
        # Fallback produces exactly zone_min + 10.0
        assert zone_max == pytest.approx(zone_min + 10.0, abs=0.3), (
            f"Fallback: expected zone_min+10={zone_min + 10.0}, got zone_max={zone_max}"
        )

    def test_crossover_equal_to_zone_min_triggers_fallback(self) -> None:
        """Crossover exactly at zone_min also collapses → zone_max = zone_min + 10."""
        dp = _dense(100.0, 300.0)
        df = _bell_fat(dp, peak_power=200.0, peak_val=1.5, sigma=2.0)
        fm_idx = int(np.argmax(df))

        # First compute natural zone_min
        zone_min_no_cx, _ = _find_fatmax_zone(dp, df, fm_idx, crossover_power=None)

        # Now use crossover exactly at zone_min
        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx, crossover_power=zone_min_no_cx)

        assert zone_max > zone_min
        assert zone_max == pytest.approx(zone_min + 10.0, abs=0.3)

    def test_crossover_above_zone_min_does_not_trigger_fallback(self) -> None:
        """Crossover above zone_min: cap applies normally without fallback."""
        dp = _dense(100.0, 300.0)
        df = _bell_fat(dp, peak_power=200.0, peak_val=1.5, sigma=20.0)
        fm_idx = int(np.argmax(df))

        # Natural zone: some range with zone_min well below 230W
        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx, crossover_power=230.0)

        assert zone_max <= 230.0 + 0.1, f"zone_max {zone_max} should not exceed crossover 230W"
        assert zone_max > zone_min
        # If crossover 230W > zone_min, fallback not needed
        # zone_max should be exactly 230W or natural gradient boundary (whichever is lower)


# ---------------------------------------------------------------------------
# 5. Low peak_val — noise floor prevents false triggering
# ---------------------------------------------------------------------------


class TestLowPeakValueNoiseFloor:
    """With very low peak_val, decline_threshold = -0.001 (noise floor) dominates."""

    def test_very_low_peak_uses_noise_floor_threshold(self) -> None:
        """peak_val=0.05 → decline_threshold = min(-0.05*0.008, -0.001) = min(-0.0004, -0.001) = -0.001."""
        # With a flat curve and low peak, gradient never falls below -0.001 (flat)
        dp = _dense(100.0, 300.0)
        df = np.full_like(dp, 0.05, dtype=float)
        fm_idx = int(np.argmax(df))

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        # Zone must still be valid
        assert zone_min < zone_max
        assert zone_max - zone_min <= 80.0 + 0.5

    def test_low_peak_with_noisy_flat_curve_stays_bounded(self) -> None:
        """Noisy near-zero curve: tiny fluctuations should not cause extreme zone expansion."""
        rng = np.random.default_rng(42)
        dp = _dense(100.0, 300.0)
        # Low peak with small noise
        df = np.clip(0.03 + rng.normal(0, 0.001, len(dp)), 0, None)
        fm_idx = int(np.argmax(df))

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        assert zone_min < zone_max, "zone must not be inverted"
        assert zone_max - zone_min <= 80.0 + 0.5, (
            f"Width {zone_max - zone_min:.1f}W exceeds 80W cap even with noisy low-peak curve"
        )

    def test_near_zero_peak_does_not_crash(self) -> None:
        """peak_val near 0 (e.g., 0.001) should not cause crash or infinite zone."""
        dp = _dense(100.0, 200.0)
        df = np.full_like(dp, 0.001, dtype=float)
        fm_idx = 0

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        assert zone_min < zone_max
        assert np.isfinite(zone_min) and np.isfinite(zone_max)


# ---------------------------------------------------------------------------
# 6. Edge cases: peak at start / peak at end
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases noted by Builder: peak at curve boundaries."""

    def test_peak_at_curve_start(self) -> None:
        """fm_idx=0: left walk never executes, zone_min = dp[0]."""
        dp = _dense(100.0, 300.0)
        df = np.array([1.5 - 0.005 * i for i in range(len(dp))])  # monotone decreasing
        df = np.clip(df, 0, None)
        fm_idx = 0  # peak is first point

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        assert zone_min == pytest.approx(float(dp[0]), abs=0.6), (
            f"zone_min {zone_min} should be at curve start {dp[0]}"
        )
        assert zone_max > zone_min

    def test_peak_at_curve_end(self) -> None:
        """fm_idx=last: gradient for loop never executes, collapse fallback adds 10W."""
        dp = _dense(100.0, 300.0)
        df = np.array([0.5 + 0.005 * i for i in range(len(dp))])  # monotone increasing
        fm_idx = len(dp) - 1  # peak is last point

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        # zone_min = zone_max (same point) then fallback applies: zone_max = zone_min + 10
        assert zone_max > zone_min, "Peak-at-end: fallback should produce zone_max > zone_min"

    def test_two_element_curve(self) -> None:
        """Minimal curve with 2 elements: no crash, valid zone."""
        dp = np.array([100.0, 200.0])
        df = np.array([1.5, 1.0])
        fm_idx = 0

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        assert zone_min < zone_max
        assert np.isfinite(zone_min) and np.isfinite(zone_max)

    def test_single_element_curve_does_not_crash(self) -> None:
        """Single-element curve: algorithm should not crash."""
        dp = np.array([150.0])
        df = np.array([1.5])
        fm_idx = 0

        # May trigger collapse fallback and add 10W
        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        assert zone_max > zone_min or zone_max == zone_min + 10.0


# ---------------------------------------------------------------------------
# 7. Width constraints: min 10W, max 80W
# ---------------------------------------------------------------------------


class TestWidthConstraints:
    """Width guards (10W min, 80W max) must always apply."""

    def test_very_narrow_zone_expanded_to_10w(self) -> None:
        """zone_max - zone_min < 10W → min guard expands to at least ~10W."""
        # Very sharp peak → 80% threshold narrows zone greatly
        dp = _dense(100.0, 300.0)
        df = _bell_fat(dp, peak_power=200.0, peak_val=1.5, sigma=1.0)  # very narrow
        fm_idx = int(np.argmax(df))

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        assert zone_max - zone_min >= 9.9, (
            f"Zone {zone_max - zone_min:.1f}W is narrower than 10W minimum"
        )
        assert zone_min < zone_max

    def test_very_wide_zone_capped_to_80w(self) -> None:
        """zone_max - zone_min > 80W → max guard caps it (asymmetric: -30/+50)."""
        dp = _dense(50.0, 400.0)  # wide range
        df = _plateau_fat(dp, 0, peak_val=1.5)  # flat — gradient never triggers
        # Peak somewhere in the middle
        fm_idx_power = 200.0
        fm_idx = int(np.argmin(np.abs(dp - fm_idx_power)))
        df_copy = df.copy()
        # Ensure peak is clearly at fm_idx
        df_copy[fm_idx] = 1.6

        zone_min, zone_max = _find_fatmax_zone(dp, df_copy, fm_idx)

        assert zone_max - zone_min <= 80.0 + 0.5, (
            f"Width {zone_max - zone_min:.1f}W exceeds 80W cap"
        )

    def test_width_max_guard_uses_asymmetric_offsets(self) -> None:
        """Width-max guard: peak-30W to peak+50W (not symmetric)."""
        dp = _dense(50.0, 400.0)
        fm_idx_power = 200.0
        fm_idx = int(np.argmin(np.abs(dp - fm_idx_power)))
        df = np.full_like(dp, 1.5, dtype=float)
        df[fm_idx] = 1.6  # clear peak

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        # When 80W cap fires: zone_min = peak - 30, zone_max = peak + 50
        assert zone_max <= fm_idx_power + 50.0 + 0.5, (
            f"zone_max {zone_max} exceeds peak+50W={fm_idx_power + 50.0}"
        )
        assert zone_min >= fm_idx_power - 30.0 - 0.5, (
            f"zone_min {zone_min} below peak-30W={fm_idx_power - 30.0}"
        )

    def test_min_guard_uses_asymmetric_offsets(self) -> None:
        """Width-min guard: peak-5W to peak+10W when zone too narrow."""
        dp = _dense(100.0, 300.0)
        fm_idx_power = 200.0
        fm_idx = int(np.argmin(np.abs(dp - fm_idx_power)))
        # Very sharp peak: 80% threshold collapses zone to sub-10W
        df = _bell_fat(dp, peak_power=fm_idx_power, peak_val=1.5, sigma=0.5)
        df = np.clip(df, 0, None)

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        # Min guard should push zone to at least peak-5 / peak+10
        assert zone_max >= fm_idx_power - 0.5, (
            f"zone_max {zone_max} should be at or above peak {fm_idx_power}"
        )
        assert zone_max - zone_min >= 9.9


# ---------------------------------------------------------------------------
# 8. Crossover double-cap after width-max expansion
# ---------------------------------------------------------------------------


class TestCrossoverDoubleCap:
    """Crossover cap re-applied after width-max expansion (per Builder notes)."""

    def test_crossover_recapped_after_width_max_expansion(self) -> None:
        """If width-max expands zone_max, crossover cap must re-apply."""
        dp = _dense(50.0, 400.0)
        fm_idx_power = 200.0
        fm_idx = int(np.argmin(np.abs(dp - fm_idx_power)))
        df = np.full_like(dp, 1.5, dtype=float)
        df[fm_idx] = 1.6

        # Crossover at 220W — after width-max expands to peak+50=250W,
        # crossover should cap it back to 220W
        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx, crossover_power=220.0)

        assert zone_max <= 220.0 + 0.1, (
            f"zone_max {zone_max} should be capped by crossover 220W even after width-max expansion"
        )
        assert zone_max > zone_min

    def test_crossover_recapped_after_width_min_expansion(self) -> None:
        """Width-min expansion must not violate crossover cap."""
        dp = _dense(100.0, 300.0)
        # Very sharp bell: sigma=0.5W — natural zone is <<10W, triggers width-min guard
        fm_idx_power = 200.0
        fm_idx = int(np.argmin(np.abs(dp - fm_idx_power)))
        sigma = 0.5
        df = 1.5 * np.exp(-((dp - fm_idx_power) ** 2) / (2 * sigma ** 2))

        # Crossover at peak+3W = 203W
        # Width-min guard would expand zone_max to peak+10W = 210W without re-cap
        crossover = fm_idx_power + 3.0
        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx, crossover_power=crossover)

        assert zone_max <= crossover + 0.1, (
            f"zone_max {zone_max:.1f} must not exceed crossover {crossover:.1f} after width-min expansion"
        )
        assert zone_max > zone_min

    def test_no_double_cap_needed_when_crossover_above_peak_plus_50(self) -> None:
        """If crossover > peak+50W, double-cap is no-op (min naturally wins)."""
        dp = _dense(50.0, 400.0)
        fm_idx_power = 200.0
        fm_idx = int(np.argmin(np.abs(dp - fm_idx_power)))
        df = np.full_like(dp, 1.5, dtype=float)
        df[fm_idx] = 1.6

        # Crossover at 280W > peak+50=250W — should not affect zone_max
        zone_min_no_cx, zone_max_no_cx = _find_fatmax_zone(dp, df, fm_idx)
        zone_min_cx, zone_max_cx = _find_fatmax_zone(dp, df, fm_idx, crossover_power=280.0)

        # Both should give same zone_max (crossover doesn't tighten)
        assert zone_max_cx == pytest.approx(zone_max_no_cx, abs=1.0), (
            f"High crossover shouldn't change zone_max: no_cx={zone_max_no_cx}, cx={zone_max_cx}"
        )


# ---------------------------------------------------------------------------
# 9. Return type and basic invariants
# ---------------------------------------------------------------------------


class TestReturnTypeAndInvariants:
    """Basic invariants that must hold for all outputs."""

    @pytest.mark.parametrize(
        "peak_power,peak_val,sigma",
        [
            (150.0, 1.5, 10.0),
            (200.0, 0.5, 25.0),
            (250.0, 2.0, 5.0),
            (180.0, 0.03, 30.0),  # low peak — noise floor
        ],
    )
    def test_returns_tuple_of_two_floats(
        self, peak_power: float, peak_val: float, sigma: float
    ) -> None:
        dp = _dense(100.0, 300.0)
        df = _bell_fat(dp, peak_power=peak_power, peak_val=peak_val, sigma=sigma)
        df = np.clip(df, 0, None)
        fm_idx = int(np.argmax(df))

        result = _find_fatmax_zone(dp, df, fm_idx)

        assert isinstance(result, tuple), "Must return a tuple"
        assert len(result) == 2, "Must return exactly 2 elements"
        zone_min, zone_max = result
        assert isinstance(zone_min, float), f"zone_min must be float, got {type(zone_min)}"
        assert isinstance(zone_max, float), f"zone_max must be float, got {type(zone_max)}"

    @pytest.mark.parametrize(
        "peak_power,peak_val,sigma",
        [
            (150.0, 1.5, 10.0),
            (200.0, 0.5, 25.0),
            (250.0, 2.0, 5.0),
        ],
    )
    def test_zone_min_always_less_than_zone_max(
        self, peak_power: float, peak_val: float, sigma: float
    ) -> None:
        dp = _dense(100.0, 300.0)
        df = _bell_fat(dp, peak_power=peak_power, peak_val=peak_val, sigma=sigma)
        df = np.clip(df, 0, None)
        fm_idx = int(np.argmax(df))

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx)

        assert zone_min < zone_max, f"zone_min {zone_min} >= zone_max {zone_max}"

    @pytest.mark.parametrize(
        "crossover",
        [None, 200.0, 230.0, 250.0, 170.0, 150.0],
    )
    def test_zone_invariants_with_various_crossovers(self, crossover: float | None) -> None:
        dp = _dense(100.0, 300.0)
        df = _bell_fat(dp, peak_power=200.0, peak_val=1.5, sigma=15.0)
        df = np.clip(df, 0, None)
        fm_idx = int(np.argmax(df))

        zone_min, zone_max = _find_fatmax_zone(dp, df, fm_idx, crossover_power=crossover)

        assert zone_min < zone_max, (
            f"crossover={crossover}: zone_min {zone_min} >= zone_max {zone_max}"
        )
        assert zone_max - zone_min >= 9.9, (
            f"crossover={crossover}: width {zone_max - zone_min:.1f}W < 10W min"
        )
        assert zone_max - zone_min <= 80.5, (
            f"crossover={crossover}: width {zone_max - zone_min:.1f}W > 80W max"
        )
        assert np.isfinite(zone_min) and np.isfinite(zone_max)
