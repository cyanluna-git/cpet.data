"""Admin API routes - 관리자 전용 엔드포인트"""

from __future__ import annotations

import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select

from app.api.deps import AdminUser, DBSession
from app.models import CPETTest, Subject, User
from app.schemas.admin import (
    AdminStatsResponse,
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserUpdate,
)
from app.schemas.auth import UserCreate, UserResponse, UserUpdate
from app.services import AuthService

router = APIRouter(prefix="/admin", tags=["Admin"])


def _normalize_role(role: Optional[str]) -> Optional[str]:
    if role is None:
        return None
    return "user" if role == "subject" else role


@router.get("/stats", response_model=AdminStatsResponse)
async def get_admin_stats(
    admin_user: AdminUser,
    db: DBSession,
) -> AdminStatsResponse:
    """[슈퍼어드민] 서비스 운영 통계"""

    users_total = await db.scalar(select(func.count()).select_from(User))
    users_active = await db.scalar(
        select(func.count()).select_from(User).where(User.is_active.is_(True))
    )
    users_inactive = await db.scalar(
        select(func.count()).select_from(User).where(User.is_active.is_(False))
    )

    role_counts_rows = (await db.execute(
        select(User.role, func.count()).group_by(User.role)
    )).all()
    users_by_role = {role: int(count) for role, count in role_counts_rows}

    subjects_total = await db.scalar(select(func.count()).select_from(Subject))
    tests_total = await db.scalar(select(func.count()).select_from(CPETTest))

    return AdminStatsResponse(
        users_total=int(users_total or 0),
        users_active=int(users_active or 0),
        users_inactive=int(users_inactive or 0),
        users_by_role=users_by_role,
        subjects_total=int(subjects_total or 0),
        tests_total=int(tests_total or 0),
    )


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    admin_user: AdminUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by email"),
    role: Optional[str] = Query(None, description="admin|researcher|user|subject"),
    is_active: Optional[bool] = Query(None),
    sort_by: str = Query("created_at", pattern="^(created_at|last_login|email|role)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> AdminUserListResponse:
    """[슈퍼어드민] 사용자 목록 조회"""

    normalized_role = _normalize_role(role)

    base = select(User)
    count_q = select(func.count()).select_from(User)

    if search:
        like = f"%{search}%"
        base = base.where(User.email.ilike(like))
        count_q = count_q.where(User.email.ilike(like))

    if normalized_role:
        base = base.where(User.role == normalized_role)
        count_q = count_q.where(User.role == normalized_role)

    if is_active is not None:
        base = base.where(User.is_active.is_(is_active))
        count_q = count_q.where(User.is_active.is_(is_active))

    sort_col = {
        "created_at": User.created_at,
        "last_login": User.last_login,
        "email": User.email,
        "role": User.role,
    }[sort_by]

    if sort_order == "asc":
        base = base.order_by(sort_col.asc())
    else:
        base = base.order_by(sort_col.desc())

    total = await db.scalar(count_q)
    total = int(total or 0)
    total_pages = max(1, math.ceil(total / page_size))

    offset = (page - 1) * page_size
    rows = (await db.execute(base.offset(offset).limit(page_size))).scalars().all()

    return AdminUserListResponse(
        items=[UserResponse.model_validate(u) for u in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: AdminUserCreate,
    admin_user: AdminUser,
    db: DBSession,
) -> UserResponse:
    """[슈퍼어드민] 사용자 생성"""

    auth_service = AuthService(db)

    existing_user = await auth_service.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    role = _normalize_role(user_data.role) or "user"
    created = await auth_service.create_user(
        UserCreate(
            email=user_data.email,
            password=user_data.password,
            role=role,
            subject_id=UUID(user_data.subject_id) if user_data.subject_id else None,
        )
    )

    return UserResponse.model_validate(created)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_data: AdminUserUpdate,
    admin_user: AdminUser,
    db: DBSession,
) -> UserResponse:
    """[슈퍼어드민] 사용자 수정 (role/active 포함)"""

    auth_service = AuthService(db)

    existing = await auth_service.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user_data.email and user_data.email != existing.email:
        dupe = await auth_service.get_user_by_email(user_data.email)
        if dupe:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    update_dict = user_data.model_dump(exclude_unset=True)

    # Map subject -> user if provided
    if "role" in update_dict:
        update_dict["role"] = _normalize_role(update_dict["role"])  # type: ignore[assignment]

    # Convert subject_id string -> UUID
    if "subject_id" in update_dict and update_dict["subject_id"] is not None:
        update_dict["subject_id"] = UUID(update_dict["subject_id"])  # type: ignore[assignment]

    updated = await auth_service.update_user(user_id, UserUpdate(**update_dict))

    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return UserResponse.model_validate(updated)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_user(
    user_id: UUID,
    admin_user: AdminUser,
    db: DBSession,
) -> Response:
    """[슈퍼어드민] 사용자 삭제"""

    if user_id == admin_user.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")

    auth_service = AuthService(db)
    deleted = await auth_service.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
