"""Import lactate blood sample data from pipeline SQLite to PostgreSQL.

Maps SQLite session_id -> PostgreSQL UUID test_id via test_date + subject research_id.

Usage:
    python scripts/import_lactate_to_postgres.py <analysis.db_path>

Example:
    python scripts/import_lactate_to_postgres.py data/hong.changsun/analysis.db
"""

import asyncio
import sqlite3
import sys
import uuid
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import CPETTest, Subject
from app.models.blood_sample import BloodSample


async def import_lactate(sqlite_path: str) -> None:
    """Import blood samples from pipeline SQLite to PostgreSQL."""
    db_path = Path(sqlite_path)
    if not db_path.exists():
        print(f"SQLite database not found: {db_path}")
        sys.exit(1)

    # Connect to SQLite
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='blood_samples'")
    if not cursor.fetchone():
        print("No blood_samples table found in SQLite database")
        conn.close()
        sys.exit(1)

    # Read sessions for mapping
    cursor.execute("SELECT id, subject_id, test_date FROM test_session")
    sessions = cursor.fetchall()

    # Read subjects for research_id lookup
    cursor.execute("SELECT id, name FROM subject")
    sqlite_subjects = {row["id"]: row["name"] for row in cursor.fetchall()}

    # Read blood samples
    cursor.execute("SELECT * FROM blood_samples ORDER BY session_id, id")
    blood_rows = cursor.fetchall()

    if not blood_rows:
        print("No blood samples found in SQLite database")
        conn.close()
        return

    print(f"Found {len(blood_rows)} blood samples across {len(sessions)} sessions")

    # Connect to PostgreSQL
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        imported = 0
        skipped = 0

        for session_row in sessions:
            session_id = session_row["id"]
            subject_name = sqlite_subjects.get(session_row["subject_id"])
            test_date_str = session_row["test_date"]

            if not subject_name or not test_date_str:
                print(f"  Skipping session {session_id}: missing subject or date")
                skipped += 1
                continue

            # Find PostgreSQL subject by research_id or encrypted_name
            result = await db.execute(
                select(Subject).where(
                    (Subject.research_id == subject_name)
                    | (Subject.encrypted_name == subject_name)
                )
            )
            pg_subject = result.scalar_one_or_none()

            if not pg_subject:
                print(f"  Subject '{subject_name}' not found in PostgreSQL, skipping session {session_id}")
                skipped += 1
                continue

            # Find matching CPET test by subject_id + test_date
            result = await db.execute(
                select(CPETTest).where(
                    CPETTest.subject_id == pg_subject.id,
                    text(f"DATE(cpet_tests.test_date) = '{test_date_str}'"),
                )
            )
            pg_test = result.scalar_one_or_none()

            if not pg_test:
                print(f"  No matching test for {subject_name} on {test_date_str}, skipping")
                skipped += 1
                continue

            # Get blood samples for this session
            session_samples = [r for r in blood_rows if r["session_id"] == session_id]

            # Check if already imported
            existing = await db.execute(
                select(BloodSample).where(
                    BloodSample.cpet_test_id == pg_test.test_id
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                print(f"  Samples already exist for test {pg_test.test_id}, skipping")
                skipped += 1
                continue

            for row in session_samples:
                sample = BloodSample(
                    cpet_test_id=pg_test.test_id,
                    block=row["block"],
                    step=row["step"],
                    load_w=row["load_w"],
                    ftp_pct=row["ftp_pct"],
                    duration_min=row["duration_min"],
                    sample_time_kst=row["sample_time_kst"],
                    hr_bpm=row["hr_bpm"],
                    lactate_mmol=row["lactate_mmol"],
                    glucose_mmol=row["glucose_mmol"],
                    notes=row["notes"],
                )
                db.add(sample)
                imported += 1

            print(f"  Imported {len(session_samples)} samples for {subject_name} ({test_date_str})")

        await db.commit()
        print(f"\nDone: {imported} samples imported, {skipped} sessions skipped")

    await engine.dispose()
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    asyncio.run(import_lactate(sys.argv[1]))
