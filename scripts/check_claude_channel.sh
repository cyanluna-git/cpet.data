#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_NAME="${1:-claude-cpet}"
PORT="${CPET_CHANNEL_PORT:-8788}"
DB_PATH="${CPET_DB_PATH:-$ROOT_DIR/data/cpet_platform.db}"
HEALTH_URL="http://127.0.0.1:${PORT}/health"

pass() {
  printf '[PASS] %s\n' "$1"
}

warn() {
  printf '[WARN] %s\n' "$1"
}

info() {
  printf '[INFO] %s\n' "$1"
}

echo "== Claude Channel Check =="
echo "root:    $ROOT_DIR"
echo "session: $SESSION_NAME"
echo "health:  $HEALTH_URL"
echo

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  pass "tmux session '$SESSION_NAME' is alive"
else
  warn "tmux session '$SESSION_NAME' is missing"
fi

if pgrep -af '(^|/)claude($| )' >/dev/null 2>&1; then
  pass "claude process is running"
  pgrep -af '(^|/)claude($| )' | sed 's/^/  /'
else
  warn "claude process is not running"
fi

if pgrep -af 'bun .*channel/webhook\.ts' >/dev/null 2>&1; then
  pass "bun webhook process is running"
  pgrep -af 'bun .*channel/webhook\.ts' | sed 's/^/  /'
else
  warn "bun webhook process is not running"
fi

if curl -fsS -m 3 "$HEALTH_URL" >/dev/null 2>&1; then
  pass "channel health endpoint responded"
else
  warn "channel health endpoint did not respond"
fi

echo
info "recent tmux pane output"
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  tmux capture-pane -pt "$SESSION_NAME" -S -40 | tail -n 40 | sed 's/^/  /'
else
  echo "  (no tmux session)"
fi

echo
info "recent jobs"
if [ -f "$DB_PATH" ] && command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 -header -column "$DB_PATH" \
    "select id, status, created_at, started_at, completed_at, report_slug from jobs order by rowid desc limit 5;" \
    | sed 's/^/  /'
else
  warn "sqlite job database not available at $DB_PATH"
fi

echo
info "quick actions"
echo "  attach: tmux attach -t $SESSION_NAME"
echo "  restart: $ROOT_DIR/scripts/start_claude_channel.sh $SESSION_NAME"
