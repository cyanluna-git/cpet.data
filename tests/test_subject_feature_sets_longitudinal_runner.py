"""
tests/test_subject_feature_sets_longitudinal_runner.py — longitudinal_delta runner tests.
"""

import json
import sqlite3
from pathlib import Path

from server.db import (
    backfill_longitudinal_delta_feature_sets,
    backfill_subject_metric_snapshots,
    create_submission,
    create_subject,
    init_db,
)


def _init_platform_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "platform.db"
    init_db(db_path)
    return db_path


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


def _fetch_feature_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT *
           FROM subject_feature_sets
           WHERE feature_spec_key = 'longitudinal_delta'
           ORDER BY anchor_measured_at ASC, rowid ASC"""
    ).fetchall()
    conn.close()
    return rows


def _fetch_snapshot_ids(db_path: Path) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT snapshot_id FROM subject_metric_snapshots ORDER BY measured_at ASC, rowid ASC"
    ).fetchall()
    conn.close()
    return [str(row[0]) for row in rows]


class TestLongitudinalDeltaFeatureRunner:
    def test_backfill_inserts_rows_and_is_idempotent(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Delta Runner Subject")

        ws1 = tmp_path / "workspaces" / "delta-runner-1"
        _create_analysis_db(
            ws1,
            "2026-02-01",
            metrics={
                "vo2max": {"vo2max_rel": 57.2},
                "lactate": {"lt1_fixed_power_w": 210.0},
            },
        )
        create_submission(
            db_path,
            "delta runner 1",
            [{"name": "runner-1.fit"}],
            str(ws1),
            subject_id=subject["id"],
        )

        ws2 = tmp_path / "workspaces" / "delta-runner-2"
        _create_analysis_db(
            ws2,
            "2026-03-20",
            metrics={
                "vo2max": {"vo2max_rel": 60.7},
                "lactate": {"lt1_fixed_power_w": 225.0},
            },
        )
        create_submission(
            db_path,
            "delta runner 2",
            [{"name": "runner-2.fit"}],
            str(ws2),
            subject_id=subject["id"],
        )

        backfill_subject_metric_snapshots(db_path)
        first = backfill_longitudinal_delta_feature_sets(db_path)
        second = backfill_longitudinal_delta_feature_sets(db_path)

        rows = _fetch_feature_rows(db_path)
        assert len(rows) == 2
        assert first == {
            "dry_run": False,
            "snapshots_scanned": 2,
            "feature_rows_built": 2,
            "inserted": 2,
            "skipped": 0,
            "would_insert": 0,
            "errors": [],
        }
        assert second == {
            "dry_run": False,
            "snapshots_scanned": 2,
            "feature_rows_built": 2,
            "inserted": 0,
            "skipped": 2,
            "would_insert": 0,
            "errors": [],
        }

        first_payload = json.loads(rows[0]["feature_payload_json"])
        second_payload = json.loads(rows[1]["feature_payload_json"])
        assert first_payload["inputs"]["previous_snapshot_id"] is None
        assert second_payload["inputs"]["previous_snapshot_id"] is not None

    def test_dry_run_reports_would_insert_without_writing(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Dry Run Delta Subject")
        workspace = tmp_path / "workspaces" / "dry-run-delta"
        _create_analysis_db(
            workspace,
            "2026-03-22",
            metrics={"vo2max": {"vo2max_rel": 57.0}},
        )
        create_submission(
            db_path,
            "dry run delta",
            [{"name": "dry-delta.fit"}],
            str(workspace),
            subject_id=subject["id"],
        )

        backfill_subject_metric_snapshots(db_path)
        result = backfill_longitudinal_delta_feature_sets(db_path, dry_run=True)

        assert result == {
            "dry_run": True,
            "snapshots_scanned": 1,
            "feature_rows_built": 1,
            "inserted": 0,
            "skipped": 0,
            "would_insert": 1,
            "errors": [],
        }
        assert _fetch_feature_rows(db_path) == []

    def test_backfill_honors_snapshot_id_filter(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Delta Filter Subject")

        ws1 = tmp_path / "workspaces" / "delta-filter-1"
        _create_analysis_db(
            ws1,
            "2026-02-01",
            metrics={"vo2max": {"vo2max_rel": 57.2}},
        )
        create_submission(
            db_path,
            "delta filter 1",
            [{"name": "filter-1.fit"}],
            str(ws1),
            subject_id=subject["id"],
        )

        ws2 = tmp_path / "workspaces" / "delta-filter-2"
        _create_analysis_db(
            ws2,
            "2026-03-20",
            metrics={"vo2max": {"vo2max_rel": 60.7}},
        )
        create_submission(
            db_path,
            "delta filter 2",
            [{"name": "filter-2.fit"}],
            str(ws2),
            subject_id=subject["id"],
        )

        backfill_subject_metric_snapshots(db_path)
        snapshot_ids = _fetch_snapshot_ids(db_path)
        result = backfill_longitudinal_delta_feature_sets(
            db_path,
            snapshot_ids=[snapshot_ids[1]],
        )

        rows = _fetch_feature_rows(db_path)
        assert result == {
            "dry_run": False,
            "snapshots_scanned": 1,
            "feature_rows_built": 1,
            "inserted": 1,
            "skipped": 0,
            "would_insert": 0,
            "errors": [],
        }
        assert len(rows) == 1
        assert rows[0]["anchor_snapshot_id"] == snapshot_ids[1]
