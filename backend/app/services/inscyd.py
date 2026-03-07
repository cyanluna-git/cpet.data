"""INSCYD report service."""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InscydReport, Subject
from app.services.cosmed_parser import SubjectInfo
from app.services.inscyd_parser import InscydParser
from app.services.test import TestService


class InscydService:
    """CRUD and upload service for INSCYD reports."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_subject(self, subject_id: UUID) -> List[InscydReport]:
        result = await self.db.execute(
            select(InscydReport)
            .where(InscydReport.subject_id == subject_id)
            .order_by(desc(InscydReport.report_date), desc(InscydReport.created_at))
        )
        return list(result.scalars().all())

    async def find_or_create_subject_from_athlete(
        self, athlete_name: str
    ) -> Tuple[Subject, bool]:
        athlete_name = (athlete_name or "").strip()
        parts = athlete_name.split()
        subject_info = SubjectInfo(
            research_id=athlete_name.replace(" ", "_") if athlete_name else "",
            first_name=parts[0] if parts else "",
            last_name=" ".join(parts[1:]) if len(parts) > 1 else "",
        )
        return await TestService(self.db).find_or_create_subject(subject_info)

    async def upload_and_parse(
        self,
        file_content: bytes,
        filename: str,
        subject_id: UUID,
    ) -> InscydReport:
        subject_result = await self.db.execute(
            select(Subject).where(Subject.id == subject_id)
        )
        subject = subject_result.scalar_one_or_none()
        if not subject:
            raise ValueError(f"Subject not found: {subject_id}")

        existing_report_result = await self.db.execute(
            select(InscydReport).where(
                InscydReport.subject_id == subject_id,
                InscydReport.source_filename == filename,
            )
        )
        existing_report = existing_report_result.scalar_one_or_none()
        if existing_report:
            await self.db.execute(
                delete(InscydReport).where(InscydReport.report_id == existing_report.report_id)
            )
            await self.db.flush()

        suffix = Path(filename).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            parser = InscydParser()
            parsed = parser.parse_file(tmp_path)
        finally:
            os.unlink(tmp_path)

        if parsed.body_height_cm and not subject.height_cm:
            subject.height_cm = parsed.body_height_cm
        if parsed.body_mass_kg and not subject.weight_kg:
            subject.weight_kg = parsed.body_mass_kg
        if parsed.body_fat_percent and not subject.body_fat_percent:
            subject.body_fat_percent = parsed.body_fat_percent
        if parsed.body_mass_index and not subject.bmi:
            subject.bmi = parsed.body_mass_index

        report = InscydReport(
            subject_id=subject_id,
            external_test_id=parsed.external_test_id,
            report_date=parsed.report_date,
            sport=parsed.sport,
            test_type=parsed.test_type,
            athlete_name=parsed.athlete_name,
            coach_name=parsed.coach_name,
            body_mass_kg=parsed.body_mass_kg,
            body_height_cm=parsed.body_height_cm,
            body_mass_index=parsed.body_mass_index,
            projected_bsa_m2=parsed.projected_bsa_m2,
            body_fat_percent=parsed.body_fat_percent,
            body_fat_kg=parsed.body_fat_kg,
            fat_free_percent=parsed.fat_free_percent,
            fat_free_kg=parsed.fat_free_kg,
            vo2max_abs_ml_min=parsed.vo2max_abs_ml_min,
            vo2max_rel_ml_kg_min=parsed.vo2max_rel_ml_kg_min,
            vlamax_mmol_l_s=parsed.vlamax_mmol_l_s,
            mfo_abs_kcal_h=parsed.mfo_abs_kcal_h,
            mfo_rel_kcal_h_kg=parsed.mfo_rel_kcal_h_kg,
            fatmax_watt=parsed.fatmax_watt,
            carbmax_abs_watt=parsed.carbmax_abs_watt,
            carbmax_rel_w_kg=parsed.carbmax_rel_w_kg,
            at_abs_watt=parsed.at_abs_watt,
            at_rel_w_kg=parsed.at_rel_w_kg,
            at_pct_vo2max=parsed.at_pct_vo2max,
            glycogen_abs_g=parsed.glycogen_abs_g,
            glycogen_rel_g_kg=parsed.glycogen_rel_g_kg,
            hr_max_bpm=parsed.hr_max_bpm,
            pwc150_watt=parsed.pwc150_watt,
            training_zones=parsed.training_zones or None,
            test_data_rows=parsed.test_data_rows or None,
            weighted_regression=parsed.weighted_regression or None,
            raw_sections=parsed.raw_sections or None,
            raw_text=parsed.raw_text,
            source_filename=filename,
            file_upload_timestamp=datetime.utcnow(),
            parsing_status="warning" if parsed.parsing_warnings else "success",
            parsing_warnings=parsed.parsing_warnings or None,
        )
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)
        return report

