"""
server.api — REST endpoints for CPET submission and job management.

Endpoints:
    POST /api/submit       — Upload files and create a new job
    GET  /api/jobs          — List jobs (optional status filter)
    GET  /api/jobs/partial  — HTMX partial for job list
    GET  /api/jobs/{job_id} — Get a single job by ID
"""

import logging
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from server.db import (
    create_job,
    create_submission,
    get_job,
    get_submission,
    list_jobs,
)
from server.workspace import create_workspace, list_files

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {".fit", ".zwo", ".xlsx", ".md", ".csv"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


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


# ── Channel dispatch ─────────────────────────────────────────────────


async def notify_channel(channel_url: str, payload: dict) -> None:
    """POST job payload to channel server. Fails gracefully."""
    async with httpx.AsyncClient() as client:
        try:
            await client.post(channel_url, json=payload, timeout=5.0)
        except (httpx.ConnectError, httpx.TimeoutException):
            logger.warning("Channel server not reachable at %s", channel_url)


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

    # Create submission and job
    create_submission(
        db_path,
        description,
        manifest,
        str(workspace),
        subject_name=subject_name,
        test_date=test_date,
        submission_id=submission_id,
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
    db_path = get_db_path(request)
    return list_jobs(db_path, status=status)


# ── GET /api/jobs/partial (HTMX) ────────────────────────────────────
# Must be registered BEFORE /api/jobs/{job_id} to avoid path conflict.


@router.get("/api/jobs/partial", response_class=HTMLResponse)
async def jobs_partial(
    request: Request,
    status: str | None = None,
) -> HTMLResponse:
    """Return an HTML partial of the job list for HTMX polling."""
    db_path = get_db_path(request)
    templates = request.app.state.templates

    jobs = list_jobs(db_path, status=status)

    # Enrich each job with submission metadata
    enriched = []
    for job in jobs:
        sub = get_submission(db_path, job["submission_id"])
        enriched.append({
            **job,
            "subject_name": sub["subject_name"] if sub else "",
            "test_date": sub["test_date"] if sub else "",
        })

    return templates.TemplateResponse(
        request, "partials/job_list.html", {"jobs": enriched},
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
