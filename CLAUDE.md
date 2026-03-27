# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project Overview

CPET v2 is a SQLite-based ingestion and publishing platform. The active stack on `main` is:

- `server/`: FastAPI, Jinja2, HTMX, cookie session auth
- `pipeline/`: parsers, analysis, SQLite schema, report generation
- `channel/`: Bun webhook server that forwards submission events to Claude Code
- `data/` and `published/`: runtime artifacts, not source of truth

Legacy `backend/`, `frontend/`, and Docker/PostgreSQL code are intentionally not part of `main`.

## Architecture

```text
Browser
  → FastAPI (`server.main`, port 8100)
  → SQLite platform DB (`data/cpet_platform.db`)
  → workspace SQLite DB (`data/workspaces/<uuid>/analysis.db`)
  → static published report (`published/<slug>/index.html`)

Optional async path:
FastAPI submit
  → POST to Bun webhook (`channel/webhook.ts`, port 8788)
  → Claude Code channel event
  → `python -m pipeline --workspace <path>`
```

## Dependency Direction

```text
server/main.py, server/auth.py
  → server/api.py, server/db.py, server/workspace.py, server/publish.py
  → pipeline/* via subprocess / generated artifacts
```

- Keep `pipeline/` deterministic and reusable from CLI.
- Keep `server/` responsible for upload, job tracking, auth, and presentation.
- Do not embed report-generation logic directly into FastAPI routes.

## Commands

Setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-server.txt -r requirements-pipeline.txt
cp .env.example .env
```

Run:

```bash
./run.sh server
./run.sh channel
./run.sh all
```

Tests:

```bash
pytest tests -q
python -m pipeline --help
```

## Environment

Important variables:

- `BACKEND_HOST`, `BACKEND_PORT`
- `CPET_DATA_DIR`
- `CPET_CHANNEL_URL`, `CPET_CHANNEL_PORT`
- `SESSION_SECRET`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`

## Repository Rules

- New upload/job behavior belongs in `server/`.
- New parsing or analysis behavior belongs in `pipeline/`.
- Prefer storing derived artifacts in workspace directories, not in git-tracked paths.
- Avoid introducing service dependencies that bypass the SQLite-first v2 design.
- Do not edit `published/` by hand unless the task is explicitly about fixture/output regeneration.

## Memory & Shared Rules

See `.claude/rules/` for shared coding conventions:

- `code-style.md`
- `testing.md`
- `api-conventions.md`
- `commit-workflow.md`
- `security.md`
