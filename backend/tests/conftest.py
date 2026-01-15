"""Pytest configuration and fixtures for CPET backend tests."""

import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import Base
from app.core.security import create_access_token, get_password_hash
from app.models import User, Subject


@pytest.fixture(scope="function")
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    """Create an async test database session."""
    # Use in-memory SQLite for testing
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    async_session_maker = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_maker() as session:
        yield session

    await engine.dispose()

# User fixtures
@pytest.fixture
async def test_admin_user(async_db: AsyncSession) -> User:
    """Create a test admin user."""
    user = User(
        user_id=uuid.uuid4(),
        email="admin@example.com",
        password_hash=get_password_hash("password123"),
        role="admin",
        is_active=True,
    )
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)
    return user


@pytest.fixture
async def test_researcher_user(async_db: AsyncSession) -> User:
    """Create a test researcher user."""
    user = User(
        user_id=uuid.uuid4(),
        email="researcher@example.com",
        password_hash=get_password_hash("password123"),
        role="researcher",
        is_active=True,
    )
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)
    return user


@pytest.fixture
async def test_subject_user(async_db: AsyncSession) -> User:
    """Create a test subject user."""
    user = User(
        user_id=uuid.uuid4(),
        email="subject@example.com",
        password_hash=get_password_hash("password123"),
        role="subject",
        is_active=True,
    )
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)
    return user


# Subject fixtures
@pytest.fixture
async def test_subject(async_db: AsyncSession) -> Subject:
    """Create a test subject."""
    subject = Subject(
        id=uuid.uuid4(),
        research_id="S001",
        encrypted_name="John Doe",
        birth_year=1990,
        gender="M",
        training_level="Recreational",
        medical_history={},
    )
    async_db.add(subject)
    await async_db.commit()
    await async_db.refresh(subject)
    return subject


@pytest.fixture
async def test_subject_2(async_db: AsyncSession) -> Subject:
    """Create a second test subject."""
    subject = Subject(
        id=uuid.uuid4(),
        research_id="S002",
        encrypted_name="Jane Doe",
        birth_year=1992,
        gender="F",
        training_level="Elite",
        medical_history={},
    )
    async_db.add(subject)
    await async_db.commit()
    await async_db.refresh(subject)
    return subject


# Token fixtures
@pytest.fixture
def admin_token(test_admin_user: User) -> str:
    """Generate JWT token for admin user."""
    return create_access_token(
        data={
            "sub": str(test_admin_user.user_id),
            "email": test_admin_user.email,
            "role": test_admin_user.role,
        }
    )


@pytest.fixture
def researcher_token(test_researcher_user: User) -> str:
    """Generate JWT token for researcher user."""
    return create_access_token(
        data={
            "sub": str(test_researcher_user.user_id),
            "email": test_researcher_user.email,
            "role": test_researcher_user.role,
        }
    )


@pytest.fixture
def subject_token(test_subject_user: User) -> str:
    """Generate JWT token for subject user."""
    return create_access_token(
        data={
            "sub": str(test_subject_user.user_id),
            "email": test_subject_user.email,
            "role": test_subject_user.role,
        }
    )


# Helper fixtures
@pytest.fixture
def auth_headers_admin(admin_token: str) -> dict:
    """Create authorization headers for admin."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def auth_headers_researcher(researcher_token: str) -> dict:
    """Create authorization headers for researcher."""
    return {"Authorization": f"Bearer {researcher_token}"}


@pytest.fixture
def auth_headers_subject(subject_token: str) -> dict:
    """Create authorization headers for subject."""
    return {"Authorization": f"Bearer {subject_token}"}
@pytest.fixture
def auth_headers_subject(subject_token: str) -> dict:
    """Create authorization headers for subject."""
    return {"Authorization": f"Bearer {subject_token}"}
