"""
tests/e2e/run_test_server.py — Launch FastAPI server for E2E tests.

Creates a temporary database, seeds a test user, and starts
uvicorn on port 8100. The test user's session cookie value is
written to .test-session-cookie so Playwright tests can inject it.

Usage:
    python tests/e2e/run_test_server.py
"""

import base64
import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ["SESSION_SECRET"] = "e2e-test-secret-key"
os.environ.setdefault("GOOGLE_CLIENT_ID", "fake-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "fake-client-secret")

# Create temp data directory
TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="cpet_e2e_"))
DB_PATH = TEST_DATA_DIR / "cpet_platform.db"

os.environ["CPET_DATA_DIR"] = str(TEST_DATA_DIR)

from itsdangerous import TimestampSigner  # noqa: E402

from server.db import init_db, upsert_user, upsert_user_profile  # noqa: E402


def _create_signed_cookie(session_data: dict, secret: str) -> str:
    """Create a Starlette-compatible signed session cookie."""
    signer = TimestampSigner(secret)
    encoded = base64.b64encode(json.dumps(session_data).encode()).decode()
    return signer.sign(encoded).decode()


def seed_test_data() -> None:
    """Initialize DB and create test user + profile."""
    init_db(DB_PATH)

    user = upsert_user(
        DB_PATH,
        google_id="e2e-google-id",
        email="e2e-test@example.com",
        display_name="E2E Test User",
        avatar_url="https://example.com/e2e-avatar.jpg",
    )

    upsert_user_profile(
        DB_PATH,
        user["id"],
        weight_kg=72.5,
        height_cm=175.0,
        body_fat_pct=15.0,
        skeletal_muscle_mass=33.0,
        bmi=23.7,
        birth_year=1990,
        gender="male",
        training_level="advanced",
        measured_at="2026-03-20",
    )

    # Generate signed session cookie and write to file
    session_data = {
        "user_id": user["id"],
        "display_name": user["display_name"],
        "avatar_url": user["avatar_url"],
        "email": user["email"],
    }
    cookie_value = _create_signed_cookie(session_data, "e2e-test-secret-key")

    cookie_file = Path(__file__).parent / ".test-session-cookie"
    cookie_file.write_text(cookie_value, encoding="utf-8")

    user_id_file = Path(__file__).parent / ".test-user-id"
    user_id_file.write_text(user["id"], encoding="utf-8")

    print(f"[E2E] Test user seeded: {user['id'][:8]}... ({user['email']})")
    print(f"[E2E] Session cookie written to {cookie_file}")


if __name__ == "__main__":
    seed_test_data()

    # Configure app state before importing (module-level side effects)
    from server.main import app  # noqa: E402

    app.state.db_path = DB_PATH
    app.state.data_dir = TEST_DATA_DIR
    app.state.channel_url = "http://127.0.0.1:9999"
    app.state.published_dir = TEST_DATA_DIR / "published"

    import uvicorn  # noqa: E402

    uvicorn.run(app, host="0.0.0.0", port=8100)
