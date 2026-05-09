# update-claude Skill

## Auto-Trigger

Invoke `/update-claude` automatically when the user says:
- "webhook 클로드 버전 업데이트" / "서버 claude 업데이트" / "claude 업데이트"
- "update claude" / "update claude version" / "서버 클로드 업그레이드"

## Environment

Load credentials from `.claude/skills/deploy/.env`:

```bash
set -a
source "$(git rev-parse --show-toplevel)/.claude/skills/deploy/.env"
set +a

SSH="ssh -i $DEPLOY_SSH_KEY $DEPLOY_USER@$DEPLOY_HOST"
```

## Procedure

### Step 1 — Check current versions

```bash
# Local
claude --version

# Remote
$SSH "claude --version"
```

Report both versions. If already up-to-date, stop here.

### Step 2 — Update on server

```bash
$SSH "sudo npm update -g @anthropic-ai/claude-code 2>&1"
```

### Step 3 — Verify

```bash
$SSH "claude --version"
```

## Success Report Format

```
Claude Code 업데이트 완료
- 이전: <old_version>
- 이후: <new_version>
- 서버: $DEPLOY_HOST
```
