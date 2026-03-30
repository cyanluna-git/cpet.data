from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from server.db import complete_onboarding, get_user, init_db, upsert_user
from server.main import app


def _login_as(client: TestClient, role: str, google_id: str, email: str, name: str) -> None:
    db_path = app.state.db_path
    user = upsert_user(db_path, google_id=google_id, email=email, display_name=name)
    complete_onboarding(db_path, user["id"], name)

    conn = __import__("sqlite3").connect(str(db_path))
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user["id"]))
    conn.commit()
    conn.close()

    with patch("server.auth.oauth.google.authorize_access_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = {
            "userinfo": {
                "sub": google_id,
                "email": email,
                "name": name,
                "picture": "",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)

    assert get_user(db_path, user["id"]) is not None


def _setup_state(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "cpet_platform.db"
    init_db(db_path)
    app.state.db_path = db_path
    app.state.data_dir = data_dir
    app.state.published_dir = tmp_path / "published"


def test_notes_requires_researcher_or_admin(tmp_path) -> None:
    _setup_state(tmp_path)
    client = TestClient(app, raise_server_exceptions=False)

    anon = client.get("/notes", follow_redirects=False)
    assert anon.status_code == 302
    assert "/auth/google/login" in anon.headers["location"]

    _login_as(client, "user", "notes-user", "notes-user@test.com", "Notes User")
    forbidden = client.get("/notes")
    assert forbidden.status_code == 403


def test_notes_index_lists_guides_for_researcher(tmp_path) -> None:
    _setup_state(tmp_path)
    client = TestClient(app, raise_server_exceptions=False)
    _login_as(client, "researcher", "notes-researcher", "notes-researcher@test.com", "Notes Researcher")

    resp = client.get("/notes")

    assert resp.status_code == 200
    assert "연구 노트" in resp.text
    assert "Two-Block CPET Fuel Split Detailed Guide" in resp.text
    assert "3-Path Energy System Detailed Guide" in resp.text
    assert ">노트<" in resp.text


def test_note_viewer_and_raw_content_render_for_admin(tmp_path) -> None:
    _setup_state(tmp_path)
    client = TestClient(app, raise_server_exceptions=False)
    _login_as(client, "admin", "notes-admin", "notes-admin@test.com", "Notes Admin")

    page = client.get("/notes/three-path-energy-system-detail")
    assert page.status_code == 200
    assert "/notes/three-path-energy-system-detail/content" in page.text

    content = client.get("/notes/three-path-energy-system-detail/content")
    assert content.status_code == 200
    assert "<title>3-Path Energy System Detailed Guide</title>" in content.text
