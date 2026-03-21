"""
server.db — Platform SQLite CRUD for submissions and jobs.

Every function takes a db_path: Path parameter. No global state.
Uses raw sqlite3, WAL mode, TEXT primary keys (UUID).
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS submissions (
    id TEXT PRIMARY KEY,
    description TEXT,
    file_manifest TEXT,
    workspace_path TEXT,
    subject_name TEXT,
    test_date TEXT,
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


def init_db(db_path: Path) -> None:
    """Create submissions and jobs tables if they don't exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.close()


def create_submission(
    db_path: Path,
    description: str,
    file_manifest: list[dict],
    workspace_path: str,
    subject_name: str = "",
    test_date: str = "",
) -> str:
    """Insert a new submission and return its UUID."""
    submission_id = str(uuid.uuid4())
    manifest_json = json.dumps(file_manifest)
    conn = _connect(db_path)
    conn.execute(
        """INSERT INTO submissions
           (id, description, file_manifest, workspace_path, subject_name, test_date)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (submission_id, description, manifest_json, workspace_path,
         subject_name, test_date),
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
