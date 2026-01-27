# 메타볼리즘 페이지 테스트 업로드 기능 추가

## 개요
일반 유저(subject role)가 메타볼리즘 분석 페이지에서 직접 자신의 CPET 테스트 엑셀 파일을 업로드할 수 있도록 기능을 추가했습니다. 기존의 TestUploadModal 컴포넌트를 재사용하여 구현했습니다.

## 주요 변경사항
- **추가**: 메타볼리즘 페이지에 "테스트 업로드" 버튼 추가
- **추가**: 테스트가 없을 때 안내 메시지 표시
- **개선**: 테스트 로딩 로직을 재사용 가능한 함수로 분리
- **추가**: 업로드 성공 시 테스트 목록 자동 새로고침

## 핵심 코드

```tsx
// MetabolismPage.tsx
// 업로드 버튼 UI
<Button
  onClick={() => setShowUploadModal(true)}
  className="gap-2 bg-[#2563EB] hover:bg-[#1d4ed8]"
>
  <Upload className="w-4 h-4" />
  테스트 업로드
</Button>

// 업로드 성공 핸들러
const handleUploadSuccess = useCallback(async () => {
  setShowUploadModal(false);
  toast.success('테스트 데이터가 업로드되었습니다');
  await loadSubjectTests(); // 테스트 목록 새로고침
}, [loadSubjectTests]);
```

## 수정된 파일
- `frontend/src/components/pages/MetabolismPage.tsx`

## 결과
- ✅ 빌드 성공
- ✅ 기존 TestUploadModal 재사용
- ✅ 업로드 후 자동 새로고침

## 다음 단계
- [ ] 업로드 진행 상태 표시 개선
- [ ] 드래그 앤 드롭 힌트 추가
- [ ] 업로드 실패 시 에러 메시지 개선
