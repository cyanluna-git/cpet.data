"""
server.db — Platform SQLite CRUD for submissions, jobs, users, subjects, and profiles.

Every function takes a db_path: Path parameter. No global state.
Uses raw sqlite3, WAL mode, TEXT primary keys (UUID).
"""

import html
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
import re

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS subjects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    gender TEXT,
    birth_year INTEGER,
    height_cm REAL,
    weight_kg REAL,
    body_fat_pct REAL,
    skeletal_muscle_mass REAL,
    bmi REAL,
    training_level TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    google_id TEXT UNIQUE,
    email TEXT UNIQUE,
    display_name TEXT,
    avatar_url TEXT,
    role TEXT DEFAULT 'user',
    onboarding_completed INTEGER DEFAULT 0,
    subject_id TEXT REFERENCES subjects(id),
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
    subject_id TEXT REFERENCES subjects(id),
    uploaded_by_user_id TEXT REFERENCES users(id),
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

CREATE TABLE IF NOT EXISTS report_user_links (
    report_slug TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id),
    linked_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS report_name_overrides (
    report_slug TEXT PRIMARY KEY,
    subject_name TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS report_notes (
    report_slug TEXT PRIMARY KEY,
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now'))
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

CREATE TABLE IF NOT EXISTS subject_metric_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(id),
    source_kind TEXT NOT NULL,
    source_ref_id TEXT NOT NULL,
    submission_id TEXT REFERENCES submissions(id),
    measured_at TEXT NOT NULL,
    measured_date TEXT GENERATED ALWAYS AS (substr(measured_at, 1, 10)) VIRTUAL,
    protocol_type TEXT,
    vo2max_ml REAL,
    vo2max_rel REAL,
    lt1_power_w REAL,
    lt2_power_w REAL,
    fatmax_power_w REAL,
    fatmax_gmin REAL,
    vlamax REAL,
    at_power_w REAL,
    carbmax_w REAL,
    glycogen_g REAL,
    extraction_version TEXT NOT NULL,
    quality_flags_json TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(subject_id, source_kind, source_ref_id)
);

CREATE INDEX IF NOT EXISTS idx_sms_subject_measured_at
ON subject_metric_snapshots(subject_id, measured_at DESC);

CREATE INDEX IF NOT EXISTS idx_sms_source_kind_measured_at
ON subject_metric_snapshots(source_kind, measured_at DESC);

CREATE INDEX IF NOT EXISTS idx_sms_submission_id
ON subject_metric_snapshots(submission_id);
"""

MIGRATION_ADD_USER_ID = """
ALTER TABLE submissions ADD COLUMN user_id TEXT REFERENCES users(id);
"""

MIGRATION_ADD_ONBOARDING = """
ALTER TABLE users ADD COLUMN onboarding_completed INTEGER DEFAULT 0;
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


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Check whether a table exists in the database."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def init_db(db_path: Path) -> None:
    """Create tables if they don't exist and run migrations."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    conn.executescript(SCHEMA_SQL)
    # Migration: add user_id to submissions if missing (backward compat)
    if not _column_exists(conn, "submissions", "user_id"):
        conn.execute(MIGRATION_ADD_USER_ID)
        conn.commit()
    # Migration: add onboarding_completed to users if missing
    if not _column_exists(conn, "users", "onboarding_completed"):
        conn.execute(MIGRATION_ADD_ONBOARDING)
        conn.commit()
    # Migration: add subject_id to users if missing
    if not _column_exists(conn, "users", "subject_id"):
        conn.execute(
            "ALTER TABLE users ADD COLUMN subject_id TEXT REFERENCES subjects(id)"
        )
        conn.commit()
    # Migration: add subject_id + uploaded_by_user_id to submissions if missing
    if not _column_exists(conn, "submissions", "subject_id"):
        conn.execute(
            "ALTER TABLE submissions ADD COLUMN subject_id TEXT REFERENCES subjects(id)"
        )
        conn.commit()
    if not _column_exists(conn, "submissions", "uploaded_by_user_id"):
        conn.execute(
            "ALTER TABLE submissions ADD COLUMN uploaded_by_user_id TEXT REFERENCES users(id)"
        )
        conn.commit()
    # Migration: migrate user_profiles data into subjects for users that have profiles
    # but no linked subject yet
    _migrate_user_profiles_to_subjects(conn)
    conn.close()


def _migrate_user_profiles_to_subjects(conn: sqlite3.Connection) -> None:
    """One-time migration: create subjects from user_profiles and link users.

    Only runs for users who have a user_profile row but no subject_id set.
    This preserves existing data while transitioning to the subjects model.
    """
    if not _table_exists(conn, "user_profiles"):
        return

    rows = conn.execute(
        """SELECT u.id AS user_id, u.display_name,
                  p.gender, p.birth_year, p.height_cm, p.weight_kg,
                  p.body_fat_pct, p.skeletal_muscle_mass, p.bmi, p.training_level
           FROM users u
           JOIN user_profiles p ON u.id = p.user_id
           WHERE u.subject_id IS NULL
             AND (p.gender IS NOT NULL OR p.birth_year IS NOT NULL)"""
    ).fetchall()

    for row in rows:
        subject_id = str(uuid.uuid4())
        name = row["display_name"] or ""
        conn.execute(
            """INSERT INTO subjects
               (id, name, gender, birth_year, height_cm, weight_kg,
                body_fat_pct, skeletal_muscle_mass, bmi, training_level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                subject_id,
                name,
                row["gender"],
                row["birth_year"],
                row["height_cm"],
                row["weight_kg"],
                row["body_fat_pct"],
                row["skeletal_muscle_mass"],
                row["bmi"],
                row["training_level"],
            ),
        )
        conn.execute(
            "UPDATE users SET subject_id = ? WHERE id = ?",
            (subject_id, row["user_id"]),
        )
        # Also update any submissions by this user to have subject_id
        conn.execute(
            "UPDATE submissions SET subject_id = ? WHERE user_id = ? AND subject_id IS NULL",
            (subject_id, row["user_id"]),
        )

    if rows:
        conn.commit()


# ── Subject CRUD ──────────────────────────────────────────────────


SUBJECT_FIELDS = {
    "name", "gender", "birth_year", "height_cm", "weight_kg",
    "body_fat_pct", "skeletal_muscle_mass", "bmi", "training_level", "notes",
}


def create_subject(
    db_path: Path,
    name: str,
    gender: str = "",
    birth_year: int | None = None,
    height_cm: float | None = None,
    weight_kg: float | None = None,
    body_fat_pct: float | None = None,
    skeletal_muscle_mass: float | None = None,
    bmi: float | None = None,
    training_level: str = "",
    notes: str = "",
) -> dict:
    """Create a new subject and return the row dict."""
    subject_id = str(uuid.uuid4())
    conn = _connect(db_path)
    conn.execute(
        """INSERT INTO subjects
           (id, name, gender, birth_year, height_cm, weight_kg,
            body_fat_pct, skeletal_muscle_mass, bmi, training_level, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            subject_id, name, gender or None, birth_year,
            height_cm, weight_kg, body_fat_pct, skeletal_muscle_mass,
            bmi, training_level or None, notes or None,
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM subjects WHERE id = ?", (subject_id,)
    ).fetchone()
    conn.close()
    return dict(row)


def get_subject(db_path: Path, subject_id: str) -> dict | None:
    """Fetch a subject by ID, or None if not found."""
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT * FROM subjects WHERE id = ?", (subject_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def list_subjects(db_path: Path) -> list[dict]:
    """List all subjects, newest first."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT * FROM subjects ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_subject(
    db_path: Path,
    subject_id: str,
    **fields: str | float | int | None,
) -> dict | None:
    """Update a subject's fields. Returns updated subject dict, or None."""
    for key in fields:
        if key not in SUBJECT_FIELDS:
            raise ValueError(f"Unknown subject field '{key}'")

    if not fields:
        return get_subject(db_path, subject_id)

    sets = []
    params: list[str | float | int | None] = []
    for key, value in fields.items():
        sets.append(f"{key} = ?")
        params.append(value)
    params.append(subject_id)

    conn = _connect(db_path)
    conn.execute(
        f"UPDATE subjects SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM subjects WHERE id = ?", (subject_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def link_user_to_subject(
    db_path: Path, user_id: str, subject_id: str,
) -> dict | None:
    """Set user.subject_id. Returns the updated user dict, or None."""
    conn = _connect(db_path)
    conn.execute(
        "UPDATE users SET subject_id = ? WHERE id = ?",
        (subject_id, user_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def unlink_user_from_subject(db_path: Path, user_id: str) -> dict | None:
    """Clear user.subject_id. Returns the updated user dict, or None."""
    conn = _connect(db_path)
    conn.execute(
        "UPDATE users SET subject_id = NULL WHERE id = ?",
        (user_id,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


# ── Submission CRUD ──────────────────────────────────────────────────


def create_submission(
    db_path: Path,
    description: str,
    file_manifest: list[dict],
    workspace_path: str,
    subject_name: str = "",
    test_date: str = "",
    submission_id: str | None = None,
    user_id: str | None = None,
    subject_id: str | None = None,
    uploaded_by_user_id: str | None = None,
) -> str:
    """Insert a new submission and return its UUID.

    If submission_id is provided, use it; otherwise generate a new one.
    user_id is kept for backward compatibility; subject_id is the new FK.
    uploaded_by_user_id tracks who performed the upload.
    """
    if submission_id is None:
        submission_id = str(uuid.uuid4())
    manifest_json = json.dumps(file_manifest)
    conn = _connect(db_path)
    conn.execute(
        """INSERT INTO submissions
           (id, description, file_manifest, workspace_path, subject_name,
            test_date, user_id, subject_id, uploaded_by_user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (submission_id, description, manifest_json, workspace_path,
         subject_name, test_date, user_id, subject_id, uploaded_by_user_id),
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

    Returns the user row as a dict. Includes an extra ``is_new`` key (not a
    DB column) so callers can distinguish first-time vs returning users.
    """
    now = _now_utc()
    conn = _connect(db_path)

    row = conn.execute(
        "SELECT * FROM users WHERE google_id = ?", (google_id,)
    ).fetchone()

    is_new = row is None

    if is_new:
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
    result = dict(user)
    result["is_new"] = is_new
    return result


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


def complete_onboarding(
    db_path: Path,
    user_id: str,
    display_name: str,
) -> None:
    """Mark a user's onboarding as completed and update display_name."""
    conn = _connect(db_path)
    conn.execute(
        "UPDATE users SET onboarding_completed = 1, display_name = ? WHERE id = ?",
        (display_name, user_id),
    )
    conn.commit()
    conn.close()


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
    Also syncs body-comp fields to the linked subject (if any).
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

    # Sync body-comp fields to linked subject
    _sync_profile_to_subject(conn, user_id, fields)

    row = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row)


def _sync_profile_to_subject(
    conn: sqlite3.Connection,
    user_id: str,
    fields: dict[str, str | float | int | None],
) -> None:
    """Sync profile fields that overlap with subject columns."""
    user_row = conn.execute(
        "SELECT subject_id FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not user_row or not user_row["subject_id"]:
        return

    subject_id = user_row["subject_id"]
    subject_fields = SUBJECT_FIELDS & set(fields.keys())
    if not subject_fields:
        return

    sets = []
    params: list[str | float | int | None] = []
    for key in subject_fields:
        sets.append(f"{key} = ?")
        params.append(fields[key])
    params.append(subject_id)
    conn.execute(
        f"UPDATE subjects SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    conn.commit()


# ── Admin / Manage ──────────────────────────────────────────────────


VALID_ROLES = {"user", "researcher", "admin"}


def list_users(db_path: Path) -> list[dict]:
    """List all users with their profile data and linked subject, newest first."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT u.*, p.birth_year, p.gender, s.name AS subject_name
           FROM users u
           LEFT JOIN user_profiles p ON u.id = p.user_id
           LEFT JOIN subjects s ON u.subject_id = s.id
           ORDER BY u.created_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_user_role(db_path: Path, user_id: str, new_role: str) -> dict | None:
    """Update a user's role. Returns the updated user dict, or None if not found.

    Raises ValueError if new_role is not in VALID_ROLES.
    """
    if new_role not in VALID_ROLES:
        raise ValueError(f"Invalid role '{new_role}'. Must be one of: {VALID_ROLES}")
    conn = _connect(db_path)
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def list_submissions_with_users(db_path: Path) -> list[dict]:
    """List all submissions with linked user/subject info and latest job status."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT s.*,
                  u.display_name AS linked_user_name,
                  u.email AS linked_user_email,
                  sub.name AS linked_subject_name,
                  j.status AS job_status,
                  j.report_url
           FROM submissions s
           LEFT JOIN users u ON s.user_id = u.id
           LEFT JOIN subjects sub ON s.subject_id = sub.id
           LEFT JOIN (
               SELECT submission_id, status, report_url,
                      ROW_NUMBER() OVER (PARTITION BY submission_id ORDER BY rowid DESC) AS rn
               FROM jobs
           ) j ON s.id = j.submission_id AND j.rn = 1
           ORDER BY s.created_at DESC"""
    ).fetchall()
    conn.close()
    results = []
    for row in rows:
        d = dict(row)
        if d.get("file_manifest"):
            d["file_manifest"] = json.loads(d["file_manifest"])
        results.append(d)
    return results


def set_report_name_override(db_path: Path, report_slug: str, subject_name: str) -> None:
    """Set or update a subject_name override for a report slug."""
    conn = _connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO report_name_overrides (report_slug, subject_name, updated_at) "
        "VALUES (?, ?, datetime('now'))",
        (report_slug, subject_name.strip()),
    )
    conn.commit()
    conn.close()


def set_report_note(db_path: Path, report_slug: str, note: str) -> None:
    """Set a note for a report slug."""
    conn = _connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO report_notes (report_slug, note, updated_at) "
        "VALUES (?, ?, datetime('now'))",
        (report_slug, note.strip()),
    )
    conn.commit()
    conn.close()


def get_report_notes(db_path: Path) -> dict[str, str]:
    """Return dict of report_slug -> note."""
    conn = _connect(db_path)
    rows = conn.execute("SELECT report_slug, note FROM report_notes WHERE note != ''").fetchall()
    conn.close()
    return {row["report_slug"]: row["note"] for row in rows}


def get_report_name_overrides(db_path: Path) -> dict[str, str]:
    """Return dict of report_slug -> overridden subject_name."""
    conn = _connect(db_path)
    rows = conn.execute("SELECT report_slug, subject_name FROM report_name_overrides").fetchall()
    conn.close()
    return {row["report_slug"]: row["subject_name"] for row in rows}


def delete_submission(db_path: Path, submission_id: str) -> bool:
    """Delete a submission and its jobs. Returns True if found and deleted."""
    conn = _connect(db_path)
    row = conn.execute("SELECT id FROM submissions WHERE id = ?", (submission_id,)).fetchone()
    if row is None:
        conn.close()
        return False
    conn.execute("DELETE FROM jobs WHERE submission_id = ?", (submission_id,))
    conn.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))
    conn.commit()
    conn.close()
    return True


def update_submission_subject_name(
    db_path: Path, submission_id: str, subject_name: str,
) -> dict | None:
    """Update a submission's subject_name. Returns updated submission, or None."""
    conn = _connect(db_path)
    conn.execute(
        "UPDATE submissions SET subject_name = ? WHERE id = ?",
        (subject_name.strip(), submission_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM submissions WHERE id = ?", (submission_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    result["file_manifest"] = json.loads(result["file_manifest"])
    return result


def link_submission_user(
    db_path: Path, submission_id: str, user_id: str,
) -> dict | None:
    """Link a submission to a user. Returns the updated submission, or None."""
    conn = _connect(db_path)
    conn.execute(
        "UPDATE submissions SET user_id = ? WHERE id = ?",
        (user_id, submission_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM submissions WHERE id = ?", (submission_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    result["file_manifest"] = json.loads(result["file_manifest"])
    return result


def link_submission_subject(
    db_path: Path, submission_id: str, subject_id: str,
) -> dict | None:
    """Link a submission to a subject. Returns the updated submission, or None."""
    conn = _connect(db_path)
    # Also update subject_name from subject.name for display purposes
    subject_row = conn.execute(
        "SELECT name FROM subjects WHERE id = ?", (subject_id,)
    ).fetchone()
    if subject_row:
        conn.execute(
            "UPDATE submissions SET subject_id = ?, subject_name = ? WHERE id = ?",
            (subject_id, subject_row["name"], submission_id),
        )
    else:
        conn.execute(
            "UPDATE submissions SET subject_id = ? WHERE id = ?",
            (subject_id, submission_id),
        )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM submissions WHERE id = ?", (submission_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    result["file_manifest"] = json.loads(result["file_manifest"])
    return result


def unlink_submission_user(db_path: Path, submission_id: str) -> dict | None:
    """Remove user link from a submission. Returns the updated submission, or None."""
    conn = _connect(db_path)
    conn.execute(
        "UPDATE submissions SET user_id = NULL WHERE id = ?",
        (submission_id,),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM submissions WHERE id = ?", (submission_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    result["file_manifest"] = json.loads(result["file_manifest"])
    return result


# ── Report-User Links (for standalone published reports) ─────────────


def link_report_to_user(db_path: Path, report_slug: str, user_id: str) -> None:
    """Link a published report (by slug) to a user."""
    conn = _connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO report_user_links (report_slug, user_id, linked_at) "
        "VALUES (?, ?, datetime('now'))",
        (report_slug, user_id),
    )
    conn.commit()
    conn.close()


def unlink_report_from_user(db_path: Path, report_slug: str) -> None:
    """Remove a report-user link."""
    conn = _connect(db_path)
    conn.execute("DELETE FROM report_user_links WHERE report_slug = ?", (report_slug,))
    conn.commit()
    conn.close()


def get_report_user_links(db_path: Path) -> dict[str, str]:
    """Return a dict of report_slug -> user_id for all linked reports."""
    conn = _connect(db_path)
    rows = conn.execute("SELECT report_slug, user_id FROM report_user_links").fetchall()
    conn.close()
    return {row["report_slug"]: row["user_id"] for row in rows}


# ── Submissions by User ──────────────────────────────────────────────


def list_submissions_by_user(db_path: Path, user_id: str) -> list[dict]:
    """List submissions for a given user, newest first.

    Looks up the user's subject_id and returns submissions matching
    either user_id or subject_id (for the new subject-based model).
    """
    conn = _connect(db_path)
    # Get user's subject_id
    user_row = conn.execute(
        "SELECT subject_id FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    subject_id = user_row["subject_id"] if user_row else None

    if subject_id:
        rows = conn.execute(
            """SELECT * FROM submissions
               WHERE user_id = ? OR subject_id = ?
               ORDER BY rowid DESC""",
            (user_id, subject_id),
        ).fetchall()
    else:
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

_TREND_SUMMARY_METRICS: list[tuple[str, str, str]] = [
    ("vo2max_rel", "VO2max", "mL/kg/min"),
    ("lt1_power_w", "LT1", "W"),
    ("lt2_power_w", "LT2", "W"),
    ("fatmax_power_w", "FatMax", "W"),
    ("fatmax_gmin", "FatMax Ox", "g/min"),
]

_TREND_COMPARE_METRICS: list[tuple[str, str, str]] = [
    ("vo2max_ml", "VO2max", "mL/min"),
    ("vo2max_rel", "VO2max", "mL/kg/min"),
    ("lt1_power_w", "LT1", "W"),
    ("lt2_power_w", "LT2", "W"),
    ("fatmax_power_w", "FatMax", "W"),
    ("fatmax_gmin", "FatMax Ox", "g/min"),
]

_CPET_SNAPSHOT_EXTRACTION_VERSION = "cpet_snapshot_v1"
_CPET_SNAPSHOT_METRIC_KEYS = (
    "vo2max_ml",
    "vo2max_rel",
    "lt1_power_w",
    "lt2_power_w",
    "fatmax_power_w",
    "fatmax_gmin",
)
_INSCYD_SNAPSHOT_EXTRACTION_VERSION = "inscyd_snapshot_v1"
_INSCYD_SNAPSHOT_METRIC_MAP = {
    "vo2max_rel_ml_kg_min": "vo2max_rel",
    "fatmax_watt": "fatmax_power_w",
    "vlamax_mmol_l_s": "vlamax",
    "at_abs_watt": "at_power_w",
    "carbmax_abs_watt": "carbmax_w",
    "glycogen_abs_g": "glycogen_g",
}
_INSCYD_SNAPSHOT_METRIC_KEYS = (
    "vo2max_ml",
    "vo2max_rel",
    "fatmax_power_w",
    "vlamax",
    "at_power_w",
    "carbmax_w",
    "glycogen_g",
)
_SNAPSHOT_METRIC_COLUMNS = (
    "vo2max_ml",
    "vo2max_rel",
    "lt1_power_w",
    "lt2_power_w",
    "fatmax_power_w",
    "fatmax_gmin",
    "vlamax",
    "at_power_w",
    "carbmax_w",
    "glycogen_g",
)
_SNAPSHOT_BASE_COLUMNS = (
    "subject_id",
    "source_kind",
    "source_ref_id",
    "submission_id",
    "measured_at",
    "protocol_type",
    "extraction_version",
    "quality_flags_json",
    "payload_json",
)
_SNAPSHOT_MUTABLE_COLUMNS = _SNAPSHOT_BASE_COLUMNS + _SNAPSHOT_METRIC_COLUMNS


def _parse_analysis_result_value(raw_value: str | None) -> float | int | None:
    """Parse a numeric analysis_results value from JSON or plain text."""
    if raw_value is None:
        return None
    try:
        value = json.loads(raw_value)
        if isinstance(value, (int, float)):
            return value
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        return float(raw_value)
    except (ValueError, TypeError):
        return None


def _resolve_workspace_path(
    workspace_path: str | None,
    data_dir: Path | None = None,
) -> Path | None:
    """Resolve a submission workspace path to an absolute path when possible."""
    if not workspace_path:
        return None
    path = Path(workspace_path)
    if path.is_absolute() or data_dir is None:
        return path
    return data_dir / path


def _read_analysis_snapshot_source(analysis_db_path: Path) -> dict:
    """Read test_session metadata plus stable trend metrics from analysis.db."""
    if not analysis_db_path.exists():
        return {}

    try:
        conn = sqlite3.connect(str(analysis_db_path))
        conn.row_factory = sqlite3.Row

        table_check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='analysis_results'"
        ).fetchone()
        if table_check is None:
            conn.close()
            return {}

        session_row = conn.execute(
            "SELECT test_date, protocol_name FROM test_session LIMIT 1"
        ).fetchone()
        if session_row is None or not session_row["test_date"]:
            conn.close()
            return {}

        data: dict = {
            "test_date": session_row["test_date"],
            "protocol_name": session_row["protocol_name"] or "",
        }

        for category, keys in _TREND_METRICS.items():
            for src_key, dest_key in keys:
                row = conn.execute(
                    "SELECT value FROM analysis_results WHERE category = ? AND key = ?",
                    (category, src_key),
                ).fetchone()
                parsed = _parse_analysis_result_value(
                    row["value"] if row is not None else None
                )
                if parsed is not None:
                    data[dest_key] = parsed

        conn.close()
        return data
    except (sqlite3.Error, OSError):
        return {}


def extract_cpet_snapshot(
    db_path: Path,
    submission_id: str,
    data_dir: Path | None = None,
) -> dict | None:
    """Build a CPET snapshot row dict from a submission and its analysis.db."""
    submission = get_submission(db_path, submission_id)
    if submission is None or not submission.get("subject_id"):
        return None

    workspace = _resolve_workspace_path(submission.get("workspace_path"), data_dir=data_dir)
    if workspace is None:
        return None

    source = _read_analysis_snapshot_source(workspace / "analysis.db")
    if not source:
        return None

    present_metrics = {
        key: source[key]
        for key in _CPET_SNAPSHOT_METRIC_KEYS
        if key in source
    }
    missing_metrics = sorted(
        key for key in _CPET_SNAPSHOT_METRIC_KEYS if key not in present_metrics
    )
    quality_flags = [f"missing_{key}" for key in missing_metrics]
    protocol_type = source.get("protocol_name", "")
    if not protocol_type:
        quality_flags.append("missing_protocol_type")
    quality_flags.sort()

    payload = {
        "source": {
            "submission_id": submission_id,
            "workspace_path": submission.get("workspace_path", ""),
            "analysis_db_name": "analysis.db",
        },
        "test_session": {
            "test_date": source["test_date"],
            "protocol_name": protocol_type,
        },
        "metrics": present_metrics,
        "missing_metrics": missing_metrics,
    }

    snapshot = {
        "snapshot_id": str(uuid.uuid4()),
        "subject_id": submission["subject_id"],
        "source_kind": "cpet_submission",
        "source_ref_id": submission_id,
        "submission_id": submission_id,
        "measured_at": source["test_date"],
        "protocol_type": protocol_type or None,
        "extraction_version": _CPET_SNAPSHOT_EXTRACTION_VERSION,
        "quality_flags_json": json.dumps(quality_flags),
        "payload_json": json.dumps(payload, ensure_ascii=True, sort_keys=True),
    }
    snapshot.update(present_metrics)
    return snapshot


def _find_inscyd_report_html(workspace: Path) -> Path | None:
    """Find the rendered INSCYD report HTML inside a workspace."""
    candidates = [
        workspace / "report" / "index.html",
        workspace / "index.html",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _read_inscyd_report_data(report_html_path: Path) -> dict:
    """Read embedded report-data JSON from a rendered INSCYD report."""
    try:
        text = report_html_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    match = re.search(
        r'<script id="report-data" type="application/json">(.*?)</script>',
        text,
        re.DOTALL,
    )
    if match is None:
        return {}

    try:
        payload = html.unescape(match.group(1))
        data = json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def extract_inscyd_snapshot(
    db_path: Path,
    submission_id: str,
    data_dir: Path | None = None,
) -> dict | None:
    """Build an INSCYD snapshot row dict from a rendered report artifact."""
    submission = get_submission(db_path, submission_id)
    if submission is None or not submission.get("subject_id"):
        return None

    workspace = _resolve_workspace_path(submission.get("workspace_path"), data_dir=data_dir)
    if workspace is None:
        return None

    report_html = _find_inscyd_report_html(workspace)
    if report_html is None:
        return None

    report_data = _read_inscyd_report_data(report_html)
    if not report_data:
        return None

    session = report_data.get("session") if isinstance(report_data.get("session"), dict) else {}
    inscyd = report_data.get("inscyd") if isinstance(report_data.get("inscyd"), dict) else {}

    measured_at = str(session.get("test_date") or "").strip()
    quality_flags: list[str] = []
    if not measured_at:
        measured_at = str(submission.get("test_date") or "").strip()
        if measured_at:
            quality_flags.append("fallback_submission_test_date")
    if not measured_at:
        return None

    protocol_type = str(session.get("test_type") or "").strip()
    if not protocol_type:
        quality_flags.append("missing_protocol_type")

    present_metrics: dict[str, float | int] = {}
    for src_key, dest_key in _INSCYD_SNAPSHOT_METRIC_MAP.items():
        value = inscyd.get(src_key)
        if isinstance(value, (int, float)):
            present_metrics[dest_key] = value

    missing_metrics = sorted(
        key for key in _INSCYD_SNAPSHOT_METRIC_KEYS if key not in present_metrics
    )
    quality_flags.extend(f"missing_{key}" for key in missing_metrics)
    quality_flags.sort()

    relative_report_html = report_html.relative_to(workspace).as_posix()
    payload = {
        "source": {
            "submission_id": submission_id,
            "workspace_path": submission.get("workspace_path", ""),
            "report_html": relative_report_html,
        },
        "meta": report_data.get("meta", {}),
        "subject": report_data.get("subject", {}),
        "session": session,
        "inscyd": inscyd,
        "warnings": report_data.get("warnings", []),
        "missing_metrics": missing_metrics,
    }

    snapshot = {
        "snapshot_id": str(uuid.uuid4()),
        "subject_id": submission["subject_id"],
        "source_kind": "inscyd_report",
        "source_ref_id": submission_id,
        "submission_id": submission_id,
        "measured_at": measured_at,
        "protocol_type": protocol_type or None,
        "extraction_version": _INSCYD_SNAPSHOT_EXTRACTION_VERSION,
        "quality_flags_json": json.dumps(quality_flags),
        "payload_json": json.dumps(payload, ensure_ascii=True, sort_keys=True),
    }
    snapshot.update(present_metrics)
    return snapshot


def _list_snapshot_candidate_submissions(
    db_path: Path,
    submission_ids: list[str] | None = None,
) -> list[dict]:
    """List submissions that can be scanned for snapshot extraction."""
    conn = _connect(db_path)
    if submission_ids:
        placeholders = ", ".join("?" for _ in submission_ids)
        rows = conn.execute(
            f"SELECT * FROM submissions WHERE id IN ({placeholders}) ORDER BY created_at ASC",
            submission_ids,
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM submissions ORDER BY created_at ASC"
        ).fetchall()
    conn.close()
    results = []
    for row in rows:
        item = dict(row)
        if item.get("file_manifest"):
            item["file_manifest"] = json.loads(item["file_manifest"])
        results.append(item)
    return results


def upsert_subject_metric_snapshot(
    db_path: Path,
    snapshot: dict,
    dry_run: bool = False,
) -> dict:
    """Insert or refresh a subject_metric_snapshots row by its source artifact key."""
    conn = _connect(db_path)
    existing = conn.execute(
        """SELECT * FROM subject_metric_snapshots
           WHERE subject_id = ? AND source_kind = ? AND source_ref_id = ?""",
        (
            snapshot["subject_id"],
            snapshot["source_kind"],
            snapshot["source_ref_id"],
        ),
    ).fetchone()

    if existing is None:
        if dry_run:
            conn.close()
            return {"action": "would_insert", "snapshot_id": snapshot.get("snapshot_id")}

        now = _now_utc()
        payload = {
            "snapshot_id": snapshot.get("snapshot_id") or str(uuid.uuid4()),
            "created_at": now,
            "updated_at": now,
        }
        for column in _SNAPSHOT_MUTABLE_COLUMNS:
            payload[column] = snapshot.get(column)

        columns = ["snapshot_id", *_SNAPSHOT_MUTABLE_COLUMNS, "created_at", "updated_at"]
        placeholders = ", ".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO subject_metric_snapshots ({', '.join(columns)}) VALUES ({placeholders})",
            [payload[column] for column in columns],
        )
        conn.commit()
        conn.close()
        return {"action": "inserted", "snapshot_id": payload["snapshot_id"]}

    existing_dict = dict(existing)
    if existing_dict.get("extraction_version") == snapshot.get("extraction_version"):
        conn.close()
        return {"action": "skipped", "snapshot_id": existing_dict["snapshot_id"]}

    if dry_run:
        conn.close()
        return {"action": "would_update", "snapshot_id": existing_dict["snapshot_id"]}

    now = _now_utc()
    set_clause = ", ".join(f"{column} = ?" for column in (*_SNAPSHOT_MUTABLE_COLUMNS, "updated_at"))
    values = [snapshot.get(column) for column in _SNAPSHOT_MUTABLE_COLUMNS]
    values.append(now)
    values.append(existing_dict["snapshot_id"])
    conn.execute(
        f"UPDATE subject_metric_snapshots SET {set_clause} WHERE snapshot_id = ?",
        values,
    )
    conn.commit()
    conn.close()
    return {"action": "updated", "snapshot_id": existing_dict["snapshot_id"]}


def backfill_subject_metric_snapshots(
    db_path: Path,
    submission_ids: list[str] | None = None,
    data_dir: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """Scan submissions, extract snapshot rows, and upsert them into the platform DB."""
    submissions = _list_snapshot_candidate_submissions(db_path, submission_ids=submission_ids)
    extractors = (extract_cpet_snapshot, extract_inscyd_snapshot)

    summary = {
        "dry_run": dry_run,
        "submissions_scanned": len(submissions),
        "snapshots_found": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "would_insert": 0,
        "would_update": 0,
        "errors": [],
    }

    for submission in submissions:
        submission_id = submission["id"]
        for extractor in extractors:
            try:
                snapshot = extractor(db_path, submission_id, data_dir=data_dir)
            except Exception as exc:  # pragma: no cover - defensive runner guard
                summary["errors"].append(
                    {
                        "submission_id": submission_id,
                        "extractor": extractor.__name__,
                        "error": str(exc),
                    }
                )
                continue

            if snapshot is None:
                continue

            summary["snapshots_found"] += 1
            result = upsert_subject_metric_snapshot(db_path, snapshot, dry_run=dry_run)
            action = result["action"]
            if action == "inserted":
                summary["inserted"] += 1
            elif action == "updated":
                summary["updated"] += 1
            elif action == "skipped":
                summary["skipped"] += 1
            elif action == "would_insert":
                summary["would_insert"] += 1
            elif action == "would_update":
                summary["would_update"] += 1

    return summary


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


def summarize_fitness_trends(trends: list[dict]) -> dict:
    """Build compact summary cards from trend rows."""
    if not trends:
        return {
            "total_tests": 0,
            "latest_test_date": None,
            "subject_name": "",
            "cards": [],
        }

    cards: list[dict] = []
    latest_test_date = trends[-1].get("test_date")
    subject_name = str(trends[-1].get("subject_name") or "")

    for key, label, unit in _TREND_SUMMARY_METRICS:
        history = [entry for entry in trends if entry.get(key) is not None]
        if not history:
            continue

        latest_entry = history[-1]
        latest_value = latest_entry.get(key)
        prev_entry = history[-2] if len(history) >= 2 else None
        delta = None
        if prev_entry is not None:
            try:
                delta = round(float(latest_value) - float(prev_entry[key]), 2)
            except (TypeError, ValueError, KeyError):
                delta = None

        best_entry = max(history, key=lambda entry: float(entry.get(key) or 0))
        try:
            gap_to_best = round(float(latest_value) - float(best_entry.get(key) or 0), 2)
        except (TypeError, ValueError):
            gap_to_best = None

        cards.append({
            "key": key,
            "label": label,
            "unit": unit,
            "latest_value": latest_value,
            "latest_test_date": latest_entry.get("test_date"),
            "delta": delta,
            "best_value": best_entry.get(key),
            "best_test_date": best_entry.get("test_date"),
            "is_best_now": latest_entry is best_entry,
            "gap_to_best": gap_to_best,
        })

    return {
        "total_tests": len(trends),
        "latest_test_date": latest_test_date,
        "subject_name": subject_name,
        "cards": cards,
    }


def build_fitness_trend_options(trends: list[dict]) -> list[dict]:
    """Return select-friendly trend options ordered newest first."""
    options: list[dict] = []
    for index, entry in enumerate(reversed(trends)):
        test_date = str(entry.get("test_date") or "날짜 없음")
        subject_name = str(entry.get("subject_name") or "").strip()
        label = test_date if not subject_name else f"{test_date} · {subject_name}"
        options.append({
            "submission_id": entry.get("submission_id"),
            "test_date": entry.get("test_date"),
            "label": label,
            "is_latest": index == 0,
        })
    return options


def build_fitness_trend_compare(
    trends: list[dict],
    baseline_submission_id: str | None = None,
    current_submission_id: str | None = None,
) -> dict:
    """Build a two-point comparison payload from trend rows."""
    if len(trends) < 2:
        return {
            "enabled": False,
            "baseline_submission_id": None,
            "baseline_test_date": None,
            "current_submission_id": None,
            "current_test_date": None,
            "metrics": [],
        }

    trend_map = {
        str(entry["submission_id"]): entry
        for entry in trends
        if entry.get("submission_id")
    }

    if current_submission_id is not None and current_submission_id not in trend_map:
        raise ValueError("invalid current selection")
    if baseline_submission_id is not None and baseline_submission_id not in trend_map:
        raise ValueError("invalid baseline selection")

    current_entry = (
        trend_map[current_submission_id]
        if current_submission_id is not None
        else trends[-1]
    )
    current_index = trends.index(current_entry)

    if baseline_submission_id is not None:
        baseline_entry = trend_map[baseline_submission_id]
    else:
        baseline_index = current_index - 1 if current_index > 0 else 1
        baseline_entry = trends[baseline_index]

    if baseline_entry["submission_id"] == current_entry["submission_id"]:
        raise ValueError("baseline and current selections must differ")

    metrics: list[dict] = []
    for key, label, unit in _TREND_COMPARE_METRICS:
        if baseline_entry.get(key) is None or current_entry.get(key) is None:
            continue

        before = baseline_entry[key]
        after = current_entry[key]
        try:
            delta = round(float(after) - float(before), 2)
        except (TypeError, ValueError):
            continue

        metrics.append({
            "key": key,
            "label": label,
            "unit": unit,
            "before_value": before,
            "after_value": after,
            "delta": delta,
        })

    return {
        "enabled": True,
        "baseline_submission_id": baseline_entry.get("submission_id"),
        "baseline_test_date": baseline_entry.get("test_date"),
        "current_submission_id": current_entry.get("submission_id"),
        "current_test_date": current_entry.get("test_date"),
        "metrics": metrics,
    }
