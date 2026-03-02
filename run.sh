#!/usr/bin/env bash
# CPET Platform Dev Launcher
# DB:      docker compose (PostgreSQL + TimescaleDB)
# Backend: local uvicorn (backend/.venv)
# Frontend: local npm run dev
#
# Usage:
#   ./run.sh              → 모든 서비스 (DB + Backend + Frontend)
#   ./run.sh db           → DB만 (Docker)
#   ./run.sh backend      → Backend만
#   ./run.sh frontend     → Frontend만
#   Ctrl+C 종료

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"

# Colors
B='\033[94m' G='\033[92m' Y='\033[93m' R='\033[91m' NC='\033[0m'
log()  { printf "${B}[INFO]${NC} %s\n" "$*"; }
ok()   { printf "${G}[OK]${NC} %s\n" "$*"; }
warn() { printf "${Y}[WARN]${NC} %s\n" "$*"; }
err()  { printf "${R}[ERROR]${NC} %s\n" "$*" >&2; }

# Tracked PIDs
BE_PID="" FE_PID=""

load_env() {
    if [[ -f "$ROOT/.env" ]]; then
        set -a
        # shellcheck disable=SC1091
        source "$ROOT/.env"
        set +a
    else
        warn ".env 파일이 없습니다 ($ROOT/.env)"
    fi
    # Apply defaults for vars not set in .env
    : "${DB_PORT:=5100}"
    : "${BACKEND_HOST:=0.0.0.0}"
    : "${BACKEND_PORT:=8100}"
    : "${FRONTEND_PORT:=3100}"
    : "${VITE_API_URL:=http://localhost:$BACKEND_PORT}"
    export VITE_API_URL FRONTEND_PORT BACKEND_PORT
}

check_prereqs() {
    local mode="$1" fail=0

    if [[ ! -f "$ROOT/.env" ]]; then
        err ".env 파일이 없습니다."
        fail=1
    fi

    if [[ "$mode" == all || "$mode" == db ]]; then
        if ! command -v docker &>/dev/null; then
            err "Docker가 설치되어 있지 않습니다."
            fail=1
        fi
    fi

    if [[ "$mode" == all || "$mode" == backend ]]; then
        if [[ ! -x "$BACKEND_DIR/.venv/bin/uvicorn" ]]; then
            err "Backend venv가 없습니다."
            err "  → cd backend && python -m venv .venv && pip install -r requirements.txt"
            fail=1
        fi
    fi

    if [[ "$mode" == all || "$mode" == frontend ]]; then
        if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
            err "Frontend 의존성이 없습니다."
            err "  → cd frontend && npm install"
            fail=1
        fi
    fi

    return $fail
}

start_db() {
    log "PostgreSQL + TimescaleDB 시작 중... (포트: $DB_PORT)"
    if docker compose -f "$ROOT/docker-compose.yml" up -d; then
        ok "DB 시작됨 → localhost:$DB_PORT"
        sleep 2
    else
        err "DB 시작 실패"
        return 1
    fi
}

start_backend() {
    log "Backend (FastAPI) 시작 중... (포트: $BACKEND_PORT)"
    (
        cd "$BACKEND_DIR"
        exec "$BACKEND_DIR/.venv/bin/uvicorn" app.main:app \
            --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT"
    ) &
    BE_PID=$!
    ok "Backend  → http://localhost:$BACKEND_PORT"
    ok "API Docs → http://localhost:$BACKEND_PORT/api/docs"
}

start_frontend() {
    log "Frontend (React + Vite) 시작 중... (포트: $FRONTEND_PORT)"
    (
        cd "$FRONTEND_DIR"
        exec npm run dev
    ) &
    FE_PID=$!
    ok "Frontend → http://localhost:$FRONTEND_PORT"
}

cleanup() {
    echo ""
    warn "서비스 종료 중..."
    if [[ -n "$BE_PID" ]]; then
        log "Backend 종료..."
        kill "$BE_PID" 2>/dev/null || true
        wait "$BE_PID" 2>/dev/null || true
    fi
    if [[ -n "$FE_PID" ]]; then
        log "Frontend 종료..."
        kill "$FE_PID" 2>/dev/null || true
        wait "$FE_PID" 2>/dev/null || true
    fi
    log "Docker 컨테이너는 계속 실행됩니다."
    log "  DB 중지: docker compose down"
    ok "종료 완료"
}

print_header() {
    local mode="$1"
    printf "\n%s\n" "============================================================"
    printf "  CPET Platform\n"
    case "$mode" in
        all)      printf "  실행: DB(Docker) + Backend + Frontend\n" ;;
        db)       printf "  실행: DB (PostgreSQL + TimescaleDB, Docker)\n" ;;
        backend)  printf "  실행: Backend (FastAPI)\n" ;;
        frontend) printf "  실행: Frontend (React + Vite)\n" ;;
    esac
    printf "  종료: Ctrl+C\n"
    printf "%s\n\n" "============================================================"
}

print_status() {
    local mode="$1"
    printf "\n%s\n" "============================================================"
    case "$mode" in
        all)
            printf "  ${G}✓${NC} 모든 서비스 실행 중\n"
            printf "  DB:       localhost:%s\n" "$DB_PORT"
            printf "  Backend:  http://localhost:%s\n" "$BACKEND_PORT"
            printf "  API Docs: http://localhost:%s/api/docs\n" "$BACKEND_PORT"
            printf "  Frontend: http://localhost:%s\n" "$FRONTEND_PORT"
            printf "  종료하려면 Ctrl+C를 누르세요\n"
            ;;
        db)
            printf "  ${G}✓${NC} DB 실행 중\n"
            printf "  PostgreSQL: localhost:%s\n" "$DB_PORT"
            printf "  중지: docker compose down\n"
            ;;
        backend)
            printf "  ${G}✓${NC} Backend 실행 중\n"
            printf "  Backend:  http://localhost:%s\n" "$BACKEND_PORT"
            printf "  API Docs: http://localhost:%s/api/docs\n" "$BACKEND_PORT"
            printf "  종료하려면 Ctrl+C를 누르세요\n"
            ;;
        frontend)
            printf "  ${G}✓${NC} Frontend 실행 중\n"
            printf "  Frontend: http://localhost:%s\n" "$FRONTEND_PORT"
            printf "  종료하려면 Ctrl+C를 누르세요\n"
            ;;
    esac
    printf "%s\n\n" "============================================================"
}

main() {
    local mode="${1:-all}"

    case "$mode" in
        all|db|backend|frontend) ;;
        -h|--help)
            printf "Usage: %s [all|db|backend|frontend]\n" "$0"
            exit 0
            ;;
        *)
            err "알 수 없는 서비스: $mode"
            printf "Usage: %s [all|db|backend|frontend]\n" "$0" >&2
            exit 1
            ;;
    esac

    load_env
    print_header "$mode"
    check_prereqs "$mode" || { err "필수 요구사항을 확인해 주세요."; exit 1; }
    ok "요구사항 확인됨"
    echo ""

    trap 'cleanup; exit 0' INT TERM

    case "$mode" in
        db)
            start_db
            print_status db
            # DB runs detached via docker compose; script exits after start
            ;;
        backend)
            start_backend
            print_status backend
            wait "$BE_PID" || true
            ;;
        frontend)
            start_frontend
            print_status frontend
            wait "$FE_PID" || true
            ;;
        all)
            start_db
            start_backend
            sleep 1
            start_frontend
            print_status all
            wait || true
            ;;
    esac
}

main "$@"
