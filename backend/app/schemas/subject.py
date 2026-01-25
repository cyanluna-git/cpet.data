"""Subject schemas - 피험자 관련 Pydantic 스키마"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field


class SubjectCreate(BaseModel):
    """피험자 생성 요청 스키마"""
    research_id: str = Field(..., min_length=1, max_length=50, description="연구 ID")
    encrypted_name: Optional[str] = Field(None, max_length=255, description="암호화된 이름")
    birth_year: Optional[int] = Field(None, ge=1900, le=2100, description="출생연도")
    gender: Optional[str] = Field(None, pattern="^(M|F|Other)$", description="성별")
    job_category: Optional[str] = Field(None, max_length=50, description="직업 카테고리")
    medical_history: Optional[Dict[str, Any]] = Field(None, description="병력")
    training_level: Optional[str] = Field(
        None,
        pattern="^(Sedentary|Recreational|Trained|Elite)$",
        description="훈련 수준"
    )
    weight_kg: Optional[float] = Field(None, ge=20, le=300, description="체중 (kg)")
    height_cm: Optional[float] = Field(None, ge=100, le=250, description="신장 (cm)")
    body_fat_percent: Optional[float] = Field(None, ge=0, le=100, description="체지방률 (%)")
    skeletal_muscle_mass: Optional[float] = Field(None, ge=0, le=100, description="골격근량 (kg)")
    bmi: Optional[float] = Field(None, ge=10, le=60, description="BMI")
    notes: Optional[str] = Field(None, description="메모")


class SubjectUpdate(BaseModel):
    """피험자 업데이트 요청 스키마"""
    research_id: Optional[str] = Field(None, min_length=1, max_length=50)
    encrypted_name: Optional[str] = Field(None, max_length=255)
    birth_year: Optional[int] = Field(None, ge=1900, le=2100)
    gender: Optional[str] = Field(None, pattern="^(M|F|Other)$")
    job_category: Optional[str] = Field(None, max_length=50)
    medical_history: Optional[Dict[str, Any]] = None
    training_level: Optional[str] = Field(None, pattern="^(Sedentary|Recreational|Trained|Elite)$")
    weight_kg: Optional[float] = Field(None, ge=20, le=300)
    height_cm: Optional[float] = Field(None, ge=100, le=250)
    body_fat_percent: Optional[float] = Field(None, ge=0, le=100)
    skeletal_muscle_mass: Optional[float] = Field(None, ge=0, le=100)
    bmi: Optional[float] = Field(None, ge=10, le=60)
    notes: Optional[str] = None


class SubjectResponse(BaseModel):
    """피험자 응답 스키마"""
    id: UUID
    research_id: str
    encrypted_name: Optional[str] = None
    birth_year: Optional[int] = None
    gender: Optional[str] = None
    job_category: Optional[str] = None
    medical_history: Optional[Dict[str, Any]] = None
    training_level: Optional[str] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    body_fat_percent: Optional[float] = None
    skeletal_muscle_mass: Optional[float] = None
    bmi: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SubjectListResponse(BaseModel):
    """피험자 목록 응답 스키마"""
    items: List[SubjectResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class SubjectWithTests(SubjectResponse):
    """테스트 포함 피험자 응답 스키마"""
    test_count: int = 0
    latest_test_date: Optional[datetime] = None
    vo2_max_best: Optional[float] = None
