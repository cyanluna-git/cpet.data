from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.db import init_db
from server.main import app


@pytest.fixture(autouse=True)
def _setup_app_state(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "cpet_platform.db"
    init_db(db_path)
    app.state.db_path = db_path
    app.state.data_dir = data_dir
    app.state.channel_url = "http://127.0.0.1:9999"
    app.state.published_dir = tmp_path / "published"


def test_jobs_partial_returns_success() -> None:
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/jobs/partial")
    assert resp.status_code == 200

