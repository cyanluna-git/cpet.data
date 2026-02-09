# 전처리 수행 버튼 기능 완성

## 개요
RawDataViewerPage에 추가된 "전처리 수행" 버튼의 미완성 로직을 완성했다. 설정 저장 후 전처리 데이터를 자동으로 리로드하여 결과를 즉시 확인할 수 있도록 개선했다.

## 주요 변경사항
- **수정한 것**: `handleSaveSettings`에 저장 후 데이터 리로드 로직 추가
  - Raw 모드에서 전처리 수행 시 자동으로 Smooth 모드로 전환
  - Smooth/Trend 모드에서는 현재 모드 유지하며 데이터 리로드
- **기존 버튼 UI**: 이미 추가되어 있던 전처리 수행 버튼 (isDirty 상태에 따라 스타일 변경)

## 핵심 코드
```typescript
// 저장 후 전처리 데이터 리로드 (결과 반영)
if (dataMode === 'raw') {
  setDataMode('smoothed'); // Raw → Smooth 자동 전환
} else {
  loadProcessedData(dataMode === 'trend' ? 'trend' : 'smoothed');
}
```

## 결과
- ✅ TypeScript 타입 체크 통과
- ✅ 프로덕션 빌드 성공

## 다음 단계
- 전처리 수행 중 로딩 상태 표시 개선 (버튼에 스피너 추가)
- Raw 모드의 Persistence Controls와 전처리 수행 버튼 간 UX 중복 정리
- 전처리 완료 후 분석 마커(FatMax, Crossover) 갱신 확인
