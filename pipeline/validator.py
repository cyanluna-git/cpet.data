"""
pipeline.validator — Lightweight QC range checks for parsed CPET data.

Validates breath-by-breath and blood sample data for physiological plausibility.
Simplified from the platform's DataValidator service.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class ValidationResult:
    """Container for validation results."""

    is_valid: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# Physiological range limits
QC_RANGES = {
    "vo2_ml": (50, 7000),
    "vco2_ml": (50, 8000),
    "rq": (0.5, 1.6),
    "hr_bpm": (30, 230),
    "ve_lmin": (3, 250),
    "fat_gmin": (-0.5, 3.0),
    "cho_gmin": (-0.5, 12.0),
    "bike_power_w": (0, 2500),
    "lactate_mmol": (0.0, 30.0),
    "glucose_mmol": (0.5, 30.0),
}

# Minimum required BxB records for meaningful analysis
MIN_BXB_RECORDS = 50
MIN_EXERCISE_DURATION_S = 300
SENSOR_DROPOUT_THRESHOLD = 0.10


def validate_workspace(workspace: Path) -> ValidationResult:
    """Validate a workspace directory for pipeline execution.

    Checks:
    - COSMED XLSX file exists
    - BxB data has minimum record count
    - Physiological values are within plausible ranges
    - Sensor dropout rates are acceptable

    Args:
        workspace: Path to workspace directory.

    Returns:
        ValidationResult with pass/fail and diagnostic messages.
    """
    workspace = Path(workspace).resolve()
    raw_dir = workspace / "raw"
    search_dir = raw_dir if raw_dir.is_dir() else workspace

    result = ValidationResult(is_valid=True)

    # Check COSMED file exists
    cosmed_files = sorted(search_dir.glob("*CPET BxB*.xlsx")) + sorted(
        search_dir.glob("*CPET*.xlsx")
    )
    if not cosmed_files:
        result.is_valid = False
        result.errors.append(
            f"No COSMED XLSX file found in {search_dir}"
        )
        return result

    result.metadata["cosmed_file"] = str(cosmed_files[0].name)
    result.metadata["has_fit"] = bool(sorted(search_dir.glob("*.fit")))
    result.metadata["has_zwo"] = bool(sorted(search_dir.glob("*.zwo")))
    result.metadata["has_lactate_md"] = bool(sorted(search_dir.glob("*.md")))
    result.metadata["has_lactate_xlsx"] = bool(
        sorted(search_dir.glob("*LT*.xlsx"))
    )

    # Try parsing COSMED to validate content
    try:
        from pipeline.parsers.cosmed import parse_cosmed

        bxb_df, subject_info = parse_cosmed(cosmed_files[0])
        result.metadata["bxb_records"] = len(bxb_df)
        result.metadata["subject_name"] = subject_info.get("name", "")

        if len(bxb_df) < MIN_BXB_RECORDS:
            result.is_valid = False
            result.errors.append(
                f"Too few BxB records: {len(bxb_df)} (minimum {MIN_BXB_RECORDS})"
            )

        # QC range checks
        _check_ranges(bxb_df, result)

        # Sensor dropout checks
        _check_dropout(bxb_df, "vo2_ml", result)
        _check_dropout(bxb_df, "hr_bpm", result)

    except Exception as e:
        result.is_valid = False
        result.errors.append(f"Failed to parse COSMED file: {e}")

    return result


def _check_ranges(
    df: pd.DataFrame, result: ValidationResult
) -> None:
    """Check physiological range plausibility."""
    for col, (lo, hi) in QC_RANGES.items():
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if series.empty:
            continue

        out_of_range = ((series < lo) | (series > hi)).sum()
        total = len(series)
        ratio = out_of_range / total if total > 0 else 0

        if ratio > 0.20:
            result.warnings.append(
                f"{col}: {ratio:.0%} of values outside range [{lo}, {hi}]"
            )
        result.metadata[f"{col}_out_of_range_pct"] = round(ratio * 100, 1)


def _check_dropout(
    df: pd.DataFrame, col: str, result: ValidationResult
) -> None:
    """Check sensor dropout rate for a column."""
    if col not in df.columns:
        return

    total = len(df)
    if total == 0:
        return

    dropout = df[col].isna().sum() + (df[col] == 0).sum()
    rate = dropout / total

    if rate > SENSOR_DROPOUT_THRESHOLD:
        result.warnings.append(
            f"{col} dropout rate: {rate:.1%} (threshold {SENSOR_DROPOUT_THRESHOLD:.0%})"
        )
    result.metadata[f"{col}_dropout_rate"] = round(rate, 3)
