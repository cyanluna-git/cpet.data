import io
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
    link_user_to_subject,
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


def _make_file(
    name: str,
    content: bytes = b"fake-content",
) -> tuple[str, tuple[str, io.BytesIO, str]]:
    return ("files", (name, io.BytesIO(content), "application/octet-stream"))


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
def test_submit_preflight_detects_exact_duplicate(
    mock_channel: AsyncMock,
    client: TestClient,
) -> None:
    _login_as(
        client,
        role="user",
        google_id="dup-preflight-gid",
        email="dup-preflight@test.com",
        name="Duplicate User",
    )

    first = client.post(
        "/api/submit",
        files=[_make_file("cosmed.xlsx", b"cosmed-123"), _make_file("ride.fit", b"fit-123")],
        data={"description": "first", "test_date": "2026-04-03"},
    )
    assert first.status_code == 201

    resp = client.post(
        "/api/submit/preflight",
        files=[_make_file("cosmed.xlsx", b"cosmed-123"), _make_file("ride.fit", b"fit-123")],
        data={"test_date": "2026-04-03"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["has_duplicates"] is True
    assert payload["source_signature"] == "CPET+FIT"
    assert payload["submission_fingerprint"]
    assert payload["duplicates"]
    assert payload["duplicates"][0]["confidence"] == "exact"


@patch("server.api.notify_channel", new_callable=AsyncMock)
def test_submit_rejects_duplicate_without_override(
    mock_channel: AsyncMock,
    client: TestClient,
) -> None:
    _login_as(
        client,
        role="user",
        google_id="dup-reject-gid",
        email="dup-reject@test.com",
        name="Duplicate Reject User",
    )

    first = client.post(
        "/api/submit",
        files=[_make_file("cosmed.xlsx", b"same-cosmed")],
        data={"description": "first", "test_date": "2026-04-03"},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/submit",
        files=[_make_file("cosmed.xlsx", b"same-cosmed")],
        data={"description": "second", "test_date": "2026-04-03"},
    )

    assert second.status_code == 409
    payload = second.json()
    assert payload["error"] == "duplicate candidates found"
    assert payload["duplicates"]


@patch("server.api.notify_channel", new_callable=AsyncMock)
def test_submit_allows_duplicate_with_override(
    mock_channel: AsyncMock,
    client: TestClient,
) -> None:
    _login_as(
        client,
        role="user",
        google_id="dup-override-gid",
        email="dup-override@test.com",
        name="Duplicate Override User",
    )

    first = client.post(
        "/api/submit",
        files=[_make_file("cosmed.xlsx", b"same-cosmed"), _make_file("ride.fit", b"same-fit")],
        data={"description": "first", "test_date": "2026-04-03"},
    )
    assert first.status_code == 201

    second = client.post(
        "/api/submit",
        files=[_make_file("cosmed.xlsx", b"same-cosmed"), _make_file("ride.fit", b"same-fit")],
        data={"description": "second", "test_date": "2026-04-03", "override_duplicates": "1"},
    )

    assert second.status_code == 201
    db_path = app.state.db_path
    second_job = second.json()["job_id"]
    conn = _connect(db_path)
    row = conn.execute(
        """
        SELECT s.*
          FROM submissions s
          JOIN jobs j ON j.submission_id = s.id
         WHERE j.id = ?
        """,
        (second_job,),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["submission_fingerprint"]
    assert row["duplicate_confidence"] == "exact"
    assert row["duplicate_group_key"]


def test_manage_submissions_shows_duplicate_badge_and_cluster_panel(client: TestClient) -> None:
    _login_as(
        client,
        role="admin",
        google_id="dup-manage-gid",
        email="dup-manage@test.com",
        name="Duplicate Manage Admin",
    )
    db_path = app.state.db_path
    user = upsert_user(db_path, google_id="dup-owner", email="dup-owner@test.com", display_name="Owner")
    subject = create_subject(db_path, "홍상선")
    link_user_to_subject(db_path, user["id"], subject["id"])

    common = {
        "description": "dup",
        "file_manifest": [{"name": "cosmed.xlsx", "extension": "xlsx"}],
        "test_date": "2026-03-19",
        "user_id": user["id"],
        "subject_id": subject["id"],
        "source_signature": "CPET",
        "submission_fingerprint": "fingerprint-123",
        "duplicate_confidence": "exact",
        "duplicate_group_key": "dup-group-123",
    }
    sub1 = create_submission(
        db_path,
        workspace_path="/tmp/dup-manage-1",
        subject_name="홍상선",
        submission_id="dup-manage-1",
        **common,
    )
    sub2 = create_submission(
        db_path,
        workspace_path="/tmp/dup-manage-2",
        subject_name="홍상선",
        submission_id="dup-manage-2",
        **common,
    )
    create_job(db_path, sub1)
    create_job(db_path, sub2)

    resp = client.get("/api/manage/submissions", params={"submissions_duplicate_only": "1"})
    assert resp.status_code == 200
    assert "중복 일치 2건" in resp.text

    cluster = client.get("/api/manage/submissions/duplicates", params={"group_key": "exact:fingerprint-123"})
    assert cluster.status_code == 200
    assert "중복 cluster 비교" in cluster.text
    assert "대표 추천" in cluster.text


def test_jobs_partial_shows_duplicate_badge_for_grouped_reports() -> None:
    db_path = app.state.db_path
    user = upsert_user(db_path, "dup-group-gid", "dup-group@test.com", "Owner")
    subject = create_subject(db_path, "이정인")
    link_user_to_subject(db_path, user["id"], subject["id"])

    sub1 = create_submission(
        db_path,
        description="dup1",
        file_manifest=[],
        workspace_path="/tmp/dup-group-1",
        subject_name="First Subject",
        test_date="2026-04-03",
        submission_id="dup-group-1",
        user_id=user["id"],
        subject_id=subject["id"],
        source_signature="CPET",
        submission_fingerprint="same-fingerprint",
        duplicate_confidence="exact",
        duplicate_group_key="dup-group-key",
    )
    sub2 = create_submission(
        db_path,
        description="dup2",
        file_manifest=[],
        workspace_path="/tmp/dup-group-2",
        subject_name="Second Subject",
        test_date="2026-04-02",
        submission_id="dup-group-2",
        user_id=user["id"],
        subject_id=subject["id"],
        source_signature="CPET",
        submission_fingerprint="same-fingerprint",
        duplicate_confidence="exact",
        duplicate_group_key="dup-group-key",
    )
    create_job(db_path, sub1)
    create_job(db_path, sub2)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/jobs/partial?group_by=subject")

    assert resp.status_code == 200
    assert "중복 일치 2건" in resp.text
    assert 'data-duplicate="1"' in resp.text
