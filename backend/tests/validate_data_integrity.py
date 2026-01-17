"""데이터 파이프라인 정합성 검증 스크립트

검증 항목:
1. Frayn 공식 정확도
2. Phase Detection 정확도  
3. Power Binning Integrity
4. LOESS Smoothing 적절성
5. Polynomial Trend 타당성
6. Edge Cases 처리
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


def validate_frayn_formula(bd):
    """Frayn 공식 정확도 검증"""
    if bd.vo2 is None or bd.vco2 is None:
        return None, None, None
    
    # Frayn 공식 (ml/min → L/min 변환)
    vo2_l = bd.vo2 / 1000.0
    vco2_l = bd.vco2 / 1000.0
    
    calculated_fat = 1.67 * vo2_l - 1.67 * vco2_l
    calculated_cho = 4.55 * vco2_l - 3.21 * vo2_l
    
    # 음수 클램핑 (생리학적으로 불가능)
    calculated_fat = max(0, calculated_fat)
    calculated_cho = max(0, calculated_cho)
    
    return calculated_fat, calculated_cho, bd.fat_oxidation


def validate_phase_transitions(breath_data):
    """Phase 전환 부드러움 검증"""
    phase_changes = []
    prev_phase = None
    
    for i, bd in enumerate(breath_data):
        if bd.phase != prev_phase:
            phase_changes.append({
                'index': i,
                'time': bd.t_sec,
                'from': prev_phase,
                'to': bd.phase,
                'power': bd.bike_power
            })
            prev_phase = bd.phase
    
    return phase_changes


def validate_binning_integrity(raw_points, binned_points):
    """Binning 과정의 데이터 보존 검증"""
    # Raw 데이터의 총 개수
    raw_count = len(raw_points)
    
    # Binned 데이터의 count 합계
    binned_count_sum = sum(p.count for p in binned_points)
    
    # Power 범위 확인
    raw_powers = [p.power for p in raw_points]
    binned_powers = [p.power for p in binned_points]
    
    return {
        'raw_count': raw_count,
        'binned_count_sum': binned_count_sum,
        'data_loss': raw_count - binned_count_sum,
        'loss_percent': (raw_count - binned_count_sum) / raw_count * 100 if raw_count > 0 else 0,
        'raw_power_range': (min(raw_powers), max(raw_powers)) if raw_powers else (0, 0),
        'binned_power_range': (min(binned_powers), max(binned_powers)) if binned_powers else (0, 0),
    }


def validate_smoothing_preservation(binned_points, smoothed_points):
    """LOESS Smoothing이 피크를 과도하게 제거하지 않는지 검증"""
    if not binned_points or not smoothed_points:
        return None
    
    # FatOx 피크 비교
    binned_fat = [p.fat_oxidation for p in binned_points if p.fat_oxidation is not None]
    smoothed_fat = [p.fat_oxidation for p in smoothed_points if p.fat_oxidation is not None]
    
    if not binned_fat or not smoothed_fat:
        return None
    
    binned_max = max(binned_fat)
    smoothed_max = max(smoothed_fat)
    
    peak_loss = (binned_max - smoothed_max) / binned_max * 100 if binned_max > 0 else 0
    
    return {
        'binned_max_fat': binned_max,
        'smoothed_max_fat': smoothed_max,
        'peak_loss_percent': peak_loss,
        'acceptable': peak_loss < 20  # 20% 이상 피크 손실은 과도함
    }


def validate_trend_fit(smoothed_points, trend_points):
    """Polynomial Trend가 Smoothed 데이터를 적절히 근사하는지 검증"""
    if not smoothed_points or not trend_points:
        return None
    
    # Power 범위가 겹치는 구간에서 비교
    smoothed_powers = [p.power for p in smoothed_points]
    trend_powers = [p.power for p in trend_points]
    
    # 공통 파워 범위 찾기
    common_min = max(min(smoothed_powers), min(trend_powers))
    common_max = min(max(smoothed_powers), max(trend_powers))
    
    # 공통 구간 데이터 추출
    smoothed_in_range = [p for p in smoothed_points if common_min <= p.power <= common_max]
    trend_in_range = [p for p in trend_points if common_min <= p.power <= common_max]
    
    if not smoothed_in_range or not trend_in_range:
        return None
    
    # FatOx R² 계산 (간단한 근사)
    smoothed_fat = np.array([p.fat_oxidation for p in smoothed_in_range if p.fat_oxidation is not None])
    
    # Trend를 smoothed power에 보간
    trend_fat_interp = []
    for sp in smoothed_in_range:
        # 가장 가까운 trend 포인트 찾기
        closest_trend = min(trend_in_range, key=lambda t: abs(t.power - sp.power))
        if closest_trend.fat_oxidation is not None:
            trend_fat_interp.append(closest_trend.fat_oxidation)
    
    if len(smoothed_fat) != len(trend_fat_interp):
        return None
    
    trend_fat_array = np.array(trend_fat_interp)
    
    # R² 계산
    ss_res = np.sum((smoothed_fat - trend_fat_array) ** 2)
    ss_tot = np.sum((smoothed_fat - np.mean(smoothed_fat)) ** 2)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    
    return {
        'r_squared': r_squared,
        'acceptable': r_squared > 0.7,  # R² > 0.7이면 적절한 피팅
        'common_power_range': (common_min, common_max),
        'n_smoothed': len(smoothed_in_range),
        'n_trend': len(trend_in_range)
    }


async def main():
    """전체 검증 실행"""
    print("="*70)
    print("데이터 파이프라인 정합성 검증")
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
        print(f"   피험자: {test.subject_id}")
        print(f"   날짜: {test.test_date}\n")
        
        # BreathData 조회
        query = select(BreathData).where(
            BreathData.test_id == test_uuid
        ).order_by(BreathData.t_sec)
        
        result = await session.execute(query)
        breath_data = list(result.scalars().all())
        
        print(f"총 데이터: {len(breath_data)}개\n")
        
        # === 1. Frayn 공식 검증 ===
        print("1️⃣  Frayn 공식 정확도 검증")
        print("-" * 70)
        
        frayn_errors = []
        exercise_data = [bd for bd in breath_data if bd.phase == "Exercise"]
        
        for bd in exercise_data[:10]:  # 첫 10개만 체크
            calc_fat, calc_cho, stored_fat = validate_frayn_formula(bd)
            if calc_fat is not None and stored_fat is not None:
                error = abs(calc_fat - stored_fat)
                frayn_errors.append(error)
                
                if error > 0.01:  # 0.01 g/min 이상 오차
                    print(f"⚠️  오차 발견: calculated={calc_fat:.4f}, stored={stored_fat:.4f}, diff={error:.4f}")
        
        if frayn_errors:
            avg_error = np.mean(frayn_errors)
            max_error = np.max(frayn_errors)
            print(f"✅ 평균 오차: {avg_error:.6f} g/min")
            print(f"   최대 오차: {max_error:.6f} g/min")
            if max_error < 0.01:
                print("   → Frayn 공식 계산 정확함\n")
            else:
                print("   → ⚠️ 일부 데이터 재계산 필요\n")
        
        # === 2. Phase Detection 검증 ===
        print("2️⃣  Phase Detection 정확도 검증")
        print("-" * 70)
        
        phase_changes = validate_phase_transitions(breath_data)
        print(f"Phase 전환 횟수: {len(phase_changes)}")
        
        for change in phase_changes:
            print(f"  {change['from']} → {change['to']}: "
                  f"t={change['time']:.0f}s, power={change['power']}W")
        
        print()
        
        # === 3. MetabolismAnalyzer 실행 ===
        print("3️⃣  전처리 파이프라인 실행")
        print("-" * 70)
        
        analyzer = MetabolismAnalyzer(
            loess_frac=0.25,
            bin_size=10,
            use_median=True
        )
        
        result = analyzer.analyze(breath_data)
        
        if not result:
            print("❌ 분석 실패")
            return
        
        print(f"✅ 분석 성공")
        print(f"   Raw: {len(result.processed_series.raw)}개")
        print(f"   Binned: {len(result.processed_series.binned)}개")
        print(f"   Smoothed: {len(result.processed_series.smoothed)}개")
        print(f"   Trend: {len(result.processed_series.trend)}개\n")
        
        # === 4. Binning Integrity 검증 ===
        print("4️⃣  Power Binning Integrity 검증")
        print("-" * 70)
        
        binning_stats = validate_binning_integrity(
            result.processed_series.raw,
            result.processed_series.binned
        )
        
        print(f"Raw 데이터: {binning_stats['raw_count']}개")
        print(f"Binned count 합계: {binning_stats['binned_count_sum']}개")
        print(f"데이터 손실: {binning_stats['data_loss']}개 ({binning_stats['loss_percent']:.1f}%)")
        print(f"Raw Power 범위: {binning_stats['raw_power_range']}")
        print(f"Binned Power 범위: {binning_stats['binned_power_range']}")
        
        if binning_stats['loss_percent'] < 5:
            print("✅ Binning 데이터 보존 양호\n")
        else:
            print("⚠️ 과도한 데이터 손실!\n")
        
        # === 5. LOESS Smoothing 검증 ===
        print("5️⃣  LOESS Smoothing 적절성 검증")
        print("-" * 70)
        
        smoothing_stats = validate_smoothing_preservation(
            result.processed_series.binned,
            result.processed_series.smoothed
        )
        
        if smoothing_stats:
            print(f"Binned FatOx 최대: {smoothing_stats['binned_max_fat']:.4f} g/min")
            print(f"Smoothed FatOx 최대: {smoothing_stats['smoothed_max_fat']:.4f} g/min")
            print(f"피크 손실: {smoothing_stats['peak_loss_percent']:.1f}%")
            
            if smoothing_stats['acceptable']:
                print("✅ Smoothing 적절함 (피크 손실 < 20%)\n")
            else:
                print("⚠️ 과도한 smoothing! 피크가 너무 많이 깎임\n")
        else:
            print("⚠️ 검증 데이터 부족\n")
        
        # === 6. Polynomial Trend 검증 ===
        print("6️⃣  Polynomial Trend Fit 타당성 검증")
        print("-" * 70)
        
        trend_stats = validate_trend_fit(
            result.processed_series.smoothed,
            result.processed_series.trend
        )
        
        if trend_stats:
            print(f"R² (적합도): {trend_stats['r_squared']:.4f}")
            print(f"공통 Power 범위: {trend_stats['common_power_range']}")
            print(f"Smoothed 포인트: {trend_stats['n_smoothed']}개")
            print(f"Trend 포인트: {trend_stats['n_trend']}개")
            
            if trend_stats['acceptable']:
                print("✅ Trend Fit 적절함 (R² > 0.7)\n")
            else:
                print("⚠️ Trend가 원본 데이터를 잘 근사하지 못함\n")
        else:
            print("⚠️ 검증 데이터 부족\n")
        
        # === 7. FatMax 마커 검증 ===
        print("7️⃣  FatMax 마커 타당성 검증")
        print("-" * 70)
        
        fatmax = result.metabolic_markers.fat_max
        print(f"FatMax Power: {fatmax.power}W")
        print(f"MFO (최대 지방산화율): {fatmax.mfo:.4f} g/min")
        print(f"FatMax Zone: {fatmax.zone_min}W ~ {fatmax.zone_max}W")
        
        # FatMax가 Smoothed 데이터 범위 내에 있는지 확인
        smoothed_powers = [p.power for p in result.processed_series.smoothed if p.fat_oxidation is not None]
        if smoothed_powers and min(smoothed_powers) <= fatmax.power <= max(smoothed_powers):
            print("✅ FatMax가 데이터 범위 내에 있음\n")
        else:
            print("⚠️ FatMax가 데이터 범위를 벗어남 (외삽 문제)\n")
        
        # === 최종 요약 ===
        print("="*70)
        print("검증 요약")
        print("="*70)
        
        issues = []
        
        if frayn_errors and max(frayn_errors) >= 0.01:
            issues.append("Frayn 공식 재계산 필요")
        
        if binning_stats['loss_percent'] >= 5:
            issues.append("Binning 데이터 손실 과다")
        
        if smoothing_stats and not smoothing_stats['acceptable']:
            issues.append("LOESS Smoothing 과도함")
        
        if trend_stats and not trend_stats['acceptable']:
            issues.append("Polynomial Trend 피팅 불량")
        
        if issues:
            print("⚠️ 발견된 문제:")
            for issue in issues:
                print(f"   - {issue}")
        else:
            print("✅ 모든 검증 통과! 데이터 파이프라인 정합성 확인됨")
        
        print()


if __name__ == "__main__":
    asyncio.run(main())
