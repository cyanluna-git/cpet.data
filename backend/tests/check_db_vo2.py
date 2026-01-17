import requests
import json

# 로그인
token = requests.post('http://localhost:8100/api/auth/login', data={'username': 'gerald.park@cpet.com', 'password': 'cpet2026!'}).json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

# 테스트 데이터 가져오기 (Exercise 단계 확인)
res = requests.get('http://localhost:8100/api/tests/c91339b9-c0ce-434d-b4ad-3c77452ed928/raw-data', headers=headers, params={'limit': 500})
data = res.json()

if 'data' in data:
    breath_data = data['data']
    
    # Exercise 단계 데이터 확인
    exercise_data = [d for d in breath_data if d.get('phase') == 'Exercise']
    print(f'총 데이터: {len(breath_data)}개')
    print(f'Exercise 단계: {len(exercise_data)}개')
    
    # Exercise 첫 10개 확인
    print('\nExercise 첫 10개 데이터의 vo2/vco2:')
    for i, d in enumerate(exercise_data[:10]):
        print(f'  {i}: power={d.get("bike_power")}, vo2={d.get("vo2")}, vco2={d.get("vco2")}, phase={d.get("phase")}')
    
    # vo2가 None인 데이터 확인
    none_vo2 = [d for d in exercise_data if d.get('vo2') is None]
    print(f'\nExercise 단계에서 vo2가 None인 데이터: {len(none_vo2)}개')
    
    # vo2가 있는 데이터 확인
    has_vo2 = [d for d in exercise_data if d.get('vo2') is not None]
    print(f'Exercise 단계에서 vo2가 있는 데이터: {len(has_vo2)}개')
    
    if has_vo2:
        print(f'\nvo2가 있는 첫 데이터:')
        d = has_vo2[0]
        print(f'  power={d.get("bike_power")}, vo2={d.get("vo2")}, vco2={d.get("vco2")}')
        print(f'  fat_ox={d.get("fat_oxidation")}, cho_ox={d.get("cho_oxidation")}')
        print(f'  phase={d.get("phase")}, t_sec={d.get("t_sec")}')
        print(f'  hr={d.get("hr")}, ve_vo2={d.get("ve_vo2")}, ve_vco2={d.get("ve_vco2")}')
