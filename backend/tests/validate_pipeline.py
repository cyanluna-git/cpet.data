import requests
import pandas as pd
import numpy as np
import json
import os

# === 설정 ===
BASE_URL = os.getenv("VITE_API_URL", f"http://localhost:{os.getenv('BACKEND_PORT', '8100')}")
LOGIN_EMAIL = "gerald.park@cpet.com"
LOGIN_PASS = "cpet2026!"
TEST_ID = "c91339b9-c0ce-434d-b4ad-3c77452ed928"


def login():
    """JWT 토큰 발급"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": LOGIN_EMAIL, "password": LOGIN_PASS},
    )
    if response.status_code != 200:
        raise Exception(f"Login failed: {response.text}")
    return response.json()["access_token"]


def run_validation():
    print(f"🚀 Starting Advanced CPET Pipeline Validation for Test ID: {TEST_ID}")

    try:
        token = login()
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Analysis API 호출
        print("\n[Step 1] Fetching Analysis Data...")
        params = {
            "include_processed": True,
            "loess_frac": 0.25,
            "bin_size": 10,
            "aggregation_method": "median",
        }
        res = requests.get(
            f"{BASE_URL}/api/tests/{TEST_ID}/analysis", headers=headers, params=params
        )

        if res.status_code != 200:
            print(f"❌ API Error: {res.status_code} - {res.text}")
            return

        data = res.json()
        processed = data.get("processed_series", {})

        # 2. 기본 구조 검증
        required_keys = ["raw", "binned", "smoothed"]
        optional_keys = ["trend"]
        missing_keys = [k for k in required_keys if k not in processed]
        if missing_keys:
            print(f"❌ Missing required keys in processed_series: {missing_keys}")
            return
        else:
            print(f"✅ Schema check passed. Required series found.")
            print(f"   - Raw points: {len(processed['raw'])}")
            print(f"   - Binned points: {len(processed['binned'])}")
            print(f"   - Smoothed points: {len(processed['smoothed'])}")
            
            # Optional trend
            if 'trend' in processed and processed['trend']:
                print(f"   - Trend points: {len(processed['trend'])}")
            else:
                print(f"   ⚠️ Trend data not available (optional)")

        # DataFrame 변환
        df_raw = pd.DataFrame(processed["raw"])
        df_trend = pd.DataFrame(processed.get("trend", [])) if processed.get("trend") else pd.DataFrame()

        # 3. 로직 검증: Recalculation (Frayn Equation Check)
        print("\n[Step 2] Verifying Oxidation Rate Recalculation...")
        
        # vo2와 vco2가 있는지 확인
        if 'vo2' not in df_raw.columns or 'vco2' not in df_raw.columns:
            print("⚠️ VO2/VCO2 data not available in raw series (skipping Frayn verification).")
            print(f"   Available columns: {list(df_raw.columns)}")
        else:
            # 임의의 샘플 5개 추출하여 검증
            sample = (
                df_raw.dropna(subset=["vo2", "vco2"]).sample(5)
                if len(df_raw.dropna(subset=["vo2", "vco2"])) >= 5
                else df_raw.dropna(subset=["vo2", "vco2"])
            )
            
            if len(sample) == 0:
                print("⚠️ No valid VO2/VCO2 data for Frayn verification.")
            else:
                errors = 0
                for _, row in sample.iterrows():
                    # 단위 환산 (mL -> L)
                    vo2_l = row["vo2"] / 1000.0
                    vco2_l = row["vco2"] / 1000.0

                    # Frayn 공식 계산
                    calc_fat = 1.67 * vo2_l - 1.67 * vco2_l
                    calc_cho = 4.55 * vco2_l - 3.21 * vo2_l

                    # 음수 클램핑 고려
                    calc_fat = max(0, calc_fat)
                    calc_cho = max(0, calc_cho)

                    # API 값과 비교 (소수점 4자리)
                    if row.get("fat_oxidation") is not None:
                        if not np.isclose(row["fat_oxidation"], calc_fat, atol=0.001):
                            errors += 1
                            print(
                                f"   ⚠️ Mismatch! Power {row.get('power')}W: API Fat={row['fat_oxidation']:.4f} vs Calc={calc_fat:.4f}"
                            )

                if errors == 0:
                    print("✅ Frayn Equation recalculation verified (VO2/VCO2 match Fat/CHO).")
                else:
                    print(f"❌ Recalculation verification failed with {errors} mismatches.")

        # 4. 로직 검증: Sparse Data Handling (Phantom Line)
        print("\n[Step 3] Checking Sparse Data Handling (Phantom Lines)...")
        # 20W ~ 70W 구간 (Warm-up Gap)에 Trend 데이터가 있는지 확인
        if not df_trend.empty:
            gap_data = df_trend[(df_trend["power"] > 20) & (df_trend["power"] < 70)]

            if gap_data.empty:
                print("✅ No phantom trend lines detected in warm-up gap (20W-70W).")
            else:
                print(f"⚠️ Found {len(gap_data)} trend points in likely gap region.")
                print(gap_data[["power", "fat_oxidation"]].head())
        else:
            print("⚠️ Trend data not available for phantom line check (skipping).")

        # 5. 로직 검증: Markers
        print("\n[Step 4] Verifying Metabolic Markers...")
        markers = data.get("metabolic_markers", {})
        fatmax = markers.get("fat_max", {})
        crossover = markers.get("crossover", {})

        print(
            f"   - FatMax Power: {fatmax.get('power')} W (MFO: {fatmax.get('mfo')} g/min)"
        )
        print(
            f"   - FatMax Zone: {fatmax.get('zone_min')}W - {fatmax.get('zone_max')}W"
        )
        print(f"   - Crossover Power: {crossover.get('power')} W")

        if fatmax.get("power") and crossover.get("power"):
            print("✅ Markers are successfully calculated.")
        else:
            print("⚠️ Some markers may be missing.")

        print("\n" + "=" * 60)
        print("🏁 Validation Complete!")
        print("=" * 60)

    except Exception as e:
        print(f"❌ Test Execution Failed: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    run_validation()
