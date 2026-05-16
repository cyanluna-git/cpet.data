"""
Regression coverage for cycling-native model fitting and confidence.

Test inventory:
1.  test_duration_bins_schema_stable
2.  test_best_rolling_power_short_series_returns_none
3.  test_best_rolling_power_valid_returns_float
4.  test_extract_workout_bests_empty_list
5.  test_extract_workout_bests_schema
6.  test_duplicate_fit_sessions_aggregated
7.  test_combined_guidance_payload_has_required_keys
8.  test_anchors_subkeys_always_present
9.  test_confidence_subkeys_always_present
10. test_summary_card_subkeys_always_present
11. test_narrative_subkeys_always_present
12. test_cp_far_below_minimum_yields_disagree_and_band
13. test_sparse_history_with_gap_bins
"""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.combined_guidance import compute_combined_guidance
from pipeline.cp_model import compute_cp_model
from pipeline.fit_history import (
    DURATION_BINS_S,
    best_rolling_power,
    extract_workout_bests,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_power_df(powers: list[float]) -> pd.DataFrame:
    """Build a minimal DataFrame with a power_w column."""
    return pd.DataFrame({"power_w": powers})


def _make_history_sparse(
    durations_s: list[int], powers_w: list[float]
) -> dict:
    """Build a history dict from selected (duration, power) pairs only."""
    bins: dict = {str(d): None for d in DURATION_BINS_S}
    for t, w in zip(durations_s, powers_w):
        bins[str(t)] = {"best_w": float(w), "source_file": "synthetic.fit"}
    total = len(DURATION_BINS_S)
    filled = sum(1 for v in bins.values() if v is not None)
    ratio = filled / total if total > 0 else 0.0
    return {
        "bins": bins,
        "coverage": {
            "filled_count": filled,
            "total_bins": total,
            "ratio": round(ratio, 4),
            "quality": "partial" if filled else "none",
        },
        "sessions": [],
    }


# Minimal CPET fixture for combined_guidance tests
CPET_MIN = {
    "ventilatory_thresholds": {"vt2_power_w": 250.0, "vt1_power_w": 180.0},
    "lactate": {"lt1_dmax_power_w": 175.0},
    "vo2max": {"vo2max_ml": 4500.0, "vo2max_rel": 60.0, "peak_power_achieved_w": 380.0},
    "cpm_indices": {"ftp_w": {"supported": True, "value": 237.5, "unit": "W", "note": ""}},
    "suitability": {},
}


# ---------------------------------------------------------------------------
# 1. DURATION_BINS_S schema stability
# ---------------------------------------------------------------------------


def test_duration_bins_schema_stable() -> None:
    """DURATION_BINS_S must contain exactly 9 bins in strict ascending order."""
    assert len(DURATION_BINS_S) == 9, (
        f"Expected 9 bins, got {len(DURATION_BINS_S)}: {DURATION_BINS_S}"
    )
    assert all(isinstance(b, int) for b in DURATION_BINS_S), (
        "All bins must be int"
    )
    assert list(DURATION_BINS_S) == sorted(DURATION_BINS_S), (
        f"Bins must be in ascending order: {DURATION_BINS_S}"
    )


# ---------------------------------------------------------------------------
# 2. best_rolling_power — series shorter than window → None
# ---------------------------------------------------------------------------


def test_best_rolling_power_short_series_returns_none() -> None:
    """Series with fewer rows than window size must return None."""
    df = make_power_df([300.0, 280.0])  # only 2 rows
    result = best_rolling_power(df, duration_sec=60)  # window = 60
    assert result is None, (
        f"Expected None for series shorter than window, got {result}"
    )


# ---------------------------------------------------------------------------
# 3. best_rolling_power — valid computation returns float
# ---------------------------------------------------------------------------


def test_best_rolling_power_valid_returns_float() -> None:
    """A series long enough for the window must return a non-None float."""
    # 10 rows of uniform power → best rolling mean = 300.0
    df = make_power_df([300.0] * 10)
    result = best_rolling_power(df, duration_sec=5)
    assert result is not None, "Expected a float, got None"
    assert isinstance(result, float), f"Expected float, got {type(result)}"
    assert result == pytest.approx(300.0, abs=1e-6), (
        f"Expected 300.0, got {result}"
    )


# ---------------------------------------------------------------------------
# 4. extract_workout_bests — empty list → all-None bins
# ---------------------------------------------------------------------------


def test_extract_workout_bests_empty_list() -> None:
    """Empty fit_paths must return a result with all bins as None and quality='none'."""
    result = extract_workout_bests([])

    assert "bins" in result
    assert "coverage" in result
    assert "sessions" in result

    for key, val in result["bins"].items():
        assert val is None, (
            f"Bin {key!r} should be None for empty input, got {val}"
        )

    assert result["coverage"]["quality"] == "none"
    assert result["coverage"]["filled_count"] == 0
    assert result["sessions"] == []


# ---------------------------------------------------------------------------
# 5. extract_workout_bests — schema: bins/coverage/sessions structure
# ---------------------------------------------------------------------------


def test_extract_workout_bests_schema() -> None:
    """extract_workout_bests result must have the documented key structure."""
    result = extract_workout_bests([])

    # Top-level keys
    assert set(result.keys()) >= {"bins", "coverage", "sessions"}

    # bins: each key is str(int), each value is None or {"best_w": float, ...}
    for key, val in result["bins"].items():
        assert key.isdigit(), f"Bin key must be str(int), got {key!r}"
        if val is not None:
            assert isinstance(val, dict), f"Non-None bin must be dict, got {val!r}"
            assert "best_w" in val, f"Bin dict must have 'best_w': {val}"
            assert isinstance(val["best_w"], float), (
                f"best_w must be float, got {type(val['best_w'])}"
            )

    # coverage sub-keys
    coverage = result["coverage"]
    for ck in ("filled_count", "total_bins", "ratio", "quality"):
        assert ck in coverage, f"coverage missing key {ck!r}"
    assert coverage["quality"] in ("full", "partial", "sparse", "none"), (
        f"Unexpected quality value: {coverage['quality']!r}"
    )

    # sessions is a list
    assert isinstance(result["sessions"], list)


# ---------------------------------------------------------------------------
# 6. Duplicate FIT paths → de-duplicated, not double-counted
# ---------------------------------------------------------------------------


def test_duplicate_fit_sessions_aggregated() -> None:
    """Passing the same file path twice must produce same result as passing it once."""
    from pathlib import Path

    # Use a fixture FIT file if available; fall back gracefully
    fixtures_dir = Path(__file__).parent / "fixtures" / "inscyd_ppd"
    raw_dir = fixtures_dir / "raw"
    search_dir = raw_dir if raw_dir.is_dir() else fixtures_dir
    fit_files = sorted(search_dir.glob("*.fit"))

    if not fit_files:
        pytest.skip("No FIT fixtures available for deduplication test")

    fit_path = fit_files[0]
    result_single = extract_workout_bests([fit_path])
    result_double = extract_workout_bests([fit_path, fit_path])

    # De-duplication: session count must be 1 in both cases
    assert len(result_single["sessions"]) == 1
    assert len(result_double["sessions"]) == 1, (
        "Duplicate file path must be de-duplicated to a single session"
    )

    # Bin values must be identical
    assert result_single["bins"] == result_double["bins"], (
        "Duplicate FIT files must not alter the bin results"
    )


# ---------------------------------------------------------------------------
# 7. compute_combined_guidance — all required top-level keys present
# ---------------------------------------------------------------------------


def test_combined_guidance_payload_has_required_keys() -> None:
    """compute_combined_guidance must always return all required top-level keys."""
    required_keys = {
        "status", "anchors", "disagreements", "confidence",
        "summary_card", "narrative", "version",
    }
    # Test for abstain path (no cp_model)
    result_no_cp = compute_combined_guidance(CPET_MIN, cp_model_result=None)
    assert required_keys <= set(result_no_cp.keys()), (
        f"Missing keys (no cp): {required_keys - set(result_no_cp.keys())}"
    )

    # Test for computed path
    cp_result = {
        "status": "computed",
        "cp_w": 245.0,
        "w_prime_j": 18000.0,
        "r_squared": 0.97,
        "suitability": {"status": "point"},
        "abstain_reason": None,
    }
    result_with_cp = compute_combined_guidance(CPET_MIN, cp_model_result=cp_result)
    assert required_keys <= set(result_with_cp.keys()), (
        f"Missing keys (with cp): {required_keys - set(result_with_cp.keys())}"
    )


# ---------------------------------------------------------------------------
# 8. anchors subkeys always present
# ---------------------------------------------------------------------------


def test_anchors_subkeys_always_present() -> None:
    """anchors must always contain all canonical subkeys (values may be None)."""
    required = {"cp_w", "w_prime_j", "vt2_power_w", "ftp_w", "lt1_power_w", "peak_power_w"}

    for cp_arg in [None, {"status": "abstained", "cp_w": None, "w_prime_j": None,
                          "suitability": {"status": "hidden"}, "abstain_reason": "no data"}]:
        result = compute_combined_guidance(CPET_MIN, cp_model_result=cp_arg)
        missing = required - set(result["anchors"].keys())
        assert not missing, (
            f"anchors missing keys for cp_arg={cp_arg!r}: {missing}"
        )


# ---------------------------------------------------------------------------
# 9. confidence subkeys always present
# ---------------------------------------------------------------------------


def test_confidence_subkeys_always_present() -> None:
    """confidence must always contain: cpet_quality, cp_model_quality, agreement_count, total_pairs."""
    required = {"cpet_quality", "cp_model_quality", "agreement_count", "total_pairs"}

    result = compute_combined_guidance(CPET_MIN, cp_model_result=None)
    missing = required - set(result["confidence"].keys())
    assert not missing, f"confidence missing keys: {missing}"

    # Also check types
    conf = result["confidence"]
    assert isinstance(conf["cpet_quality"], str)
    assert isinstance(conf["cp_model_quality"], str)
    assert isinstance(conf["agreement_count"], int)
    assert isinstance(conf["total_pairs"], int)


# ---------------------------------------------------------------------------
# 10. summary_card subkeys always present
# ---------------------------------------------------------------------------


def test_summary_card_subkeys_always_present() -> None:
    """summary_card must always contain: headline, point_w, band_w, label, badges."""
    required = {"headline", "point_w", "band_w", "label", "badges"}

    result = compute_combined_guidance(CPET_MIN, cp_model_result=None)
    missing = required - set(result["summary_card"].keys())
    assert not missing, f"summary_card missing keys: {missing}"

    sc = result["summary_card"]
    assert isinstance(sc["headline"], str)
    assert isinstance(sc["badges"], list)


# ---------------------------------------------------------------------------
# 11. narrative subkeys always present
# ---------------------------------------------------------------------------


def test_narrative_subkeys_always_present() -> None:
    """narrative must always contain: headline, body, warnings."""
    required = {"headline", "body", "warnings"}

    result = compute_combined_guidance(CPET_MIN, cp_model_result=None)
    missing = required - set(result["narrative"].keys())
    assert not missing, f"narrative missing keys: {missing}"

    narr = result["narrative"]
    assert isinstance(narr["headline"], str)
    assert isinstance(narr["body"], str)
    assert isinstance(narr["warnings"], list)


# ---------------------------------------------------------------------------
# 12. CP far below minimum → cp_vs_vt2 disagrees, band_w not None
# ---------------------------------------------------------------------------


def test_cp_far_below_minimum_yields_disagree_and_band() -> None:
    """CP=80W vs VT2=250W → ratio=0.32, outside CP_VT2_RATIO_RANGE → disagree.

    Status should be low_confidence or abstain; band_w is set when low_confidence.
    """
    cp_result = {
        "status": "computed",
        "cp_w": 80.0,
        "w_prime_j": 15000.0,
        "r_squared": 0.98,
        "suitability": {"status": "point"},
        "abstain_reason": None,
    }
    result = compute_combined_guidance(CPET_MIN, cp_model_result=cp_result)

    # cp_vs_vt2 must disagree: ratio = 80/250 = 0.32, expected (0.95, 1.10)
    cp_vt2_pair = next(
        (d for d in result["disagreements"] if d["pair"] == "cp_vs_vt2"), None
    )
    assert cp_vt2_pair is not None, "cp_vs_vt2 pair not found in disagreements"
    assert cp_vt2_pair["status"] == "disagree", (
        f"Expected cp_vs_vt2 to disagree, got {cp_vt2_pair['status']!r}"
    )
    assert cp_vt2_pair["ratio"] == pytest.approx(0.32, abs=0.001)

    # Overall status must reflect low confidence or abstain (not supported)
    assert result["status"] in ("low_confidence", "abstain"), (
        f"Expected low_confidence or abstain for CP far below VT2, got {result['status']!r}"
    )

    # When status is low_confidence, band_w must be set
    if result["status"] == "low_confidence":
        assert result["summary_card"]["band_w"] is not None, (
            "band_w must be set for low_confidence status"
        )
        lo, hi = result["summary_card"]["band_w"]
        assert lo <= hi, f"band_w must be [lo, hi] with lo <= hi, got [{lo}, {hi}]"


# ---------------------------------------------------------------------------
# 13. Sparse history with gap bins → compute_cp_model still works when ≥3 filled
# ---------------------------------------------------------------------------


def test_sparse_history_with_gap_bins() -> None:
    """History with some None bins (gaps) must still compute when ≥3 bins are filled."""
    # Fill only 3 non-contiguous bins: 60s, 300s, 1200s (indices 4, 6, 8 in DURATION_BINS_S)
    # All other bins remain None — tests gap handling
    CP = 250.0
    W_PRIME = 20_000.0
    filled_durations = [60, 300, 1200]
    powers = [CP + W_PRIME / t for t in filled_durations]

    history = _make_history_sparse(filled_durations, powers)

    # Verify the setup: exactly 3 bins filled, others are None
    filled_bins = [k for k, v in history["bins"].items() if v is not None]
    none_bins = [k for k, v in history["bins"].items() if v is None]
    assert len(filled_bins) == 3, f"Expected 3 filled bins, got {len(filled_bins)}"
    assert len(none_bins) == 6, f"Expected 6 None bins, got {len(none_bins)}"

    result = compute_cp_model(history)

    # Should compute successfully with exactly 3 filled bins
    assert result["status"] == "computed", (
        f"Expected 'computed' with 3 gap-spanning bins, got abstained: "
        f"{result.get('abstain_reason')}"
    )
    assert result["points_used"] == 3
    assert result["cp_w"] == pytest.approx(CP, abs=0.1)
    assert result["w_prime_j"] == pytest.approx(W_PRIME, abs=10.0)
