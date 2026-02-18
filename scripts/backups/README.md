# Database Backups

이 폴더는 데이터베이스 백업 파일들을 저장합니다.

## 파일 설명

### `backup_data.sql` (52.5MB)
- 전체 데이터베이스 백업
- 생성일: 2026-01-25
- 포함: subjects, users, cpet_tests, breath_data, processed_metabolism

**복구 방법:**
```bash
psql -U postgres -d cpet_db < backup_data.sql
```

### `backup_with_columns.sql`
- 컬럼 구조가 포함된 부분 백업

### `backup_breath_data.sql`
- 호흡 데이터만 백업

### `supabase_restore.sql`
- Supabase 마이그레이션용 복구 스크립트
- Supabase에서 다운로드한 데이터를 로컬 PostgreSQL로 복원할 때 사용

## 주의사항

- 백업 파일은 크기가 크므로 필요한 경우에만 사용
- 정기적으로 필요 없는 백업은 삭제 권장
- 프로덕션 데이터는 별도의 백업 솔루션 사용 권장
