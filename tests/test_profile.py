"""
tests/test_profile.py — Tests for user profile page and body composition CRUD.

Covers:
    - user_profiles table schema
    - Profile CRUD operations (get, upsert)
    - GET /profile page (auth redirect, template render)
    - PATCH /api/profile (HTMX inline edit, partial response)
    - Navigation link visibility
"""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from server.db import (
    _connect,
    get_user_profile,
    init_db,
    upsert_user,
    upsert_user_profile,
)
from server.main import app


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path, initialized."""
    path = tmp_path / "test_profile.db"
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


def _login_user(client: TestClient, google_id: str = "profile-gid") -> dict:
    """Simulate Google OAuth login and return the created user dict."""
    with patch(
        "server.auth.oauth.google.authorize_access_token",
        new_callable=AsyncMock,
    ) as mock_token:
        mock_token.return_value = {
            "userinfo": {
                "sub": google_id,
                "email": f"{google_id}@example.com",
                "name": "Profile User",
                "picture": "https://example.com/avatar.jpg",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)

    from server.db import get_user_by_google_id
    return get_user_by_google_id(app.state.db_path, google_id)


# ── user_profiles Table Schema ────────────────────────────────────


class TestUserProfilesSchema:
    def test_user_profiles_table_exists(self, db_path: Path) -> None:
        """init_db creates the user_profiles table."""
        conn = sqlite3.connect(str(db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_profiles'"
        ).fetchall()
        conn.close()
        assert len(tables) == 1

    def test_user_profiles_columns(self, db_path: Path) -> None:
        """user_profiles table has all required columns."""
        conn = sqlite3.connect(str(db_path))
        columns = conn.execute("PRAGMA table_info(user_profiles)").fetchall()
        conn.close()
        col_names = {c[1] for c in columns}
        expected = {
            "user_id", "weight_kg", "height_cm", "body_fat_pct",
            "skeletal_muscle_mass", "bmi", "birth_year", "gender",
            "training_level", "measured_at", "updated_at",
        }
        assert expected.issubset(col_names)

    def test_user_profiles_fk_constraint(self, db_path: Path) -> None:
        """user_id in user_profiles references users(id)."""
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO user_profiles (user_id) VALUES (?)",
                ("nonexistent-user-id",),
            )
        conn.close()


# ── Profile CRUD ──────────────────────────────────────────────────


class TestProfileCRUD:
    def test_get_profile_not_found(self, db_path: Path) -> None:
        """get_user_profile returns None for nonexistent user."""
        assert get_user_profile(db_path, "no-such-user") is None

    def test_upsert_creates_new_profile(self, db_path: Path) -> None:
        """upsert_user_profile creates a new profile row."""
        user = upsert_user(
            db_path, google_id="prof-g1", email="prof1@example.com",
        )
        profile = upsert_user_profile(
            db_path, user["id"],
            weight_kg=72.5,
            height_cm=175.0,
            body_fat_pct=15.2,
        )
        assert profile["user_id"] == user["id"]
        assert profile["weight_kg"] == 72.5
        assert profile["height_cm"] == 175.0
        assert profile["body_fat_pct"] == 15.2
        assert profile["updated_at"] is not None

    def test_upsert_updates_existing_profile(self, db_path: Path) -> None:
        """upsert_user_profile updates specific fields without clearing others."""
        user = upsert_user(
            db_path, google_id="prof-g2", email="prof2@example.com",
        )
        upsert_user_profile(
            db_path, user["id"],
            weight_kg=70.0,
            body_fat_pct=18.0,
        )
        updated = upsert_user_profile(
            db_path, user["id"],
            weight_kg=68.5,
        )
        assert updated["weight_kg"] == 68.5
        # body_fat_pct should remain from previous insert
        assert updated["body_fat_pct"] == 18.0

    def test_upsert_all_fields(self, db_path: Path) -> None:
        """upsert_user_profile handles all supported fields."""
        user = upsert_user(
            db_path, google_id="prof-g3", email="prof3@example.com",
        )
        profile = upsert_user_profile(
            db_path, user["id"],
            weight_kg=75.0,
            height_cm=180.0,
            body_fat_pct=12.5,
            skeletal_muscle_mass=35.0,
            bmi=23.1,
            birth_year=1990,
            gender="male",
            training_level="advanced",
            measured_at="2026-03-20",
        )
        assert profile["weight_kg"] == 75.0
        assert profile["height_cm"] == 180.0
        assert profile["body_fat_pct"] == 12.5
        assert profile["skeletal_muscle_mass"] == 35.0
        assert profile["bmi"] == 23.1
        assert profile["birth_year"] == 1990
        assert profile["gender"] == "male"
        assert profile["training_level"] == "advanced"
        assert profile["measured_at"] == "2026-03-20"

    def test_upsert_unknown_field_raises(self, db_path: Path) -> None:
        """upsert_user_profile rejects unknown field names."""
        user = upsert_user(
            db_path, google_id="prof-g4", email="prof4@example.com",
        )
        with pytest.raises(ValueError, match="Unknown profile field"):
            upsert_user_profile(db_path, user["id"], unknown_field="bad")

    def test_upsert_with_no_fields_returns_existing(self, db_path: Path) -> None:
        """upsert_user_profile with no fields on existing profile is a no-op."""
        user = upsert_user(
            db_path, google_id="prof-g5", email="prof5@example.com",
        )
        created = upsert_user_profile(db_path, user["id"], weight_kg=80.0)
        unchanged = upsert_user_profile(db_path, user["id"])
        assert unchanged["weight_kg"] == created["weight_kg"]

    def test_get_profile_after_upsert(self, db_path: Path) -> None:
        """get_user_profile retrieves what upsert_user_profile wrote."""
        user = upsert_user(
            db_path, google_id="prof-g6", email="prof6@example.com",
        )
        upsert_user_profile(db_path, user["id"], bmi=22.0)
        fetched = get_user_profile(db_path, user["id"])
        assert fetched is not None
        assert fetched["bmi"] == 22.0


# ── Profile Page Route ────────────────────────────────────────────


class TestProfilePage:
    def test_anonymous_redirects_to_login(self, client: TestClient) -> None:
        """GET /profile without session redirects to Google login."""
        resp = client.get("/profile", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/google/login" in resp.headers["location"]

    def test_logged_in_renders_profile(self, client: TestClient) -> None:
        """GET /profile with session renders the profile page."""
        _login_user(client)
        resp = client.get("/profile")
        assert resp.status_code == 200
        assert "프로필" in resp.text
        assert "Profile User" in resp.text
        assert "체성분" in resp.text

    def test_profile_shows_user_email(self, client: TestClient) -> None:
        """Profile page displays the user's email."""
        _login_user(client, google_id="email-test-gid")
        resp = client.get("/profile")
        assert resp.status_code == 200
        assert "email-test-gid@example.com" in resp.text

    def test_profile_shows_avatar(self, client: TestClient) -> None:
        """Profile page renders the user's avatar image."""
        _login_user(client)
        resp = client.get("/profile")
        assert "avatar.jpg" in resp.text


# ── PATCH /api/profile ────────────────────────────────────────────


class TestPatchProfile:
    def test_anonymous_returns_401(self, client: TestClient) -> None:
        """PATCH /api/profile without session returns 401."""
        resp = client.patch(
            "/api/profile",
            data={"weight_kg": "70.0"},
        )
        assert resp.status_code == 401

    def test_update_single_field(self, client: TestClient) -> None:
        """PATCH /api/profile updates a single field and returns partial HTML."""
        _login_user(client)
        resp = client.patch(
            "/api/profile",
            data={"weight_kg": "72.5"},
        )
        assert resp.status_code == 200
        assert "72.5" in resp.text
        # Response should be the partial template (contains body-comp-fields id)
        assert "body-comp-fields" in resp.text

    def test_update_multiple_fields(self, client: TestClient) -> None:
        """PATCH /api/profile can update multiple fields at once."""
        _login_user(client)
        resp = client.patch(
            "/api/profile",
            data={
                "weight_kg": "68.0",
                "body_fat_pct": "14.5",
                "measured_at": "2026-03-25",
            },
        )
        assert resp.status_code == 200
        assert "68.0" in resp.text or "68" in resp.text
        assert "14.5" in resp.text

    def test_update_persists_to_db(self, client: TestClient) -> None:
        """PATCH /api/profile persists changes to the database."""
        user = _login_user(client)
        client.patch(
            "/api/profile",
            data={"skeletal_muscle_mass": "33.5"},
        )
        profile = get_user_profile(app.state.db_path, user["id"])
        assert profile is not None
        assert profile["skeletal_muscle_mass"] == 33.5

    def test_empty_value_sets_null(self, client: TestClient) -> None:
        """PATCH /api/profile with empty string sets field to None."""
        user = _login_user(client)
        # First set a value
        client.patch("/api/profile", data={"weight_kg": "75.0"})
        # Then clear it
        client.patch("/api/profile", data={"weight_kg": ""})
        profile = get_user_profile(app.state.db_path, user["id"])
        assert profile is not None
        assert profile["weight_kg"] is None

    def test_update_text_fields(self, client: TestClient) -> None:
        """PATCH /api/profile handles text fields (gender, training_level)."""
        user = _login_user(client, google_id="text-fields-gid")
        client.patch(
            "/api/profile",
            data={"gender": "male", "training_level": "elite"},
        )
        profile = get_user_profile(app.state.db_path, user["id"])
        assert profile is not None
        assert profile["gender"] == "male"
        assert profile["training_level"] == "elite"

    def test_update_integer_field(self, client: TestClient) -> None:
        """PATCH /api/profile correctly parses integer fields."""
        user = _login_user(client, google_id="int-field-gid")
        client.patch(
            "/api/profile",
            data={"birth_year": "1995"},
        )
        profile = get_user_profile(app.state.db_path, user["id"])
        assert profile is not None
        assert profile["birth_year"] == 1995


# ── Navigation ────────────────────────────────────────────────────


class TestProfileNavigation:
    def test_anonymous_no_profile_link(self, client: TestClient) -> None:
        """Anonymous visitors do not see the profile nav link."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert 'href="/profile"' not in resp.text

    def test_logged_in_sees_profile_link(self, client: TestClient) -> None:
        """Logged-in users see the profile nav link."""
        _login_user(client)
        resp = client.get("/")
        assert resp.status_code == 200
        assert 'href="/profile"' in resp.text
        assert "프로필" in resp.text
