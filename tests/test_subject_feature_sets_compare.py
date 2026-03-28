"""
tests/test_subject_feature_sets_compare.py — subject_feature_sets compare tests.
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from server.db import (
    backfill_endurance_core_feature_sets,
    backfill_longitudinal_delta_feature_sets,
    backfill_subject_metric_snapshots,
    build_subject_feature_set_compare,
    complete_onboarding,
    create_submission,
    create_subject,
    init_db,
    list_subject_feature_sets,
    upsert_user,
)
from server.main import app


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
                    "INSERT OR REPLACE INTO analysis_results (category, key, value) VALUES (?, ?, ?)",
                    (category, key, value_text),
                )
    conn.commit()
    conn.close()


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


def _seed_feature_sets(db_path: Path, data_dir: Path) -> dict[str, list[dict]]:
    subject = create_subject(db_path, name="Geunyun Park")
    for slug, test_date, vo2 in (
        ("cmp-1", "2026-02-01", 57.2),
        ("cmp-2", "2026-03-20", 60.7),
    ):
        workspace = data_dir / "workspaces" / slug
        _create_analysis_db(
            workspace,
            test_date,
            metrics={
                "vo2max": {"vo2max_rel": vo2},
                "lactate": {"lt1_fixed_power_w": 210.0 if slug == "cmp-1" else 225.0},
            },
        )
        create_submission(
            db_path,
            f"compare {slug}",
            [{"name": f"{slug}.fit"}],
            str(workspace),
            subject_id=subject["id"],
        )

    backfill_subject_metric_snapshots(db_path)
    backfill_endurance_core_feature_sets(db_path)
    backfill_longitudinal_delta_feature_sets(db_path)

    return {
        "endurance_core": list_subject_feature_sets(db_path, feature_spec_key="endurance_core", include_payload=True),
        "longitudinal_delta": list_subject_feature_sets(db_path, feature_spec_key="longitudinal_delta", include_payload=True),
    }


def _login_as_researcher(client: TestClient, google_id: str = "feature-compare-gid") -> None:
    db_path = app.state.db_path
    user = upsert_user(
        db_path,
        google_id=google_id,
        email=f"{google_id}@example.com",
        display_name="Feature Compare Researcher",
    )
    complete_onboarding(db_path, user["id"], "Feature Compare Researcher")
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE users SET role = 'researcher' WHERE id = ?", (user["id"],))
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
                "name": "Feature Compare Researcher",
                "picture": "",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)


class TestSubjectFeatureSetsCompare:
    def test_compare_builder_renders_shared_numeric_deltas(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        seeded = _seed_feature_sets(db_path, app.state.data_dir)
        baseline = seeded["endurance_core"][1]
        current = seeded["endurance_core"][0]

        compare = build_subject_feature_set_compare(
            db_path,
            baseline_feature_row_id=baseline["feature_row_id"],
            current_feature_row_id=current["feature_row_id"],
        )

        assert compare["feature_spec_key"] == "endurance_core"
        assert compare["baseline"]["feature_row_id"] == baseline["feature_row_id"]
        assert compare["current"]["feature_row_id"] == current["feature_row_id"]
        metrics = {metric["key"]: metric for metric in compare["metrics"]}
        assert "vo2max_rel" in metrics
        assert metrics["vo2max_rel"]["delta"] == 3.5

    def test_compare_builder_rejects_mixed_specs(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        seeded = _seed_feature_sets(db_path, app.state.data_dir)
        baseline = seeded["endurance_core"][0]
        current = seeded["longitudinal_delta"][0]

        try:
            build_subject_feature_set_compare(
                db_path,
                baseline_feature_row_id=baseline["feature_row_id"],
                current_feature_row_id=current["feature_row_id"],
            )
        except ValueError as exc:
            assert "same spec and version" in str(exc)
        else:
            raise AssertionError("expected ValueError for mixed spec compare")

    def test_compare_partial_renders_metric_deltas(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        seeded = _seed_feature_sets(db_path, app.state.data_dir)
        baseline = seeded["endurance_core"][1]
        current = seeded["endurance_core"][0]
        client = TestClient(app, raise_server_exceptions=False)
        _login_as_researcher(client)

        resp = client.get(
            "/api/manage/feature-sets/compare",
            params={
                "baseline_feature_row_id": baseline["feature_row_id"],
                "current_feature_row_id": current["feature_row_id"],
            },
        )

        assert resp.status_code == 200
        assert "Feature Set Compare" in resp.text
        assert baseline["feature_row_id"] in resp.text
        assert current["feature_row_id"] in resp.text
        assert "vo2max rel" in resp.text
        assert "3.50" in resp.text

    def test_compare_partial_rejects_mixed_spec_selection(self, tmp_path: Path) -> None:
        db_path = _setup_app(tmp_path)
        seeded = _seed_feature_sets(db_path, app.state.data_dir)
        baseline = seeded["endurance_core"][0]
        current = seeded["longitudinal_delta"][0]
        client = TestClient(app, raise_server_exceptions=False)
        _login_as_researcher(client)

        resp = client.get(
            "/api/manage/feature-sets/compare",
            params={
                "baseline_feature_row_id": baseline["feature_row_id"],
                "current_feature_row_id": current["feature_row_id"],
            },
        )

        assert resp.status_code == 400
        assert "same spec and version" in resp.text
