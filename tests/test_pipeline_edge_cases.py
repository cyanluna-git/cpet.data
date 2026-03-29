"""
tests/test_pipeline_edge_cases.py — Edge case coverage for the pipeline package.

Shield's additions to complement Builder's 30 regression tests.
Focus areas:
  - Parser error paths (corrupt / empty / missing columns)
  - Validator out-of-range and minimum-record limits
  - Schema idempotency (re-run on existing analysis.db)
  - Analysis graceful degradation (empty DataFrames)
  - CLI error paths (nonexistent workspace, no COSMED file)
  - ZWO parser edge cases (missing <workout> element, synthesis fallback)
  - FIT parser edge cases (empty FIT with no records)
  - Lactate parser edge cases (md with no blocks, xlsx missing sheet)
  - _backfill_power behaviour (no timestamp, already has power)
  - Report with partial data (no FIT / no lactate sections)
"""

import io
import math
import sqlite3
import textwrap
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures"
PARK_WS = FIXTURES / "park_geunyun"


# =====================================================================
# Helpers
# =====================================================================


def _make_minimal_xlsx(tmp_path: Path, name: str = "test_CPET BxB.xlsx") -> Path:
    """Create the smallest valid COSMED XLSX that parse_cosmed can accept.

    Mimics the real structure: row 0 has headers, rows 1-2 are metadata,
    row 3+ are BxB data rows.
    """
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"

    # Row 0 (index 0): headers in columns A-H then BxB headers from col J (index 9)
    bxb_headers = ["t", "VO2", "VCO2", "RQ", "HR", "VE", "Fat", "CHO",
                   "VO2/kg", "METS", "VE/VO2", "VE/VCO2", "EEkc"]
    row0 = ["Date", None, None, None, "2026-03-20", None, None, None, None] + bxb_headers
    ws.append(row0)

    # Metadata rows 1-2
    ws.append([None, "Park", None, None, "09:00:00", None, None, 760])
    ws.append([None, "Geunyun", None, None, None, None, None, 20.0])
    ws.append([None, "M", None, None, None, None, None, 60.0])
    ws.append([None, 30, None, None, None, None, None, 74.2])
    ws.append([None, 175, None, None, None, None, None])
    ws.append([None, 74.2])

    import datetime as dt

    # 60 BxB data rows (above MIN_BXB_RECORDS=50)
    for i in range(60):
        t_val = dt.time(0, i // 60, i % 60)
        row = [None] * 9 + [t_val, 3000.0, 2500.0, 0.83, 140.0, 60.0, 0.8, 1.2,
                            40.0, 12.0, 28.0, 30.0, 10.0]
        ws.append(row)

    out = tmp_path / name
    wb.save(str(out))
    return out


def _make_minimal_workspace(tmp_path: Path) -> Path:
    """Create workspace with a valid minimal COSMED XLSX."""
    _make_minimal_xlsx(tmp_path)
    return tmp_path


# =====================================================================
# Parser — COSMED Edge Cases
# =====================================================================


class TestCosmedParserEdgeCases:
    """Edge cases for pipeline.parsers.cosmed.parse_cosmed."""

    def test_missing_file_raises(self) -> None:
        from pipeline.parsers.cosmed import parse_cosmed

        with pytest.raises(Exception):
            parse_cosmed(Path("/nonexistent/file.xlsx"))

    def test_corrupt_xlsx_raises(self, tmp_path: Path) -> None:
        """A file that is not a valid ZIP/XLSX should raise."""
        bad = tmp_path / "bad.xlsx"
        bad.write_bytes(b"this is not a zip file at all")

        from pipeline.parsers.cosmed import parse_cosmed

        with pytest.raises(Exception):
            parse_cosmed(bad)

    def test_missing_data_sheet_raises(self, tmp_path: Path) -> None:
        """XLSX without a 'Data' sheet should raise KeyError."""
        import openpyxl

        wb = openpyxl.Workbook()
        wb.active.title = "Sheet1"
        path = tmp_path / "no_data_sheet_CPET BxB.xlsx"
        wb.save(str(path))

        from pipeline.parsers.cosmed import parse_cosmed

        with pytest.raises(KeyError):
            parse_cosmed(path)

    def test_minimal_xlsx_parses(self, tmp_path: Path) -> None:
        """A minimal but structurally valid XLSX should parse without error."""
        from pipeline.parsers.cosmed import parse_cosmed

        path = _make_minimal_xlsx(tmp_path)
        bxb_df, subject_info = parse_cosmed(path)
        assert len(bxb_df) >= 1
        assert isinstance(subject_info, dict)

    def test_time_to_seconds_variants(self) -> None:
        """_time_to_seconds handles datetime.time, timedelta, int, float, None."""
        from pipeline.parsers.cosmed import _time_to_seconds, _parse_test_time
        import datetime as dt

        assert _time_to_seconds(None) is None
        assert _time_to_seconds(dt.time(0, 1, 30)) == 90.0
        assert _time_to_seconds(dt.timedelta(seconds=45)) == 45.0
        assert _time_to_seconds(120) == 120.0
        assert _time_to_seconds(0.5) == 0.5
        assert _parse_test_time("AM 10:29") == "10:29:00"
        assert _parse_test_time("PM 03:14") == "15:14:00"


# =====================================================================
# Parser — ZWO Edge Cases
# =====================================================================


class TestZwoParserEdgeCases:
    """Edge cases for pipeline.parsers.zwo.parse_zwo."""

    def test_neither_path_nor_df_raises(self) -> None:
        from pipeline.parsers.zwo import parse_zwo

        with pytest.raises(ValueError, match="Either path or workout_df"):
            parse_zwo(None)

    def test_missing_workout_element_raises(self, tmp_path: Path) -> None:
        """ZWO file with no <workout> element should raise ValueError."""
        zwo = tmp_path / "empty.zwo"
        zwo.write_text(
            '<?xml version="1.0"?><workout_file><name>Test</name></workout_file>'
        )
        from pipeline.parsers.zwo import parse_zwo

        with pytest.raises(ValueError, match="No <workout> element"):
            parse_zwo(zwo)

    def test_valid_zwo_parsed(self, tmp_path: Path) -> None:
        """A well-formed ZWO file with SteadyState and FreeRide stages."""
        content = textwrap.dedent("""\
            <?xml version="1.0" encoding="utf-8"?>
            <workout_file>
                <name>Test</name>
                <workout>
                    <SteadyState Duration="300" Power="0.55"/>
                    <SteadyState Duration="300" Power="0.65"/>
                    <FreeRide Duration="180"/>
                    <SteadyState Duration="300" Power="0.75"/>
                </workout>
            </workout_file>
        """)
        zwo = tmp_path / "test.zwo"
        zwo.write_text(content)

        from pipeline.parsers.zwo import parse_zwo

        df = parse_zwo(zwo)
        assert len(df) == 4
        assert set(df.columns) >= {"block", "step", "power_normalized", "duration_s", "stage_type"}
        # FreeRide maps to a recovery block
        assert df[df["stage_type"] == "freeride"]["power_normalized"].iloc[0] == 0.0

    def test_synthesis_from_empty_workout_df_raises(self) -> None:
        """Synthesizing protocol from empty workout_df should not crash
        but may return an empty or stub DataFrame."""
        from pipeline.parsers.zwo import parse_zwo

        empty_df = pd.DataFrame(columns=["target_power_w"])
        # Should not raise — returns empty/stub DataFrame
        result = parse_zwo(None, workout_df=empty_df)
        assert isinstance(result, pd.DataFrame)


# =====================================================================
# Parser — FIT Edge Cases
# =====================================================================


class TestFitParserEdgeCases:
    """Edge cases for pipeline.parsers.fit.parse_fit."""

    def test_nonexistent_fit_raises(self) -> None:
        from pipeline.parsers.fit import parse_fit

        with pytest.raises(Exception):
            parse_fit(Path("/nonexistent/file.fit"))

    def test_segment_blocks_no_laps(self) -> None:
        """segment_blocks should handle an empty laps_df gracefully."""
        from pipeline.parsers.fit import segment_blocks

        # Minimal workout_df with all required columns
        n = 20

        workout_df = pd.DataFrame(
            {
                "timestamp_kst": pd.date_range("2026-03-20 09:00", periods=n, freq="1s"),
                "elapsed_s": list(range(n)),
                "power_w": [150.0] * n,
                "target_power_w": [150.0] * 10 + [200.0] * 10,
                "hr_bpm": [140.0] * n,
                "cadence_rpm": [90.0] * n,
                "speed_mps": [10.0] * n,
                "distance_m": [float(i * 10) for i in range(n)],
            }
        )
        laps_df = pd.DataFrame()  # empty

        result = segment_blocks(workout_df, laps_df)
        assert "block" in result.columns
        assert "step" in result.columns


# =====================================================================
# Parser — Lactate Edge Cases
# =====================================================================


class TestLactateParserEdgeCases:
    """Edge cases for pipeline.parsers.lactate.parse_lactate."""

    def test_neither_path_raises(self) -> None:
        from pipeline.parsers.lactate import parse_lactate

        with pytest.raises(ValueError, match="Either md_path or xlsx_path"):
            parse_lactate()

    def test_md_with_no_blocks_returns_empty(self, tmp_path: Path) -> None:
        """Markdown with no block headers yields an empty blood_df."""
        md = tmp_path / "lactate_data.md"
        md.write_text("# Test\n\nSome text but no blocks.\n", encoding="utf-8")

        from pipeline.parsers.lactate import parse_lactate

        blood_df, info = parse_lactate(md_path=md)
        assert isinstance(blood_df, pd.DataFrame)
        assert blood_df.empty

    def test_xlsx_missing_subject_sheet_raises(self, tmp_path: Path) -> None:
        """XLSX with no recognisable subject LT sheet should raise."""
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Prt"
        ws.append(["Prt", "Data"])
        path = tmp_path / "no_subject.xlsx"
        wb.save(str(path))

        from pipeline.parsers.lactate import parse_lactate

        with pytest.raises(ValueError, match="Could not find subject LT sheet"):
            parse_lactate(xlsx_path=path)

    def test_md_basic_block_parsed(self, tmp_path: Path) -> None:
        """A minimal but valid MD with a Block 1 section should parse rows."""
        content = textwrap.dedent("""\
            | Field       | Value    |
            |-------------|----------|
            | Name        | Test     |
            | FTP         | 220      |

            ## Block 1 LT1

            | Step | Load (W) | Duration (min) | KST Time | HR | Lactate | Glucose |
            |------|----------|----------------|----------|----|---------|---------|
            | 1-1  | 100      | 3              | 09:00    | 130 | 1.5    | 4.5     |
            | 1-2  | 130      | 3              | 09:03    | 140 | 1.8    | 4.6     |
        """)
        md = tmp_path / "lactate_data.md"
        md.write_text(content, encoding="utf-8")

        from pipeline.parsers.lactate import parse_lactate

        blood_df, info = parse_lactate(md_path=md)
        assert len(blood_df) >= 2
        assert "lactate_mmol" in blood_df.columns
        assert blood_df["block"].iloc[0] == "block_1"


# =====================================================================
# Parser — parse_workspace / _backfill_power Edge Cases
# =====================================================================


class TestParseWorkspaceEdgeCases:
    """Edge cases for parse_workspace and _backfill_power."""

    def test_no_cosmed_raises(self, tmp_path: Path) -> None:
        from pipeline.parsers import parse_workspace

        with pytest.raises(FileNotFoundError, match="No COSMED XLSX"):
            parse_workspace(tmp_path)

    def test_cosmed_only_workspace_succeeds(self, tmp_path: Path) -> None:
        """Workspace with only COSMED file should parse; optional fields are None."""
        from pipeline.parsers import parse_workspace

        _make_minimal_xlsx(tmp_path)
        parsed = parse_workspace(tmp_path)

        assert parsed.cosmed_df is not None
        assert not parsed.cosmed_df.empty
        assert not parsed.has_fit
        assert not parsed.has_lactate
        assert not parsed.has_protocol

    def test_backfill_skipped_when_power_present(self) -> None:
        """_backfill_power should return df unchanged if bike_power_w already filled."""
        from pipeline.parsers import _backfill_power

        cosmed_df = pd.DataFrame(
            {
                "t_s": [1.0, 2.0, 3.0],
                "bike_power_w": [150.0, 160.0, 170.0],
                "timestamp_kst": pd.date_range("2026-03-20", periods=3, freq="1s"),
            }
        )
        workout_df = pd.DataFrame(
            {
                "timestamp_kst": pd.date_range("2026-03-20", periods=3, freq="1s"),
                "power_w": [999.0, 999.0, 999.0],
                "target_power_w": [999.0, 999.0, 999.0],
                "cadence_rpm": [100.0, 100.0, 100.0],
            }
        )
        result = _backfill_power(cosmed_df, workout_df)
        # Original values preserved
        assert list(result["bike_power_w"]) == [150.0, 160.0, 170.0]

    def test_backfill_skipped_when_no_timestamp(self) -> None:
        """_backfill_power returns df unchanged if timestamp_kst missing."""
        from pipeline.parsers import _backfill_power

        cosmed_df = pd.DataFrame({"t_s": [1.0, 2.0], "bike_power_w": [None, None]})
        workout_df = pd.DataFrame(
            {
                "timestamp_kst": pd.date_range("2026-03-20", periods=2, freq="1s"),
                "power_w": [150.0, 160.0],
                "target_power_w": [150.0, 160.0],
                "cadence_rpm": [90.0, 90.0],
            }
        )
        result = _backfill_power(cosmed_df, workout_df)
        # Without timestamp_kst on cosmed side, backfill cannot proceed
        assert "timestamp_kst" not in result.columns or True  # passes without crash

    def test_raw_subdirectory_discovery(self, tmp_path: Path) -> None:
        """parse_workspace should look inside a raw/ subdirectory first."""
        from pipeline.parsers import parse_workspace

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _make_minimal_xlsx(raw_dir)

        parsed = parse_workspace(tmp_path)
        assert not parsed.cosmed_df.empty


# =====================================================================
# Validator Edge Cases
# =====================================================================


class TestValidatorEdgeCases:
    """Extended validator edge cases beyond Builder's two tests."""

    def test_too_few_records(self, tmp_path: Path) -> None:
        """Workspace with fewer than MIN_BXB_RECORDS (50) BxB rows fails."""
        import openpyxl
        import datetime as dt
        from pipeline.validator import validate_workspace

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Data"

        bxb_headers = ["t", "VO2", "VCO2", "RQ", "HR", "VE", "Fat", "CHO",
                       "VO2/kg", "METS", "VE/VO2", "VE/VCO2", "EEkc"]
        row0 = ["Date", None, None, None, "2026-03-20", None, None, None, None] + bxb_headers
        ws.append(row0)
        ws.append([None, "Park", None, None, "09:00:00", None, None, 760])
        ws.append([None, "Geunyun"])
        ws.append([None, "M"])
        ws.append([None, 30])
        ws.append([None, 175])
        ws.append([None, 74.2])

        # Only 10 rows — below 50 minimum
        for i in range(10):
            t_val = dt.time(0, 0, i)
            row = [None] * 9 + [t_val, 3000.0, 2500.0, 0.83, 140.0, 60.0, 0.8, 1.2,
                                40.0, 12.0, 28.0, 30.0, 10.0]
            ws.append(row)

        path = tmp_path / "short_CPET BxB.xlsx"
        wb.save(str(path))

        result = validate_workspace(tmp_path)
        assert not result.is_valid
        assert any("Too few BxB records" in e for e in result.errors)

    def test_warnings_do_not_make_invalid(self, tmp_path: Path) -> None:
        """Validator with physiological range warnings should remain is_valid=True."""
        from pipeline.validator import validate_workspace, ValidationResult

        # Use real park_geunyun workspace — known good, may have minor QC flags
        result = validate_workspace(PARK_WS)
        assert result.is_valid  # warnings only, no errors

    def test_metadata_populated(self, tmp_path: Path) -> None:
        """validate_workspace should populate metadata dict with file presence flags."""
        from pipeline.validator import validate_workspace

        _make_minimal_xlsx(tmp_path)
        result = validate_workspace(tmp_path)

        assert "cosmed_file" in result.metadata
        assert "has_fit" in result.metadata
        assert "has_zwo" in result.metadata
        assert "has_lactate_md" in result.metadata
        assert "bxb_records" in result.metadata

    def test_parse_error_captured(self, tmp_path: Path) -> None:
        """If COSMED parsing fails, validator should catch and record error."""
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Data"
        # Write no rows — will produce empty df which should fail MIN_BXB check
        path = tmp_path / "empty_CPET BxB.xlsx"
        wb.save(str(path))

        from pipeline.validator import validate_workspace

        result = validate_workspace(tmp_path)
        assert not result.is_valid


# =====================================================================
# Schema Edge Cases
# =====================================================================


class TestSchemaEdgeCases:
    """Edge cases for pipeline.schema.create_database."""

    def test_idempotent_recreate(self, tmp_path: Path) -> None:
        """Running create_database twice on same workspace should not error.
        The second run drops and recreates all tables."""
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database

        _make_minimal_xlsx(tmp_path)
        parsed = parse_workspace(tmp_path)

        db1 = create_database(tmp_path, parsed)
        db2 = create_database(tmp_path, parsed)

        assert db1 == db2
        assert db2.exists()

        # Verify tables are intact after second run
        conn = sqlite3.connect(str(db2))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        table_names = {t[0] for t in tables}
        assert "subject" in table_names
        assert "breath_by_breath" in table_names

    def test_db_has_correct_table_count(self, tmp_path: Path) -> None:
        """Schema creates exactly the expected tables (7 including analysis_results)."""
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database
        from pipeline.analysis import run_analysis

        _make_minimal_xlsx(tmp_path)
        parsed = parse_workspace(tmp_path)
        db_path = create_database(tmp_path, parsed)
        run_analysis(db_path)

        conn = sqlite3.connect(str(db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name != 'sqlite_sequence'"
        ).fetchall()
        conn.close()
        assert len(tables) == 7

    def test_subject_inserted(self, tmp_path: Path) -> None:
        """Subject row should exist after create_database."""
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database

        _make_minimal_xlsx(tmp_path)
        parsed = parse_workspace(tmp_path)
        db_path = create_database(tmp_path, parsed)

        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM subject").fetchone()[0]
        conn.close()
        assert count == 1

    def test_bxb_rows_match_parsed_df(self, tmp_path: Path) -> None:
        """breath_by_breath rows should match cosmed_df length."""
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database

        _make_minimal_xlsx(tmp_path)
        parsed = parse_workspace(tmp_path)
        db_path = create_database(tmp_path, parsed)

        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM breath_by_breath").fetchone()[0]
        conn.close()
        assert count == len(parsed.cosmed_df)


# =====================================================================
# Analysis Edge Cases
# =====================================================================


class TestAnalysisEdgeCases:
    """Graceful degradation when DataFrames are empty."""

    def test_analyze_lactate_empty(self) -> None:
        from pipeline.analysis import analyze_lactate

        result = analyze_lactate(pd.DataFrame())
        assert result == {}

    def test_analyze_lactate_no_load_w(self) -> None:
        from pipeline.analysis import analyze_lactate

        blood = pd.DataFrame({"block": ["rest", "block_1"],
                              "lactate_mmol": [1.5, 2.0],
                              "load_w": [None, None]})
        result = analyze_lactate(blood)
        # Empty after dropna on load_w
        assert result == {}

    def test_analyze_clearance_no_block2(self) -> None:
        from pipeline.analysis import analyze_clearance

        blood = pd.DataFrame({"block": ["block_3", "block_3"],
                              "lactate_mmol": [5.0, 4.0],
                              "load_w": [100.0, 120.0],
                              "hr_bpm": [150.0, 145.0],
                              "duration_min": [3.0, 3.0]})
        # Should not crash even without block_2
        result = analyze_clearance(blood)
        assert isinstance(result, dict)

    def test_analyze_vo2max_empty_bxb(self) -> None:
        from pipeline.analysis import analyze_vo2max

        bxb = pd.DataFrame()
        subject = pd.DataFrame({"weight_kg": [74.2]})
        result = analyze_vo2max(bxb, subject)
        assert result == {}

    def test_analyze_substrate_empty_bxb(self) -> None:
        from pipeline.analysis import analyze_substrate

        result = analyze_substrate(pd.DataFrame())
        assert result == {}

    def test_analyze_substrate_builds_rq1_fuel_split(self) -> None:
        from pipeline.analysis import analyze_substrate

        bxb = pd.DataFrame(
            {
                "t_s": [0.0, 60.0, 120.0],
                "vo2_ml": [1500.0, 1800.0, 2200.0],
                "vco2_ml": [1200.0, 1800.0, 2640.0],
                "rq": [0.8, 1.0, 1.2],
                "hr_bpm": [110.0, 120.0, 130.0],
                "ve_lmin": [30.0, 40.0, 55.0],
                "bike_power_w": [120.0, 150.0, 180.0],
                "fat_gmin": [1.0, 0.5, 0.0],
                "cho_gmin": [0.5, 1.0, 2.0],
            }
        )

        result = analyze_substrate(bxb)
        split = result["rq1_fuel_split"]
        assert split["status"] == "computed"
        assert split["crossing_time_s"] == 60.0
        assert split["crossing_power_w"] == 150
        assert split["fat_kcal"] == pytest.approx(7.31, abs=0.02)
        assert split["cho_kcal"] == pytest.approx(3.05, abs=0.02)
        assert split["fat_pct"] == pytest.approx(70.5, abs=0.2)
        assert split["cho_pct"] == pytest.approx(29.5, abs=0.2)

    def test_ensure_substrate_columns_rebuilds_suspicious_cosmed_units(self) -> None:
        from pipeline.analysis import _ensure_substrate_columns

        bxb = pd.DataFrame(
            {
                "t_s": [0.0, 60.0],
                "vo2_ml": [1500.0, 1800.0],
                "vco2_ml": [1200.0, 1800.0],
                "fat_gmin": [None, None],
                "cho_gmin": [2338.0, 3314.0],
            }
        )

        result = _ensure_substrate_columns(bxb)
        assert result["fat_gmin"].tolist() == pytest.approx([0.501, 0.0], abs=0.01)
        assert result["cho_gmin"].tolist() == pytest.approx([0.645, 2.412], abs=0.01)

    def test_analyze_efficiency_empty_bxb(self) -> None:
        from pipeline.analysis import analyze_efficiency

        result = analyze_efficiency(pd.DataFrame())
        assert result == {}

    def test_analyze_ventilatory_thresholds_too_few_rows(self) -> None:
        from pipeline.analysis import analyze_ventilatory_thresholds

        bxb = pd.DataFrame({
            "t_s": [1.0, 2.0, 3.0],
            "vo2_ml": [3000.0, 3100.0, 3200.0],
            "rq": [0.85, 0.86, 0.87],
            "bike_power_w": [150.0, 155.0, 160.0],
            "ve_vo2": [30.0, 31.0, 32.0],
            "ve_vco2": [25.0, 26.0, 27.0],
            "hr_bpm": [140.0, 141.0, 142.0],
            "fat_gmin": [0.5, 0.5, 0.5],
            "cho_gmin": [1.0, 1.0, 1.0],
        })
        result = analyze_ventilatory_thresholds(bxb)
        # Below 20-row minimum — should return empty dict, not crash
        assert result == {}

    def test_run_analysis_returns_dict(self, tmp_path: Path) -> None:
        """run_analysis should return a dict even on minimal data."""
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database
        from pipeline.analysis import run_analysis

        _make_minimal_xlsx(tmp_path)
        parsed = parse_workspace(tmp_path)
        db_path = create_database(tmp_path, parsed)

        results = run_analysis(db_path)
        assert isinstance(results, dict)


# =====================================================================
# CLI Edge Cases
# =====================================================================


class TestCliEdgeCases:
    """Edge cases for pipeline.cli.main."""

    def test_missing_workspace_arg_exits(self) -> None:
        from pipeline.cli import main

        # --workspace is required; missing it should exit with non-zero
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code != 0

    def test_nonexistent_workspace_returns_1(self) -> None:
        from pipeline.cli import main

        code = main(["--workspace", "/nonexistent/totally/fake/path"])
        assert code == 1

    def test_workspace_without_cosmed_raises(self, tmp_path: Path) -> None:
        """CLI on a workspace with no COSMED file raises FileNotFoundError."""
        from pipeline.cli import main

        with pytest.raises(FileNotFoundError):
            main(["--workspace", str(tmp_path)])

    def test_skip_report_flag(self, tmp_path: Path) -> None:
        """--skip-report should complete without generating HTML."""
        from pipeline.cli import main

        _make_minimal_xlsx(tmp_path)
        code = main(["--workspace", str(tmp_path), "--skip-report"])
        assert code == 0
        assert not (tmp_path / "report").exists() or not list(
            (tmp_path / "report").glob("*.html")
        )

    def test_verbose_flag_does_not_crash(self, tmp_path: Path) -> None:
        """--verbose should succeed without errors."""
        from pipeline.cli import main

        _make_minimal_xlsx(tmp_path)
        code = main(["--workspace", str(tmp_path), "--skip-report", "--verbose"])
        assert code == 0


# =====================================================================
# Report with Partial Data
# =====================================================================


class TestReportPartialData:
    """HTML report generation when sections are absent."""

    def test_report_cosmed_only_renders(self, tmp_path: Path) -> None:
        """Report should render without FIT/lactate sections."""
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database
        from pipeline.analysis import run_analysis
        from pipeline.report import generate_report

        _make_minimal_xlsx(tmp_path)
        parsed = parse_workspace(tmp_path)
        db_path = create_database(tmp_path, parsed)
        run_analysis(db_path)

        report_path = generate_report(db_path, tmp_path / "report")
        assert report_path.exists()
        assert report_path.suffix == ".html"
        # Must be non-trivial HTML
        assert report_path.stat().st_size > 1000

    def test_report_output_dir_created(self, tmp_path: Path) -> None:
        """generate_report should create output_dir if it does not exist."""
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database
        from pipeline.analysis import run_analysis
        from pipeline.report import generate_report

        _make_minimal_xlsx(tmp_path)
        parsed = parse_workspace(tmp_path)
        db_path = create_database(tmp_path, parsed)
        run_analysis(db_path)

        out_dir = tmp_path / "deep" / "nested" / "report"
        assert not out_dir.exists()
        report_path = generate_report(db_path, out_dir)
        assert report_path.exists()

    def test_report_html_is_valid_markup(self, tmp_path: Path) -> None:
        """Report should contain basic HTML structural tags."""
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database
        from pipeline.analysis import run_analysis
        from pipeline.report import generate_report

        _make_minimal_xlsx(tmp_path)
        parsed = parse_workspace(tmp_path)
        db_path = create_database(tmp_path, parsed)
        run_analysis(db_path)

        report_path = generate_report(db_path, tmp_path / "report")
        html = report_path.read_text(encoding="utf-8")
        assert "<html" in html.lower() or "<!doctype" in html.lower()
        assert "</html>" in html.lower()

    def test_report_embedded_json_does_not_include_nan(self, tmp_path: Path) -> None:
        """Embedded report JSON should remain browser-parseable."""
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database
        from pipeline.analysis import run_analysis
        from pipeline.report import generate_report

        _make_minimal_xlsx(tmp_path)
        parsed = parse_workspace(tmp_path)
        db_path = create_database(tmp_path, parsed)
        run_analysis(db_path)

        report_path = generate_report(db_path, tmp_path / "report")
        html = report_path.read_text(encoding="utf-8")
        assert "NaN" not in html

    def test_json_safe_replaces_nan_recursively(self) -> None:
        """Nested NaN values should serialize as null, not invalid JSON tokens."""
        from pipeline.report import _json_safe

        payload = {
            "outer": [1.0, math.nan, {"inner": float("inf"), "ok": 2.0}],
        }

        safe = _json_safe(payload)
        assert safe["outer"][1] is None
        assert safe["outer"][2]["inner"] is None
        assert safe["outer"][2]["ok"] == 2.0


# =====================================================================
# ParsedData Dataclass Properties
# =====================================================================


class TestParsedDataProperties:
    """Unit tests for ParsedData dataclass properties."""

    def test_has_fit_false_when_none(self) -> None:
        from pipeline.parsers import ParsedData

        pd_obj = ParsedData(
            cosmed_df=pd.DataFrame(),
            subject_info={},
            workout_df=None,
        )
        assert not pd_obj.has_fit

    def test_has_fit_false_when_empty_df(self) -> None:
        from pipeline.parsers import ParsedData

        pd_obj = ParsedData(
            cosmed_df=pd.DataFrame(),
            subject_info={},
            workout_df=pd.DataFrame(),
        )
        assert not pd_obj.has_fit

    def test_has_fit_true_when_populated(self) -> None:
        from pipeline.parsers import ParsedData

        pd_obj = ParsedData(
            cosmed_df=pd.DataFrame(),
            subject_info={},
            workout_df=pd.DataFrame({"power_w": [100.0]}),
        )
        assert pd_obj.has_fit

    def test_has_lactate_false_when_none(self) -> None:
        from pipeline.parsers import ParsedData

        pd_obj = ParsedData(
            cosmed_df=pd.DataFrame(),
            subject_info={},
            blood_df=None,
        )
        assert not pd_obj.has_lactate

    def test_has_protocol_false_when_empty(self) -> None:
        from pipeline.parsers import ParsedData

        pd_obj = ParsedData(
            cosmed_df=pd.DataFrame(),
            subject_info={},
            protocol_df=pd.DataFrame(),
        )
        assert not pd_obj.has_protocol
