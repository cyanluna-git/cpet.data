# Database Scripts

모든 데이터베이스 관리 스크립트를 중앙에서 관리합니다.

## 폴더 구조

```
scripts/
├── init-db.sql                 # DB 초기화 (필수)
├── insert_cpet_users.sql       # 기본 사용자/피험자 생성
├── reset_local_dataset.sh      # 로컬 검증용 known-good dataset 재구성
├── verify_local_inscyd.sh      # 로컬 INSCYD 검증 (migration + pytest + build)
├── backups/                    # 데이터베이스 백업 파일들
│   ├── backup_data.sql         # 전체 데이터 백업 (52.5MB)
│   ├── backup_with_columns.sql # 구조 포함 백업
│   ├── backup_breath_data.sql  # 호흡 데이터만 백업
│   ├── supabase_restore.sql    # Supabase 복구 스크립트
│   └── README.md               # 백업 파일 설명서
│
└── fixtures/                   # 개발/테스트용 샘플 데이터
    ├── restore_01_subjects.sql       # 테스트 피험자
    ├── restore_02_users.sql          # 테스트 계정
    ├── restore_03_cpet_tests.sql     # 테스트 메타데이터
    ├── restore_04_processed_metabolism.sql  # 분석 결과
    └── README.md                     # 사용법 및 주의사항
```

## 빠른 시작

### 1️⃣ 데이터베이스 초기화 (처음 설정)
```bash
psql -U postgres < scripts/init-db.sql
```

### 2️⃣ 기본 사용자 생성 (Admin, 테스트 피험자)
```bash
psql -U postgres -d cpet_db < scripts/insert_cpet_users.sql
```

### 3️⃣ 테스트 데이터 추가 (선택사항)
```bash
cd scripts/fixtures
bash -c 'for file in restore_*.sql; do psql -U postgres -d cpet_db < "$file"; done'
```

### 4️⃣ 로컬 검증 데이터셋 재구성
```bash
./scripts/reset_local_dataset.sh
```

### 5️⃣ INSCYD 로컬 검증
```bash
./scripts/verify_local_inscyd.sh
```

## 스크립트 설명

### 필수 스크립트 (Root)

| 파일 | 목적 | 언제 사용 |
|------|------|----------|
| `init-db.sql` | 테이블, 인덱스, 컬럼 생성 | DB 초기 구성 시 (1회) |
| `insert_cpet_users.sql` | Admin 계정, 테스트 피험자 생성 | DB 초기 구성 시 |
| `reset_local_dataset.sh` | Docker PostgreSQL을 known-good fixture dataset으로 재구성 | 로컬 상태 초기화 시 |
| `verify_local_inscyd.sh` | reset 후 INSCYD pytest/build/E2E까지 일괄 검증 | 로컬 회귀 검증 시 |

### 선택사항 (Backups)

- **`backup_data.sql`**: 전체 데이터 백업 (52.5MB) - 마이그레이션/복구용
- **`supabase_restore.sql`**: Supabase → Local PostgreSQL 마이그레이션
- 기타: 히스토리용 백업 (필요 시만)

### 개발 보조 (Fixtures)

테스트/개발 시 샘플 데이터가 필요한 경우 사용:
- 5명의 테스트 피험자
- 관리자, 연구원 계정
- 기본 CPET 테스트 기록
- `SUB-PAR-GEU`의 breath_data/processed_metabolism/INSCYD 히스토리

## 데이터베이스 리셋

완전히 깨끗한 상태로 시작하려면:
```bash
./scripts/reset_local_dataset.sh
```

## 주의사항

⚠️ **프로덕션 환경에서 복구 스크립트 실행 금지**
- Fixtures의 restore_*.sql은 테스트용 데이터입니다
- 프로덕션 DB에서 실행하면 데이터 유실 위험
- `verify_local_inscyd.sh`는 항상 reset을 먼저 수행하므로 기존 로컬 DB 상태를 덮어씁니다

## 백업 전략

1. **자동 백업**: Docker Compose로 정기 백업 (권장)
2. **수동 백업**: 필요시 `backup_data.sql` 사용
3. **Supabase 마이그레이션**: `supabase_restore.sql` 활용
