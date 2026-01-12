# CPET 대사 분석 플랫폼

## 프로젝트 개요
COSMED K5 장비의 호흡 가스 분석 데이터(CPET)를 자동 수집하여 피험자의 대사 프로파일(FATMAX, VO2MAX)을 분석하고 시각화하는 **웹 기반 SaaS 플랫폼**입니다.

### 주요 기능

#### 🔐 인증 및 권한 관리
- 역할 기반 접근 제어 (Admin, Researcher, Subject)
- Supabase Auth 기반 보안 인증
- 자동 세션 관리

#### 👨‍🔬 연구원 대시보드
- **대시보드**: 전체 통계 현황, 최근 테스트 카드, 피험자 요약
- **피험자 관리**: 검색, 필터링, 상세 정보 조회
- **테스트 분석**: 인터랙티브 차트로 실시간 데이터 시각화
- **코호트 분석**: 그룹별 통계 비교, 산점도 분석

#### 📊 Single Test View (핵심 화면)
- **인터랙티브 차트**:
  - X축: 시간(Time) 또는 부하(Watt) 전환 가능
  - Y축: Multi-axis (HR, VO2, VCO2, RER, Fat Oxidation 등)
  - 체크박스로 라인 표시/숨김 토글
  - 구간별 배경색 (Rest, Warmup, Exercise, Recovery)
  - 마커 표시: FATMAX(초록), VO2MAX(빨강), VT1/VT2(파랑)
- **요약 카드**: VO2 MAX, HR MAX, FATMAX, MFO 핵심 지표
- **구간별 요약 테이블**: Phase별 평균값 분석

#### 🧑‍⚕️ 피험자 대시보드
- **내 대사 프로파일**: 최신 검사 결과 시각화
- **코호트 비교**: 동일 연령대/성별 대비 백분위 표시
- **검사 기록**: 과거 테스트 이력 조회
- **결과 해석**: 일반인도 이해할 수 있는 설명 제공

#### 📈 코호트 분석
- **필터**: 성별, 연령대별 그룹 선택
- **통계**: 평균, 중앙값, 백분위(10%, 25%, 75%, 90%)
- **시각화**: VO2 MAX vs FATMAX HR 산점도
- **데이터 내보내기**: Excel/CSV 다운로드 (예정)

## 기술 스택

### Frontend
- **React 18** + TypeScript
- **Tailwind CSS v4** - 모던 디자인 시스템
- **Recharts** - 인터랙티브 차트 라이브러리
- **Shadcn/ui** - 고품질 UI 컴포넌트
- **Sonner** - Toast 알림

### Backend
- **Supabase**:
  - Auth: 사용자 인증 및 권한 관리
  - Functions: Hono 기반 서버 (Deno)
  - KV Store: 피험자, 테스트 데이터 저장
- **API**: RESTful 아키텍처

### 디자인 시스템
- **Primary Color**: Deep Blue (#2563EB) - 신뢰감과 전문성
- **Secondary Color**: Orange (#F97316) - 데이터 강조
- **Chart Colors**:
  - HR (심박수): Red #EF4444
  - VO2: Blue #3B82F6
  - VCO2: Green #10B981
  - RER: Purple #A855F7
  - Fat Oxidation: Orange #F97316
- **Typography**: Pretendard (한글) + Inter (영문)

## 화면 구성

### 1. 로그인 페이지
- 이메일/비밀번호 인증
- 데모 계정 안내

### 2. 연구원 대시보드 (Researcher Dashboard)
- 통계 카드 (총 피험자, 전체 테스트, 이번 달 테스트)
- 빠른 액션 (테스트 업로드, 피험자 관리)
- 최근 테스트 카드 리스트
- 관리 중인 피험자 섹션

### 3. 피험자 목록 (Subject List)
- 검색 및 필터링
- 카드 형식 피험자 리스트
- 통계 요약 (전체/남성/여성/평균 연령)

### 4. 피험자 상세 (Subject Detail)
- 프로필 정보
- 주요 지표 변화 추이 (타임라인 차트)
- 검사 기록 이력
- 탭 네비게이션 (Overview, Test History, Notes)

### 5. Single Test View ⭐ (가장 중요)
- 메타데이터 헤더
- 주요 결과 카드 (VO2 MAX, HR MAX, FATMAX, MFO)
- 인터랙티브 차트 (Recharts)
  - X축 전환 (시간/부하)
  - 다중 Y축
  - 라인 토글 (체크박스)
  - 마커 표시 (FATMAX, VO2MAX, VT1, VT2)
  - 구간 배경색
- 구간별 요약 테이블
- 줌 컨트롤 (예정)

### 6. 피험자 대시보드 (Subject Dashboard)
- 최신 검사 결과 Hero 섹션
- 코호트 비교 백분위
- 결과 해석 (일반인용 설명)
- 검사 기록

### 7. 코호트 분석 (Cohort Analysis)
- 필터 패널 (성별, 연령대)
- VO2 MAX 분포 통계
- FATMAX HR 분포 통계
- 산점도 (Scatter Plot)

## 데이터 구조

### Subject (피험자)
```typescript
{
  id: string
  research_id: string  // "SUB-2024-057"
  name: string (암호화)
  birth_year: number
  gender: "M" | "F"
  height_cm: number
  weight_kg: number
  training_level: "Beginner" | "Intermediate" | "Advanced" | "Elite"
  created_at: timestamp
}
```

### Test (검사)
```typescript
{
  id: string
  subject_id: string
  test_date: timestamp
  protocol_type: "BxB" | "MIX"
  protocol_name: string
  
  metadata: {
    age, gender, height_cm, weight_kg,
    test_type, test_duration, barometric_pressure, etc.
  }
  
  phases: {
    rest_end_sec, warmup_end_sec, exercise_end_sec,
    peak_sec, recovery_start_sec, total_duration_sec
  }
  
  summary: {
    vo2_max, vo2_max_rel, hr_max, fat_max_hr,
    fat_max_watt, mfo, vt1_hr, vt2_hr, rer_max,
    data_quality_score
  }
  
  timeseries: [
    { time_sec, phase, hr, vo2, vco2, rer,
      bike_power, fat_oxidation, cho_oxidation, ... }
  ]
  
  markers: {
    fatmax: { time_sec, hr, vo2, watt, rer, ... }
    vo2max: { time_sec, hr, vo2, watt, rer, ... }
    vt1: { time_sec, hr, vo2, watt, ... }
    vt2: { time_sec, hr, vo2, watt, ... }
  }
}
```

## API 엔드포인트

### 인증
- `POST /auth/signup` - 회원가입 (Admin만)
- `GET /auth/me` - 현재 사용자 정보

### 피험자
- `GET /subjects` - 피험자 목록
- `GET /subjects/:id` - 피험자 상세 (테스트 포함)
- `POST /subjects` - 피험자 등록

### 테스트
- `GET /tests` - 테스트 목록
- `GET /tests/:id` - 테스트 상세
- `POST /tests` - 테스트 생성
- `PUT /tests/:id` - 테스트 수정
- `DELETE /tests/:id` - 테스트 삭제

### 코호트 분석
- `POST /cohort/stats` - 코호트 통계 (필터링 가능)

## 샘플 데이터

첫 로그인 시 자동으로 샘플 데이터가 생성됩니다:
- 3명의 샘플 피험자
- 1개의 샘플 CPET 테스트 (박용두, BxB 프로토콜)

### 데모 계정
```
연구원: researcher@cpet.com / password123
피험자: subject@cpet.com / password123
```

## 주요 특징

### 1. 한글 지원
- Pretendard 폰트 적용
- 모든 UI 한국어 라벨

### 2. 데이터 시각화
- Recharts 기반 고성능 차트
- 반응형 디자인
- 인터랙티브 툴팁
- 다중 축 지원

### 3. 사용자 경험
- 직관적인 네비게이션
- 빠른 로딩 (Skeleton UI)
- Toast 알림 (성공/오류)
- 반응형 레이아웃

### 4. 보안
- Supabase Auth 기반 인증
- Role-based Access Control (RBAC)
- 개인정보 마스킹 (research_id)
- Session 자동 관리

## 향후 개발 계획

### Phase 1 (현재)
- ✅ 기본 인증 시스템
- ✅ 연구원/피험자 대시보드
- ✅ Single Test View (인터랙티브 차트)
- ✅ 피험자 관리
- ✅ 코호트 분석

### Phase 2 (예정)
- [ ] COSMED K5 Excel 파일 업로드
- [ ] 자동 구간 감지 (Phase Detection)
- [ ] FATMAX/VO2MAX 자동 계산
- [ ] Before & After 비교 모드
- [ ] PDF 리포트 다운로드

### Phase 3 (예정)
- [ ] Admin 대시보드
- [ ] 사용자 관리 페이지
- [ ] 시스템 설정
- [ ] 엑셀 데이터 내보내기
- [ ] 통계 분석 도구 (T-test, ANOVA)

### Phase 4 (예정)
- [ ] 모바일 앱 지원
- [ ] 다국어 (영어)
- [ ] 실시간 데이터 동기화
- [ ] 고급 차트 기능 (Zoom, Pan)

## 개발 가이드

### 프로젝트 구조
```
/src
  /app
    /components
      - LoginPage.tsx
      - Navigation.tsx
      - ResearcherDashboard.tsx
      - SubjectDashboard.tsx
      - SingleTestView.tsx ⭐
      - SubjectListPage.tsx
      - SubjectDetailPage.tsx
      - CohortAnalysisPage.tsx
      /ui (Shadcn 컴포넌트)
    /utils
      - api.ts (API 클라이언트)
      - sampleData.ts (샘플 데이터)
    - App.tsx (메인 라우터)
  /styles
    - theme.css (디자인 토큰)
    - fonts.css (Pretendard)
/supabase
  /functions
    /server
      - index.tsx (Hono 서버)
      - kv_store.tsx (데이터 스토어)
```

### 주요 디자인 토큰
```css
--primary: #2563EB (Deep Blue)
--secondary: #F97316 (Orange)
--success: #10B981 (Green)
--warning: #F59E0B (Yellow)
--destructive: #EF4444 (Red)

/* Chart Colors */
--chart-hr: #EF4444 (Red)
--chart-vo2: #3B82F6 (Blue)
--chart-vco2: #10B981 (Green)
--chart-rer: #A855F7 (Purple)
--chart-fat: #F97316 (Orange)
```

## 라이선스
MIT License

## 작성자
CPET Platform 개발팀  
작성일: 2026년 1월 9일  
버전: 1.0.0
