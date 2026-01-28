# Dashboard 개선 - 트렌드 차트 및 목표 설정

## 개요
SubjectDashboard (피험자 대시보드)에 트렌드 차트와 목표 설정 기능을 추가하여 사용자 경험을 개선했습니다.

## 주요 변경사항

### 1. 트렌드 미니 차트 추가
- 테스트가 2개 이상일 때 VO2 MAX와 FATMAX HR의 변화 추이 시각화
- Recharts LineChart 사용
- 듀얼 Y축 (왼쪽: VO2 MAX, 오른쪽: FATMAX HR)
- 반응형 디자인 (모바일: h-48, 데스크톱: h-64)

### 2. 목표 설정 기능
- localStorage 기반 목표 저장 (백엔드 API 없이 로컬에서 동작)
- 세 가지 목표 유형:
  - VO2 MAX 목표 (ml/kg/min)
  - FATMAX 심박수 목표 (bpm)
  - 월간 테스트 목표 (회)
- Progress bar로 진행률 시각화
- 목표 달성 시 축하 메시지 표시

### 핵심 코드
```tsx
// 목표 데이터 로컬 저장
const GOALS_STORAGE_KEY = 'cpet_user_goals';
const [goals, setGoals] = useState<Goal>(() => {
  const saved = localStorage.getItem(GOALS_STORAGE_KEY);
  return saved ? JSON.parse(saved) : { vo2MaxTarget: null, ... };
});
```

## 결과
- 빌드 정상 완료
- 131개 테스트 모두 통과
- SubjectDashboard 파일 크기: 9.41KB → 19.79KB (기능 추가로 인한 증가)

## 다음 단계
- 백엔드 API로 목표 데이터 영구 저장 구현
- ResearcherDashboard에도 유사한 트렌드 분석 추가
- 목표 달성 알림 기능
