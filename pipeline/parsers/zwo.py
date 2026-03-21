"""
pipeline.parsers.zwo — ZWO workout protocol parser.

Parses Zwift Workout XML files into stage DataFrames.
Falls back to synthesizing protocol from FIT target power transitions.

Canonical source: hong.changsun/analysis/parsers.py
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pandas as pd


def _build_target_segments(workout_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Collapse FIT target power changes into contiguous protocol segments."""
    tp = workout_df["target_power_w"].fillna(0).astype(int)
    transitions = tp.ne(tp.shift()).cumsum()
    segments: list[dict[str, Any]] = []
    for seg_id in transitions.unique():
        mask = transitions == seg_id
        idx_start = mask.idxmax()
        idx_end = mask[::-1].idxmax()
        target = int(tp.iloc[idx_start])
        segments.append(
            {
                "seg_id": int(seg_id),
                "idx_start": int(idx_start),
                "idx_end": int(idx_end),
                "target_power": target,
                "duration_s": int(idx_end - idx_start + 1),
            }
        )
    return segments


def _synthesize_protocol_from_fit(
    workout_df: pd.DataFrame,
) -> pd.DataFrame:
    """Synthesize protocol stages from FIT target power transitions."""
    segments = _build_target_segments(workout_df)
    ramp_start = None
    for idx in range(len(segments) - 3):
        window = segments[idx : idx + 4]
        if all(
            seg["target_power"] > 0 and seg["duration_s"] <= 60 for seg in window
        ):
            ramp_start = idx
            break
    if ramp_start is None:
        long_positive = [
            i
            for i, seg in enumerate(segments)
            if seg["target_power"] > 0 and seg["duration_s"] >= 120
        ]
        ramp_start = long_positive[-1] + 1 if long_positive else 0

    block3_start = len(segments)
    for idx in range(ramp_start + 1, len(segments)):
        seg = segments[idx]
        if seg["target_power"] > 0 and seg["duration_s"] >= 120:
            block3_start = idx
            break

    stages: list[dict[str, Any]] = []
    step_counts = {"block_1": 0, "block_2": 0, "block_3": 0}
    for idx, seg in enumerate(segments):
        target = seg["target_power"]
        duration_s = float(seg["duration_s"])
        if idx < ramp_start:
            if target <= 0:
                block = "recovery_1"
                step = 0
                stage_type = "freeride"
            else:
                block = "block_1"
                step_counts[block] += 1
                step = step_counts[block]
                stage_type = "steady_state"
        elif idx < block3_start:
            if target <= 0:
                block = "recovery_2"
                step = 0
                stage_type = "freeride"
            else:
                block = "block_2"
                step_counts[block] += 1
                step = step_counts[block]
                stage_type = "ramp"
        else:
            if target <= 0:
                block = "recovery_2"
                step = 0
                stage_type = "freeride"
            else:
                block = "block_3"
                step_counts[block] += 1
                step = step_counts[block]
                stage_type = "steady_state"

        stages.append(
            {
                "block": block,
                "step": step,
                "power_normalized": float(target),
                "duration_s": duration_s,
                "stage_type": stage_type,
            }
        )
    return pd.DataFrame(stages)


def parse_zwo(
    path: Path | None = None,
    *,
    workout_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Parse ZWO workout protocol XML into a DataFrame of stages.

    Args:
        path: Explicit path to the .zwo file. If None, synthesizes from workout_df.
        workout_df: FIT workout DataFrame for synthesis fallback.

    Returns:
        DataFrame with columns: block, step, power_normalized, duration_s, stage_type.
    """
    if path is None:
        if workout_df is not None:
            return _synthesize_protocol_from_fit(workout_df)
        raise ValueError("Either path or workout_df must be provided")

    path = Path(path)
    tree = ET.parse(str(path))
    workout = tree.find("workout")
    if workout is None:
        raise ValueError("No <workout> element found in ZWO file")

    stages: list[dict[str, Any]] = []
    block = 1
    step = 0
    freeride_count = 0

    for elem in workout:
        tag = elem.tag
        if tag == "SteadyState":
            step += 1
            stages.append(
                {
                    "block": f"block_{block}",
                    "step": step,
                    "power_normalized": float(elem.get("Power", 0)),
                    "duration_s": float(elem.get("Duration", 0)),
                    "stage_type": "steady_state",
                }
            )
        elif tag == "FreeRide":
            freeride_count += 1
            stages.append(
                {
                    "block": f"recovery_{freeride_count}",
                    "step": 0,
                    "power_normalized": 0.0,
                    "duration_s": float(elem.get("Duration", 0)),
                    "stage_type": "freeride",
                }
            )
            block += 1
            step = 0

    return pd.DataFrame(stages)
