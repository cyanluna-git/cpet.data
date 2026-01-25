# 피험자 체성분 정보 필드 추가

## 개요
피험자 정보에 InBody 체성분 데이터(체지방률, 골격근량, BMI)를 저장할 수 있도록 필드를 추가했습니다.

## 주요 변경사항
- 추가한 것: `body_fat_percent` (체지방률, %)
- 추가한 것: `skeletal_muscle_mass` (골격근량, kg)
- 추가한 것: `bmi` (Body Mass Index)
- 수정한 것: 백엔드 Subject 모델 및 스키마
- 수정한 것: 프론트엔드 Subject 인터페이스
- 수정한 것: 편집 모달에 체성분 입력 필드 추가

## DB 마이그레이션
```sql
ALTER TABLE subjects ADD COLUMN IF NOT EXISTS body_fat_percent FLOAT;
ALTER TABLE subjects ADD COLUMN IF NOT EXISTS skeletal_muscle_mass FLOAT;
ALTER TABLE subjects ADD COLUMN IF NOT EXISTS bmi FLOAT;
```

## 편집 모달 UI
```
┌─────────────────────────────────────────────┐
│ 성별        │ 출생연도                       │
├─────────────────────────────────────────────┤
│ 키 (cm)     │ 체중 (kg)                     │
├─────────────────────────────────────────────┤
│ 체지방률(%) │ 골격근량(kg) │ BMI            │  ← NEW
├─────────────────────────────────────────────┤
│ 훈련 수준                                   │
│ 직업 카테고리                               │
│ 메모                                        │
└─────────────────────────────────────────────┘
```

## 결과
- ✅ DB 마이그레이션 완료
- ✅ 백엔드 스키마 업데이트 완료
- ✅ 프론트엔드 빌드 성공

## 다음 단계
- 백엔드 서버 재시작 (스키마 변경 반영)
- InBody 데이터 입력 테스트
