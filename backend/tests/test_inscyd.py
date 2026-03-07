"""Tests for INSCYD parsing and persistence."""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import InscydReport
from app.services.inscyd import InscydService
from app.services.inscyd_parser import InscydParser
from app.services.subject import SubjectService


PDF_PATH = (
    Path(__file__).resolve().parents[2]
    / "inscyd"
    / "INSCYD_KY Park_2026.pdf.pdf"
)


@pytest.mark.asyncio
async def test_inscyd_parser_extracts_metrics():
    parser = InscydParser()
    parsed = parser.parse_file(str(PDF_PATH))

    assert parsed.external_test_id == "176774433413"
    assert parsed.athlete_name == "Geunyun Park"
    assert parsed.report_date.isoformat() == "2026-01-06"
    assert parsed.vo2max_rel_ml_kg_min == pytest.approx(51.70)
    assert parsed.vlamax_mmol_l_s == pytest.approx(0.53)
    assert parsed.fatmax_watt == pytest.approx(150.0)
    assert parsed.at_abs_watt == pytest.approx(230.0)
    assert parsed.carbmax_abs_watt == pytest.approx(178.0)
    assert len(parsed.training_zones) == 13
    assert parsed.training_zones[3]["name"] == "FATmax"
    assert parsed.weighted_regression["anaerobic_threshold"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_inscyd_service_upload_and_parse(async_db, test_subject):
    service = InscydService(async_db)
    file_bytes = PDF_PATH.read_bytes()

    report = await service.upload_and_parse(
        file_content=file_bytes,
        filename=PDF_PATH.name,
        subject_id=test_subject.id,
    )

    assert report.subject_id == test_subject.id
    assert report.source_filename == PDF_PATH.name
    assert report.vo2max_rel_ml_kg_min == pytest.approx(51.70)
    assert report.training_zones is not None
    assert len(report.training_zones) == 13
    assert report.parsing_status in {"success", "warning"}


@pytest.mark.asyncio
async def test_inscyd_service_replaces_existing_report_for_same_subject_and_filename(
    async_db, test_subject
):
    service = InscydService(async_db)
    file_bytes = PDF_PATH.read_bytes()

    first = await service.upload_and_parse(
        file_content=file_bytes,
        filename=PDF_PATH.name,
        subject_id=test_subject.id,
    )
    second = await service.upload_and_parse(
        file_content=file_bytes,
        filename=PDF_PATH.name,
        subject_id=test_subject.id,
    )

    result = await async_db.execute(
        select(InscydReport).where(InscydReport.subject_id == test_subject.id)
    )
    reports = list(result.scalars().all())

    assert len(reports) == 1
    assert first.report_id != second.report_id
    assert reports[0].report_id == second.report_id


@pytest.mark.asyncio
async def test_subject_service_returns_inscyd_reports_and_updates_subject_body_metrics(
    async_db, test_subject
):
    report = await InscydService(async_db).upload_and_parse(
        file_content=PDF_PATH.read_bytes(),
        filename=PDF_PATH.name,
        subject_id=test_subject.id,
    )

    subject = await SubjectService(async_db).get_with_tests(test_subject.id)

    assert subject is not None
    assert len(subject.inscyd_reports) == 1
    assert subject.inscyd_reports[0].report_id == report.report_id
    assert subject.weight_kg == pytest.approx(report.body_mass_kg)
    assert subject.height_cm == pytest.approx(report.body_height_cm)
    assert subject.body_fat_percent == pytest.approx(report.body_fat_percent)
    assert subject.bmi == pytest.approx(report.body_mass_index)
