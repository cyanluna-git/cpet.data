"""특정 테스트 ID의 vo2/vco2 데이터 확인"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncio
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.models.breath_data import BreathData
from app.models.cpet_test import CPETTest
from app.core.config import settings

TEST_ID = "c91339b9-c0ce-434d-b4ad-3c77452ed928"

async def check_specific_test():
    """Park Yongdoo 테스트 데이터 확인"""
    
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        test_uuid = UUID(TEST_ID)
        
        # 테스트 확인
        test_query = select(CPETTest).where(CPETTest.test_id == test_uuid)
        test_result = await session.execute(test_query)
        test = test_result.scalar_one_or_none()
        
        if not test:
            print(f"❌ 테스트 없음: {TEST_ID}")
            return
        
        print(f"✅ 테스트: {TEST_ID}")
        print(f"   Subject ID: {test.subject_id}")
        print(f"   Test Date: {test.test_date}")
        print(f"   Protocol: {test.protocol_type}\n")
        
        # BreathData 조회
        query = select(BreathData).where(
            BreathData.test_id == test_uuid
        ).order_by(BreathData.t_sec)
        
        result = await session.execute(query)
        breath_data = list(result.scalars().all())
        
        print(f"총 데이터: {len(breath_data)}개")
        
        # Phase별 집계
        phases = {}
        for bd in breath_data:
            phase = bd.phase or "Unknown"
            if phase not in phases:
                phases[phase] = []
            phases[phase].append(bd)
        
        print("\nPhase별 데이터 수:")
        for phase, data in phases.items():
            print(f"  {phase}: {len(data)}개")
        
        # Exercise 단계 vo2/vco2 확인
        exercise_data = phases.get("Exercise", [])
        if exercise_data:
            print(f"\nExercise 단계 첫 10개의 vo2/vco2:")
            for i, bd in enumerate(exercise_data[:10]):
                print(f"  {i}: power={bd.bike_power}, vo2={bd.vo2}, vco2={bd.vco2}")
            
            # vo2가 None인 데이터 수
            none_vo2 = sum(1 for bd in exercise_data if bd.vo2 is None)
            print(f"\nExercise 단계에서 vo2가 None: {none_vo2}개 / {len(exercise_data)}개")
            
            # bike_power, fat_oxidation, cho_oxidation이 모두 있는 데이터
            valid_for_analysis = [
                bd for bd in exercise_data
                if bd.bike_power is not None
                and bd.fat_oxidation is not None
                and bd.cho_oxidation is not None
            ]
            print(f"분석 가능한 데이터 (power, fat_ox, cho_ox 모두 존재): {len(valid_for_analysis)}개")
            
            if valid_for_analysis:
                print("\n분석 가능한 첫 5개의 vo2/vco2:")
                for i, bd in enumerate(valid_for_analysis[:5]):
                    print(f"  {i}: power={bd.bike_power}, vo2={bd.vo2}, vco2={bd.vco2}")
                    print(f"      fat_ox={bd.fat_oxidation}, cho_ox={bd.cho_oxidation}")
        else:
            print("\n❌ Exercise 단계 데이터 없음!")

if __name__ == "__main__":
    asyncio.run(check_specific_test())
