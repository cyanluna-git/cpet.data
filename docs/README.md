# CPET Platform Documentation

프로젝트의 모든 문서를 중앙에서 관리합니다.

## 폴더 구조

```
docs/
├── README.md                      # 문서 개요 (이 파일)
├── DEPLOYMENT_GUIDE.md            # 배포 가이드
│
├── specs/                         # 기술 사양 및 설계 문서
│   ├── srs.md                     # 시스템 요구사항 명세 (SRS)
│   ├── DATABASE_SCHEMA.md         # DB 스키마 설계
│   ├── METABOLISM_ANALYSIS_DESIGN.md  # 대사 분석 설계
│   ├── DATA_VALIDATION_SERVICE.md # 데이터 검증 서비스
│   ├── DATA_VALIDATOR_QUICKREF.md # 검증기 빠른 참조
│   ├── DATA_PIPELINE_ROADMAP.md   # 데이터 파이프라인 로드맵
│   ├── api_plan.md                # API 설계 계획
│   ├── USER_ACCOUNTS.md           # 사용자 계정 명세
│   ├── figma-design-prompt.md     # Figma 디자인 프롬프트
│   ├── preprocessing_Test.md      # 전처리 테스트 명세
│   ├── preprocessing_diagram.md   # 전처리 다이어그램
│   ├── processed-metabolism-persistence.md  # 대사 데이터 영속성
│   └── assets/                    # 다이어그램, JSON 샘플
│
├── guides/                        # 개발 및 운영 가이드
│   ├── ARCHITECTURE.md            # 시스템 아키텍처
│   ├── CONTRIBUTING.md            # 기여 가이드 및 코드 스타일
│   └── TESTING_STRATEGY.md        # 테스트 전략
│
└── reports/                       # 완료 작업 보고서
    ├── REFACTORING_REPORT.md      # 리팩토링 보고서
    ├── RER_CURVE_BUG_FIX.md       # 버그 수정 기록
    ├── REVIEW.md                  # 코드 리뷰 결과
    ├── FRONTEND_OPTIMIZATIONS.md  # 프론트엔드 최적화
    └── TESTING_COMPLETE.md        # 테스트 구현 완료
```

## 빠른 시작

| 대상 | 읽을 문서 |
|------|-----------|
| 새 팀원 | [README](../README.md) → [ARCHITECTURE](./guides/ARCHITECTURE.md) → [CONTRIBUTING](./guides/CONTRIBUTING.md) |
| 배포/운영 | [DEPLOYMENT_GUIDE](./DEPLOYMENT_GUIDE.md) |
| 기능 설계 | [specs/](./specs/) 폴더 |
| 이전 작업 파악 | [reports/](./reports/) 폴더 |

## 개발자 가이드

- **[아키텍처](./guides/ARCHITECTURE.md)** — 시스템 구조 및 서비스 간 관계
- **[기여 가이드](./guides/CONTRIBUTING.md)** — 개발 규칙, 커밋 컨벤션, PR 절차
- **[테스트 전략](./guides/TESTING_STRATEGY.md)** — pytest / Vitest / E2E 전략

## 기술 사양 (specs/)

- **[SRS](./specs/srs.md)** — 전체 요구사항 명세
- **[DB 스키마](./specs/DATABASE_SCHEMA.md)** — PostgreSQL + TimescaleDB 설계
- **[대사 분석 설계](./specs/METABOLISM_ANALYSIS_DESIGN.md)** — FATMAX / VO2MAX 알고리즘
- **[API 계획](./specs/api_plan.md)** — REST API 엔드포인트 설계
- **[데이터 파이프라인](./specs/DATA_PIPELINE_ROADMAP.md)** — 처리 흐름 로드맵

## 문서 관리 규칙

- **신규 기술 사양** → `docs/specs/`
- **개발/운영 가이드** → `docs/guides/`
- **완료된 작업 기록** → `docs/reports/`
- **세션 구현 로그** → `workthrough/` (오래된 것은 `workthrough/archive/`)
