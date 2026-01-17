import requests
import json

token = requests.post('http://localhost:8100/api/auth/login', data={'username': 'gerald.park@cpet.com', 'password': 'cpet2026!'}).json()['access_token']
res = requests.get('http://localhost:8100/api/tests/c91339b9-c0ce-434d-b4ad-3c77452ed928/analysis', headers={'Authorization': f'Bearer {token}'}, params={'include_processed': True})
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
