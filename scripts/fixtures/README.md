# Test Fixtures & Sample Data

이 폴더는 개발/테스트용 샘플 데이터를 저장합니다.

## 파일 설명

### 복구 순서 (Import 시)
파일을 순서대로 실행해야 참조 무결성 유지:

1. **`restore_01_subjects.sql`**
   - 테스트 피험자 데이터 (5명)
   - 예: SUB-PAR-YON, Kim_Miso, SUB-PAR-JUN 등

2. **`restore_02_users.sql`**
   - 사용자 계정 데이터 (관리자, 연구원, 피험자)
   - JWT 토큰 테스트용

3. **`restore_03_cpet_tests.sql`**
   - CPET 테스트 메타데이터
   - 각 피험자의 테스트 기록

4. **`restore_04_processed_metabolism.sql`**
   - 처리된 대사 분석 데이터
   - VO2max, FATMAX 결과

## 사용 방법

### 모든 테스트 데이터 한 번에 복구:
```bash
cd scripts/fixtures
for file in restore_*.sql; do
  psql -U postgres -d cpet_db < "$file"
done
```

### 특정 데이터만 복구:
```bash
psql -U postgres -d cpet_db < restore_01_subjects.sql
```

## 주의사항

- 개발/테스트 환경에서만 사용
- 프로덕션 데이터 유실 위험이 있으므로 프로덕션 DB에서 실행 금지
- 새로운 테스트 데이터는 이 파일들을 수정하여 추가

## 테스트 계정 정보

- **Admin**: gerald.park@cpet.com / [기본 패스워드]
- **Researcher**: [fixtures에 정의된 데이터 참고]
- **Subject**: 각 피험자별 로그인 가능
