"""
tests/test_subject_feature_sets_explorer.py — subject_feature_sets explorer UI/API tests.
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from server.db import (
    backfill_endurance_core_feature_sets,
    backfill_longitudinal_delta_feature_sets,
    backfill_subject_metric_snapshots,
    complete_onboarding,
    create_submission,
    create_subject,
    init_db,
    upsert_user,
)
from server.main import app


def _create_analysis_db(
    workspace: Path,
    test_date: str,
    protocol_name: str = "Belgium Lactate Test Elite",
    metrics: dict | None = None,
) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    db_path = workspace / "analysis.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS test_session (
            id INTEGER PRIMARY KEY,
            test_date TEXT,
            protocol_name TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO test_session (test_date, protocol_name) VALUES (?, ?)",
        (test_date, protocol_name),
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS analysis_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            UNIQUE(category, key)
        )"""
    )
    if metrics:
        for category, entries in metrics.items():
            for key, value in entries.items():
                value_text = json.dumps(value) if not isinstance(value, str) else value
                conn.execute(
                    "INSERT OR REPLACE INTO analysis_results (category, key, value) "
                    "VALUES (?, ?, ?)",
                    (category, key, value_text),
                )
    conn.commit()
    conn.close()


def _seed_feature_rows(db_path: Path, data_dir: Path) -> tuple[dict, dict]:
    subject = create_subject(db_path, name="Geunyun Park")

    ws1 = data_dir / "workspaces" / "feature-cpet-1"
    _create_analysis_db(
        ws1,
        "2026-02-01",
        metrics={"vo2max": {"vo2max_rel": 57.2}},
    )
    create_submission(
        db_path,
        "feature cpet 1",
        [{"name": "park-1.fit"}],
        str(ws1),
        subject_id=subject["id"],
    )

    ws2 = data_dir / "workspaces" / "feature-cpet-2"
    _create_analysis_db(
        ws2,
        "2026-03-20",
        metrics={"vo2max": {"vo2max_rel": 60.7}},
    )
    create_submission(
        db_path,
        "feature cpet 2",
        [{"name": "park-2.fit"}],
        str(ws2),
        subject_id=subject["id"],
    )

    backfill_subject_metric_snapshots(db_path)
    backfill_endurance_core_feature_sets(db_path)
    backfill_longitudinal_delta_feature_sets(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM subject_feature_sets ORDER BY feature_spec_key ASC, anchor_measured_at DESC"
    ).fetchall()
    conn.close()
    return dict(rows[0]), dict(rows[-1])


def _login_as_researcher(client: TestClient, google_id: str = "feature-sets-gid") -> dict:
    db_path = app.state.db_path
    user = upsert_user(
        db_path,
        google_id=google_id,
        email=f"{google_id}@example.com",
        display_name="Feature Researcher",
    )
    complete_onboarding(db_path, user["id"], "Feature Researcher")
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE users SET role = 'researcher' WHERE id = ?", (user["id"],))
    conn.commit()
    conn.close()

    with patch(
        "server.auth.oauth.google.authorize_access_token",
        new_callable=AsyncMock,
    ) as mock_token:
        mock_token.return_value = {
            "userinfo": {
                "sub": google_id,
                "email": f"{google_id}@example.com",
                "name": "Feature Researcher",
                "picture": "",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)
    return user


class TestSubjectFeatureSetsExplorer:
    def _setup_app(self, tmp_path: Path) -> Path:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "cpet_platform.db"
        init_db(db_path)
        app.state.db_path = db_path
        app.state.data_dir = data_dir
        app.state.channel_url = "http://127.0.0.1:9999"
        app.state.published_dir = tmp_path / "published"
        return db_path

    def test_manage_feature_sets_tab_renders_explorer_table(self, tmp_path: Path) -> None:
        db_path = self._setup_app(tmp_path)
        _seed_feature_rows(db_path, app.state.data_dir)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as_researcher(client)

        resp = client.get("/manage?tab=feature_sets")

        assert resp.status_code == 200
        assert "Feature Sets Explorer" in resp.text
        assert "Geunyun Park" in resp.text
        assert "endurance_core" in resp.text
        assert "longitudinal_delta" in resp.text

    def test_feature_sets_partial_filters_by_spec_key(self, tmp_path: Path) -> None:
        db_path = self._setup_app(tmp_path)
        _seed_feature_rows(db_path, app.state.data_dir)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as_researcher(client)

        resp = client.get("/api/manage/feature-sets?feature_spec_key=longitudinal_delta")

        assert resp.status_code == 200
        assert "longitudinal_delta" in resp.text
        assert "endurance_core" not in resp.text

    def test_feature_set_detail_partial_renders_payload_and_flags(self, tmp_path: Path) -> None:
        db_path = self._setup_app(tmp_path)
        _, detail_row = _seed_feature_rows(db_path, app.state.data_dir)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as_researcher(client)

        resp = client.get(f"/api/manage/feature-sets/{detail_row['feature_row_id']}")

        assert resp.status_code == 200
        assert detail_row["feature_row_id"] in resp.text
        assert "Feature Payload JSON" in resp.text
        assert "missing_previous_snapshot" in resp.text
        assert "longitudinal_delta" in resp.text
