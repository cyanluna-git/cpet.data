"""
server.api — REST endpoints for CPET submission and job management.

Endpoints:
    POST /api/submit       — Upload files and create a new job
    GET  /api/jobs          — List jobs (optional status filter)
    GET  /api/jobs/partial  — HTMX partial for job list
    GET  /api/jobs/{job_id} — Get a single job by ID
"""

import logging
import json
import sqlite3
import uuid
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import threading

import httpx
from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from server.db import (
    create_job,
    create_submission,
    get_job,
    get_job_by_submission,
    get_submission,
    list_jobs,
    list_jobs_by_user,
    update_job_status,
)
from server.publish import publish_report
from server.workspace import create_workspace, list_files

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {".fit", ".zwo", ".xlsx", ".md", ".csv"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

REPORT_DATA_RE = re.compile(
    r'<script id="report-data" type="application/json">(.*?)</script>',
    re.DOTALL,
)
SUBJECT_NAME_ALIASES = {
    "Geunyun Park": "박근윤",
    "changsun Hong": "홍창선",
    "Changsun Hong": "홍창선",
    "Daesoon Kim": "김대순",
}


# ── Dependencies ─────────────────────────────────────────────────────


def get_db_path(request: Request) -> Path:
    """Resolve platform database path from app state."""
    return request.app.state.db_path


def get_data_dir(request: Request) -> Path:
    """Resolve data directory from app state."""
    return request.app.state.data_dir


def get_channel_url(request: Request) -> str:
    """Resolve channel webhook URL from app state."""
    return request.app.state.channel_url


def get_published_dir(request: Request) -> Path:
    """Resolve published report directory from app state."""
    published_dir = getattr(request.app.state, "published_dir", None)
    if published_dir is not None:
        return Path(published_dir)
    return Path(__file__).resolve().parent.parent / "published"


def _describe_generation_method(report_payload: dict | None) -> str:
    """Return a compact dashboard label for how the report was generated."""
    if not report_payload:
        return "알 수 없음"

    meta = report_payload.get("meta") or {}
    if meta.get("analysis_method"):
        return str(meta["analysis_method"])

    analysis = report_payload.get("analysis") or {}
    suitability = analysis.get("suitability") or {}

    if suitability:
        return "CPET 프로토콜 보정"
    if analysis:
        return "기본 CPET"
    return "알 수 없음"


def _describe_report_version(report_slug: str | None) -> str:
    """Convert a slug suffix into a compact dashboard version label."""
    if not report_slug:
        return "—"
    parts = str(report_slug).split("-")
    if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) <= 2:
        return f"v{parts[-1]}"
    return "v1"


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    """Best-effort parse of stored ISO timestamps."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _describe_processing_state(started_at: str | None) -> tuple[str, str, int]:
    """Return stage copy for in-progress jobs based on elapsed seconds."""
    started_dt = _parse_iso_timestamp(started_at)
    if started_dt is None:
        return ("워크스페이스 준비 중", "수집 파일과 분석 컨텍스트를 정렬하고 있습니다.", 0)

    elapsed = max(
        0,
        int((datetime.now(timezone.utc) - started_dt.astimezone(timezone.utc)).total_seconds()),
    )
    if elapsed < 12:
        return ("호흡 데이터 정렬 중", "COSMED, FIT, lactate 파일을 하나의 분석 세션으로 결합하고 있습니다.", elapsed)
    if elapsed < 26:
        return ("젖산·가스교환 지표 추정 중", "LT1, LT2, FatMax, VO2max 후보를 보수적으로 재평가하고 있습니다.", elapsed)
    if elapsed < 45:
        return ("리포트 빌드 중", "차트, 지표 설명, 신뢰도 레이어를 HTML 리포트로 조립하고 있습니다.", elapsed)
    return ("발행 패키징 중", "최종 리포트 URL과 대시보드 상태를 마감하고 있습니다.", elapsed)


def _report_identity(index_file: Path) -> tuple[int, str]:
    """Return a cheap identity for an HTML report file."""
    content = index_file.read_bytes()
    return (len(content), hashlib.sha256(content).hexdigest())


def _find_published_slug_for_report(report_index: Path, published_dir: Path) -> str | None:
    """Find a published slug whose index.html matches the generated workspace report."""
    if not report_index.is_file() or not published_dir.exists():
        return None

    report_identity = _report_identity(report_index)
    for report_dir in sorted(published_dir.iterdir()):
        if not report_dir.is_dir():
            continue
        published_index = report_dir / "index.html"
        if not published_index.is_file():
            continue
        try:
            if _report_identity(published_index) == report_identity:
                return report_dir.name
        except Exception:
            continue
    return None


def _extract_report_metadata(index_file: Path) -> dict[str, str]:
    """Read a published report and extract dashboard metadata."""
    subject_name = ""
    test_date = ""
    analysis_method = "알 수 없음"

    try:
        html = index_file.read_text(encoding="utf-8")
        match = REPORT_DATA_RE.search(html)
        if match:
            payload = json.loads(match.group(1))
            subject_name = (payload.get("subject") or {}).get("name") or ""
            test_date = (payload.get("session") or {}).get("test_date") or ""
            analysis_method = _describe_generation_method(payload)
    except Exception:
        pass

    return {
        "subject_name": SUBJECT_NAME_ALIASES.get(subject_name, subject_name),
        "test_date": test_date,
        "analysis_method": analysis_method,
    }


def _reconcile_job_artifacts(
    request: Request,
    job: dict,
    submission: dict | None,
) -> dict:
    """Promote non-done jobs to done once their report artifacts exist."""
    if submission is None:
        return job

    if str(job.get("status") or "") == "done" and job.get("report_slug"):
        return job

    workspace = Path(str(submission.get("workspace_path") or ""))
    report_index = workspace / "report" / "index.html"
    if not report_index.is_file():
        return job

    published_dir = get_published_dir(request)
    slug = _find_published_slug_for_report(report_index, published_dir)
    metadata = _extract_report_metadata(report_index)

    if slug is None:
        subject_name = (
            str(submission.get("subject_name") or "")
            or metadata.get("subject_name")
            or "subject"
        )
        test_date = (
            str(submission.get("test_date") or "")
            or metadata.get("test_date")
            or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        )
        slug = publish_report(workspace, subject_name, test_date, published_dir)

    update_job_status(
        get_db_path(request),
        str(job["id"]),
        "done",
        error_message=None,
        report_slug=slug,
        report_url=f"/report/{slug}/",
    )
    refreshed = get_job(get_db_path(request), str(job["id"]))
    return refreshed or job


def _build_channel_payload(job: dict, submission: dict) -> dict:
    """Reconstruct the webhook payload used for automatic analysis."""
    return {
        "submission_id": submission["id"],
        "job_id": job["id"],
        "workspace_path": submission["workspace_path"],
        "description": submission.get("description") or "",
        "files": submission.get("file_manifest") or [],
    }


def _run_pipeline_job(
    db_path: Path,
    job_id: str,
    workspace_path: str,
    subject_name: str,
    test_date: str,
    publish_dir: Path,
    report_url_prefix: str = "/report",
) -> None:
    """Run the standalone pipeline and mark the job done/failed."""
    try:
        from pipeline.analysis import run_analysis
        from pipeline.parsers import parse_workspace
        from pipeline.report import generate_report
        from pipeline.schema import create_database

        workspace = Path(workspace_path).resolve()
        parsed = parse_workspace(workspace)
        analysis_db = create_database(workspace, parsed)
        run_analysis(analysis_db)
        generate_report(analysis_db, workspace / "report")

        safe_subject = subject_name or "subject"
        safe_test_date = test_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        slug = publish_report(workspace, safe_subject, safe_test_date, publish_dir)
        update_job_status(
            db_path,
            job_id,
            "done",
            error_message=None,
            report_slug=slug,
            report_url=f"{report_url_prefix.rstrip('/')}/{slug}/",
        )
    except Exception as exc:
        logger.exception("Manual analysis fallback failed for job %s", job_id)
        update_job_status(
            db_path,
            job_id,
            "failed",
            error_message=str(exc)[:500],
            report_slug=None,
            report_url=None,
        )


def _start_fallback_analysis(
    db_path: Path,
    job: dict,
    submission: dict,
    publish_dir: Path,
) -> threading.Thread:
    """Run fallback analysis in a daemon thread so the dashboard can keep polling."""
    thread = threading.Thread(
        target=_run_pipeline_job,
        kwargs={
            "db_path": db_path,
            "job_id": str(job["id"]),
            "workspace_path": str(submission["workspace_path"]),
            "subject_name": str(submission.get("subject_name") or ""),
            "test_date": str(submission.get("test_date") or ""),
            "publish_dir": publish_dir,
        },
        daemon=True,
        name=f"cpet-job-{str(job['id'])[:8]}",
    )
    thread.start()
    return thread


def _extract_file_tags(sub: dict | None) -> list[str]:
    """Extract file type tags from a submission's file_manifest."""
    if not sub:
        return []
    manifest = sub.get("file_manifest")
    if not manifest:
        return []
    if isinstance(manifest, str):
        try:
            manifest = json.loads(manifest)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(manifest, list):
        return []

    tag_map = {
        "fit": "FIT",
        "zwo": "ZWO",
        "xlsx": "CPET",
        "md": "Lactate",
        "csv": "Lactate",
        "pdf": "INSCYD",
    }
    seen: set[str] = set()
    tags: list[str] = []
    for f in manifest:
        ext = str(f.get("extension", "") or f.get("name", "").rsplit(".", 1)[-1]).lower()
        tag = tag_map.get(ext)
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def _infer_file_tags_from_slug(slug: str, analysis_method: str) -> list[str]:
    """Infer file type tags from report slug and analysis method."""
    tags = []
    if "inscyd" in slug.lower() or "inscyd" in analysis_method.lower():
        tags.append("INSCYD")
    else:
        tags.append("CPET")
    return tags


def _scan_published_reports(published_dir: Path) -> list[dict]:
    """Scan published/ and build dashboard-like rows for standalone reports."""
    if not published_dir.exists():
        return []

    rows: list[dict] = []
    for report_dir in sorted(published_dir.iterdir()):
        if not report_dir.is_dir():
            continue
        index_file = report_dir / "index.html"
        if not index_file.is_file():
            continue

        metadata = _extract_report_metadata(index_file)
        subject_name = metadata["subject_name"] or report_dir.name
        test_date = metadata["test_date"]

        modified_at_dt = datetime.fromtimestamp(
            index_file.stat().st_mtime,
            tz=timezone.utc,
        )
        modified_at = modified_at_dt.isoformat()

        rows.append(
            {
                "id": report_dir.name,
                "display_id": hashlib.md5(report_dir.name.encode("utf-8")).hexdigest()[:8],
                "submission_id": "",
                "status": "done",
                "error_message": None,
                "report_slug": report_dir.name,
                "report_url": f"/report/{report_dir.name}/",
                "started_at": None,
                "completed_at": modified_at,
                "created_at": modified_at,
                "created_at_display": modified_at_dt.strftime("%Y-%m-%d %H:%M"),
                "subject_name": subject_name,
                "test_date": test_date,
                "analysis_method": metadata["analysis_method"],
                "report_version": _describe_report_version(report_dir.name),
                "is_latest": False,
                "file_tags": _infer_file_tags_from_slug(report_dir.name, metadata["analysis_method"]),
            }
        )

    return rows


def _list_dashboard_entries(
    request: Request, status: str | None = None, user_id: str | None = None,
) -> list[dict]:
    """Merge DB jobs with standalone published reports for dashboard views.

    When user_id is provided, only jobs whose submission belongs to that user
    are returned (the published-directory scan is skipped).
    """
    db_path = get_db_path(request)
    if user_id:
        jobs = list_jobs_by_user(db_path, user_id, status=status)
    else:
        jobs = list_jobs(db_path, status=status)

    enriched: list[dict] = []
    job_slugs: set[str] = set()
    published_dir = get_published_dir(request)
    for job in jobs:
        sub = get_submission(db_path, job["submission_id"])
        job = _reconcile_job_artifacts(request, job, sub)
        report_slug = str(job.get("report_slug") or "")
        analysis_method = "대기 중"
        if report_slug:
            index_file = published_dir / report_slug / "index.html"
            if index_file.is_file():
                analysis_method = _extract_report_metadata(index_file)[
                    "analysis_method"
                ]
        elif job.get("status") == "processing":
            analysis_method = "생성 중"
        elif job.get("status") == "failed":
            analysis_method = "생성 실패"
        processing_stage, processing_note, processing_seconds = _describe_processing_state(
            str(job.get("started_at") or "")
        )
        enriched_job = {
            **job,
            "display_id": str(job["id"])[:8],
            "created_at_display": str(job.get("created_at") or "")[:16].replace("T", " "),
            "subject_name": SUBJECT_NAME_ALIASES.get(
                sub["subject_name"] if sub else "",
                sub["subject_name"] if sub else "",
            ),
            "test_date": sub["test_date"] if sub else "",
            "analysis_method": analysis_method,
            "report_version": _describe_report_version(job.get("report_slug")),
            "is_latest": False,
            "can_trigger": bool(
                sub
                and str(job.get("status") or "") in {"pending", "failed"}
            ),
            "processing_stage": processing_stage,
            "processing_note": processing_note,
            "processing_seconds": processing_seconds,
            "submission_user_id": sub.get("user_id") if sub else None,
            "file_tags": _extract_file_tags(sub) if sub else [],
        }
        enriched.append(enriched_job)
        if job.get("report_slug"):
            job_slugs.add(str(job["report_slug"]))

    if status not in (None, "done"):
        return enriched

    # Skip standalone published reports when filtering by user
    if user_id:
        return enriched

    published_rows = _scan_published_reports(published_dir)
    for row in published_rows:
        if row["report_slug"] in job_slugs:
            continue
        enriched.append(row)

    # Apply name overrides from report_name_overrides table
    from server.db import get_report_name_overrides
    name_overrides = get_report_name_overrides(db_path)
    for row in enriched:
        slug = row.get("report_slug", "")
        if slug and slug in name_overrides:
            row["subject_name"] = name_overrides[slug]

    enriched.sort(
        key=lambda row: str(row.get("created_at") or ""),
        reverse=True,
    )

    # Deduplicate: for same subject+date+report_slug, keep only the newest
    seen_slugs: dict[str, int] = {}
    deduped: list[dict] = []
    for i, row in enumerate(enriched):
        slug = row.get("report_slug", "")
        if slug and slug in seen_slugs:
            # Skip older duplicate with same slug
            continue
        if slug:
            seen_slugs[slug] = i
        deduped.append(row)

    return deduped


# ── Channel dispatch ─────────────────────────────────────────────────


async def notify_channel(channel_url: str, payload: dict) -> None:
    """POST job payload to channel server. Fails gracefully."""
    async with httpx.AsyncClient() as client:
        try:
            await client.post(channel_url, json=payload, timeout=5.0)
        except (httpx.ConnectError, httpx.TimeoutException):
            logger.warning("Channel server not reachable at %s", channel_url)


async def _channel_is_healthy(channel_url: str) -> bool:
    """Check whether the local channel server is reachable."""
    health_url = f"{channel_url.rstrip('/')}/health"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(health_url, timeout=2.0)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            return False
    return resp.status_code == 200


# ── POST /api/submit ─────────────────────────────────────────────────


@router.post("/api/submit", status_code=201)
async def submit(
    request: Request,
    files: list[UploadFile],
    description: str = Form(""),
    subject_name: str = Form(""),
    test_date: str = Form(""),
) -> JSONResponse:
    """Upload files, create workspace/submission/job, dispatch to channel."""
    db_path = get_db_path(request)
    data_dir = get_data_dir(request)
    channel_url = get_channel_url(request)

    if not files:
        return JSONResponse(
            status_code=400,
            content={"error": "no files provided"},
        )

    # Read file contents and validate
    file_pairs: list[tuple[str, bytes]] = []
    has_xlsx = False

    for f in files:
        filename = f.filename or "unnamed"
        ext = Path(filename).suffix.lower()

        if ext not in ALLOWED_EXTENSIONS:
            return JSONResponse(
                status_code=400,
                content={"error": f"invalid file extension: {ext}"},
            )

        content = await f.read()

        if len(content) > MAX_FILE_SIZE:
            return JSONResponse(
                status_code=413,
                content={
                    "error": f"file too large: {filename} "
                    f"({len(content)} bytes, max {MAX_FILE_SIZE})"
                },
            )

        if ext == ".xlsx":
            has_xlsx = True

        file_pairs.append((filename, content))

    if not has_xlsx:
        return JSONResponse(
            status_code=400,
            content={"error": "at least one .xlsx (COSMED) file required"},
        )

    # Create workspace first to determine submission_id
    submission_id = str(uuid.uuid4())
    workspace = create_workspace(data_dir, submission_id, file_pairs)

    # Build file manifest
    manifest = list_files(workspace)

    # Extract user_id from session (None for anonymous uploads)
    user_id = request.session.get("user_id") if hasattr(request, "session") else None

    # Create submission and job
    create_submission(
        db_path,
        description,
        manifest,
        str(workspace),
        subject_name=subject_name,
        test_date=test_date,
        submission_id=submission_id,
        user_id=user_id,
    )
    job_id = create_job(db_path, submission_id)

    # Dispatch to channel (fire-and-forget, graceful on failure)
    await notify_channel(
        channel_url,
        {
            "submission_id": submission_id,
            "job_id": job_id,
            "workspace_path": str(workspace),
            "description": description,
            "files": manifest,
        },
    )

    return JSONResponse(
        status_code=201,
        content={"job_id": job_id, "status": "pending"},
    )


# ── GET /api/jobs ────────────────────────────────────────────────────


@router.get("/api/jobs")
async def jobs_list(
    request: Request,
    status: str | None = None,
) -> list[dict]:
    """List jobs, optionally filtered by status."""
    return _list_dashboard_entries(request, status=status)


# ── GET /api/jobs/partial (HTMX) ────────────────────────────────────
# Must be registered BEFORE /api/jobs/{job_id} to avoid path conflict.


@router.get("/api/jobs/partial", response_class=HTMLResponse)
async def jobs_partial(
    request: Request,
    status: str | None = None,
    filter: str | None = None,
) -> HTMLResponse:
    """Return an HTML partial of the job list for HTMX polling.

    When filter=mine, restrict to jobs created by the current session user.
    """
    templates = request.app.state.templates
    current_user_id: str | None = None
    if hasattr(request, "session"):
        current_user_id = request.session.get("user_id")

    filter_user_id: str | None = None
    if filter == "mine" and current_user_id:
        filter_user_id = current_user_id

    enriched = _list_dashboard_entries(
        request, status=status, user_id=filter_user_id,
    )

    current_user_role = ""
    if hasattr(request, "session"):
        current_user_role = request.session.get("role", "")

    return templates.TemplateResponse(
        request,
        "partials/job_list.html",
        {"jobs": enriched, "current_user_id": current_user_id, "current_user_role": current_user_role},
    )


@router.post(
    "/api/jobs/{job_id}/trigger",
    response_class=HTMLResponse,
    response_model=None,
)
async def trigger_job(
    request: Request,
    job_id: str,
) -> HTMLResponse:
    """Manually trigger analysis for a pending/failed job."""
    db_path = get_db_path(request)
    channel_url = get_channel_url(request)
    templates = request.app.state.templates
    published_dir = get_published_dir(request)

    job = get_job(db_path, job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"job not found: {job_id}"},
        )

    if str(job.get("status") or "") == "done":
        # Allow re-analysis: reset job to pending
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE jobs SET status = 'pending', error_message = NULL, "
            "started_at = NULL, completed_at = NULL WHERE id = ?",
            (job_id,),
        )
        conn.commit()
        conn.close()
        job["status"] = "pending"

    if str(job.get("status") or "") == "processing":
        return JSONResponse(
            status_code=409,
            content={"error": "job is already processing"},
        )

    submission = get_submission(db_path, str(job["submission_id"]))
    if submission is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"submission not found for job: {job_id}"},
        )

    canonical_job = get_job_by_submission(db_path, str(submission["id"])) or job
    payload = _build_channel_payload(canonical_job, submission)
    update_job_status(
        db_path,
        job_id,
        "processing",
        error_message=None,
        report_slug=None,
        report_url=None,
    )

    if await _channel_is_healthy(channel_url):
        await notify_channel(channel_url, payload)
        logger.info("Manual trigger sent to channel for job %s", job_id)
    else:
        _start_fallback_analysis(
            db_path=db_path,
            job=canonical_job,
            submission=submission,
            publish_dir=published_dir,
        )
        logger.info("Manual trigger started local fallback for job %s", job_id)

    current_user_id: str | None = None
    if hasattr(request, "session"):
        current_user_id = request.session.get("user_id")

    current_user_role = ""
    if hasattr(request, "session"):
        current_user_role = request.session.get("role", "")

    enriched = _list_dashboard_entries(request)
    return templates.TemplateResponse(
        request,
        "partials/job_list.html",
        {"jobs": enriched, "current_user_id": current_user_id, "current_user_role": current_user_role},
    )


# ── GET /api/jobs/{job_id} ───────────────────────────────────────────


@router.get("/api/jobs/{job_id}")
async def job_detail(
    request: Request,
    job_id: str,
) -> JSONResponse:
    """Get a single job by ID."""
    db_path = get_db_path(request)
    job = get_job(db_path, job_id)

    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"job not found: {job_id}"},
        )

    return JSONResponse(content=job)
