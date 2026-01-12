# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Overview

This repository contains the **CPET Database and Visualization Platform**, a web app for ingesting COSMED K5 CPET Excel files, storing them in PostgreSQL/TimescaleDB, computing metabolic metrics (e.g. FATMAX, VO2MAX), and visualizing results.

Top-level layout (see `README.md` for more detail):
- `backend/`: FastAPI + SQLAlchemy async backend
- `frontend/`: React + TypeScript + Vite SPA
- `scripts/`: database initialization SQL (`init-db.sql`)
- `doc/`: requirements (`srs.md`)
- `CPET_data/`: sample CPET files
- `docker-compose.yml`: TimescaleDB stack
- `run.py`: one-command dev orchestrator for DB, backend, and frontend
- `TODOS.md`: detailed roadmap and current phase

When in doubt about project direction or priorities, prefer information in `TODOS.md` (kept up to date) over older comments in code or docs.

## Core commands

### One-command dev environment (preferred)

Run everything from the repo root using the orchestrator script. This expects a **root** `.env` file (see below), a backend virtualenv at `backend/venv`, and `frontend/node_modules` to already exist.

```bash path=null start=null
cd /Users/cyanluna-pro16/dev/cpet.db
python run.py
```

`run.py` will:
- Load `DB_PORT`, `BACKEND_HOST`, `BACKEND_PORT`, `FRONTEND_PORT` from the root `.env` (with defaults: DB 5100, backend 8100, frontend 3100).
- Start PostgreSQL+TimescaleDB via Docker Compose.
- Start the FastAPI backend in `backend/venv` via `uvicorn app.main:app`.
- Start the Vite dev server in `frontend/` via `npm run dev`.

To stop services, press Ctrl+C in the `run.py` terminal. The DB container is intentionally left running; stop it separately with Docker if desired.

### Database: PostgreSQL + TimescaleDB

From the repo root, you can manage the database stack directly (used both by `run.py` and in `README.md`):

```bash path=null start=null
# Start database
docker compose up -d

# Stop database
docker compose down
```

`docker-compose.yml` reads credentials and ports from the **root** `.env` via:
- `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- `DB_PORT` (host port) and `DB_INTERNAL_PORT` (container port, usually 5432)

Schema and TimescaleDB setup are applied by `scripts/init-db.sql` when the container is first created.

### Backend (FastAPI)

Backend code lives under `backend/app`. Environment configuration is centralized through the root `.env` via `app.core.config.Settings` (see Architecture section below).

First-time setup:

```bash path=null start=null
cd backend
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# .\\venv\\Scripts\\activate  # Windows
pip install -r requirements.txt
```

Backend dev server (if you are not using `run.py`):

```bash path=null start=null
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

Key points:
- `app.core.config.Settings` provides `BACKEND_HOST`, `BACKEND_PORT`, `DB_*` and derives `database_url` for SQLAlchemy async.
- CORS allowed origins are configured via `ALLOWED_ORIGINS` in the root `.env` (comma-separated).

#### Backend testing and code quality

The backend uses pytest and standard Python tooling (see `backend/requirements.txt`). There is not yet a `tests/` directory in the current tree, but once tests are added the canonical commands from `backend/` are:

```bash path=null start=null
cd backend
source venv/bin/activate

# Run all tests
pytest

# Run a single test file
pytest tests/test_some_feature.py

# Filter tests by keyword
pytest -k "keyword"

# Formatting, linting, type checking
black app
flake8 app
mypy app
```

These commands align with the tools pinned in `requirements.txt` (`pytest`, `pytest-asyncio`, `black`, `flake8`, `mypy`).

### Frontend (React + Vite)

First-time setup:

```bash path=null start=null
cd frontend
npm install
cp .env.example .env  # optional; see notes below
```

Dev server (if not using `run.py`):

```bash path=null start=null
cd frontend
npm run dev
```

Other useful scripts (from `frontend/package.json`):

```bash path=null start=null
cd frontend
npm run build   # tsc -b && vite build
npm run lint    # eslint .
npm run preview # vite preview
```

Frontend configuration details:
- `vite.config.ts` reads environment from the **repo root** using `loadEnv(mode, rootDir, '')`, where `rootDir` is the parent of `frontend/`.
- It configures:
  - `server.port` from `FRONTEND_PORT` (default 3100 if unset).
  - Proxy for `/api` to `http://localhost:{BACKEND_PORT}`.
  - `import.meta.env.VITE_API_URL` to either `VITE_API_URL` (if set in `.env`) or `http://localhost:{BACKEND_PORT}`.
- `frontend/.env.example` currently defines `VITE_API_BASE_URL` and other Vite vars; if you rely on `VITE_API_URL` in future code, make sure the env examples stay in sync with `vite.config.ts`.

ESLint is configured via `frontend/eslint.config.js` using `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, and `eslint-plugin-react-refresh`.

## Architecture and structure

### Orchestration and environment

**Root-level orchestration**
- `run.py` is the canonical way to spin up the full stack in development.
- It owns the default port conventions and uses `config = { DB_PORT: 5100, BACKEND_PORT: 8100, FRONTEND_PORT: 3100 }` overridden by the root `.env`.
- It enforces basic pre-checks: presence of `.env`, Docker + Docker Compose, `backend/venv`, and `frontend/node_modules`.
- It streams prefixed logs from backend (`[BE]`) and frontend (`[FE]`) so you can see both in one terminal.

**Configuration source of truth**
- Backend configuration is defined in `backend/app/core/config.py` via a `Settings` class (`pydantic-settings`).
- `Settings` reads from the **root** `.env` (computed from `ROOT_DIR = Path(__file__).parent.parent.parent.parent`).
- Important settings:
  - DB connection: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` and `DATABASE_URL`.
  - App: `BACKEND_HOST`, `BACKEND_PORT`, `DEBUG`, `APP_NAME`.
  - Security: `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `ENCRYPTION_KEY`.
  - CORS: `ALLOWED_ORIGINS` (comma-separated string) exposed as `allowed_origins_list`.
  - Frontend: `FRONTEND_PORT` for coordination with Vite.

**Database stack**
- `docker-compose.yml` runs `timescale/timescaledb:latest-pg15` as `cpet-db`.
- Uses the root `.env` for credentials and ports (`DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT`, `DB_INTERNAL_PORT`).
- Mounts `scripts/init-db.sql` to `/docker-entrypoint-initdb.d/` to create schemas and enable TimescaleDB on first run.

### Backend architecture

Backend packages live under `backend/app`:

- `app/main.py`
  - Defines the FastAPI application with title/description for the CPET platform.
  - Configures CORS using `settings.allowed_origins_list`.
  - Exposes lightweight `"/"` and `"/health"` endpoints for basic status checks.
  - Includes routers from `app.api` under the `/api` prefix (currently only the authentication router).

- `app/core/`
  - `config.py`: `Settings` class and `settings` singleton as described above.
  - `database.py`:
    - Creates the async SQLAlchemy engine from `settings.database_url`.
    - Defines `AsyncSessionLocal` and `Base = declarative_base()` used by models.
    - Provides `get_db()` (FastAPI dependency yielding an `AsyncSession`) and `init_db()` (async table-creation helper).
  - `security.py`:
    - Password hashing and verification via `passlib`/bcrypt.
    - JWT token creation/decoding via `python-jose` using `settings.SECRET_KEY` and `settings.ALGORITHM`.

- `app/models/` (PostgreSQL/TimescaleDB layer)
  - `subject.py`: `Subject` model for participant metadata including demographics, training level, and medical history (stored in JSONB). Linked to `CPETTest` and optionally to `User`.
  - `cpet_test.py`: `CPETTest` model for test-level metadata (protocol, timings, environmental conditions, VO2MAX/FATMAX metrics, thresholds, etc.) with indexes on `subject_id` and `test_date`.
  - `breath_data.py`: `BreathData` time-series model designed for a TimescaleDB hypertable.
    - Composite primary key: `(time, test_id)`.
    - Stores breath-by-breath metrics (VO2, VCO2, VE, HR, etc.), exercise load, gas fractions, derived metrics (RER, fat/CHO oxidation, VO2/kg, METS), and quality flags/phase annotations.
    - Related back to `CPETTest` via `test` relationship; indexes on `(test_id, time)` and `(test_id, phase)` to support typical analyses.
  - `cohort_stats.py`: `CohortStats` for aggregated cohort statistics (by gender/age group/training level and metric name) with uniqueness and lookup indexes.
  - `user.py`: `User` model for authentication and authorization, with email-based login, roles (`admin`, `researcher`, `user`), `subject_id` link, active flag, and audit timestamps.

- `app/services/` (business logic & analysis)
  - `auth.py` (`AuthService`): encapsulates authentication logic using an injected `AsyncSession`.
    - User lookup by email/ID with SQLAlchemy `select()`.
    - Credential verification using `security.verify_password` and active-flag checks.
    - User creation and update (including password hashing and role/subject assignment) and deletion.
    - JWT access token creation via `security.create_access_token`, embedding `user_id`, `email`, and `role`.
  - `cosmed_parser.py` (`COSMEDParser` and related dataclasses): Excel ingestion and metabolic computation pipeline for COSMED K5 files.
    - Detects protocol type (`BxB` vs `MIX`) from filename.
    - Uses `pandas` to read the `Data` sheet and extract:
      - Subject metadata (ID, name, gender, anthropometrics, DOB).
      - Test metadata (date/time, test type, durations, HR source, protocol, ergometer, reasons for test/stopping).
      - Environmental conditions (barometric pressure, temperatures, humidity, STPD/BTPS, HR max, BSA, BMI).
      - Time-series measurements with column normalization (`COLUMN_MAPPING`) and physiological range checks (`VALID_RANGES`).
    - Provides helpers to calculate metabolic metrics (`calculate_metabolic_metrics`) using Frayn or Jeukendrup formulas and to derive:
      - FATMAX location and metrics (`find_fatmax`).
      - VO2MAX-related metrics (`find_vo2max`).
    - Returns a `ParsedCPETData` object that groups subject/test/environment metadata with a cleaned `DataFrame` of time-series data and parsing diagnostics.

- `app/api/`
  - `__init__.py`: re-exports routers (currently `auth_router`).
  - `auth.py`: FastAPI router under `/api/auth` for authentication and user management.
    - `/login` (form-based, `OAuth2PasswordRequestForm`): authenticates via `AuthService`, updates `last_login`, returns JWT `Token`.
    - `/register`: end-user registration with duplicate-email detection; returns `UserResponse`.
    - `/me` (GET/PUT): get/update current user; update logic reuses `AuthService.update_user`, including email-duplication checks and role-change restrictions for non-admins.
    - Admin-only endpoints (using `AdminUser` dependency): create and delete users by ID with safety checks (e.g. prevent self-deletion).

- `app/api/deps.py`
  - Defines core FastAPI dependencies for auth and DB:
    - `DBSession`: yields an `AsyncSession` via `get_db`.
    - `CurrentUser`: active, authenticated user.
    - `AdminUser`: current active user with `role == "admin"`.
  - Uses `OAuth2PasswordBearer(tokenUrl="/api/auth/login")` and `security.decode_access_token` to validate JWTs and fetch the corresponding `User` via `AuthService`.

- `app/schemas/auth.py`
  - Pydantic models for auth-related input/output:
    - `Token`, `TokenData`, `UserLogin`, `UserCreate`, `UserResponse`, `UserUpdate`.
  - `UserResponse` is configured with `model_config = {"from_attributes": True}` for direct construction from ORM objects.

At the moment, the main API surface is authentication; ingestion of parsed COSMED data into the SQL models will be a next step, as reflected in `TODOS.md`.

### Frontend architecture

Frontend code is under `frontend/` and uses Vite + React + TypeScript.

- Entry and routing
  - `src/main.tsx`: standard React 18+ entry point, renders `<App />` into `#root` inside `<StrictMode>`.
  - `src/App.tsx`:
    - Wraps the app in a `BrowserRouter`.
    - Defines top-level routes:
      - `/` → `Dashboard` page.
      - `/subjects`, `/tests`, `/results`, `/analysis` → placeholder `<div>` pages marked "Coming Soon".

- Pages and styles
  - `src/pages/Dashboard.tsx`:
    - Main landing/dashboard UI, styled via `Dashboard.css`.
    - Uses React Router `<Link>` components for navigation to `/subjects`, `/tests`, `/results`, `/analysis`, `/subjects/new`, and `/tests/new`.
    - Currently uses hard-coded summary stats and recent activity; no API calls yet.
  - `src/pages/Dashboard.css`: layout and styling for the dashboard cards, quick actions, and activity list.

- Tooling
  - TypeScript configs:
    - `tsconfig.json` is a solution-style config referencing `tsconfig.app.json` and `tsconfig.node.json`.
    - `tsconfig.app.json` targets the browser app (`src/`), using `moduleResolution: "bundler"`, `jsx: "react-jsx"`, and strict linting-style options (e.g., `noUnusedLocals`, `noUncheckedSideEffectImports`).
    - `tsconfig.node.json` covers Node-only tooling like `vite.config.ts`.
  - ESLint:
    - Configured via `eslint.config.js` as a flat config using `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, and `eslint-plugin-react-refresh` with browser globals.

## Project docs and roadmap

- `README.md` contains a high-level product description, technology stack, and initial get-started steps. Some specifics (e.g., backend port 8000 and a `backend/.env.example`) predate the newer `run.py` and root `.env` setup; prefer `run.py`, `Settings` in `app/core/config.py`, and `TODOS.md` for the current conventions.
- `TODOS.md` is the authoritative roadmap, organized by phases (Core Infrastructure, Analysis Engine, API, Frontend, etc.) with checklists of completed and planned work.
- `doc/srs.md` describes system requirements and should be consulted when changing core workflows (e.g., data ingestion, analysis algorithms, or access control).
