"""
server.main — FastAPI application entry point.

Initializes the platform database on startup, mounts Jinja2 templates
and static files, and includes the API router.

Usage:
    uvicorn server.main:app --port 8100 --reload
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from server.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize platform database on startup."""
    init_db(app.state.db_path)
    yield


app = FastAPI(title="CPET Platform", version="2.0.0", lifespan=lifespan)

# ── Configuration via environment ────────────────────────────────────

data_dir = Path(os.environ.get("CPET_DATA_DIR", "data"))
app.state.db_path = data_dir / "cpet_platform.db"
app.state.data_dir = data_dir
app.state.channel_url = os.environ.get(
    "CPET_CHANNEL_URL", "http://127.0.0.1:8788"
)

# ── Templates and static files ───────────────────────────────────────

_server_dir = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_server_dir / "templates"))
app.state.templates = templates

app.mount(
    "/static",
    StaticFiles(directory=str(_server_dir / "static")),
    name="static",
)

# ── Page routes ──────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request) -> HTMLResponse:
    """Render the landing page."""
    return templates.TemplateResponse(request, "index.html")


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request) -> HTMLResponse:
    """Render the file upload page."""
    return templates.TemplateResponse(request, "upload.html")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """Render the dashboard page."""
    return templates.TemplateResponse(request, "dashboard.html")


# ── API router ───────────────────────────────────────────────────────

from server.api import router  # noqa: E402

app.include_router(router)
