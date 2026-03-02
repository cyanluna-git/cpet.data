# 일반 유저 대시보드 UI 개선

## 개요
일반 유저(role: user/subject)가 내 대시보드와 메타볼리즘 페이지만 볼 수 있도록 네비게이션을 개선하고, 테스트 목록을 테이블 형식으로 변경했습니다. 또한 일반 유저의 403 에러 문제를 해결하고 메타볼리즘 차트를 FATMAX 스타일로 개선했습니다.

## 주요 변경사항

### 1. Navigation.tsx - 코호트 분석 숨김
- 코호트 분석 버튼을 `isResearcher` 조건으로 감싸서 일반 유저에게 숨김
- 일반 유저는 "내 대시보드", "메타볼리즘"만 표시

### 2. SubjectDashboard.tsx - 테스트 목록 테이블화
- 카드 형식 → 테이블 형식으로 변경 (날짜, 프로토콜, VO2MAX, HR MAX, 상태)
- 403 에러 수정: `api.getSubjects()` → `api.getTests()` 직접 호출
- 키보드 접근성 추가 (tabIndex, role="button", onKeyDown)

### 3. MetabolismPage.tsx - 일반 유저 권한 수정
- 일반 유저는 `/api/subjects` 건너뛰고 `/api/tests`로 본인 테스트 직접 로드
- key prop 경고 수정 (test.id → test.test_id || test.id)

### 4. MetabolismChart.tsx - FATMAX 스타일로 전면 개편
- Area 차트 → Line 차트
- kcal/day → g/min 단위 그대로 사용
- 이중 Y축: 왼쪽 g/min (Fat, CHO), 오른쪽 ml/min/kg (VO2/kg)
- 색상: Fat=빨강, CHO=녹색, VO2/kg=파랑

## 핵심 코드

```tsx
// Navigation.tsx - 코호트 분석 숨김
{isResearcher && (
  <Button onClick={() => onNavigate('cohort-analysis')}>
    코호트 분석
  </Button>
)}

// SubjectDashboard.tsx - 테이블 형식
<table>
  <thead>
    <tr>
      <th>날짜</th><th>프로토콜</th><th>VO2MAX</th><th>HR MAX</th><th>상태</th>
    </tr>
  </thead>
  <tbody>
    {tests.map(test => (
      <tr key={test.test_id || test.id} role="button" tabIndex={0}>
        ...
      </tr>
    ))}
  </tbody>
</table>
```

## 결과
- ✅ E2E 테스트 8개 모두 통과
- ✅ 일반 유저 403 에러 해결
- ✅ 메타볼리즘 차트 FATMAX 스타일 적용

## 다음 단계
- CohortAnalysisPage의 deprecated API (`getCohortStats`) 수정
- `/api/cohorts/summary` 404 에러 해결 (백엔드 엔드포인트 확인)
- 일반 유저 테스트 데이터 연결 확인 (woochan 사용자에게 테스트 연결)
