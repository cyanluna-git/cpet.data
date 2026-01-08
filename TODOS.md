# CPET Platform 개발 TODO 리스트

## 현재 상태
**Phase**: Phase 2 - Analysis Engine (시작)
**마지막 업데이트**: 2026-01-08
**전체 진행률**: 45%

---

## Phase 1: Core Infrastructure (진행 중)

### 완료 ✅
- [x] 프로젝트 스켈레톤 구조 생성
- [x] FastAPI 프로젝트 세팅 및 구조 설계
- [x] PostgreSQL + TimescaleDB Docker Compose 설정
- [x] 데이터베이스 스키마 설계 및 SQL 스크립트 작성
- [x] Frontend React + TypeScript + Vite 초기화
- [x] 기본 설정 파일 (.env.example, .gitignore)
- [x] Git 저장소 초기화 및 GitHub 푸시
- [x] 기본 문서 작성 (README.md, SRS)

### 완료된 추가 작업 ✅
- [x] 데이터베이스 모델 구현 (SQLAlchemy)
  - [x] Subject 모델
  - [x] CPETTest 모델
  - [x] BreathData 모델
  - [x] User 모델
  - [x] CohortStats 모델
- [x] Config 설정 개선 (ALLOWED_ORIGINS 파싱)

### 진행 중 🚧
- [x] JWT 기반 인증 시스템
  - [x] 로그인/회원가입 API
  - [x] 토큰 발급 및 검증
  - [x] 비밀번호 해싱 (bcrypt)
  - [x] 사용자 관리 API (관리자)

### 대기 중 ⏳
- [ ] Alembic 마이그레이션 설정
- [ ] 기본 API 테스트 작성

---

## Phase 2: Analysis Engine (진행 중)

### 데이터 수집 및 처리 ✅
- [x] COSMED K5 Excel 파일 파서 개발
  - [x] Excel 파일 구조 감지 (BxB vs MIX)
  - [x] 메타데이터 추출 (피험자 정보, 테스트 정보, 환경 조건)
  - [x] 시계열 데이터 파싱 (67-74개 컬럼 지원)
  - [x] 데이터 검증 (생리학적 범위 체크)
  - [x] 결측치 처리 및 경고
  - [x] 에러 핸들링
  - [x] 대사 지표 계산 (Frayn/Jeukendrup 공식)
  - [x] FATMAX/VO2MAX 자동 감지

### 구간 자동 감지
- [ ] Bike Power 기반 구간 감지 알고리즘
  - [ ] Rest 구간 감지
  - [ ] Warm-up 구간 감지
  - [ ] Exercise 구간 감지
  - [ ] Peak 구간 감지
  - [ ] Recovery 구간 감지
  - [ ] Moving Average 스무딩
  - [ ] HR/RER 보조 지표 활용

### 대사 지표 계산
- [ ] RER 계산 (VCO2/VO2)
- [ ] Frayn 공식 구현
  - [ ] 지방 연소율 계산
  - [ ] 탄수화물 연소율 계산
- [ ] Jeukendrup 공식 구현 (옵션)
- [ ] FATMAX 자동 감지
- [ ] VO2MAX 자동 감지
- [ ] VT1/VT2 감지 (옵션)
- [ ] 데이터 품질 스코어링

---

## Phase 3: API Development (예정)

### 인증 관련 API
- [ ] POST /api/auth/login
- [ ] POST /api/auth/logout
- [ ] POST /api/auth/refresh
- [ ] GET /api/auth/me

### 피험자 관리 API
- [ ] GET /api/subjects (목록, 필터링)
- [ ] POST /api/subjects (등록)
- [ ] GET /api/subjects/{id}
- [ ] PUT /api/subjects/{id}
- [ ] DELETE /api/subjects/{id}

### 테스트 관리 API
- [ ] GET /api/tests (목록)
- [ ] POST /api/tests/upload (파일 업로드)
- [ ] GET /api/tests/{test_id}
- [ ] GET /api/tests/{test_id}/raw-data
- [ ] GET /api/tests/{test_id}/metrics
- [ ] PUT /api/tests/{test_id}
- [ ] DELETE /api/tests/{test_id}

### 분석 및 시각화 API
- [ ] GET /api/tests/{test_id}/chart-data
- [ ] GET /api/subjects/{id}/comparison
- [ ] GET /api/subjects/{id}/percentile

### 통계 및 코호트 API
- [ ] GET /api/cohort/stats
- [ ] POST /api/cohort/filter
- [ ] POST /api/cohort/export

### API 문서화
- [ ] OpenAPI/Swagger 설정
- [ ] API 사용 예시 작성
- [ ] 에러 코드 정의

---

## Phase 4: Frontend Development (예정)

### 기본 구조
- [ ] React Router 설정
- [ ] 레이아웃 컴포넌트
- [ ] 네비게이션 메뉴
- [ ] API 서비스 레이어 (Axios)

### 인증 및 권한 관리
- [ ] 로그인 페이지
- [ ] 회원가입 페이지
- [ ] 권한별 라우트 가드
- [ ] 토큰 관리 (LocalStorage/SessionStorage)

### 대시보드
- [ ] 관리자 대시보드
- [ ] 피험자 대시보드
- [ ] 통계 카드 컴포넌트
- [ ] 최근 테스트 목록

### 피험자 관리
- [ ] 피험자 목록 페이지
- [ ] 피험자 등록/수정 폼
- [ ] 피험자 상세 페이지
- [ ] 메타데이터 태깅 UI

### 테스트 관리
- [ ] 테스트 업로드 페이지
- [ ] 파일 드래그 앤 드롭
- [ ] 업로드 진행률 표시
- [ ] 파싱 결과 미리보기

### 데이터 시각화
- [ ] Single Test View
  - [ ] 시계열 차트 (Recharts)
  - [ ] Multi-axis 지원
  - [ ] Zoom In/Out
  - [ ] 마커 추가/제거
  - [ ] 툴팁 표시
- [ ] Longitudinal View
  - [ ] 날짜별 비교 차트
  - [ ] Before & After 모드
- [ ] Cohort View
  - [ ] 그룹별 평균/백분위 차트
  - [ ] 개인 데이터 오버레이

### 반응형 디자인
- [ ] 모바일 최적화
- [ ] 태블릿 레이아웃
- [ ] 다크 모드 (옵션)

---

## Phase 5: Advanced Features (예정)

### 코호트 분석
- [ ] 배치 작업 스케줄러 설정
- [ ] 코호트 통계 자동 계산
- [ ] 백분위 계산 로직
- [ ] 통계 분석 도구
  - [ ] T-test
  - [ ] ANOVA
  - [ ] 상관관계 분석
  - [ ] 회귀 분석

### 데이터 내보내기
- [ ] Excel 내보내기
- [ ] CSV 내보내기
- [ ] 익명화 옵션
- [ ] 필터링된 코호트 일괄 다운로드

### 사용자 정의 기능
- [ ] 태그 시스템
- [ ] 사용자 정의 필터
- [ ] 저장된 뷰
- [ ] 즐겨찾기

---

## Phase 6: Security & Optimization (예정)

### 보안
- [ ] 데이터 암호화 구현
  - [ ] PII 데이터 암호화 (encrypted_name)
  - [ ] 암호화 키 관리
- [ ] RBAC 강화
  - [ ] Role 기반 접근 제어
  - [ ] Permission 체크
- [ ] API Rate Limiting
- [ ] CORS 설정 강화
- [ ] SQL Injection 방지
- [ ] XSS 방지
- [ ] 보안 감사 및 취약점 점검

### 성능 최적화
- [ ] 데이터베이스 쿼리 최적화
  - [ ] 인덱스 튜닝
  - [ ] N+1 쿼리 해결
- [ ] TimescaleDB 압축 설정
- [ ] Redis 캐싱 도입
  - [ ] 통계 데이터 캐싱
  - [ ] API 응답 캐싱
- [ ] 비동기 처리 (Celery)
  - [ ] 파일 업로드 백그라운드 처리
  - [ ] 통계 계산 백그라운드 처리
- [ ] Frontend 최적화
  - [ ] Code Splitting
  - [ ] Lazy Loading
  - [ ] 이미지 최적화

---

## Phase 7: Deployment & Testing (예정)

### 테스트
- [ ] 단위 테스트 (pytest)
  - [ ] 모델 테스트
  - [ ] 서비스 로직 테스트
  - [ ] API 엔드포인트 테스트
- [ ] 통합 테스트
- [ ] E2E 테스트 (Playwright/Cypress)
- [ ] 부하 테스트 (Locust)
- [ ] 테스트 커버리지 80% 이상

### 배포
- [ ] Dockerfile 작성
  - [ ] Backend Dockerfile
  - [ ] Frontend Dockerfile
- [ ] Docker Compose 프로덕션 설정
- [ ] AWS 인프라 구축
  - [ ] ECS/Elastic Beanstalk 설정
  - [ ] RDS for PostgreSQL
  - [ ] S3 for File Storage
  - [ ] CloudFront for CDN
- [ ] CI/CD 파이프라인
  - [ ] GitHub Actions 설정
  - [ ] 자동 테스트
  - [ ] 자동 배포
- [ ] 모니터링
  - [ ] AWS CloudWatch
  - [ ] Sentry (에러 트래킹)
  - [ ] 로깅 시스템

### 문서화
- [ ] 사용자 매뉴얼
- [ ] 관리자 가이드
- [ ] API 문서 완성
- [ ] 배포 가이드
- [ ] 트러블슈팅 가이드

---

## 우선순위별 작업 목록

### 🔴 High Priority (즉시 진행)
1. SQLAlchemy 모델 구현
2. COSMED K5 파일 파서 개발
3. 기본 인증 API 구현
4. 테스트 업로드 API 구현

### 🟡 Medium Priority (다음 단계)
1. 구간 자동 감지 알고리즘
2. FATMAX/VO2MAX 계산
3. 차트 시각화 컴포넌트
4. 피험자 관리 UI

### 🟢 Low Priority (향후 계획)
1. 코호트 분석 배치 작업
2. 다크 모드
3. 다국어 지원
4. 모바일 앱

---

## 기술적 부채 및 개선 사항

### 코드 품질
- [ ] Type hints 추가 (Python)
- [ ] ESLint/Prettier 설정 (TypeScript)
- [ ] 코드 리뷰 프로세스 확립
- [ ] 주석 및 Docstring 작성

### 리팩토링 필요
- [ ] Config 관리 개선
- [ ] 에러 핸들링 표준화
- [ ] 로깅 표준화
- [ ] 공통 유틸리티 함수 정리

### 문서화
- [ ] 함수별 Docstring
- [ ] 아키텍처 다이어그램
- [ ] 데이터 흐름 다이어그램
- [ ] ERD 다이어그램

---

## 참고 사항

### 알려진 이슈
- 없음

### 의존성 업데이트 필요
- 정기적으로 패키지 버전 확인 및 업데이트

### 성능 목표
- API 응답 시간: 95% 요청 < 500ms
- 대용량 데이터 처리: 10,000+ 데이터 포인트/테스트 지원
- 동시 사용자: 최소 100명 지원

---

**Last Updated**: 2026-01-07
**Next Review**: 매주 일요일
