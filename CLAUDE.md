# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working with this repository.

## Project Overview

CPET (Cardiopulmonary Exercise Test) Platform — Web application for metabolic data collection, analysis, and visualization from COSMED K5 equipment. Features: automated CPET processing, FATMAX/VO2MAX analysis, breath-by-breath visualization.

## Repository Structure

- `backend/` — Python 3.11 FastAPI + SQLAlchemy Async
- `frontend/` — React 18 + TypeScript 5 + Vite + Shadcn UI
- `docker-compose.yml` — PostgreSQL 15 + TimescaleDB
- `run.py` — Dev launcher (backend + frontend)
- `.claude/rules/` — Shared coding conventions

## Tech Stack & Key Dependencies

**Backend**: FastAPI, SQLAlchemy (async), Pydantic, pytest, PostgreSQL, TimescaleDB, openpyxl  
**Frontend**: React 18, TypeScript, Vite, Tailwind, Shadcn UI, Recharts, React Query  
**Infrastructure**: Docker, docker-compose, Python 3.11

## Architecture

```
Browser → React (port 3100, Vite proxy /api)
       → FastAPI (port 8100, JWT auth)
       → PostgreSQL 15 + TimescaleDB (port 5100)
```

**Key modules:**
- **Backend**: `app/api/`, `app/services/` (COSMEDParser, MetabolismAnalyzer), `app/models/`
- **Frontend**: `pages/`, `hooks/` (useAuth, useFetch), `components/`, `lib/api.ts`
- **Data flow**: Excel → Parser → breath_data → Analyzer → visualization

## Commands

### Database
```bash
docker-compose up -d && docker-compose down
```

### Backend
```bash
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8100
pytest && black . && flake8 . && mypy .
```

### Frontend
```bash
cd frontend
npm run dev && npm run build && npm run lint
pnpm test && pnpm test:e2e
```

### Full Stack
```bash
./dev.sh
```

## Environment Setup

Backend `.env`: `DATABASE_URL`, `SECRET_KEY`, `CORS_ORIGINS`  
Frontend `.env`: `VITE_API_URL=http://localhost:8100`

## Database

- **breath_data**: TimescaleDB hypertable (time-series)
- **cpet_tests**: Metadata + calculated metrics
- **subjects**: encrypted_name, birth_year
- All IDs: UUID

## API Documentation

http://localhost:8100/docs (Swagger UI)

## Imports

See `.claude/rules/`:
- code-style.md — Python/TypeScript conventions
- testing.md — pytest/Vitest patterns
- api-conventions.md — REST API standards
- commit-workflow.md — Git conventions
- security.md — Secrets & validation
