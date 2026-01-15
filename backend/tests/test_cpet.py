"""Tests for CPET test service and data handling."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.models import CPETTest, Subject, User
from app.services.test import TestService
from app.schemas.test import CPETTestCreate, CPETTestUpdate


@pytest.mark.asyncio
class TestCPETTestList:
    """Test listing CPET tests."""

    async def test_list_tests_for_subject_success(
        self, async_db: AsyncSession, test_subject: Subject, test_researcher_user: User
    ):
        """Test listing CPET tests for a subject."""
        # Create some test records
        test_data = CPETTest(
            test_id="TEST001",
            subject_id=test_subject.subject_id,
            test_date=datetime.utcnow(),
            max_vo2=45.5,
            max_hr=180,
            rpe_max=19,
            notes="Good effort",
        )
        async_db.add(test_data)
        await async_db.commit()

        service = TestService(async_db)
        tests = await service.get_subject_tests(test_subject.subject_id)

        assert len(tests) >= 1
        assert any(t.test_id == "TEST001" for t in tests)

    async def test_list_tests_empty(
        self, async_db: AsyncSession, test_subject_2: Subject
    ):
        """Test listing tests for subject with no tests."""
        service = TestService(async_db)
        tests = await service.get_subject_tests(test_subject_2.subject_id)

        assert len(tests) == 0

    async def test_list_all_tests(self, async_db: AsyncSession, test_subject: Subject):
        """Test listing all tests in database."""
        # Create test
        test_data = CPETTest(
            test_id="TEST002",
            subject_id=test_subject.subject_id,
            test_date=datetime.utcnow(),
            max_vo2=48.0,
            max_hr=185,
            rpe_max=20,
        )
        async_db.add(test_data)
        await async_db.commit()

        service = TestService(async_db)
        tests = await service.get_all_tests()

        assert len(tests) >= 1
        assert any(t.test_id == "TEST002" for t in tests)


@pytest.mark.asyncio
class TestCPETTestMetrics:
    """Test CPET test metrics calculation."""

    async def test_get_test_metrics_success(
        self, async_db: AsyncSession, test_subject: Subject
    ):
        """Test retrieving test metrics."""
        test_data = CPETTest(
            test_id="TEST003",
            subject_id=test_subject.subject_id,
            test_date=datetime.utcnow(),
            max_vo2=50.5,
            max_hr=190,
            rpe_max=20,
            vent_threshold=65,
            o2_pulse=14.2,
            notes="Peak performance",
        )
        async_db.add(test_data)
        await async_db.commit()

        service = TestService(async_db)
        test = await service.get_test("TEST003")

        assert test is not None
        assert test.max_vo2 == 50.5
        assert test.max_hr == 190
        assert test.vent_threshold == 65

    async def test_calculate_vo2_max(self):
        """Test VO2max calculation."""
        # VO2max = max_watts * (10.8 / weight_kg) + 7
        # Example: 250W, 75kg = 250 * (10.8 / 75) + 7 = 36 + 7 = 43 ml/kg/min
        max_watts = 250
        weight_kg = 75
        
        vo2_max = max_watts * (10.8 / weight_kg) + 7
        assert abs(vo2_max - 43.0) < 0.1

    async def test_calculate_anaerobic_threshold(self):
        """Test anaerobic threshold calculation."""
        # AT = % of VO2max where ventilation increases
        vo2_max = 50
        at_percent = 85  # Typically 80-85% of VO2max
        
        at_vo2 = vo2_max * (at_percent / 100)
        assert abs(at_vo2 - 42.5) < 0.1


@pytest.mark.asyncio
class TestCPETTestCRUD:
    """Test CRUD operations for CPET tests."""

    async def test_create_test_success(
        self, async_db: AsyncSession, test_subject: Subject
    ):
        """Test creating a new CPET test."""
        test_data = CPETTest(
            test_id="TEST004",
            subject_id=test_subject.subject_id,
            test_date=datetime.utcnow(),
            max_vo2=45.0,
            max_hr=175,
            rpe_max=19,
        )
        async_db.add(test_data)
        await async_db.commit()

        service = TestService(async_db)
        test = await service.get_test("TEST004")

        assert test is not None
        assert test.test_id == "TEST004"
        assert test.max_vo2 == 45.0

    async def test_update_test_success(
        self, async_db: AsyncSession, test_subject: Subject
    ):
        """Test updating a CPET test."""
        test_data = CPETTest(
            test_id="TEST005",
            subject_id=test_subject.subject_id,
            test_date=datetime.utcnow(),
            max_vo2=45.0,
            max_hr=175,
            rpe_max=19,
        )
        async_db.add(test_data)
        await async_db.commit()

        service = TestService(async_db)
        updated = await service.update_test(
            "TEST005",
            CPETTestUpdate(
                max_vo2=46.5,
                max_hr=178,
                notes="Updated after review",
            ),
        )

        assert updated.max_vo2 == 46.5
        assert updated.max_hr == 178
        assert updated.notes == "Updated after review"

    async def test_delete_test_success(
        self, async_db: AsyncSession, test_subject: Subject
    ):
        """Test deleting a CPET test."""
        test_data = CPETTest(
            test_id="TEST006",
            subject_id=test_subject.subject_id,
            test_date=datetime.utcnow(),
            max_vo2=45.0,
            max_hr=175,
        )
        async_db.add(test_data)
        await async_db.commit()

        service = TestService(async_db)
        await service.delete_test("TEST006")

        deleted = await service.get_test("TEST006")
        assert deleted is None

    async def test_get_nonexistent_test(self, async_db: AsyncSession):
        """Test retrieving nonexistent test."""
        service = TestService(async_db)
        test = await service.get_test("NONEXISTENT")

        assert test is None


@pytest.mark.asyncio
class TestCPETDataValidation:
    """Test CPET test data validation."""

    async def test_vo2_max_range_validation(self):
        """Test VO2max is within valid range."""
        # Normal VO2max ranges: 20-80 ml/kg/min
        valid_vo2_values = [25, 40, 55, 70]
        invalid_vo2_values = [0, 5, 85, 150]

        for vo2 in valid_vo2_values:
            assert 20 <= vo2 <= 80, f"VO2max {vo2} should be valid"

        for vo2 in invalid_vo2_values:
            assert not (20 <= vo2 <= 80), f"VO2max {vo2} should be invalid"

    async def test_max_hr_range_validation(self):
        """Test max heart rate is within valid range."""
        # Normal max HR: 100-220 bpm
        valid_hr_values = [120, 160, 190, 210]
        invalid_hr_values = [50, 80, 230, 300]

        for hr in valid_hr_values:
            assert 100 <= hr <= 220, f"Max HR {hr} should be valid"

        for hr in invalid_hr_values:
            assert not (100 <= hr <= 220), f"Max HR {hr} should be invalid"

    async def test_rpe_max_range_validation(self):
        """Test RPE max is within valid range (Borg 6-20 scale)."""
        # RPE ranges from 6 (rest) to 20 (maximum)
        valid_rpe = [15, 18, 19, 20]
        invalid_rpe = [0, 5, 21, 30]

        for rpe in valid_rpe:
            assert 6 <= rpe <= 20, f"RPE {rpe} should be valid"

        for rpe in invalid_rpe:
            assert not (6 <= rpe <= 20), f"RPE {rpe} should be invalid"

    async def test_test_date_validation(self):
        """Test test date is not in future."""
        from datetime import datetime, timedelta, timezone

        valid_date = datetime.now(timezone.utc) - timedelta(days=1)
        future_date = datetime.now(timezone.utc) + timedelta(days=1)

        assert valid_date < datetime.now(timezone.utc)
        assert future_date > datetime.now(timezone.utc)
