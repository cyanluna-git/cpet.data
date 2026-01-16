"""단일 파일 업로드 테스트"""
import httpx

# Login
r = httpx.post('http://localhost:8100/api/auth/login', data={'username': 'gerald.park@cpet.com', 'password': 'cpet2026!'})
token = r.json()['access_token']
print(f"Token: {token[:20]}...")

# Get subject
r = httpx.get('http://localhost:8100/api/subjects', params={'search': 'SUB-CHO-KWA'}, headers={'Authorization': f'Bearer {token}'})
subjects = r.json()['items']
subject = [s for s in subjects if s['research_id'] == 'SUB-CHO-KWA'][0]
print(f"Subject ID: {subject['id']}")

# Upload file
import os
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
file_path = os.path.join(base_dir, 'CPET_data', 'Cho Kwangho 20240718 CPET MIX_20240718094328.xlsx')
print(f"File: {file_path}")
with open(file_path, 'rb') as f:
    files = {'file': ('test.xlsx', f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    data = {'subject_id': subject['id'], 'calc_method': 'Frayn', 'smoothing_window': '10'}
    r = httpx.post('http://localhost:8100/api/tests/upload', files=files, data=data, headers={'Authorization': f'Bearer {token}'}, timeout=120)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:3000]}")
