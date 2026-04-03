from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.db import (
    create_job,
    create_subject,
    create_submission,
    init_db,
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
    user_beta = upsert_user(db_path, "group-beta-gid", "beta@test.com", "Beta User")
    user_alpha = upsert_user(db_path, "group-alpha-gid", "alpha@test.com", "Alpha User")
    beta_subject = create_subject(db_path, "김금현")
    alpha_subject = create_subject(db_path, "이정인")
    link_user_to_subject(db_path, user_beta["id"], beta_subject["id"])
    link_user_to_subject(db_path, user_alpha["id"], alpha_subject["id"])
    create_submission(
        db_path,
        description="group beta",
        file_manifest=[],
        workspace_path="/tmp/group-beta",
        subject_name="Third Subject",
        test_date="2026-04-01",
        submission_id="sub-group-beta",
        user_id=user_beta["id"],
    )
    create_job(db_path, "sub-group-beta")

    create_submission(
        db_path,
        description="group alpha 1",
        file_manifest=[],
        workspace_path="/tmp/group-alpha-1",
        subject_name="First Subject",
        test_date="2026-04-03",
        submission_id="sub-group-alpha-1",
        user_id=user_alpha["id"],
    )
    create_job(db_path, "sub-group-alpha-1")

    create_submission(
        db_path,
        description="group alpha 2",
        file_manifest=[],
        workspace_path="/tmp/group-alpha-2",
        subject_name="Second Subject",
        test_date="2026-04-02",
        submission_id="sub-group-alpha-2",
        user_id=user_alpha["id"],
    )
    create_job(db_path, "sub-group-alpha-2")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/jobs/partial?group_by=subject")

    assert resp.status_code == 200
    assert "이정인" in resp.text
    assert "김금현" in resp.text
    assert "First Subject" not in resp.text
    assert "Second Subject" not in resp.text
    alpha_group = resp.text.index("이정인")
    alpha_first = resp.text.index("2026-04-03", alpha_group)
    alpha_second = resp.text.index("2026-04-02", alpha_first + 1)
    beta_group = resp.text.index("김금현")
    assert alpha_group < alpha_first < alpha_second
    assert beta_group > alpha_second or beta_group < alpha_group
