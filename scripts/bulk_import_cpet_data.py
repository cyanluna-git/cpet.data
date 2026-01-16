"""
CPET_data 폴더의 모든 Excel 파일을 DB에 일괄 업로드하는 스크립트

사용법:
    python scripts/bulk_import_cpet_data.py [--dry-run] [--limit N]
    
옵션:
    --dry-run: 실제 업로드 없이 파일 목록만 출력
    --limit N: 처음 N개 파일만 처리
"""

import argparse
import asyncio
import os
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
import json

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import httpx
import pandas as pd


# Configuration
API_BASE_URL = "http://localhost:8100/api"
CPET_DATA_DIR = Path(__file__).parent.parent / "CPET_data"

# Auth credentials
ADMIN_EMAIL = "gerald.park@cpet.com"
ADMIN_PASSWORD = "cpet2026!"


def extract_subject_from_excel(file_path: Path) -> Dict[str, Any]:
    """
    Excel 파일 내부에서 피험자 정보 추출 (ID1 섹션)
    
    Returns:
        {
            'last_name': str,
            'first_name': str,
            'gender': str,
            'age': float,
            'height_cm': float,
            'weight_kg': float,
            'birth_date': str
        }
    """
    try:
        df = pd.read_excel(file_path, header=None, nrows=20)
        
        def safe_get(row, col):
            try:
                val = df.iloc[row, col]
                if pd.isna(val):
                    return None
                return val
            except:
                return None
        
        return {
            'last_name': str(safe_get(1, 1) or '').strip(),
            'first_name': str(safe_get(2, 1) or '').strip(),
            'gender': str(safe_get(3, 1) or '').strip(),
            'age': safe_get(4, 1),
            'height_cm': safe_get(5, 1),
            'weight_kg': safe_get(6, 1),
            'birth_date': str(safe_get(7, 1) or '').strip(),
        }
    except Exception as e:
        print(f"  ⚠️ Excel 파싱 에러: {e}")
        return {}


def extract_subject_info(filename: str) -> Tuple[str, str, str, Optional[datetime]]:
    """
    파일명에서 피험자 정보 추출
    
    형식: "LastName FirstName YYYYMMDD CPET TYPE_timestamp.xlsx"
    
    Returns:
        (last_name, first_name, research_id, test_date)
    """
    parts = filename.replace('.xlsx', '').replace('.xls', '').split(' ')
    
    if len(parts) < 3:
        return None, None, None, None
    
    last_name = parts[0].strip()
    first_name = parts[1].strip()
    
    # 이름에서 날짜 패턴 제거 (예: Haesung20240403 -> Haesung)
    first_name = re.sub(r'\d{8}$', '', first_name)
    
    # 정규화
    last_name = last_name.capitalize()
    first_name = first_name.capitalize()
    
    # Research ID 생성
    research_id = f"SUB-{last_name.upper()[:3]}-{first_name.upper()[:3]}"
    
    # 날짜 파싱
    test_date = None
    for part in parts:
        if re.match(r'^\d{8}$', part):
            try:
                test_date = datetime.strptime(part, '%Y%m%d')
            except ValueError:
                pass
            break
    
    return last_name, first_name, research_id, test_date


async def get_auth_token(client: httpx.AsyncClient) -> Optional[str]:
    """로그인하여 JWT 토큰 획득"""
    try:
        response = await client.post(
            f"{API_BASE_URL}/auth/login",
            data={
                "username": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
        else:
            print(f"❌ 로그인 실패: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ 로그인 에러: {e}")
        return None


async def get_subject_by_name(
    client: httpx.AsyncClient,
    token: str,
    last_name: str,
    first_name: str,
    cache: dict = None
) -> Optional[str]:
    """이름으로 subject_id 조회 (캐싱 지원)"""
    cache_key = f"{last_name}_{first_name}".lower()
    
    # 캐시 확인
    if cache and cache_key in cache:
        return cache[cache_key]
    
    for attempt in range(3):  # 최대 3회 재시도
        try:
            # 이름으로 검색
            response = await client.get(
                f"{API_BASE_URL}/subjects",
                params={"search": last_name, "page_size": 100},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                for subject in data.get("items", []):
                    # encrypted_name 형식: "FirstName LastName"
                    subject_name = subject.get("encrypted_name", "").lower()
                    if (last_name.lower() in subject_name and 
                        first_name.lower() in subject_name):
                        subject_id = subject.get("id")
                        if cache is not None:
                            cache[cache_key] = subject_id
                        return subject_id
            return None
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(1)  # 재시도 전 대기
                continue
            print(f"  ⚠️ Subject 조회 에러: {e}")
            return None


async def get_subject_id(
    client: httpx.AsyncClient,
    token: str,
    research_id: str,
    cache: dict = None
) -> Optional[str]:
    """research_id로 subject_id 조회 (캐싱 지원) - deprecated, use get_subject_by_name"""
    # 캐시 확인
    if cache and research_id in cache:
        return cache[research_id]
    
    for attempt in range(3):  # 최대 3회 재시도
        try:
            response = await client.get(
                f"{API_BASE_URL}/subjects",
                params={"search": research_id, "page_size": 100},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                for subject in data.get("items", []):
                    if subject.get("research_id") == research_id:
                        subject_id = subject.get("id")
                        if cache is not None:
                            cache[research_id] = subject_id
                        return subject_id
            return None
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(1)  # 재시도 전 대기
                continue
            print(f"  ⚠️ Subject 조회 에러: {e}")
            return None


async def upload_file_once(
    client: httpx.AsyncClient,
    token: str,
    file_path: Path,
    subject_id: str,
    calc_method: str = "Frayn",
    smoothing_window: int = 10
) -> Tuple[bool, Optional[str], Optional[dict]]:
    """
    단일 파일 업로드 시도
    """
    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            data = {
                "subject_id": subject_id,
                "calc_method": calc_method,
                "smoothing_window": str(smoothing_window),
            }
            
            response = await client.post(
                f"{API_BASE_URL}/tests/upload",
                files=files,
                data=data,
                headers={"Authorization": f"Bearer {token}"},
                timeout=180.0  # 타임아웃 증가
            )
        
        if response.status_code in (200, 201):
            result = response.json()
            test_id = result.get("test_id") or result.get("test", {}).get("test_id")
            return True, test_id, result
        else:
            return False, None, {"status": response.status_code, "detail": response.text}
            
    except Exception as e:
        return False, None, {"error": str(e)}


async def upload_file_with_retry(
    token: str,
    file_path: Path,
    subject_id: str,
    calc_method: str = "Frayn",
    smoothing_window: int = 10,
    max_retries: int = 3,
    retry_delay: float = 5.0
) -> Tuple[bool, Optional[str], Optional[dict]]:
    """
    파일 업로드 (재시도 로직 포함)
    매번 새 클라이언트를 생성하여 연결 문제 방지
    """
    last_error = None
    
    for attempt in range(max_retries):
        if attempt > 0:
            print(f"      ↻ 재시도 {attempt + 1}/{max_retries} (대기 {retry_delay}초)")
            await asyncio.sleep(retry_delay)
        
        # 새 클라이언트로 연결 (연결 풀 문제 방지)
        async with httpx.AsyncClient() as client:
            success, test_id, info = await upload_file_once(
                client, token, file_path, subject_id, calc_method, smoothing_window
            )
            
            if success:
                return success, test_id, info
            
            last_error = info
            
            # 500 에러는 재시도
            if isinstance(info, dict) and info.get("status") == 500:
                print(f"      ⚠️ 서버 에러 (500), 재시도...")
                continue
            
            # 타임아웃은 재시도
            if isinstance(info, dict) and "timeout" in str(info.get("error", "")).lower():
                print(f"      ⚠️ 타임아웃, 재시도...")
                continue
            
            # 다른 에러는 즉시 실패
            break
    
    return False, None, last_error


def collect_excel_files(data_dir: Path) -> list[Path]:
    """CPET_data 폴더에서 모든 Excel 파일 수집"""
    files = []
    
    for root, dirs, filenames in os.walk(data_dir):
        for filename in filenames:
            if filename.endswith(('.xlsx', '.xls')) and not filename.startswith('~$'):
                files.append(Path(root) / filename)
    
    # 날짜순 정렬
    files.sort(key=lambda p: p.name)
    return files


async def main():
    parser = argparse.ArgumentParser(description="CPET 데이터 일괄 임포트")
    parser.add_argument("--dry-run", action="store_true", help="실제 업로드 없이 파일 목록만 출력")
    parser.add_argument("--limit", type=int, default=0, help="처리할 파일 수 제한 (0=전체)")
    parser.add_argument("--skip", type=int, default=0, help="처음 N개 파일 건너뛰기")
    parser.add_argument("--calc-method", default="Frayn", choices=["Frayn", "Peronnet", "Jeukendrup"])
    parser.add_argument("--smoothing", type=int, default=10, help="Smoothing window 크기")
    args = parser.parse_args()
    
    print("=" * 60)
    print("CPET 데이터 일괄 임포트")
    print("=" * 60)
    
    # Excel 파일 수집
    if not CPET_DATA_DIR.exists():
        print(f"❌ CPET_data 디렉토리가 없습니다: {CPET_DATA_DIR}")
        return
    
    excel_files = collect_excel_files(CPET_DATA_DIR)
    total_files = len(excel_files)
    print(f"\n📁 발견된 Excel 파일: {total_files}개")
    
    if args.skip > 0:
        excel_files = excel_files[args.skip:]
        print(f"   (--skip {args.skip} 적용, {len(excel_files)}개 남음)")
    
    if args.limit > 0:
        excel_files = excel_files[:args.limit]
        print(f"   (--limit {args.limit} 적용)")
    
    # 피험자별 그룹핑
    subjects_files = {}
    for file_path in excel_files:
        last_name, first_name, research_id, test_date = extract_subject_info(file_path.name)
        if research_id:
            if research_id not in subjects_files:
                subjects_files[research_id] = []
            subjects_files[research_id].append({
                "path": file_path,
                "date": test_date,
                "name": f"{first_name} {last_name}"
            })
    
    print(f"\n👥 피험자: {len(subjects_files)}명")
    for research_id, files in subjects_files.items():
        print(f"   - {research_id}: {len(files)}개 파일")
    
    if args.dry_run:
        print("\n🔍 --dry-run 모드: 실제 업로드를 수행하지 않습니다.")
        print("\n파일 목록 (Excel 내부 정보 기반):")
        for i, file_path in enumerate(excel_files, 1):
            excel_info = extract_subject_from_excel(file_path)
            last_name = excel_info.get('last_name', '?')
            first_name = excel_info.get('first_name', '?')
            _, _, _, test_date = extract_subject_info(file_path.name)
            date_str = test_date.strftime("%Y-%m-%d") if test_date else "unknown"
            print(f"  {i:3}. [{first_name} {last_name}] {date_str} - {file_path.name}")
        return
    
    # API 서버 확인
    print("\n🔌 API 서버 연결 확인...")
    
    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(f"{API_BASE_URL.replace('/api', '')}/health", timeout=5.0)
            if health.status_code != 200:
                print(f"❌ API 서버가 응답하지 않습니다. 서버를 먼저 실행해주세요.")
                print(f"   cd backend && python -m uvicorn app.main:app --reload --port 8100")
                return
        except Exception as e:
            print(f"❌ API 서버 연결 실패: {e}")
            print(f"   cd backend && python -m uvicorn app.main:app --reload --port 8100")
            return
        
        print("✅ API 서버 연결됨")
        
        # 로그인
        print("\n🔐 관리자 로그인...")
        token = await get_auth_token(client)
        if not token:
            print("❌ 로그인 실패. 관리자 계정을 확인해주세요.")
            return
        print("✅ 로그인 성공")
        
        # Subject ID 캐시 (중복 조회 방지)
        subject_cache = {}
        
        # 업로드 시작
        print(f"\n📤 업로드 시작 (총 {len(excel_files)}개 파일)")
        if args.skip > 0:
            print(f"   (파일 #{args.skip + 1}부터 시작)")
        print("-" * 60)
        
        results = {
            "success": [],
            "failed": [],
            "skipped": []
        }
        
        start_idx = args.skip  # 원래 인덱스 추적
        for i, file_path in enumerate(excel_files, 1):
            original_idx = start_idx + i  # 전체 파일 목록에서의 인덱스
            
            # Excel 파일 내부에서 피험자 정보 추출
            excel_info = extract_subject_from_excel(file_path)
            last_name = excel_info.get('last_name', '')
            first_name = excel_info.get('first_name', '')
            
            # 파일명에서 날짜 추출
            _, _, _, test_date = extract_subject_info(file_path.name)
            date_str = test_date.strftime("%Y-%m-%d") if test_date else "unknown"
            
            print(f"\n[{original_idx}/{total_files}] {file_path.name}")
            print(f"   피험자 (Excel): {first_name} {last_name}")
            print(f"   날짜: {date_str}")
            
            if not last_name or not first_name:
                print(f"   ⚠️ Excel에서 피험자 정보를 찾을 수 없음")
                results["skipped"].append({
                    "file": file_path.name,
                    "reason": "Subject info not found in Excel"
                })
                continue
            
            # Subject ID 조회 (이름으로 검색, 캐시 사용)
            subject_id = await get_subject_by_name(client, token, last_name, first_name, subject_cache)
            if not subject_id:
                print(f"   ⚠️ DB에서 피험자를 찾을 수 없음: {first_name} {last_name}")
                results["skipped"].append({
                    "file": file_path.name,
                    "reason": f"Subject not found in DB: {first_name} {last_name}"
                })
                continue
            
            # 업로드 (재시도 로직 포함)
            print(f"   📤 업로드 중...")
            success, test_id, info = await upload_file_with_retry(
                token, file_path, subject_id,
                calc_method=args.calc_method,
                smoothing_window=args.smoothing
            )
            
            if success:
                print(f"   ✅ 성공! test_id: {test_id}")
                results["success"].append({
                    "file": file_path.name,
                    "test_id": test_id,
                    "subject": f"{first_name} {last_name}",
                    "date": date_str
                })
            else:
                print(f"   ❌ 실패: {info}")
                results["failed"].append({
                    "file": file_path.name,
                    "error": info
                })
            
            # 서버 부하 방지를 위한 딜레이 (2초)
            await asyncio.sleep(2.0)
        
        # 결과 요약
        print("\n" + "=" * 60)
        print("📊 업로드 결과 요약")
        print("=" * 60)
        print(f"   ✅ 성공: {len(results['success'])}개")
        print(f"   ❌ 실패: {len(results['failed'])}개")
        print(f"   ⚠️ 스킵: {len(results['skipped'])}개")
        
        # 결과 저장
        result_file = Path(__file__).parent / "import_results.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n📄 상세 결과 저장: {result_file}")
        
        if results["failed"]:
            print("\n❌ 실패한 파일:")
            for item in results["failed"]:
                print(f"   - {item['file']}: {item['error']}")


if __name__ == "__main__":
    asyncio.run(main())
