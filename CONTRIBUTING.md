# 🤝 CPET Platform Contributing Guide

CPET 프로젝트에 기여해주셔서 감사합니다! 이 문서는 개발 환경 설정부터 코드 제출까지의 모든 과정을 설명합니다.

---

## 📋 목차

1. [개발 환경 설정](#개발-환경-설정)
2. [브랜치 전략](#브랜치-전략)
3. [코드 스타일](#코드-스타일)
4. [커밋 메시지](#커밋-메시지)
5. [Pull Request 프로세스](#pull-request-프로세스)
6. [테스트 작성](#테스트-작성)
7. [문서화](#문서화)

---

## 개발 환경 설정

### 필수 요구사항

- **Python:** 3.12+
- **Node.js:** 18+ (npm 또는 yarn)
- **Docker:** 데이터베이스 실행용
- **Git:** 버전 관리

### 1단계: 저장소 복제

```bash
git clone https://github.com/your-org/cpet.db.git
cd cpet.db
```

### 2단계: Python 환경 설정

```bash
# 가상 환경 생성
python3 -m venv .venv

# 활성화 (macOS/Linux)
source .venv/bin/activate

# 활성화 (Windows)
.venv\Scripts\activate

# 의존성 설치
pip install -r backend/requirements.txt
```

### 3단계: Node.js 환경 설정

```bash
cd frontend

# 의존성 설치
npm install

cd ..
```

### 4단계: 데이터베이스 시작

```bash
# Docker Compose로 PostgreSQL + TimescaleDB 시작
docker-compose up -d

# 데이터베이스 초기화
psql -h localhost -U postgres -d cpet < scripts/init-db.sql
```

### 5단계: 환경 변수 설정

```bash
# .env 파일 생성 (루트 디렉토리)
cat > .env << EOF
# Backend
VITE_API_URL=http://localhost:8100
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5100/cpet
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Frontend
VITE_DEMO_MODE=true
VITE_ANALYTICS=false
EOF
```

### 6단계: 개발 서버 실행

```bash
# 모든 서비스 시작 (run.py 사용)
python run.py

# 또는 수동으로 터미널을 나누어 시작
# Terminal 1: Backend
cd backend && python -m uvicorn app.main:app --reload --port 8100

# Terminal 2: Frontend
cd frontend && npm run dev

# Terminal 3: (선택) Database 모니터링
docker logs -f cpet-db
```

### 7단계: 검증

- Backend: http://localhost:8100/docs (API 문서)
- Frontend: http://localhost:3100
- Database: postgres://postgres:postgres@localhost:5100/cpet

---

## 브랜치 전략

### 브랜치 명명 규칙

```
feature/feature-name          # 새 기능
fix/bug-name                  # 버그 수정
refactor/refactor-name        # 코드 리팩토링
docs/documentation-name       # 문서 추가
perf/performance-improvement  # 성능 개선
test/test-name                # 테스트 추가
```

### 예시

```bash
# 새 기능 브랜치 생성
git checkout -b feature/add-subject-list-filtering

# 버그 수정 브랜치
git checkout -b fix/navigation-redirect-issue

# 로컬에서 작업
git add .
git commit -m "feat: add subject filtering by name and gender"
git push origin feature/add-subject-list-filtering
```

---

## 코드 스타일

### Python

```python
# ✅ Good: Type hints, docstring
async def get_subjects(
    db: DBSession,
    page: int = Query(1, ge=1),
) -> SubjectListResponse:
    """
    피험자 목록 조회 (페이지네이션)
    
    Args:
        db: 데이터베이스 세션
        page: 페이지 번호 (1부터 시작)
    
    Returns:
        피험자 목록과 페이지네이션 정보
    """
    service = SubjectService(db)
    subjects, total = await service.get_list(page=page)
    return SubjectListResponse(items=subjects, total=total, page=page)


# ❌ Bad: No types, no docstring
def get_subjects(db, page=1):
    subjects = db.query(Subject).offset((page-1)*20).limit(20).all()
    return subjects
```

### TypeScript/React

```typescript
// ✅ Good: Type-safe, documented
interface UseSubjectsOptions {
  page?: number;
  search?: string;
}

export function useSubjects(options: UseSubjectsOptions = {}) {
  const { data, loading, error } = useFetch(
    () => api.getSubjects(options),
    { showErrorToast: true }
  );
  
  return { subjects: data?.items || [], loading, error };
}

// ❌ Bad: No types
export function useSubjects(options) {
  const result = useFetch(() => api.getSubjects(options));
  return result;
}
```

### 포맷팅

**Python:**
```bash
# 설치
pip install black isort flake8

# 포맷팅
black backend/
isort backend/

# 린트
flake8 backend/
```

**TypeScript:**
```bash
npm run lint
npm run format
```

---

## 커밋 메시지

### 형식

```
<type>(<scope>): <subject>

<body>

<footer>
```

### 타입

- `feat`: 새 기능
- `fix`: 버그 수정
- `refactor`: 코드 리팩토링
- `docs`: 문서
- `test`: 테스트 추가
- `perf`: 성능 개선
- `chore`: 빌드, 의존성 업데이트

### 예시

```
feat(navigation): add route-based navigation hook

- Create useNavigation hook for centralized routing
- Update all route wrappers to use new hook
- Reduce code duplication by 31%

Closes #123
```

```
fix(api): handle paginated responses in SubjectListPage

The page was treating API response as direct array.
Extract items from PaginatedResponse using helper.

Fixes #456
```

---

## Pull Request 프로세스

### 1. PR 생성 전 체크리스트

- [ ] 코드가 코드 스타일 가이드를 따르는가?
- [ ] 새로운 기능에 대한 테스트를 작성했는가?
- [ ] 기존 테스트가 모두 통과하는가?
- [ ] 문서가 업데이트되었는가?
- [ ] 커밋 메시지가 명확한가?

### 2. PR 설명 템플릿

```markdown
## 설명
이 PR이 무엇을 해결하는지 간단히 설명해주세요.

## 타입
- [ ] 버그 수정
- [ ] 새 기능
- [ ] 코드 리팩토링
- [ ] 문서 업데이트

## 변경사항
- 변경 항목 1
- 변경 항목 2
- 변경 항목 3

## 테스트 방법
테스트 방법을 설명해주세요:

1. 단계 1
2. 단계 2
3. 예상 결과

## 스크린샷 (해당하는 경우)
![스크린샷](url)

## 관련 이슈
Closes #123
```

### 3. 리뷰 받기

```bash
# PR 생성 후 리뷰어를 지정
# GitHub UI에서 Reviewers 추가
```

### 4. 피드백 반영

```bash
# 피드백 반영 후 커밋
git add .
git commit -m "refactor: address review feedback"
git push origin feature/your-feature
```

### 5. 병합

리뷰어가 승인하면 squash and merge로 병합:

```bash
# 자동으로 처리되거나, 로컬에서 수동 처리
git checkout main
git pull origin main
git merge --squash origin/feature/your-feature
git commit -m "feat(scope): your feature description"
git push origin main
```

---

## 테스트 작성

### Frontend 테스트

```typescript
// ✅ 좋은 예: 명확한 테스트
describe('useSubjects', () => {
  it('should fetch subjects successfully', async () => {
    const mockData = [{ id: '1', name: 'Subject 1' }];
    const fetchFn = vi.fn(() => Promise.resolve(mockData));
    
    const { result } = renderHook(() => useSubjects());
    
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
    
    expect(result.current.subjects).toEqual(mockData);
  });
});
```

### 테스트 실행

```bash
# Frontend
cd frontend
npm run test              # 모든 테스트 실행
npm run test -- --watch  # 감시 모드
npm run test:coverage    # 커버리지 보고서

# Backend (설정 후)
pytest backend/tests/
pytest backend/tests/ -v  # 상세 출력
```

---

## 문서화

### 코드 주석

```python
# ✅ Good: 'why' 설명
# 지수 백오프를 사용하여 네트워크 혼잡 시 재시도 간격 증가
delay = base_delay * (2 ** retry_count)

# ❌ Bad: 명백한 것을 설명
# delay 변수에 값 할당
delay = 1000
```

### 함수 문서화

```python
"""
피험자 목록 조회

Args:
    db: 데이터베이스 세션
    page: 페이지 번호
    page_size: 페이지 크기

Returns:
    SubjectListResponse: 피험자 목록과 페이지네이션 정보

Raises:
    HTTPException: 권한 없음 (401), 데이터베이스 오류 (500)

Example:
    subjects = await get_subjects(db, page=1, page_size=20)
"""
```

### README 업데이트

변경사항이 사용자를 위한 것이라면 README를 업데이트하세요:

```markdown
## Features

- ✨ [설명]
- 🐛 [설명]
- 📈 [설명]

## Getting Started

[단계별 가이드]
```

---

## 문제 해결

### 일반적인 문제

**Q: `ModuleNotFoundError: No module named 'app'`**
```bash
# A: Python 경로 설정
export PYTHONPATH="${PYTHONPATH}:$(pwd)/backend"
```

**Q: `VITE API_URL is not defined`**
```bash
# A: .env 파일 확인
cat .env | grep VITE_API_URL
```

**Q: Docker 에러**
```bash
# A: 컨테이너 재시작
docker-compose down
docker-compose up -d
```

---

## 도움말

### 리소스

- [FastAPI 문서](https://fastapi.tiangolo.com/)
- [React 문서](https://react.dev/)
- [TypeScript 문서](https://www.typescriptlang.org/)
- [Conventional Commits](https://www.conventionalcommits.org/)

### 연락처

질문이 있으신가요?
- 이슈 생성: GitHub Issues
- 토론: GitHub Discussions
- 이메일: team@cpet.com

---

## 라이선스

CPET 프로젝트에 기여하면 귀하의 기여가 LICENSE 파일의 라이선스 하에 공개됩니다.

---

**감사합니다! 🙏**
