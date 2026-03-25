"""
tests/test_onboarding.py — Tests for the onboarding flow.

Covers:
    - onboarding_completed column in users table
    - Migration adds onboarding_completed to existing DBs
    - complete_onboarding DB function
    - upsert_user returns is_new flag
    - OAuth callback redirects: new user → /onboarding, returning → /dashboard
    - Onboarding guard middleware redirects
    - GET /onboarding page rendering
    - POST /onboarding form validation and submission
    - base.html nav hidden during onboarding
"""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from server.db import (
    _connect,
    complete_onboarding,
    get_user,
    get_user_by_google_id,
    get_user_profile,
    init_db,
    upsert_user,
)
from server.main import app


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path, initialized."""
    path = tmp_path / "test_onboarding.db"
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


def _login_new_user(
    client: TestClient,
    google_id: str = "onboard-gid",
    email: str = "onboard@example.com",
    name: str = "Onboard User",
) -> None:
    """Simulate a first-time Google OAuth login (new user)."""
    with patch(
        "server.auth.oauth.google.authorize_access_token",
        new_callable=AsyncMock,
    ) as mock_token:
        mock_token.return_value = {
            "userinfo": {
                "sub": google_id,
                "email": email,
                "name": name,
                "picture": "https://example.com/pic.jpg",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)


def _login_returning_user(
    client: TestClient,
    google_id: str = "returning-gid",
    email: str = "returning@example.com",
    name: str = "Returning User",
) -> None:
    """Simulate login for a user who has already completed onboarding."""
    db_path = app.state.db_path
    # Create the user and mark onboarding as complete
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


# ── Schema Tests ─────────────────────────────────────────────────────


class TestOnboardingSchema:
    def test_users_table_has_onboarding_column(self, db_path: Path) -> None:
        """users table includes onboarding_completed column."""
        conn = sqlite3.connect(str(db_path))
        columns = conn.execute("PRAGMA table_info(users)").fetchall()
        conn.close()
        col_names = {c[1] for c in columns}
        assert "onboarding_completed" in col_names

    def test_onboarding_default_is_zero(self, db_path: Path) -> None:
        """New users default to onboarding_completed=0."""
        user = upsert_user(db_path, google_id="schema-gid", email="schema@test.com")
        assert user["onboarding_completed"] == 0

    def test_migration_adds_onboarding_to_old_db(self, tmp_path: Path) -> None:
        """Running init_db on a pre-migration DB adds onboarding_completed."""
        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(str(db_path))
        # Create old schema without onboarding_completed
        conn.executescript("""
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
        """)
        conn.close()

        init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        columns = conn.execute("PRAGMA table_info(users)").fetchall()
        col_names = {c[1] for c in columns}
        assert "onboarding_completed" in col_names
        conn.close()


# ── DB Function Tests ────────────────────────────────────────────────


class TestOnboardingDB:
    def test_upsert_user_returns_is_new_true(self, db_path: Path) -> None:
        """upsert_user returns is_new=True for first-time users."""
        user = upsert_user(db_path, google_id="new-gid", email="new@test.com")
        assert user["is_new"] is True

    def test_upsert_user_returns_is_new_false(self, db_path: Path) -> None:
        """upsert_user returns is_new=False for returning users."""
        upsert_user(db_path, google_id="ret-gid", email="ret@test.com")
        user2 = upsert_user(db_path, google_id="ret-gid", email="ret@test.com")
        assert user2["is_new"] is False

    def test_complete_onboarding(self, db_path: Path) -> None:
        """complete_onboarding sets onboarding_completed=1 and updates display_name."""
        user = upsert_user(db_path, google_id="comp-gid", email="comp@test.com")
        assert user["onboarding_completed"] == 0

        complete_onboarding(db_path, user["id"], "Korean Name")
        updated = get_user(db_path, user["id"])
        assert updated is not None
        assert updated["onboarding_completed"] == 1
        assert updated["display_name"] == "Korean Name"


# ── Auth Callback Redirect Tests ─────────────────────────────────────


class TestAuthCallbackOnboarding:
    @patch("server.auth.oauth.google.authorize_access_token", new_callable=AsyncMock)
    def test_new_user_redirects_to_onboarding(
        self, mock_token: AsyncMock, client: TestClient,
    ) -> None:
        """First-time OAuth login redirects to /onboarding."""
        mock_token.return_value = {
            "userinfo": {
                "sub": "first-time-gid",
                "email": "first@example.com",
                "name": "First User",
                "picture": "",
            }
        }
        resp = client.get("/auth/google/callback", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/onboarding"

    @patch("server.auth.oauth.google.authorize_access_token", new_callable=AsyncMock)
    def test_returning_user_redirects_to_dashboard(
        self, mock_token: AsyncMock, client: TestClient,
    ) -> None:
        """Returning user with completed onboarding redirects to /dashboard."""
        db_path = app.state.db_path
        user = upsert_user(
            db_path, google_id="ret-cb-gid", email="ret-cb@example.com",
        )
        complete_onboarding(db_path, user["id"], "Returning")

        mock_token.return_value = {
            "userinfo": {
                "sub": "ret-cb-gid",
                "email": "ret-cb@example.com",
                "name": "Returning",
                "picture": "",
            }
        }
        resp = client.get("/auth/google/callback", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/dashboard"


# ── Onboarding Guard Middleware Tests ─────────────────────────────────


class TestOnboardingGuard:
    def test_guard_redirects_incomplete_user_to_onboarding(
        self, client: TestClient,
    ) -> None:
        """Logged-in user with onboarding_completed=0 is redirected to /onboarding."""
        _login_new_user(client)
        resp = client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/onboarding"

    def test_guard_allows_onboarding_page(
        self, client: TestClient,
    ) -> None:
        """The /onboarding page itself is not blocked by the guard."""
        _login_new_user(client)
        resp = client.get("/onboarding", follow_redirects=False)
        assert resp.status_code == 200

    def test_guard_allows_auth_paths(
        self, client: TestClient,
    ) -> None:
        """Auth paths (/auth/*) bypass the guard."""
        _login_new_user(client)
        resp = client.get("/auth/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    def test_guard_allows_api_paths(
        self, client: TestClient,
    ) -> None:
        """API paths (/api/*) bypass the guard."""
        _login_new_user(client)
        resp = client.get("/api/jobs", follow_redirects=False)
        # Should NOT redirect to /onboarding, should get the API response
        assert resp.status_code != 302 or resp.headers.get("location") != "/onboarding"

    def test_guard_allows_landing_page(
        self, client: TestClient,
    ) -> None:
        """Landing page (/) is not blocked even for incomplete onboarding."""
        _login_new_user(client)
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 200

    def test_guard_allows_completed_user(
        self, client: TestClient,
    ) -> None:
        """User with completed onboarding can access /dashboard."""
        _login_returning_user(client)
        resp = client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 200

    def test_guard_redirects_upload_for_incomplete(
        self, client: TestClient,
    ) -> None:
        """Upload page is also guarded for incomplete onboarding."""
        _login_new_user(client)
        resp = client.get("/upload", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/onboarding"

    def test_guard_redirects_profile_for_incomplete(
        self, client: TestClient,
    ) -> None:
        """Profile page is also guarded for incomplete onboarding."""
        _login_new_user(client)
        resp = client.get("/profile", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/onboarding"

    def test_anonymous_user_not_affected(
        self, client: TestClient,
    ) -> None:
        """Anonymous visitors are not affected by the onboarding guard."""
        resp = client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 200


# ── Onboarding Page Tests ────────────────────────────────────────────


class TestOnboardingPage:
    def test_get_onboarding_renders_form(
        self, client: TestClient,
    ) -> None:
        """GET /onboarding renders the onboarding form."""
        _login_new_user(client)
        resp = client.get("/onboarding")
        assert resp.status_code == 200
        assert "프로필 설정" in resp.text
        assert "display_name" in resp.text
        assert "gender" in resp.text
        assert "birth_year" in resp.text

    def test_get_onboarding_redirects_anonymous(
        self, client: TestClient,
    ) -> None:
        """GET /onboarding redirects anonymous users to login."""
        resp = client.get("/onboarding", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/google/login" in resp.headers["location"]

    def test_get_onboarding_redirects_completed_user(
        self, client: TestClient,
    ) -> None:
        """GET /onboarding redirects users who already completed onboarding."""
        _login_returning_user(client)
        resp = client.get("/onboarding", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/dashboard"


# ── Onboarding Form Submission Tests ──────────────────────────────────


class TestOnboardingSubmit:
    def test_successful_onboarding(
        self, client: TestClient,
    ) -> None:
        """Valid form submission completes onboarding and redirects to /dashboard."""
        _login_new_user(client, google_id="submit-gid", email="submit@test.com")
        resp = client.post(
            "/onboarding",
            data={
                "display_name": "홍길동",
                "gender": "남성",
                "birth_year": "1990",
                "phone": "010-1234-5678",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/dashboard"

        # Verify DB was updated
        db_path = app.state.db_path
        user = get_user_by_google_id(db_path, "submit-gid")
        assert user is not None
        assert user["onboarding_completed"] == 1
        assert user["display_name"] == "홍길동"

        profile = get_user_profile(db_path, user["id"])
        assert profile is not None
        assert profile["gender"] == "남성"
        assert profile["birth_year"] == 1990

    def test_subsequent_pages_accessible_after_onboarding(
        self, client: TestClient,
    ) -> None:
        """After onboarding, user can access guarded pages."""
        _login_new_user(client, google_id="access-gid", email="access@test.com")
        client.post(
            "/onboarding",
            data={
                "display_name": "Test",
                "gender": "여성",
                "birth_year": "1985",
            },
            follow_redirects=False,
        )
        resp = client.get("/dashboard", follow_redirects=False)
        assert resp.status_code == 200

    def test_missing_display_name_shows_error(
        self, client: TestClient,
    ) -> None:
        """Missing display_name shows validation error."""
        _login_new_user(client, google_id="err1-gid", email="err1@test.com")
        resp = client.post(
            "/onboarding",
            data={
                "display_name": "",
                "gender": "남성",
                "birth_year": "1990",
            },
        )
        assert resp.status_code == 200
        assert "이름을 입력해주세요" in resp.text

    def test_invalid_gender_shows_error(
        self, client: TestClient,
    ) -> None:
        """Invalid gender shows validation error."""
        _login_new_user(client, google_id="err2-gid", email="err2@test.com")
        resp = client.post(
            "/onboarding",
            data={
                "display_name": "Test",
                "gender": "invalid",
                "birth_year": "1990",
            },
        )
        assert resp.status_code == 200
        assert "성별을 선택해주세요" in resp.text

    def test_missing_birth_year_shows_error(
        self, client: TestClient,
    ) -> None:
        """Missing birth_year shows validation error."""
        _login_new_user(client, google_id="err3-gid", email="err3@test.com")
        resp = client.post(
            "/onboarding",
            data={
                "display_name": "Test",
                "gender": "여성",
                "birth_year": "",
            },
        )
        assert resp.status_code == 200
        assert "출생년도를 입력해주세요" in resp.text

    def test_invalid_birth_year_shows_error(
        self, client: TestClient,
    ) -> None:
        """Non-numeric birth_year shows validation error."""
        _login_new_user(client, google_id="err4-gid", email="err4@test.com")
        resp = client.post(
            "/onboarding",
            data={
                "display_name": "Test",
                "gender": "기타",
                "birth_year": "abc",
            },
        )
        assert resp.status_code == 200
        assert "숫자로 입력" in resp.text

    def test_anonymous_post_redirects_to_login(
        self, client: TestClient,
    ) -> None:
        """POST /onboarding by anonymous user redirects to login."""
        resp = client.post(
            "/onboarding",
            data={
                "display_name": "Test",
                "gender": "남성",
                "birth_year": "1990",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/auth/google/login" in resp.headers["location"]


# ── Navigation Visibility Tests ──────────────────────────────────────


class TestOnboardingNavigation:
    def test_nav_hidden_during_onboarding(
        self, client: TestClient,
    ) -> None:
        """Navigation links are hidden when onboarding is incomplete."""
        _login_new_user(client, google_id="nav-gid", email="nav@test.com")
        resp = client.get("/onboarding")
        assert resp.status_code == 200
        # Navigation menu items should not be present
        assert "업로드</a>" not in resp.text
        assert "대시보드</a>" not in resp.text

    def test_nav_shown_after_onboarding(
        self, client: TestClient,
    ) -> None:
        """Navigation links are visible after onboarding is complete."""
        _login_returning_user(
            client, google_id="navdone-gid", email="navdone@test.com",
        )
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "업로드" in resp.text
        assert "대시보드" in resp.text
