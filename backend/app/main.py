"""FastAPI application entry point"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api import (
    auth_router,
    subjects_router,
    tests_router,
    subject_tests_router,
)

app = FastAPI(
    title="CPET Database and Visualization Platform",
    description="COSMED K5 CPET data collection, analysis, and visualization platform",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "CPET Database and Visualization Platform API",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


# Include routers with /api prefix
app.include_router(auth_router, prefix="/api")
app.include_router(subjects_router, prefix="/api")
app.include_router(tests_router, prefix="/api")
app.include_router(subject_tests_router, prefix="/api")
