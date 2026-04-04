"""
Smoke tests for the platform validation demo DB seeder.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.seed_demo_platform_validation import seed_demo_platform_validation


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_seeder_builds_dense_isolated_demo_db(tmp_path: Path) -> None:
    summary = seed_demo_platform_validation(
        output_root=tmp_path / "demo-seed",
        subject_count=36,
        seed=1234,
        reset=True,
    )

    db_path = Path(summary["db_path"])
    published_dir = Path(summary["published_dir"])

    assert db_path.exists()
    assert published_dir.exists()

    conn = sqlite3.connect(str(db_path))
    try:
        assert _count(conn, "subjects") == 36
        assert _count(conn, "users") >= 20
        assert _count(conn, "submissions") >= 30
        assert _count(conn, "jobs") >= 30
        assert _count(conn, "report_catalog") >= 30
        assert _count(conn, "subject_metric_snapshots") >= 36
        assert _count(conn, "subject_feature_sets") >= 36

        duplicate_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM submissions
            WHERE duplicate_confidence IN ('exact', 'likely')
            """
        ).fetchone()[0]
        assert int(duplicate_rows) >= 3

        mixed_sources = conn.execute(
            "SELECT COUNT(DISTINCT source_kind) FROM subject_metric_snapshots"
        ).fetchone()[0]
        assert int(mixed_sources) >= 3

        repeated_subjects = conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT subject_id
                FROM subject_metric_snapshots
                GROUP BY subject_id
                HAVING COUNT(*) >= 2
            )
            """
        ).fetchone()[0]
        assert int(repeated_subjects) >= 8
    finally:
        conn.close()

    html_reports = list(published_dir.glob("*/index.html"))
    assert len(html_reports) >= 30


def test_seeder_is_repeatable_with_reset(tmp_path: Path) -> None:
    output_root = tmp_path / "repeatable-demo"
    first = seed_demo_platform_validation(
        output_root=output_root,
        subject_count=24,
        seed=2026,
        reset=True,
    )
    second = seed_demo_platform_validation(
        output_root=output_root,
        subject_count=24,
        seed=2026,
        reset=True,
    )

    assert first["subject_count"] == second["subject_count"] == 24
    assert first["submissions_seeded"] == second["submissions_seeded"]
    assert first["reports_seeded"] == second["reports_seeded"]
    assert first["snapshots_seeded"] == second["snapshots_seeded"]
