"""DB 저장까지 테스트"""
import sys
import asyncio
sys.path.insert(0, '/Users/cyanluna-pro16/dev/cpet.db/backend')

from datetime import datetime, timedelta
from uuid import UUID

# SQLAlchemy async 설정
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.models import CPETTest, BreathData, Subject
from app.services.cosmed_parser import COSMEDParser

DATABASE_URL = "postgresql+asyncpg://cpet_user:cpet_password@localhost:5100/cpet_db"

file_path = '/Users/cyanluna-pro16/dev/cpet.db/CPET_data/Cho Kwangho 20240718 CPET MIX_20240718094328.xlsx'
subject_id = UUID("055f1b65-f633-4372-befc-4b84ae292d11")


async def test_db_save():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            # 1. 피험자 확인
            print("1. Checking subject...")
            result = await db.execute(select(Subject).where(Subject.id == subject_id))
            subject = result.scalar_one_or_none()
            print(f"   Subject: {subject.encrypted_name if subject else 'Not found'}")
            
            # 2. 파싱
            print("2. Parsing file...")
            parser = COSMEDParser()
            parsed_data = parser.parse_file(file_path)
            print(f"   ✓ Rows: {len(parsed_data.time_series)}")
            
            # 3. 메트릭 계산
            print("3. Calculating metrics...")
            df = parser.calculate_metabolic_metrics(parsed_data, "Frayn", 10)
            df = parser.detect_phases(df)
            boundaries = parser.get_phase_boundaries(df)
            phase_metrics = parser.calculate_phase_metrics(df)
            vo2max = parser.find_vo2max(df)
            fatmax = parser.find_fatmax(df)
            vt = parser.detect_ventilatory_thresholds(df, 'v_slope')
            print("   ✓ Metrics calculated")
            
            # 4. CPETTest 생성
            print("4. Creating CPETTest...")
            test = CPETTest(
                subject_id=subject_id,
                test_date=parsed_data.test.test_date or datetime.now(),
                test_time=parsed_data.test.test_time,
                protocol_name=parsed_data.test.protocol,
                protocol_type=parsed_data.protocol_type,
                test_type=parsed_data.test.test_type or "Maximal",
                vo2_max=vo2max.get("vo2_max"),
                vo2_max_rel=vo2max.get("vo2_max_rel"),
                hr_max=vo2max.get("hr_max"),
                fat_max_hr=fatmax.get("fat_max_hr"),
                fat_max_watt=fatmax.get("fat_max_watt"),
                fat_max_g_min=fatmax.get("fat_max_g_min"),
                vt1_hr=vt.get("vt1_hr"),
                vt1_vo2=vt.get("vt1_vo2"),
                vt2_hr=vt.get("vt2_hr"),
                vt2_vo2=vt.get("vt2_vo2"),
                warmup_end_sec=boundaries.get("warmup_end_sec"),
                test_end_sec=boundaries.get("exercise_end_sec"),
                calc_method="Frayn",
                smoothing_window=10,
                source_filename="test.xlsx",
                file_upload_timestamp=datetime.utcnow(),
                parsing_status="success",
                phase_metrics=phase_metrics,
            )
            db.add(test)
            await db.flush()
            print(f"   ✓ Test ID: {test.test_id}")
            
            # 5. BreathData 생성
            print("5. Creating BreathData...")
            base_time = test.test_date
            count = 0
            for idx, row in df.iterrows():
                t_sec = row.get("t_sec", idx)
                if t_sec is None or (isinstance(t_sec, float) and t_sec != t_sec):
                    t_sec = float(idx)
                
                breath = BreathData(
                    time=base_time + timedelta(seconds=float(t_sec)),
                    test_id=test.test_id,
                    t_sec=t_sec,
                    rf=row.get("rf"),
                    vt=row.get("vt"),
                    vo2=row.get("vo2"),
                    vco2=row.get("vco2"),
                    ve=row.get("ve"),
                    hr=int(row.get("hr")) if row.get("hr") and not (row.get("hr") != row.get("hr")) else None,
                    rer=row.get("rer"),
                    fat_oxidation=row.get("fat_oxidation"),
                    cho_oxidation=row.get("cho_oxidation"),
                    phase=row.get("phase"),
                    data_source=parsed_data.protocol_type,
                    is_valid=True,
                )
                db.add(breath)
                count += 1
            
            print(f"   ✓ Created {count} BreathData rows")
            
            # 6. 커밋 (테스트용 롤백)
            print("6. Rolling back (test mode)...")
            await db.rollback()
            print("   ✓ Rolled back")
            
            print("\n✅ All DB operations would succeed!")
            
        except Exception as e:
            import traceback
            print(f"\n❌ Error: {e}")
            traceback.print_exc()
            await db.rollback()


if __name__ == "__main__":
    asyncio.run(test_db_save())
