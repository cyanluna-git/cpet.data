# Radix UI Select 빈 문자열 에러 수정

## 개요
SubjectListPage 편집 모달에서 SelectItem에 빈 문자열 값을 사용하여 발생한 에러를 수정했습니다. Radix UI Select 컴포넌트는 빈 문자열을 값으로 허용하지 않습니다.

## 주요 변경사항
- 수정한 것: SelectItem value를 `""` → `"none"`으로 변경
- 수정한 것: 폼 상태 초기화에서 빈 문자열 대신 `"none"` 사용
- 수정한 것: 저장 시 `"none"`을 `undefined`로 변환하여 API 전송

## 핵심 코드
```tsx
// 폼 상태 초기화
const [editForm, setEditForm] = useState({
  training_level: 'none',  // 빈 문자열 대신 'none'
  job_category: 'none',
  notes: '',
});

// 모달 열 때 값 변환
function openEditModal(subject: any) {
  setEditForm({
    training_level: subject.training_level || 'none',
    job_category: subject.job_category || 'none',
    notes: subject.notes || '',
  });
}

// 저장 시 'none'을 undefined로 변환
const trainingLevel = editForm.training_level === 'none' ? undefined : editForm.training_level;
const jobCategory = editForm.job_category === 'none' ? undefined : editForm.job_category;
```

## 결과
- ✅ 프론트엔드 빌드 성공
- ✅ Radix UI Select 에러 해결

## 다음 단계
- 편집 모달에서 훈련 수준, 직업 카테고리 변경 기능 테스트
- 선택 안함 → 값 선택 → 다시 선택 안함 플로우 테스트
