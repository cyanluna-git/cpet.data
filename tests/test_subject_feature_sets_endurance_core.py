"""
tests/test_subject_feature_sets_endurance_core.py — endurance_core_v1 builder tests.
"""

import html
import json
import sqlite3
from pathlib import Path

from server.db import (
    backfill_subject_metric_snapshots,
    build_endurance_core_feature_set,
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


def _fetch_snapshot_id(db_path: Path, source_kind: str) -> str:
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT snapshot_id FROM subject_metric_snapshots WHERE source_kind = ?",
        (source_kind,),
    ).fetchone()
    conn.close()
    assert row is not None
    return str(row[0])


class TestEnduranceCoreFeatureBuilder:
    def test_builds_cpet_anchor_feature_row(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "cpet_platform.db"
        init_db(db_path)

        subject = create_subject(db_path, name="Geunyun Park")
        workspace = data_dir / "workspaces" / "feature-cpet"
        _create_analysis_db(
            workspace,
            "2026-03-20",
            metrics={
                "vo2max": {"vo2max_rel": 60.7},
                "lactate": {"lt1_fixed_power_w": 210.0, "lt1_dmax_power_w": 275.0},
                "substrate": {"fatmax_power_w": 145.0},
            },
        )
        create_submission(
            db_path,
            "feature cpet",
            [{"name": "park.fit"}],
            str(workspace),
            subject_id=subject["id"],
        )
        backfill_subject_metric_snapshots(db_path)
        snapshot_id = _fetch_snapshot_id(db_path, "cpet_submission")

        row = build_endurance_core_feature_set(db_path, snapshot_id)

        assert row is not None
        assert row["subject_id"] == subject["id"]
        assert row["feature_spec_key"] == "endurance_core"
        assert row["feature_spec_version"] == "v1"
        assert row["anchor_snapshot_id"] == snapshot_id
        assert row["anchor_measured_at"] == "2026-03-20"
        assert row["window_label"] == "anchor"
        assert json.loads(row["input_snapshot_ids_json"]) == [snapshot_id]
        assert json.loads(row["input_source_kinds_json"]) == ["cpet_submission"]

        payload = json.loads(row["feature_payload_json"])
        assert payload["spec"] == {"key": "endurance_core", "version": "v1"}
        assert payload["inputs"]["anchor_snapshot_id"] == snapshot_id
        assert payload["features"]["vo2max_rel"] == 60.7
        assert payload["features"]["lt1_power_w"] == 210.0
        assert payload["features"]["lt2_power_w"] == 275.0
        assert payload["features"]["fatmax_power_w"] == 145.0
        assert payload["features"]["source_kind"] == "cpet_submission"

        flags = json.loads(row["quality_flags_json"])
        assert "missing_vlamax" in flags
        assert "missing_at_power_w" in flags

    def test_builds_inscyd_anchor_feature_row(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "cpet_platform.db"
        init_db(db_path)

        subject = create_subject(db_path, name="Geunyun Park")
        workspace = data_dir / "workspaces" / "feature-inscyd"
        _write_inscyd_report(
            workspace,
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
            "feature inscyd",
            [{"name": "park.pdf"}],
            str(workspace),
            subject_id=subject["id"],
        )
        backfill_subject_metric_snapshots(db_path)
        snapshot_id = _fetch_snapshot_id(db_path, "inscyd_report")

        row = build_endurance_core_feature_set(db_path, snapshot_id)

        assert row is not None
        payload = json.loads(row["feature_payload_json"])
        assert payload["features"]["vo2max_rel"] == 62.3
        assert payload["features"]["fatmax_power_w"] == 150.0
        assert payload["features"]["vlamax"] == 0.53
        assert payload["features"]["at_power_w"] == 265.0
        assert payload["features"]["source_kind"] == "inscyd_report"

        flags = json.loads(row["quality_flags_json"])
        assert "missing_lt1_power_w" in flags
        assert "missing_lt2_power_w" in flags

    def test_returns_none_for_unknown_snapshot(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        init_db(db_path)

        assert build_endurance_core_feature_set(db_path, "missing") is None
