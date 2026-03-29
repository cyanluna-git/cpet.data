"""
pipeline.parsers.cosmed — COSMED K5 breath-by-breath XLSX parser.

Parses COSMED K5 export files (.xlsx) into breath-by-breath DataFrames
with subject metadata extraction.

Canonical source: hong.changsun/analysis/parsers.py
"""

import datetime as dt
from pathlib import Path
from typing import Any

import pandas as pd

# Columns to extract from COSMED XLSX (header name -> clean name)
COSMED_COLUMNS = {
    "t": "t_s",
    "Rf": "rf",
    "VT": "vt_l",
    "VE": "ve_lmin",
    "VO2": "vo2_ml",
    "VCO2": "vco2_ml",
    "RQ": "rq",
    "HR": "hr_bpm",
    "VO2/kg": "vo2_kg",
    "METS": "mets",
    "FeO2": "fe_o2",
    "FeCO2": "fe_co2",
    "PetO2": "pet_o2",
    "PetCO2": "pet_co2",
    "VE/VO2": "ve_vo2",
    "VE/VCO2": "ve_vco2",
    "EEkc": "ee_kcal",
    "EEh": "ee_h",
    "EEm": "ee_min",
    "EEtot": "ee_tot",
    "Fat": "fat_gmin",
    "CHO": "cho_gmin",
    "Ti": "ti_s",
    "Te": "te_s",
    "Ttot": "ttot_s",
    "VD/VT e": "vd_vt_e",
    "Phase": "phase",
    "Bike Power": "bike_power_w",
    "Bike Crank Cadence": "cadence_rpm",
}


def _time_to_seconds(val: Any) -> float | None:
    """Convert datetime.time or timedelta to float seconds."""
    if val is None:
        return None
    if isinstance(val, dt.time):
        return val.hour * 3600 + val.minute * 60 + val.second + val.microsecond / 1e6
    if isinstance(val, dt.timedelta):
        return val.total_seconds()
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _parse_test_time(value: Any) -> str | None:
    """Normalize COSMED test time metadata into HH:MM:SS.

    COSMED exports have been seen with:
    - datetime.time objects
    - "09:00:00"
    - "AM 10:29" / "PM 03:14"
    """
    if value is None:
        return None
    if isinstance(value, dt.time):
        return value.strftime("%H:%M:%S")

    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%H:%M:%S", "%H:%M", "%p %I:%M", "%p %I:%M:%S"):
        try:
            parsed = dt.datetime.strptime(text, fmt)
            return parsed.strftime("%H:%M:%S")
        except ValueError:
            continue

    return text


def parse_cosmed(
    path: Path,
    workout_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Parse COSMED K5 breath-by-breath XLSX file.

    Args:
        path: Explicit path to the COSMED XLSX file.
        workout_df: Optional FIT workout DataFrame for power backfill
                     (backfill is handled by parse_workspace dispatcher).

    Returns:
        Tuple of (bxb_df, subject_info dict).
    """
    import openpyxl

    path = Path(path)
    wb = openpyxl.load_workbook(str(path))
    ws = wb["Data"]
    rows = list(ws.iter_rows(values_only=True))

    # --- Subject info from rows 0-13, columns A-H ---
    subject_info: dict[str, Any] = {}

    def _cell(row_idx: int, col_idx: int) -> Any:
        if row_idx < len(rows) and col_idx < len(rows[row_idx]):
            return rows[row_idx][col_idx]
        return None

    subject_info["last_name"] = _cell(1, 1)
    subject_info["first_name"] = _cell(2, 1)
    subject_info["name"] = (
        f"{subject_info.get('first_name', '')} {subject_info.get('last_name', '')}".strip()
    )
    subject_info["gender"] = _cell(3, 1)
    subject_info["age"] = _cell(4, 1)
    subject_info["height_cm"] = _cell(5, 1)
    subject_info["weight_kg"] = _cell(6, 1)
    subject_info["dob"] = _cell(7, 1)
    subject_info["test_date"] = _cell(0, 4)
    subject_info["test_time"] = _cell(1, 4)
    subject_info["baro_pressure_mmhg"] = _cell(0, 7)
    subject_info["ambient_temp_c"] = _cell(1, 7)
    subject_info["ambient_rh_pct"] = _cell(2, 7)

    # --- BxB data: headers from row 0 (col J onward = index 9+) ---
    headers_row = rows[0]
    col_start = 9  # Column J

    # Map header index -> clean column name
    header_map: dict[int, str] = {}
    for i in range(col_start, len(headers_row)):
        h = headers_row[i]
        if h and h in COSMED_COLUMNS:
            header_map[i] = COSMED_COLUMNS[h]

    # Data rows start at row 3 (index 3)
    bxb_rows: list[dict[str, Any]] = []
    for row_idx in range(3, len(rows)):
        row = rows[row_idx]
        time_val = row[col_start] if col_start < len(row) else None
        if time_val is None:
            continue

        record: dict[str, Any] = {}
        for col_idx, col_name in header_map.items():
            val = row[col_idx] if col_idx < len(row) else None
            if col_name == "t_s":
                val = _time_to_seconds(val)
            elif col_name == "phase":
                pass  # keep as string
            elif isinstance(val, (int, float)):
                val = float(val)
            record[col_name] = val
        bxb_rows.append(record)

    bxb_df = pd.DataFrame(bxb_rows)

    # Add absolute KST timestamp
    test_time = subject_info.get("test_time")
    test_date = subject_info.get("test_date")
    if test_time:
        date_text = (
            pd.Timestamp(test_date).strftime("%Y-%m-%d")
            if test_date
            else "2026-03-20"
        )
        normalized_time = _parse_test_time(test_time) or "00:00:00"
        base_time = pd.Timestamp(f"{date_text} {normalized_time}")

        bxb_df["timestamp_kst"] = base_time + pd.to_timedelta(
            bxb_df["t_s"], unit="s"
        )

    wb.close()
    return bxb_df, subject_info
