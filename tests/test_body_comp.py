"""
tests/test_body_comp.py — Tests for InBody body composition feature (#2902).

Covers:
- analyze_body_comp() with valid / missing / partial data
- parse_workspace() reads inbody.json sidecar
- DB migration: body comp columns exist after init_db()
- create_submission() stores body comp values
- POST /api/submit stores body comp and writes inbody.json to workspace
"""

import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from pipeline.analysis import analyze_body_comp
from pipeline.parsers import ParsedData, parse_workspace
from server.db import (
    _connect,
    complete_onboarding,
    create_submission,
    get_submission,
    init_db,
    upsert_user,
)
from server.main import app


# ── analyze_body_comp ────────────────────────────────────────────────


def _make_subject(
    weight_kg: float | None = 70.0,
    body_fat_pct: float | None = 20.0,
    skeletal_muscle_mass_kg: float | None = 32.0,
    lean_body_mass_kg: float | None = 56.0,
) -> pd.DataFrame:
    return pd.DataFrame([{
        "weight_kg": weight_kg,
        "body_fat_pct": body_fat_pct,
        "skeletal_muscle_mass_kg": skeletal_muscle_mass_kg,
        "lean_body_mass_kg": lean_body_mass_kg,
    }])


class TestAnalyzeBodyComp:
    def test_returns_no_data_when_subject_empty(self):
        result = analyze_body_comp(pd.DataFrame(), {}, {}, {})
        assert result["status"] == "no_data"

    def test_returns_no_data_when_lbm_is_null(self):
        subject = _make_subject(lean_body_mass_kg=None)
        result = analyze_body_comp(subject, {}, {}, {})
        assert result["status"] == "no_data"

    def test_returns_no_data_when_lbm_is_zero(self):
        subject = _make_subject(lean_body_mass_kg=0.0)
        result = analyze_body_comp(subject, {}, {}, {})
        assert result["status"] == "no_data"

    def test_computed_status_with_valid_data(self):
        subject = _make_subject()
        vo2max = {"vo2max_ml": 4200.0, "peak_power_achieved_w": 350}
        result = analyze_body_comp(subject, vo2max, {}, {})
        assert result["status"] == "computed"
        assert result["lean_body_mass_kg"] == 56.0

    def test_vo2max_per_lbm_computed(self):
        subject = _make_subject(lean_body_mass_kg=56.0)
        vo2max = {"vo2max_ml": 4200.0}
        result = analyze_body_comp(subject, vo2max, {}, {})
        expected = round(4200.0 / 56.0, 1)
        assert result["vo2max_per_lbm_ml_min_kg"] == expected

    def test_peak_power_per_lbm_computed(self):
        subject = _make_subject(lean_body_mass_kg=56.0)
        vo2max = {"peak_power_achieved_w": 350, "vo2max_ml": 4200.0}
        result = analyze_body_comp(subject, vo2max, {}, {})
        expected = round(350 / 56.0, 2)
        assert result["peak_power_per_lbm_w_kg"] == expected

    def test_fatmax_efficiency_computed(self):
        subject = _make_subject(weight_kg=70.0, body_fat_pct=20.0, lean_body_mass_kg=56.0)
        substrate = {"fatmax_gmin": 0.8}
        result = analyze_body_comp(subject, {}, substrate, {})
        fat_mass = 70.0 * 0.20
        expected = round(0.8 / fat_mass, 4)
        assert result["fatmax_per_fat_mass_gmin_per_kg"] == expected

    def test_fatmax_skipped_when_zero_fat_pct(self):
        subject = _make_subject(body_fat_pct=0.0, lean_body_mass_kg=70.0)
        substrate = {"fatmax_gmin": 0.8}
        result = analyze_body_comp(subject, {}, substrate, {})
        assert "fatmax_per_fat_mass_gmin_per_kg" not in result

    def test_no_vo2max_key_does_not_crash(self):
        subject = _make_subject()
        result = analyze_body_comp(subject, {}, {}, {})
        assert result["status"] == "computed"
        assert "vo2max_per_lbm_ml_min_kg" not in result


# ── parse_workspace reads inbody.json ────────────────────────────────


@pytest.fixture()
def minimal_workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace with a real COSMED XLSX fixture."""
    fixture_src = Path(__file__).parent / "fixtures" / "park_geunyun"
    if not fixture_src.is_dir():
        pytest.skip("park_geunyun fixture not found")
    ws = tmp_path / "ws"
    shutil.copytree(fixture_src, ws)
    return ws


class TestParseWorkspaceInbody:
    def test_body_comp_none_when_no_inbody_json(self, minimal_workspace: Path):
        parsed = parse_workspace(minimal_workspace)
        assert parsed.body_comp is None

    def test_body_comp_loaded_from_inbody_json(self, minimal_workspace: Path):
        raw_dir = minimal_workspace / "raw"
        raw_dir.mkdir(exist_ok=True)
        payload = {"body_weight_kg": 76.9, "body_fat_pct": 23.5, "skeletal_muscle_mass_kg": 33.1}
        (raw_dir / "inbody.json").write_text(json.dumps(payload), encoding="utf-8")
        parsed = parse_workspace(minimal_workspace)
        assert parsed.body_comp == payload

    def test_body_comp_none_on_invalid_json(self, minimal_workspace: Path):
        raw_dir = minimal_workspace / "raw"
        raw_dir.mkdir(exist_ok=True)
        (raw_dir / "inbody.json").write_text("not-json", encoding="utf-8")
        parsed = parse_workspace(minimal_workspace)
        assert parsed.body_comp is None


# ── DB migrations ────────────────────────────────────────────────────


class TestDbBodyCompMigration:
    def test_body_comp_columns_exist_after_init(self, tmp_path: Path):
        db = tmp_path / "test.db"
        init_db(db)
        conn = _connect(db)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(submissions)").fetchall()}
        conn.close()
        assert "body_weight_kg" in cols
        assert "body_fat_pct" in cols
        assert "skeletal_muscle_mass_kg" in cols

    def test_create_submission_stores_body_comp(self, tmp_path: Path):
        db = tmp_path / "test.db"
        init_db(db)
        sid = create_submission(
            db, "test", [], "/tmp/ws",
            body_weight_kg=76.9,
            body_fat_pct=23.5,
            skeletal_muscle_mass_kg=33.1,
        )
        sub = get_submission(db, sid)
        assert sub["body_weight_kg"] == 76.9
        assert sub["body_fat_pct"] == 23.5
        assert sub["skeletal_muscle_mass_kg"] == 33.1

    def test_create_submission_null_when_not_provided(self, tmp_path: Path):
        db = tmp_path / "test.db"
        init_db(db)
        sid = create_submission(db, "test", [], "/tmp/ws")
        sub = get_submission(db, sid)
        assert sub["body_weight_kg"] is None
        assert sub["body_fat_pct"] is None
        assert sub["skeletal_muscle_mass_kg"] is None


# ── POST /api/submit integration ────────────────────────────────────


@pytest.fixture()
def submit_client(tmp_path: Path) -> TestClient:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "cpet_platform.db"
    init_db(db_file)
    app.state.db_path = db_file
    app.state.data_dir = data_dir
    app.state.channel_url = "http://127.0.0.1:9999"
    app.state.published_dir = tmp_path / "published"
    return TestClient(app, raise_server_exceptions=False)


def _login_submit(client: TestClient, role: str = "researcher") -> dict:
    db_path = app.state.db_path
    user = upsert_user(db_path, google_id="bc-gid", email="bc@test.com", display_name="BC User")
    complete_onboarding(db_path, user["id"], "BC User")
    conn = _connect(db_path)
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user["id"]))
    conn.commit()
    conn.close()
    with patch(
        "server.auth.oauth.google.authorize_access_token",
        new_callable=AsyncMock,
    ) as mock_token:
        mock_token.return_value = {
            "userinfo": {"sub": "bc-gid", "email": "bc@test.com", "name": "BC User", "picture": ""}
        }
        client.get("/auth/google/callback", follow_redirects=False)
    from server.db import get_user
    return get_user(db_path, user["id"])


FIXTURE_XLSX = Path(__file__).parent / "fixtures" / "park_geunyun" / "raw"


class TestSubmitBodyComp:
    def test_body_comp_stored_in_db_on_submit(self, submit_client: TestClient):
        _login_submit(submit_client)
        xlsx_files = list(FIXTURE_XLSX.glob("*.xlsx")) if FIXTURE_XLSX.is_dir() else []
        if not xlsx_files:
            pytest.skip("park_geunyun XLSX fixture not found")

        with open(xlsx_files[0], "rb") as f:
            resp = submit_client.post(
                "/api/submit",
                data={
                    "subject_name": "Test",
                    "body_weight_kg": "76.9",
                    "body_fat_pct": "23.5",
                    "skeletal_muscle_mass_kg": "33.1",
                },
                files={"files": (xlsx_files[0].name, f, "application/octet-stream")},
            )

        assert resp.status_code == 201
        job_id = resp.json()["job_id"]
        db_path = app.state.db_path
        conn = _connect(db_path)
        row = conn.execute(
            "SELECT s.body_weight_kg, s.body_fat_pct, s.skeletal_muscle_mass_kg "
            "FROM submissions s JOIN jobs j ON j.submission_id = s.id WHERE j.id = ?",
            (job_id,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 76.9
        assert row[1] == 23.5
        assert row[2] == 33.1

    def test_inbody_json_written_to_workspace(self, submit_client: TestClient):
        _login_submit(submit_client)
        xlsx_files = list(FIXTURE_XLSX.glob("*.xlsx")) if FIXTURE_XLSX.is_dir() else []
        if not xlsx_files:
            pytest.skip("park_geunyun XLSX fixture not found")

        with open(xlsx_files[0], "rb") as f:
            resp = submit_client.post(
                "/api/submit",
                data={
                    "subject_name": "Test2",
                    "body_weight_kg": "80.0",
                    "body_fat_pct": "25.0",
                    "skeletal_muscle_mass_kg": "35.0",
                },
                files={"files": (xlsx_files[0].name, f, "application/octet-stream")},
            )

        assert resp.status_code == 201
        job_id = resp.json()["job_id"]
        db_path = app.state.db_path
        conn = _connect(db_path)
        row = conn.execute(
            "SELECT s.workspace_path FROM submissions s JOIN jobs j ON j.submission_id = s.id WHERE j.id = ?",
            (job_id,),
        ).fetchone()
        conn.close()
        ws = Path(row[0])
        inbody_path = ws / "raw" / "inbody.json"
        assert inbody_path.exists()
        data = json.loads(inbody_path.read_text())
        assert data["body_weight_kg"] == 80.0
        assert data["body_fat_pct"] == 25.0
        assert data["skeletal_muscle_mass_kg"] == 35.0

    def test_no_inbody_json_when_fields_empty(self, submit_client: TestClient):
        _login_submit(submit_client)
        xlsx_files = list(FIXTURE_XLSX.glob("*.xlsx")) if FIXTURE_XLSX.is_dir() else []
        if not xlsx_files:
            pytest.skip("park_geunyun XLSX fixture not found")

        with open(xlsx_files[0], "rb") as f:
            resp = submit_client.post(
                "/api/submit",
                data={"subject_name": "Test3"},
                files={"files": (xlsx_files[0].name, f, "application/octet-stream")},
            )

        assert resp.status_code == 201
        job_id = resp.json()["job_id"]
        db_path = app.state.db_path
        conn = _connect(db_path)
        row = conn.execute(
            "SELECT s.workspace_path FROM submissions s JOIN jobs j ON j.submission_id = s.id WHERE j.id = ?",
            (job_id,),
        ).fetchone()
        conn.close()
        ws = Path(row[0])
        assert not (ws / "raw" / "inbody.json").exists()
