# 피험자 목록 생년월/신체정보 표시 개선

## 개요
피험자 목록 테이블에서 "나이" 컬럼을 "생년월"로 변경하고, 테스트 데이터에서 누락된 신체 정보를 자동으로 채웠습니다.

## 주요 변경사항
- 수정한 것: "나이" → "생년월" 컬럼명 변경
- 수정한 것: 나이 표시(`35세`) → 생년월 표시(`1990.01` 또는 `1990`)
- 수정한 것: DB에서 테스트 데이터 기반으로 피험자 신체정보 업데이트

## 핵심 코드
```tsx
// 생년월 포맷 함수
function formatBirthYearMonth(birthYear: number | null, birthDate: string | null): string | null {
  if (birthDate) {
    const date = new Date(birthDate);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    return `${year}.${month}`;
  }
  if (birthYear) {
    return `${birthYear}`;
  }
  return null;
}
```

```sql
-- 테스트 데이터에서 피험자 신체정보 업데이트
UPDATE subjects s
SET weight_kg = t.weight_kg
FROM (SELECT DISTINCT ON (subject_id) subject_id, weight_kg
      FROM cpet_tests WHERE weight_kg IS NOT NULL
      ORDER BY subject_id, test_date DESC) t
WHERE s.id = t.subject_id AND s.weight_kg IS NULL;
```

## 결과
- ✅ 프론트엔드 빌드 성공
- ✅ 12개 피험자 체중 데이터 업데이트
- ✅ 4개 피험자 생년 데이터 추가

## 다음 단계
- SUB-* 피험자들의 키, 성별 정보는 원본 Excel에 없어서 수동 입력 필요
- 피험자 등록 모달에서 신체정보 입력 기능 추가
