"""Admin API routes - 관리자 전용 엔드포인트"""

from __future__ import annotations

import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select

from app.api.deps import AdminUser, DBSession
from app.models import CPETTest, Subject, User, BreathData
from app.schemas.admin import (
    AdminStatsResponse,
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserUpdate,
    AdminTestListResponse,
    AdminTestRow,
    TestValidationInfo,
    AdminTestDemographicUpdate,
)
from app.schemas.auth import UserCreate, UserResponse, UserUpdate
from app.services import AuthService
from app.services.data_validator import DataValidator
import pandas as pd

router = APIRouter(prefix="/admin", tags=["Admin"])


def sanitize_float(value: float | None) -> float | None:
    """Convert NaN/Inf to None for JSON serialization"""
    if value is None:
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


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


@router.get("/tests", response_model=AdminTestListResponse)
async def list_all_tests(
    admin_user: AdminUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    protocol_type: Optional[str] = Query(None, description="RAMP|INTERVAL|STEADY_STATE"),
    is_valid: Optional[bool] = Query(None, description="Filter by validation status"),
    sort_by: str = Query("test_date", pattern="^(test_date|quality_score|subject_name)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> AdminTestListResponse:
    """[슈퍼어드민] 전체 테스트 목록 조회 (검증 정보 포함)"""
    
    from sqlalchemy.orm import selectinload
    from datetime import datetime as dt
    
    # Base query
    query = select(CPETTest).options(
        selectinload(CPETTest.subject),
        selectinload(CPETTest.breath_data)
    )
    
    # Count query
    count_query = select(func.count()).select_from(CPETTest)
    
    # Get all tests (we need breath_data for validation)
    result = await db.execute(query)
    all_tests = list(result.scalars().all())
    
    # Validate each test
    validator = DataValidator()
    test_rows = []
    
    for test in all_tests:
        # Convert breath_data to DataFrame
        if test.breath_data and len(test.breath_data) > 0:
            breath_list = []
            for bd in test.breath_data:
                breath_list.append({
                    't_sec': bd.t_sec,
                    'bike_power': bd.bike_power,
                    'hr': bd.hr,
                    'vo2': bd.vo2,
                    'vco2': bd.vco2,
                })
            df = pd.DataFrame(breath_list)
            validation_result = validator.validate(df)
            
            validation_info = TestValidationInfo(
                is_valid=validation_result.is_valid,
                protocol_type=validation_result.protocol_type.value,
                quality_score=sanitize_float(validation_result.quality_score) or 0.0,
                duration_min=sanitize_float(validation_result.metadata.get('duration_min', 0)) or 0.0,
                max_power=sanitize_float(validation_result.metadata.get('max_power', 0)) or 0.0,
                hr_dropout_rate=sanitize_float(validation_result.metadata.get('hr_dropout_rate', 0)) or 0.0,
                gas_dropout_rate=sanitize_float(max(
                    validation_result.metadata.get('vo2_dropout_rate', 0) or 0,
                    validation_result.metadata.get('vco2_dropout_rate', 0) or 0
                )) or 0.0,
                power_time_correlation=sanitize_float(validation_result.power_time_correlation),
                issues=validation_result.reason
            )
        else:
            # No breath data
            validation_info = TestValidationInfo(
                is_valid=False,
                protocol_type="UNKNOWN",
                quality_score=0.0,
                duration_min=0.0,
                max_power=0.0,
                hr_dropout_rate=0.0,
                gas_dropout_rate=0.0,
                issues=["No breath data available"]
            )
        
        # Calculate age
        subject_age = None
        if test.subject and test.subject.birth_year and test.test_date:
            test_year = test.test_date.year
            subject_age = test_year - test.subject.birth_year
        
        test_row = AdminTestRow(
            test_id=test.test_id,
            test_date=test.test_date,
            test_time=test.test_time,
            subject_id=test.subject_id,
            subject_name=test.subject.encrypted_name if test.subject and test.subject.encrypted_name else (test.subject.research_id if test.subject else "Unknown"),
            subject_age=subject_age,
            height_cm=sanitize_float(test.height_cm) if test.height_cm is not None else None,
            weight_kg=sanitize_float(test.weight_kg) if test.weight_kg is not None else None,
            protocol_type=test.protocol_type,
            source_filename=test.source_filename,
            parsing_status=test.parsing_status,
            validation=validation_info,
            vo2_max=sanitize_float(test.vo2_max) if test.vo2_max is not None else None,
            fat_max_watt=sanitize_float(test.fat_max_watt) if test.fat_max_watt is not None else None
        )
        
        test_rows.append(test_row)
    
    # Apply filters
    filtered_rows = test_rows
    
    if protocol_type:
        filtered_rows = [r for r in filtered_rows if r.validation.protocol_type == protocol_type]
    
    if is_valid is not None:
        filtered_rows = [r for r in filtered_rows if r.validation.is_valid == is_valid]
    
    # Sort
    reverse = (sort_order == "desc")
    if sort_by == "test_date":
        filtered_rows.sort(key=lambda x: x.test_date, reverse=reverse)
    elif sort_by == "quality_score":
        filtered_rows.sort(key=lambda x: x.validation.quality_score, reverse=reverse)
    elif sort_by == "subject_name":
        filtered_rows.sort(key=lambda x: x.subject_name, reverse=reverse)
    
    # Pagination
    total = len(filtered_rows)
    total_pages = math.ceil(total / page_size)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_rows = filtered_rows[start:end]
    
    return AdminTestListResponse(
        items=paginated_rows,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.patch("/tests/{test_id}/demographics")
async def update_test_demographics(
    test_id: UUID,
    update_data: AdminTestDemographicUpdate,
    admin_user: AdminUser,
    db: DBSession,
) -> dict:
    """Update test demographic information (age, height, weight)"""

    # Find test
    result = await db.execute(
        select(CPETTest).where(CPETTest.test_id == test_id)
    )
    test = result.scalar_one_or_none()

    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test {test_id} not found"
        )

    # Update fields
    updated_fields = []
    if update_data.age is not None:
        test.age = update_data.age
        updated_fields.append("age")
    if update_data.height_cm is not None:
        test.height_cm = update_data.height_cm
        updated_fields.append("height_cm")
    if update_data.weight_kg is not None:
        test.weight_kg = update_data.weight_kg
        updated_fields.append("weight_kg")

    if updated_fields:
        await db.commit()
        await db.refresh(test)

    return {
        "test_id": str(test_id),
        "updated_fields": updated_fields,
        "age": test.age,
        "height_cm": test.height_cm,
        "weight_kg": test.weight_kg,
    }

