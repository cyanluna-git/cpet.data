"""API routers"""

from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.subjects import router as subjects_router
from app.api.tests import router as tests_router, subject_tests_router
from app.api.processed_metabolism import router as processed_metabolism_router

__all__ = [
    "auth_router",
    "admin_router",
    "subjects_router",
    "tests_router",
    "subject_tests_router",
    "processed_metabolism_router",
]
