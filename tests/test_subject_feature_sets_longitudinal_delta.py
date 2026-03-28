"""
tests/test_subject_feature_sets_longitudinal_delta.py — longitudinal_delta_v1 builder tests.
"""

import html
import json
import sqlite3
from pathlib import Path

from server.db import (
    backfill_subject_metric_snapshots,
    build_longitudinal_delta_feature_set,
    create_submission,
    create_subject,
    init_db,
)


def _create_analysis_db(
    workspace: Path,
    test_date: str,
    protocol_name: str = "Belgium Lactate Test Elite",
    metrics: dict | None = None,
) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    db_path = workspace / "analysis.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS test_session (
            id INTEGER PRIMARY KEY,
            test_date TEXT,
            protocol_name TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO test_session (test_date, protocol_name) VALUES (?, ?)",
        (test_date, protocol_name),
    )
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
                value_text = json.dumps(value) if not isinstance(value, str) else value
                conn.execute(
                    "INSERT OR REPLACE INTO analysis_results (category, key, value) "
                    "VALUES (?, ?, ?)",
                    (category, key, value_text),
                )
    conn.commit()
    conn.close()


def _write_inscyd_report(workspace: Path, report_data: dict) -> None:
    report_dir = workspace / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = html.escape(json.dumps(report_data, ensure_ascii=False))
    (report_dir / "index.html").write_text(
        f"<html><body><script id=\"report-data\" type=\"application/json\">{payload}</script></body></html>",
        encoding="utf-8",
    )


def _fetch_snapshot_id(db_path: Path, source_kind: str, measured_at: str) -> str:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT snapshot_id FROM subject_metric_snapshots WHERE source_kind = ? AND measured_at = ?",
        (source_kind, measured_at),
    ).fetchone()
    conn.close()
    assert row is not None
    return str(row[0])


class TestLongitudinalDeltaFeatureBuilder:
    def test_builds_cpet_to_cpet_delta_row(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "cpet_platform.db"
        init_db(db_path)

        subject = create_subject(db_path, name="Geunyun Park")

        ws1 = data_dir / "workspaces" / "delta-cpet-1"
        _create_analysis_db(
            ws1,
            "2026-02-01",
            metrics={
                "vo2max": {"vo2max_rel": 57.2},
                "lactate": {"lt1_fixed_power_w": 210.0},
                "substrate": {"fatmax_power_w": 135.0},
            },
        )
        create_submission(
            db_path,
            "delta cpet 1",
            [{"name": "park-1.fit"}],
            str(ws1),
            subject_id=subject["id"],
        )

        ws2 = data_dir / "workspaces" / "delta-cpet-2"
        _create_analysis_db(
            ws2,
            "2026-03-20",
            metrics={
                "vo2max": {"vo2max_rel": 60.7},
                "lactate": {"lt1_fixed_power_w": 225.0},
                "substrate": {"fatmax_power_w": 150.0},
            },
        )
        create_submission(
            db_path,
            "delta cpet 2",
            [{"name": "park-2.fit"}],
            str(ws2),
            subject_id=subject["id"],
        )

        backfill_subject_metric_snapshots(db_path)
        anchor_snapshot_id = _fetch_snapshot_id(db_path, "cpet_submission", "2026-03-20")
        previous_snapshot_id = _fetch_snapshot_id(db_path, "cpet_submission", "2026-02-01")

        row = build_longitudinal_delta_feature_set(db_path, anchor_snapshot_id)

        assert row is not None
        assert row["feature_spec_key"] == "longitudinal_delta"
        assert row["feature_spec_version"] == "v1"
        assert row["anchor_snapshot_id"] == anchor_snapshot_id
        assert row["anchor_measured_at"] == "2026-03-20"
        assert row["window_label"] == "previous_pair"
        assert json.loads(row["input_snapshot_ids_json"]) == [previous_snapshot_id, anchor_snapshot_id]
        assert json.loads(row["input_source_kinds_json"]) == ["cpet_submission", "cpet_submission"]

        payload = json.loads(row["feature_payload_json"])
        assert payload["spec"] == {"key": "longitudinal_delta", "version": "v1"}
        assert payload["inputs"]["anchor_snapshot_id"] == anchor_snapshot_id
        assert payload["inputs"]["previous_snapshot_id"] == previous_snapshot_id
        assert payload["inputs"]["days_since_previous"] == 47
        assert payload["features"]["days_since_previous"] == 47
        assert payload["features"]["delta_vo2max_rel"] == 3.5
        assert payload["features"]["pct_delta_vo2max_rel"] == 6.12
        assert payload["features"]["delta_lt1_power_w"] == 15.0
        assert payload["features"]["pct_delta_lt1_power_w"] == 7.14
        assert payload["features"]["delta_fatmax_power_w"] == 15.0

        flags = json.loads(row["quality_flags_json"])
        assert "missing_anchor_vlamax" in flags
        assert "missing_previous_vlamax" in flags
        assert "mixed_source_compare" not in flags

    def test_builds_mixed_source_delta_row_with_flag(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "cpet_platform.db"
        init_db(db_path)

        subject = create_subject(db_path, name="Geunyun Park")

        inscyd_ws = data_dir / "workspaces" / "delta-inscyd"
        _write_inscyd_report(
            inscyd_ws,
            {
                "meta": {"report_type": "inscyd"},
                "session": {"test_date": "2026-01-06", "test_type": "PPD"},
                "inscyd": {
                    "vo2max_rel_ml_kg_min": 62.3,
                    "fatmax_watt": 150.0,
                    "vlamax_mmol_l_s": 0.53,
                    "at_abs_watt": 265.0,
                },
            },
        )
        create_submission(
            db_path,
            "delta inscyd",
            [{"name": "park.pdf"}],
            str(inscyd_ws),
            subject_id=subject["id"],
        )

        cpet_ws = data_dir / "workspaces" / "delta-cpet"
        _create_analysis_db(
            cpet_ws,
            "2026-03-20",
            metrics={
                "vo2max": {"vo2max_rel": 60.7},
                "lactate": {"lt1_fixed_power_w": 225.0},
                "substrate": {"fatmax_power_w": 145.0},
            },
        )
        create_submission(
            db_path,
            "delta cpet",
            [{"name": "park.fit"}],
            str(cpet_ws),
            subject_id=subject["id"],
        )

        backfill_subject_metric_snapshots(db_path)
        anchor_snapshot_id = _fetch_snapshot_id(db_path, "cpet_submission", "2026-03-20")
        previous_snapshot_id = _fetch_snapshot_id(db_path, "inscyd_report", "2026-01-06")

        row = build_longitudinal_delta_feature_set(db_path, anchor_snapshot_id)

        assert row is not None
        payload = json.loads(row["feature_payload_json"])
        assert payload["inputs"]["previous_snapshot_id"] == previous_snapshot_id
        assert payload["inputs"]["previous_source_kind"] == "inscyd_report"
        assert payload["inputs"]["anchor_source_kind"] == "cpet_submission"
        assert payload["inputs"]["days_since_previous"] == 73
        assert payload["features"]["delta_vo2max_rel"] == -1.6
        assert payload["features"]["pct_delta_vo2max_rel"] == -2.57
        assert payload["features"]["delta_fatmax_power_w"] == -5.0

        flags = json.loads(row["quality_flags_json"])
        assert "mixed_source_compare" in flags
        assert "missing_previous_lt1_power_w" in flags
        assert "missing_anchor_vlamax" in flags

    def test_builds_flagged_row_when_previous_snapshot_missing(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "cpet_platform.db"
        init_db(db_path)

        subject = create_subject(db_path, name="Solo Subject")
        workspace = data_dir / "workspaces" / "delta-single"
        _create_analysis_db(
            workspace,
            "2026-03-20",
            metrics={"vo2max": {"vo2max_rel": 60.7}},
        )
        create_submission(
            db_path,
            "delta single",
            [{"name": "solo.fit"}],
            str(workspace),
            subject_id=subject["id"],
        )

        backfill_subject_metric_snapshots(db_path)
        anchor_snapshot_id = _fetch_snapshot_id(db_path, "cpet_submission", "2026-03-20")

        row = build_longitudinal_delta_feature_set(db_path, anchor_snapshot_id)

        assert row is not None
        payload = json.loads(row["feature_payload_json"])
        assert payload["inputs"]["previous_snapshot_id"] is None
        assert payload["features"] == {}

        flags = json.loads(row["quality_flags_json"])
        assert flags == ["missing_previous_snapshot"]

    def test_returns_none_for_unknown_snapshot(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        init_db(db_path)

        assert build_longitudinal_delta_feature_set(db_path, "missing") is None
