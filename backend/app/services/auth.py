"""Authentication service - 인증 비즈니스 로직"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password, create_access_token
from app.models import User
from app.schemas.auth import UserCreate, UserUpdate, TokenData


class AuthService:
    """인증 서비스 클래스"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """이메일로 사용자 조회"""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """ID로 사용자 조회"""
        result = await self.db.execute(
            select(User).where(User.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def authenticate_user(
        self, email: str, password: str
    ) -> Optional[User]:
        """사용자 인증 (이메일/비밀번호 확인)"""
        user = await self.get_user_by_email(email)
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        if not user.is_active:
            return None
        return user

    async def create_user(self, user_data: UserCreate) -> User:
        """새 사용자 생성"""
        hashed_password = get_password_hash(user_data.password)
        user = User(
            email=user_data.email,
            password_hash=hashed_password,
            role=user_data.role,
            subject_id=user_data.subject_id,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_user(
        self, user_id: UUID, user_data: UserUpdate
    ) -> Optional[User]:
        """사용자 정보 업데이트"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return None

        update_data = user_data.model_dump(exclude_unset=True)

        if "password" in update_data:
            update_data["password_hash"] = get_password_hash(
                update_data.pop("password")
            )

        for field, value in update_data.items():
            setattr(user, field, value)

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_last_login(self, user: User) -> None:
        """마지막 로그인 시간 업데이트"""
        user.last_login = datetime.utcnow()
        await self.db.commit()

    def create_user_token(self, user: User) -> str:
        """사용자 액세스 토큰 생성"""
        token_data = {
            "sub": str(user.user_id),
            "email": user.email,
            "role": user.role,
        }
        return create_access_token(data=token_data)

    async def delete_user(self, user_id: UUID) -> bool:
        """사용자 삭제"""
        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        await self.db.delete(user)
        await self.db.commit()
        return True
