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
            "bike_power_w": np.linspace(80, 280, n),
            "rq": np.linspace(0.85, 1.10, n),
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
# Test 6 — All 57 keys present on empty input
# ---------------------------------------------------------------------------

def test_all_57_keys_present_on_empty_input() -> None:
    """analyze_cpm_indices returns ≥57 keys on empty/None inputs, each with 'supported'."""
    result = analyze_cpm_indices(
        bxb=pd.DataFrame(),
        vo2max_results={},
        vt_results={},
        substrate_results={},
        efficiency_results={},
        hr_results={},
    )

    assert len(result) >= 57, (
        f"Expected ≥57 keys, got {len(result)}: {sorted(result.keys())}"
    )
    for key, entry in result.items():
        assert "supported" in entry, (
            f"Key {key!r} is missing 'supported' field: {entry}"
        )


# ---------------------------------------------------------------------------
# Test 7 — Supported count with full realistic data
# ---------------------------------------------------------------------------

def test_supported_count_with_full_data() -> None:
    """With full realistic dicts, at least 23 indices should be supported."""
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
        "vt2_power_w": 240.0,
    }
    substrate_results = {
        "fatmax_power_w": 140.0,
    }
    efficiency_results = {
        "vo2_power_slope_ml_per_w": 10.5,
        "peak_gross_efficiency_pct": 22.5,
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
    assert supported_count >= 23, (
        f"Expected ≥23 supported indices, got {supported_count}. "
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


# ---------------------------------------------------------------------------
# Test 9 — cow computes correctly
# ---------------------------------------------------------------------------

def test_cow_computes() -> None:
    """cow is supported and equals o2_pulse / peak_power_achieved_w."""
    vo2max_results = {
        "vo2max_ml": 3700.0,
        "peak_power_achieved_w": 280.0,
    }
    hr_results = make_hr()

    result = analyze_cpm_indices(
        bxb=pd.DataFrame(),
        vo2max_results=vo2max_results,
        vt_results={},
        substrate_results={},
        efficiency_results={},
        hr_results=hr_results,
    )

    entry = result["cow"]
    assert entry["supported"] is True, f"Expected cow supported, got blocker: {entry.get('blocker')}"
    # o2_pulse = 3700/185 = 20.0 mL/beat; cow = 20.0/280 ≈ 0.07143
    expected = (3700.0 / 185.0) / 280.0
    assert abs(entry["value"] - expected) < 1e-5, (
        f"Expected cow ≈ {expected:.6f}, got {entry['value']}"
    )
    assert entry["unit"] == "mL/beat/W", f"Unexpected unit: {entry['unit']}"


# ---------------------------------------------------------------------------
# Test 10 — rcp_power_fraction computes correctly
# ---------------------------------------------------------------------------

def test_rcp_power_fraction_computes() -> None:
    """rcp_power_fraction is supported and equals vt2_power_w / peak_power_achieved_w."""
    vo2max_results = {
        "peak_power_achieved_w": 280.0,
    }
    vt_results = {
        "vt2_power_w": 240.0,
    }

    result = analyze_cpm_indices(
        bxb=pd.DataFrame(),
        vo2max_results=vo2max_results,
        vt_results=vt_results,
        substrate_results={},
        efficiency_results={},
        hr_results={},
    )

    entry = result["rcp_power_fraction"]
    assert entry["supported"] is True, f"Expected rcp_power_fraction supported, got blocker: {entry.get('blocker')}"
    expected = 240.0 / 280.0
    assert abs(entry["value"] - expected) < 1e-4, (
        f"Expected rcp_power_fraction ≈ {expected:.4f}, got {entry['value']}"
    )
    assert entry["unit"] == "ratio", f"Unexpected unit: {entry['unit']}"


# ---------------------------------------------------------------------------
# Test 11 — sci uses RQ formula when rq column is present
# ---------------------------------------------------------------------------

def test_sci_uses_rq_formula_when_rq_present() -> None:
    """sci uses the enhanced W·RER formula when rq column is present in bxb."""
    n = 20
    # VT1 at t_s=50s; bxb rows span 0–95s, all within ±30s window
    t_s = np.arange(n) * 5.0  # 0..95
    bxb = pd.DataFrame(
        {
            "block": ["block_1"] * n,
            "t_s": t_s,
            "ve_lmin": np.full(n, 40.0),
            "vco2_ml": np.linspace(1000, 3000, n),
            "vo2_ml": np.linspace(1200, 3500, n),
            "rq": np.full(n, 0.92),
            "hr_bpm": np.full(n, 150.0),
            "bike_power_w": np.linspace(80, 280, n),
        }
    )
    vt_results = {
        "vt1_time_s": 50.0,
        "vt1_hr": 150,
        "vt1_power_w": 180,
    }

    result = analyze_cpm_indices(
        bxb=bxb,
        vo2max_results={},
        vt_results=vt_results,
        substrate_results={},
        efficiency_results={},
        hr_results={},
    )

    entry = result["sci"]
    assert entry["supported"] is True, f"Expected sci supported, got blocker: {entry.get('blocker')}"
    # Enhanced formula: vt1_power * rq / (vt1_hr * ve_at_vt1)
    assert entry["unit"] == "W·RER/(bpm·L/min)", (
        f"Expected RER unit when rq present, got {entry['unit']!r}"
    )
    expected = 180.0 * 0.92 / (150.0 * 40.0)
    assert abs(entry["value"] - expected) < 1e-4, (
        f"Expected sci ≈ {expected:.6f}, got {entry['value']}"
    )


# ---------------------------------------------------------------------------
# Test 12 — sci falls back to original formula when rq column absent
# ---------------------------------------------------------------------------

def test_sci_falls_back_when_rq_absent() -> None:
    """sci uses the fallback W/(bpm·L/min) formula when rq column is missing."""
    n = 20
    t_s = np.arange(n) * 5.0
    bxb = pd.DataFrame(
        {
            "block": ["block_1"] * n,
            "t_s": t_s,
            "ve_lmin": np.full(n, 40.0),
            "vco2_ml": np.linspace(1000, 3000, n),
            "vo2_ml": np.linspace(1200, 3500, n),
            # NOTE: no "rq" column
            "hr_bpm": np.full(n, 150.0),
            "bike_power_w": np.linspace(80, 280, n),
        }
    )
    vt_results = {
        "vt1_time_s": 50.0,
        "vt1_hr": 150,
        "vt1_power_w": 180,
    }

    result = analyze_cpm_indices(
        bxb=bxb,
        vo2max_results={},
        vt_results=vt_results,
        substrate_results={},
        efficiency_results={},
        hr_results={},
    )

    entry = result["sci"]
    assert entry["supported"] is True, f"Expected sci supported, got blocker: {entry.get('blocker')}"
    # Fallback formula: vt1_power / (vt1_hr * ve_at_vt1)
    assert entry["unit"] == "W/(bpm·L/min)", (
        f"Expected fallback unit when rq absent, got {entry['unit']!r}"
    )
    expected = 180.0 / (150.0 * 40.0)
    assert abs(entry["value"] - expected) < 1e-4, (
        f"Expected sci fallback ≈ {expected:.6f}, got {entry['value']}"
    )


# ---------------------------------------------------------------------------
# Test 13 — hr_w_slope and ve_w_slope unsupported with fewer than 5 paired rows
# ---------------------------------------------------------------------------

def test_hr_w_slope_unsupported_with_few_rows() -> None:
    """hr_w_slope is unsupported when active BxB has fewer than 5 paired rows."""
    # 4 rows — below the ≥5 threshold
    bxb = pd.DataFrame(
        {
            "block": ["block_1"] * 4,
            "t_s": np.arange(4) * 10.0,
            "ve_lmin": np.linspace(30, 50, 4),
            "vco2_ml": np.linspace(1000, 2000, 4),
            "vo2_ml": np.linspace(1200, 2500, 4),
            "hr_bpm": np.linspace(120, 160, 4),
            "bike_power_w": np.linspace(100, 220, 4),
            "rq": np.linspace(0.85, 1.0, 4),
        }
    )

    result = analyze_cpm_indices(
        bxb=bxb,
        vo2max_results={},
        vt_results={},
        substrate_results={},
        efficiency_results={},
        hr_results={},
    )

    assert result["hr_w_slope"]["supported"] is False, (
        "hr_w_slope should be unsupported with <5 paired rows"
    )
    assert result["ve_w_slope"]["supported"] is False, (
        "ve_w_slope should be unsupported with <5 paired rows"
    )


# ---------------------------------------------------------------------------
# Test 14 — ipi unsupported when vo2_slope is zero
# ---------------------------------------------------------------------------

def test_ipi_unsupported_when_vo2_slope_zero() -> None:
    """ipi is unsupported when vo2_power_slope_ml_per_w is zero."""
    bxb = make_bxb(60)
    hr_results = make_hr()
    vo2max_results = {
        "vo2max_ml": 3500.0,
        "vo2max_rel": 45.0,
        "peak_power_achieved_w": 280.0,
    }
    efficiency_results = {
        "vo2_power_slope_ml_per_w": 0.0,  # zero → division undefined
    }

    result = analyze_cpm_indices(
        bxb=bxb,
        vo2max_results=vo2max_results,
        vt_results={},
        substrate_results={},
        efficiency_results=efficiency_results,
        hr_results=hr_results,
    )

    entry = result["ipi"]
    assert entry["supported"] is False, (
        f"Expected ipi unsupported when vo2_slope=0, got supported=True"
    )
    assert "zero" in entry["blocker"].lower() or "missing" in entry["blocker"].lower(), (
        f"Expected blocker to mention zero/missing, got: {entry['blocker']}"
    )


# ---------------------------------------------------------------------------
# Test 15 — rcp_power_fraction unsupported when vt2_power_w is None
# ---------------------------------------------------------------------------

def test_rcp_power_fraction_unsupported_without_vt2() -> None:
    """rcp_power_fraction is unsupported when vt2_power_w is missing from vt_results."""
    result = analyze_cpm_indices(
        bxb=pd.DataFrame(),
        vo2max_results={"peak_power_achieved_w": 280.0},
        vt_results={},  # no vt2_power_w
        substrate_results={},
        efficiency_results={},
        hr_results={},
    )

    entry = result["rcp_power_fraction"]
    assert entry["supported"] is False, (
        "rcp_power_fraction should be unsupported when vt2_power_w is absent"
    )


# ---------------------------------------------------------------------------
# Test 16 — tau_w_index unsupported without mono-exp fit
# ---------------------------------------------------------------------------

def test_tau_w_index_unsupported_without_mono_exp_fit() -> None:
    """tau_w_index is unsupported when energy_system_results lacks mono_exp_fit."""
    result = analyze_cpm_indices(
        bxb=make_bxb(60),
        vo2max_results={
            "vo2max_ml": 3500.0,
            "vo2max_rel": 45.0,
            "peak_power_achieved_w": 280.0,
        },
        vt_results={},
        substrate_results={},
        efficiency_results={},
        hr_results=make_hr(),
        energy_system_results={},  # no mono_exp_fit key
    )

    entry = result["tau_w_index"]
    assert entry["supported"] is False, (
        "tau_w_index should be unsupported without mono_exp_fit"
    )
    assert "mono" in entry["blocker"].lower() or "fit" in entry["blocker"].lower(), (
        f"Expected blocker to mention mono-exp fit, got: {entry['blocker']}"
    )
