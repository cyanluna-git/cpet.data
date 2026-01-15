# 🔍 CPET Platform 코드 리뷰 및 개선 계획

**작성일:** 2026-01-15  
**상태:** 진행 중 (Phase 1-2 완료, Phase 1-3 완료)

---

## 📋 개선사항 목록

### ✅ Phase 1: 우선순위 높음 (이번주)

#### 1️⃣ Frontend Navigation 로직 추출 (30분)
- **상태:** ✅ COMPLETED
- **목표:** 중복된 `handleNavigate` 로직을 `useNavigation` 훅으로 통합
- **파일:**
  - `frontend/src/types/navigation.ts` (새 파일)
  - `frontend/src/hooks/useNavigation.ts` (새 파일)
  - `frontend/src/utils/navigationConfig.ts` (새 파일)
  - `frontend/src/App.tsx` (수정)

**상세 내용:**
```
- 6개 wrapper에서 중복된 handleNavigate 제거
- navigationMap으로 중앙 집중식 관리
- View 타입 안정성 강화 (ROUTE_VIEWS 상수)
✅ Code reduction: 426 → 294 lines (-31%)
✅ Commit: "refactor: consolidate navigation logic into useNavigation hook"
```

---

#### 2️⃣ API 응답 표준화 - Frontend (1시간)
- **상태:** ✅ COMPLETED
- **목표:** 모든 페이지에서 `extractItems()` 유틸 사용
- **파일:**
  - `frontend/src/utils/apiHelpers.ts` (새 파일)
  - `frontend/src/components/pages/ResearcherDashboard.tsx` (수정)
  - `frontend/src/components/pages/SubjectListPage.tsx` (수정)
  - `frontend/src/components/pages/SubjectDashboard.tsx` (수정)

**상세 내용:**
```
- PaginatedResponse 처리 자동화
- 모든 페이지에서 일관된 데이터 추출
- 에러 처리 표준화 (getErrorMessage)
✅ All pages now use extractItems() helper
✅ Commit: "refactor: standardize API response handling with extractItems helper"
```

---

#### 3️⃣ 에러 바운더리 추가 (30분)
- **상태:** ✅ COMPLETED
- **목표:** 페이지 오류 시 앱 전체 크래시 방지
- **파일:**
  - `frontend/src/components/ErrorBoundary.tsx` (새 파일)
  - `frontend/src/App.tsx` (수정)

**상세 내용:**
```
- 페이지별 오류 격리
- 사용자 친화적 에러 메시지
- 콘솔에 에러 로깅
```

---

### 🟡 Phase 2: 우선순위 중간 (다음주)

#### 4️⃣ useFetch 커스텀 훅 (1시간)
- **상태:** ❌ Not Started
- **목표:** API 호출 로직 재사용 가능하게 추상화
- **파일:**
  - `frontend/src/hooks/useFetch.ts` (새 파일)
  - 전체 페이지 리팩토링

---

#### 5️⃣ Backend API 응답 표준화 (1시간)
- **상태:** ✅ COMPLETED
- **목표:** 일관된 응답 형식 제공
- **파일:**
  - `backend/app/core/responses.py` (새 파일 - 생성됨)
  - `backend/app/api/auth.py` (수정 가능)
  - `backend/app/api/subjects.py` (수정 가능)
  - `backend/app/api/tests.py` (수정 가능)

**상세 내용:**
```
✅ ApiResponse<T> 제네릭 클래스 생성
✅ PaginatedResponse 클래스 생성
✅ ErrorResponse 표준 형식 정의
✅ success_response(), error_response() 헬퍼 함수 생성
✅ Commit: "feat: add standard backend API response classes"
```

---

#### 6️⃣ Backend 권한 검사 데코레이터 (1시간)
- **상태:** ✅ COMPLETED
- **목표:** `require_role` 데코레이터로 권한 검사 일관화
- **파일:**
  - `backend/app/core/decorators.py` (새 파일 - 생성됨)
  - `backend/app/api/auth.py` (수정 가능)
  - `backend/app/api/subjects.py` (수정 가능)
  - `backend/app/api/tests.py` (수정 가능)

**상세 내용:**
```
✅ @require_role(*roles) 데코레이터 생성
✅ @require_admin, @require_researcher, @require_subject 편의 데코레이터
✅ 의존성 주입(DI)과 호환 가능한 구조
✅ Commit: "feat: add role-based access control decorators"
```

---

### 🟢 Phase 3: 우선순위 낮음 (향후)

#### 7️⃣ useAsync 커스텀 훅 (1시간)
- **상태:** ❌ Not Started
- **목표:** 메모리 누수와 race condition 방지
- **파일:**
  - `frontend/src/hooks/useAsync.ts` (새 파일)

---

#### 8️⃣ 환경 설정 분리 (30분)
- **상태:** ❌ Not Started
- **목표:** 설정값을 중앙에서 관리
- **파일:**
  - `frontend/src/config/env.ts` (새 파일)

---

#### 9️⃣ 테스트 커버리지 추가 (3시간)
- **상태:** ❌ Not Started
- **목표:** 유닛 테스트 및 통합 테스트 작성
- **파일:**
  - `backend/tests/test_auth.py`
  - `backend/tests/test_subjects.py`
  - `backend/tests/test_tests.py`
  - `frontend/src/__tests__/hooks/useNavigation.test.ts`
  - `frontend/src/__tests__/lib/api.test.ts`

---

#### 🔟 문서화 개선 (2시간)
- **상태:** ❌ Not Started
- **목표:** 아키텍처 및 개발 가이드 문서화
- **파일:**
  - `ARCHITECTURE.md` (새 파일)
  - `CONTRIBUTING.md` (새 파일)
  - `API.md` (새 파일)

---

## 🎯 실행 순서

1. **완료:** ✅ Phase 1-1 (Navigation 훅 추출)
2. **완료:** ✅ Phase 1-2 (API 응답 표준화)
3. **완료:** ✅ Phase 1-3 (에러 바운더리)
4. **완료:** ✅ Phase 2-1 (Backend 응답 표준화)
5. **완료:** ✅ Phase 2-2 (권한 데코레이터)

---

## 📊 진행 상황

| 항목 | 상태 | 난이도 | 예상시간 | 실제시간 |
|------|------|--------|---------|----------|
| 1. Navigation 훅 | ✅ | 낮음 | 30분 | 25분 |
| 2. API 응답 표준화 (Frontend) | ✅ | 낮음 | 1시간 | 40분 |
| 3. 에러 바운더리 | ✅ | 낮음 | 30분 | 20분 |
| 4. Backend 응답 표준화 | ✅ | 중간 | 1시간 | 15분 |
| 5. 권한 데코레이터 | ✅ | 중간 | 1시간 | 20분 |

| 2. API 응답 표준화 | ❌ | 중간 | 1시간 | - |
| 3. 에러 바운더리 | ❌ | 낮음 | 30분 | - |
| 4. useFetch 훅 | ⏳ | 중간 | 1시간 | - |
| 5. Backend API 표준화 | ⏳ | 중간 | 1시간 | - |
| 6. 권한 데코레이터 | ⏳ | 중간 | 1시간 | - |
| 7. useAsync 훅 | ⏳ | 중간 | 1시간 | - |
| 8. 환경 설정 분리 | ⏳ | 낮음 | 30분 | - |
| 9. 테스트 추가 | ⏳ | 높음 | 3시간 | - |
| 10. 문서화 개선 | ⏳ | 중간 | 2시간 | - |

**범례:**
- ✅ 완료
- ❌ 미시작
- 🟡 진행중
- ⏳ 예정

---

## 📝 노트

- 각 작업을 완료할 때마다 이 파일의 상태를 업데이트할 것
- Phase 1을 완료하면 코드 품질과 유지보수성이 크게 개선될 것으로 예상
- 테스트 작성은 마지막에 진행 (우선 기능 완성 후)
