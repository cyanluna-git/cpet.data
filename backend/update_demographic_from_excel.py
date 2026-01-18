#!/usr/bin/env python3
"""
Update demographic data (age, height, weight, birth_date) from existing Excel files
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.models.cpet_test import CPETTest
from app.models.subject import Subject
from app.services.cosmed_parser import COSMEDParser


async def update_demographic_data(excel_dir: str = "../CPET_data"):
    """Update demographic data from Excel files"""

    excel_path = Path(excel_dir)
    if not excel_path.exists():
        print(f"❌ Directory not found: {excel_dir}")
        return

    excel_files = list(excel_path.glob("*.xlsx"))
    print(f"📁 Found {len(excel_files)} Excel files in {excel_dir}")
    print("=" * 80)

    parser = COSMEDParser()
    updated_tests = 0
    updated_subjects = 0
    errors = []

    async with AsyncSessionLocal() as session:
        for excel_file in excel_files:
            filename = excel_file.name
            print(f"\n📄 Processing: {filename}")

            try:
                # Parse Excel file
                parsed_data = parser.parse_file(str(excel_file))

                # Extract demographic info
                age = parsed_data.subject.age
                height_cm = parsed_data.subject.height_cm
                weight_kg = parsed_data.subject.weight_kg
                birth_date_str = parsed_data.subject.birth_date

                print(f"   📊 Parsed data:")
                print(f"      - Age: {age}")
                print(f"      - Height: {height_cm} cm")
                print(f"      - Weight: {weight_kg} kg")
                print(f"      - Birth Date: {birth_date_str}")

                # Find matching test by source_filename
                result = await session.execute(
                    select(CPETTest)
                    .options(selectinload(CPETTest.subject))
                    .where(CPETTest.source_filename == filename)
                )
                test = result.scalar_one_or_none()

                if not test:
                    print(f"   ⚠️  Test not found in database: {filename}")
                    continue

                print(f"   ✓ Found test: {test.test_id}")

                # Update CPETTest
                test_updated = False
                if age and not test.age:
                    test.age = float(age)
                    test_updated = True
                if height_cm and not test.height_cm:
                    test.height_cm = float(height_cm)
                    test_updated = True
                # Don't overwrite weight_kg if already set (test-specific)

                if test_updated:
                    updated_tests += 1
                    print(f"   ✓ Updated test demographic data")

                # Update Subject
                if test.subject:
                    subject = test.subject
                    subject_updated = False

                    # Parse birth_date
                    if birth_date_str and not subject.birth_date:
                        try:
                            if isinstance(birth_date_str, str):
                                birth_date = datetime.strptime(birth_date_str, "%m/%d/%Y").date()
                            else:
                                birth_date = birth_date_str
                            subject.birth_date = birth_date

                            # Also set birth_year for backward compatibility
                            if not subject.birth_year:
                                subject.birth_year = birth_date.year

                            subject_updated = True
                        except Exception as e:
                            print(f"   ⚠️  Failed to parse birth_date: {e}")

                    # Update height and weight if not set
                    if height_cm and not subject.height_cm:
                        subject.height_cm = float(height_cm)
                        subject_updated = True
                    if weight_kg and not subject.weight_kg:
                        subject.weight_kg = float(weight_kg)
                        subject_updated = True

                    if subject_updated:
                        updated_subjects += 1
                        print(f"   ✓ Updated subject demographic data")

                await session.commit()

            except Exception as e:
                print(f"   ❌ Error processing {filename}: {str(e)}")
                errors.append((filename, str(e)))
                await session.rollback()
                continue

    # Summary
    print("\n" + "=" * 80)
    print("📊 Update Summary")
    print("=" * 80)
    print(f"✓ Tests updated: {updated_tests}")
    print(f"✓ Subjects updated: {updated_subjects}")

    if errors:
        print(f"\n⚠️  Errors ({len(errors)}):")
        for filename, error in errors:
            print(f"   - {filename}: {error}")

    print("\n🎉 Update completed!")


if __name__ == "__main__":
    # Import needed for selectinload
    from sqlalchemy.orm import selectinload

    asyncio.run(update_demographic_data())
