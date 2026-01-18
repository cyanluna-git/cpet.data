#!/usr/bin/env python3
"""Test script to verify demographic fields are working"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.cpet_test import CPETTest
from app.models.subject import Subject


async def test_demographic_fields():
    """Test that demographic fields exist and can be queried"""

    async with AsyncSessionLocal() as session:
        # Test CPETTest model
        print("=" * 60)
        print("Testing CPETTest demographic fields")
        print("=" * 60)

        result = await session.execute(
            select(CPETTest)
            .where(
                (CPETTest.age.isnot(None)) |
                (CPETTest.height_cm.isnot(None)) |
                (CPETTest.weight_kg.isnot(None))
            )
            .limit(5)
        )
        tests = result.scalars().all()

        if tests:
            print(f"\n✓ Found {len(tests)} test(s) with demographic data:")
            for test in tests:
                print(f"\n  Test ID: {test.test_id}")
                print(f"  Date: {test.test_date}")
                print(f"  Age: {test.age if test.age else 'N/A'}")
                print(f"  Height: {test.height_cm if test.height_cm else 'N/A'} cm")
                print(f"  Weight: {test.weight_kg if test.weight_kg else 'N/A'} kg")
        else:
            print("\n⚠ No tests with demographic data found (expected for existing data)")

        # Test Subject model
        print("\n" + "=" * 60)
        print("Testing Subject birth_date field")
        print("=" * 60)

        result = await session.execute(
            select(Subject)
            .where(Subject.birth_date.isnot(None))
            .limit(3)
        )
        subjects = result.scalars().all()

        if subjects:
            print(f"\n✓ Found {len(subjects)} subject(s) with birth_date:")
            for subj in subjects:
                print(f"\n  Research ID: {subj.research_id}")
                print(f"  Birth Date: {subj.birth_date}")
                print(f"  Birth Year: {subj.birth_year if subj.birth_year else 'N/A'}")
        else:
            print("\n⚠ No subjects with birth_date found (expected for existing data)")

        # Verify model attributes exist
        print("\n" + "=" * 60)
        print("Verifying model attributes")
        print("=" * 60)

        cpet_attrs = dir(CPETTest)
        subject_attrs = dir(Subject)

        required_cpet = ['age', 'height_cm', 'weight_kg']
        required_subject = ['birth_date', 'birth_year']

        print("\nCPETTest model:")
        for attr in required_cpet:
            if attr in cpet_attrs:
                print(f"  ✓ {attr} attribute exists")
            else:
                print(f"  ✗ {attr} attribute MISSING")

        print("\nSubject model:")
        for attr in required_subject:
            if attr in subject_attrs:
                print(f"  ✓ {attr} attribute exists")
            else:
                print(f"  ✗ {attr} attribute MISSING")

        print("\n" + "=" * 60)
        print("Test completed successfully!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_demographic_fields())
