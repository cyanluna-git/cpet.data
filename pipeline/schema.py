"""
pipeline.schema — SQLite schema creation and data loading.

Creates analysis.db from ParsedData, populating all tables.
No hardcoded paths; all locations are passed as parameters.

Canonical source: hong.changsun/analysis/schema.py
"""

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.parsers import ParsedData

SCHEMA_SQL = """
DROP TABLE IF EXISTS blood_samples;
DROP TABLE IF EXISTS breath_by_breath;
DROP TABLE IF EXISTS workout_data;
DROP TABLE IF EXISTS protocol_stages;
DROP TABLE IF EXISTS test_session;
DROP TABLE IF EXISTS subject;

CREATE TABLE subject (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    last_name TEXT,
    first_name TEXT,
    gender TEXT,
    age REAL,
    height_cm REAL,
    weight_kg REAL,
    dob TEXT,
    ftp_w INTEGER,
    max_hr INTEGER,
    est_lt1_w INTEGER,
    est_lt2_w INTEGER
);

CREATE TABLE test_session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER REFERENCES subject(id),
    test_date TEXT,
    protocol_name TEXT,
    start_time_kst TEXT,
    end_time_kst TEXT,
    ambient_temp_c REAL,
    humidity_pct REAL,
    baro_pressure_mmhg REAL
);

CREATE TABLE protocol_stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES test_session(id),
    block TEXT,
    step INTEGER,
    power_normalized REAL,
    duration_s REAL,
    stage_type TEXT
);

CREATE TABLE workout_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES test_session(id),
    timestamp_kst TEXT,
    elapsed_s REAL,
    block TEXT,
    step INTEGER,
    power_w REAL,
    target_power_w REAL,
    hr_bpm REAL,
    cadence_rpm REAL,
    speed_mps REAL,
    distance_m REAL
);

CREATE TABLE breath_by_breath (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES test_session(id),
    t_s REAL,
    timestamp_kst TEXT,
    vo2_ml REAL,
    vco2_ml REAL,
    rq REAL,
    hr_bpm REAL,
    ve_lmin REAL,
    vt_l REAL,
    rf REAL,
    fat_gmin REAL,
    cho_gmin REAL,
    bike_power_w REAL,
    vo2_kg REAL,
    mets REAL,
    pet_o2 REAL,
    pet_co2 REAL,
    fe_o2 REAL,
    fe_co2 REAL,
    ve_vo2 REAL,
    ve_vco2 REAL,
    ti_s REAL,
    te_s REAL,
    ttot_s REAL,
    vd_vt_e REAL,
    ee_kcal REAL,
    phase TEXT,
    cadence_rpm REAL
);

CREATE TABLE blood_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES test_session(id),
    block TEXT,
    step TEXT,
    load_w REAL,
    ftp_pct TEXT,
    duration_min REAL,
    sample_time_kst TEXT,
    hr_bpm REAL,
    lactate_mmol REAL,
    glucose_mmol REAL,
    notes TEXT
);
"""


def _to_int_like(value: object, default: int | None = None) -> int | None:
    """Coerce mixed metadata values into an integer when possible."""
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(round(float(text.split()[0])))
    except (TypeError, ValueError, IndexError):
        return default


def _infer_protocol_name(parsed: ParsedData) -> str:
    """Infer a human-readable protocol label from available sources."""
    if parsed.blood_df is not None and not parsed.blood_df.empty:
        return "Belgium Lactate Test Elite"

    protocol_df = parsed.protocol_df
    if protocol_df is not None and not protocol_df.empty:
        blocks = set(protocol_df["block"].dropna().astype(str))
        if "block_2" in blocks:
            return "Two-Block FatMax + VO2max CPET"

    if parsed.workout_df is not None and not parsed.workout_df.empty:
        blocks = set(parsed.workout_df.get("block", pd.Series(dtype=str)).dropna().astype(str))
        if "block_2" in blocks:
            return "Two-Block FatMax + VO2max CPET"

    return "CPET Analysis"


def create_database(workspace: Path, parsed: ParsedData) -> Path:
    """Create analysis.db from parsed data sources.

    Args:
        workspace: Workspace directory where analysis.db will be written.
        parsed: ParsedData from parse_workspace().

    Returns:
        Path to the created analysis.db file.
    """
    db_path = Path(workspace) / "analysis.db"

    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.executescript(SCHEMA_SQL)

    subject_info_xlsx = parsed.subject_info
    blood_info = parsed.blood_info

    # --- Insert subject ---
    ftp = _to_int_like(blood_info.get("FTP"), 220)
    max_hr: int | None = _to_int_like(blood_info.get("Max HR"))
    if max_hr is None and parsed.has_fit and parsed.workout_df is not None:
        max_hr = _to_int_like(parsed.workout_df["hr_bpm"].max(), 180)
    if max_hr is None:
        max_hr = 180
    est_lt1 = _to_int_like(blood_info.get("\uc608\uc0c1 LT1"))
    est_lt2 = _to_int_like(blood_info.get("\uc608\uc0c1 LT2")) or ftp

    cursor.execute(
        """INSERT INTO subject (name, last_name, first_name, gender, age,
           height_cm, weight_kg, dob, ftp_w, max_hr, est_lt1_w, est_lt2_w)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            subject_info_xlsx.get("name"),
            subject_info_xlsx.get("last_name"),
            subject_info_xlsx.get("first_name"),
            subject_info_xlsx.get("gender"),
            subject_info_xlsx.get("age"),
            subject_info_xlsx.get("height_cm"),
            subject_info_xlsx.get("weight_kg"),
            str(subject_info_xlsx.get("dob", "")),
            ftp,
            max_hr,
            est_lt1,
            est_lt2,
        ),
    )
    subject_id = cursor.lastrowid

    # --- Insert test session ---
    bxb_df = parsed.cosmed_df
    workout_df = parsed.workout_df

    if workout_df is not None and not workout_df.empty:
        test_date = pd.Timestamp(workout_df["timestamp_kst"].iloc[0]).strftime(
            "%Y-%m-%d"
        )
        start_time = str(workout_df["timestamp_kst"].iloc[0])
        end_time = str(workout_df["timestamp_kst"].iloc[-1])
    elif "timestamp_kst" in bxb_df.columns and not bxb_df.empty:
        test_date = pd.Timestamp(bxb_df["timestamp_kst"].iloc[0]).strftime(
            "%Y-%m-%d"
        )
        start_time = str(bxb_df["timestamp_kst"].iloc[0])
        end_time = str(bxb_df["timestamp_kst"].iloc[-1])
    else:
        test_date = str(subject_info_xlsx.get("test_date", ""))
        start_time = ""
        end_time = ""

    cursor.execute(
        """INSERT INTO test_session (subject_id, test_date, protocol_name,
           start_time_kst, end_time_kst, ambient_temp_c, humidity_pct, baro_pressure_mmhg)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            subject_id,
            test_date,
            _infer_protocol_name(parsed),
            start_time,
            end_time,
            subject_info_xlsx.get("ambient_temp_c"),
            subject_info_xlsx.get("ambient_rh_pct"),
            subject_info_xlsx.get("baro_pressure_mmhg"),
        ),
    )
    session_id = cursor.lastrowid

    # --- Insert protocol stages ---
    protocol_df = parsed.protocol_df
    if protocol_df is not None and not protocol_df.empty:
        for _, row in protocol_df.iterrows():
            cursor.execute(
                """INSERT INTO protocol_stages (session_id, block, step,
                   power_normalized, duration_s, stage_type)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    row["block"],
                    int(row["step"]),
                    row["power_normalized"],
                    row["duration_s"],
                    row["stage_type"],
                ),
            )
        print(f"  protocol_stages: {len(protocol_df)} rows")

    # --- Insert workout data ---
    if workout_df is not None and not workout_df.empty:
        workout_rows = []
        for _, row in workout_df.iterrows():
            workout_rows.append(
                (
                    session_id,
                    str(row["timestamp_kst"]),
                    row["elapsed_s"],
                    row.get("block", ""),
                    int(row.get("step", 0)),
                    row.get("power_w"),
                    row.get("target_power_w"),
                    row.get("hr_bpm"),
                    row.get("cadence_rpm"),
                    row.get("speed_mps"),
                    row.get("distance_m"),
                )
            )
        cursor.executemany(
            """INSERT INTO workout_data (session_id, timestamp_kst, elapsed_s,
               block, step, power_w, target_power_w, hr_bpm, cadence_rpm, speed_mps, distance_m)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            workout_rows,
        )
        print(f"  workout_data: {len(workout_rows)} rows")

    # --- Insert breath-by-breath ---
    bxb_cols = [
        "t_s",
        "timestamp_kst",
        "vo2_ml",
        "vco2_ml",
        "rq",
        "hr_bpm",
        "ve_lmin",
        "vt_l",
        "rf",
        "fat_gmin",
        "cho_gmin",
        "bike_power_w",
        "vo2_kg",
        "mets",
        "pet_o2",
        "pet_co2",
        "fe_o2",
        "fe_co2",
        "ve_vo2",
        "ve_vco2",
        "ti_s",
        "te_s",
        "ttot_s",
        "vd_vt_e",
        "ee_kcal",
        "phase",
        "cadence_rpm",
    ]
    bxb_rows = []
    for _, row in bxb_df.iterrows():
        vals = [session_id]
        for col in bxb_cols:
            v = row.get(col)
            if pd.isna(v):
                vals.append(None)
            elif col == "timestamp_kst":
                vals.append(str(v))
            else:
                vals.append(v)
        bxb_rows.append(tuple(vals))

    placeholders = ", ".join(["?"] * (len(bxb_cols) + 1))
    col_names = ", ".join(["session_id"] + bxb_cols)
    cursor.executemany(
        f"INSERT INTO breath_by_breath ({col_names}) VALUES ({placeholders})",
        bxb_rows,
    )
    print(f"  breath_by_breath: {len(bxb_rows)} rows")

    # --- Insert blood samples ---
    blood_df = parsed.blood_df
    if blood_df is not None and not blood_df.empty:
        for _, row in blood_df.iterrows():
            cursor.execute(
                """INSERT INTO blood_samples (session_id, block, step, load_w,
                   ftp_pct, duration_min, sample_time_kst, hr_bpm, lactate_mmol,
                   glucose_mmol, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    row.get("block"),
                    row.get("step"),
                    (
                        row.get("load_w")
                        if pd.notna(row.get("load_w"))
                        else None
                    ),
                    row.get("ftp_pct"),
                    (
                        row.get("duration_min")
                        if pd.notna(row.get("duration_min"))
                        else None
                    ),
                    row.get("kst_time"),
                    (
                        row.get("hr_bpm")
                        if pd.notna(row.get("hr_bpm"))
                        else None
                    ),
                    (
                        row.get("lactate_mmol")
                        if pd.notna(row.get("lactate_mmol"))
                        else None
                    ),
                    (
                        row.get("glucose_mmol")
                        if pd.notna(row.get("glucose_mmol"))
                        else None
                    ),
                    row.get("notes"),
                ),
            )
        print(f"  blood_samples: {len(blood_df)} rows")

    conn.commit()

    # --- Verification ---
    tables = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    print(f"  Tables: {[t[0] for t in tables]}")
    for table in tables:
        name = table[0]
        count = cursor.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"  {name}: {count} rows")

    print(f"\n  DB file: {db_path}")
    print(f"  DB size: {db_path.stat().st_size / 1024:.1f} KB")

    conn.close()
    return db_path
