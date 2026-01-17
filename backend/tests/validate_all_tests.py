"""Validate All CPET Tests in Database - 대사 분석 유효성 검증"""

import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload

from app.core.config import settings
from app.models.cpet_test import CPETTest
from app.models.breath_data import BreathData
from app.services.data_validator import DataValidator
from app.schemas.test import ProtocolType


class TestValidator:
    """모든 테스트 데이터 검증"""
    
    def __init__(self):
        self.engine = create_async_engine(settings.database_url, echo=False)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.validator = DataValidator()
        self.results = []
    
    async def get_all_tests(self) -> List[CPETTest]:
        """DB에서 모든 테스트 가져오기"""
        async with self.async_session() as session:
            result = await session.execute(
                select(CPETTest)
                .options(selectinload(CPETTest.breath_data))
                .order_by(CPETTest.test_date.desc())
            )
            tests = list(result.scalars().all())
            return tests
    
    def breath_data_to_df(self, breath_data: List[BreathData]) -> pd.DataFrame:
        """BreathData 리스트를 DataFrame으로 변환"""
        if not breath_data:
            return pd.DataFrame()
        
        data = []
        for bd in breath_data:
            data.append({
                't_sec': bd.t_sec,
                'bike_power': bd.bike_power,
                'hr': bd.hr,
                'vo2': bd.vo2,
                'vco2': bd.vco2,
                've': bd.ve,
                'rer': bd.rer,
                'fat_oxidation': bd.fat_oxidation,
                'cho_oxidation': bd.cho_oxidation,
            })
        
        return pd.DataFrame(data)
    
    async def validate_all(self):
        """모든 테스트 검증"""
        print("=" * 80)
        print("CPET Database - Validation Report")
        print("=" * 80)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        tests = await self.get_all_tests()
        print(f"Total Tests in Database: {len(tests)}")
        print("=" * 80)
        print()
        
        if not tests:
            print("No tests found in database.")
            return
        
        # 통계 초기화
        stats = {
            'total': 0,
            'valid': 0,
            'invalid': 0,
            'ramp': 0,
            'interval': 0,
            'steady_state': 0,
            'unknown': 0,
            'no_breath_data': 0,
            'quality_scores': []
        }
        
        # 각 테스트 검증
        for idx, test in enumerate(tests, 1):
            stats['total'] += 1
            
            # BreathData가 없는 경우
            if not test.breath_data or len(test.breath_data) == 0:
                stats['no_breath_data'] += 1
                self._print_test_header(idx, test)
                print(f"  ❌ No breath data available")
                print()
                continue
            
            # DataFrame 변환
            df = self.breath_data_to_df(test.breath_data)
            
            # 검증 실행
            result = self.validator.validate(df)
            
            # 통계 업데이트
            if result.is_valid:
                stats['valid'] += 1
            else:
                stats['invalid'] += 1
            
            if result.protocol_type == ProtocolType.RAMP:
                stats['ramp'] += 1
            elif result.protocol_type == ProtocolType.INTERVAL:
                stats['interval'] += 1
            elif result.protocol_type == ProtocolType.STEADY_STATE:
                stats['steady_state'] += 1
            else:
                stats['unknown'] += 1
            
            stats['quality_scores'].append(result.quality_score)
            
            # 결과 저장
            self.results.append({
                'test_id': str(test.test_id),
                'test_date': test.test_date,
                'subject_id': str(test.subject_id),
                'result': result
            })
            
            # 출력
            self._print_test_result(idx, test, result)
            
            # DB 업데이트
            await self._save_validation_result(test, result)
        
        # 최종 요약
        self._print_summary(stats)
    
    def _print_test_header(self, idx: int, test: CPETTest):
        """테스트 헤더 출력"""
        test_date = test.test_date.strftime('%Y-%m-%d') if test.test_date else 'N/A'
        print(f"[{idx}] Test ID: {str(test.test_id)[:8]}... | Date: {test_date}")
        if test.source_filename:
            print(f"  File: {test.source_filename}")
    
    def _print_test_result(self, idx: int, test: CPETTest, result):
        """테스트 결과 출력"""
        self._print_test_header(idx, test)
        
        # 상태 아이콘
        if result.is_valid:
            status_icon = "✅"
            status_text = "VALID"
        else:
            status_icon = "❌"
            status_text = "INVALID"
        
        # 프로토콜 아이콘
        protocol_icons = {
            ProtocolType.RAMP: "📈",
            ProtocolType.INTERVAL: "📊",
            ProtocolType.STEADY_STATE: "📉",
            ProtocolType.UNKNOWN: "❓"
        }
        protocol_icon = protocol_icons.get(result.protocol_type, "❓")
        
        print(f"  {status_icon} Status: {status_text}")
        print(f"  {protocol_icon} Protocol: {result.protocol_type.value}")
        print(f"  📊 Quality: {result.quality_score:.2f}/1.00")
        
        # 상세 정보
        metadata = result.metadata
        print(f"  ⏱️  Duration: {metadata.get('duration_min', 0):.1f} min")
        print(f"  ⚡ Max Power: {metadata.get('max_power', 0):.0f}W")
        print(f"  💓 HR Dropout: {metadata.get('hr_dropout_rate', 0):.1%}")
        print(f"  🫁 Gas Dropout: VO2={metadata.get('vo2_dropout_rate', 0):.1%}, "
              f"VCO2={metadata.get('vco2_dropout_rate', 0):.1%}")
        
        if result.power_time_correlation is not None:
            print(f"  📐 Power-Time Corr: r={result.power_time_correlation:.3f}")
        
        # 실패 사유
        if result.reason:
            print(f"  ⚠️  Issues:")
            for reason in result.reason:
                print(f"     • {reason}")
        
        # DB 저장된 상태와 비교
        if test.parsing_status:
            print(f"  💾 DB Status: {test.parsing_status}")
        if test.data_quality_score is not None:
            print(f"  💾 DB Quality: {test.data_quality_score:.2f}")
        
        print()
    
    async def _save_validation_result(self, test: CPETTest, result):
        """검증 결과를 DB에 저장"""
        async with self.async_session() as session:
            # 테스트 다시 가져오기 (현재 세션에 attach)
            db_test = await session.get(CPETTest, test.test_id)
            if db_test:
                db_test.data_quality_score = result.quality_score
                db_test.protocol_type = result.protocol_type.value
                await session.commit()
    
    def _print_summary(self, stats: Dict[str, Any]):
        """최종 요약 출력"""
        print("=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)
        
        print(f"\n📊 Overall Statistics:")
        print(f"  Total Tests: {stats['total']}")
        print(f"  With Breath Data: {stats['total'] - stats['no_breath_data']}")
        print(f"  No Breath Data: {stats['no_breath_data']}")
        
        if stats['total'] - stats['no_breath_data'] > 0:
            valid_rate = stats['valid'] / (stats['total'] - stats['no_breath_data']) * 100
            print(f"\n✅ Validation Results:")
            print(f"  Valid: {stats['valid']} ({valid_rate:.1f}%)")
            print(f"  Invalid: {stats['invalid']} ({100-valid_rate:.1f}%)")
            
            print(f"\n📈 Protocol Distribution:")
            print(f"  RAMP: {stats['ramp']}")
            print(f"  INTERVAL: {stats['interval']}")
            print(f"  STEADY_STATE: {stats['steady_state']}")
            print(f"  UNKNOWN: {stats['unknown']}")
            
            if stats['quality_scores']:
                avg_quality = sum(stats['quality_scores']) / len(stats['quality_scores'])
                min_quality = min(stats['quality_scores'])
                max_quality = max(stats['quality_scores'])
                
                print(f"\n📊 Quality Scores:")
                print(f"  Average: {avg_quality:.2f}")
                print(f"  Min: {min_quality:.2f}")
                print(f"  Max: {max_quality:.2f}")
                
                # 품질 분포
                excellent = sum(1 for q in stats['quality_scores'] if q >= 0.95)
                good = sum(1 for q in stats['quality_scores'] if 0.80 <= q < 0.95)
                fair = sum(1 for q in stats['quality_scores'] if 0.60 <= q < 0.80)
                poor = sum(1 for q in stats['quality_scores'] if q < 0.60)
                
                print(f"\n  Quality Distribution:")
                print(f"    Excellent (≥0.95): {excellent}")
                print(f"    Good (0.80-0.95): {good}")
                print(f"    Fair (0.60-0.80): {fair}")
                print(f"    Poor (<0.60): {poor}")
        
        print("\n" + "=" * 80)
        
        # 권장 사항
        if stats['invalid'] > 0:
            print(f"\n⚠️  Recommendations:")
            print(f"  • {stats['invalid']} test(s) failed validation")
            print(f"  • Review failed tests for sensor issues or incomplete data")
            print(f"  • Consider re-testing subjects with invalid data")
        
        if stats['interval'] > 0 or stats['steady_state'] > 0:
            non_ramp = stats['interval'] + stats['steady_state']
            print(f"\n📊 Protocol Analysis:")
            print(f"  • {non_ramp} test(s) are not RAMP protocols")
            print(f"  • These tests cannot use standard FatMax/VT analysis")
            print(f"  • Consider implementing protocol-specific analysis")
        
        if stats['quality_scores']:
            low_quality = sum(1 for q in stats['quality_scores'] if q < 0.80)
            if low_quality > 0:
                print(f"\n⚠️  Data Quality:")
                print(f"  • {low_quality} test(s) have quality score < 0.80")
                print(f"  • Review sensor calibration and test protocols")
        
        print()
    
    async def close(self):
        """연결 종료"""
        await self.engine.dispose()


async def main():
    """메인 함수"""
    validator = TestValidator()
    try:
        await validator.validate_all()
    finally:
        await validator.close()


if __name__ == "__main__":
    asyncio.run(main())
