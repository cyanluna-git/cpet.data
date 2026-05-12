"""tests/test_analyze_hr_new_keys.py — Unit tests for resting_hr_bpm and hrr1_bpm.

Task #2796: feat(analysis): add HRR1 and resting HR to analyze_hr()

Test inventory:
1. test_resting_hr_bpm_mean_of_first_60s_in_rest_block
2. test_resting_hr_bpm_none_when_no_rest_block
3. test_hrr1_bpm_computed_from_recovery_1_block
4. test_hrr1_bpm_none_when_no_recovery_1_block
5. test_hrr1_bpm_uses_last_row_within_60s_window
6. test_resting_hr_bpm_uses_exactly_60s_boundary
7. test_hr_recovery_dict_structure_unchanged
"""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.analysis import analyze_hr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_subject(age: float = 30, max_hr: float = 185) -> pd.DataFrame:
    return pd.DataFrame([{"age": age, "max_hr": max_hr}])


def _make_workout(*rows: dict) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    # Ensure all columns required by analyze_hr exist with sane defaults
    for col in ["block", "step", "hr_bpm", "elapsed_s", "target_power_w", "power_w"]:
        if col not in df.columns:
            df[col] = 0
    return df


# ---------------------------------------------------------------------------
# Tests: resting_hr_bpm
# ---------------------------------------------------------------------------

class TestRestingHrBpm:
    def test_resting_hr_bpm_mean_of_first_60s_in_rest_block(self):
        """Mean HR over rows with elapsed_s in [t0, t0+60] in the rest block."""
        rows = [
            # rest block: 3 rows within first 60 s
            {"block": "rest", "step": 0, "hr_bpm": 60.0, "elapsed_s": 0.0},
            {"block": "rest", "step": 0, "hr_bpm": 62.0, "elapsed_s": 30.0},
            {"block": "rest", "step": 0, "hr_bpm": 64.0, "elapsed_s": 60.0},
            # row beyond 60 s — should be excluded
            {"block": "rest", "step": 0, "hr_bpm": 90.0, "elapsed_s": 61.0},
        ]
        workout = _make_workout(*rows)
        result = analyze_hr(workout, _make_subject())
        # mean of 60, 62, 64 = 62.0
        assert result["resting_hr_bpm"] == pytest.approx(62.0, abs=0.2)

    def test_resting_hr_bpm_none_when_no_rest_block(self):
        """resting_hr_bpm is None when the workout has no rest block."""
        rows = [
            {"block": "block_1", "step": 1, "hr_bpm": 130.0, "elapsed_s": 0.0},
            {"block": "block_1", "step": 1, "hr_bpm": 135.0, "elapsed_s": 30.0},
        ]
        workout = _make_workout(*rows)
        result = analyze_hr(workout, _make_subject())
        assert result["resting_hr_bpm"] is None

    def test_resting_hr_bpm_uses_exactly_60s_boundary(self):
        """Row at exactly t0+60 is included; row at t0+60+epsilon is excluded."""
        rows = [
            {"block": "rest", "step": 0, "hr_bpm": 55.0, "elapsed_s": 100.0},
            {"block": "rest", "step": 0, "hr_bpm": 65.0, "elapsed_s": 160.0},  # exactly 60s after t0=100
            {"block": "rest", "step": 0, "hr_bpm": 99.0, "elapsed_s": 161.0},  # just over boundary
        ]
        workout = _make_workout(*rows)
        result = analyze_hr(workout, _make_subject())
        # mean of 55 and 65 = 60.0
        assert result["resting_hr_bpm"] == pytest.approx(60.0, abs=0.2)


# ---------------------------------------------------------------------------
# Tests: hrr1_bpm
# ---------------------------------------------------------------------------

class TestHrr1Bpm:
    def test_hrr1_bpm_none_when_no_recovery_1_block(self):
        """hrr1_bpm is None when there is no recovery_1 block."""
        rows = [
            {"block": "block_1", "step": 1, "hr_bpm": 150.0, "elapsed_s": 0.0},
        ]
        workout = _make_workout(*rows)
        result = analyze_hr(workout, _make_subject())
        assert result["hrr1_bpm"] is None

    def test_hrr1_bpm_computed_from_recovery_1_block(self):
        """HRR1 = first HR in recovery_1 minus HR at 60 s into recovery."""
        rows = [
            # recovery_1 starts at elapsed_s=500; first HR = 170
            {"block": "recovery_1", "step": 0, "hr_bpm": 170.0, "elapsed_s": 500.0},
            {"block": "recovery_1", "step": 0, "hr_bpm": 155.0, "elapsed_s": 530.0},
            {"block": "recovery_1", "step": 0, "hr_bpm": 145.0, "elapsed_s": 560.0},
            # last row within 60 s window (t0+60 = 560)
            {"block": "recovery_1", "step": 0, "hr_bpm": 130.0, "elapsed_s": 580.0},  # beyond 60s
        ]
        workout = _make_workout(*rows)
        result = analyze_hr(workout, _make_subject())
        # window rows: elapsed <= 500+60=560 → rows at 500, 530, 560
        # hr_at_60 = last row in window = 145.0
        # hrr1 = 170.0 - 145.0 = 25.0
        assert result["hrr1_bpm"] == pytest.approx(25.0, abs=0.2)

    def test_hrr1_bpm_uses_last_row_within_60s_window(self):
        """When recovery_1 has rows beyond 60 s, only the last row inside window is used."""
        rows = [
            {"block": "recovery_1", "step": 0, "hr_bpm": 180.0, "elapsed_s": 0.0},
            {"block": "recovery_1", "step": 0, "hr_bpm": 160.0, "elapsed_s": 59.0},
            {"block": "recovery_1", "step": 0, "hr_bpm": 150.0, "elapsed_s": 60.0},  # boundary included
            {"block": "recovery_1", "step": 0, "hr_bpm": 100.0, "elapsed_s": 61.0},  # excluded
        ]
        workout = _make_workout(*rows)
        result = analyze_hr(workout, _make_subject())
        # hr_at_60 = last row in window (elapsed <=60) = 150.0
        # hrr1 = 180.0 - 150.0 = 30.0
        assert result["hrr1_bpm"] == pytest.approx(30.0, abs=0.2)

    def test_hrr1_bpm_uses_last_row_of_block_when_all_within_60s(self):
        """When all rows of recovery_1 are within 60 s, use the very last row."""
        rows = [
            {"block": "recovery_1", "step": 0, "hr_bpm": 175.0, "elapsed_s": 0.0},
            {"block": "recovery_1", "step": 0, "hr_bpm": 165.0, "elapsed_s": 20.0},
            {"block": "recovery_1", "step": 0, "hr_bpm": 155.0, "elapsed_s": 40.0},
        ]
        workout = _make_workout(*rows)
        result = analyze_hr(workout, _make_subject())
        # all rows within 60s window, hr_at_60 = last row = 155.0
        # hrr1 = 175.0 - 155.0 = 20.0
        assert result["hrr1_bpm"] == pytest.approx(20.0, abs=0.2)


# ---------------------------------------------------------------------------
# Tests: hr_recovery dict structure unchanged
# ---------------------------------------------------------------------------

class TestHrRecoveryStructureUnchanged:
    def test_hr_recovery_dict_structure_preserved(self):
        """hr_recovery still contains start_hr_bpm, end_hr_bpm, delta_bpm for each block."""
        rows = [
            {"block": "recovery_1", "step": 0, "hr_bpm": 170.0, "elapsed_s": 0.0},
            {"block": "recovery_1", "step": 0, "hr_bpm": 160.0, "elapsed_s": 30.0},
            {"block": "recovery_1", "step": 0, "hr_bpm": 140.0, "elapsed_s": 60.0},
        ]
        workout = _make_workout(*rows)
        result = analyze_hr(workout, _make_subject())

        assert "hr_recovery" in result
        rec = result["hr_recovery"]
        assert "recovery_1" in rec
        r1 = rec["recovery_1"]
        assert "start_hr_bpm" in r1
        assert "end_hr_bpm" in r1
        assert "delta_bpm" in r1
        # delta = end - start
        assert r1["delta_bpm"] == pytest.approx(r1["end_hr_bpm"] - r1["start_hr_bpm"], abs=0.1)

    def test_all_new_keys_present_in_result(self):
        """analyze_hr always returns resting_hr_bpm and hrr1_bpm keys."""
        rows = [
            {"block": "block_1", "step": 1, "hr_bpm": 140.0, "elapsed_s": 0.0},
        ]
        workout = _make_workout(*rows)
        result = analyze_hr(workout, _make_subject())
        assert "resting_hr_bpm" in result
        assert "hrr1_bpm" in result
