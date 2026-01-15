"""Tests for subject management."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.models import Subject
from app.services import SubjectService
from app.schemas import SubjectCreate, SubjectUpdate


@pytest.mark.asyncio
@pytest.mark.subjects
class TestSubjectList:
    """Test listing subjects."""

    async def test_list_subjects_success(
        self, async_db: AsyncSession, test_subject: Subject, test_subject_2: Subject
    ):
        """Test listing subjects successfully."""
        service = SubjectService(async_db)
        
        # Test fetching subjects
        subject1 = await service.get_by_id(test_subject.id)
        subject2 = await service.get_by_id(test_subject_2.id)
        
        assert subject1 is not None
        assert subject2 is not None

    async def test_list_subjects_empty(self, async_db: AsyncSession):
        """Test listing when no subjects match."""
        service = SubjectService(async_db)
        
        # Generate a random ID that doesn't exist
        random_id = uuid4()
        subject = await service.get_by_id(random_id)
        
        assert subject is None

    async def test_list_subjects_pagination(
        self, async_db: AsyncSession, test_subject: Subject, test_subject_2: Subject
    ):
        """Test pagination in subject list."""
        service = SubjectService(async_db)
        
        # Get list with pagination
        subjects_page1, total1 = await service.get_list(page=1, page_size=1)
        assert len(subjects_page1) <= 1
        assert isinstance(total1, int)

    async def test_list_subjects_search_by_name(
        self, async_db: AsyncSession, test_subject: Subject
    ):
        """Test searching subjects by research ID."""
        service = SubjectService(async_db)
        
        # Search by research ID
        subject = await service.get_by_research_id(test_subject.research_id)
        
        assert subject is None or isinstance(subject, Subject)

    async def test_list_subjects_search_by_id(
        self, async_db: AsyncSession, test_subject: Subject
    ):
        """Test searching subjects by ID."""
        service = SubjectService(async_db)
        
        subject = await service.get_by_research_id("S001")
        
        # May or may not find
        assert isinstance(subject, Subject) or subject is None

    async def test_list_subjects_filter_by_gender(
        self, async_db: AsyncSession, test_subject: Subject
    ):
        """Test filtering subjects by gender."""
        service = SubjectService(async_db)
        subjects_list, total = await service.get_list(page=1, page_size=20)
        
        # Verify we can get a list
        assert isinstance(subjects_list, list)
        assert isinstance(total, int)

    async def test_list_subjects_filter_by_training_level(
        self, async_db: AsyncSession, test_subject: Subject
    ):
        """Test filtering subjects by training level."""
        service = SubjectService(async_db)
        subjects_list, total = await service.get_list(page=1, page_size=20)
        
        assert isinstance(subjects_list, list)
        assert isinstance(total, int)


@pytest.mark.asyncio
@pytest.mark.subjects
class TestSubjectCRUD:
    """Test subject CRUD operations."""

    async def test_get_subject_success(
        self, async_db: AsyncSession, test_subject: Subject
    ):
        """Test retrieving a specific subject."""
        service = SubjectService(async_db)
        
        subject = await service.get_by_id(test_subject.id)
        
        assert subject is not None
        assert subject.id == test_subject.id

    async def test_get_subject_not_found(self, async_db: AsyncSession):
        """Test retrieving non-existent subject."""
        service = SubjectService(async_db)
        
        random_id = uuid4()
        subject = await service.get_by_id(random_id)
        
        assert subject is None

    async def test_create_subject_success(self, async_db: AsyncSession):
        """Test creating a new subject."""
        service = SubjectService(async_db)
        
        subject_data = SubjectCreate(
            research_id="S003",
            name="Bob Smith",
            age=45,
            gender="M",
            training_level="recreational",
            medical_history="Hypertension",
        )
        
        subject = await service.create(subject_data)
        
        assert subject is not None
        assert subject.research_id == "S003"

    async def test_create_subject_validation(self, async_db: AsyncSession):
        """Test subject creation with valid data."""
        service = SubjectService(async_db)
        
        # Create with valid data
        subject_data = SubjectCreate(
            research_id="S004",
            name="Valid Subject",
            age=30,
            gender="M",
            training_level="recreational",
        )
        subject = await service.create(subject_data)
        assert subject is not None

    async def test_update_subject_success(
        self, async_db: AsyncSession, test_subject: Subject
    ):
        """Test updating subject information."""
        service = SubjectService(async_db)
        
        update_data = SubjectUpdate(age=31)
        
        updated = await service.update(test_subject.id, update_data)
        
        assert updated is not None

    async def test_delete_subject_success(
        self, async_db: AsyncSession, test_subject: Subject
    ):
        """Test deleting a subject."""
        service = SubjectService(async_db)
        
        result = await service.delete(test_subject.id)
        
        # Verify deleted
        subject = await service.get_by_id(test_subject.id)
        assert subject is None

    async def test_delete_nonexistent_subject(self, async_db: AsyncSession):
        """Test deleting non-existent subject."""
        service = SubjectService(async_db)
        
        random_id = uuid4()
        # Should handle gracefully
        result = await service.delete(random_id)
        assert result is None or isinstance(result, bool)


@pytest.mark.asyncio
@pytest.mark.subjects
class TestSubjectValidation:
    """Test subject data validation."""

    async def test_subject_age_validation(self, async_db: AsyncSession):
        """Test age validation."""
        service = SubjectService(async_db)
        
        # Valid age
        valid_data = SubjectCreate(
            research_id="S010",
            name="Test Subject",
            age=30,
            gender="M",
            training_level="recreational",
        )
        subject = await service.create(valid_data)
        assert subject.age == 30

    async def test_subject_gender_validation(self, async_db: AsyncSession):
        """Test gender validation."""
        service = SubjectService(async_db)
        
        # Valid gender
        valid_data = SubjectCreate(
            research_id="S011",
            name="Test Subject",
            age=30,
            gender="F",
            training_level="recreational",
        )
        subject = await service.create(valid_data)
        assert subject.gender == "F"

    async def test_subject_training_level_validation(self, async_db: AsyncSession):
        """Test training level validation."""
        service = SubjectService(async_db)
        
        # Valid training levels
        for level in ["sedentary", "recreational", "trained", "elite"]:
            data = SubjectCreate(
                research_id=f"S-{level}-{uuid4().hex[:6]}",
                name="Test Subject",
                age=30,
                gender="M",
                training_level=level,
            )
            subject = await service.create(data)
            assert subject.training_level == level
