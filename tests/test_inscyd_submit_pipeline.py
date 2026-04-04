import io
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from pipeline.cli import main as pipeline_main
from server.api import _run_pipeline_job
from server.db import (
    _connect,
    complete_onboarding,
    get_job,
    get_submission,
    init_db,
    list_jobs,
    list_report_catalog,
    upsert_user,
)
from server.main import app


FIXTURES_DIR = Path(__file__).parent / "fixtures"
INSCYD_RAW_DIR = FIXTURES_DIR / "inscyd_ppd" / "raw"


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


def _load_inscyd_raw_files() -> list[tuple[str, tuple[str, io.BytesIO, str]]]:
    files: list[tuple[str, tuple[str, io.BytesIO, str]]] = []
    for path in sorted(INSCYD_RAW_DIR.iterdir()):
        if path.is_file():
            files.append(
                ("files", (path.name, io.BytesIO(path.read_bytes()), "application/octet-stream"))
            )
    return files


def _login_as(
    client: TestClient,
    *,
    role: str = "user",
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


@patch("server.api.notify_channel", new_callable=AsyncMock)
def test_submit_accepts_standalone_inscyd_workspace(
    mock_channel: AsyncMock,
    client: TestClient,
) -> None:
    _login_as(
        client,
        role="user",
        google_id="inscyd-submit-gid",
        email="inscyd-submit@test.com",
        name="INSCYD Submitter",
    )

    resp = client.post(
        "/api/submit",
        files=_load_inscyd_raw_files(),
        data={
            "description": "inscyd upload",
            "subject_name": "Geunyun Park",
            "test_date": "2026-01-06",
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    mock_channel.assert_awaited_once()

    job = get_job(app.state.db_path, body["job_id"])
    assert job is not None
    submission = get_submission(app.state.db_path, job["submission_id"])
    assert submission is not None
    assert submission["source_signature"] == "FIT+INSCYD+ZWO"
    payload = mock_channel.await_args.args[1]
    assert payload["analysis_mode"] == "standalone_inscyd"
    assert payload["report_type_hint"] == "inscyd"
    assert sorted(payload["file_tags"]) == ["FIT", "INSCYD", "ZWO"]

    workspace = Path(submission["workspace_path"])
    assert (workspace / "raw" / "KY Park_2026.pdf").is_file()
    assert (workspace / "raw" / "2026-01-06-10-29-23.fit").is_file()
    assert (workspace / "raw" / "Power_Performance_Decoder___V3.zwo").is_file()


@patch("server.api.notify_channel", new_callable=AsyncMock)
def test_run_pipeline_job_routes_pdf_workspace_to_inscyd_report(
    mock_channel: AsyncMock,
    client: TestClient,
) -> None:
    _login_as(
        client,
        role="user",
        google_id="inscyd-fallback-gid",
        email="inscyd-fallback@test.com",
        name="INSCYD Fallback",
    )

    resp = client.post(
        "/api/submit",
        files=_load_inscyd_raw_files(),
        data={
            "description": "inscyd fallback",
            "subject_name": "Geunyun Park",
            "test_date": "2026-01-06",
        },
    )
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    job = get_job(app.state.db_path, job_id)
    assert job is not None
    submission = get_submission(app.state.db_path, job["submission_id"])
    assert submission is not None

    _run_pipeline_job(
        app.state.db_path,
        job_id=str(job["id"]),
        submission_id=str(submission["id"]),
        workspace_path=str(submission["workspace_path"]),
        subject_name="Geunyun Park",
        test_date="2026-01-06",
        publish_dir=Path(app.state.published_dir),
        data_dir=app.state.data_dir,
    )

    refreshed = get_job(app.state.db_path, job_id)
    assert refreshed is not None
    assert refreshed["status"] == "done"
    assert refreshed["report_slug"]
    assert refreshed["report_url"] == f"/report/{refreshed['report_slug']}/"

    published_dir = Path(app.state.published_dir) / str(refreshed["report_slug"])
    assert (published_dir / "index.html").is_file()
    assert (published_dir / "original-inscyd-report.pdf").is_file()

    catalog = list_report_catalog(app.state.db_path)
    row = next(item for item in catalog if item["report_slug"] == refreshed["report_slug"])
    assert row["analysis_method"] == "INSCYD 해설 리포트"
    assert "INSCYD" in (row.get("file_tags") or [])


def test_pipeline_cli_auto_routes_standalone_inscyd_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "inscyd-workspace"
    workspace.mkdir(parents=True)
    raw_dir = workspace / "raw"
    shutil.copytree(INSCYD_RAW_DIR, raw_dir)

    code = pipeline_main(["--workspace", str(workspace)])

    assert code == 0
    assert (workspace / "report" / "index.html").is_file()
    assert not (workspace / "analysis.db").exists()
    html = (workspace / "report" / "index.html").read_text(encoding="utf-8")
    assert "INSCYD Interpretation Report" in html
    assert 'id="report-data"' in html
    assert "&quot;report_type&quot;: &quot;inscyd&quot;" in html


@patch("server.api.notify_channel", new_callable=AsyncMock)
def test_jobs_polling_reconciles_inscyd_report_metadata(
    mock_channel: AsyncMock,
    client: TestClient,
) -> None:
    _login_as(
        client,
        role="user",
        google_id="inscyd-reconcile-gid",
        email="inscyd-reconcile@test.com",
        name="INSCYD Reconcile",
    )

    resp = client.post(
        "/api/submit",
        files=_load_inscyd_raw_files(),
        data={
            "description": "inscyd reconcile",
            "subject_name": "Geunyun Park",
            "test_date": "2026-01-06",
        },
    )
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    job = get_job(app.state.db_path, job_id)
    assert job is not None
    submission = get_submission(app.state.db_path, job["submission_id"])
    assert submission is not None

    code = pipeline_main(["--workspace", str(submission["workspace_path"])])
    assert code == 0

    jobs = client.get("/api/jobs").json()
    row = next(item for item in jobs if item["id"] == job_id)
    assert row["status"] == "done"
    assert row["analysis_method"] == "INSCYD 해설 리포트"
    assert row["report_slug"]
    assert row["report_url"] == f"/report/{row['report_slug']}/"

    published_dir = Path(app.state.published_dir) / str(row["report_slug"])
    assert (published_dir / "index.html").is_file()

    catalog = list_report_catalog(app.state.db_path)
    catalog_row = next(item for item in catalog if item["report_slug"] == row["report_slug"])
    assert catalog_row["analysis_method"] == "INSCYD 해설 리포트"
    assert "INSCYD" in (catalog_row.get("file_tags") or [])
