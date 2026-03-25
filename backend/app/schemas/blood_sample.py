"""BloodSample Schemas - 혈액 샘플 데이터 스키마"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class BloodSampleCreate(BaseModel):
    """혈액 샘플 생성 요청 스키마"""

    block: Optional[str] = Field(None, max_length=20, description="Test block (rest, block_1, block_2, block_3)")
    step: Optional[str] = Field(None, max_length=20, description="Step identifier (0, 1-1, 2-1, etc.)")
    load_w: Optional[float] = Field(None, ge=0, description="Power (Watts)")
    ftp_pct: Optional[str] = Field(None, max_length=10, description="FTP percentage")
    duration_min: Optional[float] = Field(None, ge=0, description="Step duration (minutes)")
    sample_time_kst: Optional[str] = Field(None, max_length=20, description="Sample time (KST)")
    elapsed_sec: Optional[float] = Field(None, ge=0, description="Elapsed time from test start (sec)")
    hr_bpm: Optional[float] = Field(None, ge=0, le=300, description="Heart rate (bpm)")
    lactate_mmol: Optional[float] = Field(None, ge=0, le=50, description="Blood lactate (mmol/L)")
    glucose_mmol: Optional[float] = Field(None, ge=0, le=50, description="Blood glucose (mmol/L)")
    notes: Optional[str] = Field(None, description="Notes")


class BloodSampleResponse(BaseModel):
    """혈액 샘플 응답 스키마"""

    id: UUID
    cpet_test_id: UUID
    block: Optional[str] = None
    step: Optional[str] = None
    load_w: Optional[float] = None
    ftp_pct: Optional[str] = None
    duration_min: Optional[float] = None
    sample_time_kst: Optional[str] = None
    elapsed_sec: Optional[float] = None
    hr_bpm: Optional[float] = None
    lactate_mmol: Optional[float] = None
    glucose_mmol: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BloodSampleBulkCreate(BaseModel):
    """혈액 샘플 대량 생성 요청 스키마"""

    samples: List[BloodSampleCreate] = Field(..., min_length=1, description="List of blood samples")


class BloodSampleListResponse(BaseModel):
    """혈액 샘플 목록 응답 스키마"""

    cpet_test_id: UUID
    samples: List[BloodSampleResponse]
    total: int

    # Derived lactate metrics
    resting_lactate: Optional[float] = Field(None, description="Resting blood lactate (mmol/L)")
    peak_lactate: Optional[float] = Field(None, description="Peak blood lactate (mmol/L)")
    delta_lactate: Optional[float] = Field(None, description="Peak - Resting lactate (mmol/L)")
