# 전처리 수행 버튼 UX 개선

## Overview
RawDataViewerPage에 "전처리 수행" 버튼이 추가된 이후, 기존 Persistence Controls(상태 뱃지 + 저장 버튼 + 리셋 버튼) 섹션과 기능이 중복되어 UI가 복잡해졌다. 이번 작업에서 버튼의 로딩 상태를 스피너+아이콘으로 명확히 표시하고, 중복 섹션을 제거하며, 리셋 기능을 컴팩트하게 통합했다.

## Context
- "전처리 수행" 버튼은 설정을 서버에 저장 + 전처리 데이터 리로드를 수행
- 기존에 별도로 존재하던 Persistence Controls 섹션(상태 뱃지 + 저장 + 리셋)이 동일한 `handleSaveSettings`/`handleResetSettings`를 호출하여 기능 중복
- 저장 중 상태가 텍스트만 "저장 중..."으로 변경되어 시각적 피드백이 부족

## Changes Made

### 1. 전처리 수행 버튼에 스피너 및 아이콘 추가
- `inline-flex items-center gap-1.5` 레이아웃으로 아이콘+텍스트 조합
- 저장 중: `Loader2` 스피너 (animate-spin) + "저장 중..."
- 변경됨 (isDirty): `Save` 아이콘 + "전처리 수행"
- 저장됨: `Check` 아이콘 + "저장됨"
- File: `frontend/src/components/pages/RawDataViewerPage.tsx`

### 2. 소형 리셋 버튼 추가
- 전처리 수행 버튼 바로 옆에 `RotateCcw` 아이콘만 있는 컴팩트 버튼
- `isServerPersisted`일 때만 표시 (저장된 설정이 있을 때만 리셋 의미 있음)
- 리셋 중에는 `Loader2` 스피너로 교체
- File: `frontend/src/components/pages/RawDataViewerPage.tsx`

### 3. Persistence Controls 섹션 전체 제거
- 기존: 상태 뱃지(저장 안됨/저장됨/기본값) + 저장 Button + 리셋 Button으로 구성된 별도 영역
- 제거 이유: 전처리 수행 버튼이 동일한 기능을 수행하므로 중복
- File: `frontend/src/components/pages/RawDataViewerPage.tsx`

### 4. 미사용 import 정리
- `AlertTriangle` import 제거 (Persistence Controls의 "저장 안됨" 뱃지에서만 사용됨)
- File: `frontend/src/components/pages/RawDataViewerPage.tsx`

## Code Examples

### 전처리 수행 버튼 (Before)
```tsx
// frontend/src/components/pages/RawDataViewerPage.tsx (Before)
<button
  type="button"
  onClick={handleSaveSettings}
  disabled={!selectedTestId || isSaving}
  className={`ml-2 px-3 py-1.5 text-sm font-medium rounded-md shadow-sm ...`}
>
  {isSaving ? '저장 중...' : isDirty ? '전처리 수행' : '저장됨'}
</button>
```

### 전처리 수행 버튼 (After)
```tsx
// frontend/src/components/pages/RawDataViewerPage.tsx (After)
<button
  type="button"
  onClick={handleSaveSettings}
  disabled={!selectedTestId || isSaving}
  className={`ml-2 px-3 py-1.5 text-sm font-medium rounded-md shadow-sm inline-flex items-center gap-1.5 ...`}
>
  {isSaving ? (
    <>
      <Loader2 className="w-3.5 h-3.5 animate-spin" />
      저장 중...
    </>
  ) : isDirty ? (
    <>
      <Save className="w-3.5 h-3.5" />
      전처리 수행
    </>
  ) : (
    <>
      <Check className="w-3.5 h-3.5" />
      저장됨
    </>
  )}
</button>

{/* 리셋 버튼 - 서버에 저장된 설정이 있을 때만 표시 */}
{selectedTestId && isServerPersisted && (
  <button
    type="button"
    onClick={handleResetSettings}
    disabled={isResetting}
    className="px-2 py-1.5 text-sm font-medium rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100 ..."
    title="기본 설정으로 리셋"
  >
    {isResetting ? (
      <Loader2 className="w-3.5 h-3.5 animate-spin" />
    ) : (
      <RotateCcw className="w-3.5 h-3.5" />
    )}
  </button>
)}
```

### UI 구조 변경 (Before vs After)
```
Before:
[Raw][Smooth][Trend] [전처리 수행(텍스트만)]
[파라미터 슬라이더들...]
[Analysis Window 슬라이더]
[상태뱃지 + 저장버튼 + 리셋버튼]  ← 중복 섹션

After:
[Raw][Smooth][Trend] [💾전처리 수행(아이콘+스피너)] [↺리셋]
[파라미터 슬라이더들...]
[Analysis Window 슬라이더]
                                                    ← 중복 제거됨
```

## Verification Results

### TypeScript Type Check
```bash
> npx tsc --noEmit
(no output - clean pass)
```

### Build Verification
```bash
> npm run build
dist/assets/RawDataViewerPage-Djq8dPbX.js  40.65 kB │ gzip: 11.40 kB
✓ built in 2.43s
```

### 분석 마커 갱신 확인
- `handleSaveSettings` → 저장 성공 후 `loadProcessedData` 호출
- `loadProcessedData` → `setAnalysisData(data)` 호출
- 차트에서 `analysisData?.metabolic_markers?.fat_max`, `analysisData?.metabolic_markers?.crossover` 참조
- 따라서 FatMax/Crossover 마커가 자동으로 갱신됨 (코드 변경 불필요)

## Next Steps
- 전처리 수행 후 toast 메시지에 변경된 마커 값(FatMax W, Crossover W) 함께 표시
- 버튼 상태에 따른 툴팁 개선 (현재 설정 vs 저장된 설정 차이점 상세 표시)
- 모바일 반응형에서 전처리 버튼 + 리셋 버튼 레이아웃 테스트
