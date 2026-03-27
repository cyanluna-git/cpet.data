# CPET Platform v2

CPET, FIT, ZWO, lactate 데이터를 업로드하면 SQLite 기반 파이프라인으로 분석하고 정적 HTML 리포트를 발행하는 플랫폼입니다. 현재 `main` 브랜치는 `server/ + pipeline/ + channel/` 구조만 유지합니다.

## Current Stack

- `server/`: FastAPI + Jinja2 + HTMX
- `pipeline/`: 파싱, SQLite 적재, 분석, 리포트 생성
- `channel/`: Bun webhook server for Claude Code channels
- Storage: `data/cpet_platform.db` + submission별 `analysis.db`
- Publish: `published/<slug>/index.html`

## Quick Start

사전 요구사항:

- Python 3.11+
- Bun 1.0+ (channel server를 사용할 때)

설치:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-server.txt -r requirements-pipeline.txt
cp .env.example .env
```

채널 서버까지 사용할 경우:

```bash
cd channel
bun install
cd ..
```

실행:

```bash
./run.sh server   # FastAPI만
./run.sh channel  # Bun webhook만
./run.sh all      # 둘 다
```

기본 주소:

- App: `http://127.0.0.1:8100`
- Docs: `http://127.0.0.1:8100/docs`
- Channel health: `http://127.0.0.1:8788/health`

## Repository Layout

```text
cpet.db/
├── server/                  # FastAPI app, templates, auth, dashboard
├── pipeline/                # Parser + analysis + HTML report generation
├── channel/                 # Bun webhook entrypoint
├── tests/                   # v2 test suite
├── data/                    # runtime DB/workspaces (gitignored)
├── published/               # published HTML reports (gitignored)
├── docs/                    # active specs and operational notes
├── deploy/                  # nginx/systemd deployment notes
├── requirements-server.txt
├── requirements-pipeline.txt
└── run.sh
```

## Main Flow

1. 사용자가 파일과 설명을 업로드합니다.
2. `server/api.py`가 `data/workspaces/<uuid>/raw/`에 저장하고 job을 생성합니다.
3. `channel/webhook.ts`가 Claude Code 세션으로 submission 이벤트를 전달합니다.
4. `python -m pipeline --workspace <path>`가 `analysis.db`와 `report/index.html`을 생성합니다.
5. 리포트가 `published/<slug>/`로 복사되고 대시보드에 노출됩니다.

## Verification

```bash
pytest tests -q
python -m pipeline --help
```

## Docs

- [docs/README.md](./docs/README.md)
- [docs/specs/REBUILD_PLAN.md](./docs/specs/REBUILD_PLAN.md)
- [deploy/README.md](./deploy/README.md)
- [scripts/README.md](./scripts/README.md)

### 커밋 메시지 규칙
- `feat:` 새로운 기능
- `fix:` 버그 수정
- `docs:` 문서 변경
- `refactor:` 코드 리팩토링
- `test:` 테스트 추가/수정
- `chore:` 빌드/설정 변경

## 라이선스

MIT License

## 저장소

GitHub: https://github.com/cyanluna-git/cpet.data
