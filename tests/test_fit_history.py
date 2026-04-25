"""Tests for pipeline.fit_history."""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from pipeline.fit_history import (
    DURATION_BINS_S,
    best_rolling_power,
    extract_workout_bests,
    save_fit_history,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
INSCYD_PPD_DIR = FIXTURES_DIR / "inscyd_ppd"


def _fit_files() -> list[Path]:
    # Raw files may sit directly in inscyd_ppd/ or in a raw/ subdirectory.
    raw_dir = INSCYD_PPD_DIR / "raw"
    search_dir = raw_dir if raw_dir.is_dir() else INSCYD_PPD_DIR
    return sorted(search_dir.glob("*.fit"))


# ---------------------------------------------------------------------------
# 1. Empty input
# ---------------------------------------------------------------------------


def test_empty_input() -> None:
    result = extract_workout_bests([])

    assert result["coverage"]["quality"] == "none"
    assert result["coverage"]["filled_count"] == 0
    assert result["coverage"]["ratio"] == 0.0
    # All bins present, all None
    assert set(result["bins"].keys()) == {str(d) for d in DURATION_BINS_S}
    assert all(v is None for v in result["bins"].values())
    assert result["sessions"] == []


# ---------------------------------------------------------------------------
# 2. Two FIT files fill ≥7 bins
# ---------------------------------------------------------------------------


def test_two_fit_files_fill_bins() -> None:
    fit_files = _fit_files()
    assert len(fit_files) >= 2, "Need at least 2 FIT fixtures"

    result = extract_workout_bests(fit_files)

    filled_count = result["coverage"]["filled_count"]
    assert filled_count >= 7, (
        f"Expected ≥7 bins filled, got {filled_count}. "
        f"Bins: {result['bins']}"
    )
    assert result["coverage"]["quality"] in ("full", "partial")


# ---------------------------------------------------------------------------
# 3. Every filled bin has best_w (float) and source_file (str)
# ---------------------------------------------------------------------------


def test_bin_has_best_w_and_source_file() -> None:
    fit_files = _fit_files()
    result = extract_workout_bests(fit_files)

    for duration_key, value in result["bins"].items():
        if value is not None:
            assert isinstance(value["best_w"], float), (
                f"bin {duration_key}: best_w should be float, got {type(value['best_w'])}"
            )
            assert isinstance(value["source_file"], str), (
                f"bin {duration_key}: source_file should be str, got {type(value['source_file'])}"
            )
            assert value["best_w"] > 0.0, (
                f"bin {duration_key}: best_w should be positive"
            )


# ---------------------------------------------------------------------------
# 4. Dedup by filename: same path twice → only one session entry
# ---------------------------------------------------------------------------


def test_dedup_by_filename() -> None:
    fit_files = _fit_files()
    assert fit_files, "Need at least 1 FIT fixture"

    single = fit_files[0]
    result = extract_workout_bests([single, single])

    assert len(result["sessions"]) == 1, (
        f"Duplicate path should produce 1 session, got {len(result['sessions'])}"
    )


# ---------------------------------------------------------------------------
# 5. save_fit_history writes to SQLite; JSON round-trip verifiable
# ---------------------------------------------------------------------------


def test_save_and_reload() -> None:
    fit_files = _fit_files()
    history = extract_workout_bests(fit_files)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        save_fit_history(db_path, history)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT value FROM analysis_results WHERE category=? AND key=?",
            ("fit_history", "workout_bests"),
        ).fetchone()
        conn.close()

        assert row is not None, "Row not found in analysis_results"
        reloaded = json.loads(row[0])

        assert reloaded["coverage"]["quality"] == history["coverage"]["quality"]
        assert reloaded["coverage"]["filled_count"] == history["coverage"]["filled_count"]
        assert set(reloaded["bins"].keys()) == set(history["bins"].keys())
        assert len(reloaded["sessions"]) == len(history["sessions"])
    finally:
        db_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 6. Coverage quality thresholds
# ---------------------------------------------------------------------------


def test_coverage_quality_thresholds() -> None:
    """Quality strings are computed correctly from ratio."""
    from pipeline.fit_history import DURATION_BINS_S

    total = len(DURATION_BINS_S)  # 9

    def _make_result(filled: int) -> dict:
        # Build a synthetic result with *filled* bins filled
        bins_s = list(DURATION_BINS_S)
        bins: dict = {}
        for i, d in enumerate(bins_s):
            if i < filled:
                bins[str(d)] = {"best_w": 300.0, "source_file": "synthetic.fit"}
            else:
                bins[str(d)] = None
        ratio = filled / total
        if ratio >= 0.8:
            quality = "full"
        elif ratio >= 0.4:
            quality = "partial"
        elif ratio > 0:
            quality = "sparse"
        else:
            quality = "none"
        return {"bins": bins, "coverage": {"filled_count": filled, "total_bins": total, "ratio": round(ratio, 4), "quality": quality}, "sessions": []}

    assert _make_result(0)["coverage"]["quality"] == "none"
    assert _make_result(1)["coverage"]["quality"] == "sparse"    # 1/9 ≈ 0.11
    assert _make_result(3)["coverage"]["quality"] == "sparse"    # 3/9 ≈ 0.33
    assert _make_result(4)["coverage"]["quality"] == "partial"   # 4/9 ≈ 0.44
    assert _make_result(7)["coverage"]["quality"] == "partial"   # 7/9 ≈ 0.778 < 0.8
    assert _make_result(8)["coverage"]["quality"] == "full"      # 8/9 ≈ 0.889 ≥ 0.8
    assert _make_result(9)["coverage"]["quality"] == "full"      # 9/9 = 1.0


# ---------------------------------------------------------------------------
# 7. HR-only FIT file: session appears but contributes no bins
# ---------------------------------------------------------------------------


def test_hr_only_fit_file_appears_in_sessions_but_contributes_no_bins(
    tmp_path: Path,
) -> None:
    """A FIT file without power_w should appear in sessions with no bins_contributed."""
    dummy_fit = tmp_path / "hr_only.fit"
    dummy_fit.write_bytes(b"")  # content does not matter; parse_fit is patched

    # HR-only DataFrame: no power_w column, but has elapsed_s
    hr_df = pd.DataFrame({"elapsed_s": list(range(200)), "heart_rate_bpm": [150] * 200})
    empty_laps = pd.DataFrame()

    with patch("pipeline.fit_history.parse_fit", return_value=(hr_df, empty_laps)):
        result = extract_workout_bests([dummy_fit])

    assert len(result["sessions"]) == 1, "HR-only file must still produce a session entry"
    session = result["sessions"][0]
    assert session["bins_contributed"] == [], (
        "HR-only file must not contribute to any power bin"
    )
    assert result["coverage"]["filled_count"] == 0
    assert result["coverage"]["quality"] == "none"


# ---------------------------------------------------------------------------
# 8. Quality boundary values 0.8 and 0.4 via extract_workout_bests
# ---------------------------------------------------------------------------


def test_quality_boundaries_via_extract_workout_bests(tmp_path: Path) -> None:
    """Exact ratio 0.8 → 'full' and 0.4 → 'partial' as computed by extract_workout_bests."""
    dummy_fit = tmp_path / "strong.fit"
    dummy_fit.write_bytes(b"")

    # 2000-row series; bins 1..4 fill, 999_997..999_999 cannot (too short)
    n_rows = 2000
    power_df = pd.DataFrame({
        "elapsed_s": list(range(n_rows)),
        "power_w": [300.0] * n_rows,
    })
    empty_laps = pd.DataFrame()

    with patch("pipeline.fit_history.parse_fit", return_value=(power_df, empty_laps)):
        # 5-bin tuple: 4 short bins fill, 1 impossibly long bin does not → ratio = 4/5 = 0.8
        result_08 = extract_workout_bests([dummy_fit], bins=(1, 5, 15, 30, 999_999))
        assert result_08["coverage"]["filled_count"] == 4, (
            f"Expected 4 filled bins, got {result_08['coverage']['filled_count']}"
        )
        assert result_08["coverage"]["ratio"] == 0.8
        assert result_08["coverage"]["quality"] == "full", (
            f"ratio=0.8 must be 'full', got {result_08['coverage']['quality']!r}"
        )

        # 5-bin tuple: 2 short bins fill, 3 impossibly long bins don't → ratio = 2/5 = 0.4
        result_04 = extract_workout_bests([dummy_fit], bins=(1, 5, 999_997, 999_998, 999_999))
        assert result_04["coverage"]["filled_count"] == 2, (
            f"Expected 2 filled bins, got {result_04['coverage']['filled_count']}"
        )
        assert result_04["coverage"]["ratio"] == 0.4
        assert result_04["coverage"]["quality"] == "partial", (
            f"ratio=0.4 must be 'partial', got {result_04['coverage']['quality']!r}"
        )


# ---------------------------------------------------------------------------
# 9. File shorter than longest bin: that bin remains None
# ---------------------------------------------------------------------------


def test_short_file_leaves_long_bin_none() -> None:
    """best_rolling_power returns None when the series is shorter than the window."""
    # Short series: 100 rows — cannot fill 1200-s bin
    short_df = pd.DataFrame({
        "elapsed_s": list(range(100)),
        "power_w": [250.0] * 100,
    })

    assert best_rolling_power(short_df, 1200) is None, (
        "Series of 100 rows cannot satisfy 1200-s window"
    )
    # But short bins within range must still compute
    result_1s = best_rolling_power(short_df, 1)
    assert result_1s is not None
    assert result_1s == pytest.approx(250.0)


def test_short_file_integration_leaves_1200_bin_none(tmp_path: Path) -> None:
    """extract_workout_bests with a 100-row file leaves the 1200-s bin as None."""
    dummy_fit = tmp_path / "short_ride.fit"
    dummy_fit.write_bytes(b"")

    short_df = pd.DataFrame({
        "elapsed_s": list(range(100)),
        "power_w": [250.0] * 100,
    })
    empty_laps = pd.DataFrame()

    with patch("pipeline.fit_history.parse_fit", return_value=(short_df, empty_laps)):
        result = extract_workout_bests([dummy_fit])

    assert result["bins"]["1200"] is None, (
        "1200-s bin must be None for a 100-row file"
    )
    # Short bins (1, 5, 15, 30) should fill
    for short_bin in ("1", "5", "15", "30"):
        assert result["bins"][short_bin] is not None, (
            f"Bin {short_bin}s should fill from a 100-row file"
        )
