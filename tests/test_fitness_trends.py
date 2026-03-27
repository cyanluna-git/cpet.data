"""
tests/test_fitness_trends.py — Tests for fitness metric trends on profile page.

Covers:
    - list_submissions_by_user (db.py)
    - _read_analysis_metrics (db.py)
    - get_fitness_trends (db.py, delta computation)
    - GET /api/profile/trends (JSON + HTMX partial)
    - Profile page trends section rendering
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from server.db import (
    _read_analysis_metrics,
    complete_onboarding,
    create_submission,
    get_fitness_trends,
    init_db,
    list_submissions_by_user,
    summarize_fitness_trends,
    upsert_user,
)
from server.main import app


# ── Helpers ────────────────────────────────────────────────────────


def _create_analysis_db(
    workspace: Path,
    test_date: str,
    metrics: dict | None = None,
) -> Path:
    """Create a minimal analysis.db with test_session and analysis_results."""
    workspace.mkdir(parents=True, exist_ok=True)
    db_path = workspace / "analysis.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS test_session (
            id INTEGER PRIMARY KEY, test_date TEXT
        )"""
    )
    conn.execute("INSERT INTO test_session (test_date) VALUES (?)", (test_date,))
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
                val_str = json.dumps(value) if not isinstance(value, str) else value
                conn.execute(
                    "INSERT OR REPLACE INTO analysis_results (category, key, value) "
                    "VALUES (?, ?, ?)",
                    (category, key, val_str),
                )
    conn.commit()
    conn.close()
    return db_path


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Provide a temporary platform database path, initialized."""
    path = tmp_path / "test_trends.db"
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


def _login_user(client: TestClient, google_id: str = "trends-gid") -> dict:
    """Simulate Google OAuth login and return the created user dict."""
    db_path = app.state.db_path
    user = upsert_user(
        db_path, google_id=google_id, email=f"{google_id}@example.com",
        display_name="Trends User", avatar_url="https://example.com/avatar.jpg",
    )
    complete_onboarding(db_path, user["id"], "Trends User")

    with patch(
        "server.auth.oauth.google.authorize_access_token",
        new_callable=AsyncMock,
    ) as mock_token:
        mock_token.return_value = {
            "userinfo": {
                "sub": google_id,
                "email": f"{google_id}@example.com",
                "name": "Trends User",
                "picture": "https://example.com/avatar.jpg",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)

    from server.db import get_user_by_google_id
    return get_user_by_google_id(app.state.db_path, google_id)


# ── list_submissions_by_user ─────────────────────────────────────


class TestListSubmissionsByUser:
    def test_empty_for_new_user(self, db_path: Path) -> None:
        """Returns empty list when user has no submissions."""
        user = upsert_user(db_path, google_id="no-subs", email="no@test.com")
        result = list_submissions_by_user(db_path, user["id"])
        assert result == []

    def test_returns_user_submissions_only(self, db_path: Path) -> None:
        """Only returns submissions belonging to the specified user."""
        user_a = upsert_user(db_path, google_id="user-a", email="a@test.com")
        user_b = upsert_user(db_path, google_id="user-b", email="b@test.com")

        create_submission(db_path, "desc-a", [{"name": "a.fit"}], "/ws/a",
                          user_id=user_a["id"])
        create_submission(db_path, "desc-b", [{"name": "b.fit"}], "/ws/b",
                          user_id=user_b["id"])

        subs_a = list_submissions_by_user(db_path, user_a["id"])
        assert len(subs_a) == 1
        assert subs_a[0]["description"] == "desc-a"

    def test_ordered_newest_first(self, db_path: Path) -> None:
        """Submissions are returned newest first."""
        user = upsert_user(db_path, google_id="order-test", email="o@test.com")
        create_submission(db_path, "first", [{}], "/ws/1", user_id=user["id"])
        create_submission(db_path, "second", [{}], "/ws/2", user_id=user["id"])

        subs = list_submissions_by_user(db_path, user["id"])
        assert len(subs) == 2
        assert subs[0]["description"] == "second"


# ── _read_analysis_metrics ───────────────────────────────────────


class TestReadAnalysisMetrics:
    def test_nonexistent_db_returns_empty(self, tmp_path: Path) -> None:
        """Returns empty dict when analysis.db does not exist."""
        result = _read_analysis_metrics(tmp_path / "no_such.db")
        assert result == {}

    def test_reads_vo2max_metrics(self, tmp_path: Path) -> None:
        """Extracts VO2max absolute and relative values."""
        ws = tmp_path / "ws1"
        _create_analysis_db(ws, "2026-01-15", {
            "vo2max": {"vo2max_ml": 4200.5, "vo2max_rel": 58.3},
        })
        result = _read_analysis_metrics(ws / "analysis.db")
        assert result["test_date"] == "2026-01-15"
        assert result["vo2max_ml"] == 4200.5
        assert result["vo2max_rel"] == 58.3

    def test_reads_lactate_metrics(self, tmp_path: Path) -> None:
        """Extracts LT1 and LT2 power values."""
        ws = tmp_path / "ws2"
        _create_analysis_db(ws, "2026-02-10", {
            "lactate": {"lt1_fixed_power_w": 180.0, "lt1_dmax_power_w": 165.5},
        })
        result = _read_analysis_metrics(ws / "analysis.db")
        assert result["lt1_power_w"] == 180.0
        assert result["lt2_power_w"] == 165.5

    def test_reads_substrate_metrics(self, tmp_path: Path) -> None:
        """Extracts FatMax power and oxidation rate."""
        ws = tmp_path / "ws3"
        _create_analysis_db(ws, "2026-03-05", {
            "substrate": {"fatmax_power_w": 150, "fatmax_gmin": 0.85},
        })
        result = _read_analysis_metrics(ws / "analysis.db")
        assert result["fatmax_power_w"] == 150
        assert result["fatmax_gmin"] == 0.85

    def test_missing_analysis_results_table(self, tmp_path: Path) -> None:
        """Returns empty if analysis_results table is missing."""
        ws = tmp_path / "ws4"
        ws.mkdir(parents=True)
        db = ws / "analysis.db"
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE test_session (id INTEGER PRIMARY KEY, test_date TEXT)"
        )
        conn.execute("INSERT INTO test_session (test_date) VALUES ('2026-01-01')")
        conn.commit()
        conn.close()

        result = _read_analysis_metrics(db)
        assert result == {}

    def test_handles_non_numeric_values(self, tmp_path: Path) -> None:
        """Non-numeric analysis values are skipped."""
        ws = tmp_path / "ws5"
        _create_analysis_db(ws, "2026-01-20", {
            "vo2max": {"vo2max_ml": 3800.0, "bxb_series": {"t_s": [1, 2, 3]}},
        })
        result = _read_analysis_metrics(ws / "analysis.db")
        assert result["vo2max_ml"] == 3800.0
        # bxb_series is not in our _TREND_METRICS keys, so it should not appear
        assert "bxb_series" not in result


# ── get_fitness_trends ───────────────────────────────────────────


class TestGetFitnessTrends:
    def test_no_submissions_returns_empty(self, db_path: Path) -> None:
        """Returns empty list when user has no submissions."""
        user = upsert_user(db_path, google_id="empty-trends", email="e@test.com")
        trends = get_fitness_trends(db_path, user["id"])
        assert trends == []

    def test_single_submission_no_deltas(self, tmp_path: Path, db_path: Path) -> None:
        """Single submission has metrics but no deltas."""
        user = upsert_user(db_path, google_id="one-sub", email="one@test.com")
        ws = tmp_path / "workspaces" / "ws1"
        _create_analysis_db(ws, "2026-01-10", {
            "vo2max": {"vo2max_ml": 4000.0, "vo2max_rel": 55.0},
            "lactate": {"lt1_fixed_power_w": 170.0, "lt1_dmax_power_w": 160.0},
        })
        create_submission(db_path, "test1", [{}], str(ws), user_id=user["id"])

        trends = get_fitness_trends(db_path, user["id"])
        assert len(trends) == 1
        assert trends[0]["test_date"] == "2026-01-10"
        assert trends[0]["vo2max_ml"] == 4000.0
        assert "deltas" not in trends[0]

    def test_two_submissions_computes_deltas(
        self, tmp_path: Path, db_path: Path,
    ) -> None:
        """Two submissions produce delta values on the latest entry."""
        user = upsert_user(db_path, google_id="two-subs", email="two@test.com")

        ws1 = tmp_path / "workspaces" / "ws1"
        _create_analysis_db(ws1, "2026-01-10", {
            "vo2max": {"vo2max_ml": 4000.0, "vo2max_rel": 55.0},
            "substrate": {"fatmax_power_w": 140, "fatmax_gmin": 0.7},
        })
        create_submission(db_path, "test1", [{}], str(ws1), user_id=user["id"])

        ws2 = tmp_path / "workspaces" / "ws2"
        _create_analysis_db(ws2, "2026-03-15", {
            "vo2max": {"vo2max_ml": 4200.0, "vo2max_rel": 57.5},
            "substrate": {"fatmax_power_w": 160, "fatmax_gmin": 0.85},
        })
        create_submission(db_path, "test2", [{}], str(ws2), user_id=user["id"])

        trends = get_fitness_trends(db_path, user["id"])
        assert len(trends) == 2
        # Sorted ascending by date
        assert trends[0]["test_date"] == "2026-01-10"
        assert trends[1]["test_date"] == "2026-03-15"
        # Deltas only on latest entry
        assert "deltas" not in trends[0]
        deltas = trends[1]["deltas"]
        assert deltas["vo2max_ml"] == 200.0
        assert deltas["vo2max_rel"] == 2.5
        assert deltas["fatmax_power_w"] == 20
        assert deltas["fatmax_gmin"] == 0.15

    def test_submission_without_analysis_db_skipped(
        self, db_path: Path,
    ) -> None:
        """Submissions with no analysis.db in workspace are skipped."""
        user = upsert_user(db_path, google_id="no-db", email="nodb@test.com")
        create_submission(
            db_path, "no-analysis", [{}], "/nonexistent/workspace",
            user_id=user["id"],
        )
        trends = get_fitness_trends(db_path, user["id"])
        assert trends == []


class TestSummarizeFitnessTrends:
    def test_empty_summary(self) -> None:
        summary = summarize_fitness_trends([])
        assert summary["total_tests"] == 0
        assert summary["cards"] == []

    def test_summary_uses_latest_and_best_values(self) -> None:
        trends = [
            {
                "test_date": "2026-01-10",
                "subject_name": "Park",
                "vo2max_rel": 55.0,
                "fatmax_power_w": 150,
            },
            {
                "test_date": "2026-03-15",
                "subject_name": "Park",
                "vo2max_rel": 57.5,
                "fatmax_power_w": 145,
            },
        ]

        summary = summarize_fitness_trends(trends)

        assert summary["total_tests"] == 2
        assert summary["latest_test_date"] == "2026-03-15"
        assert summary["subject_name"] == "Park"

        vo2_card = next(card for card in summary["cards"] if card["key"] == "vo2max_rel")
        assert vo2_card["latest_value"] == 57.5
        assert vo2_card["delta"] == 2.5
        assert vo2_card["best_value"] == 57.5
        assert vo2_card["is_best_now"] is True

        fatmax_card = next(card for card in summary["cards"] if card["key"] == "fatmax_power_w")
        assert fatmax_card["latest_value"] == 145
        assert fatmax_card["best_value"] == 150
        assert fatmax_card["gap_to_best"] == -5.0


# ── GET /api/profile/trends ──────────────────────────────────────


class TestProfileTrendsAPI:
    def test_anonymous_returns_401(self, client: TestClient) -> None:
        """Unauthenticated request returns 401."""
        resp = client.get("/api/profile/trends")
        assert resp.status_code == 401

    def test_json_response_no_submissions(self, client: TestClient) -> None:
        """Authenticated user with no submissions gets empty data."""
        _login_user(client)
        resp = client.get("/api/profile/trends")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []

    def test_json_response_with_trends(
        self, client: TestClient, tmp_path: Path,
    ) -> None:
        """Authenticated user with submissions gets trend data in JSON."""
        user = _login_user(client)
        db_path = app.state.db_path

        ws = tmp_path / "data" / "workspaces" / "ws-trends"
        _create_analysis_db(ws, "2026-02-20", {
            "vo2max": {"vo2max_ml": 3900.0, "vo2max_rel": 53.5},
        })
        create_submission(
            db_path, "trend-sub", [{}], str(ws), user_id=user["id"],
        )

        resp = client.get("/api/profile/trends")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["vo2max_ml"] == 3900.0
        assert body["summary"]["total_tests"] == 1
        assert body["summary"]["cards"]

    def test_htmx_returns_partial_html(self, client: TestClient) -> None:
        """HTMX request returns partial HTML instead of JSON."""
        _login_user(client)
        resp = client.get(
            "/api/profile/trends",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "fitness-trends" in resp.text


# ── Profile Page Trends Section ──────────────────────────────────


class TestProfilePageTrends:
    def test_profile_page_shows_empty_state(self, client: TestClient) -> None:
        """Profile page shows empty state message when no test records."""
        _login_user(client)
        resp = client.get("/profile")
        assert resp.status_code == 200
        assert "피트니스 지표 트렌드" in resp.text
        assert "아직 검사 기록이 없습니다" in resp.text

    def test_profile_page_shows_trend_table(
        self, client: TestClient, tmp_path: Path,
    ) -> None:
        """Profile page renders trend table when test records exist."""
        user = _login_user(client, google_id="page-trends-gid")
        db_path = app.state.db_path

        ws = tmp_path / "data" / "workspaces" / "ws-page"
        _create_analysis_db(ws, "2026-03-01", {
            "vo2max": {"vo2max_ml": 4100.0, "vo2max_rel": 56.0},
            "lactate": {"lt1_fixed_power_w": 175.0, "lt1_dmax_power_w": 168.0},
            "substrate": {"fatmax_power_w": 155, "fatmax_gmin": 0.9},
        })
        create_submission(
            db_path, "page-sub", [{}], str(ws), user_id=user["id"],
        )

        resp = client.get("/profile")
        assert resp.status_code == 200
        assert "4100.0" in resp.text
        assert "56.0" in resp.text
        assert "175.0" in resp.text
        assert "2026-03-01" in resp.text
        assert "최근 스냅샷" in resp.text
        assert "개인 최고" in resp.text

    def test_profile_page_shows_deltas(
        self, client: TestClient, tmp_path: Path,
    ) -> None:
        """Profile page renders delta values when 2+ test records exist."""
        user = _login_user(client, google_id="delta-page-gid")
        db_path = app.state.db_path

        ws1 = tmp_path / "data" / "workspaces" / "ws-d1"
        _create_analysis_db(ws1, "2026-01-01", {
            "vo2max": {"vo2max_ml": 3800.0, "vo2max_rel": 52.0},
        })
        create_submission(db_path, "d1", [{}], str(ws1), user_id=user["id"])

        ws2 = tmp_path / "data" / "workspaces" / "ws-d2"
        _create_analysis_db(ws2, "2026-03-01", {
            "vo2max": {"vo2max_ml": 4100.0, "vo2max_rel": 56.0},
        })
        create_submission(db_path, "d2", [{}], str(ws2), user_id=user["id"])

        resp = client.get("/profile")
        assert resp.status_code == 200
        # Delta should show +300.0 for vo2max_ml
        assert "+300.0" in resp.text
        assert "+4.0" in resp.text
