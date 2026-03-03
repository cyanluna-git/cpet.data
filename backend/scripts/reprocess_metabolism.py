#!/usr/bin/env python3
"""
Reprocess ALL existing ProcessedMetabolism records.

Re-runs the analysis pipeline with the current algorithm version.
Use after fixing calculation bugs (e.g. banker's rounding in v1.2.1).

Usage:
    # Dry run (count only, no changes)
    python scripts/reprocess_metabolism.py --dry-run

    # Reprocess all records
    python scripts/reprocess_metabolism.py

    # Reprocess a single test
    python scripts/reprocess_metabolism.py --test-id <uuid>
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file automatically
try:
    from dotenv import load_dotenv

    possible_env_paths = [
        Path(__file__).parent.parent.parent / ".env",
        Path(__file__).parent.parent / ".env",
    ]

    env_loaded = False
    for env_path in possible_env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            print(f"Loaded environment from {env_path}")
            env_loaded = True
            break

    if not env_loaded:
        print("WARNING: .env file not found in:")
        for p in possible_env_paths:
            print(f"   - {p}")
except ImportError:
    print("WARNING: python-dotenv not installed, skipping .env file loading")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models import BreathData, ProcessedMetabolism
from app.services.metabolism_analysis import AnalysisConfig
from app.services.processed_metabolism import (
    CURRENT_ALGORITHM_VERSION,
    ProcessedMetabolismService,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def reprocess(
    database_url: str,
    dry_run: bool = False,
    test_id: Optional[str] = None,
):
    """
    Reprocess existing ProcessedMetabolism records.

    Args:
        database_url: Database connection URL
        dry_run: If True, only count without saving
        test_id: If provided, only reprocess this specific test
    """
    logger.info("Starting metabolism reprocessing (algorithm v%s)...", CURRENT_ALGORITHM_VERSION)
    logger.info("   Dry run: %s", dry_run)

    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Build query
        query = select(ProcessedMetabolism)
        if test_id:
            query = query.where(ProcessedMetabolism.cpet_test_id == UUID(test_id))
            logger.info("   Filtering: test_id = %s", test_id)

        result = await db.execute(query)
        records = list(result.scalars().all())

        if not records:
            logger.warning("No ProcessedMetabolism records found")
            return

        logger.info("Found %d record(s) to reprocess\n", len(records))

        if dry_run:
            logger.info("DRY RUN MODE - No data will be modified")
            logger.info("   %d records would be reprocessed", len(records))
            return

        reprocessed = 0
        skipped = 0
        failed = 0

        pm_service = ProcessedMetabolismService(db)

        for idx, record in enumerate(records, 1):
            logger.info(
                "[%d/%d] Reprocessing test %s (current version: %s)",
                idx,
                len(records),
                record.cpet_test_id,
                record.algorithm_version,
            )

            try:
                # Fetch breath data
                breath_result = await db.execute(
                    select(BreathData)
                    .where(BreathData.test_id == record.cpet_test_id)
                    .order_by(BreathData.t_sec)
                )
                breath_data = list(breath_result.scalars().all())

                if len(breath_data) < 10:
                    logger.warning(
                        "   Skipped: insufficient data (%d points)", len(breath_data)
                    )
                    skipped += 1
                    continue

                # Reconstruct config from saved record
                config = AnalysisConfig(
                    bin_size=record.bin_size or 10,
                    aggregation_method=record.aggregation_method or "median",
                    loess_frac=record.loess_frac or 0.25,
                    exclude_rest=record.exclude_rest if record.exclude_rest is not None else True,
                    exclude_warmup=record.exclude_warmup if record.exclude_warmup is not None else True,
                    exclude_recovery=record.exclude_recovery if record.exclude_recovery is not None else True,
                    min_power_threshold=record.min_power_threshold,
                    trim_start_sec=record.trim_start_sec,
                    trim_end_sec=record.trim_end_sec,
                    fatmax_zone_threshold=record.fatmax_zone_threshold or 0.90,
                    auto_trim_enabled=(
                        record.trim_start_sec is None and record.trim_end_sec is None
                    ),
                )

                await pm_service.save(
                    test_id=record.cpet_test_id,
                    breath_data=breath_data,
                    config=config,
                    is_manual_override=record.is_manual_override or False,
                )
                logger.info("   Success (-> v%s)", CURRENT_ALGORITHM_VERSION)
                reprocessed += 1

            except Exception as e:
                logger.error("   Failed: %s", e)
                failed += 1
                # Mark DB record as failed so it's distinguishable from unprocessed
                try:
                    error_msg = f"Reprocess failed (v{CURRENT_ALGORITHM_VERSION}): {e}"
                    record.processing_status = "failed"
                    record.processing_warnings = [error_msg]
                    record.updated_at = datetime.utcnow()
                    await db.commit()
                except Exception as db_err:
                    logger.error("   Also failed to update status: %s", db_err)

        # Summary
        logger.info("=" * 60)
        logger.info("Reprocessing Summary")
        logger.info("=" * 60)
        logger.info("   Total records: %d", len(records))
        logger.info("   Reprocessed:   %d", reprocessed)
        logger.info("   Skipped:       %d", skipped)
        logger.info("   Failed:        %d", failed)
        logger.info("   Algorithm:     v%s", CURRENT_ALGORITHM_VERSION)
        logger.info("=" * 60)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Reprocess existing ProcessedMetabolism records with current algorithm"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count records only, do not modify",
    )
    parser.add_argument(
        "--test-id",
        type=str,
        help="Reprocess only this specific test ID",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        help="Database URL (defaults to DATABASE_URL env var)",
    )

    args = parser.parse_args()

    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not found!")
        logger.error("   Set DATABASE_URL environment variable or use --database-url")
        sys.exit(1)

    try:
        asyncio.run(
            reprocess(
                database_url=database_url,
                dry_run=args.dry_run,
                test_id=args.test_id,
            )
        )
    except KeyboardInterrupt:
        logger.warning("\nReprocessing interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error("Reprocessing failed: %s", e)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
