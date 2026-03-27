"""
tests/test_subject_metric_snapshots_explorer.py — Explorer UI/API tests.
"""

import html
import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from server.db import (
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


def _write_inscyd_report(workspace: Path, report_data: dict) -> None:
    report_dir = workspace / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = html.escape(json.dumps(report_data, ensure_ascii=False))
    (report_dir / "index.html").write_text(
        f"<html><body><script id=\"report-data\" type=\"application/json\">{payload}</script></body></html>",
        encoding="utf-8",
    )


def _seed_snapshot_rows(db_path: Path, data_dir: Path) -> tuple[dict, dict]:
    subject = create_subject(db_path, name="Geunyun Park")

    cpet_ws = data_dir / "workspaces" / "seed-cpet"
    _create_analysis_db(
        cpet_ws,
        "2026-03-20",
        metrics={"vo2max": {"vo2max_rel": 60.7}},
    )
    create_submission(
        db_path,
        "seed cpet",
        [{"name": "park.fit"}],
        str(cpet_ws),
        subject_id=subject["id"],
    )

    inscyd_ws = data_dir / "workspaces" / "seed-inscyd"
    _write_inscyd_report(
        inscyd_ws,
        {
            "meta": {"report_type": "inscyd"},
            "session": {"test_date": "2026-01-06", "test_type": "PPD"},
            "inscyd": {"vlamax_mmol_l_s": 0.53, "fatmax_watt": 150.0},
            "warnings": ["seed warning"],
        },
    )
    create_submission(
        db_path,
        "seed inscyd",
        [{"name": "park.pdf"}],
        str(inscyd_ws),
        subject_id=subject["id"],
    )

    result = backfill_subject_metric_snapshots(db_path)
    assert result["inserted"] == 2

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM subject_metric_snapshots ORDER BY source_kind ASC"
    ).fetchall()
    conn.close()
    return dict(rows[0]), dict(rows[1])


def _login_as_researcher(client: TestClient, google_id: str = "snapshots-gid") -> dict:
    db_path = app.state.db_path
    user = upsert_user(
        db_path,
        google_id=google_id,
        email=f"{google_id}@example.com",
        display_name="Snapshot Researcher",
    )
    complete_onboarding(db_path, user["id"], "Snapshot Researcher")
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
                "name": "Snapshot Researcher",
                "picture": "",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)
    return user


class TestSubjectMetricSnapshotsExplorer:
    def setup_method(self) -> None:
        self.tmp_dir = None

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

    def test_manage_snapshots_tab_renders_explorer_table(self, tmp_path: Path) -> None:
        db_path = self._setup_app(tmp_path)
        _seed_snapshot_rows(db_path, app.state.data_dir)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as_researcher(client)

        resp = client.get("/manage?tab=snapshots")

        assert resp.status_code == 200
        assert "Snapshot Explorer" in resp.text
        assert "Geunyun Park" in resp.text
        assert "cpet_submission" in resp.text
        assert "inscyd_report" in resp.text

    def test_snapshots_partial_filters_by_source_kind(self, tmp_path: Path) -> None:
        db_path = self._setup_app(tmp_path)
        _seed_snapshot_rows(db_path, app.state.data_dir)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as_researcher(client)

        resp = client.get("/api/manage/snapshots?source_kind=inscyd_report")

        assert resp.status_code == 200
        assert "inscyd_report" in resp.text
        assert "cpet_submission" not in resp.text

    def test_snapshot_detail_partial_renders_payload_and_flags(self, tmp_path: Path) -> None:
        db_path = self._setup_app(tmp_path)
        _, inscyd_row = _seed_snapshot_rows(db_path, app.state.data_dir)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as_researcher(client)

        resp = client.get(f"/api/manage/snapshots/{inscyd_row['snapshot_id']}")

        assert resp.status_code == 200
        assert inscyd_row["snapshot_id"] in resp.text
        assert "seed warning" in resp.text
        assert "missing_vo2max_ml" in resp.text
        assert "inscyd_report" in resp.text
        assert "inscyd_snapshot_v1" in resp.text
