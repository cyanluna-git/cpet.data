"""
server.db — Platform SQLite CRUD for submissions, jobs, users, subjects, and profiles.

Every function takes a db_path: Path parameter. No global state.
Uses raw sqlite3, WAL mode, TEXT primary keys (UUID).
"""

import gzip
import html
import hashlib
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
    source_signature TEXT,
    submission_fingerprint TEXT,
    duplicate_confidence TEXT,
    duplicate_group_key TEXT,
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

CREATE TABLE IF NOT EXISTS report_catalog (
    report_slug TEXT PRIMARY KEY,
    subject_name TEXT NOT NULL,
    test_date TEXT,
    analysis_method TEXT NOT NULL DEFAULT '알 수 없음',
    report_version TEXT NOT NULL DEFAULT '기본 리포트',
    report_url TEXT NOT NULL,
    completed_at TEXT,
    file_tags_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_report_catalog_test_date
ON report_catalog(test_date DESC, completed_at DESC);

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

CREATE TABLE IF NOT EXISTS subject_feature_sets (
    feature_row_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(id),
    feature_spec_key TEXT NOT NULL,
    feature_spec_version TEXT NOT NULL,
    anchor_snapshot_id TEXT REFERENCES subject_metric_snapshots(snapshot_id),
    anchor_measured_at TEXT NOT NULL,
    window_label TEXT,
    input_snapshot_ids_json TEXT NOT NULL DEFAULT '[]',
    input_source_kinds_json TEXT NOT NULL DEFAULT '[]',
    feature_payload_json TEXT NOT NULL DEFAULT '{}',
    quality_flags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(subject_id, feature_spec_key, feature_spec_version, anchor_snapshot_id, window_label)
);

CREATE INDEX IF NOT EXISTS idx_sfs_subject_anchor
ON subject_feature_sets(subject_id, anchor_measured_at DESC);

CREATE INDEX IF NOT EXISTS idx_sfs_spec
ON subject_feature_sets(feature_spec_key, feature_spec_version, anchor_measured_at DESC);

CREATE TABLE IF NOT EXISTS notes_board (
    slug TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    html_content TEXT NOT NULL,
    uploaded_by_user_id TEXT REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS submission_files (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_gz BLOB NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(submission_id, filename)
);

CREATE INDEX IF NOT EXISTS idx_submission_files_submission
ON submission_files(submission_id);
"""

MIGRATION_ADD_USER_ID = """
ALTER TABLE submissions ADD COLUMN user_id TEXT REFERENCES users(id);
"""

MIGRATION_ADD_ONBOARDING = """
ALTER TABLE users ADD COLUMN onboarding_completed INTEGER DEFAULT 0;
"""

MIGRATION_ADD_SOURCE_SIGNATURE = """
ALTER TABLE submissions ADD COLUMN source_signature TEXT;
"""

MIGRATION_ADD_SUBMISSION_FINGERPRINT = """
ALTER TABLE submissions ADD COLUMN submission_fingerprint TEXT;
"""

MIGRATION_ADD_DUPLICATE_CONFIDENCE = """
ALTER TABLE submissions ADD COLUMN duplicate_confidence TEXT;
"""

MIGRATION_ADD_DUPLICATE_GROUP_KEY = """
ALTER TABLE submissions ADD COLUMN duplicate_group_key TEXT;
"""

MIGRATION_ADD_REPORT_HTML_CONTENT = """
ALTER TABLE report_catalog ADD COLUMN html_content TEXT;
"""

VALID_STATUSES = {"pending", "processing", "done", "failed"}


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with Row factory, WAL mode, and FK enforcement."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
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

    if not _column_exists(conn, "submissions", "source_signature"):
        conn.execute(MIGRATION_ADD_SOURCE_SIGNATURE)

    if not _column_exists(conn, "submissions", "submission_fingerprint"):
        conn.execute(MIGRATION_ADD_SUBMISSION_FINGERPRINT)

    if not _column_exists(conn, "submissions", "duplicate_confidence"):
        conn.execute(MIGRATION_ADD_DUPLICATE_CONFIDENCE)

    if not _column_exists(conn, "submissions", "duplicate_group_key"):
        conn.execute(MIGRATION_ADD_DUPLICATE_GROUP_KEY)
        conn.commit()
    if not _column_exists(conn, "report_catalog", "html_content"):
        conn.execute(MIGRATION_ADD_REPORT_HTML_CONTENT)
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


def delete_subject(db_path: Path, subject_id: str) -> bool:
    """Delete a subject. Returns True if found and deleted."""
    conn = _connect(db_path)
    cursor = conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def link_user_to_subject(
    db_path: Path, user_id: str, subject_id: str,
) -> dict | None:
    """Set user.subject_id. Returns the updated user dict, or None."""
    conn = _connect(db_path)
    subject_row = conn.execute(
        "SELECT name FROM subjects WHERE id = ?",
        (subject_id,),
    ).fetchone()
    conn.execute(
        "UPDATE users SET subject_id = ? WHERE id = ?",
        (subject_id, user_id),
    )
    if subject_row is not None:
        conn.execute(
            """UPDATE submissions
               SET subject_id = ?,
                   subject_name = CASE
                       WHEN COALESCE(subject_name, '') = '' THEN ?
                       ELSE subject_name
                   END
               WHERE user_id = ?
                 AND subject_id IS NULL""",
            (subject_id, subject_row["name"], user_id),
        )
    else:
        conn.execute(
            """UPDATE submissions
               SET subject_id = ?
               WHERE user_id = ?
                 AND subject_id IS NULL""",
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
    source_signature: str = "",
    submission_fingerprint: str = "",
    duplicate_confidence: str = "",
    duplicate_group_key: str = "",
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
            test_date, user_id, subject_id, uploaded_by_user_id,
            source_signature, submission_fingerprint, duplicate_confidence, duplicate_group_key)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            submission_id,
            description,
            manifest_json,
            workspace_path,
            subject_name,
            test_date,
            user_id,
            subject_id,
            uploaded_by_user_id,
            source_signature.strip(),
            submission_fingerprint.strip(),
            duplicate_confidence.strip(),
            duplicate_group_key.strip(),
        ),
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


def get_submission_id_for_report_slug(
    db_path: Path,
    report_slug: str,
) -> str | None:
    """Return the most recent submission_id linked to a report_slug via jobs."""
    conn = _connect(db_path)
    row = conn.execute(
        """SELECT submission_id FROM jobs
           WHERE report_slug = ?
             AND submission_id IS NOT NULL
             AND submission_id != ''
           ORDER BY rowid DESC
           LIMIT 1""",
        (report_slug,),
    ).fetchone()
    conn.close()
    return row["submission_id"] if row else None


def get_latest_job(db_path: Path, submission_id: str) -> dict | None:
    """Return the most recently created job for a submission."""
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT * FROM jobs WHERE submission_id = ? ORDER BY rowid DESC LIMIT 1",
        (submission_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def reset_job_for_reanalysis(db_path: Path, job_id: str) -> None:
    """Reset an existing job back to pending for re-analysis, preserving its report_slug."""
    conn = _connect(db_path)
    conn.execute(
        """UPDATE jobs
           SET status = 'pending',
               started_at = NULL,
               completed_at = NULL,
               error_message = NULL
           WHERE id = ?""",
        (job_id,),
    )
    conn.commit()
    conn.close()


def get_prior_report_slug(
    db_path: Path,
    submission_id: str,
    exclude_job_id: str | None = None,
) -> str | None:
    """Return the most recent done job's report_slug for a submission.

    Used by re-analysis to find the existing published slug so the report
    URL stays stable across re-runs.
    """
    conn = _connect(db_path)
    if exclude_job_id is not None:
        row = conn.execute(
            """SELECT report_slug FROM jobs
               WHERE submission_id = ?
                 AND status = 'done'
                 AND report_slug IS NOT NULL
                 AND report_slug != ''
                 AND id != ?
               ORDER BY rowid DESC
               LIMIT 1""",
            (submission_id, exclude_job_id),
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT report_slug FROM jobs
               WHERE submission_id = ?
                 AND status = 'done'
                 AND report_slug IS NOT NULL
                 AND report_slug != ''
               ORDER BY rowid DESC
               LIMIT 1""",
            (submission_id,),
        ).fetchone()
    conn.close()
    return row["report_slug"] if row else None


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


def get_user_by_email(db_path: Path, email: str) -> dict | None:
    """Fetch a user by email, or None if not found."""
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
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


def update_user(db_path: Path, user_id: str, display_name: str | None = None) -> dict | None:
    """Update mutable user fields. Returns updated user dict, or None if not found."""
    conn = _connect(db_path)
    if display_name is not None:
        conn.execute(
            "UPDATE users SET display_name = ? WHERE id = ?",
            (display_name.strip() or None, user_id),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


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


def update_submission_duplicate_metadata(
    db_path: Path,
    submission_id: str,
    *,
    source_signature: str = "",
    submission_fingerprint: str = "",
    duplicate_confidence: str = "",
    duplicate_group_key: str = "",
) -> None:
    """Persist duplicate detection metadata for a submission."""
    conn = _connect(db_path)
    conn.execute(
        """UPDATE submissions
           SET source_signature = ?,
               submission_fingerprint = ?,
               duplicate_confidence = ?,
               duplicate_group_key = ?
           WHERE id = ?""",
        (
            source_signature.strip(),
            submission_fingerprint.strip(),
            duplicate_confidence.strip(),
            duplicate_group_key.strip(),
            submission_id,
        ),
    )
    conn.commit()
    conn.close()


def list_duplicate_submission_candidates(
    db_path: Path,
    *,
    user_id: str = "",
    subject_id: str = "",
    test_date: str = "",
    source_signature: str = "",
    submission_fingerprint: str = "",
    exclude_submission_id: str = "",
) -> list[dict]:
    """Return recent submission candidates for duplicate detection."""
    conn = _connect(db_path)
    where = []
    params: list[str] = []

    if submission_fingerprint:
        where.append("s.submission_fingerprint = ?")
        params.append(submission_fingerprint)
        if exclude_submission_id:
            where.append("s.id != ?")
            params.append(exclude_submission_id)

    exact_sql = ""
    if where:
        exact_sql = (
            """SELECT s.*, j.report_slug, j.report_url,
                      u.display_name AS linked_user_name,
                      subj.name AS linked_subject_name
               FROM submissions s
               LEFT JOIN users u ON s.user_id = u.id
               LEFT JOIN subjects subj ON s.subject_id = subj.id
               LEFT JOIN (
                   SELECT submission_id, report_slug, report_url,
                          ROW_NUMBER() OVER (PARTITION BY submission_id ORDER BY rowid DESC) AS rn
                   FROM jobs
               ) j ON s.id = j.submission_id AND j.rn = 1
               WHERE """
            + " AND ".join(where)
            + " ORDER BY s.created_at DESC"
        )
    rows = conn.execute(exact_sql, params).fetchall() if exact_sql else []

    likely_where = []
    likely_params: list[str] = []
    if exclude_submission_id:
        likely_where.append("s.id != ?")
        likely_params.append(exclude_submission_id)
    if test_date:
        likely_where.append("COALESCE(s.test_date, '') = ?")
        likely_params.append(test_date)
    user_subject_terms = []
    if user_id:
        user_subject_terms.append("s.user_id = ?")
        likely_params.append(user_id)
    if subject_id:
        user_subject_terms.append("s.subject_id = ?")
        likely_params.append(subject_id)
    if user_subject_terms:
        likely_where.append("(" + " OR ".join(user_subject_terms) + ")")
    if source_signature:
        likely_where.append("COALESCE(s.source_signature, '') = ?")
        likely_params.append(source_signature)

    likely_sql = ""
    if test_date and source_signature and user_subject_terms:
        likely_sql = (
            """SELECT s.*, j.report_slug, j.report_url,
                      u.display_name AS linked_user_name,
                      subj.name AS linked_subject_name
               FROM submissions s
               LEFT JOIN users u ON s.user_id = u.id
               LEFT JOIN subjects subj ON s.subject_id = subj.id
               LEFT JOIN (
                   SELECT submission_id, report_slug, report_url,
                          ROW_NUMBER() OVER (PARTITION BY submission_id ORDER BY rowid DESC) AS rn
                   FROM jobs
               ) j ON s.id = j.submission_id AND j.rn = 1
               WHERE """
            + " AND ".join(likely_where)
            + " ORDER BY s.created_at DESC"
        )
    likely_rows = conn.execute(likely_sql, likely_params).fetchall() if likely_sql else []
    conn.close()

    seen: set[str] = set()
    result: list[dict] = []
    for row, confidence in [(row, "exact") for row in rows] + [(row, "likely") for row in likely_rows]:
        item = dict(row)
        sid = str(item["id"])
        if sid in seen:
            continue
        seen.add(sid)
        if item.get("file_manifest"):
            item["file_manifest"] = json.loads(item["file_manifest"])
        item["duplicate_confidence"] = confidence
        result.append(item)
    return result


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


def upsert_report_catalog_entry(
    db_path: Path,
    *,
    report_slug: str,
    subject_name: str,
    test_date: str,
    analysis_method: str,
    report_version: str,
    report_url: str,
    completed_at: str | None,
    file_tags: list[str] | None = None,
) -> None:
    """Insert or update a published report metadata row."""
    conn = _connect(db_path)
    conn.execute(
        """INSERT OR REPLACE INTO report_catalog (
               report_slug,
               subject_name,
               test_date,
               analysis_method,
               report_version,
               report_url,
               completed_at,
               file_tags_json,
               updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
        (
            report_slug,
            subject_name.strip(),
            test_date.strip(),
            analysis_method.strip() or "알 수 없음",
            report_version.strip() or "기본 리포트",
            report_url.strip(),
            completed_at,
            json.dumps(file_tags or []),
        ),
    )
    conn.commit()
    conn.close()


def store_report_html(db_path: Path, report_slug: str, html_content: str) -> None:
    """Persist report HTML in report_catalog. Row must already exist."""
    conn = _connect(db_path)
    conn.execute(
        "UPDATE report_catalog SET html_content = ?, updated_at = datetime('now') WHERE report_slug = ?",
        (html_content, report_slug),
    )
    conn.commit()
    conn.close()


def get_report_html(db_path: Path, report_slug: str) -> str | None:
    """Return stored HTML content for a slug, or None."""
    conn = _connect(db_path)
    row = conn.execute(
        "SELECT html_content FROM report_catalog WHERE report_slug = ?",
        (report_slug,),
    ).fetchone()
    conn.close()
    return row["html_content"] if row and row["html_content"] else None


def delete_report_catalog_entry(db_path: Path, report_slug: str) -> None:
    """Delete a published report metadata row by slug."""
    conn = _connect(db_path)
    conn.execute("DELETE FROM report_catalog WHERE report_slug = ?", (report_slug,))
    conn.commit()
    conn.close()


def delete_report_metadata(db_path: Path, report_slug: str) -> dict[str, int]:
    """Delete all report-scoped metadata rows for a published report slug."""
    conn = _connect(db_path)
    deleted = {
        "report_catalog": conn.execute(
            "DELETE FROM report_catalog WHERE report_slug = ?",
            (report_slug,),
        ).rowcount,
        "report_user_links": conn.execute(
            "DELETE FROM report_user_links WHERE report_slug = ?",
            (report_slug,),
        ).rowcount,
        "report_name_overrides": conn.execute(
            "DELETE FROM report_name_overrides WHERE report_slug = ?",
            (report_slug,),
        ).rowcount,
        "report_notes": conn.execute(
            "DELETE FROM report_notes WHERE report_slug = ?",
            (report_slug,),
        ).rowcount,
    }
    conn.commit()
    conn.close()
    return deleted


def _delete_snapshot_dependencies(
    conn: sqlite3.Connection,
    snapshot_ids: list[str],
) -> dict[str, int]:
    """Delete feature rows that reference snapshot_ids, then delete snapshots."""
    if not snapshot_ids:
        return {"feature_sets": 0, "snapshots": 0}

    rows = conn.execute(
        "SELECT feature_row_id, anchor_snapshot_id, input_snapshot_ids_json FROM subject_feature_sets"
    ).fetchall()
    snapshot_id_set = set(snapshot_ids)
    feature_row_ids: list[str] = []
    for row in rows:
        if row["anchor_snapshot_id"] in snapshot_id_set:
            feature_row_ids.append(str(row["feature_row_id"]))
            continue
        try:
            input_snapshot_ids = json.loads(row["input_snapshot_ids_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            input_snapshot_ids = []
        if any(str(item) in snapshot_id_set for item in input_snapshot_ids):
            feature_row_ids.append(str(row["feature_row_id"]))

    feature_deleted = 0
    if feature_row_ids:
        placeholders = ", ".join("?" for _ in feature_row_ids)
        feature_deleted = conn.execute(
            f"DELETE FROM subject_feature_sets WHERE feature_row_id IN ({placeholders})",
            feature_row_ids,
        ).rowcount

    placeholders = ", ".join("?" for _ in snapshot_ids)
    snapshot_deleted = conn.execute(
        f"DELETE FROM subject_metric_snapshots WHERE snapshot_id IN ({placeholders})",
        snapshot_ids,
    ).rowcount

    return {"feature_sets": feature_deleted, "snapshots": snapshot_deleted}


def delete_submission_derived_metrics(db_path: Path, submission_id: str) -> dict[str, int]:
    """Delete snapshot/feature rows derived from a submission."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT snapshot_id
           FROM subject_metric_snapshots
           WHERE submission_id = ? OR source_ref_id = ?""",
        (submission_id, submission_id),
    ).fetchall()
    snapshot_ids = [str(row["snapshot_id"]) for row in rows]
    deleted = _delete_snapshot_dependencies(conn, snapshot_ids)
    conn.commit()
    conn.close()
    return deleted


def delete_report_derived_metrics(db_path: Path, report_slug: str) -> dict[str, int]:
    """Delete snapshot/feature rows derived from a standalone published report."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT snapshot_id
           FROM subject_metric_snapshots
           WHERE source_ref_id = ?""",
        (report_slug,),
    ).fetchall()
    snapshot_ids = [str(row["snapshot_id"]) for row in rows]
    deleted = _delete_snapshot_dependencies(conn, snapshot_ids)
    conn.commit()
    conn.close()
    return deleted


def _list_subject_ids_for_submission_refs(
    db_path: Path,
    submission_ids: list[str],
) -> list[str]:
    """Return subject ids associated with submissions or their existing snapshots."""
    if not submission_ids:
        return []

    placeholders = ", ".join("?" for _ in submission_ids)
    conn = _connect(db_path)
    rows = conn.execute(
        f"""
        SELECT DISTINCT subject_id
          FROM (
            SELECT subject_id
              FROM submissions
             WHERE id IN ({placeholders})
            UNION
            SELECT subject_id
              FROM subject_metric_snapshots
             WHERE submission_id IN ({placeholders})
                OR source_ref_id IN ({placeholders})
          )
         WHERE subject_id IS NOT NULL
        """,
        [*submission_ids, *submission_ids, *submission_ids],
    ).fetchall()
    conn.close()
    return [str(row["subject_id"]) for row in rows if row["subject_id"]]


def _list_subject_ids_for_report_refs(
    db_path: Path,
    report_slugs: list[str],
) -> list[str]:
    """Return subject ids associated with report links or their existing snapshots."""
    if not report_slugs:
        return []

    placeholders = ", ".join("?" for _ in report_slugs)
    conn = _connect(db_path)
    rows = conn.execute(
        f"""
        SELECT DISTINCT subject_id
          FROM (
            SELECT u.subject_id
              FROM report_user_links rul
              JOIN users u ON u.id = rul.user_id
             WHERE rul.report_slug IN ({placeholders})
            UNION
            SELECT subject_id
              FROM subject_metric_snapshots
             WHERE source_ref_id IN ({placeholders})
          )
         WHERE subject_id IS NOT NULL
        """,
        [*report_slugs, *report_slugs],
    ).fetchall()
    conn.close()
    return [str(row["subject_id"]) for row in rows if row["subject_id"]]


def list_submission_ids_for_user(
    db_path: Path,
    user_id: str,
) -> list[str]:
    """Return submission ids linked to a user."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT id FROM submissions WHERE user_id = ? ORDER BY created_at ASC, id ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [str(row["id"]) for row in rows]


def list_report_slugs_for_user(
    db_path: Path,
    user_id: str,
) -> list[str]:
    """Return standalone report slugs linked to a user."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT report_slug FROM report_user_links WHERE user_id = ? ORDER BY linked_at ASC, report_slug ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [str(row["report_slug"]) for row in rows]


def list_snapshot_ids_for_subjects(
    db_path: Path,
    subject_ids: list[str],
) -> list[str]:
    """Return snapshot ids for subjects in stable chronological order."""
    if not subject_ids:
        return []

    placeholders = ", ".join("?" for _ in subject_ids)
    conn = _connect(db_path)
    rows = conn.execute(
        f"""SELECT snapshot_id
              FROM subject_metric_snapshots
             WHERE subject_id IN ({placeholders})
             ORDER BY measured_at ASC, created_at ASC, snapshot_id ASC""",
        subject_ids,
    ).fetchall()
    conn.close()
    return [str(row["snapshot_id"]) for row in rows]


def refresh_targeted_materializations(
    db_path: Path,
    *,
    subject_ids: list[str] | None = None,
    submission_ids: list[str] | None = None,
    report_slugs: list[str] | None = None,
    data_dir: Path | None = None,
    published_dir: Path | None = None,
) -> dict:
    """Refresh snapshots and feature rows for a narrow set of changed sources."""
    submission_ids = sorted({str(item) for item in (submission_ids or []) if item})
    report_slugs = sorted({str(item) for item in (report_slugs or []) if item})
    affected_subject_ids = {str(item) for item in (subject_ids or []) if item}

    affected_subject_ids.update(_list_subject_ids_for_submission_refs(db_path, submission_ids))
    affected_subject_ids.update(_list_subject_ids_for_report_refs(db_path, report_slugs))

    deleted = {
        "submission_snapshots": 0,
        "submission_feature_sets": 0,
        "report_snapshots": 0,
        "report_feature_sets": 0,
    }
    for submission_id in submission_ids:
        result = delete_submission_derived_metrics(db_path, submission_id)
        deleted["submission_snapshots"] += int(result.get("snapshots", 0))
        deleted["submission_feature_sets"] += int(result.get("feature_sets", 0))

    for report_slug in report_slugs:
        result = delete_report_derived_metrics(db_path, report_slug)
        deleted["report_snapshots"] += int(result.get("snapshots", 0))
        deleted["report_feature_sets"] += int(result.get("feature_sets", 0))

    if submission_ids or report_slugs:
        snapshot_summary = backfill_subject_metric_snapshots(
            db_path,
            submission_ids=submission_ids or None,
            report_slugs=report_slugs or None,
            data_dir=data_dir,
            published_dir=published_dir if report_slugs else None,
        )
    else:
        snapshot_summary = {
            "dry_run": False,
            "submissions_scanned": 0,
            "snapshots_found": 0,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "would_insert": 0,
            "would_update": 0,
            "errors": [],
        }

    affected_subject_ids.update(_list_subject_ids_for_submission_refs(db_path, submission_ids))
    affected_subject_ids.update(_list_subject_ids_for_report_refs(db_path, report_slugs))
    ordered_subject_ids = sorted(affected_subject_ids)
    snapshot_ids = list_snapshot_ids_for_subjects(db_path, ordered_subject_ids)

    if snapshot_ids:
        endurance_summary = backfill_endurance_core_feature_sets(db_path, snapshot_ids=snapshot_ids)
        longitudinal_summary = backfill_longitudinal_delta_feature_sets(
            db_path,
            snapshot_ids=snapshot_ids,
        )
    else:
        empty_summary = {
            "dry_run": False,
            "snapshots_scanned": 0,
            "feature_rows_built": 0,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "would_insert": 0,
            "would_update": 0,
            "errors": [],
        }
        endurance_summary = dict(empty_summary)
        longitudinal_summary = dict(empty_summary)

    return {
        "subject_ids": ordered_subject_ids,
        "snapshot_ids": snapshot_ids,
        "deleted": deleted,
        "snapshots": snapshot_summary,
        "endurance_core": endurance_summary,
        "longitudinal_delta": longitudinal_summary,
    }


def list_report_catalog(db_path: Path) -> list[dict]:
    """List cached published report metadata rows, newest first."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT report_slug,
                  subject_name,
                  test_date,
                  analysis_method,
                  report_version,
                  report_url,
                  completed_at,
                  file_tags_json
           FROM report_catalog
           ORDER BY COALESCE(test_date, ''), COALESCE(completed_at, ''), report_slug DESC"""
    ).fetchall()
    conn.close()

    items: list[dict] = []
    for row in rows:
        item = dict(row)
        try:
            item["file_tags"] = json.loads(item.pop("file_tags_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            item["file_tags"] = []
        completed_at = str(item.get("completed_at") or "")
        item["id"] = str(item["report_slug"])
        item["display_id"] = hashlib.md5(str(item["report_slug"]).encode("utf-8")).hexdigest()[:8]
        item["submission_id"] = ""
        item["status"] = "done"
        item["error_message"] = None
        item["started_at"] = None
        item["created_at"] = completed_at
        item["created_at_display"] = completed_at[:16].replace("T", " ") if completed_at else ""
        item["is_latest"] = False
        items.append(item)
    return list(reversed(items))


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


def update_submission_subject(
    db_path: Path, submission_id: str, subject_id: str,
) -> dict | None:
    """Set a submission's subject FK and sync the denormalized subject_name.

    Looks up the canonical name from the subjects table and writes both
    submissions.subject_id and submissions.subject_name in a single transaction.
    Returns the updated submission dict, or None when either the subject_id
    does not resolve or the submission row does not exist.
    """
    subject_id_clean = (subject_id or "").strip()
    if not subject_id_clean:
        return None
    conn = _connect(db_path)
    subject_row = conn.execute(
        "SELECT id, name FROM subjects WHERE id = ?", (subject_id_clean,)
    ).fetchone()
    if subject_row is None:
        conn.close()
        return None
    canonical_name = str(subject_row["name"] or "").strip()
    conn.execute(
        "UPDATE submissions SET subject_id = ?, subject_name = ? WHERE id = ?",
        (subject_id_clean, canonical_name, submission_id),
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


def update_submission_test_date(
    db_path: Path, submission_id: str, test_date: str,
) -> dict | None:
    """Update a submission's test_date. Returns updated submission, or None."""
    conn = _connect(db_path)
    conn.execute(
        "UPDATE submissions SET test_date = ? WHERE id = ?",
        (test_date.strip(), submission_id),
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


def update_report_catalog_test_date(
    db_path: Path, report_slug: str, test_date: str,
) -> None:
    """Update a published report catalog row's test_date if it exists."""
    conn = _connect(db_path)
    conn.execute(
        "UPDATE report_catalog SET test_date = ?, updated_at = datetime('now') WHERE report_slug = ?",
        (test_date.strip(), report_slug),
    )
    conn.commit()
    conn.close()


def update_report_catalog_analysis_method(
    db_path: Path, report_slug: str, analysis_method: str,
) -> None:
    """Update a published report catalog row's analysis_method if it exists.

    Empty/whitespace-only values are normalized to '알 수 없음' to match the
    INSERT default in `upsert_report_catalog_entry`.
    """
    conn = _connect(db_path)
    conn.execute(
        "UPDATE report_catalog SET analysis_method = ?, updated_at = datetime('now') WHERE report_slug = ?",
        (analysis_method.strip() or "알 수 없음", report_slug),
    )
    conn.commit()
    conn.close()


def get_recent_published_slug(db_path: Path) -> str | None:
    """Return the report_slug of the most recently published report, or None."""
    conn = _connect(db_path)
    row = conn.execute(
        """SELECT report_slug FROM report_catalog
           ORDER BY COALESCE(completed_at, updated_at, '') DESC
           LIMIT 1"""
    ).fetchone()
    conn.close()
    return row["report_slug"] if row else None


def get_report_catalog_entry(db_path: Path, report_slug: str) -> dict | None:
    """Fetch a single report_catalog row by slug. Returns None if missing."""
    conn = _connect(db_path)
    row = conn.execute(
        """SELECT report_slug, subject_name, test_date, analysis_method,
                  report_version, report_url, completed_at, updated_at
           FROM report_catalog
           WHERE report_slug = ?""",
        (report_slug,),
    ).fetchone()
    conn.close()
    return dict(row) if row is not None else None


def link_submission_user(
    db_path: Path, submission_id: str, user_id: str,
) -> dict | None:
    """Link a submission to a user. Returns the updated submission, or None."""
    conn = _connect(db_path)
    user_row = conn.execute(
        """SELECT u.subject_id, s.name AS subject_name
           FROM users u
           LEFT JOIN subjects s ON s.id = u.subject_id
           WHERE u.id = ?""",
        (user_id,),
    ).fetchone()
    if user_row and user_row["subject_id"]:
        conn.execute(
            """UPDATE submissions
               SET user_id = ?,
                   subject_id = ?,
                   subject_name = CASE
                       WHEN COALESCE(subject_name, '') = '' THEN ?
                       ELSE subject_name
                   END
               WHERE id = ?""",
            (user_id, user_row["subject_id"], user_row["subject_name"], submission_id),
        )
    else:
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


def unlink_submission_subject(db_path: Path, submission_id: str) -> dict | None:
    """Remove subject link from a submission. Returns the updated submission, or None."""
    conn = _connect(db_path)
    conn.execute(
        "UPDATE submissions SET subject_id = NULL WHERE id = ?",
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


def list_submissions_by_ids(
    db_path: Path, submission_ids: list[str],
) -> dict[str, dict]:
    """Fetch many submissions in one query and return them keyed by id."""
    if not submission_ids:
        return {}

    conn = _connect(db_path)
    placeholders = ", ".join("?" for _ in submission_ids)
    rows = conn.execute(
        f"SELECT * FROM submissions WHERE id IN ({placeholders})",
        submission_ids,
    ).fetchall()
    conn.close()

    result: dict[str, dict] = {}
    for row in rows:
        item = dict(row)
        if item.get("file_manifest"):
            item["file_manifest"] = json.loads(item["file_manifest"])
        result[str(item["id"])] = item
    return result


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
_PUBLISHED_CPET_SNAPSHOT_EXTRACTION_VERSION = "published_cpet_snapshot_v1"
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
_SNAPSHOT_COMPARE_METRICS: list[tuple[str, str, str]] = [
    ("vo2max_ml", "VO2max", "mL/min"),
    ("vo2max_rel", "VO2max", "mL/kg/min"),
    ("lt1_power_w", "LT1", "W"),
    ("lt2_power_w", "LT2", "W"),
    ("fatmax_power_w", "FatMax", "W"),
    ("fatmax_gmin", "FatMax Ox", "g/min"),
    ("vlamax", "VLamax", "mmol/L/s"),
    ("at_power_w", "AT", "W"),
    ("carbmax_w", "CarbMax", "W"),
    ("glycogen_g", "Glycogen", "g"),
]
_ENDURANCE_CORE_FEATURE_SPEC_KEY = "endurance_core"
_ENDURANCE_CORE_FEATURE_SPEC_VERSION = "v1"
_ENDURANCE_CORE_FEATURE_KEYS = (
    "vo2max_rel",
    "lt1_power_w",
    "lt2_power_w",
    "fatmax_power_w",
    "vlamax",
    "at_power_w",
)
_LONGITUDINAL_DELTA_FEATURE_SPEC_KEY = "longitudinal_delta"
_LONGITUDINAL_DELTA_FEATURE_SPEC_VERSION = "v1"
_LONGITUDINAL_DELTA_DELTA_KEYS = (
    "vo2max_rel",
    "lt1_power_w",
    "fatmax_power_w",
    "vlamax",
)
_LONGITUDINAL_DELTA_PCT_KEYS = (
    "vo2max_rel",
    "lt1_power_w",
)


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
    if path.is_absolute():
        return path
    if path.exists():
        return path
    if data_dir is None:
        return path
    candidate = data_dir / path
    if candidate.exists():
        return candidate
    if path.parts and path.parts[0] == data_dir.name:
        stripped = Path(*path.parts[1:])
        candidate = data_dir / stripped
    return candidate


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


def _read_embedded_report_data(report_html_path: Path) -> dict:
    """Read embedded report-data JSON from a rendered report HTML."""
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


def _read_inscyd_report_data(report_html_path: Path) -> dict:
    """Read embedded report-data JSON from a rendered INSCYD report."""
    return _read_embedded_report_data(report_html_path)


def _build_inscyd_report_data_from_workspace(workspace: Path) -> dict:
    """Build report-data-like payload directly from a raw INSCYD workspace."""
    try:
        from pipeline.inscyd_workspace import parse_inscyd_workspace
    except Exception:
        return {}

    try:
        parsed = parse_inscyd_workspace(workspace)
    except Exception:
        return {}

    report = parsed.report
    return {
        "meta": {
            "report_type": "inscyd",
            "analysis_method": "INSCYD raw workspace snapshot",
        },
        "subject": {
            "name": parsed.subject_name,
            "body_mass_kg": report.body_mass_kg,
            "body_height_cm": report.body_height_cm,
        },
        "session": {
            "test_date": parsed.test_date,
            "sport": report.sport,
            "test_type": report.test_type,
        },
        "inscyd": {
            "vo2max_abs_ml_min": report.vo2max_abs_ml_min,
            "vo2max_rel_ml_kg_min": report.vo2max_rel_ml_kg_min,
            "fatmax_watt": report.fatmax_watt,
            "vlamax_mmol_l_s": report.vlamax_mmol_l_s,
            "at_abs_watt": report.at_abs_watt,
            "carbmax_abs_watt": report.carbmax_abs_watt,
            "glycogen_abs_g": report.glycogen_abs_g,
            "training_zones": report.training_zones,
            "test_data_rows": report.test_data_rows,
            "weighted_regression": report.weighted_regression,
        },
        "protocol": {
            "fit_sessions": parsed.fit_sessions,
            "zwo_summary": parsed.zwo_summary,
        },
        "warnings": parsed.warnings,
        "artifacts": {
            "original_pdf_name": parsed.pdf_path.name,
            "original_pdf_file": parsed.pdf_path.name,
        },
    }


def _build_inscyd_snapshot(
    submission: dict,
    submission_id: str,
    report_data: dict,
    source_artifact: dict,
) -> dict | None:
    """Build a normalized INSCYD snapshot from report-data-like payload."""
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
    raw_vo2_abs = inscyd.get("vo2max_abs_ml_min")
    if isinstance(raw_vo2_abs, (int, float)):
        present_metrics["vo2max_ml"] = raw_vo2_abs
    for src_key, dest_key in _INSCYD_SNAPSHOT_METRIC_MAP.items():
        value = inscyd.get(src_key)
        if isinstance(value, (int, float)):
            present_metrics[dest_key] = value

    missing_metrics = sorted(
        key for key in _INSCYD_SNAPSHOT_METRIC_KEYS if key not in present_metrics
    )
    quality_flags.extend(f"missing_{key}" for key in missing_metrics)
    quality_flags.sort()

    payload = {
        "source": {
            "submission_id": submission_id,
            **source_artifact,
        },
        "meta": report_data.get("meta", {}),
        "subject": report_data.get("subject", {}),
        "session": session,
        "inscyd": inscyd,
        "protocol": report_data.get("protocol", {}),
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


def extract_inscyd_snapshot(
    db_path: Path,
    submission_id: str,
    data_dir: Path | None = None,
) -> dict | None:
    """Build an INSCYD snapshot row dict from rendered or raw report artifacts."""
    submission = get_submission(db_path, submission_id)
    if submission is None or not submission.get("subject_id"):
        return None

    workspace = _resolve_workspace_path(submission.get("workspace_path"), data_dir=data_dir)
    if workspace is None:
        return None

    report_html = _find_inscyd_report_html(workspace)
    if report_html is not None:
        report_data = _read_inscyd_report_data(report_html)
        if report_data:
            return _build_inscyd_snapshot(
                submission,
                submission_id,
                report_data,
                source_artifact={
                    "workspace_path": submission.get("workspace_path", ""),
                    "report_html": report_html.relative_to(workspace).as_posix(),
                },
            )

    report_data = _build_inscyd_report_data_from_workspace(workspace)
    if not report_data:
        return None

    return _build_inscyd_snapshot(
        submission,
        submission_id,
        report_data,
        source_artifact={
            "workspace_path": submission.get("workspace_path", ""),
            "workspace_mode": "raw_inscyd_workspace",
        },
    )


def _build_cpet_snapshot_from_report_data(
    subject_id: str,
    report_slug: str,
    report_data: dict,
) -> dict | None:
    """Build a CPET snapshot from embedded report-data in a published report."""
    session = report_data.get("session") if isinstance(report_data.get("session"), dict) else {}
    analysis = report_data.get("analysis") if isinstance(report_data.get("analysis"), dict) else {}
    vo2max = analysis.get("vo2max") if isinstance(analysis.get("vo2max"), dict) else {}
    lactate = analysis.get("lactate") if isinstance(analysis.get("lactate"), dict) else {}
    substrate = analysis.get("substrate") if isinstance(analysis.get("substrate"), dict) else {}
    ventilatory = (
        analysis.get("ventilatory_thresholds")
        if isinstance(analysis.get("ventilatory_thresholds"), dict)
        else {}
    )

    measured_at = str(session.get("test_date") or "").strip()
    if not measured_at:
        return None

    protocol_type = str(session.get("protocol_name") or "").strip()
    quality_flags: list[str] = []
    if not protocol_type:
        quality_flags.append("missing_protocol_type")

    present_metrics: dict[str, float | int] = {}
    metric_values = {
        "vo2max_ml": vo2max.get("vo2max_ml"),
        "vo2max_rel": vo2max.get("vo2max_rel"),
        "lt1_power_w": lactate.get("lt1_fixed_power_w") or ventilatory.get("vt1_power_w"),
        "lt2_power_w": lactate.get("lt1_dmax_power_w") or ventilatory.get("vt2_power_w"),
        "fatmax_power_w": substrate.get("fatmax_power_w"),
        "fatmax_gmin": substrate.get("fatmax_gmin"),
    }
    for key, value in metric_values.items():
        if isinstance(value, (int, float)):
            present_metrics[key] = value

    missing_metrics = sorted(
        key for key in _CPET_SNAPSHOT_METRIC_KEYS if key not in present_metrics
    )
    quality_flags.extend(f"missing_{key}" for key in missing_metrics)
    quality_flags.sort()

    payload = {
        "source": {
            "report_slug": report_slug,
            "published_mode": "standalone_report",
        },
        "subject": report_data.get("subject", {}),
        "session": session,
        "analysis": {
            "vo2max": vo2max,
            "lactate": lactate,
            "substrate": substrate,
            "ventilatory_thresholds": ventilatory,
        },
        "missing_metrics": missing_metrics,
    }

    snapshot = {
        "snapshot_id": str(uuid.uuid4()),
        "subject_id": subject_id,
        "source_kind": "published_cpet_report",
        "source_ref_id": report_slug,
        "submission_id": None,
        "measured_at": measured_at,
        "protocol_type": protocol_type or None,
        "extraction_version": _PUBLISHED_CPET_SNAPSHOT_EXTRACTION_VERSION,
        "quality_flags_json": json.dumps(quality_flags),
        "payload_json": json.dumps(payload, ensure_ascii=True, sort_keys=True),
    }
    snapshot.update(present_metrics)
    return snapshot


def _list_linked_published_report_candidates(
    db_path: Path,
    published_dir: Path,
) -> list[dict]:
    """List standalone published reports linked to users with a subject_id."""
    if not published_dir.exists():
        return []

    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT rul.report_slug,
                  rul.user_id,
                  u.subject_id
           FROM report_user_links rul
           JOIN users u ON u.id = rul.user_id
           LEFT JOIN jobs j ON j.report_slug = rul.report_slug
           WHERE u.subject_id IS NOT NULL
             AND j.report_slug IS NULL
           ORDER BY rul.linked_at ASC, rul.report_slug ASC"""
    ).fetchall()
    conn.close()

    candidates = []
    for row in rows:
        report_slug = str(row["report_slug"])
        index_file = published_dir / report_slug / "index.html"
        if not index_file.is_file():
            continue
        candidates.append({
            "report_slug": report_slug,
            "user_id": str(row["user_id"]),
            "subject_id": str(row["subject_id"]),
            "index_file": index_file,
        })
    return candidates


def extract_published_report_snapshot(
    db_path: Path,
    report_slug: str,
    published_dir: Path,
) -> dict | None:
    """Build a standalone published report snapshot when linked to a subject."""
    candidate = next(
        (
            item
            for item in _list_linked_published_report_candidates(db_path, published_dir)
            if item["report_slug"] == report_slug
        ),
        None,
    )
    if candidate is None:
        return None

    report_data = _read_embedded_report_data(candidate["index_file"])
    if not report_data:
        return None

    meta = report_data.get("meta") if isinstance(report_data.get("meta"), dict) else {}
    report_type = str(meta.get("report_type") or "").strip().lower()
    if report_type == "inscyd":
        return None

    return _build_cpet_snapshot_from_report_data(
        candidate["subject_id"],
        report_slug,
        report_data,
    )


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
    report_slugs: list[str] | None = None,
    data_dir: Path | None = None,
    published_dir: Path | None = None,
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
    if published_dir is not None:
        summary["published_reports_scanned"] = 0

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

    if published_dir is not None:
        published_candidates = _list_linked_published_report_candidates(db_path, published_dir)
        if report_slugs:
            allowed_slugs = {str(item) for item in report_slugs if item}
            published_candidates = [
                item for item in published_candidates if str(item["report_slug"]) in allowed_slugs
            ]
        summary["published_reports_scanned"] = len(published_candidates)
        for candidate in published_candidates:
            try:
                snapshot = extract_published_report_snapshot(
                    db_path,
                    candidate["report_slug"],
                    published_dir=published_dir,
                )
            except Exception as exc:  # pragma: no cover - defensive runner guard
                summary["errors"].append(
                    {
                        "report_slug": candidate["report_slug"],
                        "extractor": "extract_published_report_snapshot",
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


def _deserialize_snapshot_row(
    item: dict,
    include_payload: bool = False,
) -> dict:
    """Parse JSON columns on a snapshot row dict."""
    try:
        item["quality_flags"] = json.loads(item.get("quality_flags_json") or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        item["quality_flags"] = []
    item["quality_flag_count"] = len(item["quality_flags"])

    if include_payload:
        try:
            item["payload"] = json.loads(item.get("payload_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            item["payload"] = {}
    return item


def list_subject_metric_snapshots(
    db_path: Path,
    subject_id: str | None = None,
    source_kind: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 200,
    include_payload: bool = False,
) -> list[dict]:
    """List snapshot rows with optional filters for explorer UIs."""
    conn = _connect(db_path)
    conditions = []
    params: list[str | int] = []

    if subject_id:
        conditions.append("sms.subject_id = ?")
        params.append(subject_id)
    if source_kind:
        conditions.append("sms.source_kind = ?")
        params.append(source_kind)
    if date_from:
        conditions.append("sms.measured_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("sms.measured_at <= ?")
        params.append(date_to)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    rows = conn.execute(
        f"""SELECT sms.*,
                   subj.name AS subject_name,
                   sub.description AS submission_description,
                   sub.test_date AS submission_test_date
            FROM subject_metric_snapshots sms
            LEFT JOIN subjects subj ON sms.subject_id = subj.id
            LEFT JOIN submissions sub ON sms.submission_id = sub.id
            {where_clause}
            ORDER BY sms.measured_at DESC, sms.created_at DESC
            LIMIT ?""",
        params,
    ).fetchall()
    conn.close()

    results: list[dict] = []
    for row in rows:
        item = dict(row)
        results.append(_deserialize_snapshot_row(item, include_payload=include_payload))
    return results


def get_subject_metric_snapshot(db_path: Path, snapshot_id: str) -> dict | None:
    """Fetch a single snapshot row with parsed payload fields for detail views."""
    conn = _connect(db_path)
    row = conn.execute(
        """SELECT sms.*,
                  subj.name AS subject_name,
                  sub.description AS submission_description,
                  sub.test_date AS submission_test_date
           FROM subject_metric_snapshots sms
           LEFT JOIN subjects subj ON sms.subject_id = subj.id
           LEFT JOIN submissions sub ON sms.submission_id = sub.id
           WHERE sms.snapshot_id = ?""",
        (snapshot_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None

    item = dict(row)
    return _deserialize_snapshot_row(item, include_payload=True)


def _deserialize_feature_set_row(row: dict, include_payload: bool = False) -> dict:
    """Normalize JSON columns on subject_feature_sets rows for UI/query helpers."""
    quality_flags = row.get("quality_flags_json") or "[]"
    input_snapshot_ids = row.get("input_snapshot_ids_json") or "[]"
    input_source_kinds = row.get("input_source_kinds_json") or "[]"

    try:
        row["quality_flags"] = json.loads(quality_flags)
    except json.JSONDecodeError:
        row["quality_flags"] = []

    try:
        row["input_snapshot_ids"] = json.loads(input_snapshot_ids)
    except json.JSONDecodeError:
        row["input_snapshot_ids"] = []

    try:
        row["input_source_kinds"] = json.loads(input_source_kinds)
    except json.JSONDecodeError:
        row["input_source_kinds"] = []

    if include_payload:
        try:
            row["feature_payload"] = json.loads(row.get("feature_payload_json") or "{}")
        except json.JSONDecodeError:
            row["feature_payload"] = {}

    return row


def list_subject_feature_sets(
    db_path: Path,
    subject_id: str | None = None,
    feature_spec_key: str | None = None,
    window_label: str | None = None,
    anchor_source_kind: str | None = None,
    limit: int = 200,
    include_payload: bool = False,
) -> list[dict]:
    """List subject_feature_sets rows with stable filters for future explorer UIs."""
    conn = _connect(db_path)
    conditions = []
    params: list[str | int] = []

    if subject_id:
        conditions.append("sfs.subject_id = ?")
        params.append(subject_id)
    if feature_spec_key:
        conditions.append("sfs.feature_spec_key = ?")
        params.append(feature_spec_key)
    if window_label:
        conditions.append("sfs.window_label = ?")
        params.append(window_label)
    if anchor_source_kind:
        conditions.append("sms.source_kind = ?")
        params.append(anchor_source_kind)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    rows = conn.execute(
        f"""SELECT sfs.*,
                   subj.name AS subject_name,
                   sms.source_kind AS anchor_source_kind,
                   sms.extraction_version AS anchor_extraction_version
            FROM subject_feature_sets sfs
            LEFT JOIN subjects subj ON sfs.subject_id = subj.id
            LEFT JOIN subject_metric_snapshots sms ON sfs.anchor_snapshot_id = sms.snapshot_id
            {where_clause}
            ORDER BY sfs.anchor_measured_at DESC, sfs.created_at DESC
            LIMIT ?""",
        params,
    ).fetchall()
    conn.close()

    results: list[dict] = []
    for row in rows:
        results.append(_deserialize_feature_set_row(dict(row), include_payload=include_payload))
    return results


def summarize_subject_feature_sets(
    db_path: Path,
    subject_id: str | None = None,
    feature_spec_key: str | None = None,
    window_label: str | None = None,
    anchor_source_kind: str | None = None,
) -> dict:
    """Return filtered summary counts for subject_feature_sets explorer UIs."""
    conn = _connect(db_path)
    conditions = []
    params: list[str] = []

    if subject_id:
        conditions.append("sfs.subject_id = ?")
        params.append(subject_id)
    if feature_spec_key:
        conditions.append("sfs.feature_spec_key = ?")
        params.append(feature_spec_key)
    if window_label:
        conditions.append("sfs.window_label = ?")
        params.append(window_label)
    if anchor_source_kind:
        conditions.append("sms.source_kind = ?")
        params.append(anchor_source_kind)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = conn.execute(
        f"""SELECT sfs.feature_spec_key,
                   sfs.window_label,
                   sms.source_kind AS anchor_source_kind
            FROM subject_feature_sets sfs
            LEFT JOIN subject_metric_snapshots sms ON sfs.anchor_snapshot_id = sms.snapshot_id
            {where_clause}""",
        params,
    ).fetchall()
    conn.close()

    by_spec: dict[str, int] = {}
    by_window: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for row in rows:
        spec = str(row["feature_spec_key"] or "unknown")
        window = str(row["window_label"] or "unknown")
        source = str(row["anchor_source_kind"] or "unknown")
        by_spec[spec] = by_spec.get(spec, 0) + 1
        by_window[window] = by_window.get(window, 0) + 1
        by_source[source] = by_source.get(source, 0) + 1

    return {
        "total": len(rows),
        "by_spec": by_spec,
        "by_window": by_window,
        "by_source": by_source,
    }


def get_subject_feature_set(db_path: Path, feature_row_id: str) -> dict | None:
    """Fetch a single subject_feature_sets row for detail views."""
    conn = _connect(db_path)
    row = conn.execute(
        """SELECT sfs.*,
                  subj.name AS subject_name,
                  sms.source_kind AS anchor_source_kind,
                  sms.extraction_version AS anchor_extraction_version
           FROM subject_feature_sets sfs
           LEFT JOIN subjects subj ON sfs.subject_id = subj.id
           LEFT JOIN subject_metric_snapshots sms ON sfs.anchor_snapshot_id = sms.snapshot_id
           WHERE sfs.feature_row_id = ?""",
        (feature_row_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return _deserialize_feature_set_row(dict(row), include_payload=True)


def _feature_payload_inputs(row: dict) -> dict:
    """Return normalized feature payload inputs for dashboard helpers."""
    payload = row.get("feature_payload")
    if not isinstance(payload, dict):
        return {}
    inputs = payload.get("inputs")
    return inputs if isinstance(inputs, dict) else {}


def _feature_payload_features(row: dict) -> dict:
    """Return normalized feature payload features for dashboard helpers."""
    payload = row.get("feature_payload")
    if not isinstance(payload, dict):
        return {}
    features = payload.get("features")
    return features if isinstance(features, dict) else {}


def _count_quality_flags(rows: list[dict]) -> dict[str, int]:
    """Count normalized quality flags across feature-set rows."""
    counts: dict[str, int] = {}
    for row in rows:
        for flag in row.get("quality_flags", []):
            counts[flag] = counts.get(flag, 0) + 1
    return counts


def _build_metric_position(
    latest_rows: list[dict],
    subject_id: str,
    metric_key: str,
) -> dict | None:
    """Return rank/percentile info for one metric among latest subject rows."""
    values = []
    for row in latest_rows:
        features = _feature_payload_features(row)
        value = features.get(metric_key)
        if value is None:
            value = row.get(metric_key)
        if isinstance(value, (int, float)):
            values.append({
                "subject_id": row["subject_id"],
                "value": float(value),
            })

    if not values:
        return None

    values.sort(key=lambda item: item["value"], reverse=True)
    for index, item in enumerate(values, start=1):
        if item["subject_id"] != subject_id:
            continue
        total = len(values)
        percentile = 100.0 if total == 1 else round(((total - index) / (total - 1)) * 100, 1)
        return {
            "value": item["value"],
            "rank": index,
            "total": total,
            "percentile": percentile,
        }
    return None


def _build_delta_metric_position(
    delta_rows: list[dict],
    subject_id: str,
    metric_key: str,
) -> dict | None:
    """Return percentile info for one delta metric among usable latest delta rows."""
    values = []
    for row in delta_rows:
        quality_flags = row.get("quality_flags", [])
        if "missing_previous_snapshot" in quality_flags or "mixed_source_compare" in quality_flags:
            continue
        features = _feature_payload_features(row)
        value = features.get(metric_key)
        if isinstance(value, (int, float)):
            values.append({
                "subject_id": row["subject_id"],
                "value": float(value),
            })

    if not values:
        return None

    values.sort(key=lambda item: item["value"], reverse=True)
    for index, item in enumerate(values, start=1):
        if item["subject_id"] != subject_id:
            continue
        total = len(values)
        percentile = 100.0 if total == 1 else round(((total - index) / (total - 1)) * 100, 1)
        return {
            "value": item["value"],
            "rank": index,
            "total": total,
            "percentile": percentile,
        }
    return None


def _average_score(values: list[float]) -> float | None:
    """Return an average rounded to one decimal place when values exist."""
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _format_top_share_label(rank: int | None, total: int | None) -> str:
    """Describe relative placement without exposing raw rank numbers."""
    if not rank or not total or total <= 0:
        return "코호트 기준점"
    share = max(1, min(100, round((rank / total) * 100)))
    return f"상위 {share}%권"


def _build_dashboard_timeline_point(
    row: dict,
    delta_row: dict | None,
) -> dict:
    """Normalize one dashboard timeline point from feature-set rows."""
    features = _feature_payload_features(row)
    delta_features = _feature_payload_features(delta_row) if delta_row else {}
    delta_quality_flags = delta_row.get("quality_flags", []) if delta_row else []
    usable_delta_keys = sorted(
        key for key in delta_features if key.startswith("delta_") or key.startswith("pct_delta_")
    )
    has_usable_delta = bool(usable_delta_keys) and "mixed_source_compare" not in delta_quality_flags
    return {
        "feature_row_id": row["feature_row_id"],
        "anchor_snapshot_id": row.get("anchor_snapshot_id"),
        "anchor_measured_at": row["anchor_measured_at"],
        "vo2max_rel": features.get("vo2max_rel"),
        "fatmax_power_w": features.get("fatmax_power_w"),
        "lt1_power_w": features.get("lt1_power_w"),
        "quality_flags": row.get("quality_flags", []),
        "has_usable_delta": has_usable_delta,
        "delta_quality_flags": delta_quality_flags,
        "delta_metrics": (
            {key: delta_features[key] for key in usable_delta_keys}
            if has_usable_delta
            else {}
        ),
    }


def _build_positioning_widget(position: dict | None) -> dict | None:
    """Normalize a cohort position into a dashboard-friendly band."""
    if not position:
        return None

    percentile = float(position.get("percentile") or 0.0)
    if percentile >= 75.0:
        band_key = "front_pack"
        band_label = "상위권"
    elif percentile >= 40.0:
        band_key = "mid_pack"
        band_label = "중간권"
    else:
        band_key = "building"
        band_label = "형성 구간"

    return {
        "value": position.get("value"),
        "percentile": percentile,
        "band_key": band_key,
        "band_label": band_label,
        "relative_label": _format_top_share_label(position.get("rank"), position.get("total")),
        "comparison_copy": f"코호트 내 백분위 {round(percentile)}",
    }


def _build_latest_trend_summary(timeline: list[dict]) -> dict:
    """Summarize the most recent subject trend for dashboard drill-in widgets."""
    if not timeline:
        return {
            "state": "empty",
            "comparison_anchor_measured_at": "",
            "delta_metrics": {},
        }

    latest = timeline[-1]
    previous = timeline[-2] if len(timeline) >= 2 else None
    if latest.get("has_usable_delta"):
        return {
            "state": "delta_ready",
            "comparison_anchor_measured_at": previous["anchor_measured_at"] if previous else "",
            "delta_metrics": latest.get("delta_metrics", {}),
            "delta_quality_flags": latest.get("delta_quality_flags", []),
        }

    return {
        "state": "baseline_only",
        "comparison_anchor_measured_at": previous["anchor_measured_at"] if previous else "",
        "delta_metrics": {},
        "delta_quality_flags": latest.get("delta_quality_flags", []),
    }


def _get_dashboard_subject_display_names(
    db_path: Path,
    subject_ids: list[str],
) -> dict[str, str]:
    """Prefer the latest submission.subject_name over the master subject label."""
    if not subject_ids:
        return {}

    conn = _connect(db_path)
    placeholders = ", ".join("?" for _ in subject_ids)

    # Primary: latest submission name linked to this subject
    rows = conn.execute(
        f"""SELECT subject_id, subject_name
            FROM submissions
            WHERE subject_id IN ({placeholders})
              AND subject_name IS NOT NULL
              AND trim(subject_name) != ''
            ORDER BY created_at DESC, rowid DESC""",
        subject_ids,
    ).fetchall()

    display_names: dict[str, str] = {}
    for row in rows:
        subject_id = str(row["subject_id"])
        if subject_id not in display_names:
            display_names[subject_id] = str(row["subject_name"]).strip()

    # Fallback: subjects.name for IDs not covered by any submission
    missing = [sid for sid in subject_ids if sid not in display_names]
    if missing:
        fallback_placeholders = ", ".join("?" for _ in missing)
        fallback_rows = conn.execute(
            f"""SELECT id, name FROM subjects
                WHERE id IN ({fallback_placeholders})
                  AND name IS NOT NULL AND trim(name) != ''""",
            missing,
        ).fetchall()
        for row in fallback_rows:
            display_names[str(row["id"])] = str(row["name"]).strip()

    conn.close()
    return display_names


def _filter_dashboard_rows_by_subject_ids(
    rows: list[dict],
    subject_ids: list[str] | None = None,
) -> list[dict]:
    """Restrict dashboard analytics rows to a subject scope when provided."""
    if not subject_ids:
        return rows
    allowed = set(subject_ids)
    return [row for row in rows if row.get("subject_id") in allowed]


def _classify_capacity_band(score: float | None) -> str:
    """Convert a capacity score to a narrative label."""
    if score is None:
        return "기준점 부족"
    if score >= 70.0:
        return "높은 지구력 기반"
    if score >= 45.0:
        return "중간 지구력 기반"
    return "기반 형성 구간"


def _classify_momentum_band(score: float | None, *, history_ready: bool) -> str:
    """Convert a momentum score to a narrative label."""
    if not history_ready or score is None:
        return "변화 이력 보강 필요"
    if score >= 70.0:
        return "상승 신호"
    if score >= 45.0:
        return "안정 신호"
    return "관찰 구간"


def _classify_base_band(score: float | None) -> str:
    """Convert a current-state base score to a narrative label."""
    if score is None:
        return "기준점 부족"
    if score >= 70.0:
        return "강한 지구력 기반"
    if score >= 45.0:
        return "중간 지구력 기반"
    return "기반 형성 구간"


def _build_cohort_map_point(
    latest_rows: list[dict],
    latest_delta_rows: list[dict],
    latest_row: dict,
    latest_delta_row: dict | None,
) -> dict:
    """Build one anonymous cohort-map point from current feature rows."""
    subject_id = latest_row["subject_id"]
    capacity_positions = [
        _build_metric_position(latest_rows, subject_id, "vo2max_rel"),
        _build_metric_position(latest_rows, subject_id, "lt1_power_w"),
        _build_metric_position(latest_rows, subject_id, "fatmax_power_w"),
    ]
    capacity_score = _average_score(
        [
            float(position["percentile"])
            for position in capacity_positions
            if position is not None
        ]
    )

    momentum_positions = [
        _build_delta_metric_position(latest_delta_rows, subject_id, "pct_delta_vo2max_rel"),
        _build_delta_metric_position(latest_delta_rows, subject_id, "delta_fatmax_power_w"),
        _build_delta_metric_position(latest_delta_rows, subject_id, "delta_lt1_power_w"),
    ]
    momentum_score = _average_score(
        [
            float(position["percentile"])
            for position in momentum_positions
            if position is not None
        ]
    )
    history_ready = latest_delta_row is not None and momentum_score is not None

    x = capacity_score if capacity_score is not None else 50.0
    y = momentum_score if momentum_score is not None else 18.0

    if not history_ready:
        area_key = "history_needed"
        area_label = "이력 보강 필요"
    elif x >= 66.0 and y >= 60.0:
        area_key = "rising_endurance"
        area_label = "상승 지구력 구간"
    elif x >= 66.0:
        area_key = "established_base"
        area_label = "안정 기반 구간"
    elif y >= 60.0:
        area_key = "building_momentum"
        area_label = "상승 전환 구간"
    else:
        area_key = "base_building"
        area_label = "기반 형성 구간"

    return {
        "subject_id": subject_id,
        "x": round(x, 1),
        "y": round(y, 1),
        "capacity_score": capacity_score,
        "momentum_score": momentum_score,
        "history_ready": history_ready,
        "capacity_label": _classify_capacity_band(capacity_score),
        "momentum_label": _classify_momentum_band(momentum_score, history_ready=history_ready),
        "area_key": area_key,
        "area_label": area_label,
    }


def _build_cohort_map(
    latest_rows: list[dict],
    latest_delta_by_subject: dict[str, dict],
    selected_subject_id: str | None = None,
) -> dict:
    """Build anonymized cohort-map coordinates and summary counts."""
    latest_delta_rows = list(latest_delta_by_subject.values())
    points = []
    area_counts: dict[str, int] = {}
    highlighted = None

    for latest_row in latest_rows:
        subject_id = latest_row["subject_id"]
        point = _build_cohort_map_point(
            latest_rows,
            latest_delta_rows,
            latest_row,
            latest_delta_by_subject.get(subject_id),
        )
        point["is_selected"] = subject_id == selected_subject_id
        points.append(point)
        area_counts[point["area_key"]] = area_counts.get(point["area_key"], 0) + 1
        if point["is_selected"]:
            highlighted = point

    total = len(points)
    area_order = [
        ("rising_endurance", "상승 지구력 구간"),
        ("established_base", "안정 기반 구간"),
        ("building_momentum", "상승 전환 구간"),
        ("base_building", "기반 형성 구간"),
        ("history_needed", "이력 보강 필요"),
    ]
    area_cards = []
    for key, label in area_order:
        count = area_counts.get(key, 0)
        area_cards.append({
            "key": key,
            "label": label,
            "count": count,
            "share_pct": round((count / total) * 100, 1) if total else 0.0,
        })

    return {
        "axes": {
            "x_label": "현재 유산소 능력",
            "y_label": "최근 변화량",
        },
        "points": points,
        "highlighted": highlighted,
        "summary": {
            "total_subjects": total,
            "history_ready_count": len([point for point in points if point["history_ready"]]),
            "history_needed_count": len([point for point in points if not point["history_ready"]]),
            "area_cards": area_cards,
        },
    }


def _build_current_state_map_point(
    latest_rows: list[dict],
    latest_row: dict,
) -> dict:
    """Build a current-state-only cohort map point for single-anchor subjects."""
    subject_id = latest_row["subject_id"]
    aerobic_positions = [
        _build_metric_position(latest_rows, subject_id, "vo2max_rel"),
        _build_metric_position(latest_rows, subject_id, "lt1_power_w"),
    ]
    base_positions = [
        _build_metric_position(latest_rows, subject_id, "fatmax_power_w"),
        _build_metric_position(latest_rows, subject_id, "lt1_power_w"),
    ]
    aerobic_score = _average_score(
        [
            float(position["percentile"])
            for position in aerobic_positions
            if position is not None
        ]
    )
    base_score = _average_score(
        [
            float(position["percentile"])
            for position in base_positions
            if position is not None
        ]
    )

    x = aerobic_score if aerobic_score is not None else 50.0
    y = base_score if base_score is not None else 50.0

    if x >= 66.0 and y >= 66.0:
        area_key = "balanced_high"
        area_label = "균형 상위 구간"
    elif x >= 66.0:
        area_key = "aerobic_leading"
        area_label = "유산소 우위 구간"
    elif y >= 66.0:
        area_key = "base_leading"
        area_label = "지구력 기반 우위 구간"
    else:
        area_key = "foundation_building"
        area_label = "기반 형성 구간"

    return {
        "subject_id": subject_id,
        "x": round(x, 1),
        "y": round(y, 1),
        "aerobic_score": aerobic_score,
        "base_score": base_score,
        "aerobic_label": _classify_capacity_band(aerobic_score),
        "base_label": _classify_base_band(base_score),
        "area_key": area_key,
        "area_label": area_label,
    }


def _build_current_state_map(
    latest_rows: list[dict],
    selected_subject_id: str | None = None,
) -> dict:
    """Build a current-state positioning map without change semantics."""
    points: list[dict] = []
    highlighted = None

    for latest_row in latest_rows:
        point = _build_current_state_map_point(latest_rows, latest_row)
        point["is_selected"] = point["subject_id"] == selected_subject_id
        points.append(point)
        if point["is_selected"]:
            highlighted = point

    return {
        "axes": {
            "x_label": "유산소 능력",
            "y_label": "지구력 기반",
        },
        "points": points,
        "highlighted": highlighted,
    }


def _build_latest_snapshot_metric_profiles(
    snapshot_rows: list[dict],
    metric_keys: tuple[str, ...],
) -> list[dict]:
    """Collapse mixed-source snapshot history into one latest-available metric profile per subject."""
    profiles: dict[str, dict] = {}
    for row in snapshot_rows:
        subject_id = str(row.get("subject_id") or "").strip()
        if not subject_id:
            continue
        profile = profiles.setdefault(
            subject_id,
            {
                "subject_id": subject_id,
                "latest_measured_at": row.get("measured_at", ""),
                "source_kinds": set(),
            },
        )
        latest_measured_at = str(row.get("measured_at") or "").strip()
        if latest_measured_at and latest_measured_at > str(profile.get("latest_measured_at") or ""):
            profile["latest_measured_at"] = latest_measured_at
        if row.get("source_kind"):
            profile["source_kinds"].add(str(row["source_kind"]))
        for key in metric_keys:
            if profile.get(key) is None and row.get(key) is not None:
                profile[key] = row.get(key)

    normalized: list[dict] = []
    for profile in profiles.values():
        profile["source_kinds"] = sorted(profile["source_kinds"])
        normalized.append(profile)
    return normalized


def _classify_fat_strategy_band(score: float | None) -> str:
    """Translate fat-side percentile into a fuel-strategy label."""
    if score is None:
        return "지방 활용 정보 부족"
    if score >= 66.0:
        return "지방 활용 상위권"
    if score >= 33.0:
        return "지방 활용 중간권"
    return "지방 활용 보강 구간"


def _classify_carb_strategy_band(score: float | None, inscyd_enriched: bool) -> str:
    """Translate carb-side percentile into a fuel-strategy label."""
    prefix = "INSCYD 보강" if inscyd_enriched else "CPET fallback"
    if score is None:
        return f"{prefix} 탄수 활용 정보 부족"
    if score >= 66.0:
        return f"{prefix} 탄수 동원 상위권"
    if score >= 33.0:
        return f"{prefix} 탄수 동원 중간권"
    return f"{prefix} 탄수 동원 보강 구간"


def _build_fuel_strategy_profile_point(
    cohort_rows: list[dict],
    profile_row: dict,
) -> dict:
    """Build a fat-vs-carb cohort point using CPET-safe defaults and INSCYD enrichment."""
    subject_id = profile_row["subject_id"]
    fat_positions = [
        _build_metric_position(cohort_rows, subject_id, "fatmax_power_w"),
        _build_metric_position(cohort_rows, subject_id, "fatmax_gmin"),
    ]
    carb_positions = [
        _build_metric_position(cohort_rows, subject_id, "carbmax_w"),
        _build_metric_position(cohort_rows, subject_id, "vlamax"),
        _build_metric_position(cohort_rows, subject_id, "lt2_power_w"),
        _build_metric_position(cohort_rows, subject_id, "lt1_power_w"),
    ]

    fat_score = _average_score(
        [float(position["percentile"]) for position in fat_positions if position is not None]
    )
    carb_score = _average_score(
        [float(position["percentile"]) for position in carb_positions if position is not None]
    )
    if fat_score is None or carb_score is None:
        return {}

    x = fat_score
    y = carb_score
    inscyd_enriched = any(
        profile_row.get(key) is not None for key in ("carbmax_w", "vlamax")
    )

    if x >= 66.0 and y >= 66.0:
        area_key = "hybrid_high"
        area_label = "혼합 활용 상위"
    elif x >= 66.0:
        area_key = "fat_adapted"
        area_label = "지방 활용 우위"
    elif y >= 66.0:
        area_key = "carb_driven"
        area_label = "탄수 동원 우위"
    else:
        area_key = "mixed_building"
        area_label = "혼합 전략 형성"

    return {
        "subject_id": subject_id,
        "x": round(x, 1),
        "y": round(y, 1),
        "fat_score": fat_score,
        "carb_score": carb_score,
        "fat_label": _classify_fat_strategy_band(fat_score),
        "carb_label": _classify_carb_strategy_band(carb_score, inscyd_enriched=inscyd_enriched),
        "area_key": area_key,
        "area_label": area_label,
        "inscyd_enriched": inscyd_enriched,
        "latest_measured_at": profile_row.get("latest_measured_at", ""),
        "fatmax_power_w": profile_row.get("fatmax_power_w"),
        "fatmax_gmin": profile_row.get("fatmax_gmin"),
        "lt1_power_w": profile_row.get("lt1_power_w"),
        "lt2_power_w": profile_row.get("lt2_power_w"),
        "carbmax_w": profile_row.get("carbmax_w"),
        "vlamax": profile_row.get("vlamax"),
        "source_kinds": profile_row.get("source_kinds", []),
    }


def _build_fuel_strategy_map(
    snapshot_rows: list[dict],
    selected_subject_id: str | None = None,
) -> dict | None:
    """Build a cohort map for fat-vs-carb strategy using CPET and INSCYD metrics."""
    profiles = _build_latest_snapshot_metric_profiles(
        snapshot_rows,
        (
            "fatmax_power_w",
            "fatmax_gmin",
            "lt1_power_w",
            "lt2_power_w",
            "carbmax_w",
            "vlamax",
        ),
    )
    points: list[dict] = []
    highlighted = None
    for profile in profiles:
        point = _build_fuel_strategy_profile_point(profiles, profile)
        if not point:
            continue
        point["is_selected"] = point["subject_id"] == selected_subject_id
        points.append(point)
        if point["is_selected"]:
            highlighted = point

    if not points or highlighted is None:
        return None

    return {
        "axes": {
            "x_label": "지방 활용 기반",
            "y_label": "탄수 동원 성향",
        },
        "style": {
            "other_fill": "rgba(120, 128, 140, 0.32)",
            "other_radius": 4,
            "other_stroke": "transparent",
            "selected_fill": "#2b6f77",
            "selected_radius": 8,
            "selected_stroke": "#f4efe6",
        },
        "points": points,
        "highlighted": highlighted,
        "summary": {
            "total_subjects": len(points),
            "inscyd_enriched_count": len([point for point in points if point.get("inscyd_enriched")]),
        },
    }


def _build_threshold_ladder(
    snapshot_rows: list[dict],
    selected_subject_id: str,
) -> dict | None:
    """Build a subject-level threshold ladder on a single power axis."""
    profiles = _build_latest_snapshot_metric_profiles(
        snapshot_rows,
        (
            "fatmax_power_w",
            "lt1_power_w",
            "lt2_power_w",
            "at_power_w",
            "carbmax_w",
        ),
    )
    profile = next((row for row in profiles if row["subject_id"] == selected_subject_id), None)
    if profile is None:
        return None

    marker_defs = [
        ("fatmax_power_w", "FatMax", "cpet"),
        ("lt1_power_w", "LT1", "cpet"),
        ("lt2_power_w", "LT2", "cpet"),
        ("at_power_w", "AT", "inscyd"),
        ("carbmax_w", "CarbMax", "inscyd"),
    ]
    markers = []
    for key, label, source in marker_defs:
        value = profile.get(key)
        if not isinstance(value, (int, float)):
            continue
        markers.append({
            "key": key,
            "label": label,
            "value": float(value),
            "unit": "W",
            "source": source,
        })

    if len(markers) < 2:
        return None

    markers.sort(key=lambda item: item["value"])
    min_value = markers[0]["value"]
    max_value = markers[-1]["value"]
    spread = max(max_value - min_value, 1.0)
    for marker in markers:
        marker["position_pct"] = round(((marker["value"] - min_value) / spread) * 100.0, 1)

    return {
        "markers": markers,
        "min_power_w": round(min_value, 1),
        "max_power_w": round(max_value, 1),
        "inscyd_enriched": any(marker["source"] == "inscyd" for marker in markers),
        "latest_measured_at": profile.get("latest_measured_at", ""),
    }


def _build_fat_oxidation_efficiency_point(
    cohort_rows: list[dict],
    profile_row: dict,
) -> dict:
    """Build one fat oxidation efficiency point from fatmax power and g/min."""
    subject_id = profile_row["subject_id"]
    power_position = _build_metric_position(cohort_rows, subject_id, "fatmax_power_w")
    rate_position = _build_metric_position(cohort_rows, subject_id, "fatmax_gmin")
    if power_position is None or rate_position is None:
        return {}

    x = float(power_position["percentile"])
    y = float(rate_position["percentile"])
    if x >= 66.0 and y >= 66.0:
        area_key = "power_and_rate_high"
        area_label = "고파워·고효율 지방산화"
    elif x >= 66.0:
        area_key = "power_high"
        area_label = "고파워 지방 활용"
    elif y >= 66.0:
        area_key = "rate_high"
        area_label = "고효율 지방산화"
    else:
        area_key = "building"
        area_label = "지방산화 형성 구간"

    return {
        "subject_id": subject_id,
        "x": round(x, 1),
        "y": round(y, 1),
        "area_key": area_key,
        "area_label": area_label,
        "fatmax_power_w": profile_row.get("fatmax_power_w"),
        "fatmax_gmin": profile_row.get("fatmax_gmin"),
        "is_selected": False,
    }


def _build_fat_oxidation_efficiency_map(
    snapshot_rows: list[dict],
    selected_subject_id: str | None = None,
) -> dict | None:
    """Build cohort map for fat oxidation efficiency."""
    profiles = _build_latest_snapshot_metric_profiles(
        snapshot_rows,
        ("fatmax_power_w", "fatmax_gmin"),
    )
    points = []
    highlighted = None
    for profile in profiles:
        point = _build_fat_oxidation_efficiency_point(profiles, profile)
        if not point:
            continue
        point["is_selected"] = point["subject_id"] == selected_subject_id
        points.append(point)
        if point["is_selected"]:
            highlighted = point
    if not points or highlighted is None:
        return None
    return {
        "axes": {
            "x_label": "FatMax 파워",
            "y_label": "FatMax 산화율",
        },
        "style": {
            "other_fill": "rgba(120, 128, 140, 0.30)",
            "other_radius": 4,
            "other_stroke": "transparent",
            "selected_fill": "#a17b37",
            "selected_radius": 8,
            "selected_stroke": "#f4efe6",
        },
        "points": points,
        "highlighted": highlighted,
    }


def _build_aerobic_decoupling_point(
    cohort_rows: list[dict],
    profile_row: dict,
) -> dict:
    """Build one aerobic engine vs threshold posture point."""
    subject_id = profile_row["subject_id"]
    engine_position = _build_metric_position(cohort_rows, subject_id, "vo2max_rel")
    threshold_positions = [
        _build_metric_position(cohort_rows, subject_id, "lt2_power_w"),
        _build_metric_position(cohort_rows, subject_id, "lt1_power_w"),
    ]
    if engine_position is None:
        return {}
    threshold_score = _average_score(
        [float(position["percentile"]) for position in threshold_positions if position is not None]
    )
    if threshold_score is None:
        return {}

    x = float(engine_position["percentile"])
    y = threshold_score
    if x >= 66.0 and y >= 66.0:
        area_label = "엔진·threshold 균형 상위"
    elif x >= 66.0:
        area_label = "엔진 우위 구간"
    elif y >= 66.0:
        area_label = "threshold 효율 우위"
    else:
        area_label = "유산소 효율 형성 구간"
    return {
        "subject_id": subject_id,
        "x": round(x, 1),
        "y": round(y, 1),
        "area_label": area_label,
        "vo2max_rel": profile_row.get("vo2max_rel"),
        "lt1_power_w": profile_row.get("lt1_power_w"),
        "lt2_power_w": profile_row.get("lt2_power_w"),
        "is_selected": False,
    }


def _build_aerobic_decoupling_map(
    snapshot_rows: list[dict],
    selected_subject_id: str | None = None,
) -> dict | None:
    """Build engine-vs-threshold cohort map."""
    profiles = _build_latest_snapshot_metric_profiles(
        snapshot_rows,
        ("vo2max_rel", "lt1_power_w", "lt2_power_w"),
    )
    points = []
    highlighted = None
    for profile in profiles:
        point = _build_aerobic_decoupling_point(profiles, profile)
        if not point:
            continue
        point["is_selected"] = point["subject_id"] == selected_subject_id
        points.append(point)
        if point["is_selected"]:
            highlighted = point
    if not points or highlighted is None:
        return None
    return {
        "axes": {
            "x_label": "VO2max 엔진",
            "y_label": "Threshold posture",
        },
        "style": {
            "other_fill": "rgba(120, 128, 140, 0.30)",
            "other_radius": 4,
            "other_stroke": "transparent",
            "selected_fill": "#184e59",
            "selected_radius": 8,
            "selected_stroke": "#f4efe6",
        },
        "points": points,
        "highlighted": highlighted,
    }


def _build_dashboard_delta_matrix(detail: dict) -> dict | None:
    """Build a compact delta matrix from the latest usable trend payload."""
    latest_trend = detail.get("latest_trend") or {}
    if detail.get("history_state") != "timeline" or latest_trend.get("state") != "delta_ready":
        return None
    delta_metrics = latest_trend.get("delta_metrics") or {}
    rows = []
    metric_defs = [
        ("VO2max", "delta_vo2max_rel", "pct_delta_vo2max_rel", "mL/kg/min"),
        ("LT1", "delta_lt1_power_w", "pct_delta_lt1_power_w", "W"),
        ("FatMax", "delta_fatmax_power_w", None, "W"),
        ("VLamax", "delta_vlamax", None, "mmol/L/s"),
    ]
    for label, delta_key, pct_key, unit in metric_defs:
        if delta_key not in delta_metrics:
            continue
        delta_value = delta_metrics.get(delta_key)
        if not isinstance(delta_value, (int, float)):
            continue
        direction = "up" if delta_value > 0 else "down" if delta_value < 0 else "flat"
        rows.append({
            "label": label,
            "delta": delta_value,
            "pct_delta": delta_metrics.get(pct_key) if pct_key else None,
            "unit": unit,
            "direction": direction,
        })
    if not rows:
        return None
    return {
        "comparison_anchor_measured_at": latest_trend.get("comparison_anchor_measured_at", ""),
        "rows": rows,
    }


def _build_glycogen_economy_point(
    cohort_rows: list[dict],
    profile_row: dict,
) -> dict:
    """Build one glycogen economy point for INSCYD subjects."""
    subject_id = profile_row["subject_id"]
    glycogen_position = _build_metric_position(cohort_rows, subject_id, "glycogen_g")
    output_positions = [
        _build_metric_position(cohort_rows, subject_id, "carbmax_w"),
        _build_metric_position(cohort_rows, subject_id, "vlamax"),
    ]
    if glycogen_position is None:
        return {}
    output_score = _average_score(
        [float(position["percentile"]) for position in output_positions if position is not None]
    )
    if output_score is None:
        return {}
    x = float(glycogen_position["percentile"])
    y = output_score
    if x >= 66.0 and y >= 66.0:
        area_label = "glycogen·고출력 상위"
    elif x >= 66.0:
        area_label = "glycogen reserve 우위"
    elif y >= 66.0:
        area_label = "고출력 활용 우위"
    else:
        area_label = "glycogen economy 형성"
    return {
        "subject_id": subject_id,
        "x": round(x, 1),
        "y": round(y, 1),
        "area_label": area_label,
        "glycogen_g": profile_row.get("glycogen_g"),
        "carbmax_w": profile_row.get("carbmax_w"),
        "vlamax": profile_row.get("vlamax"),
        "is_selected": False,
    }


def _build_glycogen_economy_map(
    snapshot_rows: list[dict],
    selected_subject_id: str | None = None,
) -> dict | None:
    """Build INSCYD-only glycogen economy map."""
    profiles = _build_latest_snapshot_metric_profiles(
        snapshot_rows,
        ("glycogen_g", "carbmax_w", "vlamax"),
    )
    points = []
    highlighted = None
    for profile in profiles:
        if all(profile.get(key) is None for key in ("carbmax_w", "vlamax")):
            continue
        point = _build_glycogen_economy_point(profiles, profile)
        if not point:
            continue
        point["is_selected"] = point["subject_id"] == selected_subject_id
        points.append(point)
        if point["is_selected"]:
            highlighted = point
    if not points or highlighted is None:
        return None
    return {
        "axes": {
            "x_label": "Glycogen reserve",
            "y_label": "High-output use",
        },
        "style": {
            "other_fill": "rgba(120, 128, 140, 0.30)",
            "other_radius": 4,
            "other_stroke": "transparent",
            "selected_fill": "#6d4c9f",
            "selected_radius": 8,
            "selected_stroke": "#f4efe6",
        },
        "points": points,
        "highlighted": highlighted,
    }


def _build_dashboard_coverage_panel(
    subject_snapshot_rows: list[dict],
    detail: dict,
) -> dict:
    """Build compact readiness/coverage cards for subject drill-in."""
    source_counts: dict[str, int] = {}
    for row in subject_snapshot_rows:
        source = str(row.get("source_kind") or "").strip() or "unknown"
        source_counts[source] = source_counts.get(source, 0) + 1
    return {
        "cards": [
            {"label": "CPET anchor", "value": source_counts.get("cpet_submission", 0)},
            {"label": "INSCYD anchor", "value": source_counts.get("inscyd_report", 0)},
            {"label": "반복 측정", "value": "준비됨" if detail.get("history_state") == "timeline" else "1회"},
            {"label": "delta", "value": "가능" if detail.get("latest_trend", {}).get("state") == "delta_ready" else "대기"},
            {"label": "연료 전략", "value": "가능" if detail.get("fuel_strategy_map") else "대기"},
            {"label": "INSCYD 고급", "value": "가능" if detail.get("anaerobic_profile") or detail.get("glycogen_economy_map") else "없음"},
        ]
    }


def _classify_anaerobic_band(score: float | None) -> str:
    """Translate a VLamax percentile into a readable anaerobic-mobilization band."""
    if score is None:
        return "무산소 동원 정보 부족"
    if score >= 66.0:
        return "무산소 동원 상위권"
    if score >= 33.0:
        return "무산소 동원 중간권"
    return "무산소 동원 보강 구간"


def _classify_high_intensity_band(score: float | None) -> str:
    """Translate AT/CarbMax percentile into a readable high-intensity output band."""
    if score is None:
        return "고강도 출력 정보 부족"
    if score >= 66.0:
        return "고강도 출력 상위권"
    if score >= 33.0:
        return "고강도 출력 중간권"
    return "고강도 출력 형성 구간"


def _latest_rows_with_metric(
    rows: list[dict],
    metric_key: str,
) -> list[dict]:
    """Return one latest row per subject where a given metric is available."""
    latest: dict[str, dict] = {}
    for row in rows:
        subject_id = str(row.get("subject_id") or "").strip()
        if not subject_id or row.get(metric_key) is None:
            continue
        latest.setdefault(subject_id, row)
    return list(latest.values())


def _build_anaerobic_profile_point(
    cohort_rows: list[dict],
    latest_row: dict,
) -> dict:
    """Build an INSCYD-only anaerobic profile point."""
    subject_id = latest_row["subject_id"]
    vlamax_position = _build_metric_position(cohort_rows, subject_id, "vlamax")
    at_position = _build_metric_position(cohort_rows, subject_id, "at_power_w")
    carbmax_position = _build_metric_position(cohort_rows, subject_id, "carbmax_w")

    x_score = (
        float(vlamax_position["percentile"])
        if vlamax_position is not None
        else None
    )
    output_score = _average_score(
        [
            float(position["percentile"])
            for position in (at_position, carbmax_position)
            if position is not None
        ]
    )
    x = x_score if x_score is not None else 50.0
    y = output_score if output_score is not None else 50.0

    if x >= 66.0 and y >= 66.0:
        area_key = "anaerobic_high_output"
        area_label = "무산소·고출력 상위"
    elif x >= 66.0:
        area_key = "anaerobic_punch"
        area_label = "공격형 에너지 우위"
    elif y >= 66.0:
        area_key = "high_intensity_diesel"
        area_label = "고강도 유지 우위"
    else:
        area_key = "anaerobic_building"
        area_label = "무산소 기반 형성"

    return {
        "subject_id": subject_id,
        "x": round(x, 1),
        "y": round(y, 1),
        "vlamax": latest_row.get("vlamax"),
        "at_power_w": latest_row.get("at_power_w"),
        "carbmax_w": latest_row.get("carbmax_w"),
        "glycogen_g": latest_row.get("glycogen_g"),
        "anchor_measured_at": latest_row.get("measured_at", ""),
        "anaerobic_score": x_score,
        "output_score": output_score,
        "anaerobic_label": _classify_anaerobic_band(x_score),
        "output_label": _classify_high_intensity_band(output_score),
        "area_key": area_key,
        "area_label": area_label,
    }


def _build_anaerobic_profile_map(
    snapshot_rows: list[dict],
    selected_subject_id: str | None = None,
) -> dict | None:
    """Build an INSCYD-only anaerobic profile map from latest VLamax-capable rows."""
    cohort_rows = _latest_rows_with_metric(snapshot_rows, "vlamax")
    if not cohort_rows:
        return None

    points: list[dict] = []
    highlighted = None
    for row in cohort_rows:
        point = _build_anaerobic_profile_point(cohort_rows, row)
        point["is_selected"] = point["subject_id"] == selected_subject_id
        points.append(point)
        if point["is_selected"]:
            highlighted = point

    if highlighted is None:
        return None

    return {
        "axes": {
            "x_label": "VLamax",
            "y_label": "AT / CarbMax",
        },
        "style": {
            "other_fill": "rgba(120, 128, 140, 0.38)",
            "other_radius": 4,
            "other_stroke": "transparent",
            "selected_fill": "#8f3b2f",
            "selected_radius": 8,
            "selected_stroke": "#f4efe6",
        },
        "points": points,
        "highlighted": highlighted,
        "summary": {
            "total_subjects": len(points),
            "high_anaerobic_count": len(
                [point for point in points if (point.get("anaerobic_score") or 0.0) >= 66.0]
            ),
            "high_output_count": len(
                [point for point in points if (point.get("output_score") or 0.0) >= 66.0]
            ),
        },
    }


def summarize_dashboard_feature_analytics(
    db_path: Path,
    subject_ids: list[str] | None = None,
) -> dict:
    """Build a cohort-level overview for dashboard analytics."""
    all_rows = _filter_dashboard_rows_by_subject_ids(
        list_subject_feature_sets(db_path, include_payload=False, limit=5000),
        subject_ids=subject_ids,
    )
    endurance_rows = _filter_dashboard_rows_by_subject_ids(
        list_subject_feature_sets(
        db_path,
        feature_spec_key="endurance_core",
        include_payload=True,
        limit=5000,
        ),
        subject_ids=subject_ids,
    )
    delta_rows = _filter_dashboard_rows_by_subject_ids(
        list_subject_feature_sets(
        db_path,
        feature_spec_key="longitudinal_delta",
        include_payload=True,
        limit=5000,
        ),
        subject_ids=subject_ids,
    )

    latest_by_subject: dict[str, dict] = {}
    subjects_with_multi_date_history = 0
    for row in endurance_rows:
        latest_by_subject.setdefault(row["subject_id"], row)

    rows_by_subject: dict[str, list[dict]] = {}
    for row in endurance_rows:
        rows_by_subject.setdefault(row["subject_id"], []).append(row)
    for rows in rows_by_subject.values():
        if len(rows) >= 2:
            subjects_with_multi_date_history += 1

    latest_anchor_measured_at = ""
    if endurance_rows:
        latest_anchor_measured_at = endurance_rows[0]["anchor_measured_at"]

    available_vo2 = 0
    available_fatmax = 0
    for row in endurance_rows:
        features = _feature_payload_features(row)
        if isinstance(features.get("vo2max_rel"), (int, float)):
            available_vo2 += 1
        if isinstance(features.get("fatmax_power_w"), (int, float)):
            available_fatmax += 1

    latest_rows = list(latest_by_subject.values())
    latest_delta_by_subject = {
        row["subject_id"]: delta_row
        for row in latest_rows
        if (delta_row := next(
            (
                item for item in delta_rows
                if item.get("anchor_snapshot_id") == row.get("anchor_snapshot_id")
            ),
            None,
        )) is not None
    }
    cohort_map = _build_cohort_map(latest_rows, latest_delta_by_subject)
    display_names = _get_dashboard_subject_display_names(
        db_path,
        list({row["subject_id"] for row in latest_rows}),
    )

    # Keep the headline count aligned with the cohort-map classification.
    # If a subject has an older usable delta but the latest anchor is no longer
    # history-ready, the overview should not imply that the current cohort map
    # contains a non-zero active change segment.
    subjects_with_usable_delta = int(cohort_map["summary"]["history_ready_count"])
    single_anchor_subjects = max(len(latest_by_subject) - subjects_with_multi_date_history, 0)
    sparse_subject_preview = sorted(
        [
            display_names.get(row["subject_id"], row.get("subject_name", ""))
            for row in latest_rows
            if len(rows_by_subject.get(row["subject_id"], [])) < 2
        ]
    )[:3]

    base_summary = summarize_subject_feature_sets(db_path)
    quality_flag_counts = _count_quality_flags(endurance_rows + delta_rows)

    return {
        "total_feature_rows": base_summary["total"],
        "total_subjects": len({row["subject_id"] for row in all_rows}),
        "latest_anchor_measured_at": latest_anchor_measured_at,
        "usable_anchor_rows": len(endurance_rows),
        "usable_cpet_anchor_rows": len(endurance_rows),
        "subjects_with_current_state": len(latest_by_subject),
        "subjects_with_multi_date_history": subjects_with_multi_date_history,
        "subjects_with_multi_date_cpet_history": subjects_with_multi_date_history,
        "single_anchor_subjects": single_anchor_subjects,
        "subjects_with_usable_delta": subjects_with_usable_delta,
        "spec_counts": base_summary["by_spec"],
        "available_metrics": {
            "vo2max_rel_rows": available_vo2,
            "fatmax_power_w_rows": available_fatmax,
        },
        "metric_coverage": {
            "vo2max_rel_pct": round((available_vo2 / len(endurance_rows)) * 100, 1)
            if endurance_rows
            else 0.0,
            "fatmax_power_w_pct": round((available_fatmax / len(endurance_rows)) * 100, 1)
            if endurance_rows
            else 0.0,
        },
        "anchor_window": {
            "earliest_measured_at": endurance_rows[-1]["anchor_measured_at"] if endurance_rows else "",
            "latest_measured_at": latest_anchor_measured_at,
        },
        "sparse_subject_preview": sparse_subject_preview,
        "quality_flag_counts": quality_flag_counts,
        "cohort_map_summary": cohort_map["summary"],
    }


def list_dashboard_subject_analytics(
    db_path: Path,
    limit: int = 100,
    subject_ids: list[str] | None = None,
) -> list[dict]:
    """List latest dashboard subject cards with history state and privacy-safe positioning."""
    endurance_rows = _filter_dashboard_rows_by_subject_ids(
        list_subject_feature_sets(
        db_path,
        feature_spec_key="endurance_core",
        include_payload=True,
        limit=5000,
        ),
        subject_ids=subject_ids,
    )
    delta_rows = _filter_dashboard_rows_by_subject_ids(
        list_subject_feature_sets(
        db_path,
        feature_spec_key="longitudinal_delta",
        include_payload=True,
        limit=5000,
        ),
        subject_ids=subject_ids,
    )
    delta_by_anchor_snapshot_id = {
        row.get("anchor_snapshot_id"): row
        for row in delta_rows
        if row.get("anchor_snapshot_id")
    }
    display_names = _get_dashboard_subject_display_names(
        db_path,
        list({row["subject_id"] for row in endurance_rows}),
    )

    rows_by_subject: dict[str, list[dict]] = {}
    latest_rows: list[dict] = []
    for row in endurance_rows:
        rows_by_subject.setdefault(row["subject_id"], []).append(row)
        if row["subject_id"] not in {item["subject_id"] for item in latest_rows}:
            latest_rows.append(row)

    latest_delta_by_subject = {
        row["subject_id"]: delta_by_anchor_snapshot_id.get(row.get("anchor_snapshot_id"))
        for row in latest_rows
        if delta_by_anchor_snapshot_id.get(row.get("anchor_snapshot_id")) is not None
    }

    subject_cards: list[dict] = []
    for subject_id, rows in rows_by_subject.items():
        latest = rows[0]
        latest_features = _feature_payload_features(latest)
        usable_delta_count = 0
        timeline = []
        for row in sorted(rows, key=lambda item: item["anchor_measured_at"]):
            point = _build_dashboard_timeline_point(
                row,
                delta_by_anchor_snapshot_id.get(row.get("anchor_snapshot_id")),
            )
            if point["has_usable_delta"]:
                usable_delta_count += 1
            timeline.append(point)

        latest_delta_row = latest_delta_by_subject.get(subject_id)
        cohort_map_point = _build_cohort_map_point(
            latest_rows,
            list(latest_delta_by_subject.values()),
            latest,
            latest_delta_row,
        )

        subject_cards.append({
            "subject_id": subject_id,
            "subject_name": display_names.get(subject_id, latest.get("subject_name", "")),
            "latest_anchor_measured_at": latest["anchor_measured_at"],
            "history_state": "timeline" if len(rows) >= 2 else "single_anchor",
            "usable_history_count": len(rows),
            "usable_delta_count": usable_delta_count,
            "current_state": {
                "vo2max_rel": latest_features.get("vo2max_rel"),
                "fatmax_power_w": latest_features.get("fatmax_power_w"),
                "lt1_power_w": latest_features.get("lt1_power_w"),
                "quality_flags": latest.get("quality_flags", []),
            },
            "cohort_positioning": {
                "vo2max_rel": _build_metric_position(latest_rows, subject_id, "vo2max_rel"),
                "fatmax_power_w": _build_metric_position(latest_rows, subject_id, "fatmax_power_w"),
            },
            "cohort_map_point": cohort_map_point,
            "timeline_preview": timeline[-3:],
        })

    subject_cards.sort(
        key=lambda item: (item["latest_anchor_measured_at"], item["subject_name"]),
        reverse=True,
    )
    return subject_cards[:limit]


def get_dashboard_subject_analytics(
    db_path: Path,
    subject_id: str,
    subject_ids: list[str] | None = None,
) -> dict | None:
    """Return one subject's dashboard analytics detail."""
    if subject_ids and subject_id not in set(subject_ids):
        return None

    subject_cards = list_dashboard_subject_analytics(
        db_path,
        limit=5000,
        subject_ids=subject_ids,
    )
    target = next((row for row in subject_cards if row["subject_id"] == subject_id), None)
    if target is None:
        return None

    all_endurance_rows = _filter_dashboard_rows_by_subject_ids(
        list_subject_feature_sets(
            db_path,
            feature_spec_key="endurance_core",
            include_payload=True,
            limit=5000,
        ),
        subject_ids=subject_ids,
    )
    all_delta_rows = _filter_dashboard_rows_by_subject_ids(
        list_subject_feature_sets(
            db_path,
            feature_spec_key="longitudinal_delta",
            include_payload=True,
            limit=5000,
        ),
        subject_ids=subject_ids,
    )
    all_snapshot_rows = _filter_dashboard_rows_by_subject_ids(
        list_subject_metric_snapshots(
            db_path,
            limit=5000,
            include_payload=False,
        ),
        subject_ids=subject_ids,
    )
    latest_endurance_rows: list[dict] = []
    seen_subject_ids: set[str] = set()
    for row in all_endurance_rows:
        if row["subject_id"] in seen_subject_ids:
            continue
        latest_endurance_rows.append(row)
        seen_subject_ids.add(row["subject_id"])

    endurance_rows = list_subject_feature_sets(
        db_path,
        subject_id=subject_id,
        feature_spec_key="endurance_core",
        include_payload=True,
        limit=5000,
    )
    delta_rows = list_subject_feature_sets(
        db_path,
        subject_id=subject_id,
        feature_spec_key="longitudinal_delta",
        include_payload=True,
        limit=5000,
    )
    delta_by_anchor_snapshot_id = {
        row.get("anchor_snapshot_id"): row
        for row in delta_rows
        if row.get("anchor_snapshot_id")
    }
    latest_rows = [row for row in subject_cards]
    latest_delta_by_subject = {}
    all_delta_by_anchor_snapshot_id = {
        row.get("anchor_snapshot_id"): row
        for row in all_delta_rows
        if row.get("anchor_snapshot_id")
    }
    for row in subject_cards:
        endurance_anchor = next((item for item in latest_endurance_rows if item["subject_id"] == row["subject_id"]), None)
        if endurance_anchor is None:
            continue
        delta_row = all_delta_by_anchor_snapshot_id.get(endurance_anchor.get("anchor_snapshot_id"))
        if delta_row is not None:
            latest_delta_by_subject[row["subject_id"]] = delta_row
    timeline = [
        _build_dashboard_timeline_point(
            row,
            delta_by_anchor_snapshot_id.get(row.get("anchor_snapshot_id")),
        )
        for row in sorted(endurance_rows, key=lambda item: item["anchor_measured_at"])
    ]
    latest_trend = _build_latest_trend_summary(timeline)
    positioning_widgets = {
        "vo2max_rel": _build_positioning_widget(target["cohort_positioning"].get("vo2max_rel")),
        "fatmax_power_w": _build_positioning_widget(target["cohort_positioning"].get("fatmax_power_w")),
    }
    cohort_map = _build_cohort_map(
        latest_endurance_rows,
        latest_delta_by_subject,
        selected_subject_id=subject_id,
    )
    current_state_map = _build_current_state_map(
        latest_endurance_rows,
        selected_subject_id=subject_id,
    )
    fuel_strategy_map = _build_fuel_strategy_map(
        all_snapshot_rows,
        selected_subject_id=subject_id,
    )
    anaerobic_profile = _build_anaerobic_profile_map(
        all_snapshot_rows,
        selected_subject_id=subject_id,
    )
    threshold_ladder = _build_threshold_ladder(
        all_snapshot_rows,
        selected_subject_id=subject_id,
    )
    fat_oxidation_efficiency_map = _build_fat_oxidation_efficiency_map(
        all_snapshot_rows,
        selected_subject_id=subject_id,
    )
    aerobic_decoupling_map = _build_aerobic_decoupling_map(
        all_snapshot_rows,
        selected_subject_id=subject_id,
    )
    glycogen_economy_map = _build_glycogen_economy_map(
        all_snapshot_rows,
        selected_subject_id=subject_id,
    )

    detail = {
        "subject": {
            "id": target["subject_id"],
            "name": target["subject_name"],
        },
        "latest_anchor_measured_at": target["latest_anchor_measured_at"],
        "history_state": target["history_state"],
        "usable_history_count": target["usable_history_count"],
        "usable_delta_count": target["usable_delta_count"],
        "current_state": target["current_state"],
        "cohort_positioning": target["cohort_positioning"],
        "positioning_widgets": positioning_widgets,
        "cohort_map_point": target.get("cohort_map_point"),
        "cohort_map": cohort_map,
        "current_state_map": current_state_map,
        "threshold_ladder": threshold_ladder,
        "fuel_strategy_map": fuel_strategy_map,
        "fat_oxidation_efficiency_map": fat_oxidation_efficiency_map,
        "aerobic_decoupling_map": aerobic_decoupling_map,
        "anaerobic_profile": anaerobic_profile,
        "glycogen_economy_map": glycogen_economy_map,
        "latest_trend": latest_trend,
        "timeline_window": {
            "first_anchor_measured_at": timeline[0]["anchor_measured_at"] if timeline else "",
            "latest_anchor_measured_at": timeline[-1]["anchor_measured_at"] if timeline else "",
        },
        "timeline": timeline,
    }
    subject_snapshot_rows = [
        row for row in all_snapshot_rows if row.get("subject_id") == subject_id
    ]
    detail["delta_matrix"] = _build_dashboard_delta_matrix(detail)
    detail["coverage_panel"] = _build_dashboard_coverage_panel(subject_snapshot_rows, detail)
    return detail


def build_subject_feature_set_compare(
    db_path: Path,
    baseline_feature_row_id: str,
    current_feature_row_id: str,
) -> dict:
    """Build a two-feature-set comparison payload for explorer UIs."""
    baseline = get_subject_feature_set(db_path, baseline_feature_row_id)
    if baseline is None:
        raise ValueError("invalid baseline feature set")

    current = get_subject_feature_set(db_path, current_feature_row_id)
    if current is None:
        raise ValueError("invalid current feature set")

    if baseline["feature_row_id"] == current["feature_row_id"]:
        raise ValueError("baseline and current feature sets must differ")

    if (
        baseline["feature_spec_key"] != current["feature_spec_key"]
        or baseline["feature_spec_version"] != current["feature_spec_version"]
    ):
        raise ValueError("feature sets must share the same spec and version")

    baseline_features = baseline.get("feature_payload", {}).get("features", {})
    current_features = current.get("feature_payload", {}).get("features", {})

    metrics: list[dict] = []
    for key in sorted(set(baseline_features) & set(current_features)):
        before = baseline_features.get(key)
        after = current_features.get(key)
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
            continue
        delta = round(float(after) - float(before), 2)
        metrics.append({
            "key": key,
            "label": key.replace("_", " "),
            "before_value": before,
            "after_value": after,
            "delta": delta,
        })

    return {
        "baseline": baseline,
        "current": current,
        "metrics": metrics,
        "feature_spec_key": baseline["feature_spec_key"],
        "feature_spec_version": baseline["feature_spec_version"],
    }


def build_subject_metric_snapshot_compare(
    db_path: Path,
    baseline_snapshot_id: str,
    current_snapshot_id: str,
) -> dict:
    """Build a two-snapshot comparison payload for explorer UIs."""
    baseline = get_subject_metric_snapshot(db_path, baseline_snapshot_id)
    if baseline is None:
        raise ValueError("invalid baseline snapshot")

    current = get_subject_metric_snapshot(db_path, current_snapshot_id)
    if current is None:
        raise ValueError("invalid current snapshot")

    if baseline["snapshot_id"] == current["snapshot_id"]:
        raise ValueError("baseline and current snapshots must differ")

    metrics: list[dict] = []
    for key, label, unit in _SNAPSHOT_COMPARE_METRICS:
        if baseline.get(key) is None or current.get(key) is None:
            continue

        before = baseline[key]
        after = current[key]
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
        "baseline": baseline,
        "current": current,
        "metrics": metrics,
    }


def build_endurance_core_feature_set(
    db_path: Path,
    anchor_snapshot_id: str,
) -> dict | None:
    """Build an endurance_core_v1 feature row dict from one snapshot anchor."""
    snapshot = get_subject_metric_snapshot(db_path, anchor_snapshot_id)
    if snapshot is None:
        return None

    features = {
        key: snapshot[key]
        for key in _ENDURANCE_CORE_FEATURE_KEYS
        if snapshot.get(key) is not None
    }
    features["source_kind"] = snapshot["source_kind"]

    missing_metrics = sorted(
        key for key in _ENDURANCE_CORE_FEATURE_KEYS if key not in features
    )
    quality_flags = [f"missing_{key}" for key in missing_metrics]

    payload = {
        "spec": {
            "key": _ENDURANCE_CORE_FEATURE_SPEC_KEY,
            "version": _ENDURANCE_CORE_FEATURE_SPEC_VERSION,
        },
        "inputs": {
            "anchor_snapshot_id": anchor_snapshot_id,
            "anchor_measured_at": snapshot["measured_at"],
            "source_kind": snapshot["source_kind"],
        },
        "features": features,
    }

    return {
        "feature_row_id": str(uuid.uuid4()),
        "subject_id": snapshot["subject_id"],
        "feature_spec_key": _ENDURANCE_CORE_FEATURE_SPEC_KEY,
        "feature_spec_version": _ENDURANCE_CORE_FEATURE_SPEC_VERSION,
        "anchor_snapshot_id": anchor_snapshot_id,
        "anchor_measured_at": snapshot["measured_at"],
        "window_label": "anchor",
        "input_snapshot_ids_json": json.dumps([anchor_snapshot_id]),
        "input_source_kinds_json": json.dumps([snapshot["source_kind"]]),
        "feature_payload_json": json.dumps(payload, ensure_ascii=True, sort_keys=True),
        "quality_flags_json": json.dumps(quality_flags),
    }


def _parse_snapshot_datetime(value: str) -> datetime | None:
    """Parse snapshot measured_at values stored as ISO dates or datetimes."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _find_previous_snapshot_id(
    db_path: Path,
    anchor_snapshot_id: str,
    subject_id: str,
) -> str | None:
    """Return the immediately previous snapshot id for the same subject."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT snapshot_id
           FROM subject_metric_snapshots
           WHERE subject_id = ?
           ORDER BY measured_at ASC, created_at ASC, snapshot_id ASC""",
        (subject_id,),
    ).fetchall()
    conn.close()
    ordered_ids = [str(row["snapshot_id"]) for row in rows]
    if anchor_snapshot_id not in ordered_ids:
        return None
    anchor_index = ordered_ids.index(anchor_snapshot_id)
    if anchor_index == 0:
        return None
    return ordered_ids[anchor_index - 1]


def build_longitudinal_delta_feature_set(
    db_path: Path,
    anchor_snapshot_id: str,
) -> dict | None:
    """Build a longitudinal_delta_v1 feature row from an anchor snapshot."""
    anchor = get_subject_metric_snapshot(db_path, anchor_snapshot_id)
    if anchor is None:
        return None

    previous_snapshot_id = _find_previous_snapshot_id(
        db_path,
        anchor_snapshot_id=anchor_snapshot_id,
        subject_id=anchor["subject_id"],
    )
    previous = (
        get_subject_metric_snapshot(db_path, previous_snapshot_id)
        if previous_snapshot_id is not None
        else None
    )

    input_snapshot_ids = [anchor_snapshot_id]
    input_source_kinds = [anchor["source_kind"]]
    quality_flags: list[str] = []
    features: dict[str, float | int] = {}

    previous_measured_at = None
    previous_source_kind = None
    days_since_previous = None

    if previous is None:
        quality_flags.append("missing_previous_snapshot")
    else:
        input_snapshot_ids = [previous_snapshot_id, anchor_snapshot_id]
        input_source_kinds = [previous["source_kind"], anchor["source_kind"]]
        previous_measured_at = previous["measured_at"]
        previous_source_kind = previous["source_kind"]

        anchor_dt = _parse_snapshot_datetime(anchor["measured_at"])
        previous_dt = _parse_snapshot_datetime(previous["measured_at"])
        if anchor_dt is not None and previous_dt is not None:
            days_since_previous = max(0, (anchor_dt - previous_dt).days)
            features["days_since_previous"] = days_since_previous

        if previous["source_kind"] != anchor["source_kind"]:
            quality_flags.append("mixed_source_compare")

        for key in _LONGITUDINAL_DELTA_DELTA_KEYS:
            anchor_value = anchor.get(key)
            previous_value = previous.get(key)

            missing = False
            if anchor_value is None:
                quality_flags.append(f"missing_anchor_{key}")
                missing = True
            if previous_value is None:
                quality_flags.append(f"missing_previous_{key}")
                missing = True
            if missing:
                continue

            try:
                delta = round(float(anchor_value) - float(previous_value), 2)
            except (TypeError, ValueError):
                continue

            features[f"delta_{key}"] = delta

        for key in _LONGITUDINAL_DELTA_PCT_KEYS:
            anchor_value = anchor.get(key)
            previous_value = previous.get(key)
            if anchor_value is None or previous_value is None:
                continue
            try:
                previous_float = float(previous_value)
                if previous_float == 0:
                    quality_flags.append(f"previous_zero_{key}")
                    continue
                pct_delta = round(((float(anchor_value) - previous_float) / previous_float) * 100, 2)
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            features[f"pct_delta_{key}"] = pct_delta

    payload = {
        "spec": {
            "key": _LONGITUDINAL_DELTA_FEATURE_SPEC_KEY,
            "version": _LONGITUDINAL_DELTA_FEATURE_SPEC_VERSION,
        },
        "inputs": {
            "anchor_snapshot_id": anchor_snapshot_id,
            "previous_snapshot_id": previous_snapshot_id,
            "anchor_measured_at": anchor["measured_at"],
            "previous_measured_at": previous_measured_at,
            "anchor_source_kind": anchor["source_kind"],
            "previous_source_kind": previous_source_kind,
            "days_since_previous": days_since_previous,
        },
        "features": features,
    }

    quality_flags.sort()
    return {
        "feature_row_id": str(uuid.uuid4()),
        "subject_id": anchor["subject_id"],
        "feature_spec_key": _LONGITUDINAL_DELTA_FEATURE_SPEC_KEY,
        "feature_spec_version": _LONGITUDINAL_DELTA_FEATURE_SPEC_VERSION,
        "anchor_snapshot_id": anchor_snapshot_id,
        "anchor_measured_at": anchor["measured_at"],
        "window_label": "previous_pair",
        "input_snapshot_ids_json": json.dumps(input_snapshot_ids),
        "input_source_kinds_json": json.dumps(input_source_kinds),
        "feature_payload_json": json.dumps(payload, ensure_ascii=True, sort_keys=True),
        "quality_flags_json": json.dumps(quality_flags),
    }


def _list_feature_anchor_snapshots(
    db_path: Path,
    snapshot_ids: list[str] | None = None,
) -> list[dict]:
    """List snapshot rows that can serve as feature anchors."""
    conn = _connect(db_path)
    if snapshot_ids:
        placeholders = ", ".join("?" for _ in snapshot_ids)
        rows = conn.execute(
            f"SELECT snapshot_id FROM subject_metric_snapshots WHERE snapshot_id IN ({placeholders}) ORDER BY measured_at ASC",
            snapshot_ids,
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT snapshot_id FROM subject_metric_snapshots ORDER BY measured_at ASC"
        ).fetchall()
    conn.close()
    return [{"snapshot_id": str(row["snapshot_id"])} for row in rows]


def upsert_subject_feature_set(
    db_path: Path,
    feature_row: dict,
    dry_run: bool = False,
) -> dict:
    """Insert or refresh a derived feature row by its spec/anchor identity."""
    conn = _connect(db_path)
    existing = conn.execute(
        """SELECT * FROM subject_feature_sets
           WHERE subject_id = ?
             AND feature_spec_key = ?
             AND feature_spec_version = ?
             AND anchor_snapshot_id = ?
             AND window_label = ?""",
        (
            feature_row["subject_id"],
            feature_row["feature_spec_key"],
            feature_row["feature_spec_version"],
            feature_row["anchor_snapshot_id"],
            feature_row["window_label"],
        ),
    ).fetchone()

    payload = {
        "subject_id": feature_row["subject_id"],
        "feature_spec_key": feature_row["feature_spec_key"],
        "feature_spec_version": feature_row["feature_spec_version"],
        "anchor_snapshot_id": feature_row.get("anchor_snapshot_id"),
        "anchor_measured_at": feature_row["anchor_measured_at"],
        "window_label": feature_row.get("window_label"),
        "input_snapshot_ids_json": feature_row.get("input_snapshot_ids_json", "[]"),
        "input_source_kinds_json": feature_row.get("input_source_kinds_json", "[]"),
        "feature_payload_json": feature_row.get("feature_payload_json", "{}"),
        "quality_flags_json": feature_row.get("quality_flags_json", "[]"),
    }

    if existing is not None:
        existing_dict = dict(existing)
        mutable_columns = (
            "anchor_measured_at",
            "input_snapshot_ids_json",
            "input_source_kinds_json",
            "feature_payload_json",
            "quality_flags_json",
        )
        if all(existing_dict.get(column) == payload.get(column) for column in mutable_columns):
            conn.close()
            return {"action": "skipped", "feature_row_id": existing["feature_row_id"]}

        if dry_run:
            conn.close()
            return {"action": "would_update", "feature_row_id": existing["feature_row_id"]}

        now = _now_utc()
        conn.execute(
            """UPDATE subject_feature_sets
               SET anchor_measured_at = ?,
                   input_snapshot_ids_json = ?,
                   input_source_kinds_json = ?,
                   feature_payload_json = ?,
                   quality_flags_json = ?,
                   updated_at = ?
               WHERE feature_row_id = ?""",
            (
                payload["anchor_measured_at"],
                payload["input_snapshot_ids_json"],
                payload["input_source_kinds_json"],
                payload["feature_payload_json"],
                payload["quality_flags_json"],
                now,
                existing["feature_row_id"],
            ),
        )
        conn.commit()
        conn.close()
        return {"action": "updated", "feature_row_id": existing["feature_row_id"]}

    if dry_run:
        conn.close()
        return {"action": "would_insert", "feature_row_id": feature_row.get("feature_row_id")}

    now = _now_utc()
    insert_payload = {
        "feature_row_id": feature_row.get("feature_row_id") or str(uuid.uuid4()),
        "created_at": now,
        "updated_at": now,
        **payload,
    }
    columns = list(insert_payload.keys())
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO subject_feature_sets ({', '.join(columns)}) VALUES ({placeholders})",
        [insert_payload[column] for column in columns],
    )
    conn.commit()
    conn.close()
    return {"action": "inserted", "feature_row_id": insert_payload["feature_row_id"]}


def backfill_endurance_core_feature_sets(
    db_path: Path,
    snapshot_ids: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Build and upsert endurance_core_v1 rows from snapshot anchors."""
    anchors = _list_feature_anchor_snapshots(db_path, snapshot_ids=snapshot_ids)
    summary = {
        "dry_run": dry_run,
        "snapshots_scanned": len(anchors),
        "feature_rows_built": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "would_insert": 0,
        "would_update": 0,
        "errors": [],
    }

    for anchor in anchors:
        snapshot_id = anchor["snapshot_id"]
        try:
            feature_row = build_endurance_core_feature_set(db_path, snapshot_id)
        except Exception as exc:  # pragma: no cover - defensive runner guard
            summary["errors"].append({
                "snapshot_id": snapshot_id,
                "builder": "build_endurance_core_feature_set",
                "error": str(exc),
            })
            continue

        if feature_row is None:
            continue

        summary["feature_rows_built"] += 1
        result = upsert_subject_feature_set(db_path, feature_row, dry_run=dry_run)
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


def backfill_longitudinal_delta_feature_sets(
    db_path: Path,
    snapshot_ids: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Build and upsert longitudinal_delta_v1 rows from snapshot anchors."""
    anchors = _list_feature_anchor_snapshots(db_path, snapshot_ids=snapshot_ids)
    summary = {
        "dry_run": dry_run,
        "snapshots_scanned": len(anchors),
        "feature_rows_built": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "would_insert": 0,
        "would_update": 0,
        "errors": [],
    }

    for anchor in anchors:
        snapshot_id = anchor["snapshot_id"]
        try:
            feature_row = build_longitudinal_delta_feature_set(db_path, snapshot_id)
        except Exception as exc:  # pragma: no cover - defensive runner guard
            summary["errors"].append({
                "snapshot_id": snapshot_id,
                "builder": "build_longitudinal_delta_feature_set",
                "error": str(exc),
            })
            continue

        if feature_row is None:
            continue

        summary["feature_rows_built"] += 1
        result = upsert_subject_feature_set(db_path, feature_row, dry_run=dry_run)
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


# ---------------------------------------------------------------------------
# Notes board
# ---------------------------------------------------------------------------


def get_notes_list(db_path: Path) -> list[dict]:
    """Return all notes sorted by updated_at DESC, with uploader display_name."""
    conn = _connect(db_path)
    rows = conn.execute(
        """
        SELECT n.slug, n.title, n.updated_at, n.created_at,
               n.uploaded_by_user_id,
               COALESCE(u.display_name, '—') AS uploader_name
        FROM notes_board n
        LEFT JOIN users u ON u.id = n.uploaded_by_user_id
        ORDER BY n.updated_at DESC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_note(db_path: Path, slug: str) -> dict | None:
    """Return one note by slug, or None if not found."""
    conn = _connect(db_path)
    row = conn.execute(
        """
        SELECT n.slug, n.title, n.html_content, n.updated_at, n.created_at,
               n.uploaded_by_user_id,
               COALESCE(u.display_name, '—') AS uploader_name
        FROM notes_board n
        LEFT JOIN users u ON u.id = n.uploaded_by_user_id
        WHERE n.slug = ?
        """,
        (slug,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_note(
    db_path: Path,
    slug: str,
    title: str,
    html_content: str,
    user_id: str | None = None,
) -> None:
    """Insert or replace a note. updated_at is always refreshed on replace."""
    conn = _connect(db_path)
    conn.execute(
        """
        INSERT INTO notes_board (slug, title, html_content, uploaded_by_user_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(slug) DO UPDATE SET
            title = excluded.title,
            html_content = excluded.html_content,
            uploaded_by_user_id = excluded.uploaded_by_user_id,
            updated_at = datetime('now')
        """,
        (slug, title, html_content, user_id),
    )
    conn.commit()
    conn.close()


def save_submission_files(
    db_path: Path,
    submission_id: str,
    files: list[tuple[str, bytes]],
) -> None:
    """Persist raw submission files as gzip-compressed BLOBs.

    Replaces all existing rows for submission_id in a single transaction.
    """
    conn = _connect(db_path)
    conn.execute(
        "DELETE FROM submission_files WHERE submission_id = ?",
        (submission_id,),
    )
    for filename, content in files:
        safe_name = Path(filename).name
        compressed = gzip.compress(content, compresslevel=6)
        conn.execute(
            """
            INSERT INTO submission_files (id, submission_id, filename, content_gz, size_bytes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, submission_id, safe_name, compressed, len(content)),
        )
    conn.commit()
    conn.close()


def restore_submission_files(
    db_path: Path,
    submission_id: str,
) -> list[tuple[str, bytes]]:
    """Return decompressed file tuples for a submission, ordered by filename.

    Returns an empty list if no rows exist.
    """
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT filename, content_gz FROM submission_files WHERE submission_id = ? ORDER BY filename",
        (submission_id,),
    ).fetchall()
    conn.close()
    return [(row["filename"], gzip.decompress(row["content_gz"])) for row in rows]
