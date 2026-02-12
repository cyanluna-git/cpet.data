# Backend Module

Python FastAPI service for CPET data processing and analysis.

## Overview

Async REST API (port 8100) handling CPET data upload, parsing, metabolic analysis, and persistence to PostgreSQL + TimescaleDB.

## Tech Stack

- **Framework**: FastAPI (async)
- **ORM**: SQLAlchemy (async, aiosqlite in dev)
- **Database**: PostgreSQL 15 + TimescaleDB
- **Validation**: Pydantic
- **Testing**: pytest + asyncio
- **Code Quality**: Black, flake8, mypy

## Key Modules

- `app/api/` — Endpoints (auth, tests, cohorts, subjects)
- `app/services/` — Business logic:
  - `COSMEDParser` — Excel → breath data
  - `MetabolismAnalyzer` — FATMAX, VO2MAX calculation
  - `AuthService` — JWT handling
- `app/models/` — SQLAlchemy ORM models
- `app/schemas/` — Pydantic request/response models

## Commands

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8100  # Dev
pytest                                      # Tests
black . && flake8 . && mypy .               # Quality
```

## Environment

- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: JWT signing key
- `CORS_ORIGINS`: Allowed frontend URLs

## Parent Rules

Inherit from `@../../.claude/rules/`:
- code-style.md — Python conventions (FastAPI async patterns)
- testing.md — pytest fixtures, async testing
- api-conventions.md — REST endpoint design
- commit-workflow.md — Git conventions
- security.md — Input validation, JWT security
