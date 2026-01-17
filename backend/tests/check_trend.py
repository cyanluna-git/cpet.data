import requests
import json
import os

# Get base URL from environment
BASE_URL = os.getenv("VITE_API_URL", f"http://localhost:{os.getenv('BACKEND_PORT', '8100')}")

token = requests.post(f'{BASE_URL}/api/auth/login', data={'username': 'gerald.park@cpet.com', 'password': 'cpet2026!'}).json()['access_token']
res = requests.get(f'{BASE_URL}/api/tests/c91339b9-c0ce-434d-b4ad-3c77452ed928/analysis', headers={'Authorization': f'Bearer {token}'}, params={'include_processed': True})
data = res.json()
ps = data.get('processed_series', {})
print('processed_series keys:', list(ps.keys()))
if 'trend' in ps:
    print('✅ Trend found! length:', len(ps['trend']))
    if ps['trend']:
        print('   First trend point:', ps['trend'][0])
else:
    print('❌ trend key not in response')
    
print('\nRaw sample:')
if 'raw' in ps and ps['raw']:
    print(json.dumps(ps['raw'][0], indent=2))
