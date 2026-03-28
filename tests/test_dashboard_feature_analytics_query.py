"""
tests/test_dashboard_feature_analytics_query.py — dashboard analytics query helper tests.
"""

from pathlib import Path

from server.db import (
    backfill_endurance_core_feature_sets,
    backfill_longitudinal_delta_feature_sets,
    create_submission,
    create_subject,
    get_dashboard_subject_analytics,
    init_db,
    list_dashboard_subject_analytics,
    summarize_dashboard_feature_analytics,
    upsert_subject_metric_snapshot,
)


def _init_platform_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "platform.db"
    init_db(db_path)
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
    extraction_version: str = "test-v1",
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
        "extraction_version": extraction_version,
        "quality_flags_json": "[]",
        "payload_json": "{}",
    }


def _seed_dashboard_feature_rows(db_path: Path) -> dict:
    alpha = create_subject(db_path, name="Alpha Rider")
    beta = create_subject(db_path, name="Beta Rider")
    gamma = create_subject(db_path, name="Gamma Rider")

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
        _snapshot(
            subject_id=gamma["id"],
            source_kind="inscyd_report",
            source_ref_id="gamma-inscyd-1",
            measured_at="2026-01-20",
        ),
        _snapshot(
            subject_id=gamma["id"],
            source_kind="cpet_submission",
            source_ref_id="gamma-cpet-1",
            measured_at="2026-03-01",
            vo2max_rel=60.0,
            fatmax_power_w=210.0,
            lt1_power_w=230.0,
        ),
    ):
        upsert_subject_metric_snapshot(db_path, snapshot)

    backfill_endurance_core_feature_sets(db_path)
    backfill_longitudinal_delta_feature_sets(db_path)

    return {"alpha": alpha, "beta": beta, "gamma": gamma}


class TestDashboardFeatureAnalyticsQuery:
    def test_summary_reports_realistic_overview_counts(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        seeded = _seed_dashboard_feature_rows(db_path)

        summary = summarize_dashboard_feature_analytics(db_path)

        assert summary["total_feature_rows"] == 10
        assert summary["total_subjects"] == 3
        assert summary["latest_anchor_measured_at"] == "2026-03-01"
        assert summary["usable_anchor_rows"] == 5
        assert summary["usable_cpet_anchor_rows"] == 5
        assert summary["subjects_with_current_state"] == 3
        assert summary["subjects_with_multi_date_history"] == 2
        assert summary["subjects_with_multi_date_cpet_history"] == 2
        assert summary["single_anchor_subjects"] == 1
        assert summary["subjects_with_usable_delta"] == 1
        assert summary["spec_counts"] == {"endurance_core": 5, "longitudinal_delta": 5}
        assert summary["available_metrics"]["vo2max_rel_rows"] == 4
        assert summary["available_metrics"]["fatmax_power_w_rows"] == 4
        assert summary["metric_coverage"]["vo2max_rel_pct"] == 80.0
        assert summary["metric_coverage"]["fatmax_power_w_pct"] == 80.0
        assert summary["anchor_window"] == {
            "earliest_measured_at": "2026-01-10",
            "latest_measured_at": "2026-03-01",
        }
        assert summary["leaders"]["vo2max_rel"] == {
            "subject_id": seeded["gamma"]["id"],
            "subject_name": "Gamma Rider",
            "value": 60.0,
            "total": 3,
        }
        assert summary["leaders"]["fatmax_power_w"] == {
            "subject_id": seeded["gamma"]["id"],
            "subject_name": "Gamma Rider",
            "value": 210.0,
            "total": 3,
        }
        assert summary["sparse_subject_preview"] == ["Beta Rider"]
        assert summary["quality_flag_counts"]["mixed_source_compare"] == 1
        assert summary["quality_flag_counts"]["missing_previous_snapshot"] == 3

    def test_list_returns_subject_cards_with_history_state_and_positioning(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        seeded = _seed_dashboard_feature_rows(db_path)

        rows = list_dashboard_subject_analytics(db_path)

        assert [row["subject_name"] for row in rows] == [
            "Gamma Rider",
            "Beta Rider",
            "Alpha Rider",
        ]

        gamma = next(row for row in rows if row["subject_id"] == seeded["gamma"]["id"])
        beta = next(row for row in rows if row["subject_id"] == seeded["beta"]["id"])
        alpha = next(row for row in rows if row["subject_id"] == seeded["alpha"]["id"])

        assert gamma["history_state"] == "timeline"
        assert gamma["usable_history_count"] == 2
        assert gamma["usable_delta_count"] == 0
        assert gamma["current_state"]["vo2max_rel"] == 60.0
        assert gamma["cohort_positioning"]["vo2max_rel"]["rank"] == 1

        assert beta["history_state"] == "single_anchor"
        assert beta["cohort_positioning"]["fatmax_power_w"]["rank"] == 3

        assert alpha["history_state"] == "timeline"
        assert alpha["usable_history_count"] == 2
        assert alpha["usable_delta_count"] == 1
        assert alpha["cohort_positioning"]["vo2max_rel"]["rank"] == 2

    def test_detail_returns_timeline_points_and_delta_state(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        seeded = _seed_dashboard_feature_rows(db_path)

        alpha = get_dashboard_subject_analytics(db_path, seeded["alpha"]["id"])
        gamma = get_dashboard_subject_analytics(db_path, seeded["gamma"]["id"])

        assert alpha is not None
        assert alpha["subject"]["name"] == "Alpha Rider"
        assert alpha["history_state"] == "timeline"
        assert [point["anchor_measured_at"] for point in alpha["timeline"]] == [
            "2026-01-10",
            "2026-02-10",
        ]
        assert alpha["timeline"][0]["has_usable_delta"] is False
        assert alpha["timeline"][1]["has_usable_delta"] is True
        assert alpha["timeline"][1]["delta_metrics"]["delta_vo2max_rel"] == 5.0
        assert alpha["timeline"][1]["delta_metrics"]["pct_delta_vo2max_rel"] == 10.0
        assert alpha["latest_trend"] == {
            "state": "delta_ready",
            "comparison_anchor_measured_at": "2026-01-10",
            "delta_metrics": {
                "delta_fatmax_power_w": 15.0,
                "delta_lt1_power_w": 15.0,
                "delta_vo2max_rel": 5.0,
                "pct_delta_lt1_power_w": 7.32,
                "pct_delta_vo2max_rel": 10.0,
            },
            "delta_quality_flags": ["missing_anchor_vlamax", "missing_previous_vlamax"],
        }
        assert alpha["positioning_widgets"]["vo2max_rel"]["band_key"] == "mid_pack"
        assert alpha["positioning_widgets"]["fatmax_power_w"]["band_label"] == "Mid Pack"
        assert alpha["timeline_window"] == {
            "first_anchor_measured_at": "2026-01-10",
            "latest_anchor_measured_at": "2026-02-10",
        }

        assert gamma is not None
        assert gamma["history_state"] == "timeline"
        assert [point["anchor_measured_at"] for point in gamma["timeline"]] == [
            "2026-01-20",
            "2026-03-01",
        ]
        assert len(gamma["timeline"]) == 2
        assert gamma["timeline"][0]["has_usable_delta"] is False
        assert gamma["latest_trend"]["state"] == "baseline_only"
        assert gamma["latest_trend"]["comparison_anchor_measured_at"] == "2026-01-20"
        assert gamma["timeline_window"] == {
            "first_anchor_measured_at": "2026-01-20",
            "latest_anchor_measured_at": "2026-03-01",
        }
        assert gamma["positioning_widgets"]["vo2max_rel"]["band_key"] == "front_pack"

    def test_detail_returns_none_for_missing_subject(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        _seed_dashboard_feature_rows(db_path)

        assert get_dashboard_subject_analytics(db_path, "missing-subject") is None

    def test_summary_and_list_can_be_scoped_to_specific_subjects(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        seeded = _seed_dashboard_feature_rows(db_path)

        summary = summarize_dashboard_feature_analytics(
            db_path,
            subject_ids=[seeded["alpha"]["id"]],
        )
        rows = list_dashboard_subject_analytics(
            db_path,
            subject_ids=[seeded["alpha"]["id"]],
        )

        assert summary["total_subjects"] == 1
        assert summary["subjects_with_current_state"] == 1
        assert summary["subjects_with_multi_date_history"] == 1
        assert summary["subjects_with_multi_date_cpet_history"] == 1
        assert summary["single_anchor_subjects"] == 0
        assert summary["leaders"]["vo2max_rel"]["subject_name"] == "Alpha Rider"
        assert [row["subject_name"] for row in rows] == ["Alpha Rider"]

    def test_detail_respects_subject_scope(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        seeded = _seed_dashboard_feature_rows(db_path)

        assert (
            get_dashboard_subject_analytics(
                db_path,
                seeded["beta"]["id"],
                subject_ids=[seeded["alpha"]["id"]],
            )
            is None
        )

    def test_dashboard_prefers_latest_submission_subject_name_for_display(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        seeded = _seed_dashboard_feature_rows(db_path)

        create_submission(
            db_path,
            "alias row",
            [{"name": "alias.fit"}],
            "workspaces/alias-row",
            subject_name="박근윤",
            test_date="2026-02-11",
            subject_id=seeded["alpha"]["id"],
        )

        rows = list_dashboard_subject_analytics(db_path)
        alpha = next(row for row in rows if row["subject_id"] == seeded["alpha"]["id"])
        summary = summarize_dashboard_feature_analytics(db_path)
        detail = get_dashboard_subject_analytics(db_path, seeded["alpha"]["id"])

        assert alpha["subject_name"] == "박근윤"
        assert detail is not None
        assert detail["subject"]["name"] == "박근윤"
        assert summary["sparse_subject_preview"] == ["Beta Rider"]

    def test_dashboard_list_includes_inscyd_only_anchor_subjects(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        _seed_dashboard_feature_rows(db_path)
        inscyd_only = create_subject(db_path, name="Park Geunyun")
        upsert_subject_metric_snapshot(
            db_path,
            _snapshot(
                subject_id=inscyd_only["id"],
                source_kind="inscyd_report",
                source_ref_id="park-inscyd-1",
                measured_at="2026-01-06",
                vo2max_rel=51.7,
                fatmax_power_w=150.0,
            ),
        )
        backfill_endurance_core_feature_sets(db_path)
        backfill_longitudinal_delta_feature_sets(db_path)

        rows = list_dashboard_subject_analytics(db_path)

        assert "Park Geunyun" in [row["subject_name"] for row in rows]

    def test_detail_handles_sparse_subject_with_missing_metrics(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        sparse = create_subject(db_path, name="Sparse Rider")
        upsert_subject_metric_snapshot(
            db_path,
            _snapshot(
                subject_id=sparse["id"],
                source_kind="cpet_submission",
                source_ref_id="sparse-cpet-1",
                measured_at="2026-02-20",
            ),
        )

        backfill_endurance_core_feature_sets(db_path)
        backfill_longitudinal_delta_feature_sets(db_path)

        detail = get_dashboard_subject_analytics(db_path, sparse["id"])

        assert detail is not None
        assert detail["current_state"]["vo2max_rel"] is None
        assert detail["current_state"]["fatmax_power_w"] is None
        assert detail["positioning_widgets"]["vo2max_rel"] is None
        assert detail["positioning_widgets"]["fatmax_power_w"] is None
        assert detail["latest_trend"]["state"] == "baseline_only"
        assert detail["timeline_window"] == {
            "first_anchor_measured_at": "2026-02-20",
            "latest_anchor_measured_at": "2026-02-20",
        }
