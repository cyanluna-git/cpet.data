#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_CONTAINER="${DB_CONTAINER:-cpet-db}"
DB_USER="${DB_USER:-cpet_user}"
DB_NAME="${DB_NAME:-cpet_db}"
VITE_API_URL="${VITE_API_URL:-http://localhost:8100}"

echo "[1/4] Starting local PostgreSQL container"
docker compose -f "$ROOT/docker-compose.yml" up -d postgres

echo "[2/4] Applying INSCYD migration"
cat "$ROOT/backend/migrations/create_inscyd_reports.sql" \
    | docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
    >/dev/null

echo "[3/4] Running backend INSCYD tests"
(
    cd "$ROOT/backend"
    ./.venv/bin/pytest tests/test_inscyd.py -q
)

echo "[4/4] Building frontend"
(
    cd "$ROOT/frontend"
    VITE_API_URL="$VITE_API_URL" npm run build
)

echo "Local INSCYD verification passed."
