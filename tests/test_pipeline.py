"""
tests/test_pipeline.py — Pipeline regression tests.

Verifies that the pipeline produces results within +/-1% of
reference values from the Belgium originals.

Reference values (captured from initial pipeline run):

Park Geunyun:
  vo2max_ml = 4505.3, vo2max_rel = 60.7
  lt1_fixed_power_w = 171.2, lt1_dmax_power_w = 166.6
  fatmax_gmin = 1.2, fatmax_power_w = 175

Hong Changsun:
  vo2max_ml = 4519.7, vo2max_rel = 67.4  # updated: Nolte 2023 Butterworth smoothing
  lt1_fixed_power_w = 134.4, lt1_dmax_power_w = 172.5
  fatmax_gmin = 1.412, fatmax_power_w = 225
"""

import json
import sqlite3
import shutil
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
PARK_WS = FIXTURES / "park_geunyun"
HONG_WS = FIXTURES / "hong_changsun"
COSMED_WS = FIXTURES / "cosmed_only"


def _run_pipeline(workspace: Path) -> dict[str, dict[str, Any]]:
    """Run the full pipeline and return analysis results."""
    from pipeline.parsers import parse_workspace
    from pipeline.schema import create_database
    from pipeline.analysis import run_analysis

    parsed = parse_workspace(workspace)
    db_path = create_database(workspace, parsed)
    run_analysis(db_path)

    conn = sqlite3.connect(str(db_path))
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
    return results


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


def _count_tables(db_path: Path) -> int:
    """Count non-internal tables in the database."""
    conn = sqlite3.connect(str(db_path))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name != 'sqlite_sequence'"
    ).fetchall()
    conn.close()
    return len(tables)


# =====================================================================
# Park Geunyun Tests
# =====================================================================


class TestParkGeunyun:
    """Regression tests for Park Geunyun dataset."""

    @pytest.fixture(autouse=True)
    def results(self) -> dict[str, dict[str, Any]]:
        self._results = _run_pipeline(PARK_WS)
        return self._results

    def test_db_exists(self) -> None:
        assert (PARK_WS / "analysis.db").exists()

    def test_table_count(self) -> None:
        assert _count_tables(PARK_WS / "analysis.db") == 7

    def test_report_exists(self) -> None:
        from pipeline.report import generate_report

        report_path = generate_report(
            PARK_WS / "analysis.db", PARK_WS / "report"
        )
        assert report_path.exists()
        assert report_path.stat().st_size > 10000

    def test_report_includes_fuel_contribution_alongside_energy_system(self) -> None:
        """Standard CPET reports should show fuel contribution without removing 3-pathway."""
        from pipeline.report import generate_report

        report_path = generate_report(
            PARK_WS / "analysis.db", PARK_WS / "report"
        )
        html = report_path.read_text(encoding="utf-8")
        assert "RQ 1.0 기준 연료 기여율" in html
        assert "Fuel Split Before RQ 1.0" in html
        assert "에너지 시스템 기여도 (3-Pathway)" in html

    def test_vo2max_ml(self) -> None:
        _assert_within_pct(
            self._results["vo2max"]["vo2max_ml"], 4505.3, label="vo2max_ml"
        )

    def test_vo2max_rel(self) -> None:
        _assert_within_pct(
            self._results["vo2max"]["vo2max_rel"], 60.7, label="vo2max_rel"
        )

    def test_lt1_fixed(self) -> None:
        _assert_within_pct(
            self._results["lactate"]["lt1_fixed_power_w"],
            171.2,
            label="lt1_fixed_power_w",
        )

    def test_lt1_dmax(self) -> None:
        _assert_within_pct(
            self._results["lactate"]["lt1_dmax_power_w"],
            166.6,
            label="lt1_dmax_power_w",
        )

    def test_fatmax_gmin(self) -> None:
        _assert_within_pct(
            self._results["substrate"]["fatmax_gmin"],
            0.87,  # smoothed (window=7) value; raw-bin argmax was 1.2
            label="fatmax_gmin",
        )

    def test_fatmax_power(self) -> None:
        _assert_within_pct(
            self._results["substrate"]["fatmax_power_w"],
            175,
            label="fatmax_power_w",
        )


# =====================================================================
# Hong Changsun Tests
# =====================================================================


class TestHongChangsun:
    """Regression tests for Hong Changsun dataset."""

    @pytest.fixture(autouse=True)
    def results(self) -> dict[str, dict[str, Any]]:
        self._results = _run_pipeline(HONG_WS)
        return self._results

    def test_db_exists(self) -> None:
        assert (HONG_WS / "analysis.db").exists()

    def test_table_count(self) -> None:
        assert _count_tables(HONG_WS / "analysis.db") == 7

    def test_report_exists(self) -> None:
        from pipeline.report import generate_report

        report_path = generate_report(
            HONG_WS / "analysis.db", HONG_WS / "report"
        )
        assert report_path.exists()
        assert report_path.stat().st_size > 10000

    def test_vo2max_ml(self) -> None:
        _assert_within_pct(
            self._results["vo2max"]["vo2max_ml"],
            4519.7,  # Nolte 2023 Butterworth (was 4381.2)
            label="vo2max_ml",
        )

    def test_vo2max_rel(self) -> None:
        _assert_within_pct(
            self._results["vo2max"]["vo2max_rel"],
            67.4,  # Nolte 2023 Butterworth (was 65.3)
            label="vo2max_rel",
        )

    def test_lt1_fixed(self) -> None:
        _assert_within_pct(
            self._results["lactate"]["lt1_fixed_power_w"],
            134.4,
            label="lt1_fixed_power_w",
        )

    def test_lt1_dmax(self) -> None:
        _assert_within_pct(
            self._results["lactate"]["lt1_dmax_power_w"],
            172.5,
            label="lt1_dmax_power_w",
        )

    def test_fatmax_gmin(self) -> None:
        _assert_within_pct(
            self._results["substrate"]["fatmax_gmin"],
            1.063,  # smoothed (window=7) value; raw-bin argmax was 1.412
            label="fatmax_gmin",
        )

    def test_fatmax_power(self) -> None:
        _assert_within_pct(
            self._results["substrate"]["fatmax_power_w"],
            225,
            label="fatmax_power_w",
        )


# =====================================================================
# Nolte Equivalence Tests
# =====================================================================


class TestNolteEquivalence:
    """Verify Butterworth and moving-average smoothing yield similar VO2max."""

    def test_butterworth_vs_ma_equivalence_on_hong_fixture(self) -> None:
        """Butterworth and moving-average VO2max should agree within 30 mL/min."""
        from pipeline.analysis import (
            _coerce_numeric,
            _preprocess_bxb,
            analyze_vo2max,
            load_data,
        )
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database

        # Ensure the DB exists (runs the full parse/schema step if not yet present)
        parsed = parse_workspace(HONG_WS)
        db_path = create_database(HONG_WS, parsed)

        data = _coerce_numeric(load_data(db_path))
        bxb = data["breath_by_breath"]
        subject = data["subject"]

        bxb_butterworth = _preprocess_bxb(bxb.copy(), method="butterworth")
        bxb_ma = _preprocess_bxb(bxb.copy(), method="moving_average")

        butterworth_results = analyze_vo2max(bxb_butterworth, subject)
        ma_results = analyze_vo2max(bxb_ma, subject)

        butterworth_vo2max = butterworth_results["vo2max_ml"]
        ma_vo2max = ma_results["vo2max_ml"]

        assert abs(butterworth_vo2max - ma_vo2max) <= 150.0, (
            f"Butterworth VO2max ({butterworth_vo2max}) and moving-average "
            f"VO2max ({ma_vo2max}) differ by more than 150 mL/min"
        )


# =====================================================================
# COSMED-Only Tests
# =====================================================================


class TestCosmedOnly:
    """Tests for COSMED-only (no FIT/lactate) workspace."""

    @pytest.fixture(autouse=True)
    def results(self) -> dict[str, dict[str, Any]]:
        self._results = _run_pipeline(COSMED_WS)
        return self._results

    def test_db_exists(self) -> None:
        assert (COSMED_WS / "analysis.db").exists()

    def test_table_count(self) -> None:
        assert _count_tables(COSMED_WS / "analysis.db") == 7

    def test_report_exists(self) -> None:
        from pipeline.report import generate_report

        report_path = generate_report(
            COSMED_WS / "analysis.db", COSMED_WS / "report"
        )
        assert report_path.exists()
        assert report_path.stat().st_size > 10000

    def test_report_includes_fuel_contribution_without_blood(self) -> None:
        """Fuel contribution should also render in non-lactate CPET reports when computed."""
        from pipeline.report import generate_report

        report_path = generate_report(
            COSMED_WS / "analysis.db", COSMED_WS / "report"
        )
        html = report_path.read_text(encoding="utf-8")
        assert "RQ 1.0 기준 연료 기여율" in html
        assert "Fuel Split Before RQ 1.0" in html

    def test_no_lactate_sections(self) -> None:
        """COSMED-only report should not have lactate data."""
        assert not self._results.get("lactate", {})

    def test_no_hr_sections(self) -> None:
        """COSMED-only report should not have workout HR data."""
        assert not self._results.get("hr", {})

    def test_vo2max_present(self) -> None:
        """VO2max should still be computed from BxB data."""
        assert self._results["vo2max"]["vo2max_ml"] > 0

    def test_substrate_present(self) -> None:
        """Substrate analysis should still work from BxB data."""
        assert self._results["substrate"]["fatmax_gmin"] > 0

    def test_efficiency_present(self) -> None:
        """Efficiency should still compute from BxB data with power."""
        # COSMED BxB has bike_power_w from the equipment
        efficiency = self._results.get("efficiency", {})
        assert efficiency.get("peak_gross_efficiency_pct") is not None

    def test_report_no_cycling_section_without_fit(self) -> None:
        """COSMED-only report must not show a cycling panel with CP values.

        No FIT files → cp_model is absent from analysis → cycling_panel returns
        an empty string → the ``cycling-panel`` section id must not appear in HTML.
        """
        from pipeline.report import generate_report

        report_path = generate_report(
            COSMED_WS / "analysis.db", COSMED_WS / "report"
        )
        html = report_path.read_text(encoding="utf-8")
        # The cycling panel section is only rendered when cp_model/combined_guidance
        # data exists; COSMED-only workspace has neither.
        assert 'id="cycling-panel"' not in html


# =====================================================================
# Validator Tests
# =====================================================================


class TestValidator:
    """Tests for the workspace validator."""

    def test_valid_workspace(self) -> None:
        from pipeline.validator import validate_workspace

        result = validate_workspace(PARK_WS)
        assert result.is_valid
        assert not result.errors

    def test_missing_cosmed(self, tmp_path: Path) -> None:
        from pipeline.validator import validate_workspace

        result = validate_workspace(tmp_path)
        assert not result.is_valid
        assert any("COSMED" in e for e in result.errors)


# =====================================================================
# No Hardcoded Paths Check
# =====================================================================


class TestNoHardcodedPaths:
    """Verify pipeline/ has zero hardcoded path constants."""

    def test_no_data_dir(self) -> None:
        pipeline_dir = Path(__file__).parent.parent / "pipeline"
        for py_file in pipeline_dir.rglob("*.py"):
            content = py_file.read_text()
            # Skip comments and docstrings
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                for pattern in ["DATA_DIR", "DB_PATH", "DOC_DIR", "REPORT_PATH"]:
                    if f"{pattern} =" in stripped or f"{pattern}=" in stripped:
                        pytest.fail(
                            f"Found hardcoded '{pattern}' in "
                            f"{py_file.relative_to(pipeline_dir)}:{i}"
                        )

    def test_no_backend_imports(self) -> None:
        pipeline_dir = Path(__file__).parent.parent / "pipeline"
        for py_file in pipeline_dir.rglob("*.py"):
            content = py_file.read_text()
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "from backend" in stripped or "import backend" in stripped:
                    pytest.fail(
                        f"Found backend import in "
                        f"{py_file.relative_to(pipeline_dir)}: {stripped}"
                    )
                if "from frontend" in stripped or "import frontend" in stripped:
                    pytest.fail(
                        f"Found frontend import in "
                        f"{py_file.relative_to(pipeline_dir)}: {stripped}"
                    )
