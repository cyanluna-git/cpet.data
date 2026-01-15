# CPET.db 프로젝트 통합 가이드

## 프론트엔드 (.ai-skills 스킬 적용)

### 1. 기존 컴포넌트 검토

성능 최적화가 필요한 파일들:

```bash
# 번들 최적화 검토
grep -r "import.*from" frontend/src/components --include="*.tsx" | wc -l

# 데이터 페칭 패턴 검토
grep -r "useEffect.*fetch\|useFetch" frontend/src --include="*.tsx"

# 데이터 변환 검토
grep -r "useMemo\|useCallback" frontend/src --include="*.tsx"
```

### 2. 우선 순위별 개선

#### 🔴 Critical (먼저 수정)
1. **번들 크기** - MetabolismChart 같은 무거운 컴포넌트 lazy load
2. **워터폴** - 병렬 Supabase 쿼리 활성화
3. **서버 컴포넌트** - 데이터 페칭 로직을 Server Components로 이동

#### 🟠 High (다음)
1. **Supabase 실시간** - 구독 정리 및 캐싱
2. **CPET 데이터 메모이제이션** - 무거운 계산 최적화
3. **가상 스크롤** - 큰 테이블 성능

#### 🟡 Medium (순차적으로)
1. **API 배치 처리** - Cloud Run 호출 최소화
2. **이미지 최적화** - next/image 사용
3. **폰트 최적화** - 폰트 로딩 전략

### 3. 검증 체크리스트

```bash
# ✅ 번들 크기 확인
npm run build
ls -lh .next/static/chunks/

# ✅ 성능 메트릭 (Core Web Vitals)
npm run lighthouse

# ✅ 규칙 준수 확인
grep -r "client-side-only-logic" frontend/src/app --include="*.tsx"
```

## 백엔드 (Cloud Run 배포)

### 1. FastAPI 구조 확인

```python
# backend/app/main.py 구조
- Middleware (CORS, logging)
- API Routes (auth, cohorts, subjects, tests)
- Database layer (Supabase client)
- Service layer (data processing)
```

### 2. 성능 최적화

#### 데이터베이스
```python
# ✅ 쿼리 배치 처리
@app.post("/api/cohorts/{cohort_id}/metrics")
async def get_cohort_metrics(cohort_id: str, body: dict):
    # 한 번에 여러 데이터 페칭
    stats, respiratory, metabolism = await asyncio.gather(
        get_stats(cohort_id),
        get_respiratory(cohort_id),
        get_metabolism(cohort_id)
    )
    return {"stats": stats, "respiratory": respiratory, "metabolism": metabolism}
```

#### CPET 분석
```python
# ✅ 무거운 계산 최적화 및 캐싱
from functools import lru_cache

@lru_cache(maxsize=128)
def calculate_vo2_metrics(test_id: str, weight: float):
    # 계산 결과 캐시
    ...
```

### 3. 배포 설정

```bash
# Docker 빌드 및 테스트
docker build -t cpet-db-backend:latest -f backend/Dockerfile .
docker run -p 8000:8080 cpet-db-backend:latest

# Cloud Run 배포
bash .ai-skills/deployment-guidelines/rules/cloud-run-deploy.sh
```

## 데이터베이스 (Supabase)

### 1. 초기 설정

```bash
# 마이그레이션 실행
cd backend
supabase migration up

# RLS 정책 활성화
# .ai-skills/deployment-guidelines/rules/supabase-setup.md 참고
```

### 2. 성능 최적화

```sql
-- 인덱스 생성
CREATE INDEX idx_cpet_tests_subject ON cpet_tests(subject_id);
CREATE INDEX idx_cpet_tests_created_at ON cpet_tests(created_at DESC);

-- 실시간 활성화
ALTER PUBLICATION supabase_realtime ADD TABLE cpet_tests;

-- RLS 정책 검증
SELECT tablename, policyname 
FROM pg_policies 
WHERE schemaname = 'public';
```

## 📊 성능 측정

### Before & After

```bash
# 배포 전 성능 측정
npm run lighthouse -- frontend/

# 최적화 적용
# ... 규칙 적용 ...

# 배포 후 성능 측정
npm run lighthouse -- frontend/
```

### 주요 지표

| 메트릭 | Before | After | 목표 |
|-------|--------|-------|-----|
| FCP (First Contentful Paint) | 2.5s | 1.2s | < 1.5s |
| LCP (Largest Contentful Paint) | 4.8s | 2.1s | < 2.5s |
| CLS (Cumulative Layout Shift) | 0.15 | 0.05 | < 0.1 |
| Bundle Size | 350KB | 220KB | < 250KB |

## 🔄 지속적 개선

### 월간 검토 절차

1. **성능 메트릭 분석**
   - Vercel Analytics 확인
   - Core Web Vitals 추적
   - 느린 API 엔드포인트 식별

2. **새로운 규칙 작성**
   - 프로젝트 특화 문제 발견
   - `.ai-skills/react-best-practices/rules/` 에 추가
   - 팀과 공유

3. **배포 체크리스트**
   - 성능 테스트 통과
   - RLS 정책 검증
   - 환경 변수 설정 확인

### 자동화

```yaml
# .github/workflows/performance.yml
name: Performance Check
on: [pull_request]

jobs:
  performance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Lighthouse
        run: npm run lighthouse
      - name: Validate AI Skills Rules
        run: cd .ai-skills/react-best-practices && pnpm validate
```

## 🎯 다음 단계

### Week 1-2
- [ ] SKILL.md 읽기 및 이해
- [ ] 현재 번들 크기 측정
- [ ] Critical 우선순위 규칙 3개 적용

### Week 3-4
- [ ] High 우선순위 규칙 적용
- [ ] Supabase 쿼리 최적화
- [ ] Cloud Run 배포 테스트

### Week 5+
- [ ] 성능 메트릭 재측정
- [ ] 팀 교육 및 코드 리뷰
- [ ] 정기적 유지보수 절차 수립

---

더 자세한 내용은 해당 디렉토리의 README.md와 규칙 파일을 참고하세요.
