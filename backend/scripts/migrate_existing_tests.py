#!/usr/bin/env python3
"""
기존 업로드된 테스트들에 대해 자동 전처리 수행

Usage:
    # Dry run (실제 저장 안 함)
    python scripts/migrate_existing_tests.py --dry-run

    # 실제 실행
    python scripts/migrate_existing_tests.py

    # 특정 테스트만 처리
    python scripts/migrate_existing_tests.py --test-id <uuid>
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models import CPETTest, BreathData, ProcessedMetabolism
from app.services.processed_metabolism import ProcessedMetabolismService
from app.services.metabolism_analysis import AnalysisConfig

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def migrate_tests(
    database_url: str,
    dry_run: bool = False,
    test_id: Optional[str] = None
):
    """
    기존 테스트들에 대해 자동 전처리 수행

    Args:
        database_url: Database connection URL
        dry_run: If True, only simulate without saving
        test_id: If provided, only process this specific test
    """
    logger.info("🚀 Starting test migration...")
    logger.info(f"   Database: {database_url.split('@')[1] if '@' in database_url else 'local'}")
    logger.info(f"   Dry run: {dry_run}")

    # Create async engine
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Build query
        query = select(CPETTest).where(
            CPETTest.protocol_type.in_(["RAMP", "HYBRID"]),
            CPETTest.parsing_status == "success"
        )

        # Filter by test_id if provided
        if test_id:
            query = query.where(CPETTest.test_id == UUID(test_id))
            logger.info(f"   Filtering: test_id = {test_id}")
        else:
            # Only process tests WITHOUT existing ProcessedMetabolism records
            # This is more reliable than checking processing_status
            existing_processed_ids = select(ProcessedMetabolism.cpet_test_id)
            query = query.where(~CPETTest.test_id.in_(existing_processed_ids))
            logger.info(f"   Filtering: tests without ProcessedMetabolism records")

        # Execute query
        result = await db.execute(query)
        tests = result.scalars().all()

        if not tests:
            logger.warning("⚠️  No tests found to process")
            return

        logger.info(f"📊 Found {len(tests)} test(s) to process\n")

        # Statistics
        processed = 0
        skipped = 0
        failed = 0

        # Process each test
        for idx, test in enumerate(tests, 1):
            logger.info(f"[{idx}/{len(tests)}] Processing test {test.test_id}")
            logger.info(f"         Subject: {test.subject_id}")
            logger.info(f"         Protocol: {test.protocol_type}")
            logger.info(f"         Date: {test.test_date}")

            try:
                # Fetch breath data
                breath_result = await db.execute(
                    select(BreathData)
                    .where(BreathData.test_id == test.test_id)
                    .order_by(BreathData.t_sec)
                )
                breath_data = list(breath_result.scalars().all())

                # Check minimum data requirement
                if len(breath_data) < 10:
                    logger.warning(f"⏭️  Skipped: insufficient data ({len(breath_data)} points)")
                    skipped += 1
                    print()
                    continue

                logger.info(f"         Breath data: {len(breath_data)} points")

                # Perform processing
                if not dry_run:
                    pm_service = ProcessedMetabolismService(db)
                    await pm_service.save(
                        test_id=test.test_id,
                        breath_data=breath_data,
                        config=AnalysisConfig(),
                        is_manual_override=False
                    )
                    logger.info(f"✅ Success: processed and saved")
                    processed += 1
                else:
                    logger.info(f"✅ Success: would process (dry-run mode)")
                    processed += 1

            except Exception as e:
                logger.error(f"❌ Failed: {str(e)}")
                failed += 1

            print()  # Empty line for readability

        # Summary
        logger.info("=" * 60)
        logger.info("📈 Migration Summary")
        logger.info("=" * 60)
        logger.info(f"   Total tests: {len(tests)}")
        logger.info(f"   ✅ Processed: {processed}")
        logger.info(f"   ⏭️  Skipped: {skipped}")
        logger.info(f"   ❌ Failed: {failed}")
        logger.info("=" * 60)

        if dry_run:
            logger.info("🔍 DRY RUN MODE - No data was saved")
            logger.info("   Run without --dry-run to actually save")
        else:
            logger.info("✨ Migration complete!")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migrate existing tests to add processed metabolism data")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without saving to database"
    )
    parser.add_argument(
        "--test-id",
        type=str,
        help="Process only specific test ID"
    )
    parser.add_argument(
        "--database-url",
        type=str,
        help="Database URL (defaults to DATABASE_URL env var)"
    )

    args = parser.parse_args()

    # Get database URL
    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("❌ DATABASE_URL not found!")
        logger.error("   Set DATABASE_URL environment variable or use --database-url")
        sys.exit(1)

    # Run migration
    try:
        asyncio.run(migrate_tests(
            database_url=database_url,
            dry_run=args.dry_run,
            test_id=args.test_id
        ))
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
