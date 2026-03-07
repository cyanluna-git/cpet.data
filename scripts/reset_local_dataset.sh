#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_CONTAINER="${DB_CONTAINER:-cpet-db}"
DB_USER="${DB_USER:-cpet_user}"
DB_NAME="${DB_NAME:-cpet_db}"

run_sql() {
    docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 >/dev/null
}

echo "[1/6] Starting local PostgreSQL container"
docker compose -f "$ROOT/docker-compose.yml" up -d postgres >/dev/null

echo "[2/6] Recreating database $DB_NAME"
docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL >/dev/null
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "$DB_NAME";
CREATE DATABASE "$DB_NAME";
SQL

echo "[3/6] Initializing schema"
cat "$ROOT/scripts/init-db.sql" | run_sql

echo "[4/6] Loading base fixtures"
docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
    -c "TRUNCATE TABLE users RESTART IDENTITY CASCADE;" >/dev/null

for file in \
    "$ROOT/scripts/fixtures/restore_01_subjects.sql" \
    "$ROOT/scripts/fixtures/restore_02_users.sql" \
    "$ROOT/scripts/fixtures/restore_03_cpet_tests.sql" \
    "$ROOT/scripts/fixtures/restore_04_processed_metabolism.sql" \
    "$ROOT/scripts/fixtures/restore_05_breath_data.sql"
do
    cat "$file" | run_sql
done

echo "[5/6] Applying INSCYD schema and fixture history"
cat "$ROOT/backend/migrations/create_inscyd_reports.sql" | run_sql
cat "$ROOT/scripts/fixtures/restore_06_inscyd_reports.sql" | run_sql

echo "[6/6] Local dataset ready"
docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c \
    "SELECT COUNT(*) AS subjects FROM subjects; \
     SELECT COUNT(*) AS cpet_tests FROM cpet_tests; \
     SELECT COUNT(*) AS breath_data FROM breath_data; \
     SELECT COUNT(*) AS processed_metabolism FROM processed_metabolism; \
     SELECT COUNT(*) AS inscyd_reports FROM inscyd_reports; \
     SELECT s.research_id, COUNT(DISTINCT ct.test_id) AS tests, COUNT(DISTINCT bd.time) AS breath_rows, COUNT(DISTINCT ir.report_id) AS inscyd_reports \
       FROM subjects s \
       LEFT JOIN cpet_tests ct ON ct.subject_id = s.id \
       LEFT JOIN breath_data bd ON bd.test_id = ct.test_id \
       LEFT JOIN inscyd_reports ir ON ir.subject_id = s.id \
      WHERE s.research_id = 'SUB-PAR-GEU' \
      GROUP BY s.research_id;" || true
