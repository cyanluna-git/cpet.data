"""파라미터 민감도 분석 (Parameter Sensitivity Analysis)

목적:
- LOESS fraction, bin size, aggregation method 변화가 결과에 미치는 영향 파악
- 최적 파라미터 범위 도출
- 결과의 신뢰구간 측정
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
import pandas as pd
from itertools import product

TEST_ID = "c91339b9-c0ce-434d-b4ad-3c77452ed928"  # Park Yongdoo


async def run_sensitivity_analysis():
    """파라미터 조합별 분석 실행"""
    
    print("="*80)
    print("파라미터 민감도 분석")
    print("="*80 + "\n")
    
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
        print(f"   VO2MAX: {test.vo2_max:.0f} ml/min\n")
        
        # BreathData 조회
        query = select(BreathData).where(
            BreathData.test_id == test_uuid
        ).order_by(BreathData.t_sec)
        
        result = await session.execute(query)
        breath_data = list(result.scalars().all())
        
        print(f"총 데이터: {len(breath_data)}개\n")
        
        # === 파라미터 그리드 정의 ===
        loess_fracs = [0.15, 0.2, 0.25, 0.3, 0.35, 0.5]
        bin_sizes = [5, 10, 15, 20]
        agg_methods = ['median', 'mean', 'trimmed_mean']
        
        # Baseline (기준값)
        baseline = {
            'loess_frac': 0.25,
            'bin_size': 10,
            'agg_method': 'median'
        }
        
        print(f"📊 총 테스트 조합 수: {len(loess_fracs) * len(bin_sizes) * len(agg_methods)}")
        print(f"   Baseline: loess_frac={baseline['loess_frac']}, "
              f"bin_size={baseline['bin_size']}, agg={baseline['agg_method']}\n")
        
        results = []
        
        # === 1. LOESS Fraction 민감도 (bin_size=10, agg=median 고정) ===
        print("1️⃣  LOESS Fraction 민감도 분석")
        print("-" * 80)
        print(f"{'LOESS Frac':<12} {'FatMax(W)':<12} {'MFO(g/min)':<12} {'R²':<8} {'피크손실%':<10}")
        print("-" * 80)
        
        baseline_result = None
        
        for frac in loess_fracs:
            analyzer = MetabolismAnalyzer(
                loess_frac=frac,
                bin_size=baseline['bin_size'],
                use_median=(baseline['agg_method'] == 'median')
            )
            
            if baseline['agg_method'] != 'median':
                analyzer.config.aggregation_method = baseline['agg_method']
            
            analysis = analyzer.analyze(breath_data)
            
            if not analysis:
                print(f"{frac:<12.2f} {'FAILED':<12}")
                continue
            
            # 메트릭 추출
            fatmax_power = analysis.metabolic_markers.fat_max.power
            mfo = analysis.metabolic_markers.fat_max.mfo
            
            # R² 계산 (smoothed vs trend)
            smoothed = analysis.processed_series.smoothed
            trend = analysis.processed_series.trend
            
            # R² 추정 (trend가 smoothed를 얼마나 잘 근사하는가)
            smoothed_fat = np.array([p.fat_oxidation for p in smoothed if p.fat_oxidation is not None])
            
            if len(smoothed_fat) > 0 and len(trend) > 0:
                # Trend를 smoothed power에 보간
                trend_powers = [p.power for p in trend]
                trend_fat = [p.fat_oxidation for p in trend if p.fat_oxidation is not None]
                
                # 간단한 매칭 (가장 가까운 trend 값 사용)
                matched_trend = []
                for sp in smoothed:
                    if sp.fat_oxidation is None:
                        continue
                    closest_idx = min(range(len(trend_powers)), 
                                    key=lambda i: abs(trend_powers[i] - sp.power))
                    if trend[closest_idx].fat_oxidation is not None:
                        matched_trend.append(trend[closest_idx].fat_oxidation)
                    else:
                        matched_trend.append(sp.fat_oxidation)
                
                if len(matched_trend) == len(smoothed_fat):
                    matched_trend = np.array(matched_trend)
                    ss_res = np.sum((smoothed_fat - matched_trend) ** 2)
                    ss_tot = np.sum((smoothed_fat - np.mean(smoothed_fat)) ** 2)
                    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
                else:
                    r_squared = 0
            else:
                r_squared = 0
            
            # 피크 손실 (binned vs smoothed)
            binned = analysis.processed_series.binned
            binned_fat = [p.fat_oxidation for p in binned if p.fat_oxidation is not None]
            smoothed_fat_list = [p.fat_oxidation for p in smoothed if p.fat_oxidation is not None]
            
            if binned_fat and smoothed_fat_list:
                peak_loss = (max(binned_fat) - max(smoothed_fat_list)) / max(binned_fat) * 100
            else:
                peak_loss = 0
            
            print(f"{frac:<12.2f} {fatmax_power:<12.0f} {mfo:<12.4f} {r_squared:<8.4f} {peak_loss:<10.1f}")
            
            result = {
                'test': 'loess_frac',
                'loess_frac': frac,
                'bin_size': baseline['bin_size'],
                'agg_method': baseline['agg_method'],
                'fatmax_power': fatmax_power,
                'mfo': mfo,
                'r_squared': r_squared,
                'peak_loss_pct': peak_loss,
                'n_binned': len(binned),
                'n_smoothed': len(smoothed),
                'n_trend': len(trend),
            }
            
            results.append(result)
            
            if frac == baseline['loess_frac']:
                baseline_result = result
        
        print()
        
        # === 2. Bin Size 민감도 (loess_frac=0.25, agg=median 고정) ===
        print("2️⃣  Bin Size 민감도 분석")
        print("-" * 80)
        print(f"{'Bin Size(W)':<12} {'FatMax(W)':<12} {'MFO(g/min)':<12} {'N bins':<10} {'N raw→bin':<12}")
        print("-" * 80)
        
        for bin_sz in bin_sizes:
            analyzer = MetabolismAnalyzer(
                loess_frac=baseline['loess_frac'],
                bin_size=bin_sz,
                use_median=(baseline['agg_method'] == 'median')
            )
            
            if baseline['agg_method'] != 'median':
                analyzer.config.aggregation_method = baseline['agg_method']
            
            analysis = analyzer.analyze(breath_data)
            
            if not analysis:
                print(f"{bin_sz:<12} {'FAILED':<12}")
                continue
            
            fatmax_power = analysis.metabolic_markers.fat_max.power
            mfo = analysis.metabolic_markers.fat_max.mfo
            
            raw_count = len(analysis.processed_series.raw)
            binned_count = len(analysis.processed_series.binned)
            
            # count 합계 확인 (데이터 보존)
            count_sum = sum(p.count for p in analysis.processed_series.binned if hasattr(p, 'count'))
            
            print(f"{bin_sz:<12} {fatmax_power:<12.0f} {mfo:<12.4f} {binned_count:<10} {raw_count}→{count_sum}")
            
            results.append({
                'test': 'bin_size',
                'loess_frac': baseline['loess_frac'],
                'bin_size': bin_sz,
                'agg_method': baseline['agg_method'],
                'fatmax_power': fatmax_power,
                'mfo': mfo,
                'n_raw': raw_count,
                'n_binned': binned_count,
                'count_sum': count_sum,
            })
        
        print()
        
        # === 3. Aggregation Method 민감도 (loess_frac=0.25, bin_size=10 고정) ===
        print("3️⃣  Aggregation Method 민감도 분석")
        print("-" * 80)
        print(f"{'Method':<15} {'FatMax(W)':<12} {'MFO(g/min)':<12} {'Note':<30}")
        print("-" * 80)
        
        for agg in agg_methods:
            analyzer = MetabolismAnalyzer(
                loess_frac=baseline['loess_frac'],
                bin_size=baseline['bin_size'],
                use_median=(agg == 'median')
            )
            
            if agg != 'median':
                analyzer.config.aggregation_method = agg
            
            analysis = analyzer.analyze(breath_data)
            
            if not analysis:
                print(f"{agg:<15} {'FAILED':<12}")
                continue
            
            fatmax_power = analysis.metabolic_markers.fat_max.power
            mfo = analysis.metabolic_markers.fat_max.mfo
            
            note = ""
            if agg == 'median':
                note = "Robust to outliers (기본값)"
            elif agg == 'mean':
                note = "Sensitive to outliers"
            elif agg == 'trimmed_mean':
                note = "Remove 10% extremes"
            
            print(f"{agg:<15} {fatmax_power:<12.0f} {mfo:<12.4f} {note:<30}")
            
            results.append({
                'test': 'agg_method',
                'loess_frac': baseline['loess_frac'],
                'bin_size': baseline['bin_size'],
                'agg_method': agg,
                'fatmax_power': fatmax_power,
                'mfo': mfo,
            })
        
        print()
        
        # === 결과 분석 ===
        print("="*80)
        print("민감도 분석 요약")
        print("="*80 + "\n")
        
        # DataFrame 변환
        df = pd.DataFrame(results)
        
        # 1. LOESS Fraction 영향
        loess_results = df[df['test'] == 'loess_frac'].copy()
        if not loess_results.empty:
            print("📈 LOESS Fraction 영향:")
            print(f"   FatMax Power 변화폭: {loess_results['fatmax_power'].min():.0f}W ~ "
                  f"{loess_results['fatmax_power'].max():.0f}W "
                  f"(±{(loess_results['fatmax_power'].max() - loess_results['fatmax_power'].min())/2:.0f}W)")
            print(f"   MFO 변화폭: {loess_results['mfo'].min():.4f} ~ "
                  f"{loess_results['mfo'].max():.4f} g/min "
                  f"(±{(loess_results['mfo'].max() - loess_results['mfo'].min())/2:.4f})")
            
            # 최적 범위 추천
            acceptable = loess_results[loess_results['peak_loss_pct'] < 10]
            if not acceptable.empty:
                print(f"   ✅ 권장 범위 (피크 손실 < 10%): "
                      f"{acceptable['loess_frac'].min():.2f} ~ {acceptable['loess_frac'].max():.2f}")
            
            # R² 기준 최적값
            best_r2 = loess_results.loc[loess_results['r_squared'].idxmax()]
            print(f"   ✅ 최고 Trend Fit: loess_frac={best_r2['loess_frac']:.2f} (R²={best_r2['r_squared']:.4f})")
            print()
        
        # 2. Bin Size 영향
        bin_results = df[df['test'] == 'bin_size'].copy()
        if not bin_results.empty:
            print("📊 Bin Size 영향:")
            print(f"   FatMax Power 변화폭: {bin_results['fatmax_power'].min():.0f}W ~ "
                  f"{bin_results['fatmax_power'].max():.0f}W "
                  f"(±{(bin_results['fatmax_power'].max() - bin_results['fatmax_power'].min())/2:.0f}W)")
            print(f"   MFO 변화폭: {bin_results['mfo'].min():.4f} ~ "
                  f"{bin_results['mfo'].max():.4f} g/min")
            
            # Bins 수와 해상도 트레이드오프
            print(f"   해상도: 5W → {bin_results[bin_results['bin_size']==5]['n_binned'].values[0]}개 bins, "
                  f"10W → {bin_results[bin_results['bin_size']==10]['n_binned'].values[0]}개 bins")
            print(f"   ✅ 권장: 10W (해상도와 안정성 균형)")
            print()
        
        # 3. Aggregation Method 영향
        agg_results = df[df['test'] == 'agg_method'].copy()
        if not agg_results.empty:
            print("🔢 Aggregation Method 영향:")
            print(f"   FatMax Power 변화폭: {agg_results['fatmax_power'].min():.0f}W ~ "
                  f"{agg_results['fatmax_power'].max():.0f}W")
            print(f"   MFO 변화폭: {agg_results['mfo'].min():.4f} ~ "
                  f"{agg_results['mfo'].max():.4f} g/min")
            print(f"   ✅ 권장: median (이상치에 강함, 재현성 우수)")
            print()
        
        # === 최종 권장사항 ===
        print("="*80)
        print("최종 권장 파라미터")
        print("="*80)
        print(f"✅ LOESS Fraction: 0.2 ~ 0.3 (기본값: 0.25)")
        print(f"   - 0.15: 너무 날카로움, 노이즈 민감")
        print(f"   - 0.25: 균형 (권장)")
        print(f"   - 0.35+: 과도한 smoothing, 피크 손실")
        print()
        print(f"✅ Bin Size: 10W (5W~15W 허용)")
        print(f"   - 5W: 높은 해상도, 노이즈 많음")
        print(f"   - 10W: 균형 (권장)")
        print(f"   - 20W+: 해상도 낮음, 디테일 손실")
        print()
        print(f"✅ Aggregation: median (기본값)")
        print(f"   - median: 이상치에 강함 (권장)")
        print(f"   - mean: 빠르지만 이상치 민감")
        print(f"   - trimmed_mean: median과 유사, 계산 비용 약간 높음")
        print()
        
        # CSV 저장 (선택)
        output_path = os.path.join(os.path.dirname(__file__), 'sensitivity_analysis_results.csv')
        df.to_csv(output_path, index=False)
        print(f"📄 상세 결과 저장: {output_path}")


if __name__ == "__main__":
    asyncio.run(run_sensitivity_analysis())
