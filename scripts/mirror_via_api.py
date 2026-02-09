#!/usr/bin/env python3
"""
Supabase -> Local DB 미러링 스크립트 (REST API 사용)
Usage: python scripts/mirror_via_api.py
"""

import asyncio
import httpx
import asyncpg
from datetime import datetime, date, time
import json
import math

# Supabase 설정
SUPABASE_URL = "https://bdlqqjbzztiyyrljloiq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJkbHFxamJ6enRpeXlybGpsb2lxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njc4OTQ1NDksImV4cCI6MjA4MzQ3MDU0OX0.xhgRF54DWRLRWTz590yha7EnhTvcXELTDyq_oCjLGxY"

# Local DB 설정
LOCAL_DB_URL = "postgresql://cpet_user:cpet_password@localhost:5100/cpet_db"

# 미러링할 테이블 목록 (순서 중요 - FK 의존성 고려: 부모 → 자식)
TABLES = [
    "subjects",
    "users",
    "cpet_tests",
    "breath_data",
    "processed_metabolism",
    "cohort_stats",
]

async def fetch_table_data(client: httpx.AsyncClient, table: str) -> list:
    """Supabase에서 테이블 데이터 가져오기"""
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    all_data = []
    offset = 0
    limit = 1000

    while True:
        url = f"{SUPABASE_URL}/rest/v1/{table}?select=*&offset={offset}&limit={limit}"
        response = await client.get(url, headers=headers)

        if response.status_code != 200:
            print(f"  Error fetching {table}: {response.status_code} - {response.text}")
            break

        data = response.json()
        if not data:
            break

        all_data.extend(data)
        offset += limit

        if len(data) < limit:
            break

    return all_data


async def insert_data(conn: asyncpg.Connection, table: str, data: list):
    """로컬 DB에 데이터 삽입"""
    if not data:
        print(f"  {table}: 데이터 없음")
        return

    # 기존 데이터 삭제
    await conn.execute(f"TRUNCATE TABLE {table} CASCADE")

    # 컬럼 목록
    columns = list(data[0].keys())

    # INSERT 쿼리 생성
    placeholders = ", ".join([f"${i+1}" for i in range(len(columns))])
    column_names = ", ".join([f'"{c}"' for c in columns])

    query = f'INSERT INTO {table} ({column_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'

    # DB에서 컬럼 타입 조회 (datetime 자동 변환용)
    col_types = {}
    for col in columns:
        try:
            type_row = await conn.fetchrow(
                "SELECT data_type FROM information_schema.columns WHERE table_name=$1 AND column_name=$2",
                table, col
            )
            if type_row:
                col_types[col] = type_row["data_type"]
        except Exception:
            pass

    # 데이터 삽입
    inserted = 0
    for row in data:
        values = []
        for col in columns:
            val = row.get(col)
            col_type = col_types.get(col, "")

            # NaN 문자열 → None (숫자 컬럼)
            if val == "NaN" or val == "Infinity" or val == "-Infinity":
                val = None
            # JSON 필드 처리
            elif isinstance(val, (dict, list)):
                val = json.dumps(val)
            # datetime 문자열 → datetime 객체 변환
            elif isinstance(val, str) and col_type in (
                "timestamp without time zone", "timestamp with time zone"
            ):
                try:
                    val = datetime.fromisoformat(val.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass
            # date 문자열 → date 객체 변환
            elif isinstance(val, str) and col_type == "date":
                try:
                    val = date.fromisoformat(val[:10])
                except (ValueError, TypeError):
                    pass
            # time 문자열 → time 객체 변환
            elif isinstance(val, str) and col_type == "time without time zone":
                try:
                    parts = val.split(":")
                    val = time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
                except (ValueError, TypeError, IndexError):
                    pass
            # float NaN → None
            elif isinstance(val, float) and math.isnan(val):
                val = None
            values.append(val)

        try:
            await conn.execute(query, *values)
            inserted += 1
        except Exception as e:
            print(f"  Error inserting into {table}: {e}")
            print(f"  Row: {row}")
            continue

    print(f"  {table}: {inserted}/{len(data)} rows 삽입됨")


async def main():
    print("=" * 50)
    print("Supabase -> Local DB 미러링 (REST API)")
    print("=" * 50)
    print(f"시작 시간: {datetime.now()}")
    print()

    # Supabase 연결
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Local DB 연결
        conn = await asyncpg.connect(LOCAL_DB_URL)

        try:
            # FK 제약조건 일시 비활성화
            await conn.execute("SET session_replication_role = 'replica';")

            for table in TABLES:
                print(f"\n[{table}] 처리 중...")

                # 데이터 가져오기
                data = await fetch_table_data(client, table)
                print(f"  Supabase에서 {len(data)} rows 가져옴")

                # 로컬에 삽입
                await insert_data(conn, table, data)

            # FK 제약조건 재활성화
            await conn.execute("SET session_replication_role = 'origin';")

        finally:
            await conn.close()

    print()
    print("=" * 50)
    print(f"완료 시간: {datetime.now()}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
