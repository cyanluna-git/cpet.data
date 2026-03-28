"""
tests/test_subject_feature_sets_query.py — subject_feature_sets read helper tests.
"""

import sqlite3
from pathlib import Path

from server.db import (
    backfill_endurance_core_feature_sets,
    backfill_longitudinal_delta_feature_sets,
    backfill_subject_metric_snapshots,
    create_submission,
    create_subject,
    get_subject_feature_set,
    init_db,
    list_subject_feature_sets,
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
                conn.execute(
                    "INSERT OR REPLACE INTO analysis_results (category, key, value) VALUES (?, ?, ?)",
                    (category, key, str(value)),
                )
    conn.commit()
    conn.close()


def _seed_feature_rows(db_path: Path, tmp_path: Path) -> dict:
    subject_a = create_subject(db_path, name="Feature Subject A")
    subject_b = create_subject(db_path, name="Feature Subject B")

    for subject, slug, test_date, vo2 in (
        (subject_a, "a-1", "2026-02-01", 57.2),
        (subject_a, "a-2", "2026-03-20", 60.7),
        (subject_b, "b-1", "2026-03-12", 55.1),
    ):
        workspace = tmp_path / "workspaces" / slug
        _create_analysis_db(
            workspace,
            test_date,
            metrics={"vo2max": {"vo2max_rel": vo2}},
        )
        create_submission(
            db_path,
            f"seed {slug}",
            [{"name": f"{slug}.fit"}],
            str(workspace),
            subject_id=subject["id"],
        )

    backfill_subject_metric_snapshots(db_path)
    backfill_endurance_core_feature_sets(db_path)
    backfill_longitudinal_delta_feature_sets(db_path)

    rows = list_subject_feature_sets(db_path, include_payload=True, limit=20)
    return {
        "subject_a": subject_a,
        "subject_b": subject_b,
        "all_rows": rows,
    }


class TestSubjectFeatureSetsQuery:
    def test_list_filters_by_spec_and_subject_with_desc_order(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        seeded = _seed_feature_rows(db_path, tmp_path)

        rows = list_subject_feature_sets(
            db_path,
            subject_id=seeded["subject_a"]["id"],
            feature_spec_key="endurance_core",
            limit=10,
        )

        assert len(rows) == 2
        assert [row["anchor_measured_at"] for row in rows] == ["2026-03-20", "2026-02-01"]
        assert all(row["feature_spec_key"] == "endurance_core" for row in rows)
        assert all(row["subject_id"] == seeded["subject_a"]["id"] for row in rows)
        assert all(row["subject_name"] == "Feature Subject A" for row in rows)

    def test_list_can_include_payload_and_quality_flags(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        seeded = _seed_feature_rows(db_path, tmp_path)

        rows = list_subject_feature_sets(
            db_path,
            feature_spec_key="longitudinal_delta",
            include_payload=True,
            limit=10,
        )

        assert len(rows) >= 1
        latest = rows[0]
        assert isinstance(latest["feature_payload"], dict)
        assert isinstance(latest["quality_flags"], list)
        assert "anchor_source_kind" in latest["feature_payload"]["inputs"]
        assert "input_snapshot_ids" in latest
        assert "input_source_kinds" in latest

    def test_list_filters_by_window_label_and_anchor_source_kind(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        _seed_feature_rows(db_path, tmp_path)

        rows = list_subject_feature_sets(
            db_path,
            feature_spec_key="longitudinal_delta",
            window_label="previous_pair",
            anchor_source_kind="cpet_submission",
            include_payload=True,
            limit=10,
        )

        assert len(rows) == 3
        assert all(row["feature_spec_key"] == "longitudinal_delta" for row in rows)
        assert all(row["window_label"] == "previous_pair" for row in rows)
        assert all(row["anchor_source_kind"] == "cpet_submission" for row in rows)

    def test_get_returns_detail_row_and_none_for_missing(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        seeded = _seed_feature_rows(db_path, tmp_path)
        row_id = seeded["all_rows"][0]["feature_row_id"]

        detail = get_subject_feature_set(db_path, row_id)

        assert detail is not None
        assert detail["feature_row_id"] == row_id
        assert detail["subject_name"] in {"Feature Subject A", "Feature Subject B"}
        assert detail["anchor_snapshot_id"] is not None
        assert isinstance(detail["feature_payload"], dict)
        assert isinstance(detail["quality_flags"], list)
        assert get_subject_feature_set(db_path, "missing-feature-row") is None
