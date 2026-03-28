"""
tests/test_subject_metric_snapshots_runner.py — Upsert/backfill regression tests.
"""

import html
import json
import sqlite3
import shutil
from pathlib import Path
from unittest.mock import patch

from server.db import (
    backfill_subject_metric_snapshots,
    create_submission,
    create_subject,
    init_db,
    link_user_to_subject,
    link_report_to_user,
    upsert_user,
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


def _write_inscyd_report(workspace: Path, report_data: dict) -> None:
    report_dir = workspace / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = html.escape(json.dumps(report_data, ensure_ascii=False))
    (report_dir / "index.html").write_text(
        f"<html><body><script id=\"report-data\" type=\"application/json\">{payload}</script></body></html>",
        encoding="utf-8",
    )


def _fetch_snapshot_rows(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM subject_metric_snapshots ORDER BY source_kind, measured_at, rowid"
    ).fetchall()
    conn.close()
    return rows


class TestSubjectMetricSnapshotsRunner:
    def test_backfill_inserts_new_cpet_snapshot_and_is_idempotent(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Park Geunyun")
        workspace = tmp_path / "workspaces" / "park-1"
        _create_analysis_db(
            workspace,
            "2026-03-20",
            metrics={"vo2max": {"vo2max_rel": 60.7}},
        )
        create_submission(
            db_path,
            "park cpet",
            [{"name": "park.fit"}],
            str(workspace),
            subject_id=subject["id"],
        )

        first = backfill_subject_metric_snapshots(db_path)
        second = backfill_subject_metric_snapshots(db_path)

        rows = _fetch_snapshot_rows(db_path)
        assert len(rows) == 1
        assert first == {
            "dry_run": False,
            "submissions_scanned": 1,
            "snapshots_found": 1,
            "inserted": 1,
            "updated": 0,
            "skipped": 0,
            "would_insert": 0,
            "would_update": 0,
            "errors": [],
        }
        assert second == {
            "dry_run": False,
            "submissions_scanned": 1,
            "snapshots_found": 1,
            "inserted": 0,
            "updated": 0,
            "skipped": 1,
            "would_insert": 0,
            "would_update": 0,
            "errors": [],
        }

    def test_cpet_and_inscyd_same_date_remain_separate_rows(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Geunyun Park")

        cpet_ws = tmp_path / "workspaces" / "combo-cpet"
        _create_analysis_db(
            cpet_ws,
            "2026-01-06",
            metrics={"vo2max": {"vo2max_rel": 55.2}},
        )
        create_submission(
            db_path,
            "combo cpet",
            [{"name": "combo.fit"}],
            str(cpet_ws),
            subject_id=subject["id"],
        )

        inscyd_ws = tmp_path / "workspaces" / "combo-inscyd"
        _write_inscyd_report(
            inscyd_ws,
            {
                "session": {"test_date": "2026-01-06", "test_type": "PPD"},
                "inscyd": {"vlamax_mmol_l_s": 0.53, "fatmax_watt": 150.0},
            },
        )
        create_submission(
            db_path,
            "combo inscyd",
            [{"name": "combo.pdf"}],
            str(inscyd_ws),
            subject_id=subject["id"],
        )

        result = backfill_subject_metric_snapshots(db_path)

        rows = _fetch_snapshot_rows(db_path)
        assert result["inserted"] == 2
        assert len(rows) == 2
        assert {row["source_kind"] for row in rows} == {"cpet_submission", "inscyd_report"}
        assert {row["measured_at"] for row in rows} == {"2026-01-06"}

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

        result = backfill_subject_metric_snapshots(db_path, dry_run=True)

        assert result == {
            "dry_run": True,
            "submissions_scanned": 1,
            "snapshots_found": 1,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "would_insert": 1,
            "would_update": 0,
            "errors": [],
        }
        assert _fetch_snapshot_rows(db_path) == []

    def test_refreshes_existing_row_when_extraction_version_changes(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Refresh Subject")
        workspace = tmp_path / "workspaces" / "refresh-cpet"
        analysis_db = _create_analysis_db(
            workspace,
            "2026-03-23",
            metrics={"vo2max": {"vo2max_rel": 56.0}},
        )
        create_submission(
            db_path,
            "refresh cpet",
            [{"name": "refresh.fit"}],
            str(workspace),
            subject_id=subject["id"],
        )

        first = backfill_subject_metric_snapshots(db_path)
        before = _fetch_snapshot_rows(db_path)[0]

        conn = sqlite3.connect(str(analysis_db))
        conn.execute(
            "UPDATE analysis_results SET value = ? WHERE category = 'vo2max' AND key = 'vo2max_rel'",
            (json.dumps(61.2),),
        )
        conn.commit()
        conn.close()

        with patch("server.db._CPET_SNAPSHOT_EXTRACTION_VERSION", "cpet_snapshot_v2"):
            second = backfill_subject_metric_snapshots(db_path)

        after = _fetch_snapshot_rows(db_path)[0]
        assert first["inserted"] == 1
        assert second == {
            "dry_run": False,
            "submissions_scanned": 1,
            "snapshots_found": 1,
            "inserted": 0,
            "updated": 1,
            "skipped": 0,
            "would_insert": 0,
            "would_update": 0,
            "errors": [],
        }
        assert before["snapshot_id"] == after["snapshot_id"]
        assert before["created_at"] == after["created_at"]
        assert after["extraction_version"] == "cpet_snapshot_v2"
        assert after["vo2max_rel"] == 61.2

    def test_backfill_includes_linked_standalone_published_reports(self, tmp_path: Path) -> None:
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

        result = backfill_subject_metric_snapshots(db_path, published_dir=published_dir)
        rows = _fetch_snapshot_rows(db_path)

        assert result == {
            "dry_run": False,
            "submissions_scanned": 0,
            "snapshots_found": 1,
            "inserted": 1,
            "updated": 0,
            "skipped": 0,
            "would_insert": 0,
            "would_update": 0,
            "errors": [],
            "published_reports_scanned": 1,
        }
        assert len(rows) == 1
        assert rows[0]["source_kind"] == "published_cpet_report"
        assert rows[0]["source_ref_id"] == report_slug
        assert rows[0]["measured_at"] == "2026-03-20"
