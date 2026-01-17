"""VO2/VCO2가 None으로 처리되는 원인 분석"""
import sys
import os
import requests
import json

# API를 통해 분석
BASE_URL = "http://localhost:8100"
TEST_ID = "c91339b9-c0ce-434d-b4ad-3c77452ed928"

def login():
    response = requests.post(f"{BASE_URL}/api/auth/login", data={
        "username": "gerald.park@cpet.com",
        "password": "cpet2026!"
    })
    return response.json()["access_token"]

def main():
    print("🔍 VO2/VCO2 None 처리 원인 분석\n")
    
    token = login()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. raw-data 엔드포인트로 DB 데이터 확인
    print("=" * 60)
    print("Step 1: DB 원본 데이터 확인 (raw-data API)")
    print("=" * 60)
    res = requests.get(f"{BASE_URL}/api/tests/{TEST_ID}/raw-data", headers=headers, params={"limit": 10})
    raw_data = res.json()
    
    if 'data' in raw_data and len(raw_data['data']) > 0:
        sample = raw_data['data'][0]
        print(f"✅ DB에 저장된 첫 breath data:")
        print(f"   vo2: {sample.get('vo2')} (타입: {type(sample.get('vo2'))})")
        print(f"   vco2: {sample.get('vco2')}")
        print(f"   fat_oxidation: {sample.get('fat_oxidation')}")
        print(f"   bike_power: {sample.get('bike_power')}")
        print(f"   phase: {sample.get('phase')}")
        
        # Exercise 단계 데이터 확인
        exercise_data = [d for d in raw_data['data'] if d.get('phase') == 'Exercise']
        print(f"\n   Exercise 단계 데이터: {len(exercise_data)}개")
        if exercise_data:
            ex = exercise_data[0]
            print(f"   Exercise 첫 데이터:")
            print(f"      vo2={ex.get('vo2')}, vco2={ex.get('vco2')}")
            print(f"      power={ex.get('bike_power')}")
    
    # 2. Analysis API로 processed_series 확인
    print("\n" + "=" * 60)
    print("Step 2: Processed Series 확인 (analysis API)")
    print("=" * 60)
    res = requests.get(
        f"{BASE_URL}/api/tests/{TEST_ID}/analysis",
        headers=headers,
        params={
            "include_processed": True,
            "loess_frac": 0.25,
            "bin_size": 10,
            "aggregation_method": "median"
        }
    )
    
    if res.status_code != 200:
        print(f"❌ API 오류: {res.status_code}")
        print(res.text)
        return
    
    data = res.json()
    processed = data.get("processed_series", {})
    
    print(f"✅ API 응답 수신")
    print(f"   Series 종류: {list(processed.keys())}")
    
    if 'raw' in processed and processed['raw']:
        print(f"   Raw points: {len(processed['raw'])}개")
        first_raw = processed['raw'][0]
        print(f"\n   첫 raw point 필드: {list(first_raw.keys())}")
        print(f"   ❌ 문제 발견: vo2, vco2, hr, ve_vo2, ve_vco2 필드가 없음!")
        print(f"\n   실제 데이터:")
        print(json.dumps(first_raw, indent=4))
    
    if 'trend' in processed and processed['trend']:
        print(f"\n   ✅ Trend points: {len(processed['trend'])}개")
        print(f"   Trend 샘플:")
        for t in processed['trend'][:3]:
            print(f"      power={t['power']}W, fat_ox={t.get('fat_oxidation', 'N/A')}")
    else:
        print(f"\n   ❌ Trend data가 응답에 없음!")
    
    # 3. 원인 분석
    print("\n" + "=" * 60)
    print("원인 분석")
    print("=" * 60)
    print("""
    1. DB에는 vo2/vco2 데이터가 존재함 ✅
    2. API 응답의 raw points에는 vo2/vco2가 없음 ❌
    
    가능한 원인:
    A) ProcessedDataPoint.to_dict()가 None 값을 포함하고 있지만,
       FastAPI/Pydantic이 JSON 직렬화 시 None 값의 키를 제거함
    
    B) MetabolismAnalyzer._extract_raw_points()에서 
       getattr(bd, 'vo2', None)이 None을 반환하고 있음
       → Phase trimming으로 vo2 데이터가 있는 구간이 제외되었을 가능성
    
    C) JSON 인코더 설정 문제
       → response_model_exclude_none=True가 아니더라도
          FastAPI는 기본적으로 None 값의 키를 응답에서 제외함
    """)
    
    # 4. 해결책 제안
    print("\n" + "=" * 60)
    print("해결책")
    print("=" * 60)
    print("""
    해결책 1: ProcessedDataPoint.to_dict()에서 명시적 필드 포함
              → None 대신 null로 명시
    
    해결책 2: API 라우트에 response_model_exclude_unset=False 추가
    
    해결책 3: Pydantic 스키마에서 Optional 필드 명시적 설정
    
    해결책 4 (권장): 검증 스크립트를 실제 동작에 맞게 수정
                    → vo2/vco2는 binned/smoothed에서만 검증
    """)

if __name__ == "__main__":
    main()

