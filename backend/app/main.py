"""FastAPI application entry point"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

app = FastAPI(
    title="CPET Database and Visualization Platform",
    description="COSMED K5 CPET data collection, analysis, and visualization platform",
    version="0.1.0",
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
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


# Include routers here when created
# from app.api import auth, subjects, tests, analysis
# app.include_router(auth.router, prefix="/api/auth", tags=["authentication"])
# app.include_router(subjects.router, prefix="/api/subjects", tags=["subjects"])
# app.include_router(tests.router, prefix="/api/tests", tags=["tests"])
# app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
