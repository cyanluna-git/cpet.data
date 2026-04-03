"""
tests/test_manage.py — Tests for the /manage admin page.

Covers:
    - DB functions: list_users, update_user_role, list_submissions_with_users,
      link_submission_user, unlink_submission_user
    - Access control: only researcher/admin can access /manage
    - GET /manage page rendering (users tab, submissions tab)
    - PATCH /api/manage/users/{id}/role (role changes, permission checks)
    - PATCH /api/manage/submissions/{id}/link (link submission to user)
    - DELETE /api/manage/submissions/{id}/link (unlink submission)
    - Navigation: '관리' link visible only for researcher/admin
    - Auto-matching suggestion logic
"""

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
    get_subject,
    get_report_name_overrides,
    get_report_notes,
    get_user,
    init_db,
    link_submission_user,
    list_submissions_with_users,
    list_users,
    set_report_note,
    unlink_submission_user,
    update_user_role,
    upsert_user,
    upsert_user_profile,
)
from server.main import _suggest_user_for_submission, app


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path, initialized."""
    path = tmp_path / "test_manage.db"
    init_db(path)
    return path


@pytest.fixture(autouse=True)
def _setup_app_state(tmp_path: Path) -> None:
    """Configure app.state to use temporary directories for each test."""
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
    """Provide a FastAPI TestClient."""
    return TestClient(app, raise_server_exceptions=False)


def _login_as(
    client: TestClient,
    role: str = "user",
    google_id: str = "test-gid",
    email: str = "test@example.com",
    name: str = "Test User",
) -> dict:
    """Simulate a Google OAuth login, set the user's role, and complete onboarding."""
    db_path = app.state.db_path
    user = upsert_user(db_path, google_id=google_id, email=email, display_name=name)
    complete_onboarding(db_path, user["id"], name)

    # Set role
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

    # Force-set the role in session (since upsert_user resets to DB role
    # but auth callback reads from upsert result which has old role before update)
    # We work around this by directly patching the session via the cookie
    user = get_user(db_path, user["id"])
    return user


def _create_test_submission(
    db_path: Path,
    subject_name: str = "Test Subject",
    test_date: str = "2025-01-15",
    user_id: str | None = None,
) -> str:
    """Create a test submission and return its ID."""
    return create_submission(
        db_path,
        description="test",
        file_manifest=[{"name": "test.xlsx"}],
        workspace_path="/tmp/test",
        subject_name=subject_name,
        test_date=test_date,
        user_id=user_id,
    )


# ── DB Function Tests ────────────────────────────────────────────────


class TestManageDB:
    def test_list_users_returns_all(self, db_path: Path) -> None:
        """list_users returns all users with profile data."""
        upsert_user(db_path, google_id="u1", email="u1@test.com", display_name="User 1")
        upsert_user(db_path, google_id="u2", email="u2@test.com", display_name="User 2")

        users = list_users(db_path)
        assert len(users) == 2
        emails = {u["email"] for u in users}
        assert "u1@test.com" in emails
        assert "u2@test.com" in emails

    def test_list_users_includes_profile_fields(self, db_path: Path) -> None:
        """list_users includes birth_year and gender from user_profiles."""
        user = upsert_user(db_path, google_id="p1", email="p1@test.com")
        upsert_user_profile(db_path, user["id"], birth_year=1990, gender="남성")

        users = list_users(db_path)
        assert len(users) == 1
        assert users[0]["birth_year"] == 1990
        assert users[0]["gender"] == "남성"

    def test_update_user_role(self, db_path: Path) -> None:
        """update_user_role changes the role and returns updated user."""
        user = upsert_user(db_path, google_id="r1", email="r1@test.com")
        assert user["role"] == "user"

        updated = update_user_role(db_path, user["id"], "researcher")
        assert updated is not None
        assert updated["role"] == "researcher"

    def test_update_user_role_invalid(self, db_path: Path) -> None:
        """update_user_role raises ValueError for invalid role."""
        user = upsert_user(db_path, google_id="r2", email="r2@test.com")
        with pytest.raises(ValueError, match="Invalid role"):
            update_user_role(db_path, user["id"], "superadmin")

    def test_update_user_role_not_found(self, db_path: Path) -> None:
        """update_user_role returns None for non-existent user."""
        result = update_user_role(db_path, "nonexistent-id", "admin")
        assert result is None

    def test_list_submissions_with_users(self, db_path: Path) -> None:
        """list_submissions_with_users returns submissions with linked user info."""
        user = upsert_user(db_path, google_id="s1", email="s1@test.com", display_name="Linked User")
        sid = _create_test_submission(db_path, user_id=user["id"])

        subs = list_submissions_with_users(db_path)
        assert len(subs) == 1
        assert subs[0]["id"] == sid
        assert subs[0]["linked_user_name"] == "Linked User"

    def test_list_submissions_with_null_user(self, db_path: Path) -> None:
        """list_submissions_with_users returns submissions with null user_id."""
        sid = _create_test_submission(db_path, user_id=None)

        subs = list_submissions_with_users(db_path)
        assert len(subs) == 1
        assert subs[0]["user_id"] is None
        assert subs[0]["linked_user_name"] is None

    def test_link_submission_user(self, db_path: Path) -> None:
        """link_submission_user links a submission to a user."""
        user = upsert_user(db_path, google_id="l1", email="l1@test.com")
        sid = _create_test_submission(db_path, user_id=None)

        result = link_submission_user(db_path, sid, user["id"])
        assert result is not None
        assert result["user_id"] == user["id"]

    def test_unlink_submission_user(self, db_path: Path) -> None:
        """unlink_submission_user removes the user link."""
        user = upsert_user(db_path, google_id="ul1", email="ul1@test.com")
        sid = _create_test_submission(db_path, user_id=user["id"])

        result = unlink_submission_user(db_path, sid)
        assert result is not None
        assert result["user_id"] is None

    def test_link_submission_not_found(self, db_path: Path) -> None:
        """link_submission_user returns None for non-existent submission."""
        result = link_submission_user(db_path, "nonexistent", "some-user")
        assert result is None

    def test_unlink_submission_not_found(self, db_path: Path) -> None:
        """unlink_submission_user returns None for non-existent submission."""
        result = unlink_submission_user(db_path, "nonexistent")
        assert result is None


# ── Auto-Matching Suggestion Tests ───────────────────────────────────


class TestSuggestUser:
    def test_exact_match(self) -> None:
        """Exact name match returns the user."""
        users = [{"id": "u1", "display_name": "홍길동"}]
        assert _suggest_user_for_submission("홍길동", users) == "u1"

    def test_case_insensitive_match(self) -> None:
        """Name matching is case-insensitive."""
        users = [{"id": "u1", "display_name": "John Doe"}]
        assert _suggest_user_for_submission("john doe", users) == "u1"

    def test_containment_match(self) -> None:
        """Containment-based matching works."""
        users = [{"id": "u1", "display_name": "박근윤"}]
        assert _suggest_user_for_submission("박근윤 선수", users) == "u1"

    def test_no_match(self) -> None:
        """Returns None when no reasonable match exists."""
        users = [{"id": "u1", "display_name": "김철수"}]
        assert _suggest_user_for_submission("이영희", users) is None

    def test_empty_subject(self) -> None:
        """Returns None for empty subject name."""
        users = [{"id": "u1", "display_name": "Test"}]
        assert _suggest_user_for_submission("", users) is None

    def test_no_users(self) -> None:
        """Returns None when no users exist."""
        assert _suggest_user_for_submission("Test", []) is None


# ── Access Control Tests ─────────────────────────────────────────────


class TestManageAccess:
    def test_anonymous_redirects_to_login(self, client: TestClient) -> None:
        """Anonymous user is redirected to login."""
        resp = client.get("/manage", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/google/login" in resp.headers["location"]

    def test_user_role_gets_403(self, client: TestClient) -> None:
        """User with role=user gets 403."""
        _login_as(client, role="user", google_id="user-gid", email="user@test.com")
        # Manually set session role since _login_as goes through OAuth which reads role before update
        # We need to set the session role correctly
        with client:
            # Access via a trick: set session directly
            resp = client.get("/manage")
            assert resp.status_code == 403

    def test_researcher_can_access(self, client: TestClient) -> None:
        """User with role=researcher can access /manage."""
        _login_as(client, role="researcher", google_id="res-gid", email="res@test.com")
        # We need to fix the session role
        db_path = app.state.db_path
        user = get_user(db_path, client.cookies.get("cpet_session") or "")
        # The session stores the old role. Let's re-login after setting the role.
        # Actually, the issue is the OAuth callback reads from upsert_user which doesn't re-read
        # the role we set. Let me fix the helper.

        # The _login_as helper sets the role AFTER OAuth login. The session stores the role
        # from the OAuth callback (which uses upsert_user's return). Since upsert_user for
        # returning users reads existing data, and we set the role BEFORE the callback via conn.execute,
        # but the login happens first in _login_as... Let me re-examine.
        # Actually _login_as: 1) upsert_user (creates with role=user), 2) complete_onboarding,
        # 3) UPDATE role, 4) OAuth callback (which calls upsert_user again, reading the updated role)
        # So the session SHOULD have the correct role. Let's just test it.
        resp = client.get("/manage")
        assert resp.status_code == 200

    def test_admin_can_access(self, client: TestClient) -> None:
        """User with role=admin can access /manage."""
        _login_as(client, role="admin", google_id="admin-gid", email="admin@test.com")
        resp = client.get("/manage")
        assert resp.status_code == 200


# ── Page Rendering Tests ─────────────────────────────────────────────


class TestManagePage:
    def test_users_tab_renders(self, client: TestClient) -> None:
        """GET /manage?tab=users renders the users table."""
        _login_as(client, role="admin", google_id="page-gid", email="page@test.com", name="Admin")
        resp = client.get("/manage?tab=users")
        assert resp.status_code == 200
        assert "유저 관리" in resp.text
        assert "Admin" in resp.text

    def test_submissions_tab_renders(self, client: TestClient) -> None:
        """GET /manage?tab=submissions renders the submissions table."""
        _login_as(client, role="admin", google_id="sub-gid", email="sub@test.com")
        db_path = app.state.db_path
        _create_test_submission(db_path, subject_name="Test Subject")

        resp = client.get("/manage?tab=submissions")
        assert resp.status_code == 200
        assert "검사 데이터 연결" in resp.text
        assert "Test Subject" in resp.text
        assert '<table class="min-w-full divide-y divide-gray-200">' in resp.text
        assert 'id="manage-submissions-body"' in resp.text
        assert 'id="manage-submissions-filters"' in resp.text
        assert 'name="submissions_unlinked_only"' in resp.text
        assert 'name="submissions_sort_by"' in resp.text
        assert "유저별로 묶어서 표시" in resp.text
        assert "변경" in resp.text

    def test_default_tab_is_users(self, client: TestClient) -> None:
        """GET /manage defaults to the users tab."""
        _login_as(client, role="researcher", google_id="def-gid", email="def@test.com")
        resp = client.get("/manage")
        assert resp.status_code == 200
        assert "유저 관리" in resp.text

    def test_users_tab_does_not_require_snapshot_or_feature_queries(self, client: TestClient) -> None:
        """Default/users tabs should render even if explorer queries fail."""
        _login_as(client, role="admin", google_id="safe-gid", email="safe@test.com", name="Safe Admin")
        with patch("server.main.list_subject_metric_snapshots", side_effect=RuntimeError("snapshots unavailable")):
            with patch("server.main.list_subject_feature_sets", side_effect=RuntimeError("feature sets unavailable")):
                with patch("server.main.summarize_subject_feature_sets", side_effect=RuntimeError("feature summary unavailable")):
                    resp = client.get("/manage?tab=users")

        assert resp.status_code == 200
        assert "유저 관리" in resp.text
        assert "Safe Admin" in resp.text

    def test_subjects_tab_shows_name_edit_controls_for_admin(self, client: TestClient) -> None:
        """Admin sees modal-based subject rename controls on the subjects tab."""
        _login_as(client, role="admin", google_id="subject-admin", email="subject-admin@test.com")
        db_path = app.state.db_path
        subject = create_subject(db_path, name="Old Subject Name")

        resp = client.get("/manage?tab=subjects")

        assert resp.status_code == 200
        assert f"openManageNameModal({{ mode: 'subject', subjectId: '{subject['id']}'" in resp.text
        assert "변경" in resp.text
        assert f'id="subj-name-{subject["id"]}"' not in resp.text


# ── Role Update API Tests ────────────────────────────────────────────


class TestRoleUpdateAPI:
    def test_admin_can_change_any_role(self, client: TestClient) -> None:
        """Admin can change a user's role to any valid role."""
        _login_as(client, role="admin", google_id="admin2-gid", email="admin2@test.com")
        db_path = app.state.db_path
        target = upsert_user(db_path, google_id="target-gid", email="target@test.com")
        complete_onboarding(db_path, target["id"], "Target")

        resp = client.patch(
            f"/api/manage/users/{target['id']}/role",
            data={"role": "admin"},
        )
        assert resp.status_code == 200

        updated = get_user(db_path, target["id"])
        assert updated is not None
        assert updated["role"] == "admin"


class TestManageSubjectsAPI:
    def test_admin_can_rename_subject_from_manage_api(self, client: TestClient) -> None:
        """Admin can update subject names through the manage subjects PATCH API."""
        _login_as(client, role="admin", google_id="subject-edit-gid", email="subject-edit@test.com")
        db_path = app.state.db_path
        subject = create_subject(db_path, name="Before Rename")

        resp = client.patch(
            f"/api/manage/subjects/{subject['id']}",
            data={"name": "After Rename"},
        )

        assert resp.status_code == 200
        updated = get_subject(db_path, subject["id"])
        assert updated is not None
        assert updated["name"] == "After Rename"
        assert "After Rename" in resp.text

    def test_researcher_cannot_rename_subject_from_manage_api(self, client: TestClient) -> None:
        """Only admins can rename subjects through the manage subjects PATCH API."""
        _login_as(client, role="researcher", google_id="subject-researcher-gid", email="subject-researcher@test.com")
        db_path = app.state.db_path
        subject = create_subject(db_path, name="Before Rename")

        resp = client.patch(
            f"/api/manage/subjects/{subject['id']}",
            data={"name": "After Rename"},
        )

        assert resp.status_code == 403
        updated = get_subject(db_path, subject["id"])
        assert updated is not None
        assert updated["name"] == "Before Rename"

    def test_admin_can_rename_submission_subject_name(self, client: TestClient) -> None:
        """Admin can rename a submission/report subject label through the rename API."""
        _login_as(client, role="admin", google_id="submission-rename-gid", email="submission-rename@test.com")
        db_path = app.state.db_path
        submission_id = _create_test_submission(db_path, subject_name="Before Subject")

        resp = client.patch(
            "/api/manage/rename-subject",
            data={"submission_id": submission_id, "subject_name": "After Subject"},
        )

        assert resp.status_code == 200
        from server.db import get_submission
        submission = get_submission(db_path, submission_id)
        assert submission is not None
        assert submission["subject_name"] == "After Subject"

    def test_researcher_cannot_rename_submission_subject_name(self, client: TestClient) -> None:
        """Only admins can rename submission/report subject labels."""
        _login_as(client, role="researcher", google_id="submission-rename-res-gid", email="submission-rename-res@test.com")
        db_path = app.state.db_path
        submission_id = _create_test_submission(db_path, subject_name="Before Subject")

        resp = client.patch(
            "/api/manage/rename-subject",
            data={"submission_id": submission_id, "subject_name": "After Subject"},
        )

        assert resp.status_code == 403
        from server.db import get_submission
        submission = get_submission(db_path, submission_id)
        assert submission is not None
        assert submission["subject_name"] == "Before Subject"

    def test_admin_can_update_report_metadata_from_dashboard(self, client: TestClient) -> None:
        """Admin can update both subject label and test note from report modal."""
        _login_as(client, role="admin", google_id="report-meta-admin-gid", email="report-meta-admin@test.com")
        db_path = app.state.db_path
        submission_id = _create_test_submission(db_path, subject_name="Before Subject")
        job_id = create_job(db_path, submission_id)
        conn = _connect(db_path)
        conn.execute(
            "UPDATE jobs SET status = ?, report_slug = ?, report_url = ? WHERE id = ?",
            ("done", "before-subject-20260115", "/report/before-subject-20260115/", job_id),
        )
        conn.commit()
        conn.close()

        resp = client.patch(
            "/api/manage/report-metadata",
            data={
                "submission_id": submission_id,
                "report_slug": "before-subject-20260115",
                "subject_name": "After Subject",
                "note": "2블럭 램프, 존2 후반",
            },
        )

        assert resp.status_code == 200
        from server.db import get_submission
        submission = get_submission(db_path, submission_id)
        assert submission is not None
        assert submission["subject_name"] == "After Subject"
        assert get_report_name_overrides(db_path)["before-subject-20260115"] == "After Subject"
        assert get_report_notes(db_path)["before-subject-20260115"] == "2블럭 램프, 존2 후반"

    def test_non_admin_cannot_update_other_users_report_metadata(self, client: TestClient) -> None:
        """Non-admin users cannot edit report metadata for unrelated reports."""
        _login_as(client, role="user", google_id="report-meta-user-gid", email="report-meta-user@test.com")
        db_path = app.state.db_path
        owner = upsert_user(db_path, google_id="report-meta-owner-gid", email="report-meta-owner@test.com", display_name="Owner User")
        submission_id = _create_test_submission(db_path, subject_name="Before Subject", user_id=owner["id"])

        forbidden = client.patch(
            "/api/manage/report-metadata",
            data={
                "submission_id": submission_id,
                "report_slug": "before-subject-20260115",
                "subject_name": "After Subject",
                "note": "이 메모는 저장되면 안됨",
            },
        )

        assert forbidden.status_code == 403

        note_resp = client.patch(
            "/api/report-note",
            data={
                "report_slug": "before-subject-20260115",
                "note": "남의 리포트 메모",
            },
        )
        assert note_resp.status_code == 403

    def test_non_admin_owner_can_update_note_but_not_subject_name(self, client: TestClient) -> None:
        """Owner can save note text but cannot rename subject labels."""
        owner = _login_as(client, role="user", google_id="report-meta-owner2-gid", email="report-meta-owner2@test.com")
        db_path = app.state.db_path
        submission_id = _create_test_submission(db_path, subject_name="Before Subject", user_id=owner["id"])

        forbidden = client.patch(
            "/api/manage/report-metadata",
            data={
                "submission_id": submission_id,
                "report_slug": "before-subject-20260115",
                "subject_name": "After Subject",
                "note": "이 메모는 저장되면 안됨",
            },
        )

        assert forbidden.status_code == 403

        ok = client.patch(
            "/api/manage/report-metadata",
            data={
                "submission_id": submission_id,
                "report_slug": "before-subject-20260115",
                "note": "식별 메모",
            },
        )

        assert ok.status_code == 200
        from server.db import get_submission
        submission = get_submission(db_path, submission_id)
        assert submission is not None
        assert submission["subject_name"] == "Before Subject"
        assert get_report_notes(db_path)["before-subject-20260115"] == "식별 메모"

    def test_jobs_partial_renders_edit_button_and_note_badge(self, client: TestClient) -> None:
        """Reports list shows one edit button and note badge instead of inline note editor."""
        _login_as(client, role="admin", google_id="report-partial-admin-gid", email="report-partial-admin@test.com")
        db_path = app.state.db_path
        submission_id = _create_test_submission(db_path, subject_name="Visible Subject")
        job_id = create_job(db_path, submission_id)
        conn = _connect(db_path)
        conn.execute(
            "UPDATE jobs SET status = ?, report_slug = ?, report_url = ? WHERE id = ?",
            ("done", "visible-subject-20260115", "/report/visible-subject-20260115/", job_id),
        )
        conn.commit()
        conn.close()
        set_report_note(db_path, "visible-subject-20260115", "프로토콜 식별 메모")

        resp = client.get("/api/jobs/partial")

        assert resp.status_code == 200
        assert "편집" in resp.text
        assert "프로토콜 식별 메모" in resp.text
        assert "+ 메모" not in resp.text
        assert "openNoteEdit" not in resp.text

    def test_submissions_partial_can_filter_unlinked_only_and_sort_by_name(self, client: TestClient) -> None:
        """Submissions partial supports unlinked-only filter and sort controls."""
        _login_as(client, role="admin", google_id="submission-filter-gid", email="submission-filter@test.com")
        db_path = app.state.db_path
        linked_user = upsert_user(db_path, google_id="linked-filter-user", email="linked-filter@test.com", display_name="Linked User")
        _create_test_submission(db_path, subject_name="Bravo Subject", test_date="2026-03-01", user_id=linked_user["id"])
        _create_test_submission(db_path, subject_name="Alpha Subject", test_date="2026-03-02", user_id=None)
        _create_test_submission(db_path, subject_name="Charlie Subject", test_date="2026-03-03", user_id=None)

        resp = client.get(
            "/api/manage/submissions",
            params={"submissions_unlinked_only": "1", "submissions_sort_by": "name_asc"},
        )

        assert resp.status_code == 200
        assert "Bravo Subject" not in resp.text
        alpha_idx = resp.text.index("Alpha Subject")
        charlie_idx = resp.text.index("Charlie Subject")
        assert alpha_idx < charlie_idx

    def test_submissions_partial_groups_rows_by_linked_user(self, client: TestClient) -> None:
        """Submissions partial inserts group headers per linked user and unlinked bucket."""
        _login_as(client, role="admin", google_id="submission-group-gid", email="submission-group@test.com")
        db_path = app.state.db_path
        user_a = upsert_user(db_path, google_id="group-a", email="group-a@test.com", display_name="Alpha User")
        user_b = upsert_user(db_path, google_id="group-b", email="group-b@test.com", display_name="Beta User")
        _create_test_submission(db_path, subject_name="First Subject", test_date="2026-03-01", user_id=user_a["id"])
        _create_test_submission(db_path, subject_name="Second Subject", test_date="2026-03-02", user_id=user_a["id"])
        _create_test_submission(db_path, subject_name="Third Subject", test_date="2026-03-03", user_id=user_b["id"])
        _create_test_submission(db_path, subject_name="Unlinked Subject", test_date="2026-03-04", user_id=None)

        resp = client.get("/api/manage/submissions")

        assert resp.status_code == 200
        assert "Alpha User" in resp.text
        assert "Beta User" in resp.text
        assert "미연결 검사" in resp.text
        assert "유저별로 묶어서 표시" in resp.text

    def test_researcher_can_toggle_user_researcher(self, client: TestClient) -> None:
        """Researcher can change between user and researcher roles."""
        _login_as(client, role="researcher", google_id="res2-gid", email="res2@test.com")
        db_path = app.state.db_path
        target = upsert_user(db_path, google_id="target2-gid", email="target2@test.com")

        resp = client.patch(
            f"/api/manage/users/{target['id']}/role",
            data={"role": "researcher"},
        )
        assert resp.status_code == 200

        updated = get_user(db_path, target["id"])
        assert updated is not None
        assert updated["role"] == "researcher"

    def test_researcher_cannot_set_admin(self, client: TestClient) -> None:
        """Researcher cannot assign admin role."""
        _login_as(client, role="researcher", google_id="res3-gid", email="res3@test.com")
        db_path = app.state.db_path
        target = upsert_user(db_path, google_id="target3-gid", email="target3@test.com")

        resp = client.patch(
            f"/api/manage/users/{target['id']}/role",
            data={"role": "admin"},
        )
        assert resp.status_code == 403

    def test_anonymous_cannot_update_role(self, client: TestClient) -> None:
        """Anonymous user cannot update roles."""
        resp = client.patch(
            "/api/manage/users/some-id/role",
            data={"role": "admin"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/auth/google/login" in resp.headers["location"]

    def test_invalid_role_returns_400(self, client: TestClient) -> None:
        """Invalid role returns 400."""
        _login_as(client, role="admin", google_id="inv-gid", email="inv@test.com")
        db_path = app.state.db_path
        target = upsert_user(db_path, google_id="inv-target", email="inv-target@test.com")

        resp = client.patch(
            f"/api/manage/users/{target['id']}/role",
            data={"role": "superadmin"},
        )
        assert resp.status_code == 400


# ── Submission Link/Unlink API Tests ─────────────────────────────────


class TestSubmissionLinkAPI:
    def test_link_submission_to_user(self, client: TestClient) -> None:
        """PATCH /api/manage/submissions/{id}/link links a submission."""
        _login_as(client, role="admin", google_id="link-gid", email="link@test.com")
        db_path = app.state.db_path
        target_user = upsert_user(db_path, google_id="link-user", email="link-user@test.com")
        sid = _create_test_submission(db_path, user_id=None)

        resp = client.patch(
            f"/api/manage/submissions/{sid}/link",
            data={"user_id": target_user["id"]},
        )
        assert resp.status_code == 200

        from server.db import get_submission
        sub = get_submission(db_path, sid)
        assert sub is not None
        assert sub["user_id"] == target_user["id"]

    def test_unlink_submission(self, client: TestClient) -> None:
        """DELETE /api/manage/submissions/{id}/link unlinks a submission."""
        _login_as(client, role="admin", google_id="unlink-gid", email="unlink@test.com")
        db_path = app.state.db_path
        target_user = upsert_user(db_path, google_id="unlink-user", email="unlink-user@test.com")
        sid = _create_test_submission(db_path, user_id=target_user["id"])

        resp = client.delete(f"/api/manage/submissions/{sid}/link")
        assert resp.status_code == 200

        from server.db import get_submission
        sub = get_submission(db_path, sid)
        assert sub is not None
        assert sub["user_id"] is None

    def test_link_missing_user_id_returns_400(self, client: TestClient) -> None:
        """Missing user_id in link request returns 400."""
        _login_as(client, role="admin", google_id="miss-gid", email="miss@test.com")
        db_path = app.state.db_path
        sid = _create_test_submission(db_path)

        resp = client.patch(
            f"/api/manage/submissions/{sid}/link",
            data={"user_id": ""},
        )
        assert resp.status_code == 400

    def test_link_nonexistent_submission_returns_404(self, client: TestClient) -> None:
        """Linking a non-existent submission returns 404."""
        _login_as(client, role="admin", google_id="ne-gid", email="ne@test.com")
        resp = client.patch(
            "/api/manage/submissions/nonexistent/link",
            data={"user_id": "some-user"},
        )
        # SQLite UPDATE on non-existent row succeeds silently, SELECT returns None
        assert resp.status_code == 404

    def test_anonymous_cannot_link(self, client: TestClient) -> None:
        """Anonymous user cannot link submissions."""
        resp = client.patch(
            "/api/manage/submissions/some-id/link",
            data={"user_id": "some-user"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/auth/google/login" in resp.headers["location"]


# ── Navigation Visibility Tests ──────────────────────────────────────


class TestManageNavigation:
    def test_nav_visible_for_admin(self, client: TestClient) -> None:
        """Admin sees '관리' link in navigation."""
        _login_as(client, role="admin", google_id="nav-admin", email="nav-admin@test.com")
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "관리</a>" in resp.text

    def test_nav_visible_for_researcher(self, client: TestClient) -> None:
        """Researcher sees '관리' link in navigation."""
        _login_as(client, role="researcher", google_id="nav-res", email="nav-res@test.com")
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "관리</a>" in resp.text

    def test_nav_hidden_for_user(self, client: TestClient) -> None:
        """Regular user does not see '관리' link."""
        _login_as(client, role="user", google_id="nav-user", email="nav-user@test.com")
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "관리</a>" not in resp.text

    def test_nav_hidden_for_anonymous(self, client: TestClient) -> None:
        """Anonymous visitor does not see '관리' link."""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "관리</a>" not in resp.text
