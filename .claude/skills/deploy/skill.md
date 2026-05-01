# Deploy Skill

## Auto-Trigger

Invoke `/deploy` automatically when the user says:
- "배포해줘" / "배포해" / "서버에 올려줘" / "VM에 배포"
- "deploy" / "deploy it" / "push to server"

## Environment

Load credentials from `.claude/skills/deploy/.env` before every step:

```bash
set -a
source "$(git rev-parse --show-toplevel)/.claude/skills/deploy/.env"
set +a

SSH="ssh -i $DEPLOY_SSH_KEY $DEPLOY_USER@$DEPLOY_HOST"
```

Variables defined in `.env`:

| Variable | Purpose |
|---|---|
| `DEPLOY_SSH_KEY` | Path to SSH private key |
| `DEPLOY_USER` | Remote user |
| `DEPLOY_HOST` | Server IP or hostname |
| `DEPLOY_PROJECT_DIR` | Absolute project path on the server |
| `DEPLOY_APP_HOST` | uvicorn bind host |
| `DEPLOY_APP_PORT` | uvicorn bind port |
| `DEPLOY_LOG` | Server-side log file |

## Procedure

### Step 1 — Commit uncommitted changes (if any)

```bash
git status --short
```

If there are uncommitted changes:
1. Review `git diff --stat HEAD` to identify what changed
2. Stage relevant files (exclude `.env`, credentials, secrets)
3. Commit with an appropriate conventional commit message
4. Skip this step if the working tree is clean

### Step 2 — Push

```bash
git push origin main
```

### Step 3 — Pull on server

```bash
$SSH "cd $DEPLOY_PROJECT_DIR && git pull"
```

### Step 4 — Restart process

```bash
# Kill ALL matching processes (pkill returns non-zero if none found — that's fine)
ssh -i $DEPLOY_SSH_KEY $DEPLOY_USER@$DEPLOY_HOST \
  "pkill -f 'uvicorn server.main' || true"
sleep 2

# Start new process
ssh -i $DEPLOY_SSH_KEY $DEPLOY_USER@$DEPLOY_HOST \
  "cd $DEPLOY_PROJECT_DIR && source .venv/bin/activate && \
   nohup uvicorn server.main:app \
     --host $DEPLOY_APP_HOST \
     --port $DEPLOY_APP_PORT \
     >> $DEPLOY_LOG 2>&1 &"
```

### Step 5 — Health check

```bash
sleep 3
STATUS=$($SSH "curl -s -o /dev/null -w '%{http_code}' http://$DEPLOY_APP_HOST:$DEPLOY_APP_PORT/")
```

- `200` → success, report done
- anything else → fetch last 30 lines of `$DEPLOY_LOG` and report the error

## Success Report Format

```
Deploy complete
- commit: <hash> <message>
- server: $DEPLOY_HOST
- status: 200 OK
```
