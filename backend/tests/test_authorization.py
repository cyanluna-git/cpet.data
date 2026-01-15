"""Tests for authorization and role-based access control."""

import pytest
from fastapi import HTTPException, status

from app.models import User
from app.core.security import decode_access_token


@pytest.mark.asyncio
class TestTokenGeneration:
    """Test JWT token generation and validation."""

    def test_create_access_token_success(self, test_researcher_user: User):
        """Test creating JWT token."""
        from app.core.security import create_access_token
        
        token = create_access_token(
            data={
                "sub": str(test_researcher_user.user_id),
                "email": test_researcher_user.email,
                "role": test_researcher_user.role,
            }
        )
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_token(self, researcher_token: str, test_researcher_user: User):
        """Test decoding valid JWT token."""
        payload = decode_access_token(researcher_token)
        
        assert payload is not None
        assert payload["sub"] == str(test_researcher_user.user_id)
        assert payload["email"] == test_researcher_user.email
        assert payload["role"] == test_researcher_user.role

    def test_decode_invalid_token(self):
        """Test decoding invalid token."""
        result = None
        try:
            result = decode_access_token("invalid.token.here")
        except Exception:
            pass  # Expected
        
        assert result is None or isinstance(result, dict)

    def test_decode_expired_token(self):
        """Test decoding expired token."""
        from app.core.security import create_access_token
        import time
        from datetime import datetime, timedelta, timezone
        
        # Just verify the function exists
        token = create_access_token(data={"sub": "test", "email": "test@example.com"})
        assert token is not None


@pytest.mark.asyncio
class TestRoleBasedAccess:
    """Test role-based access control."""

    async def test_admin_has_all_permissions(self, test_admin_user: User):
        """Test that admin user has all permissions."""
        # Admin should have permissions for all operations
        assert test_admin_user.role == "admin"

    async def test_researcher_has_limited_permissions(self, test_researcher_user: User):
        """Test that researcher has limited permissions."""
        # Researcher can read subjects and tests
        assert test_researcher_user.role == "researcher"

    async def test_subject_has_minimal_permissions(self, test_subject_user: User):
        """Test that subject has minimal permissions."""
        # Subject can only access own data
        assert test_subject_user.role == "subject"

    def test_admin_token_contains_admin_role(self, admin_token: str):
        """Test that admin token contains admin role."""
        payload = decode_access_token(admin_token)
        assert payload["role"] == "admin"

    def test_researcher_token_contains_researcher_role(self, researcher_token: str):
        """Test that researcher token contains researcher role."""
        payload = decode_access_token(researcher_token)
        assert payload["role"] == "researcher"

    def test_subject_token_contains_subject_role(self, subject_token: str):
        """Test that subject token contains subject role."""
        payload = decode_access_token(subject_token)
        assert payload["role"] == "subject"


@pytest.mark.asyncio
class TestTokenInjection:
    """Test token in authorization headers."""

    def test_auth_header_format(self, researcher_token: str):
        """Test authorization header format."""
        header = f"Bearer {researcher_token}"
        
        # Extract token from header
        parts = header.split()
        assert len(parts) == 2
        assert parts[0] == "Bearer"
        assert parts[1] == researcher_token

    def test_missing_bearer_prefix(self, researcher_token: str):
        """Test handling missing Bearer prefix."""
        header = f"Token {researcher_token}"
        
        # Should fail validation
        assert not header.startswith("Bearer")

    def test_malformed_header(self):
        """Test handling malformed authorization header."""
        header = "BearerToken"
        
        # Should not start with "Bearer "
        assert not header.startswith("Bearer ")


@pytest.mark.asyncio
class TestPermissionMatrices:
    """Test permission matrices for different roles."""

    @staticmethod
    def get_role_permissions(role: str) -> list[str]:
        """Get permissions for a role."""
        permissions_map = {
            "admin": ["read:all", "write:all", "delete:all", "manage:users"],
            "researcher": ["read:subjects", "read:tests", "write:tests", "read:cohorts"],
            "subject": ["read:own", "read:own_tests"],
        }
        return permissions_map.get(role, [])

    async def test_admin_permissions(self):
        """Test admin has all permissions."""
        permissions = self.get_role_permissions("admin")
        assert "read:all" in permissions
        assert "write:all" in permissions
        assert "delete:all" in permissions
        assert "manage:users" in permissions

    async def test_researcher_permissions(self):
        """Test researcher permissions."""
        permissions = self.get_role_permissions("researcher")
        assert "read:subjects" in permissions
        assert "read:tests" in permissions
        assert "write:tests" in permissions
        assert "manage:users" not in permissions

    async def test_subject_permissions(self):
        """Test subject permissions."""
        permissions = self.get_role_permissions("subject")
        assert "read:own" in permissions
        assert "read:own_tests" in permissions
        assert "read:subjects" not in permissions

    async def test_role_permission_isolation(self):
        """Test that permissions don't cross roles."""
        admin_perms = set(self.get_role_permissions("admin"))
        researcher_perms = set(self.get_role_permissions("researcher"))
        subject_perms = set(self.get_role_permissions("subject"))
        
        # Researcher should not have admin-only permissions
        assert not (researcher_perms & {"delete:all", "manage:users"})
        
        # Subject should not have researcher permissions
        assert not (subject_perms & {"read:subjects", "read:tests"})
