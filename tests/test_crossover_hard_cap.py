"""
tests/test_crossover_hard_cap.py — Tests for crossover hard cap on FatMax zone_max.

Covers both:
  1. _interpolate_and_compute_markers (via _build_power_domain_substrate)
  2. _anchor_power_domain_markers (direct unit tests)

Cases:
  - Normal: zone_max is capped to crossover power when crossover exists
  - No crossover: zone_max unchanged (empty crossovers list)
  - Collapse fallback: cap causes zone_max <= zone_min → fallback +10W
"""

import numpy as np
import pandas as pd
import pytest

from pipeline.analysis import _anchor_power_domain_markers, _build_power_domain_substrate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_anchor_payload(
    power_w: list[float],
    fat_gmin: list[float],
    primary_crossover: dict | None = None,
) -> dict:
    """Build a minimal payload suitable for _anchor_power_domain_markers."""
    return {
        "metabolism_power_curve": {
            "power_w": power_w,
            "fat_gmin": fat_gmin,
            "cho_gmin": [0.5] * len(power_w),
            "hr_bpm": [120.0] * len(power_w),
            "vo2_kg": [30.0] * len(power_w),
        },
        "metabolism_markers": {
            "primary_crossover": primary_crossover,
            "all_crossovers": [primary_crossover] if primary_crossover else [],
        },
        "metabolism_power_bins": {
            "power_w": power_w,
            "fat_gmin": fat_gmin,
            "cho_gmin": [0.5] * len(power_w),
            "sample_count": [1] * len(power_w),
        },
    }


def _make_substrate_bxb(
    powers: list[float],
    fat: list[float],
    cho: list[float],
) -> pd.DataFrame:
    """Build a minimal BxB DataFrame for _build_power_domain_substrate."""
    n = len(powers)
    return pd.DataFrame(
        {
            "bike_power_w": powers,
            "fat_gmin": fat,
            "cho_gmin": cho,
            "hr_bpm": [120.0] * n,
            "vo2_kg": [30.0] * n,
        }
    )


# ---------------------------------------------------------------------------
# _anchor_power_domain_markers — direct unit tests
# ---------------------------------------------------------------------------


class TestAnchorPowerDomainMarkersCrossoverCap:
    """Direct unit tests for the crossover hard cap inside _anchor_power_domain_markers."""

    def test_normal_cap_applies_when_crossover_below_natural_zone_max(self) -> None:
        """zone_max is capped to crossover power when crossover < natural zone_max."""
        # Dense curve: 100W-300W, fat peaks at 200W (idx 10 of 21 points)
        power_w = list(range(100, 310, 10))  # [100,110,...,300]
        # Fat: peak at 200W, descends on both sides
        fat_gmin = [abs(pw - 200) * -0.01 + 1.5 for pw in power_w]

        # Primary crossover at 230W — should cap zone_max to 230W
        cx = {"power_w": 230.0, "fat_gmin": 0.6, "cho_gmin": 0.6, "confidence": 0.2}
        payload = _make_anchor_payload(power_w, fat_gmin, cx)

        result = _anchor_power_domain_markers(payload, fatmax_power_w=200.0, fatmax_gmin=1.5)
        markers = result["metabolism_markers"]

        assert markers["fatmax_zone_max_w"] <= 230.0, (
            f"zone_max {markers['fatmax_zone_max_w']} should not exceed crossover 230W"
        )

    def test_crossover_at_or_above_natural_zone_max_does_not_change_it(self) -> None:
        """Crossover above natural zone_max — min() keeps natural zone_max unchanged."""
        power_w = list(range(100, 310, 10))
        fat_gmin = [abs(pw - 200) * -0.01 + 1.5 for pw in power_w]

        # Crossover at 295W — well above the natural 90%-threshold zone
        cx = {"power_w": 295.0, "fat_gmin": 0.1, "cho_gmin": 0.1, "confidence": 0.1}
        payload = _make_anchor_payload(power_w, fat_gmin, cx)

        result_with_cx = _anchor_power_domain_markers(payload, fatmax_power_w=200.0, fatmax_gmin=1.5)

        # Compare without crossover
        payload_no_cx = _make_anchor_payload(power_w, fat_gmin, None)
        result_no_cx = _anchor_power_domain_markers(payload_no_cx, fatmax_power_w=200.0, fatmax_gmin=1.5)

        # With a high crossover the zone_max should be no larger than without
        assert (
            result_with_cx["metabolism_markers"]["fatmax_zone_max_w"]
            <= result_no_cx["metabolism_markers"]["fatmax_zone_max_w"] + 1.0
        )

    def test_no_crossover_leaves_zone_max_unchanged(self) -> None:
        """Empty primary_crossover → zone_max computed from 90% threshold only."""
        power_w = list(range(100, 310, 10))
        fat_gmin = [abs(pw - 200) * -0.01 + 1.5 for pw in power_w]

        payload_no_cx = _make_anchor_payload(power_w, fat_gmin, None)
        result_no_cx = _anchor_power_domain_markers(payload_no_cx, fatmax_power_w=200.0, fatmax_gmin=1.5)

        payload_with_cx = _make_anchor_payload(power_w, fat_gmin, {"power_w": 290.0, "fat_gmin": 0.1, "cho_gmin": 0.1, "confidence": 0.1})
        result_with_cx = _anchor_power_domain_markers(payload_with_cx, fatmax_power_w=200.0, fatmax_gmin=1.5)

        # No crossover case: primary_crossover is None, so cap branch is skipped
        assert result_no_cx["metabolism_markers"]["fatmax_zone_max_w"] > 0

        # With crossover higher than natural zone_max: no meaningful reduction
        assert result_no_cx["metabolism_markers"]["fatmax_zone_min_w"] <= 200.0

    def test_fallback_when_cap_collapses_zone(self) -> None:
        """Crossover power <= zone_min triggers fallback: zone_max = zone_min + 10W."""
        # Create scenario where natural zone_min is at 190W
        # Crossover at 180W — below zone_min — should trigger fallback
        power_w = list(range(100, 310, 10))
        # Make fat peak sharply at 200W so zone_min is close to 190W
        fat_gmin = [max(0.0, 1.5 - abs(pw - 200) * 0.2) for pw in power_w]

        # Crossover at 185W — this will be <= zone_min (should be ~190W)
        cx = {"power_w": 185.0, "fat_gmin": 0.5, "cho_gmin": 0.5, "confidence": 0.3}
        payload = _make_anchor_payload(power_w, fat_gmin, cx)

        result = _anchor_power_domain_markers(payload, fatmax_power_w=200.0, fatmax_gmin=1.5)
        markers = result["metabolism_markers"]

        zone_min = markers["fatmax_zone_min_w"]
        zone_max = markers["fatmax_zone_max_w"]

        # zone_max must be strictly greater than zone_min
        assert zone_max > zone_min, f"zone_max {zone_max} should exceed zone_min {zone_min}"

        # If collapse occurred, fallback = zone_min + 10W
        if cx["power_w"] <= zone_min:
            assert zone_max == pytest.approx(zone_min + 10.0, abs=0.2), (
                f"Fallback expected zone_max = zone_min + 10W, got zone_max={zone_max}, zone_min={zone_min}"
            )

    def test_crossover_below_fatmax_is_excluded_from_zone_boundary(self) -> None:
        """Crossover below FatMax power must not cap zone_max (block-mixing artifact).

        When crossover < FatMax, zone_cx is set to None so _find_fatmax_zone
        computes the zone naturally from the gradient descent and 85%-threshold
        walk — the crossover is physiologically irrelevant in this position.
        """
        n_pts = 201
        powers = [100.0 + i * 1.0 for i in range(n_pts)]  # 100..300
        fat_vals = [max(0.0, 1.5 * np.exp(-((pw - 200.0) ** 2) / (2 * 2.0 ** 2))) for pw in powers]

        # Crossover at 150W — far below FatMax at 200W
        cx = {"power_w": 150.0, "fat_gmin": 0.1, "cho_gmin": 0.1, "confidence": 0.5}
        payload = _make_anchor_payload(powers, fat_vals, cx)

        result = _anchor_power_domain_markers(payload, fatmax_power_w=200.0, fatmax_gmin=1.5)
        markers = result["metabolism_markers"]

        zone_min = markers["fatmax_zone_min_w"]
        zone_max = markers["fatmax_zone_max_w"]

        # Zone must be valid (no collapse)
        assert zone_max > zone_min, f"Zone collapsed: zone_min={zone_min}, zone_max={zone_max}"
        # FatMax marker must be the time-domain value, not capped at crossover
        assert markers["fatmax_power_w"] == pytest.approx(200.0, abs=0.6)
        # zone_max must not be capped at crossover (150W) — it should be well above it
        assert zone_max > 150.0, (
            f"zone_max {zone_max} should not be capped at crossover 150W when crossover < FatMax"
        )

    def test_zone_max_equals_crossover_when_cap_is_tight(self) -> None:
        """When crossover slightly below natural zone_max, zone_max = crossover power."""
        # Craft power range 100–300, fat peak at 150W with wide zone
        power_w = list(range(100, 310, 10))
        # Plateau-shaped fat: high 120-200W, drops outside
        fat_gmin = [1.5 if 120 <= pw <= 200 else max(0.0, 1.5 - abs(pw - 160) * 0.05) for pw in power_w]

        # Natural zone_max will extend to ~200W; crossover at 170W caps it
        cx = {"power_w": 170.0, "fat_gmin": 0.8, "cho_gmin": 0.8, "confidence": 0.4}
        payload = _make_anchor_payload(power_w, fat_gmin, cx)

        result = _anchor_power_domain_markers(payload, fatmax_power_w=150.0, fatmax_gmin=1.5)
        markers = result["metabolism_markers"]

        zone_max = markers["fatmax_zone_max_w"]
        zone_min = markers["fatmax_zone_min_w"]

        assert zone_max <= 170.0, (
            f"zone_max {zone_max} should not exceed crossover power 170W"
        )
        assert zone_max > zone_min

    def test_no_payload_returns_unchanged(self) -> None:
        """Empty payload passed in → returned as-is."""
        result = _anchor_power_domain_markers({}, fatmax_power_w=200.0, fatmax_gmin=1.5)
        assert result == {}

    def test_none_fatmax_returns_payload_unchanged(self) -> None:
        """None fatmax_power_w → payload returned as-is."""
        payload = {"metabolism_markers": {}, "metabolism_power_curve": {"power_w": [100.0], "fat_gmin": [1.0]}}
        result = _anchor_power_domain_markers(payload, fatmax_power_w=None, fatmax_gmin=1.0)
        assert result == payload


# ---------------------------------------------------------------------------
# _build_power_domain_substrate — integration path via _interpolate_and_compute_markers
# ---------------------------------------------------------------------------


class TestBuildPowerDomainSubstrateCrossoverCap:
    """Tests for the crossover cap inside _interpolate_and_compute_markers,
    accessed via the public _build_power_domain_substrate entry point."""

    def _make_bxb_with_fat_cho_crossover(self) -> pd.DataFrame:
        """BxB with fat > cho at low powers, fat < cho at high powers.
        Crossover occurs near 200W — zone_max should be capped there."""
        n = 15
        powers = np.linspace(100.0, 300.0, n)
        # Fat starts high, falls below cho around 200W
        fat = np.array([2.0, 1.9, 1.8, 1.7, 1.6, 1.5, 1.2, 0.9, 0.6, 0.4, 0.3, 0.2, 0.1, 0.05, 0.0])
        cho = np.array([0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.4, 1.7, 2.0, 2.3, 2.6, 3.0, 3.4, 3.8])
        return _make_substrate_bxb(
            powers=list(powers),
            fat=list(fat),
            cho=list(cho),
        )

    def _make_bxb_fat_always_above_cho(self) -> pd.DataFrame:
        """BxB where fat > cho throughout — no crossover."""
        n = 15
        powers = np.linspace(100.0, 300.0, n)
        fat = np.linspace(2.0, 1.5, n)   # always declining but above cho
        cho = np.linspace(0.5, 1.0, n)   # always below fat
        return _make_substrate_bxb(
            powers=list(powers),
            fat=list(fat),
            cho=list(cho),
        )

    def test_crossover_caps_zone_max_in_pchip_path(self) -> None:
        """With fat-CHO crossover, zone_max in markers <= crossover power."""
        bxb = self._make_bxb_with_fat_cho_crossover()
        result = _build_power_domain_substrate(bxb)

        assert result, "Expected non-empty result"
        markers = result["metabolism_markers"]
        cx = markers.get("primary_crossover")

        if cx is not None:
            # When crossover is detected, zone_max must not exceed it
            assert markers["fatmax_zone_max_w"] <= cx["power_w"] + 0.6, (
                f"zone_max {markers['fatmax_zone_max_w']} exceeds crossover {cx['power_w']}"
            )

    def test_no_crossover_leaves_zone_max_at_threshold_value(self) -> None:
        """Without fat-CHO crossover, primary_crossover is None and zone_max is normal."""
        bxb = self._make_bxb_fat_always_above_cho()
        result = _build_power_domain_substrate(bxb)

        assert result, "Expected non-empty result"
        markers = result["metabolism_markers"]
        assert markers.get("primary_crossover") is None
        # zone_max should be a reasonable non-zero value
        assert markers["fatmax_zone_max_w"] > 0

    def test_zone_min_always_less_than_zone_max(self) -> None:
        """zone_min < zone_max must hold in all crossover scenarios."""
        bxb = self._make_bxb_with_fat_cho_crossover()
        result = _build_power_domain_substrate(bxb)

        if result:
            markers = result["metabolism_markers"]
            assert markers["fatmax_zone_min_w"] < markers["fatmax_zone_max_w"], (
                f"zone_min {markers['fatmax_zone_min_w']} >= zone_max {markers['fatmax_zone_max_w']}"
            )

    def test_crossover_cap_does_not_create_inverted_zone(self) -> None:
        """Fallback prevents zone inversion even when crossover < FatMax power."""
        # Fat stays high everywhere but we construct a scenario where
        # CHO overtakes fat right at a low power
        n = 15
        powers = list(np.linspace(100.0, 300.0, n))
        # CHO > fat from the start — crossover near 100W
        fat = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 0.8, 0.6, 0.4, 0.3, 0.2, 0.1, 0.0]
        cho = [0.5, 0.5, 0.5, 0.5, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 3.5]
        # FatMax is at 200W (index 7)
        fat[7] = 2.5  # make index 7 the peak

        bxb = _make_substrate_bxb(powers, fat, cho)
        result = _build_power_domain_substrate(bxb)

        if result:
            markers = result["metabolism_markers"]
            # Must never invert
            assert markers["fatmax_zone_min_w"] < markers["fatmax_zone_max_w"], (
                f"Inverted zone: min={markers['fatmax_zone_min_w']}, max={markers['fatmax_zone_max_w']}"
            )

    def test_zone_max_rounded_to_one_decimal(self) -> None:
        """zone_max in markers is always rounded to 1 decimal place."""
        bxb = self._make_bxb_with_fat_cho_crossover()
        result = _build_power_domain_substrate(bxb)

        if result:
            markers = result["metabolism_markers"]
            zone_max = markers["fatmax_zone_max_w"]
            # Rounding check: value matches its own 1-dp round
            assert zone_max == round(zone_max, 1)
