"""Authentication schemas - 인증 관련 Pydantic 스키마"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class Token(BaseModel):
    """JWT 토큰 응답 스키마"""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """JWT 토큰 페이로드 스키마"""

    user_id: Optional[UUID] = None
    email: Optional[str] = None


class UserLogin(BaseModel):
    """로그인 요청 스키마"""

    email: EmailStr
    password: str = Field(..., min_length=6)


class UserCreate(BaseModel):
    """사용자 생성 요청 스키마"""

    email: EmailStr
    password: str = Field(..., min_length=6)
    role: str = Field(default="user", pattern="^(admin|researcher|user)$")
    subject_id: Optional[UUID] = None


class UserResponse(BaseModel):
    """사용자 응답 스키마"""

    user_id: UUID
    email: str
    role: str
    subject_id: Optional[UUID] = None
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """사용자 업데이트 요청 스키마"""

    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)
    role: Optional[str] = Field(None, pattern="^(admin|researcher|user)$")
    is_active: Optional[bool] = None
    subject_id: Optional[UUID] = None
