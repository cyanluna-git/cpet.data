# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CPET (Cardiopulmonary Exercise Test) Platform - A web application for collecting, analyzing, and visualizing metabolic data from COSMED K5 CPET equipment. Key features include automated CPET data processing, metabolic analysis (FATMAX, VO2MAX), and interactive visualization.

## Build & Development Commands

### Database
```bash
docker-compose up -d              # Start PostgreSQL + TimescaleDB (port 5100)
docker-compose down               # Stop database
```

### Backend (Python/FastAPI)
```bash
cd backend
source .venv/bin/activate         # Activate virtualenv
uvicorn app.main:app --reload --port 8100   # Start dev server

# Testing
pytest                            # Run all tests
pytest -v -k "auth"               # Run specific tests
pytest --tb=short                 # Short traceback

# Code quality
black .                           # Format
flake8 .                          # Lint
mypy .                            # Type check
```

### Frontend (React/TypeScript/Vite)
```bash
cd frontend
npm run dev                       # Start dev server (port 3100)
npm run build                     # Production build

# Testing
pnpm test                         # Unit tests (vitest)
pnpm test:e2e                     # E2E tests (playwright)

# Code quality
npm run lint                      # ESLint
```

### Full Stack
```bash
./dev.sh                          # Start backend + frontend together
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (React 18 + TypeScript + Vite)                   │
│  Port 3100 | shadcn/ui + Tailwind | Recharts for viz       │
└─────────────────────────┬───────────────────────────────────┘
                          │ REST API
┌─────────────────────────▼───────────────────────────────────┐
│  Backend (FastAPI + SQLAlchemy Async)                       │
│  Port 8100 | JWT Auth | Pydantic schemas                    │
│  Services: AuthService, TestService, CohortService          │
│  Parser: COSMEDParser (Excel → breath data)                 │
└─────────────────────────┬───────────────────────────────────┘
                          │ SQL
┌─────────────────────────▼───────────────────────────────────┐
│  PostgreSQL 15 + TimescaleDB                                │
│  Port 5100 | Tables: users, subjects, cpet_tests,           │
│  breath_data (hypertable), processed_metabolism             │
└─────────────────────────────────────────────────────────────┘
```

### Key Data Flow

1. **File Upload**: Excel file → `COSMEDParser` extracts metadata + breath data
2. **Analysis**: `MetabolismAnalyzer` calculates FATMAX, VO2MAX, fat/CHO oxidation
3. **Storage**: Raw data → `breath_data` (TimescaleDB), processed → `processed_metabolism`
4. **Visualization**: Frontend fetches via `useFetch` hook → Recharts rendering

### Frontend Patterns

- **Hooks**: `useAuth()` (auth state), `useFetch()` (data fetching with retry), `useNavigation()` (routing)
- **API Client**: Centralized axios instance with Authorization header, timeout, exponential backoff
- **Lazy Loading**: All page components use `React.lazy()` for code splitting
- **Error Handling**: `ErrorBoundary` + toast notifications via Sonner

### Backend Patterns

- **Dependency Injection**: `db: DBSession`, `current_user: CurrentUser` via FastAPI Depends
- **Service Layer**: Business logic in `app/services/`, CRUD in service classes
- **Auth**: JWT tokens with role-based access (`admin`, `researcher`, `subject`)
- **Permissions**: `ResearcherUser`, `CurrentUser` dependencies for endpoint protection

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/api/tests.py` | Test upload/analysis endpoints |
| `backend/app/services/cosmed_parser.py` | COSMED Excel parsing |
| `backend/app/services/metabolism_analysis.py` | FATMAX/VO2MAX calculation |
| `frontend/src/hooks/useAuth.tsx` | Authentication state management |
| `frontend/src/hooks/useFetch.ts` | Data fetching with retry logic |
| `frontend/src/lib/api.ts` | API endpoint definitions |
| `frontend/src/components/pages/MetabolismPage.tsx` | Main analysis visualization |

## Database Schema Notes

- `breath_data`: TimescaleDB hypertable for time-series CPET data
- `cpet_tests`: Test metadata including calculated vo2_max, fat_max_hr, vt1/vt2
- `subjects`: Uses `encrypted_name`, `birth_year` (not `name`, `age`)
- `users`: Uses `password_hash` field (not `hashed_password`)
- All IDs are UUIDs

## Environment Variables

Backend `.env`:
```
DATABASE_URL=postgresql+asyncpg://cpet_user:cpet_password@localhost:5100/cpet_db
SECRET_KEY=your-secret-key
```

Frontend `.env`:
```
VITE_API_URL=http://localhost:8100
```

## API Documentation

When backend is running: http://localhost:8100/docs (Swagger UI)
