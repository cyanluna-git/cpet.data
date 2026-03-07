"""INSCYD report schemas."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class InscydTrainingZone(BaseModel):
    zone_number: int
    name: str
    code: Optional[str] = None
    lower_watt: Optional[float] = None
    upper_watt: Optional[float] = None
    target_watt: Optional[float] = None
    energy_kcal_h: Optional[float] = None
    fat_percent: Optional[float] = None
    carbohydrate_percent: Optional[float] = None
    fat_g_h: Optional[float] = None
    carbohydrate_g_h: Optional[float] = None


class InscydTestDataRow(BaseModel):
    type: str
    average_power_watt: Optional[float] = None
    duration_sec: Optional[int] = None
    additional_value: Optional[str] = None


class InscydReportResponse(BaseModel):
    report_id: UUID
    subject_id: UUID
    external_test_id: Optional[str] = None
    report_date: Optional[date] = None
    sport: Optional[str] = None
    test_type: Optional[str] = None
    athlete_name: Optional[str] = None
    coach_name: Optional[str] = None
    body_mass_kg: Optional[float] = None
    body_height_cm: Optional[float] = None
    body_mass_index: Optional[float] = None
    projected_bsa_m2: Optional[float] = None
    body_fat_percent: Optional[float] = None
    body_fat_kg: Optional[float] = None
    fat_free_percent: Optional[float] = None
    fat_free_kg: Optional[float] = None
    vo2max_abs_ml_min: Optional[float] = None
    vo2max_rel_ml_kg_min: Optional[float] = None
    vlamax_mmol_l_s: Optional[float] = None
    mfo_abs_kcal_h: Optional[float] = None
    mfo_rel_kcal_h_kg: Optional[float] = None
    fatmax_watt: Optional[float] = None
    carbmax_abs_watt: Optional[float] = None
    carbmax_rel_w_kg: Optional[float] = None
    at_abs_watt: Optional[float] = None
    at_rel_w_kg: Optional[float] = None
    at_pct_vo2max: Optional[float] = None
    glycogen_abs_g: Optional[float] = None
    glycogen_rel_g_kg: Optional[float] = None
    hr_max_bpm: Optional[int] = None
    pwc150_watt: Optional[float] = None
    training_zones: Optional[List[InscydTrainingZone]] = None
    test_data_rows: Optional[List[InscydTestDataRow]] = None
    weighted_regression: Optional[Dict[str, Any]] = None
    raw_sections: Optional[Dict[str, Any]] = None
    source_filename: Optional[str] = None
    file_upload_timestamp: Optional[datetime] = None
    parsing_status: Optional[str] = None
    parsing_warnings: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InscydUploadAutoResponse(BaseModel):
    report_id: UUID
    subject_id: UUID
    subject_created: bool
    subject_name: str
    source_filename: str
    parsing_status: str
    parsing_warnings: Optional[List[str]] = None
    created_at: datetime
