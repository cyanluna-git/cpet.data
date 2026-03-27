# Subject Metric Snapshots v2

> Date: 2026-03-28
>
> Status: active design draft
>
> Kanban: `#1886 Subject metric snapshots SQLite 스키마 설계 (v2)`

## 1. Purpose

`subject_metric_snapshots`는 CPET/INSCYD 제출 결과에서 추출한 핵심 metric을 연구용 2차 스냅샷 레이어로 축적하는 SQLite read model이다.

이 테이블의 목적은 화면용 카드 렌더링 자체가 아니라 다음 작업의 기반을 만드는 것이다.

- 반복 제출 집단의 longitudinal 분석
- 새 파생변수 개발
- clustering / cohort exploration
- 원본 submission/workspace와 분리된 재사용 가능한 분석 베이스 확보

현재 `main`의 profile trends 화면은 요청 시점에 `submission -> workspace -> analysis.db`를 직접 읽어 summary/compare/chart를 계산한다. 이 방식은 UI에는 충분하지만, 연구용 데이터셋을 안정적으로 축적하고 재사용하는 계층으로는 부족하다.

## 2. Decision Summary

### Final table name

`subject_metric_snapshots`

선정 이유:

- `athlete_metrics`보다 row grain이 명확하다.
- UI 컴포넌트명이 아니라 데이터 모델 이름이다.
- source-preserving snapshot layer라는 목적이 드러난다.

### Database

`data/cpet_platform.db`

이유:

- 현재 v2의 플랫폼 메타 DB가 이미 여기에 있다.
- `analysis.db`는 workspace 단위 artifact이고, cross-submission 연구 테이블은 플랫폼 DB에 두는 게 맞다.

### Row grain

`1 row = 1 subject x 1 source artifact x 1 measured_at`

초기에는 source를 합치지 않는다.

- CPET row와 INSCYD row를 자동 merge하지 않는다.
- 동일 subject, 유사 날짜라고 해서 하나의 row로 합치지 않는다.
- merge/derived/cohort row는 후속 단계로 미룬다.

### Initial source kinds

- `cpet_submission`
- `inscyd_report`

확장 reserved:

- `merged`
- `derived_feature_set`
- `manual_annotation`

## 3. Why This Layer Exists

원래 의도는 "metric을 보기 좋게 보여주는 프론트"보다 더 크다.

원본 계층:

- `submissions`
- workspace의 `analysis.db`
- INSCYD PDF/FIT 해석 결과

이 원본 계층은 분석 artifact로는 좋지만, 아래 작업에는 불편하다.

- subject별 전체 시점 조회
- source별 누락값 패턴 확인
- 재현 가능한 export
- 새 파생변수 추가 실험
- clustering 입력 테이블 준비

따라서 원본을 보존한 채, 연구용 snapshot read model을 따로 두는 것이 필요하다.

## 4. Scope

이번 설계의 범위:

- SQLite 테이블명 확정
- row grain 확정
- 필수 컬럼 / optional 컬럼 확정
- provenance 규칙 확정
- uniqueness / index 정책 확정
- source별 추출 계약의 입력/출력 요약

이번 설계의 비범위:

- backfill 구현
- refresh hook 구현
- explorer UI 구현
- cluster/percentile/derived feature 계산 구현
- 혈액 데이터 병합
- CPET/INSCYD 자동 merge row 생성

## 5. Proposed Schema

```sql
CREATE TABLE IF NOT EXISTS subject_metric_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(id),

    source_kind TEXT NOT NULL,
    source_ref_id TEXT NOT NULL,
    submission_id TEXT REFERENCES submissions(id),

    measured_at TEXT NOT NULL,
    measured_date TEXT GENERATED ALWAYS AS (substr(measured_at, 1, 10)) VIRTUAL,
    protocol_type TEXT,

    vo2max_ml REAL,
    vo2max_rel REAL,
    lt1_power_w REAL,
    lt2_power_w REAL,
    fatmax_power_w REAL,
    fatmax_gmin REAL,

    vlamax REAL,
    at_power_w REAL,
    carbmax_w REAL,
    glycogen_g REAL,

    extraction_version TEXT NOT NULL,
    quality_flags_json TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL DEFAULT '{}',

    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(subject_id, source_kind, source_ref_id)
);

CREATE INDEX IF NOT EXISTS idx_sms_subject_measured_at
ON subject_metric_snapshots(subject_id, measured_at DESC);

CREATE INDEX IF NOT EXISTS idx_sms_source_kind_measured_at
ON subject_metric_snapshots(source_kind, measured_at DESC);

CREATE INDEX IF NOT EXISTS idx_sms_submission_id
ON subject_metric_snapshots(submission_id);
```

## 6. Column Rules

### Identity

- `snapshot_id`
  application-generated UUID
- `subject_id`
  snapshot의 소유 subject
- `source_kind`
  `cpet_submission` 또는 `inscyd_report`
- `source_ref_id`
  source artifact의 고유 ID
  `cpet_submission`이면 `submissions.id`
  `inscyd_report`도 초기에는 workspace/submission 기반이면 `submissions.id`를 그대로 쓸 수 있다.
- `submission_id`
  플랫폼 DB와 연결할 수 있으면 채운다. source_ref_id와 같을 수 있다.

### Time

- `measured_at`
  분석 대상 검사의 측정 시점
  ISO 8601 string
- `measured_date`
  일 단위 필터를 단순화하기 위한 파생 컬럼

원칙:

- `created_at`은 snapshot row 생성 시각
- `measured_at`은 실제 검사/리포트 시각
- 둘을 혼동하지 않는다

### Stable metric columns

초기 flat column은 "여러 source에서 반복적으로 재사용될 가능성이 높은 값"만 둔다.

- `vo2max_ml`
- `vo2max_rel`
- `lt1_power_w`
- `lt2_power_w`
- `fatmax_power_w`
- `fatmax_gmin`
- `vlamax`
- `at_power_w`
- `carbmax_w`
- `glycogen_g`

원칙:

- 컬럼은 "연구용 기본축"만 둔다.
- source별 특수 세부값은 우선 `payload_json`에 넣는다.
- 아직 안정적으로 정의되지 않은 값은 flat column으로 승격하지 않는다.

### Provenance

- `extraction_version`
  어떤 추출 규칙 버전으로 snapshot이 만들어졌는지 저장
- `quality_flags_json`
  누락 source, parsing warning, confidence issue 같은 lightweight flag 리스트
- `payload_json`
  source별 확장 payload

`payload_json` 사용 원칙:

- raw BxB 전체를 넣지 않는다.
- snapshot row를 재현하거나 feature engineering에 다시 사용할 수 있는 "2차 추출 payload"만 넣는다.
- flat column과 동일한 값을 중복 저장해도 괜찮지만, payload가 canonical source가 되지는 않는다.

## 7. Uniqueness Policy

초기 unique key:

- `UNIQUE(subject_id, source_kind, source_ref_id)`

이유:

- source-preserving 전략과 맞는다.
- 같은 artifact를 여러 번 backfill/refresh해도 upsert 가능하다.
- 같은 날 여러 검사가 있어도 충돌하지 않는다.

의도적으로 하지 않는 것:

- `UNIQUE(subject_id, measured_at)`
- `UNIQUE(subject_id, measured_date)`

같은 날짜에 여러 artifact가 들어올 수 있기 때문이다.

## 8. Source Contracts

### CPET snapshot contract

입력:

- `submissions` row
- `workspace_path/analysis.db`
- 필요시 `subjects` metadata

최소 출력:

- `subject_id`
- `source_kind='cpet_submission'`
- `source_ref_id=submissions.id`
- `submission_id=submissions.id`
- `measured_at=test_session.test_date`
- `vo2max_ml`
- `vo2max_rel`
- `lt1_power_w`
- `lt2_power_w`
- `fatmax_power_w`
- `fatmax_gmin`
- `protocol_type`
- `quality_flags_json`
- `payload_json`

### INSCYD snapshot contract

입력:

- INSCYD workspace/report artifact
- 가능하면 `submissions` row

최소 출력:

- `subject_id`
- `source_kind='inscyd_report'`
- `source_ref_id=<stable inscyd artifact id>`
- `submission_id=<available when linked>`
- `measured_at=<report date or inferred test date>`
- `vo2max_ml` or `vo2max_rel` when available
- `fatmax_power_w` when available
- `vlamax`
- `at_power_w`
- `carbmax_w`
- `glycogen_g`
- `quality_flags_json`
- `payload_json`

## 9. Refresh Model

이 테이블은 원본을 대체하지 않는다. 재생성 가능한 read model이다.

따라서 후속 구현은 다음 원칙을 따라야 한다.

- backfill 가능해야 한다.
- 동일 source artifact 재처리 시 upsert 가능해야 한다.
- `extraction_version`이 바뀌면 row refresh가 가능해야 한다.
- 원본 `analysis.db`나 report artifact를 삭제하지 않는다.

## 10. Explorer UI Requirements

이 스키마를 바탕으로 만드는 첫 프론트는 "metric showcase"보다 "snapshot explorer"가 우선이다.

최초 UI 요구:

- snapshot table 목록
- subject/source/date filter
- row detail
- two-row compare
- export-ready view

즉 `profile trends`는 소비자 화면이고, `subject_metric_snapshots` UI는 연구자/운영자 검증 화면이다.

## 11. Deferred Items

다음은 초기 스키마에서 제외한다.

- blood markers
- body composition full flattening
- cohort percentile
- clustering label
- merged row
- derived feature row
- 100+ wide table

이 항목들은 snapshot layer가 안정화된 뒤 별도 카드로 분리한다.

## 12. Next Cards

이 설계 뒤에 이어져야 할 카드:

1. `CPET/INSCYD -> subject_metric_snapshots 추출 계약 구현 (v2)`
2. `subject_metric_snapshots backfill / refresh runner 구현 (v2)`
3. `subject_metric_snapshots explorer UI 구현 (v2)`
4. `derived feature experiment layer 설계 (v2)`

## 13. Summary

v2의 `subject_metric_snapshots`는 "모든 걸 담는 giant metrics table"이 아니다.

이 레이어의 책임은 명확하다.

- 원본 artifact를 보존한다
- 연구에 자주 쓰는 핵심 metric만 안정적으로 납작하게 만든다
- provenance와 payload를 남긴다
- longitudinal 분석과 후속 feature engineering의 기준 테이블이 된다

즉, 현재 HTMX profile 화면을 넘어서기 위한 첫 번째 데이터 계층이다.
