# CPET Platform Rebuild Plan

> AI-driven multi-artifact CPET ingestion and report publishing platform
>
> Date: 2026-03-21
> Branch: `rebuild/v2` (from `main`, clean start)

## 1. Vision

사용자가 시험 데이터셋(FIT, ZWO, CPET XLSX, Lactate)을 업로드하고 자연어로 테스트 설명을 제출하면, 서버의 Claude Code 세션이 자동으로 데이터를 파싱·분석하여 정적 HTML 리포트를 게시한다.

```
사용자 → 웹 업로드 → FastAPI → Channel webhook → Claude Code 세션
                                                    ↓
                                              pipeline skill 실행
                                              (parse → SQLite → analyze → HTML)
                                                    ↓
                                              cpet.cyanluna.com/report/<slug>/
                                                    ↓
                                              사용자 대시보드에서 확인
```

## 2. Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Backend API** | FastAPI (Python 3.11) | 기존 성숙 코드, async, 업로드/job API |
| **Platform DB** | SQLite (`cpet_platform.db`) | submission, job metadata — 외부 DB 의존 제거 |
| **Analysis DB** | SQLite per submission (`analysis.db`) | 포터블 artifact, Belgium 파이프라인에서 증명 |
| **AI Integration** | Claude Code Channels (MCP) | webhook으로 Claude 세션에 이벤트 push |
| **Channel Server** | Bun + MCP SDK | FastAPI POST → Claude Code 세션 수신 |
| **Frontend** | HTMX + Jinja2 | 빌드 스텝 없음, FastAPI가 직접 서빙 |
| **Report Serving** | Nginx static | `cpet.cyanluna.com/report/<slug>/` |
| **Analysis Core** | Python (pandas, scipy, numpy) | Belgium 파이프라인 일반화 |
| **Server** | Oracle Cloud + cpet.cyanluna.com | demo 서버에 같이 배포 |

### Stack Decisions

**React → HTMX 전환 근거:**
- 필요한 화면이 3개뿐 (업로드, 대시보드, 리포트는 static HTML)
- 별도 빌드/배포 프로세스 제거 — FastAPI 단일 프로세스
- HTMX `hx-trigger="every 3s"`로 job 상태 polling 충분
- 코드량: React ~3,000 lines → HTMX ~500 lines

**SQLite 단일 구조 근거:**
- 사용자 1명, 동시 job 1개, 월 수 건 — PostgreSQL 운영은 과잉
- 플랫폼 DB (`cpet_platform.db`): submissions + jobs 2테이블, WAL 모드로 충분
- 분석 DB (`analysis.db`): per-submission isolation, Belgium 파이프라인에서 증명
- 외부 DB 의존 제거 → Docker/서비스 관리 불필요, 백업은 파일 복사만
- 확장 필요 시 플랫폼 DB만 PostgreSQL로 교체하면 됨 (테이블 2개, 스키마 동일)

**Claude Code Channels 근거:**
- 기존 Claude Code 세션에 외부 이벤트를 push하는 공식 메커니즘
- FastAPI가 HTTP POST → channel server → Claude 세션이 skill 실행
- 별도 SDK/API 없이 MCP 표준 위에서 동작

## 3. Current Assets — What We Keep

### Belgium Pipeline (core, ~3,882 lines)

검증된 5단계 파이프라인. 2명의 피험자(박근윤, 홍창선)에서 성공적으로 실행.

| File | Lines | Role | Reuse |
|------|-------|------|-------|
| `parsers.py` | 626 | ZWO/FIT/COSMED XLSX/Markdown 파싱 | **전체** — 파서 registry로 일반화 |
| `schema.py` | 304 | SQLite 6-table schema + data loader | **전체** — 하드코딩 경로 제거 |
| `analysis.py` | 798 | Lactate threshold, FatMax, VO2max, substrate metabolism | **전체** — DB 경로 파라미터화 |
| `report.py` | 2,075 | Standalone HTML report 생성 | **전체** — 템플릿 일반화 |
| `test_report.py` | 79 | 검증 테스트 | **전체** |

### Backend Services (selective merge)

| Service | Lines | Reuse |
|---------|-------|-------|
| `metabolism_analysis.py` | 1,705 | **선택** — LOESS smoothing, power binning 알고리즘만 추출 |
| `data_validator.py` | 724 | **선택** — QC 로직을 pipeline에 통합 |
| `cosmed_parser.py` | 1,134 | **비교** — Belgium `parsers.py`와 통합, 더 성숙한 에러 핸들링 채택 |

### What We Discard

- Frontend 전체 (React 18 + 14 pages, 13,831 lines)
- Backend API routers (`api/*.py`, 2,198 lines) — 새로 작성
- Auth system (JWT) — v2에서는 단순화 또는 제거
- Backend services: `cohort.py`, `inscyd*.py`, `processed_metabolism.py`
- SQLAlchemy async ORM 모델 — 순수 sqlite3로 교체
- TimescaleDB 의존성 — SQLite per submission으로 대체
- Docker Compose (PostgreSQL + TimescaleDB) — 외부 DB 의존 완전 제거
- Alembic 마이그레이션 — SQL 파일 하나로 대체

## 4. Architecture

### Directory Structure (target)

```
cpet.db/
├── pipeline/                    # Core analysis package (from Belgium)
│   ├── __init__.py
│   ├── parsers/
│   │   ├── __init__.py          # dispatch: extension → parser
│   │   ├── zwo.py               # ZWO XML protocol parser
│   │   ├── fit.py               # FIT binary workout parser
│   │   ├── cosmed.py            # COSMED K5 XLSX parser
│   │   └── lactate.py           # Lactate CSV/MD parser
│   ├── schema.py                # SQLite schema + data loader
│   ├── analysis.py              # All analysis algorithms
│   ├── report.py                # HTML report generator
│   ├── validator.py             # Data quality checks
│   └── cli.py                   # CLI entry point (standalone execution)
│
├── server/                      # FastAPI application
│   ├── main.py                  # FastAPI app + HTMX routes
│   ├── api.py                   # REST endpoints (submit, status, list)
│   ├── db.py                    # Platform SQLite (submissions, jobs)
│   ├── templates/               # Jinja2 + HTMX templates
│   │   ├── base.html
│   │   ├── upload.html
│   │   ├── dashboard.html
│   │   └── partials/            # HTMX partial responses
│   │       ├── job_row.html
│   │       └── job_list.html
│   └── static/
│       └── htmx.min.js
│
├── channel/                     # Claude Code channel server
│   ├── webhook.ts               # Bun MCP channel (receives POST, pushes to Claude)
│   └── package.json
│
├── .claude/
│   └── skills/
│       └── cpet-pipeline/       # Claude Code skill definition
│           └── skill.md
│
├── data/                        # Runtime data (gitignored)
│   ├── cpet_platform.db         # Platform DB (submissions, jobs)
│   └── workspaces/
│       └── <uuid>/
│           ├── raw/             # Uploaded files
│           ├── analysis.db      # SQLite analysis artifact
│           └── report/
│               └── index.html   # Generated report
│
├── published/                   # Nginx serves this (gitignored)
│   └── <slug>/
│       └── index.html
│
├── tests/                       # Test suite
│   ├── test_parsers.py
│   ├── test_analysis.py
│   ├── test_report.py
│   └── fixtures/
│
├── requirements.txt
├── .mcp.json                    # Channel server registration
├── run.sh                       # Dev launcher
└── CLAUDE.md                    # Updated project instructions
```

### Data Flow

```
Phase 1: Upload
  User → POST /api/submit (multipart files + description text)
  → FastAPI saves files to data/workspaces/<uuid>/raw/
  → INSERT INTO cpet_platform.db (submissions + jobs, status='pending')
  → POST http://localhost:8788 {submission_id, workspace_path, description}

Phase 2: Channel Dispatch
  Bun channel server receives POST
  → mcp.notification({
      method: 'notifications/claude/channel',
      params: {
        content: JSON.stringify({submission_id, workspace_path, description}),
        meta: { type: 'new_submission' }
      }
    })
  → Claude Code session receives <channel source="cpet-webhook" type="new_submission">

Phase 3: AI-Assisted Processing (Claude Code skill)
  Claude reads channel event → activates cpet-pipeline skill
  ┌─ Deterministic steps (pipeline/ package):
  │  1. Detect file types in workspace/raw/
  │  2. Parse each file (ZWO → protocol, FIT → workout, XLSX → BxB, MD → lactate)
  │  3. Build SQLite DB (schema.py)
  │  4. Run analysis algorithms (analysis.py)
  │  5. Generate HTML report (report.py)
  │
  ├─ AI-assisted steps (Claude's judgment):
  │  1. Parse natural language description → infer protocol type
  │  2. QC check: flag missing files, anomalous values
  │  3. Generate coach summary (Korean text)
  │  4. Resolve ambiguities in data alignment (FIT ↔ COSMED time sync)
  │
  └─ Publish:
     1. Copy report to published/<slug>/index.html
     2. UPDATE cpet_platform.db jobs SET status='done', report_url='...'

Phase 4: User Views Report
  Dashboard polls GET /api/jobs → sees status='done'
  → Click report link → cpet.cyanluna.com/report/<slug>/
```

### Database Schema

**Platform DB** (`data/cpet_platform.db`) — SQLite, WAL mode:

```sql
CREATE TABLE submissions (
    id TEXT PRIMARY KEY,                 -- UUID (Python uuid4)
    description TEXT,                    -- 자연어 테스트 설명
    file_manifest TEXT,                  -- JSON: [{name, type, size_bytes}]
    workspace_path TEXT,                 -- data/workspaces/<uuid>
    subject_name TEXT,                   -- 피험자 이름 (display only)
    test_date TEXT,                      -- ISO date
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE jobs (
    id TEXT PRIMARY KEY,                 -- UUID
    submission_id TEXT REFERENCES submissions(id),
    status TEXT DEFAULT 'pending',       -- pending | processing | done | failed
    error_message TEXT,
    report_slug TEXT,                    -- published/<slug>
    report_url TEXT,                     -- https://cpet.cyanluna.com/report/<slug>/
    started_at TEXT,
    completed_at TEXT
);
```

**Analysis DB** (`data/workspaces/<uuid>/analysis.db`) — per submission, Belgium 6-table schema:

```
subject, test_session, protocol_stages, workout_data, breath_by_breath, blood_samples
```

## 5. Phased Implementation

### Phase 0: Core Pipeline Extraction

**Goal:** Belgium `analysis/`를 재사용 가능한 `pipeline/` 패키지로 추출

**Source → Target mapping:**

| Belgium 원본 | Target | 변경 사항 |
|-------------|--------|----------|
| `parsers.py` (626L) | `pipeline/parsers/__init__.py` + 모듈별 분리 | `DATA_DIR` 하드코딩 → `path` 파라미터, KST 상수 → config |
| `schema.py` (304L) | `pipeline/schema.py` | `DB_PATH` 하드코딩 → `create_database(workspace, parsed)`, 테이블명 유지 |
| `analysis.py` (798L) | `pipeline/analysis.py` | `DB_PATH` → `run_analysis(db_path)`, 결과를 SQLite `analysis_results` 테이블에 저장 |
| `report.py` (2,075L) | `pipeline/report.py` | `DB_PATH`/`REPORT_PATH` → `generate_report(db_path, output_dir)` |
| — | `pipeline/validator.py` (new) | `backend/app/services/data_validator.py`에서 핵심 QC 로직 추출 |
| — | `pipeline/cli.py` (new) | CLI entry point |

**Tasks:**

- [ ] `pipeline/parsers/` — 파서별 모듈 분리
  - `zwo.py`: `parse_zwo(path: Path) → pd.DataFrame`
  - `fit.py`: `parse_fit(path: Path) → tuple[pd.DataFrame, pd.DataFrame]`
  - `cosmed.py`: `parse_cosmed_xlsx(path: Path) → tuple[pd.DataFrame, dict]`
  - `lactate.py`: `parse_lactate(path: Path) → tuple[pd.DataFrame, dict]`
  - `__init__.py`: 확장자 기반 dispatch — `PARSERS = {'.zwo': parse_zwo, '.fit': parse_fit, ...}`
  - 모든 파서는 optional — 파일이 없으면 빈 DataFrame 반환, 에러 아님
- [ ] `pipeline/schema.py` — `create_database(workspace: Path, parsed_data: dict) → Path`
  - input: `{'zwo': df, 'fit': (workout_df, laps_df), 'cosmed': (bxb_df, info), 'lactate': (blood_df, info)}`
  - output: `workspace/analysis.db` 경로
  - optional 테이블: `blood_samples`는 lactate 없으면 빈 테이블로 생성
  - `protocol_stages`는 ZWO 없으면 빈 테이블로 생성
- [ ] `pipeline/analysis.py` — `run_analysis(db_path: Path) → dict[str, Any]`
  - lactate 데이터 없으면 lactate analysis skip (에러 아님)
  - 결과를 `analysis_results` 테이블에 JSON으로 저장
  - 반환값: `{'fatmax': {...}, 'vo2max': {...}, 'lactate': {...} | None, 'zones': [...]}`
- [ ] `pipeline/report.py` — `generate_report(db_path: Path, output_dir: Path) → Path`
  - `analysis_results` 테이블에서 결과 로드
  - output_dir에 `index.html` 생성
  - lactate 섹션은 데이터 유무에 따라 조건부 렌더링
- [ ] `pipeline/validator.py` — `validate_workspace(workspace: Path) → ValidationResult`
  - 필수 파일 존재 확인: COSMED XLSX (최소 1개 필수)
  - 선택 파일: FIT, ZWO, Lactate (없어도 진행)
  - 데이터 품질: VO2 범위 (100~8000 ml), RQ 범위 (0.6~1.5), HR 범위 (30~220)
  - 반환: `ValidationResult(valid: bool, warnings: list[str], errors: list[str])`
- [ ] `pipeline/cli.py` — `python -m pipeline --workspace /path/`
  - `--workspace`: 필수, raw 파일이 있는 디렉토리
  - `--skip-report`: analysis만 실행, HTML 생성 skip
  - `--verbose`: 상세 로그
  - exit code: 0=성공, 1=validation error, 2=analysis error
- [ ] `tests/test_pipeline.py` — regression test
  - fixture: Belgium 데이터 2건 (박근윤, 홍창선) 복사
  - 파서별 unit test (각 파일 타입)
  - 전체 파이프라인 integration test (workspace → analysis.db → report.html)
  - optional 파일 조합 테스트: COSMED only, COSMED+FIT, COSMED+FIT+ZWO+Lactate

**Acceptance Criteria:**

```bash
# 1. CLI 단독 실행 — 전체 파일셋
python -m pipeline --workspace ./tests/fixtures/park_geunyun/
# → data/workspaces/.../analysis.db (6 tables + analysis_results)
# → data/workspaces/.../report/index.html
# → exit code 0

# 2. CLI 단독 실행 — COSMED only (최소 구성)
python -m pipeline --workspace ./tests/fixtures/cosmed_only/
# → analysis.db (blood_samples, protocol_stages 빈 테이블)
# → report.html (lactate 섹션 없이 렌더링)
# → exit code 0

# 3. regression — 기존 Belgium 리포트와 동일 결과
pytest tests/test_pipeline.py -v
# → FatMax, VO2max, LT1/LT2 값이 기존 리포트와 ±1% 이내
```

**예상:** ~1,500 lines (기존 3,882 lines 리팩터 + validator + cli 추가)

---

### Phase 1: Submission Contract + Platform DB

**Goal:** Platform SQLite + workspace 디렉토리 규약

**Tasks:**

- [ ] `server/db.py` — Platform DB 초기화 + CRUD
  ```python
  # 초기화
  init_db(db_path: Path) → None           # CREATE TABLE IF NOT EXISTS, PRAGMA journal_mode=WAL

  # Submissions
  create_submission(description, files, subject_name, test_date) → str  # returns UUID
  get_submission(id) → dict | None

  # Jobs
  create_job(submission_id) → str          # returns job UUID, status='pending'
  update_job_status(job_id, status, **kwargs) → None  # kwargs: error_message, report_slug, report_url
  list_jobs(status: str | None = None) → list[dict]   # newest first
  get_job(job_id) → dict | None
  get_pending_jobs() → list[dict]          # for recovery after restart
  ```
- [ ] `server/workspace.py` — workspace 생성/관리
  ```python
  create_workspace(submission_id: str, files: list[UploadFile]) → Path
  # → data/workspaces/<submission_id>/raw/<filename> 에 파일 저장
  # → data/workspaces/<submission_id>/report/ 디렉토리 생성
  # → 반환: workspace root path

  get_workspace(submission_id: str) → Path | None
  list_files(workspace: Path) → list[dict]  # [{name, extension, size_bytes}]
  ```
- [ ] `server/schemas.py` — Pydantic models
  ```python
  class SubmissionCreate(BaseModel):
      description: str                      # 자연어 테스트 설명
      subject_name: str = ""                # optional
      test_date: str = ""                   # optional, ISO format

  class JobStatus(BaseModel):
      id: str
      submission_id: str
      status: Literal['pending', 'processing', 'done', 'failed']
      report_url: str | None
      error_message: str | None
      created_at: str
      completed_at: str | None

  class ReportSummary(BaseModel):
      slug: str
      subject_name: str
      test_date: str
      report_url: str
  ```

**Acceptance Criteria:**

```python
# unit test
def test_db_lifecycle():
    init_db(tmp_path / "test.db")
    sid = create_submission("lactate test", [...], "박근윤", "2026-03-20")
    jid = create_job(sid)
    assert get_job(jid)["status"] == "pending"
    update_job_status(jid, "done", report_slug="park-2026-03-20")
    assert get_job(jid)["status"] == "done"
    assert len(get_pending_jobs()) == 0
```

**예상:** ~250 lines

---

### Phase 2: Upload API

**Goal:** 멀티파일 업로드 엔드포인트 + job 생성 + channel dispatch

**Tasks:**

- [ ] `server/main.py` — FastAPI app 초기화
  - lifespan: `init_db()` 호출
  - Jinja2 template mount
  - static files mount (`/static/`)
  - CORS (개발용 localhost)
- [ ] `server/api.py` — REST endpoints
  ```
  POST /api/submit
    Input:  multipart/form-data — files[]: UploadFile[], description: str, subject_name?: str, test_date?: str
    Flow:   validate extensions → create_workspace → create_submission → create_job → POST channel webhook
    Output: 201 {"job_id": "...", "status": "pending"}
    Errors: 400 (no files), 400 (invalid extension), 413 (file too large)

  GET /api/jobs
    Input:  ?status=pending|processing|done|failed (optional)
    Output: 200 [JobStatus, ...]

  GET /api/jobs/{job_id}
    Output: 200 JobStatus
    Errors: 404

  GET /api/jobs/partial
    Output: HTML partial (job_list.html) — HTMX용
    Header: HX-Request 확인
  ```
- [ ] 파일 검증
  - 허용 확장자: `.fit`, `.zwo`, `.xlsx`, `.md`, `.csv`
  - 최대 파일 크기: 50MB per file
  - 최소 1개 `.xlsx` (COSMED) 필수
- [ ] Channel webhook dispatch
  ```python
  async def notify_channel(submission_id: str, workspace: Path, description: str, files: list[dict]):
      payload = {"submission_id": submission_id, "workspace_path": str(workspace),
                 "description": description, "files": files}
      async with httpx.AsyncClient() as client:
          try:
              await client.post("http://127.0.0.1:8788", json=payload, timeout=5.0)
          except httpx.ConnectError:
              logger.warning("Channel server not reachable — job will wait for manual processing")
  ```
  - Channel 서버 미응답 시 job은 pending 유지 (에러 아님, 나중에 수동 처리 가능)

**Acceptance Criteria:**

```bash
# 1. 업로드 성공
curl -X POST http://localhost:8100/api/submit \
  -F "files=@test.xlsx" -F "files=@test.fit" \
  -F "description=Belgium lactate test" \
  -F "subject_name=박근윤"
# → 201 {"job_id": "...", "status": "pending"}
# → data/workspaces/<uuid>/raw/test.xlsx 존재
# → data/workspaces/<uuid>/raw/test.fit 존재

# 2. 확장자 거부
curl -X POST http://localhost:8100/api/submit -F "files=@test.exe"
# → 400 {"error": "invalid file extension: .exe"}

# 3. COSMED 없이 제출
curl -X POST http://localhost:8100/api/submit -F "files=@test.fit"
# → 400 {"error": "at least one .xlsx (COSMED) file required"}

# 4. job 목록 조회
curl http://localhost:8100/api/jobs
# → 200 [{...}, ...]
```

**예상:** ~400 lines

---

### Phase 3: Channel Webhook Server

**Goal:** FastAPI POST → Claude Code 세션에 이벤트 전달

**Tasks:**

- [ ] `channel/webhook.ts` — Bun MCP channel server
  ```typescript
  #!/usr/bin/env bun
  import { Server } from '@modelcontextprotocol/sdk/server/index.js'
  import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'

  const mcp = new Server(
    { name: 'cpet-webhook', version: '0.1.0' },
    {
      capabilities: { experimental: { 'claude/channel': {} } },
      instructions: `You are a CPET analysis assistant running on a server.
        Events arrive as <channel source="cpet-webhook" type="new_submission">.
        Content is JSON: {submission_id, workspace_path, description, files: [{name, extension}]}.
        When you receive this event:
        1. Read the description to understand the test type
        2. Run: python -m pipeline --workspace {workspace_path}
        3. If successful, copy report to published/{slug}/ and update job status
        4. If failed, update job status with error message
        Use the cpet-pipeline skill for detailed instructions.`,
    },
  )

  await mcp.connect(new StdioServerTransport())

  const PORT = parseInt(process.env.CPET_CHANNEL_PORT || '8788')

  Bun.serve({
    port: PORT,
    hostname: '127.0.0.1',
    async fetch(req) {
      if (req.method === 'GET' && new URL(req.url).pathname === '/health') {
        return new Response('ok')
      }
      if (req.method !== 'POST') {
        return new Response('method not allowed', { status: 405 })
      }
      const body = await req.text()
      await mcp.notification({
        method: 'notifications/claude/channel',
        params: { content: body, meta: { type: 'new_submission' } },
      })
      return new Response('ok')
    },
  })
  ```
- [ ] `channel/package.json` — `@modelcontextprotocol/sdk` 의존성
- [ ] `.mcp.json` — channel server 등록
  ```json
  { "mcpServers": { "cpet-webhook": { "command": "bun", "args": ["channel/webhook.ts"] } } }
  ```
- [ ] `GET /health` — channel 서버 상태 확인 (FastAPI에서 health check 용도)

**Acceptance Criteria:**

```bash
# 1. channel 서버 단독 실행
bun channel/webhook.ts  # (MCP 연결 없이 HTTP만 테스트)

# 2. health check
curl http://127.0.0.1:8788/health
# → 200 "ok"

# 3. webhook 전달 (Claude 세션 연결 상태에서)
curl -X POST http://127.0.0.1:8788 \
  -d '{"submission_id":"test-123","workspace_path":"/tmp/test","description":"lactate test"}'
# → 200 "ok"
# → Claude Code 터미널에 <channel source="cpet-webhook"> 이벤트 수신
```

**예상:** ~100 lines

---

### Phase 4: Claude Code Pipeline Skill

**Goal:** Channel 이벤트 → pipeline 실행 → 리포트 게시 → job 상태 업데이트

**Tasks:**

- [ ] `.claude/skills/cpet-pipeline/skill.md` — skill 정의
  ```markdown
  ---
  name: cpet-pipeline
  description: Process CPET submission data and generate analysis report
  ---

  When you receive a <channel source="cpet-webhook" type="new_submission"> event:

  ## Step 1: Parse event
  Parse the JSON content: {submission_id, workspace_path, description, files}

  ## Step 2: Update job status
  ```bash
  python -c "
  from server.db import update_job_status, get_job_by_submission
  job = get_job_by_submission('$SUBMISSION_ID')
  update_job_status(job['id'], 'processing')
  "
  ```

  ## Step 3: Understand the test
  Read the description to determine:
  - Protocol type: lactate threshold / VO2max / submaximal / other
  - Special notes: FTP, estimated thresholds, test conditions
  - Missing data: check files list vs what's expected for this protocol

  ## Step 4: Run pipeline
  ```bash
  python -m pipeline --workspace {workspace_path} --verbose
  ```
  If exit code != 0, update job as failed with the error output.

  ## Step 5: Quality review
  Read the generated report HTML briefly. Check:
  - FatMax value is physiologically reasonable (0.2~1.2 g/min)
  - VO2max is within expected range for the subject
  - Charts have data points (not empty)

  ## Step 6: Publish
  Generate slug: {subject_name}-{test_date} (slugified)
  ```bash
  mkdir -p published/{slug}
  cp {workspace_path}/report/index.html published/{slug}/index.html
  ```

  ## Step 7: Update job
  ```bash
  python -c "
  from server.db import update_job_status, get_job_by_submission
  job = get_job_by_submission('$SUBMISSION_ID')
  update_job_status(job['id'], 'done',
                    report_slug='{slug}',
                    report_url='https://cpet.cyanluna.com/report/{slug}/')
  "
  ```
  ```
- [ ] `server/db.py`에 `get_job_by_submission(submission_id)` 추가
- [ ] Slug 생성 규칙: `{subject_name}-{YYYYMMDD}` (한글 → romanize, 공백 → dash, 소문자)
  - 충돌 시: `-2`, `-3` suffix 추가
- [ ] Error handling: pipeline 실패 시
  ```python
  update_job_status(job_id, 'failed', error_message=stderr_output[:500])
  ```

**Acceptance Criteria:**

```
# Claude Code 세션에서 channel 이벤트 수신 후:
# 1. job status가 pending → processing → done 으로 전이
# 2. published/{slug}/index.html 파일 생성
# 3. cpet_platform.db의 job.report_url에 URL 기록
# 4. pipeline 실패 시 job.status='failed', job.error_message에 에러 기록
```

**예상:** ~200 lines

---

### Phase 5: Nginx Report Publishing

**Goal:** `cpet.cyanluna.com/report/<slug>/` 정적 서빙

**Tasks:**

- [ ] Nginx server block
  ```nginx
  server {
      server_name cpet.cyanluna.com;

      # HTMX app (FastAPI)
      location / {
          proxy_pass http://127.0.0.1:8100;
          proxy_set_header Host $host;
          proxy_set_header X-Real-IP $remote_addr;
      }

      # Static reports
      location /report/ {
          alias /home/ubuntu/cpet.db/published/;
          index index.html;
          try_files $uri $uri/ =404;
          add_header Cache-Control "public, max-age=3600";
      }

      # SSL (Let's Encrypt)
      listen 443 ssl;
      ssl_certificate /etc/letsencrypt/live/cpet.cyanluna.com/fullchain.pem;
      ssl_certificate_key /etc/letsencrypt/live/cpet.cyanluna.com/privkey.pem;
  }
  ```
- [ ] `published/` 디렉토리 생성 (gitignored)
- [ ] `.gitignore` 업데이트: `data/`, `published/`

**Acceptance Criteria:**

```bash
# 1. 리포트 접근
curl -I https://cpet.cyanluna.com/report/park-geunyun-20260320/
# → 200 OK, Content-Type: text/html

# 2. 없는 리포트
curl -I https://cpet.cyanluna.com/report/nonexistent/
# → 404

# 3. 업로드 페이지 접근
curl -I https://cpet.cyanluna.com/
# → 200 OK (FastAPI proxied)
```

**예상:** config only (~30 lines)

---

### Phase 6: HTMX Dashboard

**Goal:** 업로드 + 상태 조회 + 리포트 접근 UI

**Tasks:**

- [ ] `server/templates/base.html` — 공통 레이아웃
  - Tailwind CSS (CDN)
  - htmx.min.js (CDN 또는 static)
  - 네비게이션: 업로드 | 대시보드
  - 한국어 기본
- [ ] `server/templates/upload.html` — 업로드 페이지
  ```html
  <form hx-post="/api/submit"
        hx-encoding="multipart/form-data"
        hx-target="#result"
        hx-indicator="#spinner"
        hx-on::after-request="if(event.detail.successful) window.location='/dashboard'">

    <!-- 파일 드롭존 -->
    <div id="dropzone">
      <input type="file" name="files" multiple accept=".fit,.zwo,.xlsx,.md,.csv">
      <p>FIT, ZWO, XLSX(COSMED), MD/CSV(Lactate) 파일을 선택하세요</p>
      <p>COSMED XLSX는 필수입니다</p>
    </div>

    <!-- 테스트 설명 -->
    <textarea name="description" required
      placeholder="어떤 테스트를 수행했나요?&#10;예: Belgium 락테이트 테스트, FTP 253W 기준, 3블록 프로토콜"></textarea>

    <!-- 피험자 정보 (optional) -->
    <input type="text" name="subject_name" placeholder="피험자 이름 (선택)">
    <input type="date" name="test_date">

    <button type="submit">분석 요청</button>
    <div id="spinner" class="htmx-indicator">처리 중...</div>
  </form>
  <div id="result"></div>
  ```
- [ ] `server/templates/dashboard.html` — 대시보드
  ```html
  <div hx-get="/api/jobs/partial"
       hx-trigger="load, every 3s"
       hx-swap="innerHTML">
    <!-- 초기 로딩 -->
  </div>
  ```
  - 상태 표시: pending(노랑), processing(파랑 pulse), done(초록), failed(빨강)
  - done → 리포트 링크 (새 탭)
  - failed → 에러 메시지 표시
  - 빈 상태: "아직 제출된 분석이 없습니다"
- [ ] `server/templates/partials/job_list.html` — HTMX partial
  ```html
  {% for job in jobs %}
  <tr>
    <td>{{ job.subject_name or '미지정' }}</td>
    <td>{{ job.test_date or '-' }}</td>
    <td><span class="badge badge-{{ job.status }}">{{ job.status }}</span></td>
    <td>
      {% if job.status == 'done' %}
        <a href="{{ job.report_url }}" target="_blank">리포트 보기</a>
      {% elif job.status == 'failed' %}
        <span title="{{ job.error_message }}">실패</span>
      {% else %}
        —
      {% endif %}
    </td>
    <td>{{ job.created_at }}</td>
  </tr>
  {% endfor %}
  {% if not jobs %}
  <tr><td colspan="5">아직 제출된 분석이 없습니다</td></tr>
  {% endif %}
  ```
- [ ] `server/main.py`에 페이지 라우트 추가
  ```python
  @app.get("/", response_class=HTMLResponse)
  @app.get("/upload", response_class=HTMLResponse)
  @app.get("/dashboard", response_class=HTMLResponse)
  ```

**Acceptance Criteria:**

```
# 1. 업로드 페이지 렌더링
GET / → 200, 파일 input + textarea + submit 버튼 표시

# 2. 파일 업로드 → 대시보드 리다이렉트
POST /api/submit (with files) → 201 → 브라우저가 /dashboard로 이동

# 3. 대시보드 polling
GET /dashboard → job 목록 표시, 3초마다 자동 갱신
job status 변경 시 UI 즉시 반영 (pending → processing → done)

# 4. 리포트 링크
done 상태 job의 "리포트 보기" 클릭 → 새 탭에서 report HTML 열림

# 5. 모바일
iPhone Safari에서 업로드/대시보드 정상 렌더링
```

**예상:** ~500 lines

---

### Phase 7: E2E Test Suite

**Goal:** 전체 파이프라인을 처음부터 끝까지 자동 검증

**Tasks:**

- [ ] `tests/e2e/test_full_pipeline.py` — 업로드 → 리포트 생성 전체 흐름
  ```python
  class TestFullPipeline:
      """Channel/AI 없이 deterministic 경로만 테스트"""

      def test_upload_creates_workspace(self, client, fixtures):
          """파일 업로드 → workspace 생성 → job pending"""
          resp = client.post("/api/submit", files=fixtures["park_geunyun"],
                            data={"description": "Belgium lactate test"})
          assert resp.status_code == 201
          job = resp.json()
          assert job["status"] == "pending"
          workspace = Path(get_submission(job["submission_id"])["workspace_path"])
          assert (workspace / "raw").exists()
          assert len(list((workspace / "raw").iterdir())) == 4  # fit, zwo, xlsx, md

      def test_pipeline_cli_produces_report(self, fixtures):
          """pipeline CLI → analysis.db + report.html"""
          result = subprocess.run(
              ["python", "-m", "pipeline", "--workspace", str(fixtures["workspace"])],
              capture_output=True, text=True)
          assert result.returncode == 0
          assert (fixtures["workspace"] / "analysis.db").exists()
          assert (fixtures["workspace"] / "report" / "index.html").exists()

      def test_report_html_valid(self, fixtures):
          """생성된 report.html이 핵심 데이터를 포함"""
          html = (fixtures["workspace"] / "report" / "index.html").read_text()
          assert "FatMax" in html
          assert "VO2max" in html
          assert "chart-data" in html  # embedded JSON dataset

      def test_job_status_lifecycle(self, client, fixtures):
          """job status: pending → processing → done"""
          job_id = create_test_job(client, fixtures)
          update_job_status(job_id, "processing")
          assert get_job(job_id)["status"] == "processing"
          update_job_status(job_id, "done", report_slug="test-slug")
          assert get_job(job_id)["status"] == "done"
          assert get_job(job_id)["report_slug"] == "test-slug"

      def test_job_failure_records_error(self, client, fixtures):
          """pipeline 실패 → job.status=failed + error_message"""
          job_id = create_test_job(client, fixtures)
          update_job_status(job_id, "failed", error_message="parse error: invalid COSMED format")
          job = get_job(job_id)
          assert job["status"] == "failed"
          assert "parse error" in job["error_message"]
  ```
- [ ] `tests/e2e/test_api_validation.py` — API 입력 검증
  ```python
  class TestAPIValidation:
      def test_no_files_rejected(self, client):
          resp = client.post("/api/submit", data={"description": "test"})
          assert resp.status_code == 400

      def test_invalid_extension_rejected(self, client):
          resp = client.post("/api/submit",
                            files=[("files", ("test.exe", b"data", "application/octet-stream"))],
                            data={"description": "test"})
          assert resp.status_code == 400

      def test_no_cosmed_rejected(self, client):
          resp = client.post("/api/submit",
                            files=[("files", ("test.fit", b"data", "application/octet-stream"))],
                            data={"description": "test"})
          assert resp.status_code == 400

      def test_oversized_file_rejected(self, client):
          big_file = b"x" * (50 * 1024 * 1024 + 1)  # 50MB + 1 byte
          resp = client.post("/api/submit",
                            files=[("files", ("big.xlsx", big_file, "application/octet-stream"))],
                            data={"description": "test"})
          assert resp.status_code == 413
  ```
- [ ] `tests/e2e/test_htmx_responses.py` — HTMX partial 응답 검증
  ```python
  class TestHTMXResponses:
      def test_job_partial_returns_html(self, client):
          """GET /api/jobs/partial → HTML partial (not JSON)"""
          resp = client.get("/api/jobs/partial", headers={"HX-Request": "true"})
          assert resp.status_code == 200
          assert "text/html" in resp.headers["content-type"]

      def test_dashboard_page_renders(self, client):
          resp = client.get("/dashboard")
          assert resp.status_code == 200
          assert "hx-get" in resp.text  # HTMX attribute 존재

      def test_upload_page_renders(self, client):
          resp = client.get("/upload")
          assert resp.status_code == 200
          assert 'hx-post="/api/submit"' in resp.text
  ```
- [ ] `tests/e2e/test_regression.py` — Belgium 데이터 regression
  ```python
  class TestBelgiumRegression:
      """기존 Belgium 파이프라인과 동일 결과를 보장"""

      TOLERANCE = 0.01  # ±1%

      def test_park_geunyun_fatmax(self, park_results):
          assert abs(park_results["fatmax"]["power_w"] - EXPECTED_FATMAX_POWER) / EXPECTED_FATMAX_POWER < self.TOLERANCE

      def test_park_geunyun_vo2max(self, park_results):
          assert abs(park_results["vo2max"]["vo2_ml"] - EXPECTED_VO2MAX) / EXPECTED_VO2MAX < self.TOLERANCE

      def test_park_geunyun_lt1(self, park_results):
          lt1 = park_results["lactate"]["lt1_fixed_power_w"]
          assert abs(lt1 - EXPECTED_LT1) / EXPECTED_LT1 < self.TOLERANCE

      def test_hong_changsun_full(self, hong_results):
          """두 번째 피험자도 동일 정확도"""
          assert hong_results["fatmax"]["power_w"] > 0
          assert hong_results["vo2max"]["vo2_ml"] > 0
  ```
- [ ] `tests/conftest.py` — 공유 fixtures
  ```python
  @pytest.fixture
  def client():
      """FastAPI TestClient with temp platform DB"""
      with tempfile.TemporaryDirectory() as tmp:
          os.environ["CPET_DATA_DIR"] = tmp
          from server.main import app
          init_db(Path(tmp) / "cpet_platform.db")
          yield TestClient(app)

  @pytest.fixture
  def fixtures():
      """Belgium test data fixtures"""
      return {
          "park_geunyun": FIXTURE_DIR / "park_geunyun",
          "hong_changsun": FIXTURE_DIR / "hong_changsun",
          "cosmed_only": FIXTURE_DIR / "cosmed_only",
      }
  ```
- [ ] `tests/fixtures/` — 테스트 데이터 준비
  - `park_geunyun/raw/`: .fit, .zwo, .xlsx, .md 복사 (Belgium 원본)
  - `hong_changsun/raw/`: .fit, .xlsx, .md 복사
  - `cosmed_only/raw/`: .xlsx만 (최소 구성 테스트)

**Acceptance Criteria:**

```bash
# 전체 테스트 스위트 통과
pytest tests/ -v --tb=short

# 결과 요약:
# tests/test_pipeline.py         — pipeline 단위 테스트 (파서, 분석, 리포트)
# tests/e2e/test_full_pipeline.py — 업로드 → 리포트 전체 흐름
# tests/e2e/test_api_validation.py — API 입력 검증
# tests/e2e/test_htmx_responses.py — HTMX partial 응답
# tests/e2e/test_regression.py   — Belgium 데이터 회귀 테스트
#
# 전부 green, 0 failures
```

**예상:** ~500 lines

## 6. Deployment (Oracle Cloud)

```
Oracle VM (cpet.cyanluna.com)
├── Nginx (reverse proxy + static serving)
│   ├── / → FastAPI (port 8100)
│   └── /report/ → published/ directory
│
├── FastAPI (systemd service)
│   ├── Upload API + HTMX template serving
│   ├── Platform DB: data/cpet_platform.db
│   └── POST to channel webhook on new submission
│
├── Claude Code (persistent tmux session)
│   ├── claude --dangerously-load-development-channels server:cpet-webhook
│   ├── Channel server (Bun, port 8788)
│   └── Skills: cpet-pipeline
│
└── data/
    ├── cpet_platform.db              # Platform metadata
    ├── workspaces/<uuid>/analysis.db # Per-submission analysis
    └── published/<slug>/index.html   # Static reports
```

**No external DB dependency.** 전체 시스템이 파일시스템 위에서 동작.
백업: `rsync data/ backup/` 한 줄이면 끝.

### Process Management

```bash
# systemd: FastAPI
sudo systemctl start cpet-api

# tmux: Claude Code (needs interactive session)
tmux new-session -d -s claude-cpet \
  'cd /path/to/cpet.db && claude --dangerously-load-development-channels server:cpet-webhook'

# No database service to manage
```

## 7. Migration Strategy

### Branch Plan

```
main (current, 25k+ lines)
  └── rebuild/v2 (new branch, clean start)
        ├── Keep: pipeline/ (from Belgium analysis/)
        ├── Keep: docs/ (reports, specs, test data)
        ├── Keep: .claude/ (rules, skills)
        ├── Remove: frontend/ (React)
        ├── Remove: backend/ (old FastAPI)
        └── New: server/, channel/, templates/
```

### Step-by-Step

1. `git checkout main && git checkout -b rebuild/v2`
2. Remove: `frontend/`, `backend/` (old code)
3. Move: `docs/.../analysis/` → `pipeline/` (generalize)
4. Add: `server/`, `channel/`, `templates/`
5. Update: `CLAUDE.md`, `run.sh`, `requirements.txt`
6. Regression test: Belgium 데이터로 pipeline CLI 검증
7. Deploy to Oracle

## 8. Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Channels가 research preview | Claude 세션이 죽으면 job 멈춤 | Worker fallback: channel 없이도 CLI로 직접 pipeline 실행 가능하게 |
| Claude 세션 장시간 안정성 | 메모리 누수, 연결 끊김 | systemd watchdog + tmux auto-restart |
| 파일 조합 다양성 | ZWO 없는 테스트, lactate 없는 테스트 | pipeline이 optional 파일을 graceful하게 처리 |
| Oracle VM 리소스 | 동시 분석 시 CPU/메모리 | 한 번에 1 job만 처리 (sequential queue) |
| HTMX 학습 곡선 | 처음 사용 | UI가 단순해서 기본 패턴만으로 충분 |

## 9. Success Criteria

- [ ] `python -m pipeline --workspace ./path/` 로 CLI 단독 실행 성공
- [ ] 웹 업로드 → 3분 이내 리포트 게시
- [ ] Belgium 테스트 데이터 2건 (박근윤, 홍창선) regression pass (±1%)
- [ ] COSMED only 최소 구성에서도 리포트 생성 성공
- [ ] `cpet.cyanluna.com/report/<slug>/` 에서 리포트 열람 가능
- [ ] HTMX 대시보드에서 job 상태 실시간 확인 가능 (3초 polling)
- [ ] Channel 서버 미응답 시 job이 pending 유지 (graceful degradation)
- [ ] `pytest tests/ -v` 전체 green (unit + e2e + regression)

## 10. Code Budget

| Component | New Lines | Reused Lines |
|-----------|-----------|-------------|
| `pipeline/` | ~1,500 (refactor) | ~3,882 (Belgium) |
| `server/` (API + db.py + workspace.py) | ~650 | — |
| `channel/` | ~100 | — |
| `templates/` | ~500 | — |
| Skills/config | ~200 | — |
| `tests/` (unit + e2e + regression) | ~800 | ~79 |
| **Total** | **~3,750** | **~3,961** |

Total deployable codebase: **~7,700 lines** (현재 25k+ → 69% 감소)
External dependencies: **0 services** (no PostgreSQL, no Docker, no Redis)
Test coverage: pipeline unit + API validation + HTMX responses + Belgium regression
