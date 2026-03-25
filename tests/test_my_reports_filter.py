"""
tests/test_my_reports_filter.py — Tests for My Reports filter on the dashboard.

Covers:
    - list_jobs_by_user DB function
    - /api/jobs/partial?filter=mine endpoint
    - "내 리포트" badge rendering in job_list.html
    - Filter tabs visibility (logged-in vs anonymous)
"""

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from server.db import (
    complete_onboarding,
    create_job,
    create_submission,
    init_db,
    list_jobs,
    list_jobs_by_user,
    upsert_user,
)
from server.main import app


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path, initialized."""
    path = tmp_path / "test_filter.db"
    init_db(path)
    return path


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
    app.state.published_dir = tmp_path / "published"


@pytest.fixture()
def client() -> TestClient:
    """Provide a FastAPI TestClient."""
    return TestClient(app, raise_server_exceptions=False)


def _make_xlsx(content: bytes = b"fake-xlsx") -> tuple[str, tuple[str, io.BytesIO, str]]:
    """Return a tuple suitable for TestClient file upload (.xlsx)."""
    return ("files", ("test.xlsx", io.BytesIO(content), "application/octet-stream"))


def _login_user(
    client: TestClient,
    google_id: str = "test-gid",
    email: str = "test@example.com",
    name: str = "Test User",
) -> None:
    """Simulate Google OAuth login for a user with onboarding completed."""
    db_path = app.state.db_path
    user = upsert_user(db_path, google_id=google_id, email=email, display_name=name)
    complete_onboarding(db_path, user["id"], name)

    with patch(
        "server.auth.oauth.google.authorize_access_token",
        new_callable=AsyncMock,
    ) as mock_token:
        mock_token.return_value = {
            "userinfo": {
                "sub": google_id,
                "email": email,
                "name": name,
                "picture": "",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)


# ── DB: list_jobs_by_user ──────────────────────────────────────────


class TestListJobsByUser:
    def test_returns_only_user_jobs(self, db_path: Path) -> None:
        """list_jobs_by_user returns only jobs whose submission matches user_id."""
        user_a = upsert_user(db_path, "gid-a", "a@test.com", "User A")
        user_b = upsert_user(db_path, "gid-b", "b@test.com", "User B")

        sub_a = create_submission(
            db_path, "desc-a", [], "/ws/a",
            subject_name="Subject A", user_id=user_a["id"],
        )
        sub_b = create_submission(
            db_path, "desc-b", [], "/ws/b",
            subject_name="Subject B", user_id=user_b["id"],
        )
        job_a = create_job(db_path, sub_a)
        job_b = create_job(db_path, sub_b)

        jobs_a = list_jobs_by_user(db_path, user_a["id"])
        assert len(jobs_a) == 1
        assert jobs_a[0]["id"] == job_a

        jobs_b = list_jobs_by_user(db_path, user_b["id"])
        assert len(jobs_b) == 1
        assert jobs_b[0]["id"] == job_b

    def test_excludes_anonymous_submissions(self, db_path: Path) -> None:
        """list_jobs_by_user does not return anonymous (user_id=NULL) jobs."""
        user = upsert_user(db_path, "gid-x", "x@test.com", "User X")

        sub_anon = create_submission(
            db_path, "anon", [], "/ws/anon", user_id=None,
        )
        sub_user = create_submission(
            db_path, "mine", [], "/ws/mine", user_id=user["id"],
        )
        create_job(db_path, sub_anon)
        create_job(db_path, sub_user)

        jobs = list_jobs_by_user(db_path, user["id"])
        assert len(jobs) == 1

    def test_returns_empty_for_unknown_user(self, db_path: Path) -> None:
        """list_jobs_by_user returns empty list for a user with no submissions."""
        jobs = list_jobs_by_user(db_path, "nonexistent-user-id")
        assert jobs == []

    def test_filters_by_status(self, db_path: Path) -> None:
        """list_jobs_by_user respects the status filter."""
        from server.db import update_job_status

        user = upsert_user(db_path, "gid-s", "s@test.com", "User S")
        sub = create_submission(
            db_path, "desc", [], "/ws/s", user_id=user["id"],
        )
        job_id = create_job(db_path, sub)
        update_job_status(db_path, job_id, "done")

        assert len(list_jobs_by_user(db_path, user["id"], status="done")) == 1
        assert len(list_jobs_by_user(db_path, user["id"], status="pending")) == 0


# ── API: /api/jobs/partial?filter=mine ─────────────────────────────


class TestJobsPartialFilterMine:
    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_filter_mine_shows_only_user_submissions(
        self, mock_channel: AsyncMock, client: TestClient,
    ) -> None:
        """filter=mine returns only jobs submitted by the logged-in user."""
        _login_user(client, google_id="filter-gid", email="filter@test.com", name="Filter User")

        # Submit a job as logged-in user
        client.post(
            "/api/submit",
            files=[_make_xlsx(b"user-xlsx")],
            data={"description": "my upload", "subject_name": "MySub"},
        )

        # Submit another job anonymously (new client without session)
        anon_client = TestClient(app, raise_server_exceptions=False)
        anon_client.post(
            "/api/submit",
            files=[_make_xlsx(b"anon-xlsx")],
            data={"description": "anon upload", "subject_name": "AnonSub"},
        )

        # Verify "all" has both
        all_resp = client.get("/api/jobs/partial")
        assert all_resp.status_code == 200
        assert "MySub" in all_resp.text
        assert "AnonSub" in all_resp.text

        # Verify filter=mine has only the user's job
        mine_resp = client.get("/api/jobs/partial?filter=mine")
        assert mine_resp.status_code == 200
        assert "MySub" in mine_resp.text
        assert "AnonSub" not in mine_resp.text

    def test_filter_mine_anonymous_shows_all(self, client: TestClient) -> None:
        """Anonymous user with filter=mine gets all jobs (filter is ignored)."""
        db_path = app.state.db_path
        sub = create_submission(
            db_path, "test", [{"name": "f.xlsx"}], "/ws/test",
            subject_name="TestSub",
        )
        create_job(db_path, sub)

        resp = client.get("/api/jobs/partial?filter=mine")
        assert resp.status_code == 200
        assert "TestSub" in resp.text

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_filter_mine_empty_when_no_user_submissions(
        self, mock_channel: AsyncMock, client: TestClient,
    ) -> None:
        """filter=mine returns empty message when user has no submissions."""
        _login_user(client, google_id="empty-gid", email="empty@test.com")

        # Submit anonymously
        anon_client = TestClient(app, raise_server_exceptions=False)
        anon_client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "anon"},
        )

        resp = client.get("/api/jobs/partial?filter=mine")
        assert resp.status_code == 200
        assert "아직 제출된 분석이 없습니다" in resp.text


# ── Badge: 내 리포트 ───────────────────────────────────────────────


class TestMyReportBadge:
    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_badge_shown_for_own_submission(
        self, mock_channel: AsyncMock, client: TestClient,
    ) -> None:
        """Logged-in user sees '내 리포트' badge on their own submissions."""
        _login_user(client, google_id="badge-gid", email="badge@test.com")

        client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "badge test", "subject_name": "BadgeSub"},
        )

        resp = client.get("/api/jobs/partial")
        assert resp.status_code == 200
        assert "내 리포트" in resp.text

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_badge_not_shown_for_others_submission(
        self, mock_channel: AsyncMock, client: TestClient,
    ) -> None:
        """Logged-in user does NOT see badge on other users' submissions."""
        # User A submits
        _login_user(client, google_id="user-a-gid", email="a@test.com", name="UserA")
        client.post(
            "/api/submit",
            files=[_make_xlsx(b"a-data")],
            data={"description": "a upload", "subject_name": "SubA"},
        )

        # User B logs in and checks the dashboard
        client_b = TestClient(app, raise_server_exceptions=False)
        _login_user(client_b, google_id="user-b-gid", email="b@test.com", name="UserB")

        resp = client_b.get("/api/jobs/partial")
        assert resp.status_code == 200
        assert "SubA" in resp.text
        # Badge should NOT appear for User B on User A's submission
        assert "내 리포트" not in resp.text

    def test_badge_not_shown_for_anonymous(self, client: TestClient) -> None:
        """Anonymous users never see the '내 리포트' badge."""
        db_path = app.state.db_path
        user = upsert_user(db_path, "anon-badge-gid", "anon@test.com")
        sub = create_submission(
            db_path, "test", [{"name": "f.xlsx"}], "/ws/test",
            subject_name="AnonBadgeSub", user_id=user["id"],
        )
        create_job(db_path, sub)

        resp = client.get("/api/jobs/partial")
        assert resp.status_code == 200
        assert "AnonBadgeSub" in resp.text
        assert "내 리포트" not in resp.text


# ── Dashboard: filter tabs visibility ──────────────────────────────


class TestFilterTabsVisibility:
    def test_anonymous_does_not_see_filter_tabs(self, client: TestClient) -> None:
        """Anonymous visitors do not see the filter tab buttons."""
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "filter-tabs" not in resp.text
        assert "My Reports" not in resp.text

    def test_logged_in_sees_filter_tabs(self, client: TestClient) -> None:
        """Logged-in users see the All / My Reports filter tabs."""
        _login_user(client, google_id="tabs-gid", email="tabs@test.com")

        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "filter-tabs" in resp.text
        assert "My Reports" in resp.text
        assert "All" in resp.text
