# 🧪 Backend & E2E Testing Strategy

**작성일:** 2026-01-16  
**상태:** 테스트 계획 수립 및 실행 단계

---

## 📋 Phase 6: Backend Unit Tests (3-4시간 예상)

### 6-1: 테스트 환경 설정 (30분)

#### 필요한 패키지
```bash
pip install pytest pytest-asyncio pytest-cov pytest-mock
```

#### 테스트 구조
```
backend/tests/
├── conftest.py              # pytest 설정 및 fixtures
├── test_auth.py             # 인증 테스트
├── test_subjects.py         # 피험자 관리 테스트
├── test_tests.py            # CPET 테스트 관리 테스트
├── test_cohorts.py          # 코호트 분석 테스트
└── test_models.py           # 데이터베이스 모델 테스트
```

#### pytest.ini 설정
```ini
[pytest]
testpaths = backend/tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
```

### 6-2: Authentication 테스트 (1시간)

**테스트 시나리오:**

```python
# test_auth.py
1. test_login_success
   - 유효한 이메일/비밀번호로 로그인
   - JWT 토큰 발급 확인
   - 사용자 정보 응답 확인

2. test_login_failure_invalid_credentials
   - 잘못된 비밀번호
   - 404 에러 응답 확인

3. test_login_failure_user_not_found
   - 존재하지 않는 사용자
   - 401 에러 응답 확인

4. test_register_success
   - 새 사용자 등록
   - 사용자 생성 확인
   - 응답 200 확인

5. test_register_failure_email_exists
   - 중복 이메일로 등록 시도
   - 400 에러 응답 확인

6. test_register_failure_invalid_email
   - 잘못된 이메일 형식
   - 422 유효성 검사 에러

7. test_get_current_user
   - 인증된 사용자 정보 조회
   - 올바른 사용자 정보 반환

8. test_update_current_user
   - 사용자 정보 업데이트
   - 일반 사용자는 role 변경 불가 확인

9. test_jwt_token_validation
   - 유효한 토큰 검증
   - 만료된 토큰 검증
   - 잘못된 토큰 검증
```

### 6-3: Subjects 테스트 (1시간)

**테스트 시나리오:**

```python
# test_subjects.py
1. test_list_subjects_success
   - 피험자 목록 조회
   - 페이지네이션 확인
   - 데이터 형식 검증

2. test_list_subjects_pagination
   - 페이지 1, 2, 3 데이터
   - total, pages 계산 확인
   - has_next_page, has_previous_page 검증

3. test_list_subjects_search
   - 검색 기능 (이름, 코드)
   - 필터링 (성별, 훈련 수준)
   - 결과 정확성 확인

4. test_list_subjects_unauthorized
   - 토큰 없이 접근
   - 401 에러 응답

5. test_list_subjects_forbidden
   - 일반 피험자가 접근
   - 403 에러 응답

6. test_get_subject_success
   - 특정 피험자 조회
   - 상세 정보 포함

7. test_get_subject_not_found
   - 존재하지 않는 피험자
   - 404 에러

8. test_create_subject_success
   - 새 피험자 생성
   - ID 자동 생성 확인
   - 생성일자 자동 설정

9. test_create_subject_validation
   - 필수 필드 검증
   - 데이터 타입 검증

10. test_update_subject_success
    - 피험자 정보 업데이트
    - 변경사항 반영 확인

11. test_delete_subject_success
    - 피험자 삭제
    - 관련 테스트도 삭제되는지 확인
```

### 6-4: Tests (CPET 테스트) 테스트 (1시간)

**테스트 시나리오:**

```python
# test_tests.py
1. test_list_tests_success
   - 테스트 목록 조회
   - 페이지네이션

2. test_get_test_metrics
   - 테스트 메트릭 조회
   - VO2Max, HR, VCO2 등 계산

3. test_upload_test_file_success
   - COSMED Excel 파일 업로드
   - 파일 파싱 확인
   - 데이터베이스 저장 확인

4. test_upload_test_file_invalid_format
   - 잘못된 파일 형식
   - 400 에러

5. test_upload_test_file_size_limit
   - 50MB 초과 파일
   - 413 에러

6. test_get_time_series_data
   - 시계열 데이터 조회
   - 시간 범위 필터링

7. test_delete_test_success
   - 테스트 삭제
   - 관련 호흡 데이터 삭제 확인
```

### 6-5: Authorization 테스트 (30분)

**테스트 시나리오:**

```python
# test_decorators.py
1. test_require_role_admin
   - Admin만 접근 가능
   - Researcher는 403

2. test_require_role_researcher
   - Researcher + Admin 접근 가능
   - Subject는 403

3. test_require_role_subject
   - Subject 접근 가능
   - 다른 역할은 403

4. test_require_role_missing_token
   - 토큰 없음
   - 401 에러

5. test_require_role_invalid_token
   - 잘못된 토큰
   - 401 에러
```

---

## 📋 Phase 7: E2E Tests with Playwright (4-5시간 예상)

### 7-1: Playwright 설정 (30분)

#### 설치
```bash
npm install -D @playwright/test
npx playwright install
```

#### 디렉토리 구조
```
e2e/
├── auth.spec.ts          # 인증 시나리오
├── navigation.spec.ts    # 네비게이션 시나리오
├── subjects.spec.ts      # 피험자 관리 시나리오
├── tests.spec.ts         # 테스트 관리 시나리오
├── fixtures/             # 테스트 데이터
│   ├── user.ts
│   ├── subject.ts
│   └── test.ts
└── utils/
    ├── test-helpers.ts
    └── constants.ts
```

#### playwright.config.ts
```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3100',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
  ],
});
```

### 7-2: 인증 시나리오 테스트 (1시간)

```typescript
// e2e/auth.spec.ts
test.describe('Authentication Flow', () => {
  test('Should login with valid credentials', async ({ page }) => {
    // 1. 로그인 페이지 접근
    // 2. 이메일/비밀번호 입력
    // 3. 로그인 버튼 클릭
    // 4. 대시보드로 리다이렉트 확인
    // 5. 사용자 이름 표시 확인
  });

  test('Should show error with invalid credentials', async ({ page }) => {
    // 1. 로그인 페이지 접근
    // 2. 잘못된 비밀번호 입력
    // 3. 에러 메시지 표시 확인
  });

  test('Should logout successfully', async ({ page }) => {
    // 1. 로그인
    // 2. 프로필 메뉴 클릭
    // 3. 로그아웃 클릭
    // 4. 로그인 페이지로 리다이렉트
  });

  test('Should persist session on page reload', async ({ page }) => {
    // 1. 로그인
    // 2. 페이지 새로고침
    // 3. 여전히 로그인 상태 확인
  });

  test('Should handle demo login', async ({ page }) => {
    // 1. Demo 버튼 클릭
    // 2. 역할 선택 (Researcher/Subject)
    // 3. 적절한 대시보드로 이동
  });
});
```

### 7-3: 네비게이션 시나리오 테스트 (1시간)

```typescript
// e2e/navigation.spec.ts
test.describe('Navigation', () => {
  test('Researcher should access all pages', async ({ page }) => {
    // 1. 연구자로 로그인
    // 2. Subjects 페이지 접근 및 로드 확인
    // 3. Cohort 분석 페이지 접근
    // 4. Test 상세 페이지 접근
    // 5. Metabolism 페이지 접근
  });

  test('Subject should only access own dashboard', async ({ page }) => {
    // 1. 피험자로 로그인
    // 2. 대시보드 접근 확인
    // 3. Subjects 페이지 접근 시도
    // 4. 403 또는 리다이렉트 확인
  });

  test('Should navigate using sidebar menu', async ({ page }) => {
    // 1. 로그인
    // 2. 각 메뉴 항목 클릭
    // 3. 올바른 페이지로 이동 확인
  });

  test('Should handle browser back/forward', async ({ page }) => {
    // 1. 여러 페이지 방문
    // 2. 뒤로 가기 동작
    // 3. 앞으로 가기 동작
    // 4. 올바른 페이지 표시 확인
  });
});
```

### 7-4: 피험자 관리 시나리오 테스트 (1시간)

```typescript
// e2e/subjects.spec.ts
test.describe('Subject Management', () => {
  test('Should list subjects with pagination', async ({ page }) => {
    // 1. 연구자로 로그인
    // 2. Subjects 페이지 접근
    // 3. 피험자 목록 로드 확인
    // 4. 페이지네이션 동작 확인
  });

  test('Should search and filter subjects', async ({ page }) => {
    // 1. 검색 키워드 입력
    // 2. 결과 필터링 확인
    // 3. 필터 (성별, 훈련 수준) 적용
  });

  test('Should view subject details', async ({ page }) => {
    // 1. 피험자 선택
    // 2. 상세 정보 페이지 로드
    // 3. 모든 필드 표시 확인
    // 4. 테스트 목록 표시
  });

  test('Should create new subject', async ({ page }) => {
    // 1. "Add Subject" 버튼 클릭
    // 2. 폼 작성
    // 3. 저장 클릭
    // 4. 목록에 추가됨 확인
    // 5. 성공 토스트 메시지 확인
  });

  test('Should validate subject form', async ({ page }) => {
    // 1. "Add Subject" 버튼 클릭
    // 2. 필수 필드 비움
    // 3. 저장 시도
    // 4. 검증 에러 표시 확인
  });

  test('Should update subject', async ({ page }) => {
    // 1. 피험자 선택
    // 2. 편집 모드 활성화
    // 3. 정보 수정
    // 4. 저장
    // 5. 변경사항 반영 확인
  });

  test('Should delete subject', async ({ page }) => {
    // 1. 피험자 선택
    // 2. 삭제 버튼 클릭
    // 3. 확인 다이얼로그
    // 4. 확인
    // 5. 목록에서 제거 확인
  });
});
```

### 7-5: 테스트 관리 시나리오 테스트 (1시간)

```typescript
// e2e/tests.spec.ts
test.describe('Test Management', () => {
  test('Should upload COSMED test file', async ({ page }) => {
    // 1. 테스트 업로드 페이지 접근
    // 2. 피험자 선택
    // 3. Excel 파일 업로드
    // 4. 파싱 진행 표시
    // 5. 완료 확인
    // 6. 메트릭 표시
  });

  test('Should show error for invalid file format', async ({ page }) => {
    // 1. 테스트 업로드 페이지 접근
    // 2. 잘못된 형식 파일 선택
    // 3. 에러 메시지 표시 확인
  });

  test('Should view test metrics', async ({ page }) => {
    // 1. 테스트 목록 접근
    // 2. 테스트 선택
    // 3. 상세 정보 페이지
    // 4. VO2Max, HR, VCO2 등 메트릭 표시
  });

  test('Should view time series chart', async ({ page }) => {
    // 1. 테스트 상세 페이지
    // 2. 차트 로드 확인
    // 3. 마우스 호버 시 데이터 팁 표시
    // 4. 줌 기능 확인
  });

  test('Should download test data', async ({ page }) => {
    // 1. 테스트 상세 페이지
    // 2. "Export" 버튼 클릭
    // 3. 파일 다운로드 시작
    // 4. 파일 검증
  });
});
```

### 7-6: 에러 처리 시나리오 (30분)

```typescript
// e2e/error-handling.spec.ts
test.describe('Error Handling', () => {
  test('Should show error boundary on component crash', async ({ page }) => {
    // 1. 특정 페이지 접근
    // 2. 의도적 에러 트리거
    // 3. ErrorBoundary UI 표시
    // 4. "Try Again" 버튼 동작
  });

  test('Should handle network errors', async ({ page }) => {
    // 1. 오프라인 모드 활성화
    // 2. 데이터 페칭 시도
    // 3. 에러 토스트 표시
    // 4. 재시도 가능
  });

  test('Should handle API timeout', async ({ page }) => {
    // 1. 느린 네트워크 시뮬레이션
    // 2. 요청 전송
    // 3. 타임아웃 발생
    // 4. 에러 메시지 표시
  });

  test('Should show 401 error on token expiration', async ({ page }) => {
    // 1. 로그인
    // 2. 토큰 만료 시뮬레이션
    // 3. 다시 로그인 페이지로 리다이렉트
  });
});
```

---

## 🎯 테스트 실행 계획

### 개발 환경에서 실행
```bash
# Backend 테스트
cd backend
pytest tests/ -v --cov=app

# Frontend E2E 테스트
cd frontend
npx playwright test

# 특정 테스트만 실행
npx playwright test e2e/auth.spec.ts
npx playwright test --debug
```

### 테스트 커버리지 목표
- Backend: 80%+ 커버리지
- Frontend: 모든 주요 사용자 플로우 커버

---

## ✅ 체크리스트

**Backend 테스트:**
- [ ] pytest 설정
- [ ] conftest.py (fixtures)
- [ ] test_auth.py (9 테스트)
- [ ] test_subjects.py (11 테스트)
- [ ] test_tests.py (7 테스트)
- [ ] test_decorators.py (5 테스트)
- [ ] 모든 테스트 통과
- [ ] 커버리지 80%+

**E2E 테스트:**
- [ ] Playwright 설정
- [ ] playwright.config.ts
- [ ] e2e/auth.spec.ts (5 테스트)
- [ ] e2e/navigation.spec.ts (4 테스트)
- [ ] e2e/subjects.spec.ts (7 테스트)
- [ ] e2e/tests.spec.ts (5 테스트)
- [ ] e2e/error-handling.spec.ts (4 테스트)
- [ ] 모든 테스트 통과

---

## 📊 예상 일정

| 항목 | 시간 | 상태 |
|------|------|------|
| Backend 테스트 설정 | 0.5h | ⏳ |
| Auth 테스트 | 1h | ⏳ |
| Subjects 테스트 | 1h | ⏳ |
| Tests 테스트 | 1h | ⏳ |
| Authorization 테스트 | 0.5h | ⏳ |
| **Backend 소계** | **4h** | **⏳** |
| E2E 설정 | 0.5h | ⏳ |
| Auth E2E | 1h | ⏳ |
| Navigation E2E | 1h | ⏳ |
| Subjects E2E | 1h | ⏳ |
| Tests E2E | 1h | ⏳ |
| Error Handling E2E | 0.5h | ⏳ |
| **E2E 소계** | **5h** | **⏳** |
| **총계** | **9h** | **⏳** |

---

**상태:** 테스트 계획 수립 완료 ✅  
**다음 단계:** Backend 테스트 환경 설정 및 작성
