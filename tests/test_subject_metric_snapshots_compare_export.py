"""
tests/test_subject_metric_snapshots_compare_export.py — Compare/export tests.
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


def _login_as_researcher(client: TestClient, google_id: str = "snapshot-compare-gid") -> None:
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


def _fetch_snapshot_rows(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM subject_metric_snapshots ORDER BY measured_at ASC, source_kind ASC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _seed_compare_rows(db_path: Path, data_dir: Path) -> tuple[dict, dict]:
    subject = create_subject(db_path, name="Geunyun Park")

    ws1 = data_dir / "workspaces" / "compare-cpet-1"
    _create_analysis_db(
        ws1,
        "2026-02-01",
        metrics={
            "vo2max": {"vo2max_rel": 57.2},
            "substrate": {"fatmax_power_w": 135.0},
        },
    )
    create_submission(
        db_path,
        "compare cpet 1",
        [{"name": "park-1.fit"}],
        str(ws1),
        subject_id=subject["id"],
    )

    ws2 = data_dir / "workspaces" / "compare-cpet-2"
    _create_analysis_db(
        ws2,
        "2026-03-20",
        metrics={
            "vo2max": {"vo2max_rel": 60.7},
            "substrate": {"fatmax_power_w": 150.0},
        },
    )
    create_submission(
        db_path,
        "compare cpet 2",
        [{"name": "park-2.fit"}],
        str(ws2),
        subject_id=subject["id"],
    )

    result = backfill_subject_metric_snapshots(db_path)
    assert result["inserted"] == 2

    rows = _fetch_snapshot_rows(db_path)
    baseline_row = next(row for row in rows if row["measured_at"] == "2026-02-01")
    current_row = next(row for row in rows if row["measured_at"] == "2026-03-20")
    return baseline_row, current_row


def _seed_export_rows(db_path: Path, data_dir: Path) -> tuple[dict, dict]:
    subject = create_subject(db_path, name="Geunyun Park")

    cpet_ws = data_dir / "workspaces" / "export-cpet"
    _create_analysis_db(
        cpet_ws,
        "2026-03-20",
        metrics={
            "vo2max": {"vo2max_rel": 60.7},
            "substrate": {"fatmax_power_w": 145.0},
        },
    )
    create_submission(
        db_path,
        "export cpet",
        [{"name": "park.fit"}],
        str(cpet_ws),
        subject_id=subject["id"],
    )

    inscyd_ws = data_dir / "workspaces" / "export-inscyd"
    _write_inscyd_report(
        inscyd_ws,
        {
            "meta": {"report_type": "inscyd"},
            "session": {"test_date": "2026-01-06", "test_type": "PPD"},
            "inscyd": {
                "vlamax_mmol_l_s": 0.53,
                "fatmax_watt": 150.0,
                "vo2max_rel_ml_kg_min": 62.3,
            },
            "warnings": ["seed warning"],
        },
    )
    create_submission(
        db_path,
        "export inscyd",
        [{"name": "park.pdf"}],
        str(inscyd_ws),
        subject_id=subject["id"],
    )

    result = backfill_subject_metric_snapshots(db_path)
    assert result["inserted"] == 2

    rows = _fetch_snapshot_rows(db_path)
    cpet_row = next(row for row in rows if row["source_kind"] == "cpet_submission")
    inscyd_row = next(row for row in rows if row["source_kind"] == "inscyd_report")
    return cpet_row, inscyd_row


class TestSubjectMetricSnapshotsCompareExport:
    def test_compare_partial_renders_metric_deltas(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        baseline_row, current_row = _seed_compare_rows(db_path, app.state.data_dir)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as_researcher(client)

        resp = client.get(
            "/api/manage/snapshots/compare",
            params={
                "baseline_snapshot_id": baseline_row["snapshot_id"],
                "current_snapshot_id": current_row["snapshot_id"],
            },
        )

        assert resp.status_code == 200
        assert baseline_row["snapshot_id"] in resp.text
        assert current_row["snapshot_id"] in resp.text
        assert "VO2max" in resp.text
        assert "FatMax" in resp.text
        assert "3.5" in resp.text
        assert "15.0" in resp.text

    def test_export_csv_respects_filters(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        _, inscyd_row = _seed_export_rows(db_path, app.state.data_dir)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as_researcher(client)

        resp = client.get("/api/manage/snapshots/export.csv?source_kind=inscyd_report")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "inscyd_report" in resp.text
        assert "cpet_submission" not in resp.text
        assert inscyd_row["snapshot_id"] in resp.text

    def test_export_json_includes_filtered_snapshot_payload(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        _, inscyd_row = _seed_export_rows(db_path, app.state.data_dir)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as_researcher(client)

        resp = client.get("/api/manage/snapshots/export.json?source_kind=inscyd_report")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["filters"]["source_kind"] == "inscyd_report"
        assert body["snapshots"][0]["snapshot_id"] == inscyd_row["snapshot_id"]
        assert body["snapshots"][0]["source_kind"] == "inscyd_report"
        assert body["snapshots"][0]["quality_flags"]
        assert body["snapshots"][0]["payload"]["warnings"] == ["seed warning"]
