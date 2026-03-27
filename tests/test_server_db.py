"""
tests/test_server_db.py — Unit tests for server.db and server.workspace.

22 tests covering the full submission/job lifecycle,
workspace creation, and schema validation.
"""

import json
import sqlite3
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from server.db import (
    _connect,
    create_job,
    create_submission,
    get_job,
    get_job_by_submission,
    get_pending_jobs,
    get_submission,
    init_db,
    list_jobs,
    update_job_status,
)
from server.workspace import create_workspace, get_workspace, list_files
from server.schemas import JobStatus, ReportSummary, SubmissionCreate


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path, initialized."""
    path = tmp_path / "test_platform.db"
    init_db(path)
    return path


@pytest.fixture()
def base_dir(tmp_path: Path) -> Path:
    """Provide a temporary base directory for workspaces."""
    d = tmp_path / "data"
    d.mkdir()
    return d


# ── Database Initialization ──────────────────────────────────────────


class TestInitDb:
    def test_creates_tables(self, db_path: Path) -> None:
        conn = sqlite3.connect(str(db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        conn.close()
        names = [t[0] for t in tables]
        assert "users" in names
        assert "submissions" in names
        assert "jobs" in names

    def test_wal_mode(self, db_path: Path) -> None:
        conn = _connect(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"

    def test_idempotent(self, db_path: Path) -> None:
        init_db(db_path)
        init_db(db_path)
        conn = sqlite3.connect(str(db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        conn.close()
        # 8 tables: subjects, users, submissions, jobs,
        #           report_user_links, report_name_overrides,
        #           report_notes, user_profiles
        assert len(tables) == 8


# ── Submissions ──────────────────────────────────────────────────────


class TestSubmissions:
    def test_create_returns_uuid(self, db_path: Path) -> None:
        sid = create_submission(
            db_path, "test upload", [{"name": "a.xlsx", "extension": "xlsx", "size_bytes": 1024}],
            "/data/ws/abc",
        )
        assert isinstance(sid, str)
        assert len(sid) == 36  # UUID format

    def test_get_submission_found(self, db_path: Path) -> None:
        manifest = [{"name": "b.fit", "extension": "fit", "size_bytes": 2048}]
        sid = create_submission(
            db_path, "desc", manifest, "/ws/path",
            subject_name="Park", test_date="2026-03-20",
        )
        sub = get_submission(db_path, sid)
        assert sub is not None
        assert sub["id"] == sid
        assert sub["description"] == "desc"
        assert sub["subject_name"] == "Park"
        assert sub["test_date"] == "2026-03-20"
        assert sub["file_manifest"] == manifest
        assert sub["workspace_path"] == "/ws/path"
        assert sub["created_at"] is not None

    def test_get_submission_not_found(self, db_path: Path) -> None:
        assert get_submission(db_path, "nonexistent") is None

    def test_manifest_stored_as_json(self, db_path: Path) -> None:
        manifest = [
            {"name": "x.xlsx", "extension": "xlsx", "size_bytes": 100},
            {"name": "y.fit", "extension": "fit", "size_bytes": 200},
        ]
        sid = create_submission(db_path, "multi", manifest, "/ws")
        conn = sqlite3.connect(str(db_path))
        raw = conn.execute(
            "SELECT file_manifest FROM submissions WHERE id = ?", (sid,)
        ).fetchone()[0]
        conn.close()
        assert json.loads(raw) == manifest

    def test_text_primary_key(self, db_path: Path) -> None:
        sid = create_submission(db_path, "d", [], "/ws")
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT typeof(id) FROM submissions WHERE id = ?", (sid,)
        ).fetchone()
        conn.close()
        assert row[0] == "text"


# ── Jobs ─────────────────────────────────────────────────────────────


class TestJobs:
    def test_create_job_returns_uuid(self, db_path: Path) -> None:
        sid = create_submission(db_path, "d", [], "/ws")
        jid = create_job(db_path, sid)
        assert isinstance(jid, str)
        assert len(jid) == 36

    def test_create_job_default_pending(self, db_path: Path) -> None:
        sid = create_submission(db_path, "d", [], "/ws")
        jid = create_job(db_path, sid)
        job = get_job(db_path, jid)
        assert job is not None
        assert job["status"] == "pending"
        assert job["started_at"] is None
        assert job["completed_at"] is None

    def test_get_job_not_found(self, db_path: Path) -> None:
        assert get_job(db_path, "missing") is None

    def test_update_to_processing(self, db_path: Path) -> None:
        sid = create_submission(db_path, "d", [], "/ws")
        jid = create_job(db_path, sid)
        update_job_status(db_path, jid, "processing")
        job = get_job(db_path, jid)
        assert job is not None
        assert job["status"] == "processing"
        assert job["started_at"] is not None
        assert job["completed_at"] is None

    def test_update_to_done(self, db_path: Path) -> None:
        sid = create_submission(db_path, "d", [], "/ws")
        jid = create_job(db_path, sid)
        update_job_status(
            db_path, jid, "done",
            report_slug="park-2026-03-20",
            report_url="/reports/park-2026-03-20.html",
        )
        job = get_job(db_path, jid)
        assert job is not None
        assert job["status"] == "done"
        assert job["completed_at"] is not None
        assert job["report_slug"] == "park-2026-03-20"
        assert job["report_url"] == "/reports/park-2026-03-20.html"

    def test_update_to_failed(self, db_path: Path) -> None:
        sid = create_submission(db_path, "d", [], "/ws")
        jid = create_job(db_path, sid)
        update_job_status(
            db_path, jid, "failed",
            error_message="Parser crashed",
        )
        job = get_job(db_path, jid)
        assert job is not None
        assert job["status"] == "failed"
        assert job["completed_at"] is not None
        assert job["error_message"] == "Parser crashed"

    def test_update_invalid_status(self, db_path: Path) -> None:
        sid = create_submission(db_path, "d", [], "/ws")
        jid = create_job(db_path, sid)
        with pytest.raises(ValueError, match="Invalid status"):
            update_job_status(db_path, jid, "cancelled")

    def test_list_jobs_newest_first(self, db_path: Path) -> None:
        sid = create_submission(db_path, "d", [], "/ws")
        j1 = create_job(db_path, sid)
        j2 = create_job(db_path, sid)
        jobs = list_jobs(db_path)
        assert len(jobs) == 2
        assert jobs[0]["id"] == j2
        assert jobs[1]["id"] == j1

    def test_list_jobs_status_filter(self, db_path: Path) -> None:
        sid = create_submission(db_path, "d", [], "/ws")
        j1 = create_job(db_path, sid)
        j2 = create_job(db_path, sid)
        update_job_status(db_path, j1, "processing")
        pending = list_jobs(db_path, status="pending")
        assert len(pending) == 1
        assert pending[0]["id"] == j2

    def test_get_pending_jobs(self, db_path: Path) -> None:
        sid = create_submission(db_path, "d", [], "/ws")
        j1 = create_job(db_path, sid)
        j2 = create_job(db_path, sid)
        update_job_status(db_path, j1, "done")
        pending = get_pending_jobs(db_path)
        assert len(pending) == 1
        assert pending[0]["id"] == j2

    def test_get_job_by_submission(self, db_path: Path) -> None:
        sid = create_submission(db_path, "d", [], "/ws")
        jid = create_job(db_path, sid)
        found = get_job_by_submission(db_path, sid)
        assert found is not None
        assert found["id"] == jid

    def test_get_job_by_submission_not_found(self, db_path: Path) -> None:
        assert get_job_by_submission(db_path, "no-such-sub") is None


# ── Workspace ────────────────────────────────────────────────────────


class TestWorkspace:
    def test_create_workspace_dirs(self, base_dir: Path) -> None:
        ws = create_workspace(base_dir, "sub-1", [])
        assert (ws / "raw").is_dir()
        assert (ws / "report").is_dir()

    def test_create_workspace_writes_files(self, base_dir: Path) -> None:
        files = [
            ("data.xlsx", b"excel-content"),
            ("ride.fit", b"fit-content"),
        ]
        ws = create_workspace(base_dir, "sub-2", files)
        assert (ws / "raw" / "data.xlsx").read_bytes() == b"excel-content"
        assert (ws / "raw" / "ride.fit").read_bytes() == b"fit-content"

    def test_get_workspace_exists(self, base_dir: Path) -> None:
        create_workspace(base_dir, "sub-3", [])
        ws = get_workspace(base_dir, "sub-3")
        assert ws is not None
        assert ws.is_dir()

    def test_get_workspace_missing(self, base_dir: Path) -> None:
        assert get_workspace(base_dir, "no-such-id") is None

    def test_list_files(self, base_dir: Path) -> None:
        files = [
            ("report.xlsx", b"x" * 512),
            ("workout.fit", b"f" * 1024),
        ]
        ws = create_workspace(base_dir, "sub-4", files)
        listing = list_files(ws)
        assert len(listing) == 2
        names = {f["name"] for f in listing}
        assert names == {"report.xlsx", "workout.fit"}
        for f in listing:
            assert "extension" in f
            assert "size_bytes" in f
            if f["name"] == "report.xlsx":
                assert f["extension"] == "xlsx"
                assert f["size_bytes"] == 512
            else:
                assert f["extension"] == "fit"
                assert f["size_bytes"] == 1024


# ── Schemas (Pydantic) ──────────────────────────────────────────────


class TestSchemas:
    def test_submission_create(self) -> None:
        s = SubmissionCreate(description="test")
        assert s.description == "test"
        assert s.subject_name == ""
        assert s.test_date == ""

    def test_job_status(self) -> None:
        j = JobStatus(
            id="abc", submission_id="def", status="pending",
            created_at="2026-03-21T00:00:00",
        )
        assert j.status == "pending"
        assert j.report_url is None

    def test_report_summary(self) -> None:
        r = ReportSummary(
            slug="park-2026", subject_name="Park",
            test_date="2026-03-20", report_url="/r/park.html",
        )
        assert r.slug == "park-2026"


# ── Full Lifecycle ──────────────────────────────────────────────────


class TestFullLifecycle:
    def test_full_lifecycle(self, db_path: Path, base_dir: Path) -> None:
        """End-to-end: submit -> workspace -> job -> process -> done."""
        files = [("test.xlsx", b"data-bytes")]
        ws = create_workspace(base_dir, "lifecycle-id", files)

        manifest = list_files(ws)
        assert len(manifest) == 1
        assert manifest[0]["name"] == "test.xlsx"

        sid = create_submission(
            db_path, "lifecycle test", manifest, str(ws),
            subject_name="Test Subject", test_date="2026-03-21",
        )
        sub = get_submission(db_path, sid)
        assert sub is not None
        assert sub["file_manifest"] == manifest

        jid = create_job(db_path, sid)
        job = get_job(db_path, jid)
        assert job is not None
        assert job["status"] == "pending"

        update_job_status(db_path, jid, "processing")
        job = get_job(db_path, jid)
        assert job is not None
        assert job["status"] == "processing"
        assert job["started_at"] is not None

        update_job_status(
            db_path, jid, "done",
            report_slug="test-2026-03-21",
            report_url="/reports/test-2026-03-21.html",
        )
        job = get_job(db_path, jid)
        assert job is not None
        assert job["status"] == "done"
        assert job["completed_at"] is not None
        assert job["report_url"] == "/reports/test-2026-03-21.html"

        found = get_job_by_submission(db_path, sid)
        assert found is not None
        assert found["id"] == jid

        pending = get_pending_jobs(db_path)
        assert len(pending) == 0

        all_jobs = list_jobs(db_path)
        assert len(all_jobs) == 1


# ── Edge Cases: Submissions ──────────────────────────────────────────


class TestSubmissionEdgeCases:
    def test_empty_file_manifest(self, db_path: Path) -> None:
        """Empty manifest is valid and round-trips as an empty list."""
        sid = create_submission(db_path, "no files", [], "/ws")
        sub = get_submission(db_path, sid)
        assert sub is not None
        assert sub["file_manifest"] == []

    def test_very_long_description(self, db_path: Path) -> None:
        """Submissions with very long descriptions are stored intact."""
        long_desc = "A" * 10_000
        sid = create_submission(db_path, long_desc, [], "/ws")
        sub = get_submission(db_path, sid)
        assert sub is not None
        assert sub["description"] == long_desc

    def test_unicode_in_description(self, db_path: Path) -> None:
        """Unicode (Korean, emoji) survives the round-trip."""
        desc = "박건윤 테스트 🏃‍♂️"
        sid = create_submission(db_path, desc, [], "/ws")
        sub = get_submission(db_path, sid)
        assert sub is not None
        assert sub["description"] == desc

    def test_init_db_creates_nested_parent_dirs(self, tmp_path: Path) -> None:
        """init_db creates parent dirs if they do not exist."""
        deep_path = tmp_path / "a" / "b" / "c" / "platform.db"
        init_db(deep_path)
        assert deep_path.exists()


# ── Edge Cases: Jobs ─────────────────────────────────────────────────


class TestJobEdgeCases:
    def test_update_job_unknown_kwarg_raises(self, db_path: Path) -> None:
        """Unknown kwargs to update_job_status must raise ValueError."""
        sid = create_submission(db_path, "d", [], "/ws")
        jid = create_job(db_path, sid)
        with pytest.raises(ValueError, match="Unknown kwarg"):
            update_job_status(db_path, jid, "processing", unknown_field="x")

    def test_update_nonexistent_job_is_silent(self, db_path: Path) -> None:
        """Updating a job that doesn't exist is a no-op (no exception)."""
        # SQLite UPDATE on a missing row succeeds silently; verify no exception
        update_job_status(db_path, "ghost-job-id", "done")

    def test_update_to_done_sets_completed_at_not_started_at(
        self, db_path: Path
    ) -> None:
        """Transitioning directly to 'done' sets completed_at but not started_at."""
        sid = create_submission(db_path, "d", [], "/ws")
        jid = create_job(db_path, sid)
        update_job_status(db_path, jid, "done")
        job = get_job(db_path, jid)
        assert job is not None
        assert job["completed_at"] is not None
        assert job["started_at"] is None

    def test_timestamps_are_iso_format(self, db_path: Path) -> None:
        """started_at and completed_at must be parseable ISO-8601 strings."""
        from datetime import datetime

        sid = create_submission(db_path, "d", [], "/ws")
        jid = create_job(db_path, sid)
        update_job_status(db_path, jid, "processing")
        update_job_status(db_path, jid, "done")
        job = get_job(db_path, jid)
        assert job is not None
        # Both should parse without error
        datetime.fromisoformat(job["started_at"])
        datetime.fromisoformat(job["completed_at"])

    def test_list_jobs_unknown_status_returns_empty(self, db_path: Path) -> None:
        """Filtering by a status that has no rows returns an empty list."""
        sid = create_submission(db_path, "d", [], "/ws")
        create_job(db_path, sid)
        result = list_jobs(db_path, status="processing")
        assert result == []

    def test_get_job_by_submission_returns_latest(self, db_path: Path) -> None:
        """When a submission has multiple jobs, the most recent is returned."""
        sid = create_submission(db_path, "d", [], "/ws")
        create_job(db_path, sid)
        jid2 = create_job(db_path, sid)
        found = get_job_by_submission(db_path, sid)
        assert found is not None
        assert found["id"] == jid2

    def test_create_job_for_nonexistent_submission(self, db_path: Path) -> None:
        """Creating a job for a nonexistent submission_id succeeds at DB level.

        SQLite does not enforce FK constraints by default.
        This test documents the current behaviour; callers must validate upstream.
        """
        jid = create_job(db_path, "no-such-submission")
        job = get_job(db_path, jid)
        assert job is not None
        assert job["submission_id"] == "no-such-submission"

    def test_all_valid_statuses_accepted(self, db_path: Path) -> None:
        """Every value in VALID_STATUSES must be accepted without error."""
        from server.db import VALID_STATUSES

        sid = create_submission(db_path, "d", [], "/ws")
        for status in VALID_STATUSES:
            jid = create_job(db_path, sid)
            # Must not raise
            update_job_status(db_path, jid, status)
            job = get_job(db_path, jid)
            assert job is not None
            assert job["status"] == status


# ── Edge Cases: Workspace ────────────────────────────────────────────


class TestWorkspaceEdgeCases:
    def test_create_workspace_nonexistent_base_dir(self, tmp_path: Path) -> None:
        """create_workspace creates base_dir if it does not exist."""
        base_dir = tmp_path / "does" / "not" / "exist"
        ws = create_workspace(base_dir, "sub-x", [])
        assert (ws / "raw").is_dir()
        assert (ws / "report").is_dir()

    def test_filename_with_spaces(self, base_dir: Path) -> None:
        """Filenames containing spaces are written and listed correctly."""
        files = [("my data file.xlsx", b"content")]
        ws = create_workspace(base_dir, "sub-spaces", files)
        listing = list_files(ws)
        assert len(listing) == 1
        assert listing[0]["name"] == "my data file.xlsx"
        assert listing[0]["extension"] == "xlsx"

    def test_filename_with_unicode(self, base_dir: Path) -> None:
        """Filenames with non-ASCII characters are stored and listed correctly."""
        files = [("박건윤_측정.xlsx", b"data")]
        ws = create_workspace(base_dir, "sub-unicode", files)
        listing = list_files(ws)
        assert len(listing) == 1
        assert listing[0]["name"] == "박건윤_측정.xlsx"

    def test_list_files_no_raw_dir(self, base_dir: Path) -> None:
        """list_files returns [] when the raw/ subdirectory is missing."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            fake_ws = Path(td) / "ws-no-raw"
            fake_ws.mkdir()
            # raw/ intentionally not created
            result = list_files(fake_ws)
            assert result == []

    def test_list_files_empty_raw_dir(self, base_dir: Path) -> None:
        """list_files returns [] for a workspace that received no files."""
        ws = create_workspace(base_dir, "sub-empty", [])
        result = list_files(ws)
        assert result == []

    def test_list_files_sorted_alphabetically(self, base_dir: Path) -> None:
        """list_files returns entries sorted by filename (Path.iterdir sorted)."""
        files = [("z_last.fit", b"z"), ("a_first.xlsx", b"a"), ("m_mid.fit", b"m")]
        ws = create_workspace(base_dir, "sub-sort", files)
        listing = list_files(ws)
        names = [f["name"] for f in listing]
        assert names == sorted(names)

    def test_file_overwrite_on_duplicate_name(self, base_dir: Path) -> None:
        """Writing two files with the same name results in the last content winning."""
        files = [("data.xlsx", b"first"), ("data.xlsx", b"second")]
        ws = create_workspace(base_dir, "sub-dup", files)
        content = (ws / "raw" / "data.xlsx").read_bytes()
        assert content == b"second"


# ── Edge Cases: WAL Concurrent Access ────────────────────────────────


class TestWALConcurrency:
    def test_concurrent_writes_succeed(self, db_path: Path) -> None:
        """Multiple threads writing submissions concurrently must all succeed."""
        errors: list[Exception] = []

        def worker() -> None:
            try:
                create_submission(db_path, "concurrent", [], "/ws")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent write errors: {errors}"

        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        conn.close()
        assert count == 10

    def test_concurrent_reads_do_not_block(self, db_path: Path) -> None:
        """Multiple threads reading simultaneously under WAL must not block."""
        sid = create_submission(db_path, "shared", [], "/ws")
        results: list[dict | None] = []
        lock = threading.Lock()

        def reader() -> None:
            row = get_submission(db_path, sid)
            with lock:
                results.append(row)

        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        assert all(r is not None for r in results)
        assert all(r["id"] == sid for r in results)  # type: ignore[index]


# ── Edge Cases: Schemas ──────────────────────────────────────────────


class TestSchemaEdgeCases:
    def test_submission_create_missing_description_raises(self) -> None:
        """description is required; omitting it raises ValidationError."""
        with pytest.raises(ValidationError):
            SubmissionCreate()  # type: ignore[call-arg]

    def test_job_status_invalid_literal_raises(self) -> None:
        """An invalid status literal must raise a Pydantic ValidationError."""
        with pytest.raises(ValidationError):
            JobStatus(
                id="x",
                submission_id="y",
                status="cancelled",  # not a valid Literal
                created_at="2026-03-21T00:00:00",
            )

    def test_job_status_all_valid_literals(self) -> None:
        """All four valid statuses are accepted by JobStatus."""
        for status in ("pending", "processing", "done", "failed"):
            j = JobStatus(
                id="x",
                submission_id="y",
                status=status,  # type: ignore[arg-type]
                created_at="2026-03-21T00:00:00",
            )
            assert j.status == status

    def test_submission_create_optional_fields_default(self) -> None:
        """subject_name and test_date default to empty strings."""
        s = SubmissionCreate(description="hello")
        assert s.subject_name == ""
        assert s.test_date == ""

    def test_report_summary_all_fields_required(self) -> None:
        """ReportSummary with any missing field raises ValidationError."""
        with pytest.raises(ValidationError):
            ReportSummary(slug="s", subject_name="n")  # type: ignore[call-arg]
