"""
tests/test_subject_feature_sets_export.py — subject_feature_sets export tests.
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
                    "INSERT OR REPLACE INTO analysis_results (category, key, value) VALUES (?, ?, ?)",
                    (category, key, value_text),
                )
    conn.commit()
    conn.close()


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


def _seed_export_rows(db_path: Path, data_dir: Path) -> None:
    subject = create_subject(db_path, name="Geunyun Park")

    ws1 = data_dir / "workspaces" / "export-cpet-1"
    _create_analysis_db(
        ws1,
        "2026-02-01",
        metrics={"vo2max": {"vo2max_rel": 57.2}},
    )
    create_submission(
        db_path,
        "export cpet 1",
        [{"name": "park-1.fit"}],
        str(ws1),
        subject_id=subject["id"],
    )

    ws2 = data_dir / "workspaces" / "export-cpet-2"
    _create_analysis_db(
        ws2,
        "2026-03-20",
        metrics={"vo2max": {"vo2max_rel": 60.7}},
    )
    create_submission(
        db_path,
        "export cpet 2",
        [{"name": "park-2.fit"}],
        str(ws2),
        subject_id=subject["id"],
    )

    backfill_subject_metric_snapshots(db_path)
    backfill_endurance_core_feature_sets(db_path)
    backfill_longitudinal_delta_feature_sets(db_path)


def _login_as_researcher(client: TestClient, google_id: str = "feature-export-gid") -> None:
    db_path = app.state.db_path
    user = upsert_user(
        db_path,
        google_id=google_id,
        email=f"{google_id}@example.com",
        display_name="Feature Export Researcher",
    )
    complete_onboarding(db_path, user["id"], "Feature Export Researcher")
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
                "name": "Feature Export Researcher",
                "picture": "",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)


class TestSubjectFeatureSetsExport:
    def test_export_csv_respects_filters(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        _seed_export_rows(db_path, app.state.data_dir)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as_researcher(client)

        resp = client.get(
            "/api/manage/feature-sets/export.csv"
            "?feature_spec_key=longitudinal_delta"
            "&feature_window_label=previous_pair"
            "&feature_anchor_source_kind=cpet_submission"
        )

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "longitudinal_delta" in resp.text
        assert "endurance_core" not in resp.text
        assert "previous_pair" in resp.text
        assert "cpet_submission" in resp.text

    def test_export_json_includes_filtered_feature_payload(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        _seed_export_rows(db_path, app.state.data_dir)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as_researcher(client)

        resp = client.get(
            "/api/manage/feature-sets/export.json"
            "?feature_spec_key=longitudinal_delta"
            "&feature_window_label=previous_pair"
            "&feature_anchor_source_kind=cpet_submission"
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert body["filters"]["feature_spec_key"] == "longitudinal_delta"
        assert body["filters"]["feature_window_label"] == "previous_pair"
        assert body["filters"]["feature_anchor_source_kind"] == "cpet_submission"
        assert all(item["feature_spec_key"] == "longitudinal_delta" for item in body["feature_sets"])
        assert all(item["window_label"] == "previous_pair" for item in body["feature_sets"])
        assert all(item["anchor_source_kind"] == "cpet_submission" for item in body["feature_sets"])
        assert "features" in body["feature_sets"][0]["feature_payload"]
