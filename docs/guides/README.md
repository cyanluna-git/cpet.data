# 📖 개발 및 운영 가이드

프로젝트 개발에 필요한 모든 가이드를 모았습니다.

## 문서 목록

### 🏗️ [ARCHITECTURE.md](./ARCHITECTURE.md)
**시스템 아키텍처 설명서**
- 백엔드/프론트엔드 구조
- 데이터베이스 설계
- API 설계 패턴
- 의존성 관계

**읽는 대상**: 모든 개발자
**읽는 시간**: 15-20분

---

### 🤝 [CONTRIBUTING.md](./CONTRIBUTING.md)
**기여하는 방법 가이드**
- 개발 환경 설정
- 브랜치 전략
- 코드 스타일 규칙
- PR 작성 방법
- 테스트 작성 규칙

**읽는 대상**: 신규 개발자, PR 작성자
**읽는 시간**: 10-15분

---

### 🧪 [TESTING_STRATEGY.md](./TESTING_STRATEGY.md)
**테스트 전략 및 실행 가이드**
- 테스트 구조 (Unit, Integration, E2E)
- 백엔드 테스트 (pytest)
- 프론트엔드 테스트 (Vitest)
- 테스트 실행 방법
- 커버리지 기준

**읽는 대상**: 테스트 작성자, QA
**읽는 시간**: 15-20분

---

## 빠른 시작

### 신규 개발자
```bash
# 1. 프로젝트 설정
cd cpet.db
./dev.sh

# 2. 문서 읽기 (순서대로)
# - ARCHITECTURE.md
# - CONTRIBUTING.md
# - TESTING_STRATEGY.md

# 3. 첫 PR 작성
# CONTRIBUTING.md의 PR 가이드 참고
```

### 배포 담당자
1. `DEPLOYMENT_GUIDE.md` 읽기
2. `ARCHITECTURE.md`의 인프라 섹션 읽기

## 자주 묻는 질문

**Q: 어디서 코딩 규칙을 찾나요?**
A: `CONTRIBUTING.md`의 "코드 스타일" 섹션 참고
또는 `.claude/rules/` 폴더의 상세 규칙 참고

**Q: 테스트는 어떻게 작성하나요?**
A: `TESTING_STRATEGY.md` 참고
예제: `backend/tests/`, `frontend/src/__tests__/`

**Q: 시스템 구조를 알고 싶어요**
A: `ARCHITECTURE.md` 읽기 (다이어그램 포함)

