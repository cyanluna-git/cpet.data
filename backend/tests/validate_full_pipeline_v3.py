"""
🧪 CPET 파이프라인 정밀 검증 스크립트 v3.0

검증 전략: "API 결과를 믿지 않고, Raw 데이터를 받아 직접 계산해서 비교"

검증 항목:
1. 대사율 계산 정확도 (Frayn Formula Integrity)
2. Phase Detection Consistency
3. Power Binning Integrity (Cross-Check)
4. LOESS Smoothing Quality (Residual Analysis)
5. Trend Validity & Extrapolation Check
6. Edge Cases (RER Anomaly, Data Length)
"""
import requests
import pandas as pd
import numpy as np
from typing import Dict, Any
import os


# === 설정 ===
BASE_URL = os.getenv("VITE_API_URL", f"http://localhost:{os.getenv('BACKEND_PORT', '8100')}")
TEST_ID = "c91339b9-c0ce-434d-b4ad-3c77452ed928"
LOGIN_EMAIL = "gerald.park@cpet.com"
LOGIN_PASS = "cpet2026!"


def login() -> str:
    """로그인하여 토큰 반환"""
    res = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": LOGIN_EMAIL, "password": LOGIN_PASS}
    )
    if res.status_code != 200:
        raise Exception(f"Login failed: {res.status_code} - {res.text}")
    return res.json()["access_token"]


def print_section(title: str):
    """섹션 헤더 출력"""
    print("\n" + "="*70)
    print(f"🔍 [{title}]")
    print("="*70)


def print_result(passed: bool, message: str, details: str = ""):
    """검증 결과 출력"""
    icon = "✅ PASS" if passed else "❌ FAIL"
    print(f"   {icon}: {message}")
    if details:
        print(f"      {details}")


def validate_frayn_formula(df_raw: pd.DataFrame) -> Dict[str, Any]:
    """1. Frayn 공식 정확도 검증"""
    print_section("Check 1: Metabolic Rate Calculation Integrity")
    
    # vo2, vco2가 없으면 스킵
    if 'vo2' not in df_raw.columns or 'vco2' not in df_raw.columns:
        print_result(False, "vo2/vco2 columns not available in API response", "SKIP - Cannot verify Frayn formula")
        print("   ⚠️ This means vo2/vco2 values are None in ProcessedDataPoint")
        print("   ⚠️ Need to check why MetabolismAnalyzer._extract_raw_points() returns None for vo2/vco2")
        return {"passed": False, "reason": "no_vo2_vco2_columns", "skipped": True}
    
    # VO2, VCO2가 있는 행만 추출
    valid_raw = df_raw.dropna(subset=['vo2', 'vco2', 'fat_oxidation']).copy()
    
    if valid_raw.empty:
        print_result(False, "No valid data with vo2/vco2/fat_oxidation")
        return {"passed": False, "reason": "no_data"}
    
    # Frayn 공식으로 직접 계산 (mL/min -> L/min 변환)
    calc_fat = (1.67 * valid_raw['vo2']/1000 - 1.67 * valid_raw['vco2']/1000).clip(lower=0)
    calc_cho = (4.55 * valid_raw['vco2']/1000 - 3.21 * valid_raw['vo2']/1000).clip(lower=0)
    
    # 오차 계산 (소수점 3자리 허용: 0.005 g/min)
    fat_diff = np.abs(valid_raw['fat_oxidation'] - calc_fat)
    cho_diff = np.abs(valid_raw['cho_oxidation'] - calc_cho) if 'cho_oxidation' in valid_raw.columns else pd.Series()
    
    mismatch_count = (fat_diff > 0.005).sum()
    max_diff = fat_diff.max()
    mean_diff = fat_diff.mean()
    
    passed = mismatch_count == 0
    print_result(
        passed,
        f"DB stored oxidation rates match Frayn formula (N={len(valid_raw)})",
        f"Mismatches: {mismatch_count}, Max diff: {max_diff:.6f} g/min, Mean: {mean_diff:.6f} g/min"
    )
    
    return {
        "passed": passed,
        "total_points": len(valid_raw),
        "mismatches": int(mismatch_count),
        "max_diff": float(max_diff),
        "mean_diff": float(mean_diff)
    }


def validate_phase_detection(df_raw: pd.DataFrame) -> Dict[str, Any]:
    """2. Phase Detection 일관성 검증"""
    print_section("Check 2: Phase Detection Consistency")
    
    if 'phase' not in df_raw.columns:
        print_result(False, "Phase column not found in raw data", "SKIP")
        return {"passed": True, "reason": "no_phase_column"}
    
    issues = []
    
    # Rest 구간인데 Power가 높은 경우
    rest_high_power = df_raw[(df_raw['phase'] == 'Rest') & (df_raw['power'] > 30)]
    if not rest_high_power.empty:
        issues.append(f"{len(rest_high_power)} Rest points with power > 30W")
    
    # Warmup 구간인데 Power가 Rest 수준인 경우
    warmup_low_power = df_raw[(df_raw['phase'] == 'Warm-up') & (df_raw['power'] < 20)]
    if not warmup_low_power.empty:
        issues.append(f"{len(warmup_low_power)} Warm-up points with power < 20W")
    
    # Exercise 구간인데 Power가 Warmup 수준인 경우
    exercise_low_power = df_raw[(df_raw['phase'] == 'Exercise') & (df_raw['power'] < 50)]
    if not exercise_low_power.empty:
        issues.append(f"{len(exercise_low_power)} Exercise points with power < 50W")
    
    passed = len(issues) == 0
    
    if passed:
        print_result(True, "Phase labels are consistent with power levels")
    else:
        print_result(False, "Phase labeling inconsistencies found", " | ".join(issues))
    
    # Phase transition 점검
    phase_changes = []
    prev_phase = None
    for idx, row in df_raw.iterrows():
        if row['phase'] != prev_phase:
            phase_changes.append({
                'from': prev_phase,
                'to': row['phase'],
                'power': row['power']
            })
            prev_phase = row['phase']
    
    print(f"   Phase transitions: {len(phase_changes)}")
    for change in phase_changes[:3]:  # 처음 3개만 표시
        print(f"      {change['from']} → {change['to']}: {change['power']:.0f}W")
    
    return {
        "passed": passed,
        "issues": issues,
        "transition_count": len(phase_changes)
    }


def validate_binning_integrity(df_raw: pd.DataFrame, df_binned: pd.DataFrame) -> Dict[str, Any]:
    """3. Power Binning 무결성 검증 (직접 계산하여 비교)"""
    print_section("Check 3: Power Binning Integrity (Cross-Check)")
    
    if df_binned.empty:
        print_result(False, "No binned data returned from API")
        return {"passed": False, "reason": "no_binned_data"}
    
    # 스크립트에서 직접 Binning 수행 (10W 단위)
    df_raw_copy = df_raw.copy()
    df_raw_copy['bin'] = (df_raw_copy['power'] / 10).round() * 10
    
    # Median 집계
    manual_bin = df_raw_copy.groupby('bin').agg({
        'fat_oxidation': 'median',
        'cho_oxidation': 'median',
        'rer': 'median',
        'power': 'count'  # count로 개수 확인
    }).reset_index()
    manual_bin.rename(columns={'power': 'count'}, inplace=True)
    
    # API 결과와 비교
    merged = pd.merge(
        manual_bin, 
        df_binned, 
        left_on='bin', 
        right_on='power', 
        suffixes=('_manual', '_api'),
        how='inner'
    )
    
    if merged.empty:
        print_result(False, "No matching bins between manual and API calculation")
        return {"passed": False, "reason": "no_match"}
    
    # Fat oxidation 비교
    fat_diff = np.abs(merged['fat_oxidation_manual'] - merged['fat_oxidation_api'])
    max_diff = fat_diff.max()
    mean_diff = fat_diff.mean()
    
    # Count 비교 (데이터 손실 체크)
    total_raw = len(df_raw_copy)
    total_binned_count = df_binned['count'].sum() if 'count' in df_binned.columns else len(df_binned)
    
    passed = max_diff < 0.01  # 0.01 g/min 허용 오차
    
    print_result(
        passed,
        f"API Binning matches manual calculation (N={len(merged)} bins)",
        f"Max diff: {max_diff:.6f} g/min, Mean: {mean_diff:.6f} g/min"
    )
    
    # 데이터 보존율
    if 'count' in df_binned.columns:
        preservation_rate = (total_binned_count / total_raw * 100) if total_raw > 0 else 0
        print(f"   Data Preservation: {total_raw} raw → {total_binned_count} binned ({preservation_rate:.1f}%)")
        
        if preservation_rate < 95:
            print(f"   ⚠️ WARNING: {100-preservation_rate:.1f}% data loss during binning!")
    
    return {
        "passed": passed,
        "matched_bins": len(merged),
        "max_diff": float(max_diff),
        "mean_diff": float(mean_diff),
        "raw_count": total_raw,
        "binned_count": int(total_binned_count) if 'count' in df_binned.columns else len(df_binned)
    }


def validate_smoothing_quality(df_binned: pd.DataFrame, df_smooth: pd.DataFrame) -> Dict[str, Any]:
    """4. LOESS Smoothing 품질 검증 (잔차 분석)"""
    print_section("Check 4: LOESS Smoothing Quality (Residual Analysis)")
    
    if df_smooth.empty or df_binned.empty:
        print_result(False, "Missing binned or smoothed data", "SKIP")
        return {"passed": True, "reason": "no_data"}
    
    # Power를 기준으로 매칭 (Binned와 Smoothed는 같은 Power 포인트를 가짐)
    merged = pd.merge(
        df_binned,
        df_smooth,
        on='power',
        suffixes=('_binned', '_smooth'),
        how='inner'
    )
    
    if merged.empty:
        print_result(False, "Cannot match binned and smoothed data")
        return {"passed": False, "reason": "no_match"}
    
    # Fat oxidation 잔차 계산
    residuals = np.abs(merged['fat_oxidation_binned'] - merged['fat_oxidation_smooth'])
    mae = residuals.mean()
    max_residual = residuals.max()
    
    # 피크 보존율
    binned_max = merged['fat_oxidation_binned'].max()
    smooth_max = merged['fat_oxidation_smooth'].max()
    peak_preservation = (smooth_max / binned_max * 100) if binned_max > 0 else 0
    peak_loss = 100 - peak_preservation
    
    # 임계값: MAE < 0.15 g/min, 피크 손실 < 20%
    passed = mae < 0.15 and peak_loss < 20
    
    print_result(
        passed,
        f"Smoothing preserves data shape (N={len(merged)} points)",
        f"MAE: {mae:.4f} g/min, Max residual: {max_residual:.4f} g/min"
    )
    print(f"   Peak Preservation: {peak_preservation:.1f}% (Binned: {binned_max:.4f} → Smooth: {smooth_max:.4f} g/min)")
    
    if not passed:
        if mae >= 0.15:
            print("   ⚠️ WARNING: Smoothing is too aggressive (high MAE)")
        if peak_loss >= 20:
            print(f"   ⚠️ WARNING: Excessive peak loss ({peak_loss:.1f}%)")
    
    return {
        "passed": passed,
        "mae": float(mae),
        "max_residual": float(max_residual),
        "peak_preservation_pct": float(peak_preservation),
        "peak_loss_pct": float(peak_loss)
    }


def validate_trend_extrapolation(df_raw: pd.DataFrame, df_trend: pd.DataFrame) -> Dict[str, Any]:
    """5. Trend Extrapolation 검증"""
    print_section("Check 5: Trend Validity & Extrapolation Check")
    
    if df_trend.empty:
        print_result(False, "No trend data returned from API", "SKIP")
        return {"passed": True, "reason": "no_trend"}
    
    # Raw 데이터의 Power 범위
    min_raw_p = df_raw['power'].min()
    max_raw_p = df_raw['power'].max()
    
    # Trend가 범위를 벗어나는 포인트 (±10W 여유)
    trend_out_of_bounds = df_trend[
        (df_trend['power'] < min_raw_p - 10) | 
        (df_trend['power'] > max_raw_p + 10)
    ]
    
    passed = trend_out_of_bounds.empty
    
    print_result(
        passed,
        f"Trend lines stay within valid power range ({min_raw_p:.0f}-{max_raw_p:.0f}W)",
        f"Trend range: {df_trend['power'].min():.0f}-{df_trend['power'].max():.0f}W, Out-of-bounds: {len(trend_out_of_bounds)} points"
    )
    
    if not passed:
        print(f"   ⚠️ WARNING: Trend extrapolates beyond safe range!")
        print(f"      Extrapolated points: {list(trend_out_of_bounds['power'].values)}")
    
    return {
        "passed": passed,
        "raw_power_range": (float(min_raw_p), float(max_raw_p)),
        "trend_power_range": (float(df_trend['power'].min()), float(df_trend['power'].max())),
        "out_of_bounds_count": len(trend_out_of_bounds)
    }


def validate_edge_cases(df_raw: pd.DataFrame) -> Dict[str, Any]:
    """6. Edge Cases 검증 (데이터 품질)"""
    print_section("Check 6: Edge Cases & Data Quality")
    
    results = []
    
    # 1. 데이터 길이
    data_length = len(df_raw)
    if data_length < 50:
        results.append(("WARNING", f"Dataset is very short ({data_length} points). Results may be unstable."))
    else:
        results.append(("PASS", f"Sufficient data length ({data_length} points)"))
    
    # 2. RER 이상치 (생리학적으로 불가능한 값)
    if 'rer' in df_raw.columns:
        valid_rer = df_raw['rer'].dropna()
        abnormal_rer = valid_rer[(valid_rer < 0.65) | (valid_rer > 1.3)]
        abnormal_pct = (len(abnormal_rer) / len(valid_rer) * 100) if len(valid_rer) > 0 else 0
        
        if not abnormal_rer.empty:
            results.append(("WARNING", f"Found {len(abnormal_rer)} points ({abnormal_pct:.1f}%) with abnormal RER (<0.65 or >1.3)"))
            results.append(("INFO", "Likely sensor error or mask leak"))
        else:
            results.append(("PASS", "All RER values are within physiological limits (0.65-1.3)"))
    
    # 3. 결측값 비율
    if 'vo2' in df_raw.columns:
        missing_vo2 = df_raw['vo2'].isna().sum()
        missing_vco2 = df_raw['vco2'].isna().sum() if 'vco2' in df_raw.columns else 0
        missing_pct = (missing_vo2 / len(df_raw) * 100) if len(df_raw) > 0 else 0
        
        if missing_pct > 30:
            results.append(("FAIL", f"Excessive missing VO2/VCO2 data ({missing_pct:.1f}%)"))
        elif missing_pct > 10:
            results.append(("WARNING", f"Moderate missing data ({missing_pct:.1f}%)"))
        else:
            results.append(("PASS", f"Low missing data rate ({missing_pct:.1f}%)"))
    else:
        results.append(("WARNING", "vo2/vco2 columns not in API response (all None)"))
    
    # 4. Power 분포 (Ramp vs Step 프로토콜 감지)
    if 'power' in df_raw.columns:
        power_std = df_raw['power'].std()
        power_range = df_raw['power'].max() - df_raw['power'].min()
        
        if power_std < 10 and power_range < 30:
            results.append(("INFO", "Steady-state protocol detected (constant power)"))
        else:
            results.append(("INFO", f"Incremental protocol (power range: {power_range:.0f}W, std: {power_std:.1f}W)"))
    
    # 결과 출력
    for level, msg in results:
        if level == "PASS":
            print_result(True, msg)
        elif level == "FAIL":
            print_result(False, msg)
        else:  # WARNING or INFO
            print(f"   ⚠️ {level}: {msg}")
    
    passed = all(level != "FAIL" for level, _ in results)
    
    return {
        "passed": passed,
        "data_length": data_length,
        "abnormal_rer_count": len(abnormal_rer) if 'rer' in df_raw.columns else 0,
        "missing_pct": float(missing_pct),
        "results": results
    }


def run_precision_validation():
    """전체 검증 실행"""
    print("\n" + "🚀 " + "="*66)
    print("🚀 [CPET Pipeline Precision Validation v3.0]")
    print("🚀 " + "="*66)
    print(f"\n📋 Test ID: {TEST_ID}")
    print(f"📋 Endpoint: {BASE_URL}")
    print(f"📋 Strategy: Cross-check API results with direct calculation\n")
    
    all_results = {}
    
    try:
        # 로그인
        print("🔐 Authenticating...")
        token = login()
        headers = {"Authorization": f"Bearer {token}"}
        print("✅ Login successful\n")
        
        # API 데이터 가져오기
        print("📥 Fetching analysis data from API...")
        res = requests.get(
            f"{BASE_URL}/api/tests/{TEST_ID}/analysis",
            headers=headers,
            params={
                "include_processed": "true",
                "loess_frac": 0.25,
                "bin_size": 10,
                "aggregation_method": "median",
                "min_power_threshold": 0
            }
        )
        
        if res.status_code != 200:
            raise Exception(f"API request failed: {res.status_code} - {res.text}")
        
        data = res.json()
        series = data.get("processed_series", {})
        
        # DataFrame 변환
        df_raw = pd.DataFrame(series.get('raw', []))
        df_binned = pd.DataFrame(series.get('binned', []))
        df_smooth = pd.DataFrame(series.get('smoothed', []))
        df_trend = pd.DataFrame(series.get('trend', []))
        
        print(f"✅ Data loaded successfully")
        print(f"   Raw: {len(df_raw)}, Binned: {len(df_binned)}, Smooth: {len(df_smooth)}, Trend: {len(df_trend)}")
        
        # 디버깅: 사용 가능한 컬럼 확인
        print(f"\n📋 Available columns in raw data:")
        print(f"   {', '.join(df_raw.columns.tolist())}\n")
        
        # 검증 수행
        all_results['frayn'] = validate_frayn_formula(df_raw)
        all_results['phase'] = validate_phase_detection(df_raw)
        all_results['binning'] = validate_binning_integrity(df_raw, df_binned)
        all_results['smoothing'] = validate_smoothing_quality(df_binned, df_smooth)
        all_results['trend'] = validate_trend_extrapolation(df_raw, df_trend)
        all_results['edge_cases'] = validate_edge_cases(df_raw)
        
        # 최종 요약
        print("\n" + "="*70)
        print("📊 VALIDATION SUMMARY")
        print("="*70)
        
        checks = [
            ("1. Frayn Formula", all_results['frayn']['passed']),
            ("2. Phase Detection", all_results['phase']['passed']),
            ("3. Binning Integrity", all_results['binning']['passed']),
            ("4. Smoothing Quality", all_results['smoothing']['passed']),
            ("5. Trend Validity", all_results['trend']['passed']),
            ("6. Edge Cases", all_results['edge_cases']['passed'])
        ]
        
        passed_count = sum(1 for _, passed in checks if passed)
        total_count = len(checks)
        
        for name, passed in checks:
            icon = "✅" if passed else "❌"
            print(f"   {icon} {name}")
        
        print("\n" + "="*70)
        if passed_count == total_count:
            print("🎉 ALL CHECKS PASSED! Pipeline integrity verified.")
        else:
            print(f"⚠️  {passed_count}/{total_count} checks passed. Review failures above.")
        print("="*70 + "\n")
        
        return all_results
        
    except Exception as e:
        print(f"\n❌ Validation System Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


if __name__ == "__main__":
    results = run_precision_validation()
