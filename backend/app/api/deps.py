"""API dependencies - FastAPI 의존성"""

from typing import Annotated, List
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User
from app.services import AuthService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """현재 인증된 사용자 반환"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id_str: str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(user_id)
    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """현재 활성화된 사용자 반환"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


async def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """현재 관리자 사용자 반환"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


def require_roles(allowed_roles: List[str]):
    """역할 기반 권한 검사 의존성 팩토리"""
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(allowed_roles)}",
            )
        return current_user
    return role_checker


async def get_researcher_user(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    """연구자 이상 권한 필요"""
    if current_user.role not in ["admin", "researcher"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Researcher privileges required",
        )
    return current_user


# Type aliases for dependency injection
CurrentUser = Annotated[User, Depends(get_current_active_user)]
AdminUser = Annotated[User, Depends(get_current_admin_user)]
ResearcherUser = Annotated[User, Depends(get_researcher_user)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
