"""
server.db — Platform SQLite CRUD for submissions, jobs, users, and profiles.

Every function takes a db_path: Path parameter. No global state.
Uses raw sqlite3, WAL mode, TEXT primary keys (UUID).
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    google_id TEXT UNIQUE,
    email TEXT UNIQUE,
    display_name TEXT,
    avatar_url TEXT,
    role TEXT DEFAULT 'user',
    created_at TEXT DEFAULT (datetime('now')),
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS submissions (
    id TEXT PRIMARY KEY,
    description TEXT,
    file_manifest TEXT,
    workspace_path TEXT,
    subject_name TEXT,
    test_date TEXT,
    user_id TEXT REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    submission_id TEXT REFERENCES submissions(id),
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    report_slug TEXT,
    report_url TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY REFERENCES users(id),
    weight_kg REAL,
    height_cm REAL,
    body_fat_pct REAL,
    skeletal_muscle_mass REAL,
    bmi REAL,
    birth_year INTEGER,
    gender TEXT,
    training_level TEXT,
    measured_at TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
"""

MIGRATION_ADD_USER_ID = """
ALTER TABLE submissions ADD COLUMN user_id TEXT REFERENCES users(id);
"""

VALID_STATUSES = {"pending", "processing", "done", "failed"}


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with Row factory and WAL mode."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now_utc() -> str:
    """ISO-format UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check whether a column exists in a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def init_db(db_path: Path) -> None:
    """Create tables if they don't exist and run migrations."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    conn.executescript(SCHEMA_SQL)
    # Migration: add user_id to submissions if missing (backward compat)
    if not _column_exists(conn, "submissions", "user_id"):
        conn.execute(MIGRATION_ADD_USER_ID)
        conn.commit()
    conn.close()


def create_submission(
    db_path: Path,
    description: str,
    file_manifest: list[dict],
    workspace_path: str,
    subject_name: str = "",
    test_date: str = "",
    submission_id: str | None = None,
    user_id: str | None = None,
) -> str:
    """Insert a new submission and return its UUID.

    If submission_id is provided, use it; otherwise generate a new one.
    This allows workspace creation to determine the ID first.
    user_id is optional for backward compatibility (anonymous uploads).
    """
    if submission_id is None:
        submission_id = str(uuid.uuid4())
    manifest_json = json.dumps(file_manifest)
    conn = _connect(db_path)
    conn.execute(
        """INSERT INTO submissions
           (id, description, file_manifest, workspace_path, subject_name, test_date, user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (submission_id, description, manifest_json, workspace_path,
         subject_name, test_date, user_id),
    )
    conn.commit()
    conn.close()
    return submission_id


def get_submission(db_path: Path, submission_id: str) -> dict | None:
    """Fetch a submission by ID, or None if not found."""
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT * FROM submissions WHERE id = ?", (submission_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    result["file_manifest"] = json.loads(result["file_manifest"])
    return result


def create_job(db_path: Path, submission_id: str) -> str:
    """Create a new job for a submission and return its UUID."""
    job_id = str(uuid.uuid4())
    conn = _connect(db_path)
    conn.execute(
        "INSERT INTO jobs (id, submission_id) VALUES (?, ?)",
        (job_id, submission_id),
    )
    conn.commit()
    conn.close()
    return job_id


def update_job_status(
    db_path: Path,
    job_id: str,
    status: str,
    **kwargs: str | None,
) -> None:
    """Update job status and optional fields.

    Sets started_at when transitioning to 'processing'.
    Sets completed_at when transitioning to 'done' or 'failed'.

    Accepted kwargs: error_message, report_slug, report_url.
    """
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {VALID_STATUSES}"
        )

    now = _now_utc()
    sets = ["status = ?"]
    params: list[str | None] = [status]

    if status == "processing":
        sets.append("started_at = ?")
        params.append(now)
    elif status in ("done", "failed"):
        sets.append("completed_at = ?")
        params.append(now)

    allowed_kwargs = {"error_message", "report_slug", "report_url"}
    for key, value in kwargs.items():
        if key not in allowed_kwargs:
            raise ValueError(f"Unknown kwarg '{key}'")
        sets.append(f"{key} = ?")
        params.append(value)

    params.append(job_id)
    sql = f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?"

    conn = _connect(db_path)
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def list_jobs(
    db_path: Path, status: str | None = None
) -> list[dict]:
    """List jobs, newest first. Optionally filter by status."""
    conn = _connect(db_path)
    if status is not None:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY rowid DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY rowid DESC"
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def list_jobs_by_user(
    db_path: Path, user_id: str, status: str | None = None
) -> list[dict]:
    """List jobs whose submission belongs to user_id, newest first."""
    conn = _connect(db_path)
    if status is not None:
        rows = conn.execute(
            """SELECT j.* FROM jobs j
               JOIN submissions s ON j.submission_id = s.id
               WHERE s.user_id = ? AND j.status = ?
               ORDER BY j.rowid DESC""",
            (user_id, status),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT j.* FROM jobs j
               JOIN submissions s ON j.submission_id = s.id
               WHERE s.user_id = ?
               ORDER BY j.rowid DESC""",
            (user_id,),
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_job(db_path: Path, job_id: str) -> dict | None:
    """Fetch a single job by ID, or None if not found."""
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT * FROM jobs WHERE id = ?", (job_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def get_pending_jobs(db_path: Path) -> list[dict]:
    """Return all jobs with status='pending', newest first."""
    return list_jobs(db_path, status="pending")


def get_job_by_submission(
    db_path: Path, submission_id: str
) -> dict | None:
    """Find the job associated with a submission, or None."""
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT * FROM jobs WHERE submission_id = ? ORDER BY rowid DESC",
        (submission_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


# ── User CRUD ───────────────────────────────────────────────────────


def upsert_user(
    db_path: Path,
    google_id: str,
    email: str,
    display_name: str = "",
    avatar_url: str = "",
) -> dict:
    """Create a user on first login or update last_login_at for returning users.

    Returns the user row as a dict.
    """
    now = _now_utc()
    conn = _connect(db_path)

    row = conn.execute(
        "SELECT * FROM users WHERE google_id = ?", (google_id,)
    ).fetchone()

    if row is None:
        user_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO users
               (id, google_id, email, display_name, avatar_url, role, created_at, last_login_at)
               VALUES (?, ?, ?, ?, ?, 'user', ?, ?)""",
            (user_id, google_id, email, display_name, avatar_url, now, now),
        )
        conn.commit()
        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    else:
        conn.execute(
            """UPDATE users
               SET email = ?, display_name = ?, avatar_url = ?, last_login_at = ?
               WHERE google_id = ?""",
            (email, display_name, avatar_url, now, google_id),
        )
        conn.commit()
        user = conn.execute(
            "SELECT * FROM users WHERE google_id = ?", (google_id,)
        ).fetchone()

    conn.close()
    return dict(user)


def get_user(db_path: Path, user_id: str) -> dict | None:
    """Fetch a user by ID, or None if not found."""
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def get_user_by_google_id(db_path: Path, google_id: str) -> dict | None:
    """Fetch a user by Google ID, or None if not found."""
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT * FROM users WHERE google_id = ?", (google_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


# ── User Profile CRUD ──────────────────────────────────────────────


PROFILE_FIELDS = {
    "weight_kg", "height_cm", "body_fat_pct", "skeletal_muscle_mass",
    "bmi", "birth_year", "gender", "training_level", "measured_at",
}


def get_user_profile(db_path: Path, user_id: str) -> dict | None:
    """Fetch a user profile by user ID, or None if not found."""
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def upsert_user_profile(
    db_path: Path,
    user_id: str,
    **fields: str | float | int | None,
) -> dict:
    """Create or update a user profile. Returns the updated profile dict.

    Only fields in PROFILE_FIELDS are accepted; unknown keys raise ValueError.
    """
    for key in fields:
        if key not in PROFILE_FIELDS:
            raise ValueError(f"Unknown profile field '{key}'")

    now = _now_utc()
    conn = _connect(db_path)

    existing = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()

    if existing is None:
        columns = ["user_id", "updated_at"]
        values: list[str | float | int | None] = [user_id, now]
        for key, value in fields.items():
            columns.append(key)
            values.append(value)
        placeholders = ", ".join("?" for _ in columns)
        col_names = ", ".join(columns)
        conn.execute(
            f"INSERT INTO user_profiles ({col_names}) VALUES ({placeholders})",
            values,
        )
    else:
        if not fields:
            conn.close()
            return dict(existing)
        sets = ["updated_at = ?"]
        params: list[str | float | int | None] = [now]
        for key, value in fields.items():
            sets.append(f"{key} = ?")
            params.append(value)
        params.append(user_id)
        conn.execute(
            f"UPDATE user_profiles SET {', '.join(sets)} WHERE user_id = ?",
            params,
        )

    conn.commit()
    row = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row)


# ── Submissions by User ──────────────────────────────────────────────


def list_submissions_by_user(db_path: Path, user_id: str) -> list[dict]:
    """List submissions for a given user, newest first."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM submissions WHERE user_id = ? ORDER BY rowid DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    results = []
    for row in rows:
        d = dict(row)
        d["file_manifest"] = json.loads(d["file_manifest"])
        results.append(d)
    return results


# ── Fitness Trends (from workspace analysis.db files) ─────────────


# Keys to extract from each analysis.db's analysis_results table.
_TREND_METRICS: dict[str, list[tuple[str, str]]] = {
    "vo2max": [
        ("vo2max_ml", "vo2max_ml"),
        ("vo2max_rel", "vo2max_rel"),
    ],
    "lactate": [
        ("lt1_fixed_power_w", "lt1_power_w"),
        ("lt1_dmax_power_w", "lt2_power_w"),
    ],
    "substrate": [
        ("fatmax_power_w", "fatmax_power_w"),
        ("fatmax_gmin", "fatmax_gmin"),
    ],
}


def _read_analysis_metrics(analysis_db_path: Path) -> dict:
    """Read key metrics from a single workspace analysis.db file.

    Returns a flat dict of metric name -> numeric value, plus test_date.
    Returns empty dict if analysis.db does not exist or has no data.
    """
    if not analysis_db_path.exists():
        return {}

    try:
        conn = sqlite3.connect(str(analysis_db_path))
        conn.row_factory = sqlite3.Row

        # Get test date from test_session table
        test_date_row = conn.execute(
            "SELECT test_date FROM test_session LIMIT 1"
        ).fetchone()
        test_date = test_date_row["test_date"] if test_date_row else None

        # Check if analysis_results table exists
        table_check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_results'"
        ).fetchone()
        if table_check is None:
            conn.close()
            return {}

        # Read all relevant metrics
        metrics: dict = {"test_date": test_date}
        for category, keys in _TREND_METRICS.items():
            for src_key, dest_key in keys:
                row = conn.execute(
                    "SELECT value FROM analysis_results WHERE category = ? AND key = ?",
                    (category, src_key),
                ).fetchone()
                if row is not None and row["value"] is not None:
                    try:
                        val = json.loads(row["value"])
                        if isinstance(val, (int, float)):
                            metrics[dest_key] = val
                    except (json.JSONDecodeError, TypeError):
                        # Try plain float parse for simple numeric strings
                        try:
                            metrics[dest_key] = float(row["value"])
                        except (ValueError, TypeError):
                            pass

        conn.close()
        return metrics
    except (sqlite3.Error, OSError):
        return {}


def get_fitness_trends(
    db_path: Path, user_id: str, data_dir: Path | None = None,
) -> list[dict]:
    """Build a time-series of key fitness metrics across a user's submissions.

    Each element contains test_date and available metrics extracted from
    the corresponding workspace's analysis.db.

    Args:
        db_path: Path to the platform database.
        user_id: User ID to look up submissions.
        data_dir: Optional data directory root (used to resolve relative workspace paths).

    Returns:
        List of dicts sorted by test_date ascending, each containing
        test_date and available metric values.
    """
    submissions = list_submissions_by_user(db_path, user_id)
    trends: list[dict] = []

    for sub in submissions:
        workspace_path = sub.get("workspace_path")
        if not workspace_path:
            continue

        ws = Path(workspace_path)
        if not ws.is_absolute() and data_dir is not None:
            ws = data_dir / ws

        analysis_db = ws / "analysis.db"
        metrics = _read_analysis_metrics(analysis_db)
        if not metrics or not metrics.get("test_date"):
            continue

        # Include submission metadata for context
        metrics["submission_id"] = sub["id"]
        metrics["subject_name"] = sub.get("subject_name", "")
        trends.append(metrics)

    # Sort by test_date ascending (oldest first)
    trends.sort(key=lambda m: m.get("test_date", ""))

    # Compute deltas if 2+ entries exist
    if len(trends) >= 2:
        prev = trends[-2]
        curr = trends[-1]
        deltas: dict = {}
        for key in ("vo2max_ml", "vo2max_rel", "lt1_power_w", "lt2_power_w",
                     "fatmax_power_w", "fatmax_gmin"):
            if key in curr and key in prev:
                try:
                    deltas[key] = round(curr[key] - prev[key], 2)
                except (TypeError, ValueError):
                    pass
        if deltas:
            trends[-1]["deltas"] = deltas

    return trends
