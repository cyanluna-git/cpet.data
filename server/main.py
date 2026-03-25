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
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from server.db import (
    get_fitness_trends,
    get_user,
    get_user_profile,
    init_db,
    upsert_user_profile,
)

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
    }


def _template_response(
    request: Request, template_name: str, context: dict | None = None,
) -> HTMLResponse:
    """Render a template with current_user injected into context."""
    ctx = {"current_user": _get_session_user(request)}
    if context:
        ctx.update(context)
    return templates.TemplateResponse(request, template_name, ctx)


# ── Page routes ──────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request) -> HTMLResponse:
    """Render the landing page."""
    return _template_response(request, "index.html")


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request) -> HTMLResponse:
    """Render the file upload page."""
    return _template_response(request, "upload.html")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """Render the dashboard page."""
    return _template_response(request, "dashboard.html")


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request) -> HTMLResponse:
    """Render the user profile page. Redirects to login if not authenticated."""
    from fastapi.responses import RedirectResponse

    session_user = _get_session_user(request)
    if session_user is None:
        return RedirectResponse(url="/auth/google/login", status_code=302)

    user_id = session_user["id"]
    db_path = request.app.state.db_path
    data_dir = request.app.state.data_dir
    user = get_user(db_path, user_id) or session_user
    profile = get_user_profile(db_path, user_id) or {}
    trends = get_fitness_trends(db_path, user_id, data_dir=data_dir)

    return _template_response(request, "profile.html", {
        "user": user,
        "profile": profile,
        "trends": trends,
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
async def profile_trends(request: Request) -> HTMLResponse:
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

    # HTMX partial response
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "partials/profile_trends.html",
            {"trends": trends},
        )

    return JSONResponse(content={"data": trends})


# ── Auth router ──────────────────────────────────────────────────────

from server.auth import router as auth_router  # noqa: E402

app.include_router(auth_router)

# ── API router ───────────────────────────────────────────────────────

from server.api import router  # noqa: E402

app.include_router(router)
