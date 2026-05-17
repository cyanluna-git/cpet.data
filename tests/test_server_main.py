"""
tests/test_server_main.py — Unit tests for server.main helpers.

Currently focused on the reanalyze-button injection helpers introduced for
the reanalyze-only mode (kanban #2720):
    - _can_reanalyze_submission
    - _build_reanalyze_button_html
    - _inject_reanalyze_button
    - GET /report/<slug>/ button-injection authorization (integration)
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
    get_user,
    init_db,
    store_report_html,
    update_job_status,
    upsert_report_catalog_entry,
    upsert_user,
)
from server.main import (
    _build_reanalyze_button_html,
    _can_reanalyze_submission,
    _inject_reanalyze_button,
    app,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary, initialized platform DB."""
    path = tmp_path / "test_main.db"
    init_db(path)
    return path


# ── _can_reanalyze_submission ────────────────────────────────────────


class TestCanReanalyzeSubmission:
    """Authorization checks for the reanalyze button / endpoint."""

    def test_owner_can_reanalyze(self, db_path: Path) -> None:
        """The submission owner (matching user_id) is authorized."""
        session_user = {"id": "user-123", "role": "user"}
        submission = {"id": "sub-1", "user_id": "user-123"}
        assert _can_reanalyze_submission(db_path, session_user, submission) is True

    def test_researcher_can_reanalyze_anyone(self, db_path: Path) -> None:
        """Researchers can reanalyze any submission, even when not the owner."""
        session_user = {"id": "researcher-1", "role": "researcher"}
        submission = {"id": "sub-1", "user_id": "someone-else"}
        assert _can_reanalyze_submission(db_path, session_user, submission) is True

    def test_admin_can_reanalyze_anyone(self, db_path: Path) -> None:
        """Admins can reanalyze any submission."""
        session_user = {"id": "admin-1", "role": "admin"}
        submission = {"id": "sub-1", "user_id": "someone-else"}
        assert _can_reanalyze_submission(db_path, session_user, submission) is True

    def test_unrelated_user_cannot_reanalyze(self, db_path: Path) -> None:
        """A regular user that does not own the submission is denied."""
        session_user = {"id": "user-456", "role": "user"}
        submission = {"id": "sub-1", "user_id": "user-123"}
        assert _can_reanalyze_submission(db_path, session_user, submission) is False

    def test_session_without_id_cannot_reanalyze(self, db_path: Path) -> None:
        """A session user with no id falls through to False (defensive)."""
        session_user = {"id": "", "role": "user"}
        submission = {"id": "sub-1", "user_id": "user-123"}
        assert _can_reanalyze_submission(db_path, session_user, submission) is False

    def test_user_id_compared_as_strings(self, db_path: Path) -> None:
        """user_id comparison must coerce to string (defensive)."""
        session_user = {"id": "42", "role": "user"}
        submission = {"id": "sub-1", "user_id": 42}  # int — should still match
        assert _can_reanalyze_submission(db_path, session_user, submission) is True

    def test_submission_with_null_user_id_denies_regular_user(
        self, db_path: Path
    ) -> None:
        """A submission with no owner cannot be reanalyzed by an unrelated user."""
        session_user = {"id": "user-123", "role": "user"}
        submission = {"id": "sub-1", "user_id": None, "subject_id": None}
        assert _can_reanalyze_submission(db_path, session_user, submission) is False

    def test_subject_link_grants_reanalyze(self, db_path: Path) -> None:
        """A user whose subject_id matches the submission's subject_id is authorized.

        This is the post-refactor ownership model where submissions are linked
        to subjects rather than users directly (commit 08d8623).
        """
        with _connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute(
                "INSERT INTO users (id, google_id, email, role, subject_id) "
                "VALUES (?, ?, ?, ?, ?)",
                ("user-789", "g-789", "user789@example.com", "user", "subj-42"),
            )
            conn.commit()
        session_user = {"id": "user-789", "role": "user"}
        submission = {"id": "sub-1", "user_id": None, "subject_id": "subj-42"}
        assert _can_reanalyze_submission(db_path, session_user, submission) is True

    def test_subject_mismatch_denies_reanalyze(self, db_path: Path) -> None:
        """A user with a different subject_id cannot reanalyze the submission."""
        with _connect(db_path) as conn:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute(
                "INSERT INTO users (id, google_id, email, role, subject_id) "
                "VALUES (?, ?, ?, ?, ?)",
                ("user-other", "g-other", "other@example.com", "user", "subj-99"),
            )
            conn.commit()
        session_user = {"id": "user-other", "role": "user"}
        submission = {"id": "sub-1", "user_id": None, "subject_id": "subj-42"}
        assert _can_reanalyze_submission(db_path, session_user, submission) is False


# ── _build_reanalyze_button_html ─────────────────────────────────────


class TestBuildReanalyzeButtonHtml:
    def test_includes_submission_id_in_action(self) -> None:
        """The form action must point at /api/submit?reanalyze=<sid>."""
        html = _build_reanalyze_button_html("sub-abc-123")
        assert 'action="/api/submit?reanalyze=sub-abc-123"' in html

    def test_form_uses_post_and_multipart(self) -> None:
        """The form posts as multipart/form-data so empty submit works."""
        html = _build_reanalyze_button_html("sub-1")
        assert 'method="post"' in html
        assert 'enctype="multipart/form-data"' in html

    def test_button_label_is_korean_reanalyze(self) -> None:
        """The visible label should be Korean '재분석'."""
        html = _build_reanalyze_button_html("sub-1")
        assert "재분석" in html

    def test_quotes_in_submission_id_are_escaped(self) -> None:
        """Defensive: a raw double-quote in the id must not break the action attr."""
        html = _build_reanalyze_button_html('evil"id')
        # The raw quote must be escaped so the action attribute stays well-formed
        assert 'action="/api/submit?reanalyze=evil"id"' not in html
        assert "&quot;" in html


# ── _inject_reanalyze_button ─────────────────────────────────────────


class TestInjectReanalyzeButton:
    def test_injects_before_body_close(self) -> None:
        """The button HTML is inserted directly before the </body> tag."""
        html = "<html><body><h1>Report</h1></body></html>"
        result = _inject_reanalyze_button(html, "sub-1")
        assert "재분석" in result
        # Button appears before </body>, not after
        body_close = result.index("</body>")
        button_pos = result.index("재분석")
        assert button_pos < body_close

    def test_no_op_when_body_close_absent(self) -> None:
        """If </body> is missing, the input is returned unchanged (defensive)."""
        html = "<html><h1>No body tag</h1></html>"
        result = _inject_reanalyze_button(html, "sub-1")
        assert result == html

    def test_only_first_body_close_is_replaced(self) -> None:
        """If multiple </body> appear (rare), only the first is targeted."""
        html = "<html><body>A</body><body>B</body></html>"
        result = _inject_reanalyze_button(html, "sub-x")
        # Exactly one button injected
        assert result.count("재분석") == 1

    def test_double_call_inserts_two_buttons(self) -> None:
        """Documented behaviour: helper has no idempotency guard.

        Calling _inject_reanalyze_button twice on the same HTML produces
        two buttons. This is a defensive gap worth flagging — current
        callers gate the injection upstream so it does not occur in
        practice, but the helper itself does not protect against it.
        """
        html = "<html><body>X</body></html>"
        once = _inject_reanalyze_button(html, "sub-1")
        twice = _inject_reanalyze_button(once, "sub-1")
        assert twice.count("재분석") == 2

    def test_submission_id_appears_in_injected_form(self) -> None:
        """The injected form's action contains the submission id."""
        html = "<html><body>x</body></html>"
        result = _inject_reanalyze_button(html, "sub-xyz")
        assert "reanalyze=sub-xyz" in result


# ── GET /report/<slug>/ button-injection (integration) ───────────────


@pytest.fixture()
def report_client(tmp_path: Path) -> TestClient:
    """Wire app.state up against tmp dirs for a report-serving test."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "cpet_platform.db"
    init_db(db_file)
    app.state.db_path = db_file
    app.state.data_dir = data_dir
    app.state.channel_url = "http://127.0.0.1:9999"
    app.state.published_dir = tmp_path / "published"
    return TestClient(app, raise_server_exceptions=False)


def _login_as(
    client: TestClient,
    role: str = "user",
    google_id: str = "report-gid",
    email: str = "report@test.com",
    name: str = "Report User",
) -> dict:
    """Mock-OAuth-login + role-set helper (mirrors test_manage._login_as)."""
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
    return get_user(db_path, user["id"])


def _seed_published_report(
    db_path: Path,
    *,
    slug: str,
    owner_user_id: str,
    html: str = "<html><body><h1>Report</h1></body></html>",
) -> str:
    """Insert a submission + done job + report_catalog row with html_content.

    Returns the submission_id so callers can build owner-scoped sessions.
    """
    sid = create_submission(
        db_path,
        "seeded report submission",
        [{"name": "data.xlsx", "extension": "xlsx", "size_bytes": 5}],
        "/seeded/ws",
        subject_name="Park",
        test_date="2026-03-20",
        user_id=owner_user_id,
    )
    jid = create_job(db_path, sid)
    update_job_status(
        db_path,
        jid,
        "done",
        report_slug=slug,
        report_url=f"/report/{slug}/",
    )
    upsert_report_catalog_entry(
        db_path,
        report_slug=slug,
        subject_name="Park",
        test_date="2026-03-20",
        analysis_method="CPET",
        report_version="v1",
        report_url=f"/report/{slug}/",
        completed_at=None,
    )
    store_report_html(db_path, slug, html)
    return sid


class TestReportPageReanalyzeButton:
    """End-to-end: GET /report/<slug>/ injects the button only when authorized."""

    def test_owner_sees_button(self, report_client: TestClient) -> None:
        """The submission owner sees the 재분석 button."""
        owner = _login_as(
            report_client, role="user", google_id="r-owner", email="o@t.com"
        )
        _seed_published_report(
            app.state.db_path, slug="owner-slug", owner_user_id=owner["id"]
        )
        resp = report_client.get("/report/owner-slug/")
        assert resp.status_code == 200
        assert "재분석" in resp.text
        assert "/api/submit?reanalyze=" in resp.text

    def test_anonymous_does_not_see_button(self, report_client: TestClient) -> None:
        """Anonymous visitor never sees the button."""
        # Seed under some owner; the anonymous request shouldn't get the button
        owner = upsert_user(
            app.state.db_path,
            google_id="anon-test-owner",
            email="ato@t.com",
            display_name="ATO",
        )
        _seed_published_report(
            app.state.db_path, slug="anon-slug", owner_user_id=owner["id"]
        )
        resp = report_client.get("/report/anon-slug/")
        assert resp.status_code == 200
        assert "재분석" not in resp.text

    def test_admin_sees_button_for_other_users_report(
        self, report_client: TestClient
    ) -> None:
        """Admin gets the button on someone else's report."""
        owner = upsert_user(
            app.state.db_path,
            google_id="admin-test-owner",
            email="ato2@t.com",
            display_name="Owner",
        )
        _seed_published_report(
            app.state.db_path, slug="admin-slug", owner_user_id=owner["id"]
        )
        _login_as(
            report_client, role="admin", google_id="admin-viewer", email="adm@t.com"
        )
        resp = report_client.get("/report/admin-slug/")
        assert resp.status_code == 200
        assert "재분석" in resp.text

    def test_other_regular_user_does_not_see_button(
        self, report_client: TestClient
    ) -> None:
        """A logged-in regular user that isn't the owner does NOT see the button."""
        owner = upsert_user(
            app.state.db_path,
            google_id="other-test-owner",
            email="oto@t.com",
            display_name="Owner",
        )
        _seed_published_report(
            app.state.db_path, slug="other-slug", owner_user_id=owner["id"]
        )
        _login_as(
            report_client, role="user", google_id="other-viewer", email="ov@t.com"
        )
        resp = report_client.get("/report/other-slug/")
        assert resp.status_code == 200
        assert "재분석" not in resp.text

    def test_missing_html_content_returns_404(
        self, report_client: TestClient
    ) -> None:
        """A catalog row with empty html_content returns 404 (no filesystem fallback)."""
        _login_as(
            report_client, role="user", google_id="ff-owner", email="ff@t.com"
        )
        slug = "no-html-slug"
        _seed_published_report(
            app.state.db_path, slug=slug, owner_user_id=None, html=""
        )
        resp = report_client.get(f"/report/{slug}/")
        assert resp.status_code == 404

    def test_unknown_slug_returns_404(self, report_client: TestClient) -> None:
        """A slug with no DB row returns 404."""
        resp = report_client.get("/report/totally-unknown-slug/")
        assert resp.status_code == 404
