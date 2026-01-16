"""Admin schemas - 관리자 전용 Pydantic 스키마"""

from __future__ import annotations

from typing import List, Optional

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
    subject_id: Optional[str] = None
