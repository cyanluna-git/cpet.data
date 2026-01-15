"""Decorators for role-based access control and request validation."""

from functools import wraps
from typing import List, Callable, Any
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthCredential
import jwt
from ..core.config import settings
from ..core.security import decode_token

security = HTTPBearer()


def require_role(*allowed_roles: str) -> Callable:
    """
    Decorator to require specific roles for an endpoint.
    
    Usage:
        @app.get("/admin-only")
        @require_role("admin")
        async def admin_endpoint(current_user: User = Depends(get_current_user)):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Get current_user from kwargs (from dependency injection)
            current_user = kwargs.get('current_user')
            
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated"
                )
            
            if hasattr(current_user, 'role'):
                user_role = current_user.role
            elif isinstance(current_user, dict):
                user_role = current_user.get('role')
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid user object"
                )
            
            if user_role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"This action requires one of the following roles: {', '.join(allowed_roles)}"
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_any_role(*allowed_roles: str) -> Callable:
    """
    Decorator to require any of the specified roles for an endpoint.
    Same as require_role but with more explicit naming.
    """
    return require_role(*allowed_roles)


def require_admin(func: Callable) -> Callable:
    """Decorator to require admin role."""
    return require_role("admin")(func)


def require_researcher(func: Callable) -> Callable:
    """Decorator to require researcher role."""
    return require_role("researcher", "admin")(func)


def require_subject(func: Callable) -> Callable:
    """Decorator to require subject role."""
    return require_role("subject")(func)
