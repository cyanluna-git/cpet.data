"""
CPET_data 폴더의 파일명에서 피험자 정보를 추출하여 사용자 계정을 생성하는 스크립트

이메일 형식: firstname.lastname@cpet.com
패스워드: 모두 동일한 강력한 기본 패스워드
"""

import os
import re
import asyncio
from pathlib import Path
from datetime import datetime
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Default strong password for all users
DEFAULT_PASSWORD = "Cpet2024!Strong#Pass"


def extract_subjects_from_filenames(data_dir: Path) -> list[dict]:
    """파일명에서 피험자 정보 추출"""
    subjects = {}
    
    for filename in os.listdir(data_dir):
        if not filename.endswith('.xlsx'):
            continue
            
        # 파일명 형식: "LastName FirstName YYYYMMDD CPET TYPE_timestamp.xlsx"
        # 또는: "LASTNAME FIRSTNAME YYYYMMDD CPET TYPE_timestamp.xlsx"
        parts = filename.split(' ')
        
        if len(parts) < 3:
            continue
            
        # 첫 두 단어가 이름 (Last First 순서)
        last_name = parts[0].strip()
        first_name = parts[1].strip()
        
        # 이름에서 날짜 패턴 제거 (예: Haesung20240403 -> Haesung)
        first_name = re.sub(r'\d{8}$', '', first_name)
        
        # 이름 정규화 (대소문자 통일)
        last_name_normalized = last_name.capitalize()
        first_name_normalized = first_name.capitalize()
        
        # 고유 키 생성
        key = f"{last_name_normalized}_{first_name_normalized}".lower()
        
        if key not in subjects:
            subjects[key] = {
                'last_name': last_name_normalized,
                'first_name': first_name_normalized,
                'files': []
            }
        
        subjects[key]['files'].append(filename)
    
    return list(subjects.values())


def generate_user_data(subjects: list[dict]) -> list[dict]:
    """사용자 데이터 생성"""
    users = []
    password_hash = pwd_context.hash(DEFAULT_PASSWORD)
    
    for subject in subjects:
        first_name = subject['first_name'].lower()
        last_name = subject['last_name'].lower()
        
        # 이메일 생성: firstname.lastname@cpet.com
        email = f"{first_name}.{last_name}@cpet.com"
        
        # Research ID 생성
        research_id = f"SUB-{last_name.upper()[:3]}-{first_name.upper()[:3]}"
        
        users.append({
            'email': email,
            'password_hash': password_hash,
            'role': 'user',  # subject role
            'is_active': True,
            'first_name': subject['first_name'],
            'last_name': subject['last_name'],
            'research_id': research_id,
            'file_count': len(subject['files']),
        })
    
    return users


def generate_sql_script(users: list[dict]) -> str:
    """SQL INSERT 스크립트 생성"""
    sql_lines = [
        "-- CPET 피험자 사용자 및 subject 데이터 생성 스크립트",
        f"-- 생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"-- 기본 패스워드: {DEFAULT_PASSWORD}",
        "",
        "BEGIN;",
        "",
        "-- 기존 테스트 데이터 정리 (선택적)",
        "-- DELETE FROM users WHERE email LIKE '%@cpet.com' AND email != 'gerald.park@cpet.com';",
        "",
    ]
    
    for user in users:
        # Subject 생성
        sql_lines.append(f"""
-- {user['first_name']} {user['last_name']} ({user['file_count']} files)
INSERT INTO subjects (research_id, encrypted_name, gender, notes, created_at, updated_at)
VALUES (
    '{user['research_id']}',
    '{user['first_name']} {user['last_name']}',
    NULL,
    'CPET 테스트 피험자 ({user['file_count']}개 파일)',
    NOW(),
    NOW()
)
ON CONFLICT (research_id) DO UPDATE SET updated_at = NOW()
RETURNING id;
""")
        
        # User 생성 (subject와 연결)
        sql_lines.append(f"""
INSERT INTO users (email, password_hash, role, is_active, subject_id, created_at, updated_at)
SELECT 
    '{user['email']}',
    '{user['password_hash']}',
    'user',
    true,
    s.id,
    NOW(),
    NOW()
FROM subjects s
WHERE s.research_id = '{user['research_id']}'
ON CONFLICT (email) DO UPDATE SET 
    password_hash = EXCLUDED.password_hash,
    updated_at = NOW();
""")
    
    sql_lines.append("")
    sql_lines.append("COMMIT;")
    sql_lines.append("")
    sql_lines.append("-- 생성된 사용자 확인")
    sql_lines.append("SELECT u.email, u.role, s.research_id, s.encrypted_name")
    sql_lines.append("FROM users u")
    sql_lines.append("LEFT JOIN subjects s ON u.subject_id = s.id")
    sql_lines.append("WHERE u.email LIKE '%@cpet.com'")
    sql_lines.append("ORDER BY u.email;")
    
    return "\n".join(sql_lines)


def main():
    # CPET_data 디렉토리 경로
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "CPET_data"
    
    if not data_dir.exists():
        print(f"Error: CPET_data directory not found at {data_dir}")
        return
    
    print(f"CPET 데이터 디렉토리: {data_dir}")
    print("-" * 50)
    
    # 피험자 정보 추출
    subjects = extract_subjects_from_filenames(data_dir)
    print(f"\n총 {len(subjects)}명의 고유 피험자 발견:\n")
    
    for s in subjects:
        print(f"  - {s['last_name']} {s['first_name']}: {len(s['files'])}개 파일")
    
    # 사용자 데이터 생성
    users = generate_user_data(subjects)
    
    print(f"\n생성할 사용자 계정:")
    print("-" * 50)
    for u in users:
        print(f"  Email: {u['email']}")
        print(f"  Name: {u['first_name']} {u['last_name']}")
        print(f"  Research ID: {u['research_id']}")
        print()
    
    print(f"\n기본 패스워드: {DEFAULT_PASSWORD}")
    
    # SQL 스크립트 생성
    sql_script = generate_sql_script(users)
    
    # SQL 파일 저장
    sql_file = script_dir / "insert_cpet_users.sql"
    with open(sql_file, 'w', encoding='utf-8') as f:
        f.write(sql_script)
    
    print(f"\nSQL 스크립트 생성 완료: {sql_file}")
    print("\n실행 방법:")
    print(f"  docker exec -i cpet-db psql -U cpet_user -d cpet_db < {sql_file}")


if __name__ == "__main__":
    main()
