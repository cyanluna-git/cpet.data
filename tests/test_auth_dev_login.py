"""
tests/test_auth_dev_login.py — local dev login route tests.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from server.db import complete_onboarding, init_db, upsert_user
from server.main import app


def _setup_app(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "cpet_platform.db"
    init_db(db_path)
    app.state.db_path = db_path
    app.state.data_dir = data_dir
    app.state.channel_url = "http://127.0.0.1:9999"
    app.state.published_dir = tmp_path / "published"
    return db_path


def test_dev_login_disabled_redirects_home(tmp_path: Path, monkeypatch) -> None:
    _setup_app(tmp_path)
    monkeypatch.delenv("ENABLE_LOCAL_DEV_LOGIN", raising=False)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/auth/dev-login", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "/"


def test_dev_login_enabled_creates_manage_session(tmp_path: Path, monkeypatch) -> None:
    db_path = _setup_app(tmp_path)
    user = upsert_user(
        db_path,
        google_id="local-admin-gid",
        email="local-admin@example.com",
        display_name="Local Admin",
    )
    complete_onboarding(db_path, user["id"], "Local Admin")

    conn = __import__("sqlite3").connect(str(db_path))
    conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user["id"],))
    conn.commit()
    conn.close()

    monkeypatch.setenv("ENABLE_LOCAL_DEV_LOGIN", "1")
    monkeypatch.setenv("DEV_LOGIN_EMAIL", "local-admin@example.com")
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/auth/dev-login", follow_redirects=False)
    manage = client.get("/manage?tab=feature_sets", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.headers["location"] == "/manage?tab=feature_sets"
    assert manage.status_code == 200
    assert "Feature Sets Explorer" in manage.text
