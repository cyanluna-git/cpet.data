"""
pipeline.parsers.fit — Garmin FIT file parser + block segmentation.

Parses FIT workout files into record and lap DataFrames, then assigns
block/step labels via target power transition detection.

Canonical source: hong.changsun/analysis/parsers.py
"""

from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import fitparse

KST = timezone(timedelta(hours=9))


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


def parse_fit(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse FIT workout file into workout records and lap DataFrames.

    Args:
        path: Explicit path to the .fit file.

    Returns:
        Tuple of (workout_df, laps_df).
    """
    path = Path(path)
    fitfile = fitparse.FitFile(str(path))

    # --- Records ---
    records: list[dict[str, Any]] = []
    for rec in fitfile.get_messages("record"):
        row: dict[str, Any] = {}
        for field in rec.fields:
            if field.name in (
                "timestamp",
                "power",
                "heart_rate",
                "cadence",
                "enhanced_speed",
                "distance",
                "target_power",
            ):
                row[field.name] = field.value
        if "timestamp" not in row:
            continue
        records.append(row)

    workout_df = pd.DataFrame(records)

    # UTC -> KST
    workout_df["timestamp_utc"] = pd.to_datetime(workout_df["timestamp"])
    workout_df["timestamp_kst"] = workout_df["timestamp_utc"] + timedelta(hours=9)

    # Elapsed seconds from first record
    t0 = workout_df["timestamp_kst"].iloc[0]
    workout_df["elapsed_s"] = (workout_df["timestamp_kst"] - t0).dt.total_seconds()

    # Rename columns
    workout_df = workout_df.rename(
        columns={
            "power": "power_w",
            "heart_rate": "hr_bpm",
            "cadence": "cadence_rpm",
            "enhanced_speed": "speed_mps",
            "distance": "distance_m",
            "target_power": "target_power_w",
        }
    )

    cols = [
        "timestamp_kst",
        "elapsed_s",
        "power_w",
        "target_power_w",
        "hr_bpm",
        "cadence_rpm",
        "speed_mps",
        "distance_m",
    ]
    workout_df = workout_df[cols].copy()

    # --- Laps ---
    laps: list[dict[str, Any]] = []
    for i, lap in enumerate(fitfile.get_messages("lap"), 1):
        row: dict[str, Any] = {"lap_number": i}
        for field in lap.fields:
            if field.name in (
                "timestamp",
                "total_timer_time",
                "avg_power",
                "avg_heart_rate",
            ):
                row[field.name] = field.value
        if "timestamp" in row:
            row["end_time_utc"] = row.pop("timestamp")
            row["end_time_kst"] = pd.Timestamp(row["end_time_utc"]) + timedelta(
                hours=9
            )
            duration = row.get("total_timer_time", 0) or 0
            row["start_time_kst"] = row["end_time_kst"] - timedelta(seconds=duration)
            row["duration_s"] = duration
        laps.append(row)

    laps_df = pd.DataFrame(laps)

    return workout_df, laps_df


def segment_blocks(
    workout_df: pd.DataFrame,
    laps_df: pd.DataFrame,
    tolerance_s: int = 3,
) -> pd.DataFrame:
    """Assign block and step labels to each workout record.

    Primary: target_power transitions.
    Validation: cross-check with lap boundaries.

    Args:
        workout_df: FIT workout records DataFrame.
        laps_df: FIT lap records DataFrame.
        tolerance_s: Seconds tolerance for lap cross-validation.

    Returns:
        workout_df with block and step columns added.
    """
    df = workout_df.copy()
    segments = _build_target_segments(df)

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

    block_labels: list[str] = []
    step_labels: list[int] = []
    step_counts = {"block_1": 0, "block_2": 0, "block_3": 0}

    for idx, seg in enumerate(segments):
        target = seg["target_power"]
        if idx < ramp_start:
            if target <= 0:
                block_labels.append("recovery_1")
                step_labels.append(0)
            else:
                step_counts["block_1"] += 1
                block_labels.append("block_1")
                step_labels.append(step_counts["block_1"])
        elif idx < block3_start:
            if target <= 0:
                block_labels.append("recovery_2")
                step_labels.append(0)
            else:
                step_counts["block_2"] += 1
                block_labels.append("block_2")
                step_labels.append(step_counts["block_2"])
        else:
            if target <= 0:
                block_labels.append("recovery_2")
                step_labels.append(0)
            else:
                step_counts["block_3"] += 1
                block_labels.append("block_3")
                step_labels.append(step_counts["block_3"])

    # Apply labels to each record
    df["block"] = ""
    df["step"] = 0
    for i, seg in enumerate(segments):
        df.loc[seg["idx_start"] : seg["idx_end"], "block"] = block_labels[i]
        df.loc[seg["idx_start"] : seg["idx_end"], "step"] = step_labels[i]

    # --- Post-processing: detect recovery_2 from power dropout ---
    b2_mask = df["block"] == "block_2"
    if b2_mask.any():
        b2_indices = df.index[b2_mask]
        power_zero = df.loc[b2_indices, "power_w"].eq(0)

        consecutive = 0
        recovery_start = None
        for idx in reversed(b2_indices):
            if power_zero.loc[idx]:
                consecutive += 1
                recovery_start = idx
            else:
                if consecutive >= 10:
                    break
                consecutive = 0
                recovery_start = None

        if recovery_start is not None and consecutive >= 10:
            df.loc[recovery_start : b2_indices[-1], "block"] = "recovery_2"
            df.loc[recovery_start : b2_indices[-1], "step"] = 0

    # --- Validation: cross-check with laps ---
    warnings = _cross_validate(df, laps_df, tolerance_s)
    for w in warnings:
        print(f"  [WARN] {w}")

    return df


def _cross_validate(
    df: pd.DataFrame,
    laps_df: pd.DataFrame,
    tolerance_s: int,
) -> list[str]:
    """Cross-validate block assignments against lap boundaries."""
    warnings: list[str] = []

    lap_block_map: dict[int, str] = {}
    for _, lap in laps_df.iterrows():
        start = lap["start_time_kst"]
        end = lap["end_time_kst"]
        mid = start + (end - start) / 2

        closest = (df["timestamp_kst"] - mid).abs().idxmin()
        block = df.loc[closest, "block"]
        lap_num = lap["lap_number"]
        lap_block_map[lap_num] = block

    block_laps: dict[str, list[int]] = {}
    for lap_num, block in lap_block_map.items():
        block_laps.setdefault(block, []).append(lap_num)

    for block, lap_list in sorted(block_laps.items()):
        expected = list(range(min(lap_list), max(lap_list) + 1))
        if sorted(lap_list) != expected:
            warnings.append(f"Block '{block}' has non-contiguous laps: {lap_list}")

    return warnings
