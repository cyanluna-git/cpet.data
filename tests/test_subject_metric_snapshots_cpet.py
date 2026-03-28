"""
tests/test_subject_metric_snapshots_cpet.py — Contract tests for CPET snapshot extraction.
"""

import json
import sqlite3
import shutil
from pathlib import Path

from server.db import (
    create_submission,
    create_subject,
    extract_published_report_snapshot,
    extract_cpet_snapshot,
    init_db,
    link_user_to_subject,
    link_report_to_user,
    upsert_user,
)


def _create_analysis_db(
    workspace: Path,
    test_date: str,
    protocol_name: str = "Belgium Lactate Test Elite",
    metrics: dict | None = None,
) -> Path:
    """Create a minimal analysis.db with test_session and analysis_results."""
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
    return db_path


def _init_platform_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "platform.db"
    init_db(db_path)
    return db_path


class TestExtractCpetSnapshot:
    def test_extracts_stable_snapshot_fields(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Park Geunyun")
        workspace = tmp_path / "workspaces" / "park-1"
        _create_analysis_db(
            workspace,
            "2026-03-20",
            protocol_name="Belgium Lactate Test Elite",
            metrics={
                "vo2max": {"vo2max_ml": 4505.3, "vo2max_rel": 60.7},
                "lactate": {"lt1_fixed_power_w": 171.2, "lt1_dmax_power_w": 166.6},
                "substrate": {"fatmax_power_w": 175.0, "fatmax_gmin": 1.2},
            },
        )
        submission_id = create_submission(
            db_path,
            "park cpet",
            [{"name": "park.fit"}],
            str(workspace),
            subject_id=subject["id"],
        )

        snapshot = extract_cpet_snapshot(db_path, submission_id)

        assert snapshot is not None
        assert len(snapshot["snapshot_id"]) == 36
        assert snapshot["subject_id"] == subject["id"]
        assert snapshot["source_kind"] == "cpet_submission"
        assert snapshot["source_ref_id"] == submission_id
        assert snapshot["submission_id"] == submission_id
        assert snapshot["measured_at"] == "2026-03-20"
        assert snapshot["protocol_type"] == "Belgium Lactate Test Elite"
        assert snapshot["vo2max_ml"] == 4505.3
        assert snapshot["vo2max_rel"] == 60.7
        assert snapshot["lt1_power_w"] == 171.2
        assert snapshot["lt2_power_w"] == 166.6
        assert snapshot["fatmax_power_w"] == 175.0
        assert snapshot["fatmax_gmin"] == 1.2
        assert snapshot["extraction_version"] == "cpet_snapshot_v1"

        assert json.loads(snapshot["quality_flags_json"]) == []
        payload = json.loads(snapshot["payload_json"])
        assert payload["source"]["submission_id"] == submission_id
        assert payload["source"]["workspace_path"] == str(workspace)
        assert payload["source"]["analysis_db_name"] == "analysis.db"
        assert payload["test_session"]["test_date"] == "2026-03-20"
        assert payload["test_session"]["protocol_name"] == "Belgium Lactate Test Elite"
        assert payload["metrics"]["vo2max_ml"] == 4505.3
        assert payload["metrics"]["fatmax_gmin"] == 1.2
        assert payload["missing_metrics"] == []

    def test_resolves_relative_workspace_against_data_dir(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        data_dir = tmp_path / "data"
        subject = create_subject(db_path, name="Relative Subject")
        workspace = data_dir / "workspaces" / "relative-1"
        _create_analysis_db(
            workspace,
            "2026-02-01",
            metrics={"vo2max": {"vo2max_ml": 3900.0}},
        )
        submission_id = create_submission(
            db_path,
            "relative cpet",
            [{"name": "rel.fit"}],
            "workspaces/relative-1",
            subject_id=subject["id"],
        )

        snapshot = extract_cpet_snapshot(db_path, submission_id, data_dir=data_dir)

        assert snapshot is not None
        assert snapshot["measured_at"] == "2026-02-01"
        payload = json.loads(snapshot["payload_json"])
        assert payload["source"]["workspace_path"] == "workspaces/relative-1"

    def test_resolves_workspace_path_that_already_includes_data_prefix(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        data_dir = tmp_path / "data"
        subject = create_subject(db_path, name="Prefixed Subject")
        workspace = data_dir / "workspaces" / "prefixed-1"
        _create_analysis_db(
            workspace,
            "2026-02-02",
            metrics={"vo2max": {"vo2max_rel": 41.2}},
        )
        submission_id = create_submission(
            db_path,
            "prefixed cpet",
            [{"name": "prefixed.fit"}],
            "data/workspaces/prefixed-1",
            subject_id=subject["id"],
        )

        snapshot = extract_cpet_snapshot(db_path, submission_id, data_dir=data_dir)

        assert snapshot is not None
        assert snapshot["measured_at"] == "2026-02-02"
        assert snapshot["vo2max_rel"] == 41.2

    def test_returns_none_without_subject_link(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        workspace = tmp_path / "workspaces" / "orphan"
        _create_analysis_db(workspace, "2026-03-20")
        submission_id = create_submission(
            db_path,
            "orphan cpet",
            [{"name": "orphan.fit"}],
            str(workspace),
        )

        assert extract_cpet_snapshot(db_path, submission_id) is None

    def test_returns_none_without_analysis_db(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="No Analysis")
        workspace = tmp_path / "workspaces" / "missing-db"
        workspace.mkdir(parents=True)
        submission_id = create_submission(
            db_path,
            "missing analysis",
            [{"name": "missing.fit"}],
            str(workspace),
            subject_id=subject["id"],
        )

        assert extract_cpet_snapshot(db_path, submission_id) is None

    def test_emits_missing_metric_quality_flags(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Sparse Subject")
        workspace = tmp_path / "workspaces" / "sparse"
        _create_analysis_db(
            workspace,
            "2026-03-21",
            protocol_name="",
            metrics={"vo2max": {"vo2max_rel": 56.4}},
        )
        submission_id = create_submission(
            db_path,
            "sparse cpet",
            [{"name": "sparse.fit"}],
            str(workspace),
            subject_id=subject["id"],
        )

        snapshot = extract_cpet_snapshot(db_path, submission_id)

        assert snapshot is not None
        flags = json.loads(snapshot["quality_flags_json"])
        assert flags == [
            "missing_fatmax_gmin",
            "missing_fatmax_power_w",
            "missing_lt1_power_w",
            "missing_lt2_power_w",
            "missing_protocol_type",
            "missing_vo2max_ml",
        ]
        payload = json.loads(snapshot["payload_json"])
        assert payload["missing_metrics"] == [
            "fatmax_gmin",
            "fatmax_power_w",
            "lt1_power_w",
            "lt2_power_w",
            "vo2max_ml",
        ]

    def test_extracts_linked_published_cpet_report_snapshot(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        published_dir = tmp_path / "published"
        report_slug = "geunyun-park-20260320-energy"
        report_dir = published_dir / report_slug
        report_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(
            Path("tests/fixtures/cosmed_only/report/index.html"),
            report_dir / "index.html",
        )

        subject = create_subject(db_path, name="Gerald Park")
        user = upsert_user(
            db_path,
            google_id="park-google",
            email="park@example.com",
            display_name="Gerald Park",
        )
        link_user_to_subject(db_path, user["id"], subject["id"])
        link_report_to_user(db_path, report_slug, user["id"])

        snapshot = extract_published_report_snapshot(db_path, report_slug, published_dir)

        assert snapshot is not None
        assert snapshot["subject_id"] == subject["id"]
        assert snapshot["source_kind"] == "published_cpet_report"
        assert snapshot["source_ref_id"] == report_slug
        assert snapshot["submission_id"] is None
        assert snapshot["measured_at"] == "2026-03-20"
        assert snapshot["protocol_type"] == "Belgium Lactate Test Elite"
        assert snapshot["vo2max_ml"] == 4505.3
        assert snapshot["vo2max_rel"] == 60.7
        assert snapshot["lt1_power_w"] == 175
        assert snapshot["lt2_power_w"] == 288
        assert snapshot["fatmax_power_w"] == 175
        assert snapshot["fatmax_gmin"] == 1.2
        assert snapshot["extraction_version"] == "published_cpet_snapshot_v1"

        payload = json.loads(snapshot["payload_json"])
        assert payload["source"]["report_slug"] == report_slug
        assert payload["source"]["published_mode"] == "standalone_report"
        assert payload["subject"]["name"] == "Geunyun Park"
        assert payload["session"]["test_date"] == "2026-03-20"
