"""
server.main — FastAPI application entry point.

Initializes the platform database on startup, mounts Jinja2 templates
and static files, and includes the API and auth routers.

Usage:
    uvicorn server.main:app --port 8100 --reload
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from server.db import (
    build_fitness_trend_compare,
    build_fitness_trend_options,
    complete_onboarding,
    create_subject,
    get_fitness_trends,
    summarize_fitness_trends,
    get_report_user_links,
    get_subject,
    get_submission,
    get_user,
    get_user_profile,
    delete_submission,
    init_db,
    link_report_to_user,
    link_submission_user,
    link_submission_subject,
    link_user_to_subject,
    get_report_name_overrides,
    set_report_note,
    list_subjects,
    set_report_name_override,
    update_subject,
    update_submission_subject_name,
    list_submissions_with_users,
    list_users,
    unlink_report_from_user,
    unlink_submission_user,
    unlink_user_from_subject,
    update_user_role,
    upsert_user_profile,
)
from server.api import _list_dashboard_entries

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize platform database on startup."""
    init_db(app.state.db_path)
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

_published_dir = _repo_dir / "published"
app.state.published_dir = _published_dir
if _published_dir.exists():
    # Support both the documented /report/<slug>/ path and older /reports/<slug>/ links.
    app.mount(
        "/report",
        StaticFiles(directory=str(_published_dir), html=True),
        name="report",
    )
    app.mount(
        "/reports",
        StaticFiles(directory=str(_published_dir), html=True),
        name="reports",
    )


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
    return _template_response(request, "dashboard.html")


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


def _get_manage_submissions(request: Request, users: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """Build the full submissions list for manage page (DB + published/ scan)."""
    db_path = request.app.state.db_path
    all_entries = _list_dashboard_entries(request)
    report_links = get_report_user_links(db_path)
    users_by_id = {u["id"]: u for u in users}

    submissions = []
    for entry in all_entries:
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
async def manage_page(request: Request, tab: str = "users") -> HTMLResponse:
    """Render the admin management page with tabs for users, subjects, and submissions."""
    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result
    session_user = auth_result

    db_path = request.app.state.db_path
    users = list_users(db_path)
    subjects = list_subjects(db_path)
    submissions, suggestions = _get_manage_submissions(request, users)

    active_tab = tab if tab in ("users", "subjects", "submissions") else "users"

    return _template_response(request, "manage.html", {
        "users": users,
        "subjects": subjects,
        "submissions": submissions,
        "suggestions": suggestions,
        "active_tab": active_tab,
        "session_user": session_user,
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


def _render_manage_submissions(request: Request, session_user: dict) -> HTMLResponse:
    """Helper to render the submissions partial after a link/unlink operation."""
    db_path = request.app.state.db_path
    users = list_users(db_path)
    submissions, suggestions = _get_manage_submissions(request, users)
    return templates.TemplateResponse(
        request,
        "partials/manage_submissions.html",
        {
            "submissions": submissions,
            "users": users,
            "suggestions": suggestions,
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

    if not link_user_id:
        return JSONResponse(status_code=400, content={"error": "user_id is required"})

    db_path = request.app.state.db_path

    # Try submission-based link first
    sub = get_submission(db_path, entry_id)
    if sub:
        link_submission_user(db_path, entry_id, link_user_id)

    # Always also link by report_slug (covers standalone reports)
    if report_slug:
        link_report_to_user(db_path, report_slug, link_user_id)

    return _render_manage_submissions(request, session_user)


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

    db_path = request.app.state.db_path

    # Try submission unlink
    sub = get_submission(db_path, entry_id)
    if sub:
        unlink_submission_user(db_path, entry_id)

    # Also unlink by report_slug
    if report_slug:
        unlink_report_from_user(db_path, report_slug)

    return _render_manage_submissions(request, session_user)


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
    """Update subject_name for any entry. Researcher/admin only."""
    from fastapi.responses import JSONResponse

    auth_result = _require_manage_access(request)
    if isinstance(auth_result, (RedirectResponse, HTMLResponse)):
        return auth_result

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
    set_report_note(db_path, report_slug, note)
    return HTMLResponse(note or '<span class="text-gray-300 text-[11px] cursor-pointer">+ 메모</span>')


@app.delete("/api/manage/entries/{entry_id}", response_class=HTMLResponse)
async def manage_delete_entry(request: Request, entry_id: str) -> HTMLResponse:
    """Delete a submission/job entry. Admin or owner of the submission."""
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
        delete_submission(db_path, entry_id)
    else:
        # Standalone published report — delete by slug (entry_id = report_slug)
        pub_dir = Path(request.app.state.published_dir) / entry_id
        if pub_dir.exists():
            shutil.rmtree(pub_dir, ignore_errors=True)

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
    unlink_user_from_subject(db_path, target_user_id)

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
