"""Subject Service - 피험자 관련 비즈니스 로직"""

from datetime import datetime
from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Subject, CPETTest
from app.schemas.subject import SubjectCreate, SubjectUpdate


class SubjectService:
    """피험자 CRUD 및 조회 서비스"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, subject_id: UUID) -> Optional[Subject]:
        """ID로 피험자 조회"""
        result = await self.db.execute(
            select(Subject).where(Subject.id == subject_id)
        )
        return result.scalar_one_or_none()

    async def get_by_research_id(self, research_id: str) -> Optional[Subject]:
        """연구 ID로 피험자 조회"""
        result = await self.db.execute(
            select(Subject).where(Subject.research_id == research_id)
        )
        return result.scalar_one_or_none()

    async def get_with_tests(self, subject_id: UUID) -> Optional[Subject]:
        """피험자와 테스트 목록 함께 조회"""
        result = await self.db.execute(
            select(Subject)
            .options(selectinload(Subject.tests))
            .where(Subject.id == subject_id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        gender: Optional[str] = None,
        training_level: Optional[str] = None,
    ) -> Tuple[List[Subject], int]:
        """피험자 목록 조회 (페이징, 필터링)"""
        query = select(Subject)

        # 검색어 필터
        if search:
            query = query.where(
                Subject.research_id.ilike(f"%{search}%") |
                Subject.encrypted_name.ilike(f"%{search}%")
            )

        # 성별 필터
        if gender and gender != "All":
            query = query.where(Subject.gender == gender)

        # 훈련 수준 필터
        if training_level and training_level != "All":
            query = query.where(Subject.training_level == training_level)

        # 전체 개수 쿼리
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # 페이징 적용
        query = query.order_by(desc(Subject.created_at))
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        subjects = list(result.scalars().all())

        return subjects, total

    async def get_list_with_stats(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        gender: Optional[str] = None,
        training_level: Optional[str] = None,
    ) -> Tuple[List[dict], int]:
        """피험자 목록과 테스트 통계 조회"""
        subjects, total = await self.get_list(
            page=page,
            page_size=page_size,
            search=search,
            gender=gender,
            training_level=training_level,
        )

        results = []
        for subject in subjects:
            # 테스트 통계 조회
            stats = await self._get_subject_stats(subject.id)
            results.append({
                "subject": subject,
                **stats,
            })

        return results, total

    async def _get_subject_stats(self, subject_id: UUID) -> dict:
        """피험자별 테스트 통계"""
        # 테스트 수
        count_result = await self.db.execute(
            select(func.count())
            .select_from(CPETTest)
            .where(CPETTest.subject_id == subject_id)
        )
        test_count = count_result.scalar() or 0

        # 최신 테스트 날짜
        latest_result = await self.db.execute(
            select(CPETTest.test_date)
            .where(CPETTest.subject_id == subject_id)
            .order_by(desc(CPETTest.test_date))
            .limit(1)
        )
        latest_test_date = latest_result.scalar_one_or_none()

        # 최고 VO2MAX
        vo2_result = await self.db.execute(
            select(func.max(CPETTest.vo2_max))
            .where(CPETTest.subject_id == subject_id)
        )
        vo2_max_best = vo2_result.scalar()

        return {
            "test_count": test_count,
            "latest_test_date": latest_test_date,
            "vo2_max_best": vo2_max_best,
        }

    async def create(self, data: SubjectCreate) -> Subject:
        """피험자 생성"""
        subject = Subject(
            research_id=data.research_id,
            encrypted_name=data.encrypted_name,
            birth_year=data.birth_year,
            gender=data.gender,
            job_category=data.job_category,
            medical_history=data.medical_history,
            training_level=data.training_level,
            weight_kg=data.weight_kg,
            height_cm=data.height_cm,
            notes=data.notes,
        )
        self.db.add(subject)
        await self.db.commit()
        await self.db.refresh(subject)
        return subject

    async def update(
        self, subject_id: UUID, data: SubjectUpdate
    ) -> Optional[Subject]:
        """피험자 업데이트"""
        subject = await self.get_by_id(subject_id)
        if not subject:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(subject, field, value)

        subject.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(subject)
        return subject

    async def delete(self, subject_id: UUID) -> bool:
        """피험자 삭제 (cascade로 테스트도 삭제)"""
        subject = await self.get_by_id(subject_id)
        if not subject:
            return False

        await self.db.delete(subject)
        await self.db.commit()
        return True

    async def get_subjects_for_cohort(
        self,
        gender: Optional[str] = None,
        age_min: Optional[int] = None,
        age_max: Optional[int] = None,
        training_level: Optional[str] = None,
    ) -> List[UUID]:
        """코호트 분석용 피험자 ID 목록 조회"""
        current_year = datetime.now().year
        query = select(Subject.id)

        if gender and gender != "All":
            query = query.where(Subject.gender == gender)

        if age_min is not None and Subject.birth_year is not None:
            max_birth_year = current_year - age_min
            query = query.where(Subject.birth_year <= max_birth_year)

        if age_max is not None and Subject.birth_year is not None:
            min_birth_year = current_year - age_max
            query = query.where(Subject.birth_year >= min_birth_year)

        if training_level and training_level != "All":
            query = query.where(Subject.training_level == training_level)

        result = await self.db.execute(query)
        return list(result.scalars().all())
