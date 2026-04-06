"""
tests/test_e2e.py — End-to-end tests for cross-module flows.

Covers three major gaps:
1. Upload → pipeline CLI subprocess → verify artifacts
2. Report HTML content regression
3. Full lifecycle: upload → pipeline → publish → job done

Reference values from test_pipeline.py:
  Park Geunyun: fatmax_power_w=175, vo2max_ml=4505.3, vo2max_rel=60.7
  Hong Changsun: fatmax_power_w=225, vo2max_ml=4490.9, vo2max_rel=66.9
"""

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from server.db import get_job, get_submission, list_jobs, update_job_status
from server.main import app
from server.publish import publish_report

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PARK_WS = FIXTURES_DIR / "park_geunyun"
HONG_WS = FIXTURES_DIR / "hong_changsun"
COSMED_WS = FIXTURES_DIR / "cosmed_only"

PYTHON = str(Path(__file__).parent.parent / "backend" / ".venv" / "bin" / "python3")

# Fall back to sys.executable if backend venv doesn't exist
if not Path(PYTHON).exists():
    PYTHON = sys.executable


def _assert_within_pct(
    actual: float, expected: float, pct: float = 1.0, label: str = ""
) -> None:
    """Assert actual is within +/-pct% of expected."""
    if expected == 0:
        assert abs(actual) < 0.01, f"{label}: expected ~0, got {actual}"
        return
    diff_pct = abs(actual - expected) / abs(expected) * 100
    assert diff_pct <= pct, (
        f"{label}: {actual} is {diff_pct:.2f}% from reference {expected} "
        f"(tolerance: +/-{pct}%)"
    )


# =====================================================================
# Class 1: Upload → Pipeline Integration
# =====================================================================


class TestUploadToPipeline:
    """Upload real fixture files via API, run pipeline CLI, verify outputs."""

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_upload_park_creates_workspace(
        self,
        mock_channel: AsyncMock,
        e2e_client: TestClient,
        park_fixture_files: list,
    ) -> None:
        """Upload Park fixture files → workspace raw/ contains all files."""
        resp = e2e_client.post(
            "/api/submit",
            files=park_fixture_files,
            data={
                "description": "Park Belgium test",
                "subject_name": "Park Geunyun",
                "test_date": "2026-03-20",
            },
        )
        assert resp.status_code == 201

        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        assert len(jobs) == 1
        sub = get_submission(db_path, jobs[0]["submission_id"])
        assert sub is not None
        ws = Path(sub["workspace_path"])

        raw_files = {f.name for f in (ws / "raw").iterdir()}
        assert any(f.endswith(".xlsx") for f in raw_files)
        assert any(f.endswith(".fit") for f in raw_files)
        assert any(f.endswith(".md") for f in raw_files)

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_upload_then_pipeline_cli(
        self,
        mock_channel: AsyncMock,
        e2e_client: TestClient,
        park_fixture_files: list,
    ) -> None:
        """Upload Park → run pipeline CLI as subprocess → analysis.db + report exist."""
        resp = e2e_client.post(
            "/api/submit",
            files=park_fixture_files,
            data={
                "description": "Park pipeline test",
                "subject_name": "Park Geunyun",
                "test_date": "2026-03-20",
            },
        )
        assert resp.status_code == 201

        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        sub = get_submission(db_path, jobs[0]["submission_id"])
        ws = Path(sub["workspace_path"])

        result = subprocess.run(
            [PYTHON, "-m", "pipeline", "--workspace", str(ws)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Pipeline failed:\n{result.stderr}"

        assert (ws / "analysis.db").exists()
        assert (ws / "report" / "index.html").exists()
        assert (ws / "report" / "index.html").stat().st_size > 10000

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_pipeline_cli_cosmed_only_workspace(
        self,
        mock_channel: AsyncMock,
        e2e_client: TestClient,
        cosmed_only_fixture_files: list,
    ) -> None:
        """Pipeline CLI succeeds on COSMED-only workspace (no FIT/lactate)."""
        resp = e2e_client.post(
            "/api/submit",
            files=cosmed_only_fixture_files,
            data={
                "description": "COSMED only test",
                "subject_name": "Test Subject",
                "test_date": "2026-03-20",
            },
        )
        assert resp.status_code == 201

        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        sub = get_submission(db_path, jobs[0]["submission_id"])
        ws = Path(sub["workspace_path"])

        result = subprocess.run(
            [PYTHON, "-m", "pipeline", "--workspace", str(ws)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Pipeline failed:\n{result.stderr}"
        assert (ws / "analysis.db").exists()
        assert (ws / "report" / "index.html").exists()

    def test_pipeline_cli_invalid_workspace_returns_nonzero(
        self, tmp_path: Path
    ) -> None:
        """Pipeline CLI returns non-zero exit code for nonexistent workspace."""
        fake_ws = tmp_path / "nonexistent"
        result = subprocess.run(
            [PYTHON, "-m", "pipeline", "--workspace", str(fake_ws)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_pipeline_analysis_values_match_reference(
        self,
        mock_channel: AsyncMock,
        e2e_client: TestClient,
        park_fixture_files: list,
    ) -> None:
        """Pipeline via uploaded workspace produces values within 1% of reference."""
        import sqlite3

        resp = e2e_client.post(
            "/api/submit",
            files=park_fixture_files,
            data={
                "description": "Park values check",
                "subject_name": "Park Geunyun",
                "test_date": "2026-03-20",
            },
        )
        assert resp.status_code == 201

        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        sub = get_submission(db_path, jobs[0]["submission_id"])
        ws = Path(sub["workspace_path"])

        result = subprocess.run(
            [PYTHON, "-m", "pipeline", "--workspace", str(ws)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0

        conn = sqlite3.connect(str(ws / "analysis.db"))
        rows = conn.execute(
            "SELECT category, key, value FROM analysis_results"
        ).fetchall()
        conn.close()

        results: dict[str, dict[str, Any]] = {}
        for cat, key, val in rows:
            if cat not in results:
                results[cat] = {}
            try:
                results[cat][key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                results[cat][key] = val

        _assert_within_pct(
            results["vo2max"]["vo2max_ml"], 4505.3, label="vo2max_ml"
        )
        _assert_within_pct(
            results["substrate"]["fatmax_power_w"], 175, label="fatmax_power_w"
        )


# =====================================================================
# Class 2: Report Content Regression
# =====================================================================


class TestReportContentRegression:
    """Verify generated report HTML contains expected content."""

    @pytest.fixture(autouse=True)
    def park_report_html(self) -> str:
        """Generate Park report and return HTML content."""
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database
        from pipeline.analysis import run_analysis
        from pipeline.report import generate_report

        parsed = parse_workspace(PARK_WS)
        db_path = create_database(PARK_WS, parsed)
        run_analysis(db_path)
        report_path = generate_report(db_path, PARK_WS / "report")
        self._park_html = report_path.read_text(encoding="utf-8")

    def test_park_report_contains_fatmax_power(self) -> None:
        """Park report HTML mentions FatMax power near 175W."""
        assert "175" in self._park_html
        assert "FatMax" in self._park_html

    def test_park_report_contains_vo2max_values(self) -> None:
        """Park report HTML contains VO2max metric values."""
        assert "VO2max" in self._park_html or "vo2max" in self._park_html
        assert "60.7" in self._park_html

    def test_park_report_contains_embedded_chart_data(self) -> None:
        """Park report HTML contains embedded JSON chart data."""
        assert 'id="chart-data"' in self._park_html
        assert 'id="report-data"' in self._park_html
        assert "JSON.parse" in self._park_html

    def test_hong_report_contains_expected_sections(self) -> None:
        """Hong report HTML contains coach summary, hero, and analysis sections."""
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database
        from pipeline.analysis import run_analysis
        from pipeline.report import generate_report

        parsed = parse_workspace(HONG_WS)
        db_path = create_database(HONG_WS, parsed)
        run_analysis(db_path)
        report_path = generate_report(db_path, HONG_WS / "report")
        html = report_path.read_text(encoding="utf-8")

        assert "coach-brief" in html
        assert "Belgium Lactate Test" in html
        assert "225" in html  # Hong FatMax power
        assert "66.9" in html  # Hong VO2max relative
        assert 'id="chart-data"' in html

    def test_park_report_contains_lactate_threshold(self) -> None:
        """Park report mentions lactate threshold values."""
        assert "171.2" in self._park_html  # LT1 fixed power

    def test_cosmed_report_uses_protocol_aware_conservative_copy(self) -> None:
        """COSMED-only report should surface indirect/suppressed metric messaging."""
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database
        from pipeline.analysis import run_analysis
        from pipeline.report import generate_report

        parsed = parse_workspace(COSMED_WS)
        db_path = create_database(COSMED_WS, parsed)
        run_analysis(db_path)
        report_path = generate_report(db_path, COSMED_WS / "report")
        html = report_path.read_text(encoding="utf-8")

        assert "VT1 (간접)" in html
        assert "LT1 (D-max)" not in html
        assert "FatMax 근사 band" in html or "FatMax band" in html
        assert "직접 lactate turnpoint 대신" in html or "ventilatory surrogate" in html


# =====================================================================
# Class 3: Full Lifecycle E2E
# =====================================================================


class TestFullLifecycleE2E:
    """Upload → pipeline → publish_report → job done with slug."""

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_full_lifecycle_upload_pipeline_publish(
        self,
        mock_channel: AsyncMock,
        e2e_client: TestClient,
        park_fixture_files: list,
    ) -> None:
        """Full flow: upload → pipeline subprocess → publish → job marked done."""
        resp = e2e_client.post(
            "/api/submit",
            files=park_fixture_files,
            data={
                "description": "full lifecycle",
                "subject_name": "Park Geunyun",
                "test_date": "2026-03-20",
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]

        db_path = app.state.db_path
        job = get_job(db_path, job_id)
        assert job is not None
        assert job["status"] == "pending"

        sub = get_submission(db_path, job["submission_id"])
        ws = Path(sub["workspace_path"])

        # Mark processing
        update_job_status(db_path, job_id, "processing")
        job = get_job(db_path, job_id)
        assert job["status"] == "processing"
        assert job["started_at"] is not None

        # Run pipeline
        result = subprocess.run(
            [PYTHON, "-m", "pipeline", "--workspace", str(ws)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0

        # Publish report
        publish_dir = ws.parent / "published"
        slug = publish_report(ws, "Park Geunyun", "2026-03-20", publish_dir)
        assert slug == "park-geunyun-20260320"
        assert (publish_dir / slug / "index.html").is_file()

        # Mark done
        update_job_status(
            db_path, job_id, "done",
            report_slug=slug,
            report_url=f"/reports/{slug}/",
        )
        job = get_job(db_path, job_id)
        assert job["status"] == "done"
        assert job["report_slug"] == slug
        assert job["completed_at"] is not None

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_upload_corrupt_data_pipeline_fails(
        self,
        mock_channel: AsyncMock,
        e2e_client: TestClient,
    ) -> None:
        """Upload corrupt xlsx → pipeline fails → job marked failed."""
        corrupt_files = [
            ("files", ("corrupt.xlsx", io.BytesIO(b"not-real-xlsx"), "application/octet-stream")),
        ]
        resp = e2e_client.post(
            "/api/submit",
            files=corrupt_files,
            data={
                "description": "corrupt data test",
                "subject_name": "Bad Data",
                "test_date": "2026-01-01",
            },
        )
        assert resp.status_code == 201
        job_id = resp.json()["job_id"]

        db_path = app.state.db_path
        sub = get_submission(db_path, resp.json()["job_id"])
        # get_job_by_submission not needed; we have job_id
        job = get_job(db_path, job_id)
        sub = get_submission(db_path, job["submission_id"])
        ws = Path(sub["workspace_path"])

        update_job_status(db_path, job_id, "processing")

        result = subprocess.run(
            [PYTHON, "-m", "pipeline", "--workspace", str(ws)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode != 0

        # Mark as failed
        update_job_status(
            db_path, job_id, "failed",
            error_message="Pipeline failed: corrupt COSMED file",
        )
        job = get_job(db_path, job_id)
        assert job["status"] == "failed"
        assert job["error_message"] is not None
        assert job["completed_at"] is not None

    @patch("server.api.notify_channel", new_callable=AsyncMock)
    def test_two_independent_subjects_no_interference(
        self,
        mock_channel: AsyncMock,
        e2e_client: TestClient,
        park_fixture_files: list,
        hong_fixture_files: list,
    ) -> None:
        """Two subjects uploaded independently produce separate workspaces and results."""
        resp_park = e2e_client.post(
            "/api/submit",
            files=park_fixture_files,
            data={
                "description": "Park subject",
                "subject_name": "Park Geunyun",
                "test_date": "2026-03-20",
            },
        )
        assert resp_park.status_code == 201

        resp_hong = e2e_client.post(
            "/api/submit",
            files=hong_fixture_files,
            data={
                "description": "Hong subject",
                "subject_name": "Hong Changsun",
                "test_date": "2026-03-19",
            },
        )
        assert resp_hong.status_code == 201

        db_path = app.state.db_path
        jobs = list_jobs(db_path)
        assert len(jobs) == 2

        park_job_id = resp_park.json()["job_id"]
        hong_job_id = resp_hong.json()["job_id"]
        assert park_job_id != hong_job_id

        park_job = get_job(db_path, park_job_id)
        hong_job = get_job(db_path, hong_job_id)

        park_sub = get_submission(db_path, park_job["submission_id"])
        hong_sub = get_submission(db_path, hong_job["submission_id"])

        park_ws = Path(park_sub["workspace_path"])
        hong_ws = Path(hong_sub["workspace_path"])
        assert park_ws != hong_ws

        # Run pipeline on both
        for ws in (park_ws, hong_ws):
            result = subprocess.run(
                [PYTHON, "-m", "pipeline", "--workspace", str(ws)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert result.returncode == 0, f"Pipeline failed for {ws.name}:\n{result.stderr}"

        # Verify separate analysis.db files
        assert (park_ws / "analysis.db").exists()
        assert (hong_ws / "analysis.db").exists()

        # Verify distinct results
        import sqlite3

        def _get_vo2max(ws: Path) -> float:
            conn = sqlite3.connect(str(ws / "analysis.db"))
            val = conn.execute(
                "SELECT value FROM analysis_results "
                "WHERE category='vo2max' AND key='vo2max_rel'"
            ).fetchone()[0]
            conn.close()
            return json.loads(val)

        park_vo2 = _get_vo2max(park_ws)
        hong_vo2 = _get_vo2max(hong_ws)

        _assert_within_pct(park_vo2, 60.7, label="Park vo2max_rel")
        _assert_within_pct(hong_vo2, 66.9, label="Hong vo2max_rel")
        assert abs(park_vo2 - hong_vo2) > 1.0, "Results should differ between subjects"
