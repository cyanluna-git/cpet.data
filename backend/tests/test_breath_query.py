"""BreathData 쿼리 테스트 - vo2/vco2 필드 로딩 확인"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncio
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.models.breath_data import BreathData
from app.models.cpet_test import CPETTest
from app.core.config import settings

async def test_breath_data_query():
    """BreathData 쿼리 시 vo2/vco2 필드가 제대로 로드되는지 확인"""
    
    # DB 연결
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # 최신 테스트 1개 조회
        test_query = select(CPETTest).order_by(CPETTest.test_date.desc()).limit(1)
        test_result = await session.execute(test_query)
        test = test_result.scalar_one_or_none()
        
        if not test:
            print("❌ 테스트 데이터 없음")
            return
        
        print(f"✅ 테스트 ID: {test.test_id}")
        print(f"   Subject ID: {test.subject_id}")
        print(f"   Test Date: {test.test_date}\n")
        
        # Exercise 단계 breath_data 조회 (test.py의 get_analysis와 동일한 방식)
        query = select(BreathData).where(
            BreathData.test_id == test.test_id
        ).order_by(BreathData.t_sec).limit(10)
        
        result = await session.execute(query)
        breath_data = list(result.scalars().all())
        
        print(f"조회된 BreathData 수: {len(breath_data)}\n")
        
        # 첫 10개 데이터의 vo2/vco2 확인
        print("첫 10개 데이터의 vo2/vco2 (getattr 사용):")
        for i, bd in enumerate(breath_data):
            vo2 = getattr(bd, 'vo2', None)
            vco2 = getattr(bd, 'vco2', None)
            power = getattr(bd, 'bike_power', None)
            phase = getattr(bd, 'phase', None)
            
            print(f"  {i}: power={power}, vo2={vo2}, vco2={vco2}, phase={phase}")
            
            # 직접 접근도 시도
            try:
                direct_vo2 = bd.vo2
                direct_vco2 = bd.vco2
                print(f"      (직접접근: vo2={direct_vo2}, vco2={direct_vco2})")
            except Exception as e:
                print(f"      (직접접근 실패: {e})")
        
        print("\n" + "="*60)
        print("BreathData 객체 속성 확인 (첫 번째 데이터):")
        if breath_data:
            bd = breath_data[0]
            print(f"  dir(bd)에 'vo2' 있는가? {'vo2' in dir(bd)}")
            print(f"  hasattr(bd, 'vo2')? {hasattr(bd, 'vo2')}")
            print(f"  bd.__dict__.keys(): {list(bd.__dict__.keys())}")

if __name__ == "__main__":
    asyncio.run(test_breath_data_query())
