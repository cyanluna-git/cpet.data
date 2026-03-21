"""
tests/conftest.py — Shared fixtures for E2E tests.

Provides reusable fixtures: TestClient with real temp data dir,
and fixture file loaders for Park Geunyun and Hong Changsun datasets.
"""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.db import init_db
from server.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def e2e_client(tmp_path: Path) -> TestClient:
    """FastAPI TestClient with real temp data dir and initialized DB."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "cpet_platform.db"
    init_db(db_path)

    app.state.db_path = db_path
    app.state.data_dir = data_dir
    app.state.channel_url = "http://127.0.0.1:9999"

    return TestClient(app, raise_server_exceptions=False)


def _load_raw_files(workspace_name: str) -> list[tuple[str, tuple[str, io.BytesIO, str]]]:
    """Read all raw files from a fixture workspace as upload tuples."""
    raw_dir = FIXTURES_DIR / workspace_name / "raw"
    pairs: list[tuple[str, tuple[str, io.BytesIO, str]]] = []
    for f in sorted(raw_dir.iterdir()):
        if f.is_file():
            content = f.read_bytes()
            pairs.append(
                ("files", (f.name, io.BytesIO(content), "application/octet-stream"))
            )
    return pairs


@pytest.fixture()
def park_fixture_files() -> list[tuple[str, tuple[str, io.BytesIO, str]]]:
    """Read Park Geunyun raw files as upload tuples."""
    return _load_raw_files("park_geunyun")


@pytest.fixture()
def hong_fixture_files() -> list[tuple[str, tuple[str, io.BytesIO, str]]]:
    """Read Hong Changsun raw files as upload tuples."""
    return _load_raw_files("hong_changsun")


@pytest.fixture()
def cosmed_only_fixture_files() -> list[tuple[str, tuple[str, io.BytesIO, str]]]:
    """Read COSMED-only raw files as upload tuples."""
    return _load_raw_files("cosmed_only")
