"""
server.auth — Google OAuth login/logout routes.

Uses authlib for the OAuth flow and Starlette session middleware
for cookie-based session management.

Routes:
    GET /auth/google/login    — Redirect to Google consent screen
    GET /auth/google/callback — Handle Google redirect, create/update user, set session
    GET /auth/logout          — Clear session, redirect to landing page
"""

import logging
import os
from pathlib import Path

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.config import Config

from server.db import get_user_by_email, upsert_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ── OAuth client setup ──────────────────────────────────────────────

oauth = OAuth()

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


# ── Dependencies ────────────────────────────────────────────────────


def _get_db_path(request: Request) -> Path:
    """Resolve platform database path from app state."""
    return request.app.state.db_path


# ── Routes ──────────────────────────────────────────────────────────


@router.get("/google/login")
async def google_login(request: Request) -> RedirectResponse:
    """Redirect the user to Google's OAuth consent screen."""
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, str(redirect_uri))


@router.get("/google/callback")
async def google_callback(request: Request) -> RedirectResponse:
    """Handle the OAuth callback from Google.

    On first login, creates a new user with role='user'.
    On subsequent logins, updates last_login_at and profile info.
    Stores user_id in the session cookie.
    """
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if userinfo is None:
        logger.error("Google OAuth callback: no userinfo in token")
        return RedirectResponse(url="/", status_code=302)

    google_id = str(userinfo.get("sub", ""))
    email = str(userinfo.get("email", ""))
    display_name = str(userinfo.get("name", ""))
    avatar_url = str(userinfo.get("picture", ""))

    if not google_id or not email:
        logger.error("Google OAuth callback: missing sub or email in userinfo")
        return RedirectResponse(url="/", status_code=302)

    db_path = _get_db_path(request)
    user = upsert_user(
        db_path,
        google_id=google_id,
        email=email,
        display_name=display_name,
        avatar_url=avatar_url,
    )

    request.session["user_id"] = user["id"]
    request.session["display_name"] = user["display_name"]
    request.session["avatar_url"] = user["avatar_url"]
    request.session["email"] = user["email"]
    request.session["role"] = user.get("role", "user")
    request.session["onboarding_completed"] = user.get("onboarding_completed", 0)
    request.session["subject_id"] = user.get("subject_id", "")

    logger.info("User logged in: %s (%s)", user["id"][:8], email)

    # First-time users or users who haven't completed onboarding → /onboarding
    if user.get("is_new") or not user.get("onboarding_completed"):
        return RedirectResponse(url="/onboarding", status_code=302)

    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Clear the session and redirect to the landing page."""
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)


@router.get("/dev-login")
async def dev_login(
    request: Request,
    email: str = "",
    next: str = "/manage?tab=feature_sets",
) -> RedirectResponse:
    """Create a local dev session without external OAuth.

    Only works when ENABLE_LOCAL_DEV_LOGIN=1.
    Uses DEV_LOGIN_EMAIL as the default target account when no query email is given.
    """
    if os.environ.get("ENABLE_LOCAL_DEV_LOGIN", "") != "1":
        return RedirectResponse(url="/", status_code=302)

    target_email = (email or os.environ.get("DEV_LOGIN_EMAIL", "")).strip()
    if not target_email:
        return RedirectResponse(url="/", status_code=302)

    user = get_user_by_email(_get_db_path(request), target_email)
    if user is None:
        return RedirectResponse(url="/", status_code=302)

    request.session["user_id"] = user["id"]
    request.session["display_name"] = user.get("display_name", "")
    request.session["avatar_url"] = user.get("avatar_url", "")
    request.session["email"] = user.get("email", "")
    request.session["role"] = user.get("role", "user")
    request.session["onboarding_completed"] = user.get("onboarding_completed", 0)
    request.session["subject_id"] = user.get("subject_id", "")

    logger.info("Local dev login: %s (%s)", user["id"][:8], target_email)
    return RedirectResponse(url=next or "/", status_code=302)
