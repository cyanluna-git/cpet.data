# CPET 대사 분석 플랫폼 UI/UX 디자인 요청서

## 프로젝트 개요
COSMED K5 장비의 호흡 가스 분석 데이터(CPET)를 자동 수집하여 피험자의 대사 프로파일(FATMAX, VO2MAX)을 분석하고 시각화하는 **웹 기반 SaaS 플랫폼**의 전체 UI/UX 디자인을 요청합니다.

### 플랫폼 성격
- **산업**: Healthcare/Sports Science
- **타겟**: 대학 연구실, 스포츠 과학 센터, 병원
- **디바이스**: Desktop-first (1920x1080 이상), Tablet 반응형 지원

---

## 사용자 페르소나

### 1. 관리자 (Admin/교수)
- **역할**: 전체 시스템 관리, 사용자 계정 생성, 데이터 감독
- **목표**: 연구 데이터 보안 관리, 시스템 모니터링
- **기술 수준**: 중상

### 2. 연구원 (Researcher)
- **역할**: 데이터 업로드, 코호트 분석, 통계 작업, 논문 작성용 데이터 추출
- **목표**: 효율적인 데이터 분석, 그룹 비교, 인사이트 도출
- **기술 수준**: 중
- **페인포인트**: 복잡한 Excel 작업, 수동 계산, 그래프 작성 시간 소요

### 3. 피험자 (Subject/선수/일반인)
- **역할**: 본인의 대사 프로파일 확인, 과거 기록 비교
- **목표**: 본인의 체력 수준 이해, 훈련 효과 확인
- **기술 수준**: 하~중
- **페인포인트**: 전문 용어 이해 어려움, 데이터 해석 필요

---

## 디자인해야 할 화면 (총 15개 화면)

### A. 인증 및 온보딩 (2 화면)
1. **로그인 페이지**
   - 이메일/비밀번호 입력
   - "비밀번호 찾기" 링크
   - Role 선택 없음 (자동 구분)
   - 깔끔하고 전문적인 디자인

2. **회원가입 페이지** (Admin만 사용, 초대 링크 기반)
   - 최소 정보 입력 (이름, 이메일, 비밀번호)
   - Role 선택 (Researcher/Subject)
   - Subject인 경우 → 피험자 정보 추가 입력 필요

---

### B. 관리자 대시보드 (3 화면)

3. **Admin Dashboard (메인)**
   - 상단: 전체 통계 카드
     - 총 피험자 수
     - 총 테스트 수 (이번 달)
     - 활성 연구원 수
     - 스토리지 사용량
   - 중간: 최근 활동 타임라인
   - 하단: 시스템 상태 (DB 연결, 배치 작업 상태)

4. **사용자 관리 페이지**
   - 좌측: 필터 사이드바 (Role, 활성 상태)
   - 메인: 사용자 테이블
     - 컬럼: 이름, 이메일, Role, 가입일, 마지막 로그인, 상태, 액션(편집/삭제)
   - 우측 상단: "+ 사용자 초대" 버튼 (모달 트리거)
   - 검색 기능

5. **시스템 설정 페이지**
   - 탭 네비게이션:
     - General (시스템 이름, 로고 업로드)
     - Security (비밀번호 정책, 세션 타임아웃)
     - Notifications (이메일 알림 설정)
     - Backup (자동 백업 스케줄)

---

### C. 연구원 워크플로우 (6 화면)

6. **Researcher Dashboard (메인)**
   - 상단: Welcome 메시지 + 빠른 액션 버튼
     - "새 테스트 업로드"
     - "코호트 분석"
   - 중간: 최근 업로드한 테스트 카드 리스트 (썸네일 + 요약)
   - 하단: "내가 관리하는 피험자" 섹션

7. **피험자 목록 페이지**
   - 좌측: 고급 필터 패널
     - 성별, 연령대, 병력 태그, 훈련 수준
     - 사용자 정의 태그 (다중 선택)
   - 메인: 피험자 카드/테이블 토글 뷰
     - 카드 뷰: 프로필 사진, 이름(익명 ID), 나이, 최근 테스트 날짜, VO2MAX
     - 테이블 뷰: 더 많은 컬럼 표시
   - 우측 상단: "+ 피험자 등록" 버튼, 엑셀 내보내기

8. **피험자 상세 페이지**
   - 상단: 피험자 프로필 헤더
     - 좌측: 프로필 정보 (Research ID, 나이, 성별, 신장, 체중, BMI)
     - 우측: 태그 (수정 가능), 메모 버튼
   - 중간: 탭 네비게이션
     - **Overview**: 주요 지표 타임라인 그래프 (VO2MAX, FATMAX 변화)
     - **Test History**: 테스트 목록 (날짜, 프로토콜, 주요 결과)
     - **Medical History**: 병력 정보
     - **Notes**: 연구 노트 (Markdown 지원)

9. **테스트 업로드 페이지**
   - Step 1: 파일 업로드 (Drag & Drop 또는 찾아보기)
     - 지원 형식 안내: COSMED K5 Excel (.xlsx)
     - 다중 파일 업로드 지원
   - Step 2: 피험자 매칭
     - 파일명에서 자동 감지된 이름 표시
     - 드롭다운으로 기존 피험자 선택 또는 "새 피험자 등록"
   - Step 3: 분석 옵션 설정
     - 계산 방법 선택 (Frayn/Jeukendrup)
     - Smoothing 윈도우 (10초/30초)
     - 자동 구간 감지 체크박스
   - Step 4: 업로드 진행률 표시 → 완료 후 테스트 상세 페이지로 이동

10. **Single Test View (단일 실험 분석)**
    - **핵심 화면! 가장 중요함**
    - 상단: 테스트 메타데이터
      - 좌측: 피험자 이름, 날짜, 프로토콜 타입
      - 우측: 주요 결과 카드 (VO2MAX, FATMAX, HR MAX)
    - 메인: 인터랙티브 차트 영역 (Recharts 스타일)
      - X축: 시간(Time) 또는 부하(Watt) 토글
      - Y축: Multi-axis 설정 패널
        - 왼쪽 Y축: HR, VO2, VCO2 (체크박스 선택)
        - 오른쪽 Y축: RER, Fat Oxidation (체크박스 선택)
      - 마커 표시: FATMAX(초록), VO2MAX(빨강), VT1/VT2(파랑)
      - 구간 하이라이트: Rest(회색), Warm-up(노랑), Exercise(투명), Recovery(회색)
      - 줌 컨트롤 (Zoom In/Out/Reset)
      - 툴팁: 데이터 포인트 hover 시 모든 값 표시
    - 하단: 구간별 요약 테이블
      - Rest, Warm-up, Exercise, Peak, Recovery 별 평균값
    - 우측 사이드바: 
      - "편집" 버튼 (마커 수동 조정 모드)
      - "비교 추가" 버튼 (다른 테스트 오버레이)
      - "리포트 다운로드" 버튼 (PDF)

11. **Longitudinal View (시계열 변화 추적)**
    - 상단: 피험자 선택 + 지표 선택
    - 메인: 시계열 라인 차트
      - X축: 날짜
      - Y축: 선택된 지표 (VO2MAX, FATMAX HR, HR MAX 등)
      - 다중 지표 오버레이 가능
    - Before & After 비교 모드 토글
      - 두 개의 테스트 선택 → 나란히 비교

---

### D. 코호트 분석 (1 화면)

12. **Cohort Analysis Dashboard**
    - 상단: 코호트 정의 패널
      - 필터 조합: 성별, 연령대, 훈련 수준, 병력 태그
      - "적용" 버튼 → 매칭되는 피험자 수 표시
    - 메인: 3개의 차트 영역
      - 차트 1: 박스 플롯 (Box Plot) - VO2MAX 분포
        - 개인 데이터 포인트 오버레이
        - 백분위 선 표시 (10%, 50%, 90%)
      - 차트 2: 바이올린 플롯 - FATMAX HR 분포
      - 차트 3: 산점도 (Scatter Plot) - VO2MAX vs FATMAX 상관관계
    - 하단: 통계 테이블
      - 평균, 중앙값, 표준편차, 최소/최대값
    - 우측 상단: "엑셀 다운로드", "통계 분석" 버튼

---

### E. 피험자 개인 대시보드 (2 화면)

13. **Subject Dashboard (메인)**
    - 상단: "내 대사 프로파일" 헤더
    - Hero 섹션: 최신 테스트 결과 카드
      - VO2MAX: 큰 숫자 + 백분위 표시 (예: "상위 25%")
      - FATMAX: 심박수 + 운동 강도
      - 코호트 평균 대비 비교 (작은 그래프)
    - 중간: "내 기록 변화" 섹션
      - 간단한 라인 차트 (최근 5개 테스트)
    - 하단: "다음 목표" 카드 (연구원이 설정한 목표)

14. **Subject Test History**
    - 테스트 목록 (날짜 역순)
    - 각 카드 클릭 시 → Simplified Test View (읽기 전용)
      - 전문 용어 최소화
      - 해석 텍스트 포함 (예: "당신의 지방 연소는 심박수 145에서 가장 높았습니다")

---

### F. 공통 컴포넌트

15. **네비게이션 및 레이아웃**
    - **Top Navigation Bar**
      - 좌측: 로고 + 플랫폼 이름
      - 중앙: 주요 메뉴 (Role별 다름)
        - Admin: Dashboard, Users, Settings
        - Researcher: Dashboard, Subjects, Tests, Cohort Analysis
        - Subject: Dashboard, My Tests
      - 우측: 검색, 알림, 프로필 드롭다운 (로그아웃)
    - **Side Navigation** (선택적, Researcher용)
      - 접고 펼치기 가능
      - 아이콘 + 텍스트

---

## 디자인 요구사항

### 1. 색상 팔레트
- **Primary Color**: 신뢰감과 전문성을 주는 색상 (예: Deep Blue #2563EB 또는 Teal #0D9488)
- **Secondary Color**: 액센트 (예: Orange #F97316 - 데이터 포인트 강조)
- **Success**: Green #10B981 (FATMAX 마커)
- **Danger**: Red #EF4444 (VO2MAX 마커)
- **Warning**: Yellow #F59E0B (VT1/VT2 마커)
- **Neutral**: Gray scale (#F9FAFB, #E5E7EB, #6B7280, #1F2937)
- **Background**: White #FFFFFF / Light Gray #F9FAFB

### 2. 타이포그래피
- **Font Family**: 
  - 영어: Inter, 'Segoe UI', 'Helvetica Neue' (모던하고 가독성 좋은 Sans-serif)
  - 한글: 'Pretendard', 'Noto Sans KR' (한글 지원)
- **Hierarchy**:
  - H1: 32px/Bold (페이지 제목)
  - H2: 24px/Semibold (섹션 제목)
  - H3: 18px/Semibold (카드 제목)
  - Body: 14px/Regular (일반 텍스트)
  - Caption: 12px/Regular (보조 텍스트)

### 3. 차트 스타일 (Recharts 기반)
- **라인 차트**: 부드러운 곡선 (Curve: monotone)
- **색상**: 각 지표별 일관된 색상
  - HR: Red #EF4444
  - VO2: Blue #3B82F6
  - VCO2: Green #10B981
  - RER: Purple #A855F7
  - Fat Oxidation: Orange #F97316
- **그리드**: 얇은 회색 점선
- **툴팁**: 반투명 배경, 그림자, 모든 지표 표시
- **레전드**: 체크박스로 on/off 가능

### 4. 카드 및 컨테이너
- **카드**: 흰색 배경, border-radius: 8px, 그림자: 0 1px 3px rgba(0,0,0,0.1)
- **호버 효과**: 그림자 증가 + 살짝 위로 이동
- **패딩**: 24px (일반), 16px (작은 카드)

### 5. 버튼
- **Primary Button**: Primary Color 배경, 흰색 텍스트, border-radius: 6px, 호버 시 어두워짐
- **Secondary Button**: 투명 배경, Primary Color 테두리, 호버 시 배경 색상
- **Danger Button**: Red 배경 (삭제 등)
- **크기**: 
  - Large: 48px height (중요 액션)
  - Medium: 40px height (일반)
  - Small: 32px height (보조 액션)

### 6. 폼 요소
- **Input Field**: 
  - border: 1px solid #D1D5DB
  - border-radius: 6px
  - padding: 12px
  - focus: border color → Primary Color, 그림자 추가
- **Label**: 14px/Semibold, 위쪽 배치
- **Error State**: 빨간 테두리 + 아래에 에러 메시지

### 7. 데이터 테이블
- **헤더**: 회색 배경 (#F9FAFB), Semibold
- **Row**: Hover 시 배경색 변경
- **Sorting**: 헤더 클릭 시 화살표 아이콘
- **Pagination**: 하단 중앙, 이전/다음 + 페이지 번호

### 8. 모달
- **배경**: 반투명 검정 오버레이 (rgba(0,0,0,0.5))
- **컨텐츠**: 중앙 정렬, 최대 너비 600px, 그림자
- **닫기**: X 버튼 (우측 상단) 또는 ESC 키

### 9. 반응형 디자인
- **Desktop (>1280px)**: 기본 레이아웃
- **Tablet (768px-1279px)**: 
  - 차트 영역 세로로 배치
  - 사이드바 접기
- **Mobile (<768px)**: 피험자 대시보드만 지원 (간소화)

---

## 인터랙션 및 애니메이션

### 1. 차트 인터랙션
- **Zoom**: 마우스 휠 또는 핀치 제스처
- **Pan**: 드래그하여 이동
- **Tooltip**: 마우스 호버 시 표시
- **Toggle**: 레전드 클릭 시 해당 라인 show/hide

### 2. 데이터 로딩
- **Skeleton Screen**: 차트 및 카드 로딩 시
- **Progress Bar**: 파일 업로드 시

### 3. 피드백
- **Toast Notification**: 우측 상단에서 슬라이드 인
  - 성공: Green 배경
  - 에러: Red 배경
  - 정보: Blue 배경
- **3초 후 자동 사라짐**

### 4. 트랜지션
- **페이지 전환**: 페이드 효과 (200ms)
- **모달**: Scale + Fade (300ms)
- **호버**: Smooth transition (150ms)

---

## 특수 요구사항

### 1. 접근성 (Accessibility)
- WCAG 2.1 AA 준수
- 키보드 네비게이션 지원
- 색각 이상자를 위한 패턴/아이콘 사용
- 스크린 리더 호환 (aria-label)

### 2. 데이터 시각화 원칙
- 과학적 정확성 유지 (축 라벨, 단위 명확히)
- 시각적 계층 구조 (중요한 지표 강조)
- 색상 일관성 (동일 지표는 항상 같은 색상)

### 3. 다국어 지원 (추후)
- 한국어/영어 토글 고려한 레이아웃
- 텍스트 길이 변화에 대응

### 4. 보안 및 개인정보
- 민감 정보 마스킹 표시 (예: 실명 대신 Research ID)
- 권한 없는 기능 숨김 처리

---

## 산출물 요청사항

### 1. Figma 파일 구조
```
📁 CPET Platform
  📄 Cover (프로젝트 설명)
  📁 00. Design System
    - Colors
    - Typography
    - Components (버튼, 카드, 입력 필드 등)
    - Icons
  📁 01. Admin Screens (3개)
  📁 02. Researcher Screens (6개)
  📁 03. Subject Screens (2개)
  📁 04. Auth Screens (2개)
  📁 05. Common Components (네비게이션, 모달 등)
  📁 06. Charts & Data Viz (차트 예시)
  📁 07. Mobile Views (선택적)
```

### 2. 컴포넌트 라이브러리
- 재사용 가능한 컴포넌트 생성
- Variants 활용 (버튼 상태: default, hover, active, disabled)
- Auto Layout 적용

### 3. 프로토타입
- 주요 사용자 플로우 연결
  - Researcher: 로그인 → 테스트 업로드 → Single Test View
  - Subject: 로그인 → Dashboard → Test History
- 인터랙션 애니메이션 적용

### 4. 개발자 Handoff
- CSS 코드 스니펫 준비
- 에셋 Export 설정 (SVG, PNG @1x, @2x)
- Spacing/Sizing 명확히 (8px 그리드 시스템)

---

## 참고 자료

### 유사 플랫폼 (영감)
- **데이터 대시보드**: Tableau, Grafana, Metabase
- **차트 인터랙션**: TradingView, Google Analytics
- **의료/과학 플랫폼**: EPIC MyChart, LabCorp Patient Portal

### 차트 라이브러리 (개발 시 사용할 것)
- Recharts (React 차트 라이브러리) - 디자인 참고

### 디자인 스타일
- Modern, Clean, Professional
- Flat Design with subtle depth (그림자, 호버 효과)
- 데이터 중심 (차트와 숫자가 주인공)

---

## 타임라인 및 우선순위

### Phase 1 (1주차) - 핵심 화면
1. Design System 구축
2. Single Test View (가장 중요!)
3. Researcher Dashboard
4. 피험자 목록 페이지

### Phase 2 (2주차) - 보조 화면
5. 테스트 업로드 페이지
6. Longitudinal View
7. Cohort Analysis Dashboard
8. 로그인/회원가입

### Phase 3 (3주차) - 나머지 및 프로토타입
9. Admin 화면 3개
10. Subject 화면 2개
11. 프로토타입 연결
12. 반응형 대응

---

## 질문 및 확인사항

디자인 진행 전 다음 사항을 확인해주세요:
1. 플랫폼 이름/로고가 있나요?
2. 선호하는 색상 팔레트가 있나요? (브랜드 컬러)
3. 차트 예시로 사용할 실제 데이터를 제공할 수 있나요?
4. 특정 참고하고 싶은 플랫폼이 있나요?
5. 모바일 앱 버전도 고려 중인가요?

---

**프롬프트 작성일**: 2026년 1월 9일  
**기반 문서**: SRS v1.1 (2026.01.07)  
**요청자**: CPET Platform 개발팀
