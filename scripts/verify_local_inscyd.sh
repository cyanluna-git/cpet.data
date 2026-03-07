#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_CONTAINER="${DB_CONTAINER:-cpet-db}"
DB_USER="${DB_USER:-cpet_user}"
DB_NAME="${DB_NAME:-cpet_db}"
VITE_API_URL="${VITE_API_URL:-http://localhost:8100}"

echo "[1/5] Starting local PostgreSQL container"
docker compose -f "$ROOT/docker-compose.yml" up -d postgres

echo "[2/5] Resetting local verification dataset"
"$ROOT/scripts/reset_local_dataset.sh"

echo "[3/5] Running backend INSCYD tests"
(
    cd "$ROOT/backend"
    ./.venv/bin/pytest tests/test_inscyd.py -q
)

echo "[4/5] Building frontend"
(
    cd "$ROOT/frontend"
    VITE_API_URL="$VITE_API_URL" npm run build
)

echo "[5/5] Running INSCYD E2E"
(
    cd "$ROOT/frontend"
    VITE_API_URL="$VITE_API_URL" npm run test:e2e -- e2e/inscyd-upload.spec.ts --project=chromium
)

echo "Local INSCYD verification passed."
