# 모바일 반응형 최적화

## 개요
CPET Platform의 전체 프론트엔드에 모바일 최적화를 적용했습니다. 네비게이션 햄버거 메뉴, 반응형 그리드, 차트 크기 조절, 타이포그래피 스케일링 등을 구현하여 375px~768px 모바일 화면에서 최적의 사용자 경험을 제공합니다.

## 주요 변경사항

### 1. 네비게이션 모바일 메뉴 (Critical)
- **파일**: `Navigation.tsx`
- 햄버거 메뉴 + Sheet drawer 구현
- 데스크톱: `hidden md:flex` / 모바일: `flex md:hidden`
- SheetClose로 메뉴 클릭 시 자동 닫힘

### 2. RawDataViewerPage Select 너비 수정 (Critical)
- `min-w-[300px]` → `w-full sm:w-auto sm:min-w-[200px] md:min-w-[280px]`
- 375px 화면에서 select가 화면을 초과하는 문제 해결

### 3. 페이지 컨테이너 패딩 (8개 파일)
- `px-6 py-8` → `px-4 md:px-6 py-6 md:py-8`
- 모바일에서 좌우 패딩 24px → 16px로 콘텐츠 영역 확보

### 4. Grid 레이아웃 반응형
- `grid-cols-3` → `grid-cols-1 sm:grid-cols-3`
- 통계 카드, 분석 결과 등 모바일에서 1열로 스택

### 5. 차트 반응형 (CSS-First)
- **파일**: `MetabolismChart.tsx`
- `h-[280px] sm:h-[350px] md:h-[400px]` wrapper 추가
- `useIsMobile` 훅으로 동적 마진 적용

### 6. 타이포그래피 스케일링
- 페이지 제목: `text-2xl md:text-3xl`
- 통계 숫자: `text-xl sm:text-2xl md:text-3xl`

## 핵심 코드

```tsx
// Navigation.tsx - 모바일 메뉴
<div className="flex md:hidden items-center gap-2">
  <Sheet open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
    <Button variant="ghost" size="icon" onClick={() => setMobileMenuOpen(true)}>
      <Menu className="h-5 w-5" />
    </Button>
    <SheetContent side="left" className="w-72 p-0">
      {/* 세로 네비게이션 메뉴 */}
    </SheetContent>
  </Sheet>
</div>
```

```tsx
// MetabolismChart.tsx - CSS-First 차트 반응형
<div className="h-[280px] sm:h-[350px] md:h-[400px] w-full">
  <ResponsiveContainer width="100%" height="100%">
    <ComposedChart margin={isMobile ? mobileMargins : desktopMargins}>
```

## 수정된 파일 목록
- `Navigation.tsx` - 모바일 메뉴
- `RawDataViewerPage.tsx` - Select 너비
- `MetabolismChart.tsx` - 차트 반응형
- `SubjectDashboard.tsx`
- `ResearcherDashboard.tsx`
- `SubjectListPage.tsx`
- `SubjectDetailPage.tsx`
- `AdminDashboardPage.tsx`
- `AdminDataPage.tsx`
- `AdminUsersPage.tsx`
- `CohortAnalysisPage.tsx`
- `MetabolismPage.tsx`

## 결과
- ✅ 빌드 성공 (vite build)
- ✅ Gemini 코드 리뷰 통과
- ✅ TypeScript 에러 없음

## 다음 단계
- [ ] 실제 모바일 기기에서 테스트 (iPhone SE 375px)
- [ ] 터치 타겟 크기 검증 (44px 이상)
- [ ] 테이블 컴포넌트 수평 스크롤 UX 개선
- [ ] 모바일 전용 폼 입력 최적화 (더 큰 입력 필드)
