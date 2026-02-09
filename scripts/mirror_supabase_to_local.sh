#!/bin/bash
# Supabase -> Local DB 미러링 스크립트
# Usage: ./scripts/mirror_supabase_to_local.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Supabase -> Local DB 미러링 ===${NC}"

# Supabase (Source)
SUPA_HOST="db.bdlqqjbzztiyyrljloiq.supabase.co"
SUPA_PORT="5432"
SUPA_USER="postgres"
SUPA_PASSWORD="xKpsLwB5sV5Q15TV"
SUPA_DB="postgres"

# Local (Target)
LOCAL_HOST="localhost"
LOCAL_PORT="5100"
LOCAL_USER="cpet_user"
LOCAL_PASSWORD="cpet_password"
LOCAL_DB="cpet_db"

# Temp dump file
DUMP_FILE="/tmp/supabase_dump_$(date +%Y%m%d_%H%M%S).sql"

echo -e "${GREEN}1. Supabase에서 데이터 덤프 중...${NC}"
PGPASSWORD="$SUPA_PASSWORD" pg_dump \
    -h "$SUPA_HOST" \
    -p "$SUPA_PORT" \
    -U "$SUPA_USER" \
    -d "$SUPA_DB" \
    --no-owner \
    --no-acl \
    --clean \
    --if-exists \
    -F p \
    -f "$DUMP_FILE"

echo -e "${GREEN}2. 덤프 파일 생성 완료: $DUMP_FILE${NC}"
echo "   파일 크기: $(du -h "$DUMP_FILE" | cut -f1)"

echo -e "${GREEN}3. 로컬 DB에 복원 중...${NC}"
PGPASSWORD="$LOCAL_PASSWORD" psql \
    -h "$LOCAL_HOST" \
    -p "$LOCAL_PORT" \
    -U "$LOCAL_USER" \
    -d "$LOCAL_DB" \
    -f "$DUMP_FILE" \
    2>&1 | grep -E "(ERROR|NOTICE|WARNING)" || true

echo -e "${GREEN}4. 미러링 완료!${NC}"

# 테이블 카운트 비교
echo -e "\n${YELLOW}=== 데이터 검증 ===${NC}"
echo "Supabase 테이블 row counts:"
PGPASSWORD="$SUPA_PASSWORD" psql \
    -h "$SUPA_HOST" \
    -p "$SUPA_PORT" \
    -U "$SUPA_USER" \
    -d "$SUPA_DB" \
    -c "SELECT schemaname, relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 10;"

echo -e "\nLocal 테이블 row counts:"
PGPASSWORD="$LOCAL_PASSWORD" psql \
    -h "$LOCAL_HOST" \
    -p "$LOCAL_PORT" \
    -U "$LOCAL_USER" \
    -d "$LOCAL_DB" \
    -c "SELECT schemaname, relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 10;"

# Cleanup
echo -e "\n${YELLOW}덤프 파일 삭제할까요? (y/n)${NC}"
read -r answer
if [[ "$answer" == "y" ]]; then
    rm "$DUMP_FILE"
    echo "덤프 파일 삭제됨"
else
    echo "덤프 파일 유지: $DUMP_FILE"
fi

echo -e "\n${GREEN}=== 완료 ===${NC}"
