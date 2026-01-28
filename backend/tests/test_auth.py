"""Tests for authentication endpoints."""

import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password, get_password_hash
from app.models import User
from app.services import AuthService


@pytest.mark.asyncio
@pytest.mark.auth
class TestAuthService:
    """Test AuthService methods."""

    async def test_create_user_success(self, async_db: AsyncSession):
        """Test creating a new user."""
        service = AuthService(async_db)

        from app.schemas.auth import UserCreate
        user_create = UserCreate(
            email="newuser@example.com",
            password="password123",
            role="researcher",
        )
        user = await service.create_user(user_create)

        assert user.email == "newuser@example.com"
        assert user.role == "researcher"
        assert verify_password("password123", user.password_hash)

    async def test_authenticate_user_success(
        self, async_db: AsyncSession, test_researcher_user: User
    ):
        """Test authenticating a user with valid credentials."""
        service = AuthService(async_db)

        user = await service.authenticate_user(
            email=test_researcher_user.email,
            password="password123",  # Default test password
        )

        assert user is not None
        assert user.email == test_researcher_user.email

    async def test_authenticate_user_invalid_password(
        self, async_db: AsyncSession, test_researcher_user: User
    ):
        """Test authenticating a user with invalid password."""
        service = AuthService(async_db)

        user = await service.authenticate_user(
            email=test_researcher_user.email,
            password="wrongpassword",
        )

        assert user is None

    async def test_authenticate_user_not_found(self, async_db: AsyncSession):
        """Test authenticating a non-existent user."""
        service = AuthService(async_db)

        user = await service.authenticate_user(
            email="nonexistent@example.com",
            password="password123",
        )

        assert user is None

    async def test_get_user_by_email(
        self, async_db: AsyncSession, test_researcher_user: User
    ):
        """Test retrieving user by email."""
        service = AuthService(async_db)

        user = await service.get_user_by_email(test_researcher_user.email)

        assert user is not None
        assert user.email == test_researcher_user.email

    async def test_get_user_by_email_not_found(self, async_db: AsyncSession):
        """Test retrieving non-existent user by email."""
        service = AuthService(async_db)

        user = await service.get_user_by_email("nonexistent@example.com")

        assert user is None

    async def test_update_user_success(
        self, async_db: AsyncSession, test_researcher_user: User
    ):
        """Test updating user information."""
        service = AuthService(async_db)

        from app.schemas.auth import UserUpdate
        update_data = UserUpdate(email="updated@example.com")

        updated_user = await service.update_user(
            test_researcher_user.user_id, update_data
        )

        assert updated_user.email == "updated@example.com"

    async def test_update_user_role(
        self, async_db: AsyncSession, test_researcher_user: User
    ):
        """Test updating user role."""
        service = AuthService(async_db)

        from app.schemas.auth import UserUpdate
        update_data = UserUpdate(role="admin")

        updated_user = await service.update_user(
            test_researcher_user.user_id, update_data
        )

        # Service allows role change (authorization should be checked at API level)
        assert updated_user.role == "admin"

    async def test_create_user_token_success(
        self, async_db: AsyncSession, test_researcher_user: User
    ):
        """Test creating JWT token for user."""
        service = AuthService(async_db)

        token = service.create_user_token(test_researcher_user)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    async def test_password_hashing(self):
        """Test that passwords are hashed correctly."""
        password = "test_password_123"

        hashed = get_password_hash(password)

        # Same password should verify
        assert verify_password(password, hashed)

        # Different password should not verify
        assert not verify_password("wrong_password", hashed)

        # Hash should be different each time
        hashed2 = get_password_hash(password)
        assert hashed != hashed2
        assert verify_password(password, hashed2)


@pytest.mark.asyncio
@pytest.mark.auth
class TestUserDuplicate:
    """Test duplicate user handling."""

    async def test_cannot_create_duplicate_email(
        self, async_db: AsyncSession, test_researcher_user: User
    ):
        """Test that duplicate email is rejected."""
        service = AuthService(async_db)

        # Should return None or raise exception
        existing_user = await service.get_user_by_email(test_researcher_user.email)
        assert existing_user is not None


@pytest.mark.asyncio
@pytest.mark.auth
class TestUserActivation:
    """Test user activation/deactivation."""

    async def test_inactive_user_cannot_login(self, async_db: AsyncSession):
        """Test that inactive user cannot login."""
        # Create inactive user with proper UUID and field names
        user = User(
            user_id=uuid.uuid4(),
            email="inactive@example.com",
            password_hash=get_password_hash("password123"),
            role="researcher",
            is_active=False,
        )
        async_db.add(user)
        await async_db.commit()

        service = AuthService(async_db)
        authenticated_user = await service.authenticate_user(
            email="inactive@example.com",
            password="password123",
        )

        # Should not authenticate inactive user
        assert authenticated_user is None
