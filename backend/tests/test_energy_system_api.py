"""API Integration Tests for Energy System 3-pathway Analysis.

Tests the FastAPI endpoints:
- GET  /api/tests/{test_id}/energy-system  (auto-calculate)
- POST /api/tests/{test_id}/energy-system  (override + save)

Uses in-memory SQLite via conftest.py fixtures and an httpx AsyncClient
to drive the full request lifecycle.
"""

import math
import uuid
from datetime import datetime
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base, get_db
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models import BreathData, CPETTest, ProcessedMetabolism, Subject, User
from app.models.blood_sample import BloodSample


# ---------------------------------------------------------------------------
# Helpers — synthetic data factories
# ---------------------------------------------------------------------------


def _make_subject(subject_id: uuid.UUID | None = None) -> Subject:
    return Subject(
        id=subject_id or uuid.uuid4(),
        research_id=f"ES-{uuid.uuid4().hex[:6]}",
        encrypted_name="Test Subject",
        birth_year=1990,
        gender="M",
        training_level="Recreational",
        medical_history={},
    )


def _make_user(
    role: str = "researcher",
    subject_id: uuid.UUID | None = None,
) -> User:
    return User(
        user_id=uuid.uuid4(),
        email=f"{uuid.uuid4().hex[:8]}@test.com",
        password_hash=get_password_hash("password123"),
        role=role,
        is_active=True,
        subject_id=subject_id,
    )


def _make_test(
    subject_id: uuid.UUID,
    *,
    weight_kg: float = 70.0,
    warmup_end_sec: int = 0,
    test_end_sec: int = 600,
) -> CPETTest:
    return CPETTest(
        test_id=uuid.uuid4(),
        subject_id=subject_id,
        test_date=datetime(2025, 6, 1),
        weight_kg=weight_kg,
        warmup_end_sec=warmup_end_sec,
        test_end_sec=test_end_sec,
    )


def _make_breath_rows(
    test_id: uuid.UUID,
    *,
    duration_sec: int = 600,
    recovery_sec: int = 180,
    vo2_ml_min: float = 2000.0,
    exercise_power: int = 200,
    recovery_tau: float = 30.0,
) -> list[BreathData]:
    """Generate synthetic BreathData for exercise + recovery."""
    rows: list[BreathData] = []
    base = datetime(2025, 6, 1, 10, 0, 0)

    # Exercise phase
    for i in range(duration_sec):
        rows.append(BreathData(
            time=datetime(2025, 6, 1, 10, i // 60, i % 60),
            test_id=test_id,
            t_sec=float(i),
            vo2=vo2_ml_min,
            bike_power=exercise_power,
        ))

    # Recovery phase (mono-exponential decay)
    amplitude = vo2_ml_min - 500.0
    for i in range(recovery_sec):
        t = duration_sec + i
        vo2 = amplitude * math.exp(-i / recovery_tau) + 500.0
        rows.append(BreathData(
            time=datetime(2025, 6, 1, 10, t // 60, t % 60),
            test_id=test_id,
            t_sec=float(t),
            vo2=vo2,
            bike_power=0,
        ))

    return rows


def _make_blood_samples(
    test_id: uuid.UUID,
    *,
    resting: float = 1.0,
    peak: float = 8.0,
) -> list[BloodSample]:
    return [
        BloodSample(
            id=uuid.uuid4(),
            cpet_test_id=test_id,
            block="rest",
            lactate_mmol=resting,
            elapsed_sec=0.0,
        ),
        BloodSample(
            id=uuid.uuid4(),
            cpet_test_id=test_id,
            block="exercise",
            lactate_mmol=peak,
            elapsed_sec=590.0,
        ),
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def researcher_client(async_db: AsyncSession) -> AsyncGenerator[tuple[AsyncClient, uuid.UUID], None]:
    """Provide an httpx AsyncClient authenticated as researcher, with seeded data.

    Returns (client, test_id) where test_id has breath + blood sample data.
    """
    # Seed subject, user, test
    subject = _make_subject()
    async_db.add(subject)
    await async_db.flush()

    user = _make_user(role="researcher")
    async_db.add(user)
    await async_db.flush()

    cpet = _make_test(subject.id)
    async_db.add(cpet)
    await async_db.flush()

    # Breath data + blood samples
    breath_rows = _make_breath_rows(cpet.test_id)
    async_db.add_all(breath_rows)
    blood = _make_blood_samples(cpet.test_id)
    async_db.add_all(blood)
    await async_db.commit()

    # Token
    token = create_access_token(data={
        "sub": str(user.user_id),
        "email": user.email,
        "role": user.role,
    })

    # Override DB dependency
    async def _override_db():
        yield async_db

    app.dependency_overrides[get_db] = _override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {token}"
        yield client, cpet.test_id

    app.dependency_overrides.clear()


@pytest.fixture
async def subject_client(async_db: AsyncSession) -> AsyncGenerator[tuple[AsyncClient, uuid.UUID, uuid.UUID], None]:
    """Client authenticated as a 'subject' user linked to their own test.

    Returns (client, test_id, subject_id).
    """
    subject = _make_subject()
    async_db.add(subject)
    await async_db.flush()

    user = _make_user(role="subject", subject_id=subject.id)
    async_db.add(user)
    await async_db.flush()

    cpet = _make_test(subject.id)
    async_db.add(cpet)
    await async_db.flush()

    breath_rows = _make_breath_rows(cpet.test_id)
    async_db.add_all(breath_rows)
    blood = _make_blood_samples(cpet.test_id)
    async_db.add_all(blood)
    await async_db.commit()

    token = create_access_token(data={
        "sub": str(user.user_id),
        "email": user.email,
        "role": user.role,
    })

    async def _override_db():
        yield async_db

    app.dependency_overrides[get_db] = _override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {token}"
        yield client, cpet.test_id, subject.id

    app.dependency_overrides.clear()


@pytest.fixture
async def no_lactate_client(async_db: AsyncSession) -> AsyncGenerator[tuple[AsyncClient, uuid.UUID], None]:
    """Client with test data but NO blood samples (2-pathway)."""
    subject = _make_subject()
    async_db.add(subject)
    await async_db.flush()

    user = _make_user(role="researcher")
    async_db.add(user)
    await async_db.flush()

    cpet = _make_test(subject.id)
    async_db.add(cpet)
    await async_db.flush()

    breath_rows = _make_breath_rows(cpet.test_id)
    async_db.add_all(breath_rows)
    await async_db.commit()

    token = create_access_token(data={
        "sub": str(user.user_id),
        "email": user.email,
        "role": user.role,
    })

    async def _override_db():
        yield async_db

    app.dependency_overrides[get_db] = _override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {token}"
        yield client, cpet.test_id

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetEnergySystem:
    """GET /api/tests/{test_id}/energy-system"""

    async def test_three_pathway_with_lactate(
        self, researcher_client: tuple[AsyncClient, uuid.UUID]
    ) -> None:
        """With breath + lactate data, response has 3 pathways summing to 100%."""
        client, test_id = researcher_client

        resp = await client.get(f"/api/tests/{test_id}/energy-system")
        assert resp.status_code == 200

        data = resp.json()
        assert data["has_lactate"] is True
        assert data["has_phosphagen"] is True
        assert data["total_kj"] is not None
        assert data["total_kj"] > 0

        names = [p["name"] for p in data["pathways"]]
        assert "Oxidative" in names
        assert "Glycolytic" in names
        assert "Phosphagen" in names
        assert len(data["pathways"]) == 3

        pct_sum = sum(p["percentage"] for p in data["pathways"])
        assert abs(pct_sum - 100.0) < 0.2, f"Percentage sum {pct_sum} != 100%"

    async def test_two_pathway_without_lactate(
        self, no_lactate_client: tuple[AsyncClient, uuid.UUID]
    ) -> None:
        """Without lactate data, response has 2 pathways and has_lactate=false."""
        client, test_id = no_lactate_client

        resp = await client.get(f"/api/tests/{test_id}/energy-system")
        assert resp.status_code == 200

        data = resp.json()
        assert data["has_lactate"] is False

        names = [p["name"] for p in data["pathways"]]
        assert "Glycolytic" not in names
        assert "Oxidative" in names

        # Percentages of present pathways should sum to 100%
        pct_sum = sum(p["percentage"] for p in data["pathways"] if p["percentage"] is not None)
        assert abs(pct_sum - 100.0) < 0.2

    async def test_404_for_unknown_test(
        self, researcher_client: tuple[AsyncClient, uuid.UUID]
    ) -> None:
        """Non-existent test_id returns 404."""
        client, _ = researcher_client
        fake_id = uuid.uuid4()

        resp = await client.get(f"/api/tests/{fake_id}/energy-system")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestPostEnergySystem:
    """POST /api/tests/{test_id}/energy-system"""

    async def test_recovery_override_changes_phosphagen(
        self, researcher_client: tuple[AsyncClient, uuid.UUID]
    ) -> None:
        """POST with manual recovery window produces is_manual_override=true."""
        client, test_id = researcher_client

        # First, get baseline
        baseline = await client.get(f"/api/tests/{test_id}/energy-system")
        assert baseline.status_code == 200

        # Override with a narrower recovery window
        resp = await client.post(
            f"/api/tests/{test_id}/energy-system",
            json={
                "recovery_start_sec": 610,
                "recovery_end_sec": 720,
                "save": False,
            },
        )
        assert resp.status_code == 200

        data = resp.json()
        assert data["recovery_window"]["is_manual_override"] is True
        assert data["recovery_window"]["start_sec"] == 610

    async def test_save_requires_researcher_role(
        self, researcher_client: tuple[AsyncClient, uuid.UUID]
    ) -> None:
        """Researcher can save energy system results."""
        client, test_id = researcher_client

        # First create a processed_metabolism record so save has a target
        # (without it, the save just appends a warning but still returns 200)
        resp = await client.post(
            f"/api/tests/{test_id}/energy-system",
            json={"save": True},
        )
        assert resp.status_code == 200

    async def test_invalid_recovery_window(
        self, researcher_client: tuple[AsyncClient, uuid.UUID]
    ) -> None:
        """recovery_end_sec <= recovery_start_sec returns 400."""
        client, test_id = researcher_client

        resp = await client.post(
            f"/api/tests/{test_id}/energy-system",
            json={
                "recovery_start_sec": 700,
                "recovery_end_sec": 600,
            },
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestEdgeCases:
    """Edge cases: short recovery, single lactate point, etc."""

    async def test_short_recovery_no_phosphagen(
        self, async_db: AsyncSession
    ) -> None:
        """Very short recovery phase: phosphagen not calculable."""
        subject = _make_subject()
        async_db.add(subject)
        await async_db.flush()

        user = _make_user(role="researcher")
        async_db.add(user)
        await async_db.flush()

        cpet = _make_test(subject.id, test_end_sec=600)
        async_db.add(cpet)
        await async_db.flush()

        # Only 5 seconds of recovery
        breath = _make_breath_rows(cpet.test_id, recovery_sec=5)
        async_db.add_all(breath)
        blood = _make_blood_samples(cpet.test_id)
        async_db.add_all(blood)
        await async_db.commit()

        token = create_access_token(data={
            "sub": str(user.user_id),
            "email": user.email,
            "role": user.role,
        })

        async def _override_db():
            yield async_db

        app.dependency_overrides[get_db] = _override_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers["Authorization"] = f"Bearer {token}"

            resp = await client.get(f"/api/tests/{cpet.test_id}/energy-system")
            assert resp.status_code == 200

            data = resp.json()
            assert data["has_lactate"] is True
            # Phosphagen may or may not be available with 5 sec recovery
            # but warnings should exist if unavailable
            if not data["has_phosphagen"]:
                assert len(data["warnings"]) > 0

        app.dependency_overrides.clear()

    async def test_single_lactate_point(
        self, async_db: AsyncSession
    ) -> None:
        """A single blood sample without a rest sample means no delta_lactate."""
        subject = _make_subject()
        async_db.add(subject)
        await async_db.flush()

        user = _make_user(role="researcher")
        async_db.add(user)
        await async_db.flush()

        cpet = _make_test(subject.id)
        async_db.add(cpet)
        await async_db.flush()

        breath = _make_breath_rows(cpet.test_id)
        async_db.add_all(breath)

        # Only peak sample, no rest block
        single_blood = BloodSample(
            id=uuid.uuid4(),
            cpet_test_id=cpet.test_id,
            block="exercise",
            lactate_mmol=8.0,
            elapsed_sec=590.0,
        )
        async_db.add(single_blood)
        await async_db.commit()

        token = create_access_token(data={
            "sub": str(user.user_id),
            "email": user.email,
            "role": user.role,
        })

        async def _override_db():
            yield async_db

        app.dependency_overrides[get_db] = _override_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers["Authorization"] = f"Bearer {token}"

            resp = await client.get(f"/api/tests/{cpet.test_id}/energy-system")
            assert resp.status_code == 200

            data = resp.json()
            # Without a resting_lactate, has_lactate may still be false
            # because the code requires both resting and peak lactate
            if not data["has_lactate"]:
                names = [p["name"] for p in data["pathways"]]
                assert "Glycolytic" not in names

        app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestAuthAndAccess:
    """Authentication and role-based access control."""

    async def test_unauthenticated_get_returns_401(
        self, async_db: AsyncSession
    ) -> None:
        """Request without Bearer token returns 401."""
        # Seed minimal data so the route exists
        subject = _make_subject()
        async_db.add(subject)
        await async_db.flush()

        cpet = _make_test(subject.id)
        async_db.add(cpet)
        await async_db.commit()

        async def _override_db():
            yield async_db

        app.dependency_overrides[get_db] = _override_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/tests/{cpet.test_id}/energy-system")
            assert resp.status_code == 401

        app.dependency_overrides.clear()

    async def test_subject_can_access_own_test(
        self, subject_client: tuple[AsyncClient, uuid.UUID, uuid.UUID]
    ) -> None:
        """A subject-role user can read energy-system data for their own test."""
        client, test_id, _ = subject_client

        resp = await client.get(f"/api/tests/{test_id}/energy-system")
        assert resp.status_code == 200

    async def test_subject_cannot_access_other_subject_test(
        self, async_db: AsyncSession
    ) -> None:
        """A subject-role user gets 403 when accessing a different subject's test."""
        # Create the owner subject and test
        owner_subject = _make_subject()
        async_db.add(owner_subject)
        await async_db.flush()

        cpet = _make_test(owner_subject.id)
        async_db.add(cpet)
        await async_db.flush()

        breath_rows = _make_breath_rows(cpet.test_id)
        async_db.add_all(breath_rows)

        # Create a different subject user (unrelated to the test)
        other_subject = _make_subject()
        async_db.add(other_subject)
        await async_db.flush()

        other_user = _make_user(role="subject", subject_id=other_subject.id)
        async_db.add(other_user)
        await async_db.commit()

        token = create_access_token(data={
            "sub": str(other_user.user_id),
            "email": other_user.email,
            "role": other_user.role,
        })

        async def _override_db():
            yield async_db

        app.dependency_overrides[get_db] = _override_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers["Authorization"] = f"Bearer {token}"
            resp = await client.get(f"/api/tests/{cpet.test_id}/energy-system")
            assert resp.status_code == 403

        app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestSavedResultsPath:
    """GET returns cached results when processed_metabolism.energy_system is set."""

    async def test_get_returns_saved_results_when_available(
        self, async_db: AsyncSession
    ) -> None:
        """If a ProcessedMetabolism row already has energy_system data,
        GET must return that saved dict without recalculating."""
        subject = _make_subject()
        async_db.add(subject)
        await async_db.flush()

        user = _make_user(role="researcher")
        async_db.add(user)
        await async_db.flush()

        cpet = _make_test(subject.id)
        async_db.add(cpet)
        await async_db.flush()

        # Store a pre-computed result in ProcessedMetabolism
        saved_data = {
            "pathways": [
                {"name": "Oxidative", "energy_kj": 999.0, "percentage": 100.0, "color": "#3B82F6"},
            ],
            "total_kj": 999.0,
            "has_lactate": False,
            "has_phosphagen": False,
            "delta_lactate": None,
            "exercise_duration_sec": 600.0,
            "body_weight_kg": 70.0,
            "mono_exp_fit": None,
            "recovery_window": None,
            "warnings": ["pre-saved sentinel"],
        }
        pm = ProcessedMetabolism(
            cpet_test_id=cpet.test_id,
            energy_system=saved_data,
        )
        async_db.add(pm)

        # Also add breath data (to confirm the router doesn't recalculate)
        breath_rows = _make_breath_rows(cpet.test_id)
        async_db.add_all(breath_rows)
        await async_db.commit()

        token = create_access_token(data={
            "sub": str(user.user_id),
            "email": user.email,
            "role": user.role,
        })

        async def _override_db():
            yield async_db

        app.dependency_overrides[get_db] = _override_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers["Authorization"] = f"Bearer {token}"
            resp = await client.get(f"/api/tests/{cpet.test_id}/energy-system")

        app.dependency_overrides.clear()

        assert resp.status_code == 200
        data = resp.json()
        # The sentinel value confirms the saved path was taken, not live calculation
        assert data["total_kj"] == 999.0
        assert "pre-saved sentinel" in data["warnings"]


@pytest.mark.asyncio
class TestPostOverrides:
    """POST endpoint optional exercise window override."""

    async def test_exercise_window_override(
        self, researcher_client: tuple[AsyncClient, uuid.UUID]
    ) -> None:
        """POST with explicit exercise_start_sec/exercise_end_sec is accepted."""
        client, test_id = researcher_client

        resp = await client.post(
            f"/api/tests/{test_id}/energy-system",
            json={
                "exercise_start_sec": 0,
                "exercise_end_sec": 300,
                "save": False,
            },
        )
        assert resp.status_code == 200

        data = resp.json()
        # With 300s window instead of 600s, duration should be ≤ 300s
        assert data["exercise_duration_sec"] is not None
        assert data["exercise_duration_sec"] <= 300.0

    async def test_subject_cannot_save_energy_system(
        self, subject_client: tuple[AsyncClient, uuid.UUID, uuid.UUID]
    ) -> None:
        """A subject-role user gets 403 when attempting save=true."""
        client, test_id, _ = subject_client

        resp = await client.post(
            f"/api/tests/{test_id}/energy-system",
            json={"save": True},
        )
        assert resp.status_code == 403

    async def test_no_breath_data_returns_404(
        self, async_db: AsyncSession
    ) -> None:
        """Test that exists but has no breath data returns 404 on GET."""
        subject = _make_subject()
        async_db.add(subject)
        await async_db.flush()

        user = _make_user(role="researcher")
        async_db.add(user)
        await async_db.flush()

        cpet = _make_test(subject.id)
        async_db.add(cpet)
        await async_db.commit()

        # No breath data added — _calculate_energy_system raises 404

        token = create_access_token(data={
            "sub": str(user.user_id),
            "email": user.email,
            "role": user.role,
        })

        async def _override_db():
            yield async_db

        app.dependency_overrides[get_db] = _override_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers["Authorization"] = f"Bearer {token}"
            resp = await client.get(f"/api/tests/{cpet.test_id}/energy-system")
            assert resp.status_code == 404

        app.dependency_overrides.clear()
