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

## Memory & Rules

### Imports
See `.claude/rules/` (auto-loaded, path-scoped):
- **code-style.md** — Python/TypeScript conventions
- **testing.md** — pytest/Vitest patterns
- **api-conventions.md** — REST API standards
- **commit-workflow.md** — Git conventions (all files)
- **security.md** — Secrets & validation

### Project-specific Rules
- **backend/.claude/CLAUDE.md** — FastAPI service config
- **frontend/.claude/CLAUDE.md** — React SPA config

### Auto Memory
To enable auto memory learning across sessions:
```bash
export CLAUDE_CODE_DISABLE_AUTO_MEMORY=0
/memory  # View/edit memory files
```
Auto memory stores patterns, debugging insights, and architecture notes in `~/.claude/projects/cpet.db/memory/`

## Model Selection Guide

Automatically route tasks to appropriate Claude models based on complexity:

### Haiku (Fast responses)
**Use for:** Basic questions, queries, file searches, simple modifications
- "What files contain FATMAX logic?"
- "Explain this function"
- "Fix this typo in README"
- "List database tables"
- **Time:** <30 seconds

### Sonnet (Balanced performance)
**Use for:** Detailed analysis, exploration, planning, medium-scale code changes (3–5 files)
- "Analyze COSMED parser efficiency"
- "Design caching strategy for breath_data"
- "Refactor authentication flow"
- "Implement new API endpoint"
- "Debug performance issue"
- **Time:** 30s–2 minutes

### Opus (Deep reasoning)
**Use for:** Complex reasoning, architecture design, large refactoring (5+ files), comprehensive implementations
- "Plan full-stack VO2MAX calculation redesign"
- "Refactor entire data pipeline"
- "Optimize database query performance"
- "Implement real-time data processing"
- "Design new testing framework"
- **Time:** 2–10 minutes

**Quick Reference:**
```
/ask "what is..."              → Haiku
/analyze "improve this..."     → Sonnet
/design "architect..."         → Opus
```

Explicitly specify model when needed: `[Opus] Design the new...`
