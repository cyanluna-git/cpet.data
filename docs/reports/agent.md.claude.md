# Agent Guide (CPET Platform)

이 문서는 에이전트가 프로젝트 구조와 최신 논의 사항을 빠르게 파악하기 위한 요약입니다.

## 핵심 문서
- README: 프로젝트 개요 및 실행 가이드
- ARCHITECTURE: 시스템 구조와 데이터 흐름
- doc/DATABASE_SCHEMA.md: DB 스키마 (정제 데이터셋 계획 포함)
- doc/METABOLISM_ANALYSIS_DESIGN.md: 대사 분석 알고리즘 및 정제 파이프라인 설계
- doc/DATA_PIPELINE_ROADMAP.md: 데이터 로드/재분석/정제 데이터셋 로드맵
- doc/api_plan.md: API 현황 및 계획 (정제 시리즈 엔드포인트 포함)

## 최근 변경 요약
- Raw Data Viewer에 차트 프리셋 버튼 추가: FATMAX, RER Curve, VO2 Kinetics, VT Analysis, Custom.
- Raw Data 차트는 X/Y 축 선택 기반 XY 플롯(ComposedChart + Scatter).
- Y축 선택 전에는 차트 렌더링 없이 안내 메시지 표시.
- 테스트 선택 방식: 피험자 → 해당 테스트 날짜 필터링.
- 테스트 목록 조회는 page_size 최대 100 제한.

## 차트/분석 파이프라인 계획
- Raw breath-by-breath 데이터는 그대로 보존.
- 차트 전용 정제 데이터셋(예: breath_data_processed)을 별도 생성:
  - Phase trimming (Rest/Warm-up/Recovery 제거)
  - Power binning (5–10W, median/trimmed mean)
  - Interpolation (PCHIP/Akima 또는 LOESS)
  - 테스트 유형 자동 태깅 (Ramp/Step/Mixed)

## 주요 파일 위치
- Frontend Raw Data Viewer: frontend/src/components/pages/RawDataViewerPage.tsx
- Backend 테스트 서비스: backend/app/services/test.py
- 분석 로직: backend/app/services/metabolism_analysis.py
- 테스트 API: backend/app/api/tests.py
- 스키마: backend/app/schemas/test.py

## 주의 사항
- /api/tests의 page_size는 최대 100 (초과 시 422).
- 대량 시딩은 메모리/커넥션 이슈 가능 (batch 처리 권장).
