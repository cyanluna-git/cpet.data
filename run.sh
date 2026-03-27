#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

B='\033[94m' G='\033[92m' Y='\033[93m' R='\033[91m' NC='\033[0m'
log()  { printf "${B}[INFO]${NC} %s\n" "$*"; }
ok()   { printf "${G}[OK]${NC} %s\n" "$*"; }
warn() { printf "${Y}[WARN]${NC} %s\n" "$*"; }
err()  { printf "${R}[ERROR]${NC} %s\n" "$*" >&2; }

SERVER_PID=""
CHANNEL_PID=""

load_env() {
    if [[ -f "$ROOT/.env" ]]; then
        set -a
        # shellcheck disable=SC1091
        source "$ROOT/.env"
        set +a
    else
        warn ".env 파일이 없습니다. 기본값으로 실행합니다."
    fi

    : "${BACKEND_HOST:=127.0.0.1}"
    : "${BACKEND_PORT:=8100}"
    : "${CPET_CHANNEL_PORT:=8788}"
    : "${CPET_CHANNEL_URL:=http://127.0.0.1:${CPET_CHANNEL_PORT}}"
    : "${CPET_DATA_DIR:=data}"

    export BACKEND_HOST BACKEND_PORT CPET_CHANNEL_PORT CPET_CHANNEL_URL CPET_DATA_DIR
}

check_prereqs() {
    local mode="$1"
    local fail=0

    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        err "python3를 찾을 수 없습니다."
        fail=1
    fi

    if ! "$PYTHON_BIN" -c "import uvicorn" >/dev/null 2>&1; then
        err "uvicorn이 설치되어 있지 않습니다."
        err "  → pip install -r requirements-server.txt -r requirements-pipeline.txt"
        fail=1
    fi

    if [[ "$mode" == "all" || "$mode" == "channel" ]]; then
        if ! command -v bun >/dev/null 2>&1; then
            err "bun을 찾을 수 없습니다."
            fail=1
        elif [[ ! -d "$ROOT/channel/node_modules" ]]; then
            err "channel 의존성이 없습니다."
            err "  → cd channel && bun install"
            fail=1
        fi
    fi

    return "$fail"
}

start_server() {
    log "FastAPI 서버 시작 중... (${BACKEND_HOST}:${BACKEND_PORT})"
    (
        cd "$ROOT"
        exec "$PYTHON_BIN" -m uvicorn server.main:app \
            --reload \
            --host "$BACKEND_HOST" \
            --port "$BACKEND_PORT"
    ) &
    SERVER_PID=$!
    ok "App      → http://${BACKEND_HOST}:${BACKEND_PORT}"
    ok "Docs     → http://${BACKEND_HOST}:${BACKEND_PORT}/docs"
}

start_channel() {
    log "Claude channel webhook 시작 중... (127.0.0.1:${CPET_CHANNEL_PORT})"
    (
        cd "$ROOT/channel"
        exec bun run webhook.ts
    ) &
    CHANNEL_PID=$!
    ok "Channel  → http://127.0.0.1:${CPET_CHANNEL_PORT}/health"
}

cleanup() {
    echo
    warn "서비스 종료 중..."

    if [[ -n "$SERVER_PID" ]]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    if [[ -n "$CHANNEL_PID" ]]; then
        kill "$CHANNEL_PID" 2>/dev/null || true
        wait "$CHANNEL_PID" 2>/dev/null || true
    fi

    ok "종료 완료"
}

usage() {
    cat <<'EOF'
Usage: ./run.sh [all|server|channel]

  all      Run FastAPI and Bun webhook together
  server   Run only FastAPI
  channel  Run only Bun webhook
EOF
}

main() {
    local mode="${1:-all}"

    case "$mode" in
        all|server|channel) ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            err "알 수 없는 모드: $mode"
            usage >&2
            exit 1
            ;;
    esac

    load_env
    check_prereqs "$mode" || exit 1
    trap 'cleanup; exit 0' INT TERM

    case "$mode" in
        server)
            start_server
            wait "$SERVER_PID"
            ;;
        channel)
            start_channel
            wait "$CHANNEL_PID"
            ;;
        all)
            start_channel
            start_server
            wait
            ;;
    esac
}

main "$@"
