"""API routers"""

from app.api.auth import router as auth_router
from app.api.admin import router as admin_router
from app.api.subjects import router as subjects_router
from app.api.inscyd import router as inscyd_router
from app.api.tests import router as tests_router, subject_tests_router
from app.api.processed_metabolism import router as processed_metabolism_router
from app.api.cohorts import router as cohorts_router
from app.api.blood_samples import router as blood_samples_router
from app.api.energy_system import router as energy_system_router

__all__ = [
    "auth_router",
    "admin_router",
    "subjects_router",
    "inscyd_router",
    "tests_router",
    "subject_tests_router",
    "processed_metabolism_router",
    "cohorts_router",
    "blood_samples_router",
    "energy_system_router",
]
