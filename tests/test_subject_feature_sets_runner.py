"""
tests/test_subject_feature_sets_runner.py — endurance_core feature set runner tests.
"""

import json
import sqlite3
from pathlib import Path

from server.db import (
    backfill_endurance_core_feature_sets,
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
) -> Path:
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


def _fetch_feature_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM subject_feature_sets ORDER BY anchor_measured_at, rowid"
    ).fetchall()
    conn.close()
    return rows


def _fetch_snapshot_ids(db_path: Path) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT snapshot_id FROM subject_metric_snapshots ORDER BY measured_at, rowid"
    ).fetchall()
    conn.close()
    return [str(row[0]) for row in rows]


class TestSubjectFeatureSetsRunner:
    def test_backfill_inserts_endurance_core_rows_and_is_idempotent(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Park Geunyun")

        ws1 = tmp_path / "workspaces" / "feature-1"
        _create_analysis_db(
            ws1,
            "2026-03-20",
            metrics={"vo2max": {"vo2max_rel": 60.7}},
        )
        create_submission(
            db_path,
            "feature 1",
            [{"name": "park-1.fit"}],
            str(ws1),
            subject_id=subject["id"],
        )

        ws2 = tmp_path / "workspaces" / "feature-2"
        _create_analysis_db(
            ws2,
            "2026-03-27",
            metrics={"vo2max": {"vo2max_rel": 61.8}},
        )
        create_submission(
            db_path,
            "feature 2",
            [{"name": "park-2.fit"}],
            str(ws2),
            subject_id=subject["id"],
        )

        backfill_subject_metric_snapshots(db_path)
        first = backfill_endurance_core_feature_sets(db_path)
        second = backfill_endurance_core_feature_sets(db_path)

        rows = _fetch_feature_rows(db_path)
        assert len(rows) == 2
        assert first == {
            "dry_run": False,
            "snapshots_scanned": 2,
            "feature_rows_built": 2,
            "inserted": 2,
            "updated": 0,
            "skipped": 0,
            "would_insert": 0,
            "would_update": 0,
            "errors": [],
        }
        assert second == {
            "dry_run": False,
            "snapshots_scanned": 2,
            "feature_rows_built": 2,
            "inserted": 0,
            "updated": 0,
            "skipped": 2,
            "would_insert": 0,
            "would_update": 0,
            "errors": [],
        }

    def test_dry_run_reports_would_insert_without_writing(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Dry Run Subject")
        workspace = tmp_path / "workspaces" / "dry-run"
        _create_analysis_db(
            workspace,
            "2026-03-22",
            metrics={"vo2max": {"vo2max_rel": 57.0}},
        )
        create_submission(
            db_path,
            "dry run cpet",
            [{"name": "dry.fit"}],
            str(workspace),
            subject_id=subject["id"],
        )

        backfill_subject_metric_snapshots(db_path)
        result = backfill_endurance_core_feature_sets(db_path, dry_run=True)

        assert result == {
            "dry_run": True,
            "snapshots_scanned": 1,
            "feature_rows_built": 1,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "would_insert": 1,
            "would_update": 0,
            "errors": [],
        }
        assert _fetch_feature_rows(db_path) == []

    def test_backfill_honors_snapshot_id_filter(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Filter Subject")

        ws1 = tmp_path / "workspaces" / "filter-1"
        _create_analysis_db(
            ws1,
            "2026-03-20",
            metrics={"vo2max": {"vo2max_rel": 60.7}},
        )
        create_submission(
            db_path,
            "filter 1",
            [{"name": "park-1.fit"}],
            str(ws1),
            subject_id=subject["id"],
        )

        ws2 = tmp_path / "workspaces" / "filter-2"
        _create_analysis_db(
            ws2,
            "2026-03-27",
            metrics={"vo2max": {"vo2max_rel": 61.8}},
        )
        create_submission(
            db_path,
            "filter 2",
            [{"name": "park-2.fit"}],
            str(ws2),
            subject_id=subject["id"],
        )

        backfill_subject_metric_snapshots(db_path)
        snapshot_ids = _fetch_snapshot_ids(db_path)

        result = backfill_endurance_core_feature_sets(
            db_path,
            snapshot_ids=[snapshot_ids[1]],
        )

        rows = _fetch_feature_rows(db_path)
        assert result == {
            "dry_run": False,
            "snapshots_scanned": 1,
            "feature_rows_built": 1,
            "inserted": 1,
            "updated": 0,
            "skipped": 0,
            "would_insert": 0,
            "would_update": 0,
            "errors": [],
        }
        assert len(rows) == 1
        assert rows[0]["anchor_snapshot_id"] == snapshot_ids[1]

    def test_backfill_updates_existing_row_when_anchor_snapshot_changes(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Refresh Subject")

        workspace = tmp_path / "workspaces" / "refresh-1"
        _create_analysis_db(
            workspace,
            "2026-03-20",
            metrics={"vo2max": {"vo2max_rel": 60.7}},
        )
        create_submission(
            db_path,
            "refresh feature",
            [{"name": "refresh.fit"}],
            str(workspace),
            subject_id=subject["id"],
        )

        backfill_subject_metric_snapshots(db_path)
        first = backfill_endurance_core_feature_sets(db_path)
        rows = _fetch_feature_rows(db_path)
        assert len(rows) == 1

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """UPDATE subject_metric_snapshots
               SET vo2max_rel = ?, extraction_version = ?
               WHERE snapshot_id = ?""",
            (63.1, "manual-refresh-v2", rows[0]["anchor_snapshot_id"]),
        )
        conn.commit()
        conn.close()

        second = backfill_endurance_core_feature_sets(db_path)
        refreshed = _fetch_feature_rows(db_path)
        payload = json.loads(refreshed[0]["feature_payload_json"])

        assert first["inserted"] == 1
        assert second == {
            "dry_run": False,
            "snapshots_scanned": 1,
            "feature_rows_built": 1,
            "inserted": 0,
            "updated": 1,
            "skipped": 0,
            "would_insert": 0,
            "would_update": 0,
            "errors": [],
        }
        assert payload["features"]["vo2max_rel"] == 63.1
