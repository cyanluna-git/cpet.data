"""Regression coverage for protocol-aware suitability and conservative report copy."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from pipeline.analysis import run_analysis
from pipeline.parsers import parse_workspace
from pipeline.report import generate_report
from pipeline.schema import create_database

FIXTURES = Path(__file__).parent / "fixtures"
COSMED_WS = FIXTURES / "cosmed_only"
PARK_WS = FIXTURES / "park_geunyun"


def _run_pipeline(workspace: Path) -> dict[str, dict[str, Any]]:
    parsed = parse_workspace(workspace)
    db_path = create_database(workspace, parsed)
    run_analysis(db_path)

    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT category, key, value FROM analysis_results ORDER BY category, key"
    ).fetchall()
    conn.close()

    results: dict[str, dict[str, Any]] = {}
    for category, key, value in rows:
        results.setdefault(category, {})
        try:
            results[category][key] = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            results[category][key] = value
    return results


def test_cosmed_pipeline_records_protocol_suitability_contract() -> None:
    results = _run_pipeline(COSMED_WS)

    protocol = results["protocol"]
    suitability = results["suitability"]

    assert protocol["protocol_family"] in {"cpet", "two_block_cpet"}
    assert protocol["window_metadata"]["vo2max_window"] in {"active_window", "block_2"}

    assert suitability["lt1"]["status"] in {"indirect", "unsupported"}
    assert suitability["lt2"]["status"] == "indirect"
    assert suitability["clearance"]["status"] == "unsupported"
    assert suitability["fatmax"]["status"] in {"supported", "low_confidence", "unsupported"}
    assert "band_power_w" in suitability["fatmax"]
    assert suitability["vo2max"]["status"] in {"supported", "low_confidence", "unsupported"}
    assert "range_rel_ml_kg_min" in suitability["vo2max"]


def test_cosmed_report_uses_conservative_metric_copy() -> None:
    parsed = parse_workspace(COSMED_WS)
    db_path = create_database(COSMED_WS, parsed)
    run_analysis(db_path)
    report_path = generate_report(db_path, COSMED_WS / "report")
    html = report_path.read_text(encoding="utf-8")

    assert "VT1 (간접)" in html
    assert "LT1 (D-max)" not in html
    assert "FatMax 근사 band" in html or "FatMax band" in html
    assert "보수적 기준" in html or "ventilatory surrogate" in html


def test_belgium_report_keeps_direct_lactate_metric_copy() -> None:
    parsed = parse_workspace(PARK_WS)
    db_path = create_database(PARK_WS, parsed)
    run_analysis(db_path)
    report_path = generate_report(db_path, PARK_WS / "report")
    html = report_path.read_text(encoding="utf-8")

    assert "LT1 (D-max)" in html
    assert "VT1 (간접)" not in html
    assert "젖산 클리어런스" in html
