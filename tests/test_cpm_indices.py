"""
tests/test_cpm_indices.py — E2E unit tests for the CPM index pipeline.

Covers analyze_cpm_indices() (pipeline.analysis) and build_cpm_panel()
(pipeline.report) with synthetic inputs.
"""
import numpy as np
import pandas as pd
import pytest

from pipeline.analysis import analyze_cpm_indices
from pipeline.report import build_cpm_panel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_bxb(n: int = 60) -> pd.DataFrame:
    """Synthetic breath-by-breath DataFrame with block_1 rows."""
    return pd.DataFrame(
        {
            "block": ["block_1"] * n,
            "t_s": np.arange(n) * 5.0,
            "ve_lmin": np.linspace(30, 80, n),
            "vco2_ml": np.linspace(1000, 3000, n),
            "vo2_ml": np.linspace(1200, 3500, n),
            "ve_vo2": np.linspace(25, 35, n),
            "ve_vco2": np.linspace(28, 38, n),
            "vd_vt_e": np.linspace(0.2, 0.35, n),
            "vt_l": np.linspace(1.5, 3.0, n),
            "rf": np.linspace(18, 28, n),
            "hr_bpm": np.linspace(120, 185, n),
            "ee_kcal": np.linspace(5, 15, n),
        }
    )


def make_hr(resting: int = 55) -> dict:
    """Synthetic HR results dict."""
    return {
        "actual_max_hr": 185,
        "predicted_max_hr": 190,
        "resting_hr_bpm": resting,
        "hrr1_bpm": 25,
        "hr_power_slope": 0.8,
    }


def _empty_results() -> tuple[dict, dict, dict, dict, dict]:
    """Return empty dicts for vo2max, vt, substrate, efficiency, hr results."""
    return {}, {}, {}, {}, {}


# ---------------------------------------------------------------------------
# Test 1 — O2 Pulse
# ---------------------------------------------------------------------------

def test_o2_pulse_computes() -> None:
    """o2_pulse_ml_beat is supported and equals vo2max_ml / actual_max_hr."""
    vo2max_results = {"vo2max_ml": 3700.0, "vo2max_rel": 22.0, "rer_max": None}
    hr_results = make_hr()

    result = analyze_cpm_indices(
        bxb=pd.DataFrame(),
        vo2max_results=vo2max_results,
        vt_results={},
        substrate_results={},
        efficiency_results={},
        hr_results=hr_results,
    )

    entry = result["o2_pulse_ml_beat"]
    assert entry["supported"] is True, f"Expected supported, got blocker: {entry.get('blocker')}"
    expected = 3700.0 / 185.0
    assert abs(entry["value"] - expected) < 0.01, (
        f"Expected o2_pulse ≈ {expected:.2f}, got {entry['value']}"
    )


# ---------------------------------------------------------------------------
# Test 2 — VE/VCO2 Slope
# ---------------------------------------------------------------------------

def test_ve_vco2_slope_computes() -> None:
    """ve_vco2_slope is supported and value falls in a reasonable range (20–50)."""
    bxb = make_bxb(60)
    hr_results = make_hr()

    result = analyze_cpm_indices(
        bxb=bxb,
        vo2max_results={},
        vt_results={},
        substrate_results={},
        efficiency_results={},
        hr_results=hr_results,
    )

    entry = result["ve_vco2_slope"]
    assert entry["supported"] is True, f"Expected supported, got blocker: {entry.get('blocker')}"
    assert 20.0 <= entry["value"] <= 50.0, (
        f"ve_vco2_slope {entry['value']} not in expected range [20, 50]"
    )


# ---------------------------------------------------------------------------
# Test 3 — OUES
# ---------------------------------------------------------------------------

def test_oues_computes() -> None:
    """oues is supported with a positive value for synthetic linear BxB data."""
    bxb = make_bxb(60)
    hr_results = make_hr()

    result = analyze_cpm_indices(
        bxb=bxb,
        vo2max_results={},
        vt_results={},
        substrate_results={},
        efficiency_results={},
        hr_results=hr_results,
    )

    entry = result["oues"]
    assert entry["supported"] is True, f"Expected supported, got blocker: {entry.get('blocker')}"
    assert entry["value"] > 0, f"Expected positive OUES, got {entry['value']}"


# ---------------------------------------------------------------------------
# Test 4 — Weber Class (all four classes)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "vo2max_rel, expected_class",
    [
        (22.0, "A"),
        (18.0, "B"),
        (13.0, "C"),
        (8.0, "D"),
    ],
)
def test_weber_class_all_classes(vo2max_rel: float, expected_class: str) -> None:
    """Weber class maps vo2max_rel to the correct A/B/C/D category."""
    result = analyze_cpm_indices(
        bxb=pd.DataFrame(),
        vo2max_results={"vo2max_rel": vo2max_rel},
        vt_results={},
        substrate_results={},
        efficiency_results={},
        hr_results={},
    )

    entry = result["weber_class"]
    assert entry["supported"] is True, (
        f"Expected supported for vo2max_rel={vo2max_rel}, got: {entry}"
    )
    assert entry["value"] == expected_class, (
        f"vo2max_rel={vo2max_rel}: expected Weber class {expected_class!r}, got {entry['value']!r}"
    )


# ---------------------------------------------------------------------------
# Test 5 — Chronotropic Index unsupported without resting HR
# ---------------------------------------------------------------------------

def test_ci_unsupported_without_resting_hr() -> None:
    """chronotropic_index is unsupported when resting_hr_bpm is None."""
    hr_results = {
        "actual_max_hr": 185,
        "predicted_max_hr": 190,
        "resting_hr_bpm": None,
        "hrr1_bpm": 25,
        "hr_power_slope": 0.8,
    }

    result = analyze_cpm_indices(
        bxb=pd.DataFrame(),
        vo2max_results={},
        vt_results={},
        substrate_results={},
        efficiency_results={},
        hr_results=hr_results,
    )

    entry = result["chronotropic_index"]
    assert entry["supported"] is False, (
        f"Expected chronotropic_index unsupported, but got supported=True"
    )


# ---------------------------------------------------------------------------
# Test 6 — All 36 keys present on empty input
# ---------------------------------------------------------------------------

def test_all_36_keys_present_on_empty_input() -> None:
    """analyze_cpm_indices returns ≥36 keys on empty/None inputs, each with 'supported'."""
    result = analyze_cpm_indices(
        bxb=pd.DataFrame(),
        vo2max_results={},
        vt_results={},
        substrate_results={},
        efficiency_results={},
        hr_results={},
    )

    assert len(result) >= 36, (
        f"Expected ≥36 keys, got {len(result)}: {sorted(result.keys())}"
    )
    for key, entry in result.items():
        assert "supported" in entry, (
            f"Key {key!r} is missing 'supported' field: {entry}"
        )


# ---------------------------------------------------------------------------
# Test 7 — Supported count with full realistic data
# ---------------------------------------------------------------------------

def test_supported_count_with_full_data() -> None:
    """With full realistic dicts, at least 15 indices should be supported."""
    bxb = make_bxb(60)
    hr_results = make_hr()

    vo2max_results = {
        "vo2max_ml": 3500.0,
        "vo2max_rel": 45.0,
        "rer_max": 1.12,
        "peak_power_achieved_w": 280.0,
    }
    vt_results = {
        "vt1_hr": 145,
        "vt1_vo2_ml": 2100.0,
        "vt1_power_w": 180.0,
        "vt1_time_s": 120.0,
        "vt2_vo2_ml": 2900.0,
        "vt2_time_s": 200.0,
    }
    substrate_results = {
        "fatmax_power_w": 140.0,
    }
    efficiency_results = {
        "vo2_power_slope_ml_per_w": 10.5,
    }

    result = analyze_cpm_indices(
        bxb=bxb,
        vo2max_results=vo2max_results,
        vt_results=vt_results,
        substrate_results=substrate_results,
        efficiency_results=efficiency_results,
        hr_results=hr_results,
    )

    supported_count = sum(
        1 for v in result.values() if isinstance(v, dict) and v.get("supported")
    )
    assert supported_count >= 15, (
        f"Expected ≥15 supported indices, got {supported_count}. "
        f"Unsupported: {[k for k,v in result.items() if not v.get('supported')]}"
    )


# ---------------------------------------------------------------------------
# Test 8 — build_cpm_panel with empty dict returns string
# ---------------------------------------------------------------------------

def test_report_builds_without_error() -> None:
    """build_cpm_panel({}) returns a string (empty section) without raising."""
    result = build_cpm_panel({})
    assert isinstance(result, str), (
        f"Expected str from build_cpm_panel({{}}), got {type(result)}"
    )
