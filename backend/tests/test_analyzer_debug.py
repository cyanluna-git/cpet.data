"""MetabolismAnalyzer 디버깅 - vo2/vco2 필드 누락 원인 분석"""
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
from app.services.metabolism_analysis import MetabolismAnalyzer

async def test_analyzer_input():
    """MetabolismAnalyzer에 전달되는 breath_data 확인"""
    
    # DB 연결
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # 최신 테스트 조회
        test_query = select(CPETTest).order_by(CPETTest.test_date.desc()).limit(1)
        test_result = await session.execute(test_query)
        test = test_result.scalar_one_or_none()
        
        if not test:
            print("❌ 테스트 데이터 없음")
            return
        
        print(f"✅ 테스트 ID: {test.test_id}\n")
        
        # test.py의 get_analysis()와 동일한 쿼리
        query = select(BreathData).where(
            BreathData.test_id == test.test_id
        ).order_by(BreathData.t_sec)
        
        result = await session.execute(query)
        breath_data = list(result.scalars().all())
        
        print(f"총 BreathData: {len(breath_data)}")
        
        # Exercise phase만 필터링
        exercise_data = [bd for bd in breath_data if bd.phase == "Exercise"]
        print(f"Exercise phase: {len(exercise_data)}")
        
        # MetabolismAnalyzer 생성 및 분석
        analyzer = MetabolismAnalyzer(
            loess_frac=0.25,
            bin_size=10,
            use_median=True
        )
        
        # _apply_phase_trimming 직접 호출하여 필터링 결과 확인
        filtered_data = analyzer._apply_phase_trimming(breath_data)
        print(f"\nPhase trimming 후: {len(filtered_data)}")
        
        if filtered_data:
            print("\nFiltered 데이터 첫 5개의 vo2/vco2:")
            for i, bd in enumerate(filtered_data[:5]):
                vo2 = getattr(bd, 'vo2', None)
                vco2 = getattr(bd, 'vco2', None)
                power = getattr(bd, 'bike_power', None)
                fat_ox = getattr(bd, 'fat_oxidation', None)
                cho_ox = getattr(bd, 'cho_oxidation', None)
                phase = getattr(bd, 'phase', None)
                
                print(f"  {i}: power={power}, vo2={vo2}, vco2={vco2}")
                print(f"      fat_ox={fat_ox}, cho_ox={cho_ox}, phase={phase}")
        else:
            print("⚠️ Phase trimming 후 데이터 없음!")
            return
        
        # _extract_raw_points 직접 호출
        raw_points = analyzer._extract_raw_points(filtered_data)
        print(f"\n_extract_raw_points 결과: {len(raw_points)} points")
        
        if raw_points:
            print("\nRaw points 첫 5개의 vo2/vco2:")
            for i, pt in enumerate(raw_points[:5]):
                print(f"  {i}: power={pt.power}, vo2={pt.vo2}, vco2={pt.vco2}")
                print(f"      fat_ox={pt.fat_oxidation}, cho_ox={pt.cho_oxidation}")
        
        # 전체 analyze() 호출
        print("\n" + "="*60)
        print("MetabolismAnalyzer.analyze() 호출:")
        result = analyzer.analyze(breath_data)
        
        if result:
            print(f"✅ 분석 성공")
            print(f"   Raw points: {len(result.processed_series.raw)}")
            print(f"   Binned points: {len(result.processed_series.binned)}")
            print(f"   Smoothed points: {len(result.processed_series.smoothed)}")
            print(f"   Trend points: {len(result.processed_series.trend)}")
            
            if result.processed_series.raw:
                print("\n   Raw series 첫 5개의 vo2/vco2:")
                for i, pt in enumerate(result.processed_series.raw[:5]):
                    print(f"     {i}: power={pt.power}, vo2={pt.vo2}, vco2={pt.vco2}")
        else:
            print("❌ 분석 실패 (None 반환)")

if __name__ == "__main__":
    asyncio.run(test_analyzer_input())
