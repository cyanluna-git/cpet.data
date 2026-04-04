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
import sqlite3
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

from server.db import (  # noqa: E402
    backfill_endurance_core_feature_sets,
    backfill_longitudinal_delta_feature_sets,
    complete_onboarding,
    create_subject,
    init_db,
    upsert_subject_metric_snapshot,
    upsert_user,
    upsert_user_profile,
)


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
    complete_onboarding(DB_PATH, user["id"], user["display_name"])

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("UPDATE users SET role = 'researcher' WHERE id = ?", (user["id"],))
    conn.commit()
    conn.close()

    alpha = create_subject(DB_PATH, name="Alpha Rider")
    beta = create_subject(DB_PATH, name="Sparse Rider")
    gamma = create_subject(DB_PATH, name="INSCYD Rider")

    def _snapshot(
        *,
        subject_id: str,
        source_kind: str = "cpet_submission",
        source_ref_id: str,
        measured_at: str,
        vo2max_rel: float | None = None,
        fatmax_power_w: float | None = None,
        fatmax_gmin: float | None = None,
        lt1_power_w: float | None = None,
        lt2_power_w: float | None = None,
        vlamax: float | None = None,
        at_power_w: float | None = None,
        carbmax_w: float | None = None,
        glycogen_g: float | None = None,
    ) -> dict:
        return {
            "subject_id": subject_id,
            "source_kind": source_kind,
            "source_ref_id": source_ref_id,
            "submission_id": None,
            "measured_at": measured_at,
            "protocol_type": "Belgium Lactate Test Elite" if source_kind == "cpet_submission" else "INSCYD",
            "vo2max_ml": None,
            "vo2max_rel": vo2max_rel,
            "lt1_power_w": lt1_power_w,
            "lt2_power_w": lt2_power_w,
            "fatmax_power_w": fatmax_power_w,
            "fatmax_gmin": fatmax_gmin,
            "vlamax": vlamax,
            "at_power_w": at_power_w,
            "carbmax_w": carbmax_w,
            "glycogen_g": glycogen_g,
            "extraction_version": "e2e-seed-v1",
            "quality_flags_json": "[]",
            "payload_json": "{}",
        }

    for row in (
        _snapshot(
            subject_id=alpha["id"],
            source_ref_id="alpha-cpet-1",
            measured_at="2026-01-10",
            vo2max_rel=50.0,
            fatmax_power_w=180.0,
            fatmax_gmin=0.41,
            lt1_power_w=205.0,
            lt2_power_w=262.0,
        ),
        _snapshot(
            subject_id=alpha["id"],
            source_ref_id="alpha-cpet-2",
            measured_at="2026-02-10",
            vo2max_rel=55.0,
            fatmax_power_w=195.0,
            fatmax_gmin=0.48,
            lt1_power_w=220.0,
            lt2_power_w=278.0,
        ),
        _snapshot(
            subject_id=beta["id"],
            source_ref_id="sparse-cpet-1",
            measured_at="2026-02-20",
            vo2max_rel=48.0,
            fatmax_power_w=170.0,
            fatmax_gmin=0.37,
            lt1_power_w=198.0,
            lt2_power_w=250.0,
        ),
        _snapshot(
            subject_id=gamma["id"],
            source_kind="inscyd_report",
            source_ref_id="gamma-inscyd-1",
            measured_at="2026-02-12",
            vo2max_rel=57.0,
            fatmax_power_w=184.0,
            fatmax_gmin=0.44,
            lt1_power_w=214.0,
            lt2_power_w=271.0,
            vlamax=0.39,
            at_power_w=276.0,
            carbmax_w=342.0,
            glycogen_g=390.0,
        ),
    ):
        upsert_subject_metric_snapshot(DB_PATH, row)

    backfill_endurance_core_feature_sets(DB_PATH)
    backfill_longitudinal_delta_feature_sets(DB_PATH)

    # Generate signed session cookie and write to file
    session_data = {
        "user_id": user["id"],
        "display_name": user["display_name"],
        "avatar_url": user["avatar_url"],
        "email": user["email"],
        "role": "researcher",
        "onboarding_completed": 1,
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
