# MetabolismPage 무한 API 호출 버그 수정

## 개요
피험자를 선택했을 때 화면이 심하게 깜빡이며 동일한 API가 수십 번 반복 호출되는 버그를 수정했습니다. useEffect 의존성 배열의 잘못된 설정이 원인이었습니다.

## 주요 변경사항
- 수정한 것: `loadTests` useEffect의 의존성 배열에서 `tests.length` 제거
- 개선한 것: subject role 체크를 useEffect 최상단으로 이동하여 불필요한 로직 실행 방지
- 수정한 것: 테스트 자동 선택 로직 제거 (lazy loading 정책 일관성)

## 핵심 코드
```typescript
// 변경 전 - 무한 루프 발생
}, [selectedSubjectId, showCohortAverage, user.role, tests.length]);

// 변경 후 - 안정적인 동작
}, [selectedSubjectId, showCohortAverage, user.role]);
```

**버그 원인 분석:**
1. 피험자 선택 → `selectedSubjectId` 변경 → useEffect 실행
2. `setTests([])` 호출 → `tests.length = 0`
3. API 호출 후 `setTests(items)` → `tests.length` 변경
4. `tests.length` 변경이 의존성 배열에 있어서 → useEffect 재실행 → 무한 루프!

## 결과
- 빌드 성공
- 피험자 선택 시 API 호출 1회로 정상화

## 다음 단계
- 변경사항 커밋 및 테스트 검증
- subject role 사용자의 테스트 선택 UI 개선 검토 (현재 컨트롤 패널이 숨겨져 있음)
