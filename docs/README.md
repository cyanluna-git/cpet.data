# CPET Platform Documentation

`main` 브랜치 기준 문서 인덱스입니다. 현재 활성 코드베이스는 SQLite 중심 v2 아키텍처를 기준으로 정리합니다.

## Start Here

- [README.md](../README.md): 현재 코드베이스와 실행 방법
- [specs/REBUILD_PLAN.md](./specs/REBUILD_PLAN.md): v2 목표 구조와 설계 의도
- [specs/SUBJECT_METRIC_SNAPSHOTS_V2.md](./specs/SUBJECT_METRIC_SNAPSHOTS_V2.md): 연구용 2차 snapshot layer 설계
- [specs/DERIVED_FEATURE_EXPERIMENT_LAYER_V2.md](./specs/DERIVED_FEATURE_EXPERIMENT_LAYER_V2.md): snapshot 위 파생 feature / clustering 실험 계층 설계
- [specs/DATA_VALIDATION_SERVICE.md](./specs/DATA_VALIDATION_SERVICE.md): 검증 서비스 설계
- [specs/DATA_VALIDATOR_QUICKREF.md](./specs/DATA_VALIDATOR_QUICKREF.md): 검증 규칙 빠른 참조
- [specs/USER_ACCOUNTS.md](./specs/USER_ACCOUNTS.md): 사용자/온보딩 흐름
- [../deploy/README.md](../deploy/README.md): 배포 운영 메모
- [../scripts/README.md](../scripts/README.md): 운영 스크립트와 보조 유틸

## Notes

- `docs/reports/`는 과거 작업 기록 보관소입니다. 일부 문서는 레거시 스택을 설명할 수 있습니다.
- `docs/guides/`는 v2 기준으로 재구성 중입니다.
- [guides/TWO_BLOCK_CPET_FUEL_SPLIT.md](./guides/TWO_BLOCK_CPET_FUEL_SPLIT.md): 2블럭 CPET의 RQ 1.0 이전 연료 기여율 계산 기준과 Changmo 케이스 정리
- [guides/TWO_BLOCK_CPET_FUEL_SPLIT_DETAIL.html](./guides/TWO_BLOCK_CPET_FUEL_SPLIT_DETAIL.html): 2블럭 CPET 연료 기여율 계산의 상세 HTML 가이드
- [guides/THREE_PATH_ENERGY_SYSTEM_DETAIL.html](./guides/THREE_PATH_ENERGY_SYSTEM_DETAIL.html): 3-path 에너지 시스템 기여도 계산 방식과 코드 기준 공식 정리
- [guides/CPET_METFLEX_LANDSCAPE_REVIEW.html](./guides/CPET_METFLEX_LANDSCAPE_REVIEW.html): CPET-derived metabolic flexibility metric 논문의 문헌·특허 지형과 ZeLIA 적용 함의를 정리한 내부 HTML 리뷰
- [guides/CYCLING_VO2_RNN_REVIEW.html](./guides/CYCLING_VO2_RNN_REVIEW.html): Cycling VO2 RNN pilot study를 읽고 ZeLIA의 VO2 surrogate 연구 방향을 정리한 내부 HTML 리뷰
- [papers/CPET_LACTATE_AI_MASTERS_THESIS_TOPICS.md](./papers/CPET_LACTATE_AI_MASTERS_THESIS_TOPICS.md): CPET + lactate + AI 기반 석사 논문 주제 후보 4개를 연구문제, 가설, 데이터, 분석방법, 한계 기준으로 정리한 초안
- [guides/LACTATE_SURROGATE_RESEARCH_BRIEF.html](./guides/LACTATE_SURROGATE_RESEARCH_BRIEF.html): 젖산 surrogate model 주제를 별도 연구 페이지로 분리해 연구 framing과 Gemini Deep Research 프롬프트를 정리한 노트
- [papers/LACTATE_SURROGATE_RESEARCH_BRIEF.md](./papers/LACTATE_SURROGATE_RESEARCH_BRIEF.md): 위 노트의 원문 마크다운
- [guides/CPET_LACTATE_SURROGATE_STRATEGY.html](./guides/CPET_LACTATE_SURROGATE_STRATEGY.html): Gemini Deep Research가 작성한 CPET 기반 혈중 젖산 대리 모델링 연구 전략 전문
- 신규 활성 설계 문서는 가능하면 `docs/specs/`에 추가합니다.
