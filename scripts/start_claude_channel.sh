#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_NAME="${1:-claude-cpet}"
CHANNEL_NAME="cpet-webhook"

export PATH="$ROOT_DIR/.venv/bin:$HOME/.bun/bin:$HOME/.local/bin:$PATH"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required" >&2
  exit 1
fi

if ! command -v bun >/dev/null 2>&1; then
  echo "bun is not installed or not on PATH" >&2
  exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "claude is not installed or not on PATH" >&2
  exit 1
fi

if [ ! -f "$ROOT_DIR/.mcp.json" ]; then
  echo ".mcp.json not found in $ROOT_DIR" >&2
  exit 1
fi

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
  echo "tmux session '$SESSION_NAME' already exists"
  echo "attach: tmux attach -t $SESSION_NAME"
  exit 0
fi

tmux new-session -d -s "$SESSION_NAME" \
  "bash -lc 'cd \"$ROOT_DIR\" && export PATH=\"$ROOT_DIR/.venv/bin:$HOME/.bun/bin:$HOME/.local/bin:\$PATH\" && claude --add-dir \"$ROOT_DIR\" --permission-mode bypassPermissions --dangerously-load-development-channels server:$CHANNEL_NAME'"

echo "started tmux session: $SESSION_NAME"
echo "attach: tmux attach -t $SESSION_NAME"
