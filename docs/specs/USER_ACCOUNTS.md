# CPET 플랫폼 사용자 계정 정보

> 생성일: 2026-01-16  
> 환경: 개발/테스트

## 공통 로그인 정보

| 항목 | 값 |
|------|-----|
| **패스워드** | `cpet2026!` |
| **이메일 형식** | `firstname.lastname@cpet.com` |

---

## 관리자 계정

| 이메일 | 역할 | 이름 |
|--------|------|------|
| gerald.park@cpet.com | admin | Gerald Park |

---

## 피험자 계정 (13명)

| # | 이메일 | 이름 | 연구 ID | 테스트 파일 수 |
|---|--------|------|---------|----------------|
| 1 | changsun.hong@cpet.com | Changsun Hong | SUB-HON-CHA | 7 |
| 2 | daesoon.kim@cpet.com | Daesoon Kim | SUB-KIM-DAE | 3 |
| 3 | dongwook.kim@cpet.com | Dongwook Kim | SUB-KIM-DON | 5 |
| 4 | doyoon.kim@cpet.com | Doyoon Kim | SUB-KIM-DOY | 1 |
| 5 | geunyun.park@cpet.com | Geunyun Park | SUB-PAR-GEU | 4 |
| 6 | haesung.shin@cpet.com | Haesung Shin | SUB-SHI-HAE | 2 |
| 7 | junghooon.park@cpet.com | Junghooon Park | SUB-PAR-JUN | 1 |
| 8 | kwangho.cho@cpet.com | Kwangho Cho | SUB-CHO-KWA | 1 |
| 9 | kyoungkyu.son@cpet.com | Kyoungkyu Son | SUB-SON-KYO | 1 |
| 10 | sunghoon.chung@cpet.com | Sunghoon Chung | SUB-CHU-SUN | 2 |
| 11 | sungjun.joo@cpet.com | Sungjun Joo | SUB-JOO-SUN | 3 |
| 12 | woochan.seok@cpet.com | Woochan Seok | SUB-SEO-WOO | 4 |
| 13 | youngdoo.park@cpet.com | Youngdoo Park | SUB-PAR-YOU | - |

---

## 데이터베이스 확인 명령

```bash
# 전체 사용자 목록 조회
docker exec -i cpet-db psql -U cpet_user -d cpet_db -c "
SELECT u.email, u.role, s.research_id, s.encrypted_name
FROM users u
LEFT JOIN subjects s ON u.subject_id = s.id
WHERE u.email LIKE '%@cpet.com'
ORDER BY u.email;"

# 특정 사용자 패스워드 재설정 (cpet2026!)
docker exec -i cpet-db psql -U cpet_user -d cpet_db -c "
UPDATE users 
SET password_hash = '\$2b\$12\$Ew/lSYsANZfWQH6J6Oewc.E6IC7NGeTNauLEei/se8XTkcBd9osZu'
WHERE email = 'user@cpet.com';"
```

---

## 계정 생성 스크립트

새로운 피험자 추가 시 사용:

```bash
# 스크립트 실행
cd /Users/cyanluna-pro16/dev/cpet.db
source .venv/bin/activate
python scripts/create_users_from_cpet_data.py

# SQL 실행
docker exec -i cpet-db psql -U cpet_user -d cpet_db < scripts/insert_cpet_users.sql
```

---

## 참고사항

- 모든 피험자 계정은 `CPET_data/` 폴더의 파일명에서 자동 추출됨
- 이메일은 `firstname.lastname@cpet.com` 형식으로 자동 생성
- 연구 ID는 `SUB-{성 3자}-{이름 3자}` 형식
- 피험자는 자신의 테스트 데이터만 조회 가능 (role: user)
- 관리자는 모든 데이터 접근 가능 (role: admin)
