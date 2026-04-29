"""
server.main — FastAPI application entry point.

Initializes the platform database on startup, mounts Jinja2 templates
and static files, and includes the API and auth routers.

Usage:
    uvicorn server.main:app --port 8100 --reload
"""

import os
import csv
import io
import re
import hashlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from server.db import (
    backfill_endurance_core_feature_sets,
    backfill_longitudinal_delta_feature_sets,
    backfill_subject_metric_snapshots,
    build_subject_feature_set_compare,
    build_fitness_trend_compare,
    build_fitness_trend_options,
    build_subject_metric_snapshot_compare,
    complete_onboarding,
    create_subject,
    get_subject_metric_snapshot,
    get_fitness_trends,
    summarize_fitness_trends,
    get_report_user_links,
    get_subject,
    get_subject_feature_set,
    get_dashboard_subject_analytics,
    get_submission,
    get_user,
    get_user_profile,
    delete_submission,
    delete_submission_derived_metrics,
    delete_report_derived_metrics,
    delete_report_metadata,
    init_db,
    link_report_to_user,
    link_submission_user,
    link_submission_subject,
    link_user_to_subject,
    get_report_name_overrides,
    set_report_note,
    list_subjects,
    list_subject_metric_snapshots,
    list_submission_ids_for_user,
    list_report_slugs_for_user,
    list_dashboard_subject_analytics,
    list_submissions_by_user,
    list_subject_feature_sets,
    set_report_name_override,
    refresh_targeted_materializations,
    summarize_dashboard_feature_analytics,
    summarize_subject_feature_sets,
    update_subject,
    update_submission_subject_name,
    update_submission_test_date,
    update_report_catalog_test_date,
    list_submissions_with_users,
    list_users,
    unlink_report_from_user,
    unlink_submission_user,
    unlink_user_from_subject,
    update_user_role,
    upsert_user_profile,
    get_notes_list,
    get_note,
    upsert_note,
    get_report_html,
)
from server.api import _list_dashboard_entries, sync_published_report_catalog, sync_submission_duplicate_metadata

load_dotenv()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize platform database on startup."""
    init_db(app.state.db_path)
    sync_published_report_catalog(app.state.db_path, app.state.published_dir)
    sync_submission_duplicate_metadata(app.state.db_path)
    yield


app = FastAPI(title="CPET Platform", version="2.0.0", lifespan=lifespan)

# ── Session middleware (cookie-based) ────────────────────────────────

SESSION_SECRET = os.environ.get(
    "SESSION_SECRET",
    "change-me-in-production-please-use-a-real-secret-key",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="cpet_session",
    max_age=60 * 60 * 24 * 30,  # 30 days
    same_site="lax",
    https_only=False,  # set True in production behind HTTPS
)


# ── Configuration via environment ────────────────────────────────────

data_dir = Path(os.environ.get("CPET_DATA_DIR", "data"))
app.state.db_path = data_dir / "cpet_platform.db"
app.state.data_dir = data_dir
app.state.channel_url = os.environ.get(
    "CPET_CHANNEL_URL", "http://127.0.0.1:8788"
)

# ── Templates and static files ───────────────────────────────────────

_server_dir = Path(__file__).resolve().parent
_repo_dir = _server_dir.parent
templates = Jinja2Templates(directory=str(_server_dir / "templates"))
app.state.templates = templates

app.mount(
    "/static",
    StaticFiles(directory=str(_server_dir / "static")),
    name="static",
)

_published_dir = Path(
    os.environ.get("CPET_PUBLISHED_DIR", str(_repo_dir / "published"))
).resolve()
app.state.published_dir = _published_dir
_published_dir.mkdir(parents=True, exist_ok=True)



# ── Template context: inject current user into every response ────────


def _get_session_user(request: Request) -> dict | None:
    """Read user info from session. Returns None for anonymous visitors."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return {
        "id": user_id,
        "display_name": request.session.get("display_name", ""),
        "avatar_url": request.session.get("avatar_url", ""),
        "email": request.session.get("email", ""),
        "role": request.session.get("role", "user"),
        "onboarding_completed": request.session.get("onboarding_completed", 0),
    }


def _check_onboarding(request: Request) -> RedirectResponse | None:
    """Return a redirect to /onboarding if the user hasn't completed it, else None."""
    user_id = request.session.get("user_id")
    if user_id and not request.session.get("onboarding_completed"):
        return RedirectResponse(url="/onboarding", status_code=302)
    return None


def _is_preview_mode(request: Request) -> bool:
    """Check if admin is in 'preview as user' mode."""
    return bool(request.session.get("preview_as_user"))


def _template_response(
    request: Request, template_name: str, context: dict | None = None,
) -> HTMLResponse:
    """Render a template with current_user injected into context."""
    user = _get_session_user(request)
    preview = False
    if user and user.get("role") == "admin" and _is_preview_mode(request):
        preview = True
        user = {**user, "role": "user", "_actual_role": "admin"}
    ctx = {"current_user": user, "preview_as_user": preview}
    if context:
        ctx.update(context)
    return templates.TemplateResponse(request, template_name, ctx)



def _slugify(name: str) -> str:
    """Derive a URL-safe slug from a filename stem."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _extract_html_title(html_text: str, fallback: str) -> str:
    """Extract text from the first <title> tag, or return fallback."""
    match = re.search(r"<title>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return fallback
    return re.sub(r"\s+", " ", match.group(1)).strip() or fallback


def _build_note_content_security_policy() -> str:
    """Return a restrictive CSP for researcher note documents."""
    return "; ".join([
        "sandbox allow-scripts allow-popups",
        "default-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'self'",
        "img-src 'self' data: https:",
        "font-src https://fonts.gstatic.com data:",
        "style-src 'unsafe-inline' https://fonts.googleapis.com",
        "script-src 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://unpkg.com",
        "connect-src https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://unpkg.com",
    ])


def _can_edit_report_metadata(
    db_path: Path,
    session_user: dict,
    submission_id: str,
    report_slug: str,
) -> bool:
    """Return whether the current user may edit the given report metadata."""
    if session_user.get("role") == "admin":
        return True

    user_id = str(session_user.get("id") or "")
    if not user_id:
        return False

    actor = get_user(db_path, user_id) or {}
    actor_subject_id = str(actor.get("subject_id") or "")

    if submission_id:
        submission = get_submission(db_path, submission_id)
        if submission is not None:
            if str(submission.get("user_id") or "") == user_id:
                return True
            if actor_subject_id and str(submission.get("subject_id") or "") == actor_subject_id:
                return True

    if report_slug:
        report_links = get_report_user_links(db_path)
        if str(report_links.get(report_slug) or "") == user_id:
            return True

    return False


# ── Page routes ──────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request) -> HTMLResponse:
    """Render the landing page."""
    return _template_response(request, "index.html")


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request, reanalyze: str = "") -> HTMLResponse:
    """Render the file upload page. Login required."""
    # Login required for upload
    user = _get_session_user(request)
    if not user:
        return RedirectResponse(url="/auth/google/login", status_code=302)
    guard = _check_onboarding(request)
    if guard:
        return guard

    db_path = request.app.state.db_path
    actual_role = request.session.get("role", "user")

    # For researcher/admin: load subjects list for target selection
    subjects = []
    if actual_role in ("researcher", "admin"):
        subjects = list_subjects(db_path)

    # For regular user: get their linked subject
    user_subject = None
    user_record = get_user(db_path, user["id"])
    if user_record and user_record.get("subject_id"):
        user_subject = get_subject(db_path, user_record["subject_id"])

    prefill = {}
    existing_files = []
    if reanalyze:
        sub = get_submission(db_path, reanalyze)
        if sub:
            prefill = {
                "submission_id": sub["id"],
                "subject_name": sub.get("subject_name", ""),
                "test_date": sub.get("test_date", ""),
                "description": sub.get("description", ""),
            }
            # List existing files in workspace
            import json as _json
            manifest = sub.get("file_manifest", [])
            if isinstance(manifest, str):
                try:
                    manifest = _json.loads(manifest)
                except Exception:
                    manifest = []
            existing_files = [f.get("name", "") for f in manifest if isinstance(f, dict)]

    return _template_response(request, "upload.html", {
        "prefill": prefill,
        "existing_files": existing_files,
        "subjects": subjects,
        "user_subject": user_subject,
        "is_researcher": actual_role in ("researcher", "admin"),
    })


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """Render the dashboard page."""
    guard = _check_onboarding(request)
    if guard:
        return guard
    session_user = _get_session_user(request)
    requested_tab = (request.query_params.get("tab") or "").strip().lower()
    if requested_tab not in {"analytics", "reports"}:
        requested_tab = "analytics" if session_user else "reports"
    if requested_tab == "analytics" and session_user is None:
        requested_tab = "reports"
    return _template_response(request, "dashboard.html", {
        "dashboard_tab": requested_tab,
    })


@app.get("/notes", response_class=HTMLResponse)
async def notes_page(request: Request) -> HTMLResponse:
    """Render the protected notes index."""
    auth_result = _require_notes_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    db_path = request.app.state.db_path
    return _template_response(request, "notes.html", {
        "notes": get_notes_list(db_path),
    })


@app.get("/notes/{note_slug}", response_class=HTMLResponse)
async def note_viewer_page(request: Request, note_slug: str) -> HTMLResponse:
    """Render a protected note viewer shell."""
    auth_result = _require_notes_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    db_path = request.app.state.db_path
    note = get_note(db_path, note_slug)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")
    return _template_response(request, "note_viewer.html", {"note": note})


@app.get("/notes/{note_slug}/content", response_class=HTMLResponse)
async def note_content_page(request: Request, note_slug: str) -> HTMLResponse:
    """Return the raw note HTML stored in DB after access control."""
    auth_result = _require_notes_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    db_path = request.app.state.db_path
    note = get_note(db_path, note_slug)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")
    return HTMLResponse(
        note["html_content"],
        headers={
            "Content-Security-Policy": _build_note_content_security_policy(),
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/api/notes", response_class=HTMLResponse)
async def upload_note(
    request: Request,
    file: UploadFile = File(...),
) -> HTMLResponse:
    """Upload or replace a note HTML file. Slug is derived from filename."""
    auth_result = _require_notes_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    if not file.filename or not file.filename.lower().endswith(".html"):
        raise HTTPException(status_code=400, detail="HTML 파일만 업로드할 수 있습니다.")

    raw = await file.read()
    try:
        html_content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="파일 인코딩이 UTF-8이어야 합니다.")

    stem = Path(file.filename).stem
    slug = _slugify(stem)
    if not slug:
        raise HTTPException(status_code=400, detail="파일명에서 slug를 추출할 수 없습니다.")

    title = _extract_html_title(html_content, stem.replace("-", " ").replace("_", " "))
    db_path = request.app.state.db_path
    upsert_note(db_path, slug, title, html_content, session_user.get("id"))

    return RedirectResponse(url="/notes", status_code=303)


@app.post("/api/notes/{slug}/replace", response_class=HTMLResponse)
async def replace_note(
    request: Request,
    slug: str,
    file: UploadFile = File(...),
) -> HTMLResponse:
    """Replace an existing note's HTML. Only the uploader or admin may replace."""
    auth_result = _require_notes_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result
    db_path = request.app.state.db_path

    existing = get_note(db_path, slug)
    if existing is None:
        raise HTTPException(status_code=404, detail="note not found")

    role = session_user.get("role", "user")
    owner_id = existing.get("uploaded_by_user_id")
    if role != "admin" and owner_id != session_user.get("id"):
        raise HTTPException(status_code=403, detail="본인이 올린 노트만 수정할 수 있습니다.")

    if not file.filename or not file.filename.lower().endswith(".html"):
        raise HTTPException(status_code=400, detail="HTML 파일만 업로드할 수 있습니다.")

    raw = await file.read()
    try:
        html_content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="파일 인코딩이 UTF-8이어야 합니다.")

    stem = Path(file.filename).stem
    title = _extract_html_title(html_content, stem.replace("-", " ").replace("_", " "))
    upsert_note(db_path, slug, title, html_content, session_user.get("id"))

    return RedirectResponse(url="/notes", status_code=303)


# ---------------------------------------------------------------------------
# Report serving — DB-primary, file fallback
# ---------------------------------------------------------------------------

def _serve_report_slug(db_path: Path, published_dir: Path, slug: str) -> HTMLResponse:
    """Serve a report from DB, falling back to the published file."""
    html = get_report_html(db_path, slug)
    if html:
        return HTMLResponse(html)
    # File fallback (for reports not yet migrated)
    index = published_dir / slug / "index.html"
    if index.is_file():
        return HTMLResponse(index.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="report not found")


@app.get("/report/{slug}", response_class=HTMLResponse)
async def report_redirect(slug: str) -> RedirectResponse:
    return RedirectResponse(url=f"/report/{slug}/", status_code=301)


@app.get("/report/{slug}/", response_class=HTMLResponse)
async def report_page(request: Request, slug: str) -> HTMLResponse:
    db_path = request.app.state.db_path
    published_dir = request.app.state.published_dir
    return _serve_report_slug(db_path, published_dir, slug)


@app.get("/reports/{slug}", response_class=HTMLResponse)
async def reports_redirect(slug: str) -> RedirectResponse:
    return RedirectResponse(url=f"/report/{slug}/", status_code=301)


@app.get("/reports/{slug}/", response_class=HTMLResponse)
async def reports_slug_page(request: Request, slug: str) -> RedirectResponse:
    return RedirectResponse(url=f"/report/{slug}/", status_code=301)


def _render_dashboard_analytics(
    request: Request,
    session_user: dict,
    selected_subject_id: str = "",
) -> HTMLResponse:
    """Render the dashboard analytics overview partial."""
    db_path = request.app.state.db_path
    subject_scope = _get_dashboard_subject_scope(db_path, session_user)
    _ensure_dashboard_feature_analytics_materialized(
        request,
        subject_scope if session_user.get("role") == "user" else None,
    )
    overview = summarize_dashboard_feature_analytics(db_path, subject_ids=subject_scope or None)
    dashboard_subjects = list_dashboard_subject_analytics(
        db_path,
        limit=100,
        subject_ids=subject_scope or None,
    )
    if selected_subject_id and dashboard_subjects:
        allowed_ids = {row["subject_id"] for row in dashboard_subjects}
        if selected_subject_id not in allowed_ids:
            selected_subject_id = ""
    if not selected_subject_id and dashboard_subjects:
        selected_subject_id = dashboard_subjects[0]["subject_id"]
    selected_subject_name = next(
        (
            row["subject_name"]
            for row in dashboard_subjects
            if row["subject_id"] == selected_subject_id
        ),
        "",
    )
    return templates.TemplateResponse(
        request,
        "partials/dashboard_feature_analytics.html",
        {
            "overview": overview,
            "dashboard_subjects": dashboard_subjects,
            "dashboard_scope_locked": session_user.get("role") == "user",
            "selected_subject_id": selected_subject_id,
            "selected_subject_name": selected_subject_name,
        },
    )


@app.get("/api/dashboard/analytics", response_class=HTMLResponse)
async def dashboard_analytics_partial(
    request: Request,
    subject_id: str = "",
) -> HTMLResponse:
    """Render the dashboard analytics overview partial."""
    auth_result = _require_dashboard_access(request)
    if isinstance(auth_result, Response):
        return auth_result
    return _render_dashboard_analytics(
        request,
        session_user=auth_result,
        selected_subject_id=subject_id,
    )


@app.get("/api/dashboard/analytics/subject", response_class=HTMLResponse)
async def dashboard_analytics_subject_partial(
    request: Request,
    subject_id: str = "",
) -> HTMLResponse:
    """Render one subject's dashboard analytics drill-in partial."""
    auth_result = _require_dashboard_access(request)
    if isinstance(auth_result, Response):
        return auth_result

    db_path = request.app.state.db_path
    subject_scope = _get_dashboard_subject_scope(db_path, auth_result)
    _ensure_dashboard_feature_analytics_materialized(
        request,
        subject_scope if auth_result.get("role") == "user" else None,
    )
    if not subject_id:
        dashboard_subjects = list_dashboard_subject_analytics(
            db_path,
            limit=1,
            subject_ids=subject_scope or None,
        )
        subject_id = dashboard_subjects[0]["subject_id"] if dashboard_subjects else ""

    detail = (
        get_dashboard_subject_analytics(
            db_path,
            subject_id,
            subject_ids=subject_scope or None,
        )
        if subject_id
        else None
    )
    return templates.TemplateResponse(
        request,
        "partials/dashboard_feature_analytics_subject.html",
        {
            "detail": detail,
        },
    )


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request) -> HTMLResponse:
    """Render the user profile page. Redirects to login if not authenticated."""
    guard = _check_onboarding(request)
    if guard:
        return guard

    session_user = _get_session_user(request)
    if session_user is None:
        return RedirectResponse(url="/auth/google/login", status_code=302)

    user_id = session_user["id"]
    db_path = request.app.state.db_path
    data_dir = request.app.state.data_dir
    user = get_user(db_path, user_id) or session_user
    profile = get_user_profile(db_path, user_id) or {}
    trends = get_fitness_trends(db_path, user_id, data_dir=data_dir)
    trend_summary = summarize_fitness_trends(trends)
    trend_options = build_fitness_trend_options(trends)
    trend_compare = build_fitness_trend_compare(trends)

    # Load linked subject
    linked_subject = None
    if user.get("subject_id"):
        linked_subject = get_subject(db_path, user["subject_id"])

    return _template_response(request, "profile.html", {
        "user": user,
        "profile": profile,
        "trends": trends,
        "trend_summary": trend_summary,
        "trend_options": trend_options,
        "trend_compare": trend_compare,
        "linked_subject": linked_subject,
    })


@app.patch("/api/profile", response_class=HTMLResponse)
async def update_profile(request: Request) -> HTMLResponse:
    """Update user profile fields. Returns the body-comp partial for HTMX swap."""
    from fastapi.responses import JSONResponse

    session_user = _get_session_user(request)
    if session_user is None:
        return JSONResponse(status_code=401, content={"error": "not authenticated"})

    user_id = session_user["id"]
    db_path = request.app.state.db_path

    form = await request.form()
    fields: dict[str, str | float | int | None] = {}

    float_fields = {"weight_kg", "height_cm", "body_fat_pct", "skeletal_muscle_mass", "bmi"}
    int_fields = {"birth_year"}
    text_fields = {"gender", "training_level", "measured_at"}

    for key in float_fields:
        if key in form:
            raw = str(form[key]).strip()
            fields[key] = float(raw) if raw else None

    for key in int_fields:
        if key in form:
            raw = str(form[key]).strip()
            fields[key] = int(raw) if raw else None

    for key in text_fields:
        if key in form:
            raw = str(form[key]).strip()
            fields[key] = raw if raw else None

    profile = upsert_user_profile(db_path, user_id, **fields)

    return templates.TemplateResponse(
        request,
        "partials/profile_body_comp.html",
        {"profile": profile},
    )


# ── Profile Trends API ────────────────────────────────────────────────


@app.get("/api/profile/trends")
async def profile_trends(
    request: Request,
    baseline: str | None = Query(default=None),
    current: str | None = Query(default=None),
) -> HTMLResponse:
    """Return fitness metric trends as JSON or HTMX partial.

    If the request has HX-Request header (HTMX), returns the trends
    partial HTML. Otherwise returns JSON.
    """
    from fastapi.responses import JSONResponse

    session_user = _get_session_user(request)
    if session_user is None:
        return JSONResponse(status_code=401, content={"error": "not authenticated"})

    user_id = session_user["id"]
    db_path = request.app.state.db_path
    data_dir = request.app.state.data_dir
    trends = get_fitness_trends(db_path, user_id, data_dir=data_dir)
    trend_summary = summarize_fitness_trends(trends)
    trend_options = build_fitness_trend_options(trends)
    try:
        trend_compare = build_fitness_trend_compare(
            trends,
            baseline_submission_id=baseline,
            current_submission_id=current,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    # HTMX partial response
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "partials/profile_trends.html",
            {
                "trends": trends,
                "trend_summary": trend_summary,
                "trend_options": trend_options,
                "trend_compare": trend_compare,
            },
        )

    return JSONResponse(content={
        "data": trends,
        "summary": trend_summary,
        "options": trend_options,
        "compare": trend_compare,
    })


# ── Onboarding routes ─────────────────────────────────────────────────


@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request) -> HTMLResponse:
    """Render the onboarding form. Redirects if not logged in or already completed."""
    from fastapi.responses import RedirectResponse

    session_user = _get_session_user(request)
    if session_user is None:
        return RedirectResponse(url="/auth/google/login", status_code=302)
    if session_user.get("onboarding_completed"):
        return RedirectResponse(url="/dashboard", status_code=302)

    # Pre-fill with session data
    user_id = session_user["id"]
    db_path = request.app.state.db_path
    profile = get_user_profile(db_path, user_id) or {}

    return _template_response(request, "onboarding.html", {
        "profile": profile,
    })


@app.post("/onboarding", response_class=HTMLResponse)
async def onboarding_submit(request: Request) -> HTMLResponse:
    """Process the onboarding form: update users + user_profiles, then redirect."""
    from fastapi.responses import RedirectResponse

    session_user = _get_session_user(request)
    if session_user is None:
        return RedirectResponse(url="/auth/google/login", status_code=302)

    user_id = session_user["id"]
    db_path = request.app.state.db_path

    form = await request.form()
    display_name = str(form.get("display_name", "")).strip()
    gender = str(form.get("gender", "")).strip()
    birth_year_raw = str(form.get("birth_year", "")).strip()
    phone = str(form.get("phone", "")).strip()

    # Validation: required fields
    errors: list[str] = []
    if not display_name:
        errors.append("이름을 입력해주세요.")
    if gender not in ("남성", "여성", "기타"):
        errors.append("성별을 선택해주세요.")
    birth_year = 0
    if not birth_year_raw:
        errors.append("출생년도를 입력해주세요.")
    else:
        try:
            birth_year = int(birth_year_raw)
            if birth_year < 1900 or birth_year > 2025:
                errors.append("출생년도가 올바르지 않습니다.")
        except ValueError:
            errors.append("출생년도는 숫자로 입력해주세요.")

    if errors:
        profile = get_user_profile(db_path, user_id) or {}
        return _template_response(request, "onboarding.html", {
            "profile": profile,
            "errors": errors,
            "form_data": {
                "display_name": display_name,
                "gender": gender,
                "birth_year": birth_year_raw,
                "phone": phone,
            },
        })

    # Update user display_name + onboarding_completed
    complete_onboarding(db_path, user_id, display_name)

    # Update user_profiles with gender + birth_year
    profile_fields: dict[str, str | float | int | None] = {
        "gender": gender,
        "birth_year": birth_year,
    }
    upsert_user_profile(db_path, user_id, **profile_fields)

    # Create a subject for this user and link it
    user_record = get_user(db_path, user_id)
    if user_record and not user_record.get("subject_id"):
        subject = create_subject(
            db_path,
            name=display_name,
            gender=gender,
            birth_year=birth_year,
        )
        link_user_to_subject(db_path, user_id, subject["id"])

    # Update session
    request.session["display_name"] = display_name
    request.session["onboarding_completed"] = 1

    return RedirectResponse(url="/dashboard", status_code=302)


# ── Manage page routes ────────────────────────────────────────────────


def _require_manage_access(request: Request) -> dict | RedirectResponse:
    """Check that the current user has researcher or admin role.

    Returns the session user dict if authorized.
    Returns a RedirectResponse (to login) or raises an HTMLResponse (403) otherwise.
    """
    session_user = _get_session_user(request)
    if session_user is None:
        return RedirectResponse(url="/auth/google/login", status_code=302)

    role = session_user.get("role", "user")
    if role not in ("researcher", "admin"):
        from fastapi.responses import HTMLResponse as HR
        return HR(
            content="<h1>403 Forbidden</h1><p>권한이 없습니다.</p>",
            status_code=403,
        )
    return session_user


def _require_notes_access(request: Request) -> dict | RedirectResponse:
    """Notes are visible only to researcher/admin users."""
    return _require_manage_access(request)


def _require_dashboard_access(request: Request) -> dict | RedirectResponse:
    """Allow any authenticated user to access dashboard analytics."""
    session_user = _get_session_user(request)
    if session_user is None:
        return RedirectResponse(url="/auth/google/login", status_code=302)
    return session_user


def _get_dashboard_subject_scope(db_path: Path, session_user: dict) -> list[str]:
    """Return subject IDs the current user is allowed to inspect on dashboard."""
    role = session_user.get("role", "user")
    if role in ("researcher", "admin"):
        return []

    subject_ids: list[str] = []
    seen: set[str] = set()
    user = get_user(db_path, session_user["id"]) or {}

    def _append(subject_id: str | None) -> None:
        if subject_id and subject_id not in seen:
            seen.add(subject_id)
            subject_ids.append(subject_id)

    _append(user.get("subject_id"))
    for submission in list_submissions_by_user(db_path, session_user["id"]):
        _append(submission.get("subject_id"))
    return subject_ids


def _ensure_dashboard_feature_analytics_materialized(
    request: Request,
    subject_scope: list[str] | None = None,
) -> None:
    """Lazily backfill dashboard analytics tables when feature rows are absent."""
    db_path = request.app.state.db_path
    if subject_scope:
        has_rows = any(
            list_subject_feature_sets(db_path, subject_id=subject_id, limit=1)
            for subject_id in subject_scope
        )
    else:
        has_rows = bool(list_subject_feature_sets(db_path, limit=1))

    if has_rows:
        return

    backfill_subject_metric_snapshots(
        db_path,
        data_dir=request.app.state.data_dir,
        published_dir=request.app.state.published_dir,
    )
    backfill_endurance_core_feature_sets(db_path)
    backfill_longitudinal_delta_feature_sets(db_path)


def _suggest_user_for_submission(
    subject_name: str, users: list[dict],
) -> str | None:
    """Return the user_id of the best matching user by display_name similarity.

    Uses simple normalized containment for Korean/English name matching.
    Returns None if no reasonable match is found.
    """
    if not subject_name or not subject_name.strip():
        return None

    sn = subject_name.strip().lower()
    best_id: str | None = None
    best_score = 0.0

    for user in users:
        dn = (user.get("display_name") or "").strip().lower()
        if not dn:
            continue

        # Exact match
        if sn == dn:
            return user["id"]

        # Containment match
        score = 0.0
        if sn in dn or dn in sn:
            shorter = min(len(sn), len(dn))
            longer = max(len(sn), len(dn))
            score = shorter / longer if longer > 0 else 0.0

        if score > best_score and score >= 0.5:
            best_score = score
            best_id = user["id"]

    return best_id


def _get_manage_submissions(
    request: Request,
    users: list[dict],
    *,
    unlinked_only: str = "",
    sort_by: str = "recent_desc",
    duplicate_only: str = "",
) -> tuple[list[dict], dict[str, str]]:
    """Build the full submissions list for manage page (DB + published/ scan)."""
    db_path = request.app.state.db_path
    all_entries = _list_dashboard_entries(request)
    db_submissions = list_submissions_with_users(db_path)
    report_links = get_report_user_links(db_path)
    users_by_id = {u["id"]: u for u in users}
    entries_by_submission_id = {
        str(entry.get("submission_id")): entry
        for entry in all_entries
        if entry.get("submission_id")
    }

    submissions = []
    for sub_row in db_submissions:
        submission_id = str(sub_row["id"])
        entry = entries_by_submission_id.get(submission_id, {})
        merged = {
            "id": submission_id,
            "submission_id": submission_id,
            "subject_name": sub_row.get("subject_name") or "",
            "test_date": sub_row.get("test_date") or "",
            "status": entry.get("status") or sub_row.get("job_status") or "",
            "report_slug": entry.get("report_slug") or "",
            "report_url": entry.get("report_url") or sub_row.get("report_url") or "",
            "user_id": sub_row.get("user_id"),
            "linked_user_name": sub_row.get("linked_user_name") or sub_row.get("linked_user_email"),
            "created_at": sub_row.get("created_at") or "",
            "source_signature": sub_row.get("source_signature") or "",
            "submission_fingerprint": sub_row.get("submission_fingerprint") or "",
            "duplicate_confidence": sub_row.get("duplicate_confidence") or "",
            "duplicate_group_key": sub_row.get("duplicate_group_key") or "",
            "file_tags": entry.get("file_tags") or [],
        }
        submissions.append(merged)

    for entry in all_entries:
        if entry.get("submission_id"):
            continue
        # Check user_id from submission first
        sub_id = entry.get("submission_id")
        user_id = None
        linked_user_name = None

        if sub_id:
            sub = get_submission(db_path, sub_id)
            if sub:
                user_id = sub.get("user_id")

        # Fallback: check report_user_links for standalone reports
        report_slug = entry.get("report_slug", "")
        if not user_id and report_slug and report_slug in report_links:
            user_id = report_links[report_slug]

        if user_id and user_id in users_by_id:
            u = users_by_id[user_id]
            linked_user_name = u.get("display_name") or u.get("email")

        entry["user_id"] = user_id
        entry["linked_user_name"] = linked_user_name
        submissions.append(entry)

    clusters: dict[str, list[dict]] = {}
    for row in submissions:
        source_signature = str(row.get("source_signature") or "").strip()
        if not source_signature:
            tags = row.get("file_tags") or []
            if isinstance(tags, list):
                source_signature = "+".join(sorted(str(tag) for tag in tags if str(tag).strip()))
        key = ""
        if str(row.get("submission_fingerprint") or "").strip():
            key = f"exact:{str(row.get('submission_fingerprint') or '').strip()}"
        elif str(row.get("duplicate_group_key") or "").strip():
            key = f"likely:{str(row.get('duplicate_group_key') or '').strip()}"
        else:
            linked_name = str(row.get("linked_user_name") or row.get("subject_name") or "").strip()
            test_date = str(row.get("test_date") or "").strip()
            if linked_name and test_date and source_signature:
                key = "likely:" + hashlib.sha256(
                    f"{linked_name}|{test_date}|{source_signature}".encode("utf-8")
                ).hexdigest()[:16]
        row["duplicate_cluster_key"] = ""
        row["duplicate_cluster_count"] = 0
        row["duplicate_badge"] = ""
        if key:
            clusters.setdefault(key, []).append(row)

    for key, items in clusters.items():
        if len(items) < 2:
            continue
        badge = "exact" if key.startswith("exact:") else "likely"
        for row in items:
            row["duplicate_cluster_key"] = key
            row["duplicate_cluster_count"] = len(items)
            row["duplicate_badge"] = badge

    if unlinked_only == "1":
        submissions = [row for row in submissions if not row.get("user_id")]
    if duplicate_only == "1":
        submissions = [row for row in submissions if int(row.get("duplicate_cluster_count") or 0) > 1]

    def _group_sort_key(row: dict) -> tuple[int, str]:
        linked_name = str(row.get("linked_user_name") or "").strip().lower()
        if linked_name:
            return (0, linked_name)
        return (1, "zzzz-unlinked")

    if sort_by == "recent_asc":
        submissions.sort(
            key=lambda row: (
                str(row.get("test_date") or row.get("created_at") or ""),
                str(row.get("subject_name") or "").lower(),
            ),
        )
        submissions.sort(key=_group_sort_key)
    elif sort_by == "name_asc":
        submissions.sort(
            key=lambda row: (
                str(row.get("subject_name") or "").lower(),
                str(row.get("test_date") or row.get("created_at") or ""),
            ),
        )
        submissions.sort(key=_group_sort_key)
    elif sort_by == "name_desc":
        submissions.sort(
            key=lambda row: (
                str(row.get("subject_name") or "").lower(),
                str(row.get("test_date") or row.get("created_at") or ""),
            ),
            reverse=True,
        )
        submissions.sort(key=_group_sort_key)
    else:
        submissions.sort(
            key=lambda row: (
                str(row.get("test_date") or row.get("created_at") or ""),
                str(row.get("subject_name") or "").lower(),
            ),
            reverse=True,
        )
        submissions.sort(key=_group_sort_key)

    # Build suggestion map
    suggestions: dict[str, str] = {}
    for sub in submissions:
        if sub.get("user_id") is None:
            suggested = _suggest_user_for_submission(
                sub.get("subject_name", ""), users,
            )
            if suggested:
                suggestions[sub["id"]] = suggested

    return submissions, suggestions


@app.get("/manage", response_class=HTMLResponse)
async def manage_page(
    request: Request,
    tab: str = "users",
    submissions_unlinked_only: str = "",
    submissions_duplicate_only: str = "",
    submissions_sort_by: str = "recent_desc",
    subject_id: str = "",
    source_kind: str = "",
    date_from: str = "",
    date_to: str = "",
    feature_subject_id: str = "",
    feature_spec_key: str = "",
    feature_window_label: str = "",
    feature_anchor_source_kind: str = "",
) -> HTMLResponse:
    """Render the admin management page with tabs for users, subjects, and submissions."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    active_tab = tab if tab in ("users", "subjects", "submissions", "snapshots", "feature_sets") else "users"

    db_path = request.app.state.db_path
    users = list_users(db_path)
    subjects = list_subjects(db_path)
    submissions, suggestions = _get_manage_submissions(
        request,
        users,
        unlinked_only=submissions_unlinked_only,
        sort_by=submissions_sort_by,
        duplicate_only=submissions_duplicate_only,
    )
    snapshots: list[dict] = []
    snapshot_compare_defaults = {
        "baseline_snapshot_id": "",
        "current_snapshot_id": "",
    }
    if active_tab == "snapshots":
        snapshots = list_subject_metric_snapshots(
            db_path,
            subject_id=subject_id or None,
            source_kind=source_kind or None,
            date_from=date_from or None,
            date_to=date_to or None,
        )
        snapshot_compare_defaults = {
            "baseline_snapshot_id": snapshots[1]["snapshot_id"] if len(snapshots) >= 2 else "",
            "current_snapshot_id": snapshots[0]["snapshot_id"] if len(snapshots) >= 2 else "",
        }

    feature_sets: list[dict] = []
    feature_set_summary = {
        "total": 0,
        "by_spec": {},
        "by_window": {},
        "by_source": {},
    }
    if active_tab == "feature_sets":
        feature_sets = list_subject_feature_sets(
            db_path,
            subject_id=feature_subject_id or None,
            feature_spec_key=feature_spec_key or None,
            window_label=feature_window_label or None,
            anchor_source_kind=feature_anchor_source_kind or None,
        )
        feature_set_summary = summarize_subject_feature_sets(
            db_path,
            subject_id=feature_subject_id or None,
            feature_spec_key=feature_spec_key or None,
            window_label=feature_window_label or None,
            anchor_source_kind=feature_anchor_source_kind or None,
        )

    return _template_response(request, "manage.html", {
        "users": users,
        "subjects": subjects,
        "submissions": submissions,
        "snapshots": snapshots,
        "feature_sets": feature_sets,
        "feature_set_summary": feature_set_summary,
        "suggestions": suggestions,
        "active_tab": active_tab,
        "session_user": session_user,
        "submission_filters": {
            "unlinked_only": submissions_unlinked_only,
            "duplicate_only": submissions_duplicate_only,
            "sort_by": submissions_sort_by,
        },
        "snapshot_compare_defaults": snapshot_compare_defaults,
        "snapshot_filters": {
            "subject_id": subject_id,
            "source_kind": source_kind,
            "date_from": date_from,
            "date_to": date_to,
        },
        "feature_set_filters": {
            "subject_id": feature_subject_id,
            "feature_spec_key": feature_spec_key,
            "window_label": feature_window_label,
            "anchor_source_kind": feature_anchor_source_kind,
        },
    })


@app.patch("/api/manage/users/{user_id}/role", response_class=HTMLResponse)
async def manage_update_user_role(
    request: Request, user_id: str,
) -> HTMLResponse:
    """Update a user's role. Returns the updated users partial for HTMX swap."""
    from fastapi.responses import JSONResponse

    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    form = await request.form()
    new_role = str(form.get("role", "")).strip()

    if not new_role:
        return JSONResponse(status_code=400, content={"error": "role is required"})

    # Permission check: researcher can only toggle user<->researcher
    actor_role = session_user.get("role", "user")
    if actor_role == "researcher" and new_role not in ("user", "researcher"):
        return JSONResponse(
            status_code=403,
            content={"error": "researchers can only assign user or researcher roles"},
        )

    db_path = request.app.state.db_path

    try:
        updated = update_user_role(db_path, user_id, new_role)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    if updated is None:
        return JSONResponse(status_code=404, content={"error": "user not found"})

    # If the actor changed their own role, update the session
    if user_id == session_user["id"]:
        request.session["role"] = new_role

    users = list_users(db_path)
    return templates.TemplateResponse(
        request,
        "partials/manage_users.html",
        {"users": users, "session_user": session_user, "current_user": session_user},
    )


def _render_manage_submissions(
    request: Request,
    session_user: dict,
    *,
    unlinked_only: str = "",
    sort_by: str = "recent_desc",
    duplicate_only: str = "",
) -> HTMLResponse:
    """Helper to render the submissions partial after a link/unlink operation."""
    db_path = request.app.state.db_path
    users = list_users(db_path)
    submissions, suggestions = _get_manage_submissions(
        request,
        users,
        unlinked_only=unlinked_only,
        sort_by=sort_by,
        duplicate_only=duplicate_only,
    )
    return templates.TemplateResponse(
        request,
        "partials/manage_submissions.html",
        {
            "submissions": submissions,
            "users": users,
            "suggestions": suggestions,
            "submission_filters": {
                "unlinked_only": unlinked_only,
                "duplicate_only": duplicate_only,
                "sort_by": sort_by,
            },
            "session_user": session_user,
            "current_user": session_user,
        },
    )


@app.get("/api/manage/submissions/duplicates", response_class=HTMLResponse)
async def manage_duplicate_cluster(
    request: Request,
    group_key: str = "",
) -> HTMLResponse:
    """Render a duplicate cluster detail card for manage page."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    users = list_users(request.app.state.db_path)
    submissions, _suggestions = _get_manage_submissions(request, users)
    rows = [row for row in submissions if str(row.get("duplicate_cluster_key") or "") == group_key]
    if not group_key or not rows:
        return HTMLResponse(
            "<div class='text-sm text-gray-500'>같은 중복 cluster를 가진 항목을 선택하면 비교 정보가 표시됩니다.</div>"
        )

    rows.sort(
        key=lambda row: (
            str(row.get("report_url") or "") != "",
            str(row.get("created_at") or ""),
        ),
        reverse=True,
    )
    primary_id = str(rows[0].get("submission_id") or rows[0].get("report_slug") or "")

    return templates.TemplateResponse(
        request,
        "partials/manage_duplicate_cluster.html",
        {
            "rows": rows,
            "primary_id": primary_id,
            "group_key": group_key,
            "session_user": session_user,
            "current_user": session_user,
        },
    )


def _render_manage_snapshots(
    request: Request,
    session_user: dict,
    subject_id: str = "",
    source_kind: str = "",
    date_from: str = "",
    date_to: str = "",
) -> HTMLResponse:
    """Helper to render the snapshot explorer partial after HTMX filtering."""
    db_path = request.app.state.db_path
    snapshots = list_subject_metric_snapshots(
        db_path,
        subject_id=subject_id or None,
        source_kind=source_kind or None,
        date_from=date_from or None,
        date_to=date_to or None,
    )
    subjects = list_subjects(db_path)
    compare_defaults = {
        "baseline_snapshot_id": snapshots[1]["snapshot_id"] if len(snapshots) >= 2 else "",
        "current_snapshot_id": snapshots[0]["snapshot_id"] if len(snapshots) >= 2 else "",
    }
    return templates.TemplateResponse(
        request,
        "partials/manage_snapshots.html",
        {
            "snapshots": snapshots,
            "subjects": subjects,
            "snapshot_filters": {
                "subject_id": subject_id,
                "source_kind": source_kind,
                "date_from": date_from,
                "date_to": date_to,
            },
            "snapshot_compare_defaults": compare_defaults,
            "session_user": session_user,
            "current_user": session_user,
        },
    )


def _render_manage_feature_sets(
    request: Request,
    session_user: dict,
    feature_subject_id: str = "",
    feature_spec_key: str = "",
    feature_window_label: str = "",
    feature_anchor_source_kind: str = "",
) -> HTMLResponse:
    """Helper to render the feature set explorer partial after HTMX filtering."""
    db_path = request.app.state.db_path
    subjects = list_subjects(db_path)
    feature_sets = list_subject_feature_sets(
        db_path,
        subject_id=feature_subject_id or None,
        feature_spec_key=feature_spec_key or None,
        window_label=feature_window_label or None,
        anchor_source_kind=feature_anchor_source_kind or None,
    )
    feature_set_summary = summarize_subject_feature_sets(
        db_path,
        subject_id=feature_subject_id or None,
        feature_spec_key=feature_spec_key or None,
        window_label=feature_window_label or None,
        anchor_source_kind=feature_anchor_source_kind or None,
    )
    return templates.TemplateResponse(
        request,
        "partials/manage_feature_sets.html",
        {
            "feature_sets": feature_sets,
            "feature_set_summary": feature_set_summary,
            "subjects": subjects,
            "feature_set_filters": {
                "subject_id": feature_subject_id,
                "feature_spec_key": feature_spec_key,
                "window_label": feature_window_label,
                "anchor_source_kind": feature_anchor_source_kind,
            },
            "session_user": session_user,
            "current_user": session_user,
        },
    )


@app.patch("/api/manage/link/{entry_id}", response_class=HTMLResponse)
async def manage_link_entry(
    request: Request, entry_id: str,
) -> HTMLResponse:
    """Link any entry (submission or standalone report) to a user."""
    from fastapi.responses import JSONResponse

    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    form = await request.form()
    link_user_id = str(form.get("user_id", "")).strip()
    report_slug = str(form.get("report_slug", "")).strip()
    submissions_unlinked_only = str(form.get("submissions_unlinked_only", "")).strip()
    submissions_duplicate_only = str(form.get("submissions_duplicate_only", "")).strip()
    submissions_sort_by = str(form.get("submissions_sort_by", "recent_desc")).strip() or "recent_desc"

    if not link_user_id:
        return JSONResponse(status_code=400, content={"error": "user_id is required"})

    db_path = request.app.state.db_path

    # Try submission-based link first
    sub = get_submission(db_path, entry_id)
    if sub is None and not report_slug:
        return JSONResponse(status_code=404, content={"error": "entry not found"})

    refresh_submission_ids: list[str] = []
    refresh_report_slugs: list[str] = []
    refresh_subject_ids: list[str] = []

    if sub:
        updated_submission = link_submission_user(db_path, entry_id, link_user_id)
        refresh_submission_ids.append(entry_id)
        if updated_submission and updated_submission.get("subject_id"):
            refresh_subject_ids.append(str(updated_submission["subject_id"]))

    # Always also link by report_slug (covers standalone reports)
    if report_slug:
        link_report_to_user(db_path, report_slug, link_user_id)
        refresh_report_slugs.append(report_slug)

    try:
        refresh_targeted_materializations(
            db_path,
            subject_ids=refresh_subject_ids or None,
            submission_ids=refresh_submission_ids or None,
            report_slugs=refresh_report_slugs or None,
            data_dir=request.app.state.data_dir,
            published_dir=request.app.state.published_dir,
        )
    except Exception:
        logger.exception("Failed targeted materialization refresh after manage link for %s", entry_id)

    return _render_manage_submissions(
        request,
        session_user,
        unlinked_only=submissions_unlinked_only,
        sort_by=submissions_sort_by,
        duplicate_only=submissions_duplicate_only,
    )


@app.get("/api/manage/snapshots", response_class=HTMLResponse)
async def manage_snapshots_partial(
    request: Request,
    subject_id: str = "",
    source_kind: str = "",
    date_from: str = "",
    date_to: str = "",
) -> HTMLResponse:
    """Render the filtered snapshot explorer partial for HTMX swaps."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result
    return _render_manage_snapshots(
        request,
        session_user,
        subject_id=subject_id,
        source_kind=source_kind,
        date_from=date_from,
        date_to=date_to,
    )


@app.get("/api/manage/feature-sets", response_class=HTMLResponse)
async def manage_feature_sets_partial(
    request: Request,
    feature_subject_id: str = "",
    feature_spec_key: str = "",
    feature_window_label: str = "",
    feature_anchor_source_kind: str = "",
) -> HTMLResponse:
    """Render the filtered feature set explorer partial for HTMX swaps."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result
    return _render_manage_feature_sets(
        request,
        session_user,
        feature_subject_id=feature_subject_id,
        feature_spec_key=feature_spec_key,
        feature_window_label=feature_window_label,
        feature_anchor_source_kind=feature_anchor_source_kind,
    )


@app.get("/api/manage/submissions", response_class=HTMLResponse)
async def manage_submissions_partial(
    request: Request,
    submissions_unlinked_only: str = "",
    submissions_duplicate_only: str = "",
    submissions_sort_by: str = "recent_desc",
) -> HTMLResponse:
    """Render the filtered submissions partial for HTMX swaps."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result
    return _render_manage_submissions(
        request,
        session_user,
        unlinked_only=submissions_unlinked_only,
        sort_by=submissions_sort_by,
        duplicate_only=submissions_duplicate_only,
    )


@app.get("/api/manage/feature-sets/compare", response_class=HTMLResponse)
async def manage_feature_set_compare(
    request: Request,
    baseline_feature_row_id: str = "",
    current_feature_row_id: str = "",
) -> HTMLResponse:
    """Render a compare card for two selected feature sets."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    if not baseline_feature_row_id or not current_feature_row_id:
        return HTMLResponse(
            "<div class='text-sm text-gray-500'>비교할 feature set 두 개를 선택하세요.</div>",
            status_code=400,
        )

    try:
        compare = build_subject_feature_set_compare(
            request.app.state.db_path,
            baseline_feature_row_id=baseline_feature_row_id,
            current_feature_row_id=current_feature_row_id,
        )
    except ValueError as exc:
        return HTMLResponse(
            f"<div class='text-sm text-gray-500'>{str(exc)}</div>",
            status_code=400,
        )

    return templates.TemplateResponse(
        request,
        "partials/manage_feature_set_compare.html",
        {
            "compare": compare,
            "session_user": session_user,
            "current_user": session_user,
        },
    )


@app.get("/api/manage/snapshots/compare", response_class=HTMLResponse)
async def manage_snapshot_compare(
    request: Request,
    baseline_snapshot_id: str = "",
    current_snapshot_id: str = "",
) -> HTMLResponse:
    """Render a compare card for two selected snapshots."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    if not baseline_snapshot_id or not current_snapshot_id:
        return HTMLResponse(
            "<div class='text-sm text-gray-500'>비교할 snapshot 두 개를 선택하세요.</div>",
            status_code=400,
        )

    try:
        compare = build_subject_metric_snapshot_compare(
            request.app.state.db_path,
            baseline_snapshot_id=baseline_snapshot_id,
            current_snapshot_id=current_snapshot_id,
        )
    except ValueError as exc:
        return HTMLResponse(
            f"<div class='text-sm text-gray-500'>{str(exc)}</div>",
            status_code=400,
        )

    return templates.TemplateResponse(
        request,
        "partials/manage_snapshot_compare.html",
        {
            "compare": compare,
            "session_user": session_user,
            "current_user": session_user,
        },
    )


def _snapshot_export_filters(
    subject_id: str = "",
    source_kind: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict[str, str]:
    """Normalize snapshot filter values for exporter routes."""
    return {
        "subject_id": subject_id,
        "source_kind": source_kind,
        "date_from": date_from,
        "date_to": date_to,
    }


def _feature_set_export_filters(
    feature_subject_id: str = "",
    feature_spec_key: str = "",
    feature_window_label: str = "",
    feature_anchor_source_kind: str = "",
) -> dict[str, str]:
    """Normalize feature set filter values for exporter routes."""
    return {
        "feature_subject_id": feature_subject_id,
        "feature_spec_key": feature_spec_key,
        "feature_window_label": feature_window_label,
        "feature_anchor_source_kind": feature_anchor_source_kind,
    }


@app.get("/api/manage/snapshots/export.json")
async def manage_snapshot_export_json(
    request: Request,
    subject_id: str = "",
    source_kind: str = "",
    date_from: str = "",
    date_to: str = "",
) -> JSONResponse:
    """Export filtered snapshot rows as JSON."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result

    filters = _snapshot_export_filters(
        subject_id=subject_id,
        source_kind=source_kind,
        date_from=date_from,
        date_to=date_to,
    )
    snapshots = list_subject_metric_snapshots(
        request.app.state.db_path,
        subject_id=subject_id or None,
        source_kind=source_kind or None,
        date_from=date_from or None,
        date_to=date_to or None,
        limit=1000,
        include_payload=True,
    )
    return JSONResponse({
        "count": len(snapshots),
        "filters": filters,
        "snapshots": snapshots,
    })


@app.get("/api/manage/snapshots/export.csv")
async def manage_snapshot_export_csv(
    request: Request,
    subject_id: str = "",
    source_kind: str = "",
    date_from: str = "",
    date_to: str = "",
) -> Response:
    """Export filtered snapshot rows as CSV."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result

    snapshots = list_subject_metric_snapshots(
        request.app.state.db_path,
        subject_id=subject_id or None,
        source_kind=source_kind or None,
        date_from=date_from or None,
        date_to=date_to or None,
        limit=1000,
    )
    fieldnames = [
        "snapshot_id",
        "subject_id",
        "subject_name",
        "source_kind",
        "source_ref_id",
        "submission_id",
        "measured_at",
        "protocol_type",
        "vo2max_ml",
        "vo2max_rel",
        "lt1_power_w",
        "lt2_power_w",
        "fatmax_power_w",
        "fatmax_gmin",
        "vlamax",
        "at_power_w",
        "carbmax_w",
        "glycogen_g",
        "extraction_version",
        "quality_flags_json",
        "payload_json",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in snapshots:
        writer.writerow({name: row.get(name) for name in fieldnames})

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=subject-metric-snapshots.csv"
        },
    )


@app.get("/api/manage/feature-sets/export.json")
async def manage_feature_set_export_json(
    request: Request,
    feature_subject_id: str = "",
    feature_spec_key: str = "",
    feature_window_label: str = "",
    feature_anchor_source_kind: str = "",
) -> JSONResponse:
    """Export filtered feature set rows as JSON."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result

    filters = _feature_set_export_filters(
        feature_subject_id=feature_subject_id,
        feature_spec_key=feature_spec_key,
        feature_window_label=feature_window_label,
        feature_anchor_source_kind=feature_anchor_source_kind,
    )
    feature_sets = list_subject_feature_sets(
        request.app.state.db_path,
        subject_id=feature_subject_id or None,
        feature_spec_key=feature_spec_key or None,
        window_label=feature_window_label or None,
        anchor_source_kind=feature_anchor_source_kind or None,
        limit=1000,
        include_payload=True,
    )
    return JSONResponse({
        "count": len(feature_sets),
        "filters": filters,
        "feature_sets": feature_sets,
    })


@app.get("/api/manage/feature-sets/export.csv")
async def manage_feature_set_export_csv(
    request: Request,
    feature_subject_id: str = "",
    feature_spec_key: str = "",
    feature_window_label: str = "",
    feature_anchor_source_kind: str = "",
) -> Response:
    """Export filtered feature set rows as CSV."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result

    feature_sets = list_subject_feature_sets(
        request.app.state.db_path,
        subject_id=feature_subject_id or None,
        feature_spec_key=feature_spec_key or None,
        window_label=feature_window_label or None,
        anchor_source_kind=feature_anchor_source_kind or None,
        limit=1000,
    )
    fieldnames = [
        "feature_row_id",
        "subject_id",
        "subject_name",
        "feature_spec_key",
        "feature_spec_version",
        "anchor_snapshot_id",
        "anchor_measured_at",
        "window_label",
        "anchor_source_kind",
        "anchor_extraction_version",
        "input_snapshot_ids_json",
        "input_source_kinds_json",
        "quality_flags_json",
        "feature_payload_json",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in feature_sets:
        writer.writerow({name: row.get(name) for name in fieldnames})

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=subject-feature-sets.csv"
        },
    )


@app.get("/api/manage/feature-sets/{feature_row_id}", response_class=HTMLResponse)
async def manage_feature_set_detail(request: Request, feature_row_id: str) -> HTMLResponse:
    """Render a feature set detail card for explorer inspection."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    feature_set = get_subject_feature_set(request.app.state.db_path, feature_row_id)
    if feature_set is None:
        return HTMLResponse("<div class='text-sm text-gray-500'>Feature set not found.</div>", status_code=404)

    return templates.TemplateResponse(
        request,
        "partials/manage_feature_set_detail.html",
        {
            "feature_set": feature_set,
            "session_user": session_user,
            "current_user": session_user,
        },
    )


@app.get("/api/manage/snapshots/{snapshot_id}", response_class=HTMLResponse)
async def manage_snapshot_detail(request: Request, snapshot_id: str) -> HTMLResponse:
    """Render a snapshot detail card for explorer inspection."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    snapshot = get_subject_metric_snapshot(request.app.state.db_path, snapshot_id)
    if snapshot is None:
        return HTMLResponse("<div class='text-sm text-gray-500'>Snapshot not found.</div>", status_code=404)

    return templates.TemplateResponse(
        request,
        "partials/manage_snapshot_detail.html",
        {
            "snapshot": snapshot,
            "session_user": session_user,
            "current_user": session_user,
        },
    )


@app.delete("/api/manage/link/{entry_id}", response_class=HTMLResponse)
async def manage_unlink_entry(
    request: Request, entry_id: str,
) -> HTMLResponse:
    """Unlink any entry (submission or standalone report) from a user."""
    from fastapi.responses import JSONResponse

    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    form = await request.form()
    report_slug = str(form.get("report_slug", "")).strip()
    submissions_unlinked_only = str(form.get("submissions_unlinked_only", "")).strip()
    submissions_duplicate_only = str(form.get("submissions_duplicate_only", "")).strip()
    submissions_sort_by = str(form.get("submissions_sort_by", "recent_desc")).strip() or "recent_desc"

    db_path = request.app.state.db_path

    # Try submission unlink
    sub = get_submission(db_path, entry_id)
    refresh_submission_ids: list[str] = []
    refresh_report_slugs: list[str] = []
    refresh_subject_ids: list[str] = []
    if sub:
        if sub.get("subject_id"):
            refresh_subject_ids.append(str(sub["subject_id"]))
        unlink_submission_user(db_path, entry_id)
        refresh_submission_ids.append(entry_id)

    # Also unlink by report_slug
    if report_slug:
        refresh_report_slugs.append(report_slug)
        unlink_report_from_user(db_path, report_slug)

    try:
        refresh_targeted_materializations(
            db_path,
            subject_ids=refresh_subject_ids or None,
            submission_ids=refresh_submission_ids or None,
            report_slugs=refresh_report_slugs or None,
            data_dir=request.app.state.data_dir,
            published_dir=request.app.state.published_dir,
        )
    except Exception:
        logger.exception("Failed targeted materialization refresh after manage unlink for %s", entry_id)

    return _render_manage_submissions(
        request,
        session_user,
        unlinked_only=submissions_unlinked_only,
        sort_by=submissions_sort_by,
        duplicate_only=submissions_duplicate_only,
    )


@app.post("/api/manage/preview-mode")
async def toggle_preview_mode(request: Request) -> HTMLResponse:
    """Toggle admin preview-as-user mode."""
    form = await request.form()
    preview = str(form.get("preview", "0")).strip()
    if request.session.get("role") == "admin":
        request.session["preview_as_user"] = preview == "1"
    return HTMLResponse("ok")


@app.patch("/api/manage/rename-subject", response_class=HTMLResponse)
async def manage_rename_subject(request: Request) -> HTMLResponse:
    """Update subject_name for any entry. Admin only."""
    from fastapi.responses import JSONResponse

    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result
    if session_user.get("role") != "admin":
        return JSONResponse(status_code=403, content={"error": "admin only"})

    form = await request.form()
    new_name = str(form.get("subject_name", "")).strip()
    submission_id = str(form.get("submission_id", "")).strip()
    report_slug = str(form.get("report_slug", "")).strip()

    if not new_name:
        return JSONResponse(status_code=400, content={"error": "subject_name is required"})

    db_path = request.app.state.db_path

    # Update submission if exists
    if submission_id:
        update_submission_subject_name(db_path, submission_id, new_name)

    # Always store as report_slug override (covers standalone published)
    if report_slug:
        set_report_name_override(db_path, report_slug, new_name)

    return HTMLResponse(f'<span>{new_name}</span>')


@app.patch("/api/manage/report-metadata", response_class=HTMLResponse)
async def manage_update_report_metadata(request: Request) -> HTMLResponse:
    """Update report display metadata from the dashboard reports list.

    Any logged-in user can update note text.
    Only admins can update subject_name.
    """
    from fastapi.responses import JSONResponse

    session_user = _get_session_user(request)
    if session_user is None:
        return JSONResponse(status_code=401, content={"error": "login required"})

    form = await request.form()
    new_name = str(form.get("subject_name", "")).strip()
    test_date = str(form.get("test_date", "")).strip()
    note = str(form.get("note", "")).strip()
    submission_id = str(form.get("submission_id", "")).strip()
    report_slug = str(form.get("report_slug", "")).strip()

    if not submission_id and not report_slug:
        return JSONResponse(status_code=400, content={"error": "submission_id or report_slug is required"})

    db_path = request.app.state.db_path
    if not _can_edit_report_metadata(db_path, session_user, submission_id, report_slug):
        return JSONResponse(status_code=403, content={"error": "not allowed"})

    if test_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", test_date):
        return JSONResponse(status_code=400, content={"error": "test_date must be YYYY-MM-DD"})

    if new_name:
        if session_user.get("role") != "admin":
            return JSONResponse(status_code=403, content={"error": "admin only for subject rename"})
        if submission_id:
            update_submission_subject_name(db_path, submission_id, new_name)
        if report_slug:
            set_report_name_override(db_path, report_slug, new_name)

    if test_date:
        if session_user.get("role") != "admin":
            return JSONResponse(status_code=403, content={"error": "admin only for test date edit"})
        if submission_id:
            update_submission_test_date(db_path, submission_id, test_date)
        if report_slug:
            update_report_catalog_test_date(db_path, report_slug, test_date)

    if report_slug:
        set_report_note(db_path, report_slug, note)

    return JSONResponse(
        content={
            "ok": True,
            "subject_name": new_name,
            "test_date": test_date,
            "note": note,
            "report_slug": report_slug,
            "submission_id": submission_id,
        }
    )


@app.patch("/api/report-note", response_class=HTMLResponse)
async def update_report_note(request: Request) -> HTMLResponse:
    """Update a report note. Any logged-in user."""
    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    if not user_id:
        return HTMLResponse("", status_code=401)

    form = await request.form()
    report_slug = str(form.get("report_slug", "")).strip()
    note = str(form.get("note", "")).strip()

    if not report_slug:
        return HTMLResponse("", status_code=400)

    db_path = request.app.state.db_path
    session_user = _get_session_user(request)
    if session_user is None or not _can_edit_report_metadata(db_path, session_user, "", report_slug):
        return HTMLResponse("", status_code=403)
    set_report_note(db_path, report_slug, note)
    return HTMLResponse(note or '<span class="text-gray-300 text-[11px] cursor-pointer">+ 메모</span>')


@app.delete("/api/manage/entries/{entry_id}", response_class=HTMLResponse)
async def manage_delete_entry(request: Request, entry_id: str) -> HTMLResponse:
    """Delete a report entry plus its derived metrics. Admin or owner of the submission."""
    from fastapi.responses import JSONResponse
    import shutil

    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "login required"})

    actual_role = request.session.get("role", "user")
    is_admin = actual_role == "admin"

    db_path = request.app.state.db_path

    # Check ownership: admin can delete anything, users can delete their own
    sub = get_submission(db_path, entry_id)
    if sub and not is_admin:
        if sub.get("user_id") != user_id:
            return JSONResponse(status_code=403, content={"error": "자신의 리포트만 삭제할 수 있습니다"})

    if not sub and not is_admin:
        # Standalone published report — only admin can delete
        from server.db import get_report_user_links
        links = get_report_user_links(db_path)
        if links.get(entry_id) != user_id:
            return JSONResponse(status_code=403, content={"error": "자신의 리포트만 삭제할 수 있습니다"})

    # Proceed with deletion
    if sub:
        ws = sub.get("workspace_path")
        if ws:
            ws_path = Path(ws)
            if ws_path.exists():
                shutil.rmtree(ws_path, ignore_errors=True)
        # Remove published report if exists
        from server.db import list_jobs
        jobs = list_jobs(db_path)
        for job in jobs:
            if job.get("submission_id") == entry_id and job.get("report_slug"):
                pub_dir = Path(request.app.state.published_dir) / job["report_slug"]
                if pub_dir.exists():
                    shutil.rmtree(pub_dir, ignore_errors=True)
                delete_report_metadata(db_path, str(job["report_slug"]))
        delete_submission_derived_metrics(db_path, entry_id)
        delete_submission(db_path, entry_id)
    else:
        # Standalone published report — delete by slug (entry_id = report_slug)
        pub_dir = Path(request.app.state.published_dir) / entry_id
        if pub_dir.exists():
            shutil.rmtree(pub_dir, ignore_errors=True)
        delete_report_derived_metrics(db_path, entry_id)
        delete_report_metadata(db_path, entry_id)

    sync_submission_duplicate_metadata(db_path)

    # Return empty to trigger HTMX refresh
    return HTMLResponse("")


# Keep old endpoints for backward compat
@app.patch("/api/manage/submissions/{submission_id}/link", response_class=HTMLResponse)
async def manage_link_submission(request: Request, submission_id: str) -> HTMLResponse:
    """Legacy: link a submission to a user."""
    return await manage_link_entry(request, submission_id)


@app.delete("/api/manage/submissions/{submission_id}/link", response_class=HTMLResponse)
async def manage_unlink_submission(request: Request, submission_id: str) -> HTMLResponse:
    """Legacy: unlink a submission from a user."""
    return await manage_unlink_entry(request, submission_id)


# ── Manage Subjects ──────────────────────────────────────────────────


@app.post("/api/manage/subjects", response_class=HTMLResponse)
async def manage_create_subject(request: Request) -> HTMLResponse:
    """Create a new subject from the manage page."""
    from fastapi.responses import JSONResponse

    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    form = await request.form()
    name = str(form.get("name", "")).strip()
    gender = str(form.get("gender", "")).strip()
    birth_year_raw = str(form.get("birth_year", "")).strip()
    height_cm_raw = str(form.get("height_cm", "")).strip()
    weight_kg_raw = str(form.get("weight_kg", "")).strip()
    training_level = str(form.get("training_level", "")).strip()
    notes = str(form.get("notes", "")).strip()

    if not name:
        return JSONResponse(status_code=400, content={"error": "이름은 필수입니다"})

    db_path = request.app.state.db_path

    birth_year: int | None = None
    if birth_year_raw:
        try:
            birth_year = int(birth_year_raw)
        except ValueError:
            pass

    height_cm: float | None = None
    if height_cm_raw:
        try:
            height_cm = float(height_cm_raw)
        except ValueError:
            pass

    weight_kg: float | None = None
    if weight_kg_raw:
        try:
            weight_kg = float(weight_kg_raw)
        except ValueError:
            pass

    create_subject(
        db_path,
        name=name,
        gender=gender or None,
        birth_year=birth_year,
        height_cm=height_cm,
        weight_kg=weight_kg,
        training_level=training_level or None,
        notes=notes or None,
    )

    # Return the updated subjects partial
    subjects = list_subjects(db_path)
    users = list_users(db_path)
    return templates.TemplateResponse(
        request,
        "partials/manage_subjects.html",
        {"subjects": subjects, "users": users, "session_user": session_user, "current_user": session_user},
    )


@app.patch("/api/manage/subjects/{subject_id}", response_class=HTMLResponse)
async def manage_update_subject(request: Request, subject_id: str) -> HTMLResponse:
    """Update a subject's fields from the manage page."""
    from fastapi.responses import JSONResponse

    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result
    if session_user.get("role") != "admin":
        return JSONResponse(status_code=403, content={"error": "admin only"})

    form = await request.form()
    db_path = request.app.state.db_path

    fields: dict[str, str | float | int | None] = {}
    for key in ("name", "gender", "training_level", "notes"):
        if key in form:
            raw = str(form[key]).strip()
            fields[key] = raw if raw else None
    for key in ("height_cm", "weight_kg", "body_fat_pct", "skeletal_muscle_mass", "bmi"):
        if key in form:
            raw = str(form[key]).strip()
            fields[key] = float(raw) if raw else None
    if "birth_year" in form:
        raw = str(form["birth_year"]).strip()
        fields["birth_year"] = int(raw) if raw else None

    try:
        update_subject(db_path, subject_id, **fields)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    subjects = list_subjects(db_path)
    users = list_users(db_path)
    return templates.TemplateResponse(
        request,
        "partials/manage_subjects.html",
        {"subjects": subjects, "users": users, "session_user": session_user, "current_user": session_user},
    )


@app.patch("/api/manage/subjects/{subject_id}/link-user", response_class=HTMLResponse)
async def manage_link_user_to_subject(request: Request, subject_id: str) -> HTMLResponse:
    """Link a user to a subject."""
    from fastapi.responses import JSONResponse

    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    form = await request.form()
    target_user_id = str(form.get("user_id", "")).strip()
    if not target_user_id:
        return JSONResponse(status_code=400, content={"error": "user_id is required"})

    db_path = request.app.state.db_path
    link_user_to_subject(db_path, target_user_id, subject_id)
    try:
        refresh_targeted_materializations(
            db_path,
            subject_ids=[subject_id],
            submission_ids=list_submission_ids_for_user(db_path, target_user_id) or None,
            report_slugs=list_report_slugs_for_user(db_path, target_user_id) or None,
            data_dir=request.app.state.data_dir,
            published_dir=request.app.state.published_dir,
        )
    except Exception:
        logger.exception(
            "Failed targeted materialization refresh after linking user %s to subject %s",
            target_user_id,
            subject_id,
        )

    subjects = list_subjects(db_path)
    users = list_users(db_path)
    return templates.TemplateResponse(
        request,
        "partials/manage_subjects.html",
        {"subjects": subjects, "users": users, "session_user": session_user, "current_user": session_user},
    )


@app.delete("/api/manage/subjects/{subject_id}/link-user", response_class=HTMLResponse)
async def manage_unlink_user_from_subject(request: Request, subject_id: str) -> HTMLResponse:
    """Unlink a user from a subject."""
    from fastapi.responses import JSONResponse

    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    form = await request.form()
    target_user_id = str(form.get("user_id", "")).strip()
    if not target_user_id:
        return JSONResponse(status_code=400, content={"error": "user_id is required"})

    db_path = request.app.state.db_path
    report_slugs = list_report_slugs_for_user(db_path, target_user_id)
    unlink_user_from_subject(db_path, target_user_id)
    try:
        refresh_targeted_materializations(
            db_path,
            subject_ids=[subject_id],
            report_slugs=report_slugs or None,
            data_dir=request.app.state.data_dir,
            published_dir=request.app.state.published_dir,
        )
    except Exception:
        logger.exception(
            "Failed targeted materialization refresh after unlinking user %s from subject %s",
            target_user_id,
            subject_id,
        )

    subjects = list_subjects(db_path)
    users = list_users(db_path)
    return templates.TemplateResponse(
        request,
        "partials/manage_subjects.html",
        {"subjects": subjects, "users": users, "session_user": session_user, "current_user": session_user},
    )


# ── Auth router ──────────────────────────────────────────────────────

from server.auth import router as auth_router  # noqa: E402

app.include_router(auth_router)

# ── API router ───────────────────────────────────────────────────────

from server.api import router  # noqa: E402

app.include_router(router)
