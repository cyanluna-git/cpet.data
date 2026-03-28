"""
tests/test_dashboard_feature_analytics_partial.py — dashboard analytics partial tests.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from server.db import (
    backfill_endurance_core_feature_sets,
    backfill_longitudinal_delta_feature_sets,
    complete_onboarding,
    create_subject,
    init_db,
    link_user_to_subject,
    upsert_subject_metric_snapshot,
    upsert_user,
)
from server.main import app


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


def _snapshot(
    *,
    subject_id: str,
    source_kind: str,
    source_ref_id: str,
    measured_at: str,
    vo2max_rel: float | None = None,
    fatmax_power_w: float | None = None,
    lt1_power_w: float | None = None,
) -> dict:
    return {
        "subject_id": subject_id,
        "source_kind": source_kind,
        "source_ref_id": source_ref_id,
        "submission_id": None,
        "measured_at": measured_at,
        "protocol_type": "Belgium Lactate Test Elite" if source_kind == "cpet_submission" else "INSCYD",
        "vo2max_ml": None,
        "vo2max_rel": vo2max_rel,
        "lt1_power_w": lt1_power_w,
        "lt2_power_w": None,
        "fatmax_power_w": fatmax_power_w,
        "fatmax_gmin": None,
        "vlamax": None,
        "at_power_w": None,
        "carbmax_w": None,
        "glycogen_g": None,
        "extraction_version": "test-v1",
        "quality_flags_json": "[]",
        "payload_json": "{}",
    }


def _seed_feature_rows(db_path: Path) -> dict:
    alpha = create_subject(db_path, name="Alpha Rider")
    beta = create_subject(db_path, name="Beta Rider")

    for snapshot in (
        _snapshot(
            subject_id=alpha["id"],
            source_kind="cpet_submission",
            source_ref_id="alpha-cpet-1",
            measured_at="2026-01-10",
            vo2max_rel=50.0,
            fatmax_power_w=180.0,
            lt1_power_w=205.0,
        ),
        _snapshot(
            subject_id=alpha["id"],
            source_kind="cpet_submission",
            source_ref_id="alpha-cpet-2",
            measured_at="2026-02-10",
            vo2max_rel=55.0,
            fatmax_power_w=195.0,
            lt1_power_w=220.0,
        ),
        _snapshot(
            subject_id=beta["id"],
            source_kind="cpet_submission",
            source_ref_id="beta-cpet-1",
            measured_at="2026-02-15",
            vo2max_rel=48.0,
            fatmax_power_w=170.0,
            lt1_power_w=198.0,
        ),
    ):
        upsert_subject_metric_snapshot(db_path, snapshot)

    backfill_endurance_core_feature_sets(db_path)
    backfill_longitudinal_delta_feature_sets(db_path)
    return {"alpha": alpha, "beta": beta}


def _login_as(client: TestClient, role: str, google_id: str = "dashboard-analytics-gid") -> dict:
    db_path = app.state.db_path
    user = upsert_user(
        db_path,
        google_id=google_id,
        email=f"{google_id}@example.com",
        display_name="Dashboard Analytics User",
    )
    complete_onboarding(db_path, user["id"], "Dashboard Analytics User")

    conn = __import__("sqlite3").connect(str(db_path))
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
                "email": f"{google_id}@example.com",
                "name": "Dashboard Analytics User",
                "picture": "",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)
    return user


class TestDashboardFeatureAnalyticsPartial:
    def test_dashboard_page_mounts_analytics_region_for_researcher(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        _seed_feature_rows(db_path)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as(client, "researcher")

        resp = client.get("/dashboard")

        assert resp.status_code == 200
        assert 'id="dashboard-analytics-region"' in resp.text
        assert '/api/dashboard/analytics' in resp.text

    def test_dashboard_page_mounts_analytics_region_for_regular_user(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        _seed_feature_rows(db_path)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as(client, "user")

        resp = client.get("/dashboard")

        assert resp.status_code == 200
        assert 'id="dashboard-analytics-region"' in resp.text

    def test_dashboard_reports_tab_hides_analytics_and_mounts_job_list(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        _seed_feature_rows(db_path)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as(client, "researcher")

        resp = client.get("/dashboard?tab=reports")

        assert resp.status_code == 200
        assert 'id="dashboard-analytics-region"' not in resp.text
        assert 'id="filter-tabs"' in resp.text
        assert 'id="job-list-body"' in resp.text
        assert 'hx-get="/api/jobs/partial"' in resp.text

    def test_dashboard_analytics_overview_partial_renders_summary(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        seeded = _seed_feature_rows(db_path)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as(client, "researcher")

        resp = client.get("/api/dashboard/analytics")

        assert resp.status_code == 200
        assert "주요 지표 대시보드" in resp.text
        assert "Single-Anchor Watchlist" in resp.text
        assert "Repeat-Test Ready" in resp.text
        assert "Cohort Areas" in resp.text
        assert "개별 이름 없이 전체 분포와 변화 영역만 익명으로 집계합니다." in resp.text
        assert "Top VO2max" not in resp.text
        assert seeded["alpha"]["id"] in resp.text

    def test_dashboard_analytics_overview_scopes_regular_user_to_own_subject(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        seeded = _seed_feature_rows(db_path)
        client = TestClient(app, raise_server_exceptions=False)
        user = _login_as(client, "user")
        link_user_to_subject(db_path, user["id"], seeded["alpha"]["id"])

        resp = client.get("/api/dashboard/analytics")

        assert resp.status_code == 200
        assert "My Dashboard" in resp.text
        assert "Alpha Rider" in resp.text
        assert "Beta Rider" not in resp.text
        assert "Current Cohort" in resp.text

    def test_dashboard_analytics_subject_partial_renders_drill_in(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        seeded = _seed_feature_rows(db_path)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as(client, "admin")

        resp = client.get(
            "/api/dashboard/analytics/subject",
            params={"subject_id": seeded["alpha"]["id"]},
        )

        assert resp.status_code == 200
        assert "Alpha Rider" in resp.text
        assert "Current State" in resp.text
        assert "Cohort Positioning" in resp.text
        assert "Trend Signal" in resp.text
        assert "상위 50%권" in resp.text
        assert "vs 2026-01-10" in resp.text
        assert "ΔFatMax 15.0" in resp.text
        assert "시계열 변화 차트" in resp.text
        assert "코호트 좌표계" in resp.text
        assert "VO2max" in resp.text
        assert "LT1" in resp.text
        assert "FatMax" in resp.text
        assert "2026-01-10" in resp.text
        assert "2026-02-10" in resp.text
        assert "핵심 지표가 anchor마다 어떻게 움직였는지 먼저 곡선으로 확인합니다." not in resp.text
        assert "익명 점 군집 안에서 현재 기반 체력과 최근 변화 방향을 함께 읽습니다." not in resp.text
        assert "data-dashboard-chart-select" not in resp.text

    def test_dashboard_analytics_subject_partial_blocks_regular_user_from_other_subject(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        seeded = _seed_feature_rows(db_path)
        client = TestClient(app, raise_server_exceptions=False)
        user = _login_as(client, "user")
        link_user_to_subject(db_path, user["id"], seeded["alpha"]["id"])

        resp = client.get(
            "/api/dashboard/analytics/subject",
            params={"subject_id": seeded["beta"]["id"]},
        )

        assert resp.status_code == 200
        assert "선택한 피험자의 대시보드 분석 상세를 불러올 수 없습니다." in resp.text

    def test_dashboard_analytics_subject_partial_keeps_metric_cards_without_dropdown_for_sparse_subject(
        self, tmp_path: Path
    ) -> None:
        db_path = _setup_app(tmp_path)
        seeded = _seed_feature_rows(db_path)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as(client, "admin")

        resp = client.get(
            "/api/dashboard/analytics/subject",
            params={"subject_id": seeded["beta"]["id"]},
        )

        assert resp.status_code == 200
        assert "VO2max" in resp.text
        assert "LT1" in resp.text
        assert "FatMax" in resp.text
        assert "data-dashboard-chart-select" not in resp.text
        assert resp.text.count("data-dashboard-chart-root") == 3
