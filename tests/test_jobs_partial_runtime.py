from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.db import create_job, create_submission, init_db, upsert_report_catalog_entry
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
    resp = client.get("/api/jobs/partial?group_by=subject")
    assert resp.status_code == 200


def test_jobs_partial_renders_db_job_rows() -> None:
    db_path = app.state.db_path
    create_submission(
        db_path,
        description="runtime partial",
        file_manifest=[],
        workspace_path="/tmp/runtime-partial",
        subject_name="Runtime Subject",
        test_date="2026-04-01",
        submission_id="sub-runtime-1",
    )
    create_job(db_path, "sub-runtime-1")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/jobs/partial?group_by=subject")

    assert resp.status_code == 200
    assert "Runtime Subject" in resp.text
    assert 'data-status="pending"' in resp.text


def test_jobs_partial_renders_catalog_rows_without_jobs(tmp_path: Path) -> None:
    published_dir = app.state.published_dir
    (published_dir / "standalone-report").mkdir(parents=True, exist_ok=True)
    (published_dir / "standalone-report" / "index.html").write_text(
        """<!doctype html>
        <html><head><title>Standalone</title></head>
        <body>
        <script id="report-data" type="application/json">{"subject":{"name":"Standalone Subject"},"session":{"test_date":"2026-04-01"},"meta":{"analysis_method":"기본 CPET"}}</script>
        </body></html>
        """,
        encoding="utf-8",
    )

    upsert_report_catalog_entry(
        app.state.db_path,
        report_slug="standalone-report",
        subject_name="Standalone Subject",
        test_date="2026-04-01",
        analysis_method="기본 CPET",
        report_version="v1",
        report_url="/report/standalone-report/",
        completed_at="2026-04-01T00:00:00+00:00",
        file_tags=["CPET"],
    )

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/jobs/partial?group_by=subject")

    assert resp.status_code == 200
    assert "Standalone Subject" in resp.text
    assert "/report/standalone-report/" in resp.text


def test_jobs_partial_groups_rows_by_subject_name() -> None:
    db_path = app.state.db_path
    create_submission(
        db_path,
        description="group beta",
        file_manifest=[],
        workspace_path="/tmp/group-beta",
        subject_name="Beta",
        test_date="2026-04-01",
        submission_id="sub-group-beta",
    )
    create_job(db_path, "sub-group-beta")

    create_submission(
        db_path,
        description="group alpha 1",
        file_manifest=[],
        workspace_path="/tmp/group-alpha-1",
        subject_name="Alpha",
        test_date="2026-04-03",
        submission_id="sub-group-alpha-1",
    )
    create_job(db_path, "sub-group-alpha-1")

    create_submission(
        db_path,
        description="group alpha 2",
        file_manifest=[],
        workspace_path="/tmp/group-alpha-2",
        subject_name="Alpha",
        test_date="2026-04-02",
        submission_id="sub-group-alpha-2",
    )
    create_job(db_path, "sub-group-alpha-2")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/jobs/partial?group_by=subject")

    assert resp.status_code == 200
    assert resp.text.count("피험자 그룹") >= 2
    first_alpha = resp.text.index("Alpha")
    second_alpha = resp.text.index("Alpha", first_alpha + 1)
    beta = resp.text.index("Beta")
    assert first_alpha < second_alpha
    assert beta > second_alpha
