"""Authentication API routes - 인증 API 엔드포인트"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import DBSession, CurrentUser, AdminUser
from app.schemas.auth import Token, UserCreate, UserResponse, UserUpdate
from app.services import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DBSession,
) -> Token:
    """
    사용자 로그인 및 JWT 토큰 발급

    - **username**: 이메일 주소
    - **password**: 비밀번호
    """
    auth_service = AuthService(db)
    user = await auth_service.authenticate_user(
        email=form_data.username,
        password=form_data.password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await auth_service.update_last_login(user)
    access_token = auth_service.create_user_token(user)

    return Token(access_token=access_token)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: DBSession,
) -> UserResponse:
    """
    새 사용자 등록

    - 이메일 중복 확인
    - 비밀번호 해싱 후 저장
    """
    auth_service = AuthService(db)

    existing_user = await auth_service.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = await auth_service.create_user(user_data)
    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: CurrentUser,
) -> UserResponse:
    """현재 로그인한 사용자 정보 조회"""
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_data: UserUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> UserResponse:
    """현재 로그인한 사용자 정보 업데이트"""
    auth_service = AuthService(db)

    # 이메일 변경 시 중복 확인
    if user_data.email and user_data.email != current_user.email:
        existing_user = await auth_service.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # 일반 사용자는 role 변경 불가
    if user_data.role and current_user.role != "admin":
        user_data.role = None

    updated_user = await auth_service.update_user(
        current_user.user_id, user_data
    )
    return UserResponse.model_validate(updated_user)


# Admin endpoints
@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    user_data: UserCreate,
    admin_user: AdminUser,
    db: DBSession,
) -> UserResponse:
    """[관리자] 새 사용자 생성"""
    auth_service = AuthService(db)

    existing_user = await auth_service.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = await auth_service.create_user(user_data)
    return UserResponse.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_user(
    user_id: str,
    admin_user: AdminUser,
    db: DBSession,
) -> None:
    """[관리자] 사용자 삭제"""
    try:
        uuid_user_id = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format",
        )

    if uuid_user_id == admin_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )

    auth_service = AuthService(db)
    deleted = await auth_service.delete_user(uuid_user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
