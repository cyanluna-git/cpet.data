"""
tests/test_api.py — API tests for server.api endpoints.

Uses FastAPI TestClient for synchronous HTTP testing.
Validates file upload, job lifecycle, validation errors, and HTMX partials.
"""

import io
import os
import threading
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from server.db import get_job, get_submission, init_db, list_jobs
from server.main import app


@pytest.fixture(autouse=True)
def _setup_app_state(tmp_path: Path) -> None:
    """Configure app.state to use temporary directories for each test."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "cpet_platform.db"
    init_db(db_path)

    app.state.db_path = db_path
    app.state.data_dir = data_dir
    app.state.channel_url = "http://127.0.0.1:9999"


@pytest.fixture()
def client() -> TestClient:
    """Provide a FastAPI TestClient."""
    return TestClient(app, raise_server_exceptions=False)


def _make_xlsx(content: bytes = b"fake-xlsx") -> tuple[str, io.BytesIO, str]:
    """Return a tuple suitable for TestClient file upload (.xlsx)."""
    return ("files", ("test.xlsx", io.BytesIO(content), "application/octet-stream"))


def _make_file(
    name: str, content: bytes = b"fake-content"
) -> tuple[str, tuple[str, io.BytesIO, str]]:
    """Return a tuple suitable for TestClient file upload (any extension)."""
    return ("files", (name, io.BytesIO(content), "application/octet-stream"))


# ── POST /api/submit ─────────────────────────────────────────────────


class TestSubmitEndpoint:
    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_success(
        self, mock_channel: AsyncMock, client: TestClient, tmp_path: Path
    ) -> None:
        """Valid xlsx upload returns 201 with job_id."""
        resp = client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "test upload", "subject_name": "Park"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "job_id" in body
        assert body["status"] == "pending"

        # Verify channel was notified
        mock_channel.assert_awaited_once()

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_creates_workspace_files(
        self, mock_channel: AsyncMock, client: TestClient, tmp_path: Path
    ) -> None:
        """Uploaded files are saved to the workspace raw/ directory."""
        resp = client.post(
            "/api/submit",
            files=[_make_xlsx(b"excel-data"), _make_file("ride.fit", b"fit-data")],
            data={"description": "multi-file"},
        )
        assert resp.status_code == 201

        # Find the workspace directory
        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        assert len(jobs) == 1
        sub = get_submission(db_path, jobs[0]["submission_id"])
        assert sub is not None
        ws = Path(sub["workspace_path"])
        assert (ws / "raw" / "test.xlsx").exists()
        assert (ws / "raw" / "ride.fit").exists()

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_creates_db_records(
        self, mock_channel: AsyncMock, client: TestClient, tmp_path: Path
    ) -> None:
        """Submit creates both a submission and a job in the database."""
        resp = client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={
                "description": "db check",
                "subject_name": "Test",
                "test_date": "2026-03-21",
            },
        )
        assert resp.status_code == 201
        body = resp.json()

        db_path = app.state.db_path
        job = get_job(db_path, body["job_id"])
        assert job is not None
        assert job["status"] == "pending"

        sub = get_submission(db_path, job["submission_id"])
        assert sub is not None
        assert sub["description"] == "db check"
        assert sub["subject_name"] == "Test"
        assert sub["test_date"] == "2026-03-21"

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_multiple_xlsx(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Multiple xlsx files are accepted."""
        resp = client.post(
            "/api/submit",
            files=[
                _make_file("cosmed.xlsx", b"cosmed"),
                _make_file("lactate.xlsx", b"lactate"),
            ],
            data={"description": "dual xlsx"},
        )
        assert resp.status_code == 201

    def test_submit_invalid_extension(self, client: TestClient) -> None:
        """Files with disallowed extensions return 400."""
        resp = client.post(
            "/api/submit",
            files=[_make_file("malware.exe", b"bad")],
            data={"description": "bad file"},
        )
        assert resp.status_code == 400
        assert "invalid file extension" in resp.json()["error"]

    def test_submit_no_xlsx(self, client: TestClient) -> None:
        """Submission without any xlsx returns 400."""
        resp = client.post(
            "/api/submit",
            files=[_make_file("ride.fit", b"fit-data")],
            data={"description": "no xlsx"},
        )
        assert resp.status_code == 400
        assert "xlsx" in resp.json()["error"].lower()

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_oversized_file(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Files exceeding MAX_FILE_SIZE return 413."""
        big_content = b"x" * (50 * 1024 * 1024 + 1)
        resp = client.post(
            "/api/submit",
            files=[_make_file("huge.xlsx", big_content)],
            data={"description": "too big"},
        )
        assert resp.status_code == 413
        assert "too large" in resp.json()["error"]

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_mixed_valid_extensions(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """All allowed extensions are accepted together."""
        resp = client.post(
            "/api/submit",
            files=[
                _make_file("data.xlsx", b"xlsx"),
                _make_file("ride.fit", b"fit"),
                _make_file("protocol.zwo", b"zwo"),
                _make_file("notes.md", b"md"),
                _make_file("lactate.csv", b"csv"),
            ],
            data={"description": "all types"},
        )
        assert resp.status_code == 201


# ── GET /api/jobs ────────────────────────────────────────────────────


class TestJobsListEndpoint:
    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_list_jobs_empty(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Empty database returns an empty list."""
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_list_jobs_after_submit(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """After a submission, the job appears in the list."""
        client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "list test"},
        )
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        jobs = resp.json()
        assert len(jobs) == 1
        assert jobs[0]["status"] == "pending"

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_list_jobs_status_filter(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Status query parameter filters results."""
        client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "filter test"},
        )
        resp = client.get("/api/jobs?status=processing")
        assert resp.status_code == 200
        assert resp.json() == []

        resp = client.get("/api/jobs?status=pending")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ── GET /api/jobs/{job_id} ───────────────────────────────────────────


class TestJobDetailEndpoint:
    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_get_job_found(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Existing job returns 200 with job data."""
        resp = client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "detail test"},
        )
        job_id = resp.json()["job_id"]

        resp = client.get(f"/api/jobs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == job_id
        assert body["status"] == "pending"

    def test_get_job_not_found(self, client: TestClient) -> None:
        """Missing job returns 404."""
        resp = client.get("/api/jobs/nonexistent-id")
        assert resp.status_code == 404
        assert "not found" in resp.json()["error"]


# ── GET /api/jobs/partial ────────────────────────────────────────────


class TestJobsPartialEndpoint:
    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_partial_returns_html(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Partial endpoint returns text/html content."""
        client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={
                "description": "partial test",
                "subject_name": "Park",
                "test_date": "2026-03-21",
            },
        )
        resp = client.get("/api/jobs/partial")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Park" in resp.text
        assert "2026-03-21" in resp.text

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_partial_empty(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Empty job list renders the Korean empty state message."""
        resp = client.get("/api/jobs/partial")
        assert resp.status_code == 200
        assert "아직 제출된 분석이 없습니다" in resp.text

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_partial_with_status_filter(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Partial endpoint respects status query parameter."""
        client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "filter partial"},
        )
        resp = client.get("/api/jobs/partial?status=done")
        assert resp.status_code == 200
        assert "아직 제출된 분석이 없습니다" in resp.text


# ── Channel dispatch ─────────────────────────────────────────────────


class TestChannelDispatch:
    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_channel_payload_contains_job_id(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Channel notification includes job_id and submission_id."""
        resp = client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "channel test"},
        )
        body = resp.json()
        mock_channel.assert_awaited_once()
        call_args = mock_channel.call_args
        payload = call_args[0][1]
        assert payload["job_id"] == body["job_id"]
        assert "submission_id" in payload
        assert "workspace_path" in payload

    def test_channel_unreachable_still_returns_201(
        self, client: TestClient
    ) -> None:
        """When channel server is down, submit still succeeds."""
        # Default channel_url points to 127.0.0.1:9999 which is not running
        resp = client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "offline channel"},
        )
        assert resp.status_code == 201


# ── Empty description & optional fields ──────────────────────────────


class TestOptionalFields:
    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_empty_description(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Empty description string is stored as empty string, not None."""
        resp = client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": ""},
        )
        assert resp.status_code == 201
        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        sub = get_submission(db_path, jobs[0]["submission_id"])
        assert sub is not None
        assert sub["description"] == ""

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_omit_all_optional_fields(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Submission with only required xlsx file and no metadata succeeds."""
        resp = client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={},
        )
        assert resp.status_code == 201
        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        sub = get_submission(db_path, jobs[0]["submission_id"])
        assert sub is not None
        assert sub["description"] == ""
        assert sub["subject_name"] == ""
        assert sub["test_date"] == ""

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_whitespace_only_description(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Whitespace-only description is accepted and stored as-is."""
        resp = client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "   "},
        )
        assert resp.status_code == 201
        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        sub = get_submission(db_path, jobs[0]["submission_id"])
        assert sub is not None
        assert sub["description"] == "   "


# ── Boundary file sizes ───────────────────────────────────────────────


class TestFileSizeBoundaries:
    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_exact_max_size(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """File at exactly MAX_FILE_SIZE (50 MB) is accepted."""
        exact_content = b"x" * (50 * 1024 * 1024)
        resp = client.post(
            "/api/submit",
            files=[_make_file("exact.xlsx", exact_content)],
            data={"description": "exact limit"},
        )
        assert resp.status_code == 201

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_one_byte_over_max(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """File one byte over MAX_FILE_SIZE returns 413."""
        over_content = b"x" * (50 * 1024 * 1024 + 1)
        resp = client.post(
            "/api/submit",
            files=[_make_file("over.xlsx", over_content)],
            data={"description": "one over"},
        )
        assert resp.status_code == 413

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_zero_byte_file(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Zero-byte xlsx file is accepted (empty upload is valid)."""
        resp = client.post(
            "/api/submit",
            files=[_make_file("empty.xlsx", b"")],
            data={"description": "zero bytes"},
        )
        assert resp.status_code == 201
        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        sub = get_submission(db_path, jobs[0]["submission_id"])
        ws = Path(sub["workspace_path"])
        assert (ws / "raw" / "empty.xlsx").exists()
        assert (ws / "raw" / "empty.xlsx").stat().st_size == 0


# ── Multiple xlsx files ───────────────────────────────────────────────


class TestMultipleXlsxFiles:
    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_three_xlsx_files(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Three xlsx files are all saved to workspace raw/."""
        resp = client.post(
            "/api/submit",
            files=[
                _make_file("cosmed.xlsx", b"cosmed"),
                _make_file("lactate.xlsx", b"lactate"),
                _make_file("protocol.xlsx", b"protocol"),
            ],
            data={"description": "three xlsx"},
        )
        assert resp.status_code == 201
        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        sub = get_submission(db_path, jobs[0]["submission_id"])
        ws = Path(sub["workspace_path"])
        assert (ws / "raw" / "cosmed.xlsx").exists()
        assert (ws / "raw" / "lactate.xlsx").exists()
        assert (ws / "raw" / "protocol.xlsx").exists()

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_submit_manifest_lists_all_xlsx(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """File manifest records all uploaded xlsx files with correct metadata."""
        resp = client.post(
            "/api/submit",
            files=[
                _make_file("cosmed.xlsx", b"c" * 100),
                _make_file("lactate.xlsx", b"l" * 200),
            ],
            data={"description": "manifest check"},
        )
        assert resp.status_code == 201
        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        sub = get_submission(db_path, jobs[0]["submission_id"])
        manifest = sub["file_manifest"]
        names = {f["name"] for f in manifest}
        assert "cosmed.xlsx" in names
        assert "lactate.xlsx" in names
        cosmed = next(f for f in manifest if f["name"] == "cosmed.xlsx")
        lactate = next(f for f in manifest if f["name"] == "lactate.xlsx")
        assert cosmed["size_bytes"] == 100
        assert lactate["size_bytes"] == 200


# ── Partial HTML content validation ──────────────────────────────────


class TestPartialHtmlContent:
    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_partial_renders_job_id_prefix(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Job list partial renders first 8 chars of job ID."""
        resp = client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "id prefix test"},
        )
        job_id = resp.json()["job_id"]

        html = client.get("/api/jobs/partial").text
        assert job_id[:8] in html

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_partial_renders_pending_status(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Newly submitted job shows 'pending' status in partial HTML."""
        client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "status render"},
        )
        html = client.get("/api/jobs/partial").text
        assert "pending" in html

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_partial_no_jobs_shows_empty_message(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Empty job list renders the Korean empty state message."""
        html = client.get("/api/jobs/partial").text
        assert "아직 제출된 분석이 없습니다" in html

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_partial_job_row_has_data_status_attribute(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Each job row has data-status attribute matching the job status."""
        client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "data-status test"},
        )
        html = client.get("/api/jobs/partial").text
        assert 'data-status="pending"' in html

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_partial_missing_subject_shows_dash(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """When subject_name is empty, partial renders em-dash placeholder."""
        client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "no subject"},
            # subject_name intentionally omitted
        )
        html = client.get("/api/jobs/partial").text
        assert "—" in html  # Jinja2 renders '—' for falsy subject_name

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_partial_multiple_jobs_all_rendered(
        self, mock_channel: AsyncMock, client: TestClient
    ) -> None:
        """Multiple jobs are each rendered as separate job-row divs."""
        for name in ("Alpha", "Beta", "Gamma"):
            client.post(
                "/api/submit",
                files=[_make_xlsx()],
                data={"description": f"job {name}", "subject_name": name},
            )
        html = client.get("/api/jobs/partial").text
        assert html.count("job-row") == 3
        assert "Alpha" in html
        assert "Beta" in html
        assert "Gamma" in html


# ── Concurrent uploads ────────────────────────────────────────────────


class TestConcurrentUploads:
    def test_concurrent_submits_all_succeed(self, client: TestClient) -> None:
        """Multiple concurrent uploads each get a distinct job_id."""
        results: list[dict] = []
        errors: list[Exception] = []

        def do_submit(description: str) -> None:
            try:
                resp = client.post(
                    "/api/submit",
                    files=[_make_xlsx()],
                    data={"description": description},
                )
                results.append(resp.json())
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=do_submit, args=(f"concurrent-{i}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 5
        # All must succeed
        for r in results:
            assert r.get("status") == "pending", f"unexpected result: {r}"
        # All job IDs must be unique
        job_ids = [r["job_id"] for r in results]
        assert len(set(job_ids)) == 5, "Duplicate job IDs detected"

    def test_concurrent_submits_create_separate_workspaces(
        self, client: TestClient
    ) -> None:
        """Concurrent submissions do not share workspaces."""
        workspace_paths: list[str] = []
        lock = threading.Lock()

        def do_submit(idx: int) -> None:
            resp = client.post(
                "/api/submit",
                files=[_make_xlsx()],
                data={"description": f"workspace-{idx}"},
            )
            if resp.status_code == 201:
                db_path = app.state.db_path
                jobs = list_jobs(db_path)
                # Find the matching job
                job_id = resp.json()["job_id"]
                from server.db import get_submission
                job = next(
                    (j for j in jobs if j["id"] == job_id), None
                )
                if job:
                    sub = get_submission(db_path, job["submission_id"])
                    if sub:
                        with lock:
                            workspace_paths.append(sub["workspace_path"])

        threads = [
            threading.Thread(target=do_submit, args=(i,))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(workspace_paths) == 4
        assert len(set(workspace_paths)) == 4, "Workspaces are not unique"


# ── Page routes ──────────────────────────────────────────────────────


class TestPageRoutes:
    def test_root_redirects_to_upload(self, client: TestClient) -> None:
        """GET / redirects to /upload."""
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 307
        assert resp.headers["location"] == "/upload"

    def test_upload_page_renders(self, client: TestClient) -> None:
        """GET /upload returns 200 with HTML containing the upload form."""
        resp = client.get("/upload")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "업로드" in resp.text
        assert 'hx-post="/api/submit"' in resp.text

    def test_dashboard_page_renders(self, client: TestClient) -> None:
        """GET /dashboard returns 200 with HTML containing the dashboard table."""
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "대시보드" in resp.text
        assert 'hx-get="/api/jobs/partial"' in resp.text


# ── Security: path traversal ──────────────────────────────────────────


class TestPathTraversalPrevention:
    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_traversal_filename_written_to_raw_only(
        self, mock_channel: AsyncMock, client: TestClient, tmp_path: Path
    ) -> None:
        """A filename with directory traversal components is stripped to basename."""
        resp = client.post(
            "/api/submit",
            files=[_make_file("../../etc/passwd.xlsx", b"malicious")],
            data={"description": "traversal attempt"},
        )
        assert resp.status_code == 201
        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        sub = get_submission(db_path, jobs[0]["submission_id"])
        assert sub is not None
        ws = Path(sub["workspace_path"])
        raw = ws / "raw"
        # File must be inside raw/ — traversal path resolved to basename only
        saved = list(raw.iterdir())
        assert len(saved) == 1
        assert saved[0].parent == raw, "file escaped raw/ directory"
        assert saved[0].name == "passwd.xlsx"

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_absolute_path_filename_written_to_raw_only(
        self, mock_channel: AsyncMock, client: TestClient, tmp_path: Path
    ) -> None:
        """A filename that is an absolute path is stripped to basename."""
        resp = client.post(
            "/api/submit",
            files=[_make_file("/etc/cron.d/evil.xlsx", b"evil")],
            data={"description": "absolute path attempt"},
        )
        assert resp.status_code == 201
        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        sub = get_submission(db_path, jobs[0]["submission_id"])
        assert sub is not None
        ws = Path(sub["workspace_path"])
        raw = ws / "raw"
        saved = list(raw.iterdir())
        assert len(saved) == 1
        assert saved[0].parent == raw, "file escaped raw/ directory"
        assert saved[0].name == "evil.xlsx"
