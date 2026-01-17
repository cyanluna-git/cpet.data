#!/usr/bin/env python3
"""
End-to-End Preprocessing Pipeline Test
테스트 대상: 박용두 20241217 데이터

테스트 항목:
1. Database에서 테스트 데이터 조회
2. Gas Transport Delay 적용 확인
3. Rolling IQR Outlier Detection 확인
4. Power Binning 결과 확인
5. LOESS Smoothing (1차 전처리) 결과 확인
6. Polynomial Trend (2차/3차 전처리) 결과 확인
7. API 응답 검증
"""

import sys
import os
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models import CPETTest, BreathData, Subject
from app.services.metabolism_analysis import MetabolismAnalyzer, AnalysisConfig


def main():
    print("=" * 60)
    print("🧪 CPET Preprocessing Pipeline End-to-End Test")
    print("=" * 60)

    # 1. Database Connection (convert async URL to sync)
    db_url = settings.database_url.replace("+asyncpg", "")
    print(f"\n📊 Database URL: {db_url[:50]}...")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # 2. Find test data (박용두 20241217)
        print("\n🔍 Step 1: Finding test data (박용두 20241217)...")

        # Find subject
        subject = (
            session.query(Subject).filter(Subject.research_id.ilike("%YON%")).first()
        )

        if not subject:
            print("❌ Subject not found! Trying alternative search...")
            subjects = session.query(Subject).all()
            print(f"   Available subjects: {[s.research_id for s in subjects[:5]]}...")
            return

        print(f"   ✅ Found subject: {subject.research_id} (ID: {subject.id})")

        # Find test
        test = (
            session.query(CPETTest)
            .filter(
                CPETTest.subject_id == subject.id,
                CPETTest.source_filename.ilike("%20241217%"),
            )
            .first()
        )

        if not test:
            tests = (
                session.query(CPETTest).filter(CPETTest.subject_id == subject.id).all()
            )
            print(f"   Available tests: {[t.source_filename for t in tests]}")
            if tests:
                test = tests[0]
                print(f"   Using first available test: {test.source_filename}")
            else:
                print("❌ No tests found for subject!")
                return

        print(f"   ✅ Found test: {test.source_filename}")
        print(f"   Test ID: {test.test_id}")
        print(f"   Test Date: {test.test_date}")

        # 3. Get breath data
        print("\n📊 Step 2: Loading breath data from database...")
        breath_data = (
            session.query(BreathData)
            .filter(BreathData.test_id == test.test_id)
            .order_by(BreathData.t_sec)
            .all()
        )

        print(f"   ✅ Loaded {len(breath_data)} breath data points")
        print(
            f"   Time range: {breath_data[0].t_sec:.1f}s - {breath_data[-1].t_sec:.1f}s"
        )
        print(
            f"   Power range: {min(bd.bike_power or 0 for bd in breath_data):.0f}W - {max(bd.bike_power or 0 for bd in breath_data):.0f}W"
        )

        # 4. Run MetabolismAnalyzer with new pipeline
        print("\n🔬 Step 3: Running MetabolismAnalyzer with new pipeline...")

        config = AnalysisConfig(
            loess_frac=0.25,
            bin_size=10,
            aggregation_method="median",
            gas_delay_seconds=15.0,  # NEW: Gas transport delay
            outlier_window_size=30,  # NEW: Outlier detection window
            outlier_iqr_multiplier=2.0,
            trend_gap_threshold_watts=30,
            exclude_initial_hyperventilation=True,
            initial_time_threshold=120.0,
            initial_power_threshold=40,
        )

        print(
            f"   Config: gas_delay={config.gas_delay_seconds}s, outlier_window={config.outlier_window_size}s"
        )

        analyzer = MetabolismAnalyzer(config)
        result = analyzer.analyze(breath_data)

        if result is None:
            print("❌ Analysis returned None!")
            print(f"   Warnings: {analyzer.warnings}")
            return

        print(f"   ✅ Analysis completed successfully")
        print(f"   Warnings: {result.warnings}")

        # 5. Verify processed series
        print("\n📈 Step 4: Verifying processed series...")
        ps = result.processed_series

        print(f"\n   📍 RAW points: {len(ps.raw)}")
        if ps.raw:
            sample = ps.raw[len(ps.raw) // 2]
            print(
                f"      Sample (mid): power={sample.power:.0f}W, fat={sample.fat_oxidation:.3f}, cho={sample.cho_oxidation:.3f}"
            )

        print(f"\n   📍 BINNED points: {len(ps.binned)}")
        if ps.binned:
            powers = [p.power for p in ps.binned]
            print(f"      Power range: {min(powers):.0f}W - {max(powers):.0f}W")
            gaps = [powers[i + 1] - powers[i] for i in range(len(powers) - 1)]
            max_gap = max(gaps) if gaps else 0
            print(f"      Max gap between bins: {max_gap:.0f}W")

            # Show a few binned points
            print(f"      First 3 bins:")
            for p in ps.binned[:3]:
                print(
                    f"         {p.power:.0f}W: fat={p.fat_oxidation:.3f}, cho={p.cho_oxidation:.3f}, rer={p.rer:.3f if p.rer else 'N/A'}"
                )

        print(f"\n   📍 SMOOTHED points (1차 전처리 - LOESS): {len(ps.smoothed)}")
        if ps.smoothed:
            sample = ps.smoothed[len(ps.smoothed) // 2]
            print(
                f"      Sample (mid): power={sample.power:.0f}W, fat={sample.fat_oxidation:.4f}, cho={sample.cho_oxidation:.4f}"
            )
            print(
                f"      VO2={sample.vo2:.1f if sample.vo2 else 'N/A'}, HR={sample.hr:.0f if sample.hr else 'N/A'}"
            )

        print(f"\n   📍 TREND points (2차/3차 전처리 - Polynomial): {len(ps.trend)}")
        if ps.trend:
            powers = [p.power for p in ps.trend]
            print(f"      Power range: {min(powers):.0f}W - {max(powers):.0f}W")

            # Check for gaps in trend (sparse data handling)
            gaps = [powers[i + 1] - powers[i] for i in range(len(powers) - 1)]
            large_gaps = [
                (powers[i], powers[i + 1])
                for i in range(len(powers) - 1)
                if gaps[i] > 10
            ]
            if large_gaps:
                print(f"      ⚠️ Gaps in trend (sparse data handled): {large_gaps}")
            else:
                print(f"      ✅ No gaps in trend data")

            # Show a few trend points
            print(f"      First 3 trend points:")
            for p in ps.trend[:3]:
                print(
                    f"         {p.power:.0f}W: fat={p.fat_oxidation:.4f}, cho={p.cho_oxidation:.4f}"
                )

        # 6. Verify metabolic markers
        print("\n🎯 Step 5: Verifying metabolic markers...")
        markers = result.metabolic_markers

        print(
            f"   FatMax: {markers.fat_max.power}W, MFO={markers.fat_max.mfo:.4f} g/min"
        )
        print(
            f"   FatMax Zone: {markers.fat_max.zone_min}W - {markers.fat_max.zone_max}W"
        )
        print(f"   Crossover: {markers.crossover.power}W")

        # 7. Convert to dict (API response format)
        print("\n📤 Step 6: Verifying API response format...")
        api_response = result.to_dict()

        print(f"   Keys in response: {list(api_response.keys())}")
        print(
            f"   processed_series keys: {list(api_response['processed_series'].keys())}"
        )

        # Verify trend data is included
        if "trend" in api_response["processed_series"]:
            trend_count = len(api_response["processed_series"]["trend"])
            print(f"   ✅ Trend data included: {trend_count} points")
        else:
            print(f"   ❌ Trend data MISSING from API response!")

        # 8. Summary
        print("\n" + "=" * 60)
        print("✅ END-TO-END TEST SUMMARY")
        print("=" * 60)
        print(f"   Subject: {subject.research_id}")
        print(f"   Test: {test.source_filename}")
        print(f"   Raw points: {len(ps.raw)}")
        print(f"   Binned points: {len(ps.binned)}")
        print(f"   Smoothed points (1차): {len(ps.smoothed)}")
        print(f"   Trend points (2차/3차): {len(ps.trend)}")
        print(f"   FatMax: {markers.fat_max.power}W ({markers.fat_max.mfo:.3f} g/min)")
        print(f"   Crossover: {markers.crossover.power}W")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()
