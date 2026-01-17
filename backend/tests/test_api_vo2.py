"""실제 API 호출하여 vo2/vco2 응답 확인"""
import requests
import json

BASE_URL = "http://localhost:8100"
TEST_ID = "c91339b9-c0ce-434d-b4ad-3c77452ed928"

# 1. 로그인
login_data = {
    "username": "gerald.park@cpet.com",
    "password": "cpet2026!"
}
login_res = requests.post(f"{BASE_URL}/api/auth/login", data=login_data)
if login_res.status_code != 200:
    print(f"❌ 로그인 실패: {login_res.status_code}")
    print(login_res.text)
    exit(1)

token = login_res.json()["access_token"]
print(f"✅ 로그인 성공\n")

# 2. Analysis API 호출
headers = {"Authorization": f"Bearer {token}"}
params = {
    "include_processed": "true",
    "loess_frac": 0.25,
    "bin_size": 10,
    "aggregation_method": "median",
}

print(f"🔍 API 호출: /api/tests/{TEST_ID}/analysis")
print(f"   파라미터: {params}\n")

api_res = requests.get(
    f"{BASE_URL}/api/tests/{TEST_ID}/analysis",
    headers=headers,
    params=params
)

if api_res.status_code != 200:
    print(f"❌ API 실패: {api_res.status_code}")
    print(api_res.text)
    exit(1)

data = api_res.json()
print(f"✅ API 성공 (Status 200)\n")

# 3. processed_series 확인
if "processed_series" not in data:
    print("❌ processed_series 없음!")
    exit(1)

ps = data["processed_series"]
print("📊 Processed Series:")
print(f"   raw: {len(ps.get('raw', []))}개")
print(f"   binned: {len(ps.get('binned', []))}개")
print(f"   smoothed: {len(ps.get('smoothed', []))}개")
print(f"   trend: {len(ps.get('trend', []))}개\n")

# 4. Raw series의 vo2/vco2 확인
raw_series = ps.get("raw", [])
if not raw_series:
    print("❌ raw series 비어있음!")
    exit(1)

print("🔬 Raw series 첫 5개 데이터:")
for i, point in enumerate(raw_series[:5]):
    print(f"  {i}: power={point.get('power')}, vo2={point.get('vo2')}, vco2={point.get('vco2')}")
    print(f"      fat_ox={point.get('fat_oxidation')}, cho_ox={point.get('cho_oxidation')}")

# vo2/vco2가 None이 아닌 것 카운트
has_vo2 = sum(1 for p in raw_series if p.get('vo2') is not None)
has_vco2 = sum(1 for p in raw_series if p.get('vco2') is not None)

print(f"\n✅ vo2 값 존재: {has_vo2} / {len(raw_series)}")
print(f"✅ vco2 값 존재: {has_vco2} / {len(raw_series)}")

if has_vo2 == 0:
    print("\n❌ 모든 vo2가 None! 이게 문제입니다.")
else:
    print("\n✅ vo2/vco2 데이터가 API 응답에 포함되어 있습니다!")
