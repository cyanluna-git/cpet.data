import html
import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from server.db import (
    _connect,
    complete_onboarding,
    create_job,
    create_submission,
    create_subject,
    get_submission,
    init_db,
    link_report_to_user,
    link_user_to_subject,
    upsert_report_catalog_entry,
    upsert_user,
)
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


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _login_as(
    client: TestClient,
    *,
    role: str,
    google_id: str,
    email: str,
    name: str,
) -> dict:
    db_path = app.state.db_path
    user = upsert_user(db_path, google_id=google_id, email=email, display_name=name)
    complete_onboarding(db_path, user["id"], name)

    conn = _connect(db_path)
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user["id"]))
    conn.commit()
    conn.close()

    with patch(
        "server.auth.oauth.google.authorize_access_token",
        new_callable=AsyncMock,
    ) as mock_token:
        mock_token.return_value = {
            "userinfo": {
                "sub": google_id,
                "email": email,
                "name": name,
                "picture": "",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)
    return user


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
    for category, entries in (metrics or {}).items():
        for key, value in entries.items():
            value_text = json.dumps(value) if not isinstance(value, str) else value
            conn.execute(
                "INSERT OR REPLACE INTO analysis_results (category, key, value) VALUES (?, ?, ?)",
                (category, key, value_text),
            )
    conn.commit()
    conn.close()


def _write_report_html(report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "index.html").write_text("<html><body>report</body></html>", encoding="utf-8")


def _write_published_cpet_report(report_dir: Path, *, subject_name: str, test_date: str) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "subject": {"name": subject_name},
        "session": {"test_date": test_date, "protocol_name": "CPET"},
        "analysis": {
            "vo2max": {"vo2max_rel": 59.4},
            "lactate": {"lt1_fixed_power_w": 215.0},
            "substrate": {"fatmax_power_w": 148.0, "fatmax_gmin": 1.12},
        },
        "meta": {"analysis_method": "기본 CPET"},
    }
    escaped = html.escape(json.dumps(payload, ensure_ascii=False))
    (report_dir / "index.html").write_text(
        f"<html><body><script id=\"report-data\" type=\"application/json\">{escaped}</script></body></html>",
        encoding="utf-8",
    )


def _count_rows(db_path: Path, table: str, where: str = "", params: tuple = ()) -> int:
    conn = _connect(db_path)
    sql = f"SELECT COUNT(*) AS count FROM {table}"
    if where:
        sql += f" WHERE {where}"
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return int(row["count"] if row else 0)


def test_jobs_partial_reconcile_materializes_submission_metrics(client: TestClient, tmp_path: Path) -> None:
    db_path = app.state.db_path
    subject = create_subject(db_path, "홍상선")
    workspace = tmp_path / "workspace-reconcile"
    _create_analysis_db(
        workspace,
        "2026-04-04",
        metrics={
            "vo2max": {"vo2max_rel": 61.5},
            "lactate": {"lt1_fixed_power_w": 228.0},
            "substrate": {"fatmax_power_w": 152.0},
        },
    )
    _write_report_html(workspace / "report")

    submission_id = create_submission(
        db_path,
        description="reconcile me",
        file_manifest=[{"name": "cosmed.xlsx"}],
        workspace_path=str(workspace),
        subject_name="홍상선",
        test_date="2026-04-04",
        submission_id="reconcile-submission",
        subject_id=subject["id"],
    )
    create_job(db_path, submission_id)

    resp = client.get("/api/jobs/partial")
    assert resp.status_code == 200
    assert _count_rows(
        db_path,
        "subject_metric_snapshots",
        "source_ref_id = ?",
        (submission_id,),
    ) == 1
    assert _count_rows(
        db_path,
        "subject_feature_sets",
        "subject_id = ?",
        (subject["id"],),
    ) >= 1


def test_manage_link_report_materializes_standalone_metrics(client: TestClient, tmp_path: Path) -> None:
    admin = _login_as(
        client,
        role="admin",
        google_id="refresh-report-admin",
        email="refresh-report-admin@test.com",
        name="Refresh Admin",
    )
    db_path = app.state.db_path
    subject = create_subject(db_path, "김대순")
    link_user_to_subject(db_path, admin["id"], subject["id"])

    report_slug = "daesoon-standalone"
    _write_published_cpet_report(
        app.state.published_dir / report_slug,
        subject_name="김대순",
        test_date="2026-03-19",
    )
    upsert_report_catalog_entry(
        db_path,
        report_slug=report_slug,
        subject_name="김대순",
        test_date="2026-03-19",
        analysis_method="기본 CPET",
        report_version="v1",
        report_url=f"/report/{report_slug}/",
        completed_at="2026-03-19T00:00:00Z",
        file_tags=["CPET"],
    )

    resp = client.patch(
        f"/api/manage/link/{report_slug}",
        data={"user_id": admin["id"], "report_slug": report_slug},
    )
    assert resp.status_code == 200
    assert _count_rows(
        db_path,
        "subject_metric_snapshots",
        "source_ref_id = ? AND source_kind = 'published_cpet_report'",
        (report_slug,),
    ) == 1
    assert _count_rows(
        db_path,
        "subject_feature_sets",
        "subject_id = ?",
        (subject["id"],),
    ) >= 1

    resp = client.request(
        "DELETE",
        f"/api/manage/link/{report_slug}",
        data={"report_slug": report_slug},
    )
    assert resp.status_code == 200
    assert _count_rows(
        db_path,
        "subject_metric_snapshots",
        "source_ref_id = ? AND source_kind = 'published_cpet_report'",
        (report_slug,),
    ) == 0


def test_link_user_to_subject_refreshes_existing_sources(client: TestClient, tmp_path: Path) -> None:
    _login_as(
        client,
        role="admin",
        google_id="refresh-subject-admin",
        email="refresh-subject-admin@test.com",
        name="Refresh Subject Admin",
    )
    db_path = app.state.db_path
    target_user = upsert_user(
        db_path,
        google_id="target-user-gid",
        email="target-user@test.com",
        display_name="Target User",
    )
    subject = create_subject(db_path, "유양우")

    workspace = tmp_path / "workspace-link-subject"
    _create_analysis_db(
        workspace,
        "2026-03-14",
        metrics={
            "vo2max": {"vo2max_rel": 58.2},
            "lactate": {"lt1_fixed_power_w": 221.0},
            "substrate": {"fatmax_power_w": 144.0},
        },
    )
    submission_id = create_submission(
        db_path,
        description="subject-link-refresh",
        file_manifest=[{"name": "cosmed.xlsx"}],
        workspace_path=str(workspace),
        subject_name="유양우",
        test_date="2026-03-14",
        submission_id="subject-link-refresh-sub",
        user_id=target_user["id"],
    )

    report_slug = "yangwoo-standalone"
    _write_published_cpet_report(
        app.state.published_dir / report_slug,
        subject_name="유양우",
        test_date="2026-03-14",
    )
    upsert_report_catalog_entry(
        db_path,
        report_slug=report_slug,
        subject_name="유양우",
        test_date="2026-03-14",
        analysis_method="기본 CPET",
        report_version="v1",
        report_url=f"/report/{report_slug}/",
        completed_at="2026-03-14T00:00:00Z",
        file_tags=["CPET"],
    )
    link_report_to_user(db_path, report_slug, target_user["id"])

    resp = client.patch(
        f"/api/manage/subjects/{subject['id']}/link-user",
        data={"user_id": target_user["id"]},
    )
    assert resp.status_code == 200

    refreshed_submission = get_submission(db_path, submission_id)
    assert refreshed_submission is not None
    assert refreshed_submission["subject_id"] == subject["id"]
    assert _count_rows(
        db_path,
        "subject_metric_snapshots",
        "source_ref_id = ? AND source_kind = 'cpet_submission'",
        (submission_id,),
    ) == 1
    assert _count_rows(
        db_path,
        "subject_metric_snapshots",
        "source_ref_id = ? AND source_kind = 'published_cpet_report'",
        (report_slug,),
    ) == 1
    assert _count_rows(
        db_path,
        "subject_feature_sets",
        "subject_id = ?",
        (subject["id"],),
    ) >= 2
