"""
pipeline.parsers — Dispatch layer for workspace file discovery and parsing.

All parsers accept explicit Path parameters; no global DATA_DIR.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.parsers.cosmed import parse_cosmed
from pipeline.parsers.fit import parse_fit, segment_blocks
from pipeline.parsers.lactate import parse_lactate
from pipeline.parsers.zwo import parse_zwo


@dataclass
class ParsedData:
    """Container for all parsed data from a workspace."""

    cosmed_df: pd.DataFrame
    subject_info: dict[str, Any]

    # Optional sources
    protocol_df: pd.DataFrame | None = None
    workout_df: pd.DataFrame | None = None
    laps_df: pd.DataFrame | None = None
    blood_df: pd.DataFrame | None = None
    blood_info: dict[str, Any] = field(default_factory=dict)

    @property
    def has_fit(self) -> bool:
        return self.workout_df is not None and not self.workout_df.empty

    @property
    def has_lactate(self) -> bool:
        return self.blood_df is not None and not self.blood_df.empty

    @property
    def has_protocol(self) -> bool:
        return self.protocol_df is not None and not self.protocol_df.empty


def _find_first(workspace: Path, patterns: list[str]) -> Path | None:
    """Return the first matching file under workspace, or None."""
    for pattern in patterns:
        matches = sorted(workspace.glob(pattern))
        if matches:
            return matches[0]
    return None


def parse_workspace(workspace: Path) -> ParsedData:
    """Discover and parse all available data files in a workspace directory.

    The workspace must contain at least one COSMED XLSX file.
    FIT, ZWO, and lactate files are optional.

    Args:
        workspace: Path to directory containing raw data files.

    Returns:
        ParsedData with all available parsed sources.
    """
    workspace = Path(workspace).resolve()

    # Look for raw/ subdirectory first, fall back to workspace root
    raw_dir = workspace / "raw"
    search_dir = raw_dir if raw_dir.is_dir() else workspace

    # --- COSMED XLSX (required) ---
    cosmed_path = _find_first(search_dir, ["*CPET BxB*.xlsx", "*CPET*.xlsx"])
    if cosmed_path is None:
        raise FileNotFoundError(
            f"No COSMED XLSX file found in {search_dir}. "
            "Expected filename pattern: *CPET BxB*.xlsx"
        )
    cosmed_df, subject_info = parse_cosmed(cosmed_path)

    # --- FIT file (optional) ---
    fit_path = _find_first(search_dir, ["*.fit"])
    workout_df = None
    laps_df = None
    if fit_path is not None:
        workout_df, laps_df = parse_fit(fit_path)

    # --- ZWO protocol (optional) ---
    protocol_df = None
    zwo_path = _find_first(search_dir, ["*.zwo"])
    if zwo_path is not None:
        protocol_df = parse_zwo(zwo_path)
    elif workout_df is not None:
        # Synthesize protocol from FIT target power transitions
        protocol_df = parse_zwo(None, workout_df=workout_df)

    # --- Segment blocks if we have both FIT data and protocol ---
    if workout_df is not None and laps_df is not None:
        workout_df = segment_blocks(workout_df, laps_df)

    # --- Backfill COSMED power from FIT if needed ---
    if workout_df is not None:
        cosmed_df = _backfill_power(cosmed_df, workout_df)

    # --- Lactate data (optional) ---
    blood_df = None
    blood_info: dict[str, Any] = {}
    lactate_md_path = _find_first(search_dir, ["lactate_data.md", "*.md"])
    lactate_xlsx_path = _find_first(search_dir, ["*LT*.xlsx", "*Test_LT*.xlsx"])
    # Exclude COSMED xlsx from lactate search
    if lactate_xlsx_path is not None and lactate_xlsx_path == cosmed_path:
        lactate_xlsx_path = None

    if lactate_md_path is not None:
        blood_df, blood_info = parse_lactate(md_path=lactate_md_path)
    elif lactate_xlsx_path is not None:
        blood_df, blood_info = parse_lactate(xlsx_path=lactate_xlsx_path)

    return ParsedData(
        cosmed_df=cosmed_df,
        subject_info=subject_info,
        protocol_df=protocol_df,
        workout_df=workout_df,
        laps_df=laps_df,
        blood_df=blood_df,
        blood_info=blood_info,
    )


def _backfill_power(
    cosmed_df: pd.DataFrame,
    workout_df: pd.DataFrame,
) -> pd.DataFrame:
    """Backfill COSMED bike_power_w from FIT data via merge_asof."""
    if "bike_power_w" not in cosmed_df.columns:
        cosmed_df["bike_power_w"] = None
    if "cadence_rpm" not in cosmed_df.columns:
        cosmed_df["cadence_rpm"] = None

    if cosmed_df["bike_power_w"].notna().sum() > 0:
        return cosmed_df
    if "timestamp_kst" not in cosmed_df.columns:
        return cosmed_df

    workout_align = (
        workout_df[["timestamp_kst", "power_w", "target_power_w", "cadence_rpm"]]
        .dropna(subset=["timestamp_kst"])
        .sort_values("timestamp_kst")
        .rename(
            columns={
                "power_w": "fit_power_w",
                "target_power_w": "fit_target_power_w",
                "cadence_rpm": "fit_cadence_rpm",
            }
        )
    )
    bxb_align = cosmed_df.sort_values("timestamp_kst").copy()
    merged = pd.merge_asof(
        bxb_align,
        workout_align,
        on="timestamp_kst",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=20),
    )
    cosmed_df = merged.sort_index()
    cosmed_df["bike_power_w"] = (
        cosmed_df["bike_power_w"]
        .fillna(cosmed_df.get("fit_power_w"))
        .fillna(cosmed_df.get("fit_target_power_w"))
    )
    cosmed_df["cadence_rpm"] = cosmed_df["cadence_rpm"].fillna(
        cosmed_df.get("fit_cadence_rpm")
    )
    cosmed_df = cosmed_df.drop(
        columns=["fit_power_w", "fit_target_power_w", "fit_cadence_rpm"],
        errors="ignore",
    )
    return cosmed_df
