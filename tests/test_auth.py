"""
tests/test_auth.py — Tests for Google OAuth, session auth, and user CRUD.

Covers:
    - users table schema and CRUD operations
    - Google OAuth login/callback/logout routes
    - Session-based user injection into templates
    - user_id recording on submissions
    - Anonymous (non-logged-in) upload backward compatibility
"""

import io
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from server.db import (
    _connect,
    complete_onboarding,
    create_submission,
    get_submission,
    get_user,
    get_user_by_google_id,
    init_db,
    list_jobs,
    upsert_user,
)
from server.main import app


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path, initialized."""
    path = tmp_path / "test_auth.db"
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


# ── Users Table Schema ──────────────────────────────────────────────


class TestUsersTableSchema:
    def test_users_table_exists(self, db_path: Path) -> None:
        """init_db creates the users table."""
        conn = sqlite3.connect(str(db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchall()
        conn.close()
        assert len(tables) == 1

    def test_users_table_columns(self, db_path: Path) -> None:
        """users table has all required columns."""
        conn = sqlite3.connect(str(db_path))
        columns = conn.execute("PRAGMA table_info(users)").fetchall()
        conn.close()
        col_names = {c[1] for c in columns}
        expected = {
            "id", "google_id", "email", "display_name",
            "avatar_url", "role", "created_at", "last_login_at",
        }
        assert expected.issubset(col_names)

    def test_submissions_has_user_id_column(self, db_path: Path) -> None:
        """submissions table includes the user_id column."""
        conn = sqlite3.connect(str(db_path))
        columns = conn.execute("PRAGMA table_info(submissions)").fetchall()
        conn.close()
        col_names = {c[1] for c in columns}
        assert "user_id" in col_names


# ── User CRUD ───────────────────────────────────────────────────────


class TestUserCRUD:
    def test_upsert_creates_new_user(self, db_path: Path) -> None:
        """First login creates a new user with role='user'."""
        user = upsert_user(
            db_path,
            google_id="google-123",
            email="test@example.com",
            display_name="Test User",
            avatar_url="https://example.com/avatar.jpg",
        )
        assert user["google_id"] == "google-123"
        assert user["email"] == "test@example.com"
        assert user["display_name"] == "Test User"
        assert user["avatar_url"] == "https://example.com/avatar.jpg"
        assert user["role"] == "user"
        assert user["created_at"] is not None
        assert user["last_login_at"] is not None
        assert len(user["id"]) == 36  # UUID

    def test_upsert_updates_returning_user(self, db_path: Path) -> None:
        """Subsequent logins update last_login_at and profile info."""
        user1 = upsert_user(
            db_path,
            google_id="google-456",
            email="old@example.com",
            display_name="Old Name",
        )
        user2 = upsert_user(
            db_path,
            google_id="google-456",
            email="new@example.com",
            display_name="New Name",
            avatar_url="https://example.com/new-avatar.jpg",
        )
        # Same user ID
        assert user2["id"] == user1["id"]
        # Updated fields
        assert user2["email"] == "new@example.com"
        assert user2["display_name"] == "New Name"
        assert user2["avatar_url"] == "https://example.com/new-avatar.jpg"
        # last_login_at should be updated
        assert user2["last_login_at"] >= user1["last_login_at"]

    def test_upsert_preserves_role(self, db_path: Path) -> None:
        """upsert does not change the user's role."""
        user = upsert_user(
            db_path,
            google_id="google-role-test",
            email="role@example.com",
        )
        assert user["role"] == "user"
        # Manually change role to admin
        conn = _connect(db_path)
        conn.execute(
            "UPDATE users SET role = 'admin' WHERE id = ?", (user["id"],)
        )
        conn.commit()
        conn.close()
        # Re-upsert should not reset role
        user2 = upsert_user(
            db_path,
            google_id="google-role-test",
            email="role@example.com",
        )
        assert user2["role"] == "admin"

    def test_get_user_found(self, db_path: Path) -> None:
        """get_user returns the user dict for a valid ID."""
        created = upsert_user(
            db_path, google_id="g1", email="u1@example.com",
        )
        found = get_user(db_path, created["id"])
        assert found is not None
        assert found["id"] == created["id"]
        assert found["email"] == "u1@example.com"

    def test_get_user_not_found(self, db_path: Path) -> None:
        """get_user returns None for a nonexistent ID."""
        assert get_user(db_path, "nonexistent") is None

    def test_get_user_by_google_id(self, db_path: Path) -> None:
        """get_user_by_google_id looks up by Google sub claim."""
        upsert_user(db_path, google_id="gid-abc", email="abc@example.com")
        found = get_user_by_google_id(db_path, "gid-abc")
        assert found is not None
        assert found["email"] == "abc@example.com"

    def test_get_user_by_google_id_not_found(self, db_path: Path) -> None:
        assert get_user_by_google_id(db_path, "no-such-gid") is None

    def test_google_id_unique_constraint(self, db_path: Path) -> None:
        """Two users cannot share the same google_id."""
        upsert_user(db_path, google_id="unique-gid", email="a@example.com")
        # Direct insert with same google_id should fail
        conn = _connect(db_path)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users (id, google_id, email) VALUES (?, ?, ?)",
                ("new-id", "unique-gid", "b@example.com"),
            )
        conn.close()

    def test_email_unique_constraint(self, db_path: Path) -> None:
        """Two users cannot share the same email."""
        upsert_user(db_path, google_id="gid-1", email="shared@example.com")
        conn = _connect(db_path)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users (id, google_id, email) VALUES (?, ?, ?)",
                ("new-id", "gid-2", "shared@example.com"),
            )
        conn.close()


# ── Submission with user_id ─────────────────────────────────────────


class TestSubmissionUserId:
    def test_submission_with_user_id(self, db_path: Path) -> None:
        """Submissions can record the user_id of the uploader."""
        user = upsert_user(
            db_path, google_id="g-sub", email="sub@example.com",
        )
        sid = create_submission(
            db_path, "test", [], "/ws",
            user_id=user["id"],
        )
        sub = get_submission(db_path, sid)
        assert sub is not None
        assert sub["user_id"] == user["id"]

    def test_submission_without_user_id(self, db_path: Path) -> None:
        """Submissions without user_id default to NULL (anonymous)."""
        sid = create_submission(db_path, "anonymous", [], "/ws")
        sub = get_submission(db_path, sid)
        assert sub is not None
        assert sub["user_id"] is None

    def test_existing_submissions_still_work(self, db_path: Path) -> None:
        """Backward compat: existing submissions with no user_id column value still load."""
        sid = create_submission(db_path, "old upload", [], "/ws")
        sub = get_submission(db_path, sid)
        assert sub is not None
        assert sub["user_id"] is None


# ── Migration ───────────────────────────────────────────────────────


class TestMigration:
    def test_migration_adds_user_id_to_old_db(self, tmp_path: Path) -> None:
        """Running init_db on a pre-migration DB adds user_id column."""
        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(str(db_path))
        # Create old schema without users table or user_id column
        conn.executescript("""
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
        """)
        conn.close()

        # Run init_db which should add users table + migrate submissions
        init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        columns = conn.execute("PRAGMA table_info(submissions)").fetchall()
        col_names = {c[1] for c in columns}
        assert "user_id" in col_names

        # users table should exist
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchall()
        assert len(tables) == 1
        conn.close()


# ── Auth Routes ─────────────────────────────────────────────────────


class TestAuthRoutes:
    def test_google_login_redirects(self, client: TestClient) -> None:
        """GET /auth/google/login redirects to Google's consent screen."""
        resp = client.get("/auth/google/login", follow_redirects=False)
        # Should redirect (302) to Google
        assert resp.status_code in (302, 303)
        location = resp.headers.get("location", "")
        assert "accounts.google.com" in location or "google" in location.lower()

    def test_logout_clears_session(self, client: TestClient) -> None:
        """GET /auth/logout clears session and redirects to landing page."""
        # First simulate a session by setting cookies
        resp = client.get("/auth/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    @patch("server.auth.oauth.google.authorize_access_token", new_callable=AsyncMock)
    def test_callback_creates_user_and_sets_session(
        self, mock_token: AsyncMock, client: TestClient,
    ) -> None:
        """Successful OAuth callback creates user and sets session.

        New users are redirected to /onboarding (not /dashboard).
        """
        mock_token.return_value = {
            "userinfo": {
                "sub": "google-id-999",
                "email": "callback@example.com",
                "name": "Callback User",
                "picture": "https://example.com/pic.jpg",
            }
        }
        resp = client.get("/auth/google/callback", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/onboarding"

        # Verify user was created in DB
        db_path = app.state.db_path
        user = get_user_by_google_id(db_path, "google-id-999")
        assert user is not None
        assert user["email"] == "callback@example.com"
        assert user["display_name"] == "Callback User"

    @patch("server.auth.oauth.google.authorize_access_token", new_callable=AsyncMock)
    def test_callback_missing_userinfo_redirects_home(
        self, mock_token: AsyncMock, client: TestClient,
    ) -> None:
        """Callback with no userinfo redirects to landing page."""
        mock_token.return_value = {}
        resp = client.get("/auth/google/callback", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    @patch("server.auth.oauth.google.authorize_access_token", new_callable=AsyncMock)
    def test_callback_missing_sub_redirects_home(
        self, mock_token: AsyncMock, client: TestClient,
    ) -> None:
        """Callback with empty sub redirects to landing page."""
        mock_token.return_value = {
            "userinfo": {"sub": "", "email": ""}
        }
        resp = client.get("/auth/google/callback", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"


# ── Template Navigation ─────────────────────────────────────────────


class TestTemplateNavigation:
    def test_anonymous_sees_login_button(self, client: TestClient) -> None:
        """Anonymous visitors see '로그인' in the navigation."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "로그인" in resp.text
        assert "로그아웃" not in resp.text

    @patch("server.auth.oauth.google.authorize_access_token", new_callable=AsyncMock)
    def test_logged_in_sees_user_info(
        self, mock_token: AsyncMock, client: TestClient,
    ) -> None:
        """Logged-in users (with onboarding complete) see their name and logout link."""
        # Pre-create user with onboarding completed
        db_path = app.state.db_path
        user = upsert_user(
            db_path, google_id="nav-test-gid", email="nav@example.com",
            display_name="Nav User",
        )
        complete_onboarding(db_path, user["id"], "Nav User")

        # Simulate login (returning user)
        mock_token.return_value = {
            "userinfo": {
                "sub": "nav-test-gid",
                "email": "nav@example.com",
                "name": "Nav User",
                "picture": "https://example.com/nav.jpg",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)

        # Now visit a page - session should persist
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Nav User" in resp.text
        assert "로그아웃" in resp.text

    @patch("server.auth.oauth.google.authorize_access_token", new_callable=AsyncMock)
    def test_logout_then_sees_login_button(
        self, mock_token: AsyncMock, client: TestClient,
    ) -> None:
        """After logout, the login button reappears."""
        # Login
        mock_token.return_value = {
            "userinfo": {
                "sub": "logout-test-gid",
                "email": "logout@example.com",
                "name": "Logout User",
                "picture": "",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)

        # Logout
        client.get("/auth/logout", follow_redirects=False)

        # Check nav
        resp = client.get("/")
        assert "로그인" in resp.text
        assert "Logout User" not in resp.text


# ── Submission user_id from Session ─────────────────────────────────


class TestSubmissionSessionUserId:
    @patch("server.api.notify_channel", new_callable=AsyncMock)
    @patch("server.auth.oauth.google.authorize_access_token", new_callable=AsyncMock)
    def test_logged_in_submit_records_user_id(
        self,
        mock_token: AsyncMock,
        mock_channel: AsyncMock,
        client: TestClient,
    ) -> None:
        """Submission by a logged-in user records user_id."""
        mock_token.return_value = {
            "userinfo": {
                "sub": "submit-gid",
                "email": "submit@example.com",
                "name": "Submit User",
                "picture": "",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)

        resp = client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "logged-in upload"},
        )
        assert resp.status_code == 201

        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        sub = get_submission(db_path, jobs[0]["submission_id"])
        assert sub is not None
        assert sub["user_id"] is not None
        # Verify it matches the logged-in user
        user = get_user_by_google_id(db_path, "submit-gid")
        assert sub["user_id"] == user["id"]

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_anonymous_submit_has_null_user_id(
        self, mock_channel: AsyncMock, client: TestClient,
    ) -> None:
        """Anonymous uploads have user_id=NULL (backward compat)."""
        resp = client.post(
            "/api/submit",
            files=[_make_xlsx()],
            data={"description": "anonymous upload"},
        )
        assert resp.status_code == 201

        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        sub = get_submission(db_path, jobs[0]["submission_id"])
        assert sub is not None
        assert sub["user_id"] is None
