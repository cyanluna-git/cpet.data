"""API routers"""

from app.api.auth import router as auth_router
from app.api.subjects import router as subjects_router
from app.api.tests import router as tests_router, subject_tests_router

__all__ = [
    "auth_router",
    "subjects_router",
    "tests_router",
    "subject_tests_router",
]
