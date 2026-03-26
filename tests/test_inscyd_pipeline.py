"""Regression coverage for the standalone INSCYD interpretation lane."""

from pathlib import Path

from pipeline.inscyd_coaching import build_coaching_payload
from pipeline.inscyd_report import build_report_context, generate_inscyd_report
from pipeline.inscyd_workspace import parse_inscyd_workspace


FIXTURES_DIR = Path(__file__).parent / "fixtures"
INSCYD_WS = FIXTURES_DIR / "inscyd_ppd"


def test_parse_inscyd_workspace_extracts_pdf_metrics_and_fit_evidence() -> None:
    parsed = parse_inscyd_workspace(INSCYD_WS)

    assert parsed.report.athlete_name == "Geunyun Park"
    assert parsed.report.test_type == "PPD"
    assert parsed.report.vo2max_rel_ml_kg_min == 51.7
    assert parsed.report.vlamax_mmol_l_s == 0.53
    assert parsed.report.fatmax_watt == 150.0
    assert parsed.report.at_abs_watt == 230.0
    assert len(parsed.fit_sessions) == 2
    assert parsed.zwo_summary["source"] == "Power_Performance_Decoder___V3.zwo"
    assert parsed.zwo_summary["fit_alignment"]
    assert any(row["fit_session_count"] == 2 for row in parsed.zwo_summary["fit_alignment"])


def test_build_report_context_compiles_valid_widget_plan() -> None:
    context = build_report_context(INSCYD_WS)
    plan = context["report_plan"]
    report_data = context["report_data"]

    assert report_data["meta"]["analysis_method"] == "INSCYD 해설 리포트"
    assert report_data["meta"]["report_type"] == "inscyd"
    assert report_data["subject"]["name"] == "Geunyun Park"
    assert report_data["coaching"]["archetype"]["title"]
    assert report_data["coaching"]["training_directions"]
    assert report_data["coaching"]["microcycle"]
    assert "key_metrics" in plan
    assert "coaching_overview" in plan
    assert "training_directions" in plan
    assert "microcycle" in plan
    assert "training_zones" in plan
    assert "test_rows" in plan
    assert "fit_protocol" in plan
    assert "fit_alignment" in plan
    assert report_data["artifacts"] == {}


def test_build_coaching_payload_omits_microcycle_when_fit_evidence_is_missing() -> None:
    parsed = parse_inscyd_workspace(INSCYD_WS)
    parsed.fit_sessions = []
    parsed.zwo_summary["fit_alignment"] = []

    payload = build_coaching_payload(parsed)

    assert payload["confidence"] == "low"
    assert payload["microcycle"] == []


def test_generate_inscyd_report_writes_html_with_embedded_report_data(tmp_path: Path) -> None:
    report_path = generate_inscyd_report(INSCYD_WS, tmp_path / "report")
    html = report_path.read_text(encoding="utf-8")

    assert "INSCYD Interpretation Report" in html
    assert "INSCYD가 제시한 핵심 지표" in html
    assert "Geunyun Park" in html
    assert "VLamax" in html
    assert "현재 상태" in html
    assert "향후 훈련 방향" in html
    assert "예시 주간 구성" in html
    assert "Zone Coach Note" in html
    assert "Effort Coach Note" in html
    assert "Reported vs FIT best effort" in html
    assert "2 uploaded FIT files" in html
    assert "원본 PDF 열기" in html
    assert "Original Pages" in html
    assert "FIT와 INSCYD effort의 대조" not in html
    assert 'id="report-data"' in html
    assert "inscyd" in html
    assert (tmp_path / "report" / "original-inscyd-report.pdf").is_file()
    assert (tmp_path / "report" / "original-page-1.png").is_file()
