"""
tests/test_subject_metric_snapshots_inscyd.py — Contract tests for INSCYD snapshot extraction.
"""

import html
import json
from pathlib import Path
import shutil

from server.db import (
    create_submission,
    create_subject,
    extract_inscyd_snapshot,
    init_db,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"
INSCYD_FIXTURE_WS = FIXTURES_DIR / "inscyd_ppd"


def _init_platform_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "platform.db"
    init_db(db_path)
    return db_path


def _write_inscyd_report(workspace: Path, report_data: dict) -> Path:
    report_dir = workspace / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    html_path = report_dir / "index.html"
    payload = html.escape(json.dumps(report_data, ensure_ascii=False))
    html_path.write_text(
        f"<html><body><script id=\"report-data\" type=\"application/json\">{payload}</script></body></html>",
        encoding="utf-8",
    )
    return html_path


class TestExtractInscydSnapshot:
    def test_extracts_stable_snapshot_fields_from_report_html(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Geunyun Park")
        workspace = tmp_path / "workspaces" / "inscyd-1"
        _write_inscyd_report(
            workspace,
            {
                "meta": {"report_type": "inscyd"},
                "subject": {"name": "Geunyun Park"},
                "session": {"test_date": "2026-01-06", "test_type": "PPD"},
                "inscyd": {
                    "vo2max_rel_ml_kg_min": 51.7,
                    "fatmax_watt": 150.0,
                    "vlamax_mmol_l_s": 0.53,
                    "at_abs_watt": 230.0,
                    "carbmax_abs_watt": 318.0,
                    "glycogen_abs_g": 410.0,
                },
                "warnings": ["low confidence"],
            },
        )
        submission_id = create_submission(
            db_path,
            "inscyd upload",
            [{"name": "inscyd.pdf"}],
            str(workspace),
            subject_id=subject["id"],
        )

        snapshot = extract_inscyd_snapshot(db_path, submission_id)

        assert snapshot is not None
        assert len(snapshot["snapshot_id"]) == 36
        assert snapshot["subject_id"] == subject["id"]
        assert snapshot["source_kind"] == "inscyd_report"
        assert snapshot["source_ref_id"] == submission_id
        assert snapshot["submission_id"] == submission_id
        assert snapshot["measured_at"] == "2026-01-06"
        assert snapshot["protocol_type"] == "PPD"
        assert snapshot["vo2max_rel"] == 51.7
        assert snapshot["fatmax_power_w"] == 150.0
        assert snapshot["vlamax"] == 0.53
        assert snapshot["at_power_w"] == 230.0
        assert snapshot["carbmax_w"] == 318.0
        assert snapshot["glycogen_g"] == 410.0
        assert snapshot["extraction_version"] == "inscyd_snapshot_v1"

        flags = json.loads(snapshot["quality_flags_json"])
        assert flags == ["missing_vo2max_ml"]
        payload = json.loads(snapshot["payload_json"])
        assert payload["source"]["submission_id"] == submission_id
        assert payload["source"]["report_html"] == "report/index.html"
        assert payload["session"]["test_date"] == "2026-01-06"
        assert payload["inscyd"]["vlamax_mmol_l_s"] == 0.53
        assert payload["missing_metrics"] == ["vo2max_ml"]

    def test_extracts_from_real_fixture_report(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Geunyun Park")
        submission_id = create_submission(
            db_path,
            "fixture inscyd",
            [{"name": "KY Park_2026.pdf"}],
            str(INSCYD_FIXTURE_WS),
            subject_id=subject["id"],
        )

        snapshot = extract_inscyd_snapshot(db_path, submission_id)

        assert snapshot is not None
        assert snapshot["measured_at"] == "2026-01-06"
        assert snapshot["protocol_type"] == "PPD"
        assert snapshot["vo2max_rel"] == 51.7
        assert snapshot["fatmax_power_w"] == 150.0
        assert snapshot["vlamax"] == 0.53
        assert snapshot["at_power_w"] == 230.0
        flags = json.loads(snapshot["quality_flags_json"])
        assert flags == ["missing_carbmax_w", "missing_glycogen_g", "missing_vo2max_ml"]

    def test_falls_back_to_submission_test_date_when_session_date_missing(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Fallback Subject")
        workspace = tmp_path / "workspaces" / "inscyd-fallback"
        _write_inscyd_report(
            workspace,
            {
                "session": {"test_type": "PPD"},
                "inscyd": {"vlamax_mmol_l_s": 0.41},
            },
        )
        submission_id = create_submission(
            db_path,
            "fallback inscyd",
            [{"name": "fallback.pdf"}],
            str(workspace),
            subject_id=subject["id"],
            test_date="2026-01-09",
        )

        snapshot = extract_inscyd_snapshot(db_path, submission_id)

        assert snapshot is not None
        assert snapshot["measured_at"] == "2026-01-09"
        flags = json.loads(snapshot["quality_flags_json"])
        assert "fallback_submission_test_date" in flags

    def test_returns_none_without_subject_link(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        workspace = tmp_path / "workspaces" / "inscyd-orphan"
        _write_inscyd_report(
            workspace,
            {
                "session": {"test_date": "2026-01-06"},
                "inscyd": {"vlamax_mmol_l_s": 0.53},
            },
        )
        submission_id = create_submission(
            db_path,
            "orphan inscyd",
            [{"name": "orphan.pdf"}],
            str(workspace),
        )

        assert extract_inscyd_snapshot(db_path, submission_id) is None

    def test_falls_back_to_raw_workspace_when_report_html_is_missing(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="Geunyun Park")
        workspace = tmp_path / "workspaces" / "inscyd-raw-only"
        raw_dir = workspace / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir = workspace / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)

        for path in (INSCYD_FIXTURE_WS / "raw").iterdir():
            shutil.copy2(path, raw_dir / path.name)
        (metadata_dir / "submission_context.json").write_text(
            json.dumps({
                "report_type": "inscyd",
                "subject_name": "박근윤",
                "test_date": "2026-01-06",
            }),
            encoding="utf-8",
        )

        submission_id = create_submission(
            db_path,
            "raw only inscyd",
            [{"name": "KY Park_2026.pdf"}],
            str(workspace),
            subject_id=subject["id"],
            test_date="2026-01-06",
        )

        snapshot = extract_inscyd_snapshot(db_path, submission_id)

        assert snapshot is not None
        assert snapshot["measured_at"] == "2026-01-06"
        assert snapshot["protocol_type"] == "PPD"
        assert snapshot["vo2max_ml"] == 3836.0
        assert snapshot["vo2max_rel"] == 51.7
        assert snapshot["fatmax_power_w"] == 150.0
        assert snapshot["vlamax"] == 0.53
        assert snapshot["at_power_w"] == 230.0
        assert snapshot["carbmax_w"] == 178.0
        assert snapshot["glycogen_g"] == 373.0
        payload = json.loads(snapshot["payload_json"])
        assert payload["source"]["workspace_mode"] == "raw_inscyd_workspace"
        assert payload["subject"]["name"] == "박근윤"
        assert payload["protocol"]["fit_sessions"]

    def test_returns_none_without_report_html(self, tmp_path: Path) -> None:
        db_path = _init_platform_db(tmp_path)
        subject = create_subject(db_path, name="No Report")
        workspace = tmp_path / "workspaces" / "inscyd-missing"
        workspace.mkdir(parents=True)
        submission_id = create_submission(
            db_path,
            "missing report",
            [{"name": "missing.pdf"}],
            str(workspace),
            subject_id=subject["id"],
        )

        assert extract_inscyd_snapshot(db_path, submission_id) is None
