"""Phase 2: 생리학적 개형(Physiological Pattern) 검증

검증 항목:
1. FatMax 위치 타당성 (40-65% VO2max)
2. Fat/CHO Crossover 존재 및 위치 (RER 0.85-1.0 구간)
3. RER 추이 패턴 (Rest → Exercise → Peak)
4. 산화율 증가 패턴 (Fat: 역U자, CHO: 지수증가)
"""
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
from app.services.metabolism_analysis import MetabolismAnalyzer
import numpy as np

TEST_ID = "c91339b9-c0ce-434d-b4ad-3c77452ed928"  # Park Yongdoo


def validate_fatmax_position(fatmax_power, vo2_at_fatmax, vo2max, smoothed_points):
    """FatMax 위치가 생리학적으로 타당한지 검증"""
    
    # VO2max 대비 FatMax 위치 (일반적으로 40-65%)
    vo2_percent = (vo2_at_fatmax / vo2max * 100) if vo2max > 0 else 0
    
    # FatMax가 smoothed 데이터의 중간 구간에 있는지 확인
    powers = [p.power for p in smoothed_points]
    if powers:
        power_range = max(powers) - min(powers)
        fatmax_position = (fatmax_power - min(powers)) / power_range if power_range > 0 else 0
    else:
        fatmax_position = 0
    
    return {
        'vo2_percent': vo2_percent,
        'valid_vo2_range': 40 <= vo2_percent <= 70,  # 약간 여유있게 70%까지
        'power_position': fatmax_position,
        'valid_position': 0.3 <= fatmax_position <= 0.7,  # 파워 범위의 중간 구간
    }


def validate_crossover_point(smoothed_points):
    """Fat/CHO Crossover 지점 검증"""
    
    # Fat >= CHO인 구간과 Fat < CHO인 구간 찾기
    crossover_candidates = []
    
    for i in range(len(smoothed_points) - 1):
        curr = smoothed_points[i]
        next_pt = smoothed_points[i + 1]
        
        if (curr.fat_oxidation is None or curr.cho_oxidation is None or
            next_pt.fat_oxidation is None or next_pt.cho_oxidation is None):
            continue
        
        # 교차 감지 (부호가 바뀌는 지점)
        curr_diff = curr.fat_oxidation - curr.cho_oxidation
        next_diff = next_pt.fat_oxidation - next_pt.cho_oxidation
        
        if curr_diff * next_diff <= 0:  # 부호가 다르거나 0
            # 선형 보간으로 교차 지점 계산
            if abs(curr_diff - next_diff) > 0.001:
                ratio = abs(curr_diff) / abs(curr_diff - next_diff)
                crossover_power = curr.power + (next_pt.power - curr.power) * ratio
                
                # 해당 지점의 RER 추정
                crossover_rer = curr.rer + (next_pt.rer - curr.rer) * ratio if curr.rer and next_pt.rer else None
                
                crossover_candidates.append({
                    'power': crossover_power,
                    'rer': crossover_rer,
                    'fat_value': curr.fat_oxidation + (next_pt.fat_oxidation - curr.fat_oxidation) * ratio,
                    'cho_value': curr.cho_oxidation + (next_pt.cho_oxidation - curr.cho_oxidation) * ratio,
                })
    
    if crossover_candidates:
        # 가장 첫 번째 교차점 (일반적으로 의미있는 crossover)
        crossover = crossover_candidates[0]
        valid_rer = crossover['rer'] and 0.85 <= crossover['rer'] <= 1.05
        
        return {
            'exists': True,
            'power': crossover['power'],
            'rer': crossover['rer'],
            'fat_value': crossover['fat_value'],
            'cho_value': crossover['cho_value'],
            'valid_rer_range': valid_rer,
        }
    else:
        return {
            'exists': False,
            'power': None,
            'rer': None,
        }


def validate_rer_progression(raw_points):
    """RER 추이가 생리학적으로 타당한지 검증"""
    
    # Phase별 RER 평균
    phase_rer = {}
    
    for point in raw_points:
        if point.rer is None:
            continue
        
        # Phase 정보 (없으면 power 기반 추정)
        if hasattr(point, 'phase') and point.phase:
            phase = point.phase
        else:
            # Power 기반 추정
            if point.power < 30:
                phase = 'Rest'
            elif point.power < 100:
                phase = 'Warmup'
            else:
                phase = 'Exercise'
        
        if phase not in phase_rer:
            phase_rer[phase] = []
        phase_rer[phase].append(point.rer)
    
    # 각 Phase의 평균 RER
    avg_rer = {phase: np.mean(rers) for phase, rers in phase_rer.items()}
    
    # 검증 기준
    rest_valid = avg_rer.get('Rest', 0.8) < 0.9  # Rest는 0.7-0.85 정도
    exercise_increasing = True  # Exercise에서 증가하는지
    
    if 'Rest' in avg_rer and 'Exercise' in avg_rer:
        exercise_increasing = avg_rer['Exercise'] > avg_rer['Rest']
    
    # Peak RER (높은 파워 구간)
    high_power_rers = [p.rer for p in raw_points if p.rer and p.power > 200]
    peak_rer = np.mean(high_power_rers) if high_power_rers else None
    peak_valid = peak_rer and peak_rer > 1.0 if peak_rer else False
    
    return {
        'phase_avg': avg_rer,
        'rest_valid': rest_valid,
        'exercise_increasing': exercise_increasing,
        'peak_rer': peak_rer,
        'peak_valid': peak_valid,
    }


def validate_oxidation_patterns(smoothed_points):
    """Fat/CHO 산화율 패턴 검증"""
    
    if len(smoothed_points) < 5:
        return None
    
    # Fat Oxidation 패턴 - 역 U자형 확인
    fat_values = [p.fat_oxidation for p in smoothed_points if p.fat_oxidation is not None]
    powers = [p.power for p in smoothed_points if p.fat_oxidation is not None]
    
    if len(fat_values) < 5:
        return None
    
    # 최대값이 중간 구간에 있는지 확인
    max_fat_idx = np.argmax(fat_values)
    fat_peak_position = max_fat_idx / len(fat_values)
    
    # Fat이 초반에 증가하고 후반에 감소하는지 확인
    first_third = fat_values[:len(fat_values)//3]
    last_third = fat_values[-len(fat_values)//3:]
    
    fat_increases_initially = len(first_third) > 1 and fat_values[len(first_third)-1] > fat_values[0]
    fat_decreases_finally = len(last_third) > 1 and fat_values[-1] < max(fat_values)
    
    # CHO Oxidation 패턴 - 지수 증가 확인
    cho_values = [p.cho_oxidation for p in smoothed_points if p.cho_oxidation is not None]
    
    if len(cho_values) >= 5:
        # 후반부가 초반부보다 높은지 (증가 추세)
        cho_initial = np.mean(cho_values[:len(cho_values)//3])
        cho_final = np.mean(cho_values[-len(cho_values)//3:])
        cho_increases = cho_final > cho_initial * 1.5  # 최소 1.5배 증가
    else:
        cho_increases = False
    
    return {
        'fat_peak_position': fat_peak_position,
        'fat_peak_in_middle': 0.3 <= fat_peak_position <= 0.7,
        'fat_increases_initially': fat_increases_initially,
        'fat_decreases_finally': fat_decreases_finally,
        'fat_inverse_u_shape': fat_increases_initially and fat_decreases_finally,
        'cho_increases': cho_increases,
        'cho_fold_change': (cho_final / cho_initial) if cho_increases and cho_initial > 0 else None,
    }


async def main():
    """Phase 2 생리학적 검증 실행"""
    print("="*70)
    print("Phase 2: 생리학적 개형 검증")
    print("="*70 + "\n")
    
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        test_uuid = UUID(TEST_ID)
        
        # 테스트 및 데이터 로드
        test_query = select(CPETTest).where(CPETTest.test_id == test_uuid)
        test_result = await session.execute(test_query)
        test = test_result.scalar_one_or_none()
        
        if not test:
            print(f"❌ 테스트 없음: {TEST_ID}")
            return
        
        print(f"📋 테스트: {TEST_ID}")
        print(f"   VO2MAX: {test.vo2_max} ml/min\n")
        
        # BreathData 조회
        query = select(BreathData).where(
            BreathData.test_id == test_uuid
        ).order_by(BreathData.t_sec)
        
        result = await session.execute(query)
        breath_data = list(result.scalars().all())
        
        # MetabolismAnalyzer 실행
        analyzer = MetabolismAnalyzer(
            loess_frac=0.25,
            bin_size=10,
            use_median=True
        )
        
        analysis_result = analyzer.analyze(breath_data)
        
        if not analysis_result:
            print("❌ 분석 실패")
            return
        
        # === 1. FatMax 위치 타당성 ===
        print("1️⃣  FatMax 위치 타당성 검증")
        print("-" * 70)
        
        fatmax = analysis_result.metabolic_markers.fat_max
        
        # FatMax 지점의 VO2 찾기
        vo2_at_fatmax = None
        for p in analysis_result.processed_series.smoothed:
            if abs(p.power - fatmax.power) < 5 and p.vo2:
                vo2_at_fatmax = p.vo2
                break
        
        if vo2_at_fatmax is None:
            # Raw 데이터에서 찾기
            for p in analysis_result.processed_series.raw:
                if abs(p.power - fatmax.power) < 10 and p.vo2:
                    vo2_at_fatmax = p.vo2
                    break
        
        if vo2_at_fatmax and test.vo2_max:
            fatmax_validation = validate_fatmax_position(
                fatmax.power,
                vo2_at_fatmax,
                test.vo2_max,
                analysis_result.processed_series.smoothed
            )
            
            print(f"FatMax Power: {fatmax.power}W")
            print(f"FatMax VO2: {vo2_at_fatmax:.0f} ml/min")
            print(f"VO2max: {test.vo2_max:.0f} ml/min")
            print(f"FatMax at {fatmax_validation['vo2_percent']:.1f}% of VO2max")
            
            if fatmax_validation['valid_vo2_range']:
                print(f"✅ PASS: FatMax 위치가 생리학적 범위 내 (40-70% VO2max)")
            else:
                print(f"⚠️ WARNING: FatMax가 비정상적 위치 (권장: 40-70% VO2max)")
            
            if fatmax_validation['valid_position']:
                print(f"✅ PASS: FatMax가 파워 범위 중간 구간에 위치")
            else:
                print(f"⚠️ WARNING: FatMax가 파워 범위 극단에 위치 (데이터 부족 가능성)")
        else:
            print("⚠️ SKIP: VO2 데이터 부족으로 검증 불가")
        
        print()
        
        # === 2. Fat/CHO Crossover ===
        print("2️⃣  Fat/CHO Crossover 지점 검증")
        print("-" * 70)
        
        crossover = validate_crossover_point(analysis_result.processed_series.smoothed)
        
        if crossover['exists']:
            print(f"✅ Crossover 존재: {crossover['power']:.0f}W")
            print(f"   Fat Oxidation: {crossover['fat_value']:.3f} g/min")
            print(f"   CHO Oxidation: {crossover['cho_value']:.3f} g/min")
            
            if crossover['rer']:
                print(f"   RER at Crossover: {crossover['rer']:.3f}")
                
                if crossover['valid_rer_range']:
                    print(f"   ✅ PASS: Crossover RER이 생리학적 범위 내 (0.85-1.05)")
                else:
                    print(f"   ⚠️ WARNING: Crossover RER이 비정상적 ({crossover['rer']:.3f})")
            else:
                print(f"   ⚠️ RER 데이터 없음")
        else:
            print("⚠️ Crossover 미감지: Fat이 항상 CHO보다 높거나 낮음")
            print("   (매우 낮거나 높은 강도 테스트에서는 정상일 수 있음)")
        
        print()
        
        # === 3. RER 추이 패턴 ===
        print("3️⃣  RER 추이 패턴 검증")
        print("-" * 70)
        
        rer_validation = validate_rer_progression(analysis_result.processed_series.raw)
        
        print("Phase별 평균 RER:")
        for phase, avg in rer_validation['phase_avg'].items():
            print(f"  {phase}: {avg:.3f}")
        
        print()
        
        if rer_validation['rest_valid']:
            print("✅ PASS: Rest RER이 정상 범위 (< 0.9)")
        else:
            print("⚠️ WARNING: Rest RER이 높음 (과호흡 가능성)")
        
        if rer_validation['exercise_increasing']:
            print("✅ PASS: Exercise로 갈수록 RER 증가 (정상 패턴)")
        else:
            print("⚠️ WARNING: RER이 증가하지 않음")
        
        if rer_validation['peak_rer']:
            print(f"Peak RER (고강도 구간): {rer_validation['peak_rer']:.3f}")
            if rer_validation['peak_valid']:
                print("✅ PASS: Peak RER > 1.0 (무산소 대사 활성화)")
            else:
                print("⚠️ WARNING: Peak RER이 낮음 (최대 노력 미달 가능성)")
        
        print()
        
        # === 4. 산화율 패턴 ===
        print("4️⃣  산화율 증가 패턴 검증")
        print("-" * 70)
        
        pattern_validation = validate_oxidation_patterns(analysis_result.processed_series.smoothed)
        
        if pattern_validation:
            print(f"Fat Oxidation 패턴:")
            print(f"  피크 위치: {pattern_validation['fat_peak_position']:.1%} (파워 범위 내)")
            
            if pattern_validation['fat_peak_in_middle']:
                print(f"  ✅ PASS: 피크가 중간 구간에 위치 (역 U자형)")
            else:
                print(f"  ⚠️ WARNING: 피크가 극단에 위치")
            
            if pattern_validation['fat_inverse_u_shape']:
                print(f"  ✅ PASS: 초반 증가 → 후반 감소 (정상 역 U자형)")
            else:
                if not pattern_validation['fat_increases_initially']:
                    print(f"  ⚠️ WARNING: 초반에 증가하지 않음")
                if not pattern_validation['fat_decreases_finally']:
                    print(f"  ⚠️ WARNING: 후반에 감소하지 않음 (데이터 범위 부족 가능성)")
            
            print()
            print(f"CHO Oxidation 패턴:")
            
            if pattern_validation['cho_increases']:
                fold = pattern_validation['cho_fold_change']
                print(f"  ✅ PASS: 지수 증가 패턴 ({fold:.1f}배 증가)")
            else:
                print(f"  ⚠️ WARNING: 증가 패턴 미약")
        else:
            print("⚠️ SKIP: 데이터 부족으로 검증 불가")
        
        print()
        
        # === 최종 요약 ===
        print("="*70)
        print("생리학적 검증 요약")
        print("="*70)
        
        issues = []
        passes = []
        
        # FatMax
        if vo2_at_fatmax and test.vo2_max:
            if fatmax_validation['valid_vo2_range'] and fatmax_validation['valid_position']:
                passes.append("FatMax 위치 타당")
            else:
                issues.append("FatMax 위치 비정상")
        
        # Crossover
        if crossover['exists'] and crossover['valid_rer_range']:
            passes.append("Crossover 정상")
        elif not crossover['exists']:
            issues.append("Crossover 미감지")
        
        # RER
        if rer_validation['rest_valid'] and rer_validation['exercise_increasing']:
            passes.append("RER 추이 정상")
        else:
            issues.append("RER 추이 비정상")
        
        # Pattern
        if pattern_validation and pattern_validation['fat_inverse_u_shape'] and pattern_validation['cho_increases']:
            passes.append("산화율 패턴 정상")
        elif pattern_validation:
            issues.append("산화율 패턴 비정상")
        
        if passes:
            print("✅ 통과 항목:")
            for p in passes:
                print(f"   - {p}")
        
        if issues:
            print("\n⚠️ 주의 항목:")
            for i in issues:
                print(f"   - {i}")
        else:
            print("\n🎉 모든 생리학적 패턴 검증 통과!")
        
        print()


if __name__ == "__main__":
    asyncio.run(main())
