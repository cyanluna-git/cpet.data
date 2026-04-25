"""
pipeline.fit_history — FIT workout history normalisation for cycling model inputs.

Provides:
  - DURATION_BINS_S  canonical power-curve duration bins (seconds)
  - best_rolling_power  rolling-mean best-effort helper (moved from inscyd_workspace)
  - extract_workout_bests  aggregate per-bin best across multiple FIT files
  - save_fit_history  persist result to analysis_results SQLite table
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.parsers.fit import parse_fit

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: Canonical cycling power-curve duration bins, in seconds.
#: Nine bins chosen to span 1-s sprint through 20-min sustained effort.
DURATION_BINS_S: tuple[int, ...] = (1, 5, 15, 30, 60, 180, 300, 600, 1200)


# ---------------------------------------------------------------------------
# Rolling-power helper (moved from inscyd_workspace._best_rolling_power)
# ---------------------------------------------------------------------------


def best_rolling_power(workout_df: pd.DataFrame, duration_sec: int) -> float | None:
    """Return the best rolling-mean power for *duration_sec* seconds.

    Args:
        workout_df: Parsed FIT records DataFrame (must contain ``power_w``).
        duration_sec: Window length in seconds.

    Returns:
        Best rolling-mean watts as float, or None when not computable.
    """
    if duration_sec <= 0 or workout_df.empty or "power_w" not in workout_df.columns:
        return None
    series = workout_df["power_w"].fillna(0)
    if len(series) < duration_sec:
        return None
    best = series.rolling(window=duration_sec, min_periods=duration_sec).mean().max()
    if pd.isna(best):
        return None
    return float(best)


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------


def extract_workout_bests(
    fit_paths: list[Path | str],
    bins: tuple[int, ...] = DURATION_BINS_S,
) -> dict[str, Any]:
    """Aggregate per-bin best-effort power across multiple FIT files.

    Duplicates are resolved by filename (``Path.name``); first occurrence wins.

    Args:
        fit_paths: List of paths to ``.fit`` files.
        bins: Duration bins in seconds to compute.  Defaults to
            :data:`DURATION_BINS_S`.

    Returns:
        Dict with keys:

        ``bins``
            Mapping ``{str(duration_s): {"best_w": float, "source_file": str} | None}``
            for every bin.  Value is ``None`` when no file could fill the bin.

        ``coverage``
            ``{filled_count, total_bins, ratio, quality}`` where *quality* is
            one of ``"full"``, ``"partial"``, ``"sparse"``, ``"none"``.

        ``sessions``
            ``[{filename, record_count, duration_sec, bins_contributed}]``
            one entry per de-duplicated file actually parsed.
    """
    # Dedup by filename; first occurrence of each basename wins.
    seen_names: set[str] = set()
    unique_paths: list[Path] = []
    for p in fit_paths:
        p = Path(p)
        if p.name not in seen_names:
            seen_names.add(p.name)
            unique_paths.append(p)

    # Initialise bin table: all bins set to None.
    bin_table: dict[str, dict[str, Any] | None] = {str(d): None for d in bins}

    sessions: list[dict[str, Any]] = []

    for fit_path in unique_paths:
        try:
            workout_df, _laps_df = parse_fit(fit_path)
        except Exception:
            # Skip unreadable files; the caller handles absence of sessions.
            continue

        record_count = int(len(workout_df))
        duration_sec = (
            int(workout_df["elapsed_s"].max()) if not workout_df.empty else 0
        )
        bins_contributed: list[str] = []

        for d in bins:
            key = str(d)
            candidate = best_rolling_power(workout_df, d)
            if candidate is None:
                continue
            current = bin_table[key]
            if current is None or candidate > current["best_w"]:
                bin_table[key] = {
                    "best_w": candidate,
                    "source_file": fit_path.name,
                }
                bins_contributed.append(key)

        sessions.append(
            {
                "filename": fit_path.name,
                "record_count": record_count,
                "duration_sec": duration_sec,
                "bins_contributed": bins_contributed,
            }
        )

    # Compute coverage
    total_bins = len(bins)
    filled_count = sum(1 for v in bin_table.values() if v is not None)
    ratio = filled_count / total_bins if total_bins > 0 else 0.0

    if ratio >= 0.8:
        quality = "full"
    elif ratio >= 0.4:
        quality = "partial"
    elif ratio > 0:
        quality = "sparse"
    else:
        quality = "none"

    return {
        "bins": bin_table,
        "coverage": {
            "filled_count": filled_count,
            "total_bins": total_bins,
            "ratio": round(ratio, 4),
            "quality": quality,
        },
        "sessions": sessions,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_fit_history(db_path: Path | str, history: dict[str, Any]) -> None:
    """Persist *history* to the ``analysis_results`` SQLite table.

    Creates the table when it does not yet exist (same DDL as
    ``pipeline.analysis``).  Uses ``INSERT OR REPLACE`` keyed on
    ``category='fit_history'``, ``key='workout_bests'``.

    Args:
        db_path: Path to the workspace ``analysis.db`` file.
        history: Output of :func:`extract_workout_bests`.
    """
    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            UNIQUE(category, key)
        )
        """
    )

    value_json = json.dumps(history, ensure_ascii=False)
    cursor.execute(
        "INSERT OR REPLACE INTO analysis_results (category, key, value) VALUES (?, ?, ?)",
        ("fit_history", "workout_bests", value_json),
    )

    conn.commit()
    conn.close()
