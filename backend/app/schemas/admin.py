"""Admin schemas - 관리자 전용 Pydantic 스키마"""

from __future__ import annotations

from datetime import datetime, time
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.auth import UserResponse


class AdminStatsResponse(BaseModel):
    """관리자 대시보드용 통계"""

    users_total: int
    users_active: int
    users_inactive: int
    users_by_role: dict[str, int]

    subjects_total: int
    tests_total: int


class AdminUserListResponse(BaseModel):
    """사용자 목록 응답 (페이지네이션)"""

    items: List[UserResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminUserCreate(BaseModel):
    """[관리자] 사용자 생성 요청"""

    email: EmailStr
    password: str = Field(..., min_length=6)
    # frontend 용어(subject)도 허용하되 내부적으로 user로 매핑한다.
    role: str = Field(default="user", pattern="^(admin|researcher|user|subject)$")
    subject_id: Optional[str] = None


class AdminUserUpdate(BaseModel):
    """[관리자] 사용자 업데이트 요청"""

    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)
    role: Optional[str] = Field(None, pattern="^(admin|researcher|user|subject)$")
    is_active: Optional[bool] = None


class TestValidationInfo(BaseModel):
    """테스트 검증 정보"""
    
    is_valid: bool
    protocol_type: str  # RAMP, INTERVAL, STEADY_STATE, UNKNOWN
    quality_score: float
    duration_min: float
    max_power: float
    hr_dropout_rate: float
    gas_dropout_rate: float
    power_time_correlation: Optional[float] = None
    issues: List[str] = []


class AdminTestRow(BaseModel):
    """관리 테이블용 테스트 행"""

    test_id: UUID
    test_date: datetime
    test_time: Optional[time] = None

    # 피험자 정보
    subject_id: UUID
    subject_name: str
    subject_age: Optional[int] = None

    # 테스트 시점의 신체 정보
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None

    # 테스트 정보
    protocol_type: Optional[str] = None
    source_filename: Optional[str] = None
    parsing_status: Optional[str] = None

    # 검증 정보
    validation: TestValidationInfo

    # 분석 결과 (있으면)
    vo2_max: Optional[float] = None
    fat_max_watt: Optional[float] = None
    
    model_config = {"from_attributes": True}


class AdminTestListResponse(BaseModel):
    """관리자 테스트 목록 응답"""

    items: List[AdminTestRow]
    total: int
    page: int
    page_size: int
    total_pages: int
    subject_id: Optional[str] = None


class AdminTestDemographicUpdate(BaseModel):
    """테스트 인구통계 정보 업데이트"""

    age: Optional[float] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
