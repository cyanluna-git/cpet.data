"""Tests for pipeline.cp_model — Critical Power / W' 2-parameter model.

Test inventory:
1. test_real_inscyd_ppd_fit_files_compute
2. test_perfect_synthetic_fit_yields_point_suitability
3. test_filled_count_below_three_abstains
4. test_negative_w_prime_abstains
5. test_low_cp_abstains
6. test_constant_power_degenerate
7. test_run_analysis_skips_cp_model_when_no_fit
8. test_run_analysis_includes_cp_model_when_fit_present
9. test_persistence_round_trip
10. test_computed_result_powers_used_matches_input
11. test_durations_used_length_equals_points_used
12. test_suitability_band_when_r_squared_between_0_80_and_0_95
13. test_suitability_hidden_when_r_squared_below_0_80
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.cp_model import compute_cp_model
from pipeline.fit_history import (
    DURATION_BINS_S,
    extract_workout_bests,
    save_fit_history,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
INSCYD_PPD_DIR = FIXTURES_DIR / "inscyd_ppd"
INSCYD_NO_FIT_DIR = FIXTURES_DIR / "inscyd_no_fit"


def _inscyd_fit_files() -> list[Path]:
    raw_dir = INSCYD_PPD_DIR / "raw"
    search_dir = raw_dir if raw_dir.is_dir() else INSCYD_PPD_DIR
    return sorted(search_dir.glob("*.fit"))


def _make_history(durations_s: list[int], powers_w: list[float]) -> dict:
    """Build a synthetic history dict with the given (duration, power) pairs."""
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


# ---------------------------------------------------------------------------
# 1. Real INSCYD PPD FIT files → status="computed"
# ---------------------------------------------------------------------------


def test_real_inscyd_ppd_fit_files_compute() -> None:
    """Real inscyd_ppd FIT files must produce a computed CP result."""
    fit_files = _inscyd_fit_files()
    assert len(fit_files) >= 2, "Need at least 2 FIT fixtures in inscyd_ppd/raw/"

    history = extract_workout_bests(fit_files)
    result = compute_cp_model(history)

    assert result["status"] == "computed", (
        f"Expected 'computed', got 'abstained': {result.get('abstain_reason')}"
    )
    assert result["cp_w"] is not None
    assert result["cp_w"] > 0, f"CP should be positive, got {result['cp_w']}"
    assert result["w_prime_j"] is not None
    assert result["w_prime_j"] > 0, f"W' should be positive, got {result['w_prime_j']}"
    assert result["r_squared"] is not None
    assert 0.0 <= result["r_squared"] <= 1.0
    assert result["rmse"] is not None
    assert result["rmse"] >= 0.0
    assert result["points_used"] >= 3
    assert isinstance(result["powers_used_w"], list)
    assert all(isinstance(p, float) for p in result["powers_used_w"])
    assert result["suitability"]["status"] in ("point", "band", "hidden")


# ---------------------------------------------------------------------------
# 2. Perfect synthetic data → r²≈1.0, suitability="point"
# ---------------------------------------------------------------------------


def test_perfect_synthetic_fit_yields_point_suitability() -> None:
    """Exact hyperbolic bins (CP=250, W'=20000) must yield r²≈1.0 and suitability='point'."""
    CP = 250.0
    W_PRIME = 20_000.0
    # Use canonical bins that are guaranteed to exist in DURATION_BINS_S
    test_bins = [60, 180, 300, 600, 1200]
    powers = [CP + W_PRIME / t for t in test_bins]

    history = _make_history(test_bins, powers)
    result = compute_cp_model(history)

    assert result["status"] == "computed", (
        f"Abstained unexpectedly: {result.get('abstain_reason')}"
    )
    assert result["r_squared"] == pytest.approx(1.0, abs=1e-6), (
        f"Expected r²≈1.0, got {result['r_squared']}"
    )
    assert result["suitability"]["status"] == "point", (
        f"Expected 'point', got {result['suitability']['status']}"
    )
    assert result["cp_w"] == pytest.approx(CP, abs=0.01)
    assert result["w_prime_j"] == pytest.approx(W_PRIME, abs=1.0)


# ---------------------------------------------------------------------------
# 3. Fewer than 3 filled bins → abstained
# ---------------------------------------------------------------------------


def test_filled_count_below_three_abstains() -> None:
    """Exactly 2 filled bins must produce status='abstained'."""
    history = _make_history([60, 300], [300.0, 250.0])
    result = compute_cp_model(history)

    assert result["status"] == "abstained"
    assert result["abstain_reason"] is not None
    assert "3" in result["abstain_reason"] or "fewer" in result["abstain_reason"]


# ---------------------------------------------------------------------------
# 4. Negative W' → abstained
# ---------------------------------------------------------------------------


def test_negative_w_prime_abstains() -> None:
    """Inverted slope (power increases with duration) must produce W'<0 → abstained."""
    # Inverted: longer duration → higher power (slope is negative → W' < 0)
    history = _make_history(
        [60, 180, 300, 600, 1200],
        [100.0, 150.0, 200.0, 250.0, 300.0],  # power increases with t → negative W'
    )
    result = compute_cp_model(history)

    assert result["status"] == "abstained"
    assert result["abstain_reason"] is not None
    assert "negative" in result["abstain_reason"].lower() or "W′" in result["abstain_reason"]


# ---------------------------------------------------------------------------
# 5. CP below physiological minimum → abstained
# ---------------------------------------------------------------------------


def test_low_cp_abstains() -> None:
    """Very low power values that produce CP < 50W must result in abstention."""
    # Very low consistent power with slight downward slope → CP very low
    history = _make_history(
        [60, 180, 300, 600, 1200],
        [30.0, 28.0, 26.0, 24.0, 22.0],
    )
    result = compute_cp_model(history)

    assert result["status"] == "abstained"
    assert result["abstain_reason"] is not None
    assert (
        "CP" in result["abstain_reason"]
        or "physiological" in result["abstain_reason"]
        or "minimum" in result["abstain_reason"]
    )


# ---------------------------------------------------------------------------
# 6. Constant power → degenerate abstain
# ---------------------------------------------------------------------------


def test_constant_power_degenerate() -> None:
    """All bins at identical power → degenerate input → abstained with 'degenerate' in reason."""
    history = _make_history(
        [60, 180, 300],
        [250.0, 250.0, 250.0],
    )
    result = compute_cp_model(history)

    assert result["status"] == "abstained", (
        f"Expected 'abstained' for constant power, got {result['status']!r}"
    )
    assert result["abstain_reason"] is not None
    assert "degenerate" in result["abstain_reason"].lower(), (
        f"Expected 'degenerate' in reason, got: {result['abstain_reason']!r}"
    )


# ---------------------------------------------------------------------------
# 7. run_analysis skips cp_model when no *.fit in workspace
# ---------------------------------------------------------------------------


def test_run_analysis_skips_cp_model_when_no_fit(tmp_path: Path) -> None:
    """When no *.fit files exist beside analysis.db, cp_model must not appear in results."""
    from pipeline.analysis import run_analysis

    # Seed a minimal analysis.db so run_analysis can load data without crash
    db_path = tmp_path / "analysis.db"
    _seed_minimal_db(db_path)

    # Ensure no .fit files exist in tmp_path
    assert list(tmp_path.glob("*.fit")) == [], "Precondition: no .fit files"

    # Patch heavy analysis steps to avoid needing real CPET data
    with _patch_analysis_steps():
        result = run_analysis(db_path)

    assert "cp_model" not in result, (
        "cp_model must not appear in results when no FIT files are present"
    )


# ---------------------------------------------------------------------------
# 8. run_analysis includes cp_model when *.fit files present
# ---------------------------------------------------------------------------


def test_run_analysis_includes_cp_model_when_fit_present(tmp_path: Path) -> None:
    """When *.fit files exist beside analysis.db, cp_model must appear in results."""
    from pipeline.analysis import run_analysis

    db_path = tmp_path / "analysis.db"
    _seed_minimal_db(db_path)

    # Copy a real FIT file to the workspace directory
    real_fit_files = _inscyd_fit_files()
    assert real_fit_files, "Need at least 1 FIT fixture for test 8"
    import shutil
    shutil.copy(real_fit_files[0], tmp_path / real_fit_files[0].name)

    with _patch_analysis_steps():
        result = run_analysis(db_path)

    assert "cp_model" in result, (
        "cp_model must appear in results when FIT files are present"
    )
    assert "cp_result" in result["cp_model"]


# ---------------------------------------------------------------------------
# 9. Persistence round-trip: save_fit_history + compute + verify SQLite row
# ---------------------------------------------------------------------------


def test_persistence_round_trip() -> None:
    """save_fit_history + compute_cp_model result survives a SQLite round-trip."""
    CP = 280.0
    W_PRIME = 25_000.0
    test_bins = [60, 180, 300, 600, 1200]
    powers = [CP + W_PRIME / t for t in test_bins]
    history = _make_history(test_bins, powers)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        save_fit_history(db_path, history)
        cp_result = compute_cp_model(history)

        assert cp_result["status"] == "computed"
        assert cp_result["cp_w"] == pytest.approx(CP, abs=0.01)
        assert cp_result["w_prime_j"] == pytest.approx(W_PRIME, abs=1.0)

        # Verify the fit_history row persisted correctly
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT value FROM analysis_results WHERE category=? AND key=?",
            ("fit_history", "workout_bests"),
        ).fetchone()
        conn.close()

        assert row is not None, "fit_history row not found in analysis_results"
        reloaded = json.loads(row[0])
        assert reloaded["coverage"]["filled_count"] == len(test_bins)
        assert reloaded["bins"][str(test_bins[0])] is not None

    finally:
        db_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 10. powers_used_w values match the input powers for a computed result
# ---------------------------------------------------------------------------


def test_computed_result_powers_used_matches_input() -> None:
    """powers_used_w in a computed result must equal the input best powers exactly."""
    CP = 250.0
    W_PRIME = 20_000.0
    test_bins = [60, 180, 300, 600, 1200]
    powers = [CP + W_PRIME / t for t in test_bins]

    history = _make_history(test_bins, powers)
    result = compute_cp_model(history)

    assert result["status"] == "computed"
    assert result["powers_used_w"] == pytest.approx(powers, abs=1e-9), (
        f"powers_used_w {result['powers_used_w']} does not match input {powers}"
    )
    # abstain_reason must be None for a computed result
    assert result["abstain_reason"] is None, (
        f"Expected abstain_reason=None for computed result, got {result['abstain_reason']!r}"
    )


# ---------------------------------------------------------------------------
# 11. durations_used_s length == points_used
# ---------------------------------------------------------------------------


def test_durations_used_length_equals_points_used() -> None:
    """durations_used_s must have exactly points_used entries in every result."""
    # Test on a computed result
    CP = 280.0
    W_PRIME = 22_000.0
    test_bins = [60, 180, 300, 600]
    powers = [CP + W_PRIME / t for t in test_bins]
    history = _make_history(test_bins, powers)
    result = compute_cp_model(history)

    assert result["status"] == "computed"
    assert len(result["durations_used_s"]) == result["points_used"], (
        f"durations_used_s length {len(result['durations_used_s'])} != "
        f"points_used {result['points_used']}"
    )
    assert len(result["powers_used_w"]) == result["points_used"], (
        f"powers_used_w length {len(result['powers_used_w'])} != "
        f"points_used {result['points_used']}"
    )

    # Also verify for an abstained result (fewer than 3 bins)
    history_short = _make_history([60, 300], [300.0, 250.0])
    result_short = compute_cp_model(history_short)

    assert result_short["status"] == "abstained"
    assert len(result_short["durations_used_s"]) == result_short["points_used"], (
        f"abstained: durations_used_s length {len(result_short['durations_used_s'])} != "
        f"points_used {result_short['points_used']}"
    )


# ---------------------------------------------------------------------------
# 12. Noisy data → suitability="band" (0.80 <= r² < 0.95)
# ---------------------------------------------------------------------------


def test_suitability_band_when_r_squared_between_0_80_and_0_95() -> None:
    """Moderately noisy hyperbolic data must yield suitability='band' (0.80 <= r² < 0.95)."""
    # Alternating +/- noise pushes r² below 0.95 while keeping W'>0 and CP>50.
    # Powers derived empirically: r² ≈ 0.81.
    test_bins = [60, 120, 180, 300, 600, 1200]
    powers = [683.33, 336.67, 451.11, 246.67, 333.33, 226.67]

    history = _make_history(test_bins, powers)
    result = compute_cp_model(history)

    assert result["status"] == "computed", (
        f"Expected 'computed', got abstained: {result.get('abstain_reason')}"
    )
    assert 0.80 <= result["r_squared"] < 0.95, (
        f"Expected 0.80 <= r² < 0.95 for band, got {result['r_squared']}"
    )
    assert result["suitability"]["status"] == "band", (
        f"Expected suitability='band', got {result['suitability']['status']!r}"
    )
    assert result["abstain_reason"] is None


# ---------------------------------------------------------------------------
# 13. Highly noisy data → suitability="hidden" (r² < 0.80), still computed
# ---------------------------------------------------------------------------


def test_suitability_hidden_when_r_squared_below_0_80() -> None:
    """Highly noisy hyperbolic data must yield suitability='hidden' (r² < 0.80) but status='computed'."""
    # Large alternating noise yields r² ≈ 0.56 while keeping W'>0 and CP>50.
    test_bins = [60, 120, 180, 300, 600, 1200]
    powers = [783.33, 236.67, 551.11, 146.67, 413.33, 146.67]

    history = _make_history(test_bins, powers)
    result = compute_cp_model(history)

    assert result["status"] == "computed", (
        f"Expected 'computed', got abstained: {result.get('abstain_reason')}"
    )
    assert result["r_squared"] < 0.80, (
        f"Expected r² < 0.80 for hidden, got {result['r_squared']}"
    )
    assert result["suitability"]["status"] == "hidden", (
        f"Expected suitability='hidden', got {result['suitability']['status']!r}"
    )
    # Even hidden results must have abstain_reason=None (they ARE computed)
    assert result["abstain_reason"] is None, (
        f"Expected abstain_reason=None for computed/hidden result, got {result['abstain_reason']!r}"
    )


# ---------------------------------------------------------------------------
# Helpers for tests 7 & 8
# ---------------------------------------------------------------------------


def _seed_minimal_db(db_path: Path) -> None:
    """Create a minimal analysis.db with all required tables but no data."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    for table_sql in [
        "CREATE TABLE IF NOT EXISTS breath_by_breath (id INTEGER PRIMARY KEY)",
        "CREATE TABLE IF NOT EXISTS blood_samples (id INTEGER PRIMARY KEY)",
        "CREATE TABLE IF NOT EXISTS workout_data (id INTEGER PRIMARY KEY)",
        "CREATE TABLE IF NOT EXISTS subject_info (id INTEGER PRIMARY KEY, age REAL, weight_kg REAL, height_cm REAL, sex TEXT)",
        "CREATE TABLE IF NOT EXISTS workout_protocol (id INTEGER PRIMARY KEY)",
        """CREATE TABLE IF NOT EXISTS analysis_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            UNIQUE(category, key)
        )""",
    ]:
        cursor.execute(table_sql)
    conn.commit()
    conn.close()


def _patch_analysis_steps():
    """Context manager: patch all heavy analysis functions so run_analysis completes fast."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        empty: dict = {}
        zone_empty: dict = {"zones": []}
        with (
            patch("pipeline.analysis.analyze_lactate", return_value=empty),
            patch("pipeline.analysis.analyze_clearance", return_value=empty),
            patch("pipeline.analysis.analyze_vo2max", return_value=empty),
            patch("pipeline.analysis.analyze_ventilatory_thresholds", return_value=empty),
            patch("pipeline.analysis.analyze_substrate", return_value=empty),
            patch("pipeline.analysis.analyze_efficiency", return_value=empty),
            patch("pipeline.analysis.analyze_hr", return_value=empty),
            patch("pipeline.analysis.compute_training_zones", return_value=zone_empty),
            patch("pipeline.analysis.analyze_energy_system", return_value=empty),
            patch("pipeline.analysis._infer_protocol_metadata", return_value=empty),
            patch("pipeline.analysis._build_protocol_metric_suitability", return_value=empty),
        ):
            yield

    return _ctx()
