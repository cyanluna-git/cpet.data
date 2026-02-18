# 📚 CPET Platform Documentation

프로젝트의 모든 문서를 중앙에서 관리합니다.

## 폴더 구조

```
docs/
├── README.md                   # 문서 개요 (이 파일)
├── DEPLOYMENT_GUIDE.md         # 배포 가이드
│
├── guides/                     # 개발 및 운영 가이드
│   ├── ARCHITECTURE.md         # 시스템 아키텍처 설명
│   ├── CONTRIBUTING.md         # 기여하는 방법
│   └── TESTING_STRATEGY.md     # 테스트 전략
│
└── reports/                    # 완료된 작업/개선 보고서
    ├── REFACTORING_REPORT.md   # 리팩토링 완료 보고서
    ├── RER_CURVE_BUG_FIX.md    # RER 곡선 버그 수정 기록
    ├── REVIEW.md               # 코드 리뷰 결과
    ├── FRONTEND_OPTIMIZATIONS.md # 프론트엔드 최적화 기록
    └── TESTING_COMPLETE.md     # 테스트 구현 완료 보고서
```

## 📖 문서 가이드

### 🎯 빠른 시작
- **[프로젝트 개요](../README.md)** - 프로젝트 소개 및 설치 방법
- **[배포 가이드](./DEPLOYMENT_GUIDE.md)** - 운영 환경 배포 방법

### 🏗️ 개발자 가이드
- **[아키텍처](./guides/ARCHITECTURE.md)** - 시스템 설계 및 구조
- **[기여 가이드](./guides/CONTRIBUTING.md)** - 개발 규칙 및 코드 스타일
- **[테스트 전략](./guides/TESTING_STRATEGY.md)** - 테스트 방법론 및 실행 방법

### 📊 작업 기록
- **[리팩토링](./reports/REFACTORING_REPORT.md)** - 코드 구조 개선 내용
- **[버그 수정](./reports/RER_CURVE_BUG_FIX.md)** - RER 곡선 표시 버그 해결
- **[성능 최적화](./reports/FRONTEND_OPTIMIZATIONS.md)** - 프론트엔드 성능 개선 기록
- **[테스트 구현](./reports/TESTING_COMPLETE.md)** - 테스트 프레임워크 추가
- **[코드 리뷰](./reports/REVIEW.md)** - 코드 품질 검토 결과

## 🔑 핵심 문서

### 새 팀원이 읽어야 할 것
1. [README](../README.md) - 5분 읽기
2. [ARCHITECTURE](./guides/ARCHITECTURE.md) - 15분 읽기
3. [CONTRIBUTING](./guides/CONTRIBUTING.md) - 10분 읽기

### 배포/운영 담당자
1. [DEPLOYMENT_GUIDE](./DEPLOYMENT_GUIDE.md) - 필수
2. [ARCHITECTURE](./guides/ARCHITECTURE.md) - 시스템 이해용

### 개발자 (추가 개선 시)
1. [TESTING_STRATEGY](./guides/TESTING_STRATEGY.md)
2. [보고서들](./reports/) - 이전 작업 이해용

## 📝 문서 관리 규칙

### 새 문서 작성 시
- **진행 중인 작업**: Root `TODOS.md` 또는 해당 폴더에 임시 문서
- **완료된 작업**: `docs/reports/` 폴더로 이동
- **운영 정보**: `docs/guides/` 폴더에 추가

### 오래된 문서
- 6개월 이상 업데이트 없는 문서는 `docs/reports/archived/`로 이동 고려
- 내용이 변경되면 최신 정보로 업데이트

## 🚀 활용 팁

### 빠른 검색
```bash
# 문서에서 키워드 검색
grep -r "keyword" docs/

# 특정 주제의 보고서 찾기
ls -lh docs/reports/ | grep "keyword"
```

### 문서 업데이트
```bash
# 가장 최근에 수정된 문서 확인
ls -lt docs/**/*.md | head -10
```

