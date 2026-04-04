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
    fatmax_gmin: float | None = None,
    lt1_power_w: float | None = None,
    lt2_power_w: float | None = None,
    vlamax: float | None = None,
    at_power_w: float | None = None,
    carbmax_w: float | None = None,
    glycogen_g: float | None = None,
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
        "lt2_power_w": lt2_power_w,
        "fatmax_power_w": fatmax_power_w,
        "fatmax_gmin": fatmax_gmin,
        "vlamax": vlamax,
        "at_power_w": at_power_w,
        "carbmax_w": carbmax_w,
        "glycogen_g": glycogen_g,
        "extraction_version": "test-v1",
        "quality_flags_json": "[]",
        "payload_json": "{}",
    }


def _seed_feature_rows(db_path: Path) -> dict:
    alpha = create_subject(db_path, name="Alpha Rider")
    beta = create_subject(db_path, name="Beta Rider")
    gamma = create_subject(db_path, name="INSCYD Rider")

    for snapshot in (
        _snapshot(
            subject_id=alpha["id"],
            source_kind="cpet_submission",
            source_ref_id="alpha-cpet-1",
            measured_at="2026-01-10",
            vo2max_rel=50.0,
            fatmax_power_w=180.0,
            fatmax_gmin=0.41,
            lt1_power_w=205.0,
            lt2_power_w=262.0,
        ),
        _snapshot(
            subject_id=alpha["id"],
            source_kind="cpet_submission",
            source_ref_id="alpha-cpet-2",
            measured_at="2026-02-10",
            vo2max_rel=55.0,
            fatmax_power_w=195.0,
            fatmax_gmin=0.48,
            lt1_power_w=220.0,
            lt2_power_w=278.0,
        ),
        _snapshot(
            subject_id=beta["id"],
            source_kind="cpet_submission",
            source_ref_id="beta-cpet-1",
            measured_at="2026-02-15",
            vo2max_rel=48.0,
            fatmax_power_w=170.0,
            fatmax_gmin=0.37,
            lt1_power_w=198.0,
            lt2_power_w=250.0,
        ),
        _snapshot(
            subject_id=gamma["id"],
            source_kind="inscyd_report",
            source_ref_id="gamma-inscyd-1",
            measured_at="2026-02-12",
            vo2max_rel=57.0,
            fatmax_power_w=184.0,
            fatmax_gmin=0.44,
            lt1_power_w=214.0,
            lt2_power_w=271.0,
            vlamax=0.39,
            at_power_w=276.0,
            carbmax_w=342.0,
            glycogen_g=390.0,
        ),
    ):
        upsert_subject_metric_snapshot(db_path, snapshot)

    backfill_endurance_core_feature_sets(db_path)
    backfill_longitudinal_delta_feature_sets(db_path)
    return {"alpha": alpha, "beta": beta, "gamma": gamma}


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
        assert 'hx-get="/api/jobs/partial?group_by=subject"' in resp.text
        assert 'hx-trigger="load, every 10s"' in resp.text

    def test_dashboard_analytics_overview_partial_renders_summary(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        seeded = _seed_feature_rows(db_path)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as(client, "researcher")

        resp = client.get("/api/dashboard/analytics")

        assert resp.status_code == 200
        assert "코호트 운영 개요" in resp.text
        assert "추가 측정 필요" in resp.text
        assert "반복 측정 해석 가능" in resp.text
        assert "코호트 분포 요약" in resp.text
        assert "개별 이름 없이 현재 위치와 최근 변화 방향의 분포만 익명으로 집계합니다." in resp.text
        assert "개별 피험자 보기" in resp.text
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
        assert "내 분석 대상" in resp.text
        assert "Alpha Rider" in resp.text
        assert "Beta Rider" not in resp.text
        assert "현재 분석 가능 피험자" in resp.text

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
        assert "반복 측정 추세" in resp.text
        assert "상위 " in resp.text
        assert "vs 2026-01-10" in resp.text
        assert "ΔFatMax 15.0" in resp.text
        assert "데이터 준비도" in resp.text
        assert "대사 threshold ladder" in resp.text
        assert "연료 전략 프로필" in resp.text
        assert "지방산화 효율" in resp.text
        assert "유산소 엔진·threshold posture" in resp.text
        assert "최근 변화 매트릭스" in resp.text
        assert "현재 연료 전략" in resp.text
        assert "탄수 활용 해석" in resp.text
        assert "시계열 변화 차트" in resp.text
        assert "코호트 내 현재 위치" in resp.text
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
        assert "현재 상태 요약" in resp.text
        assert "변화 해석 준비도" in resp.text
        assert "코호트 내 현재 위치 맵" in resp.text
        assert "현재 해석" in resp.text
        assert "다음 측정 권장" in resp.text
        assert "데이터 준비도" in resp.text
        assert "연료 전략 프로필" in resp.text
        assert "대사 threshold ladder" in resp.text
        assert "시계열 변화 차트" not in resp.text
        assert "data-dashboard-chart-select" not in resp.text
        assert "data-dashboard-chart-root" not in resp.text
        assert resp.text.count("data-dashboard-map-root") >= 3

    def test_dashboard_analytics_subject_partial_renders_anaerobic_profile_for_inscyd_subject(
        self, tmp_path: Path
    ) -> None:
        db_path = _setup_app(tmp_path)
        seeded = _seed_feature_rows(db_path)
        client = TestClient(app, raise_server_exceptions=False)
        _login_as(client, "admin")

        resp = client.get(
            "/api/dashboard/analytics/subject",
            params={"subject_id": seeded["gamma"]["id"]},
        )

        assert resp.status_code == 200
        assert "무산소 프로필" in resp.text
        assert "연료 전략 프로필" in resp.text
        assert "대사 threshold ladder" in resp.text
        assert "glycogen economy" in resp.text
        assert "현재 무산소 성향" in resp.text
        assert "고강도 활용" in resp.text
        assert "VLamax 0.39" in resp.text
        assert "AT 276.0W" in resp.text
        assert "CarbMax 342.0W" in resp.text
