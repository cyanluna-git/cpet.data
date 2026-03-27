# Derived Feature Experiment Layer v2

> Date: 2026-03-28
>
> Status: active design draft
>
> Kanban: `#1899 derived feature experiment layer 설계 (v2)`

## 1. Purpose

`subject_metric_snapshots` 위에 연구용 파생변수 계층을 하나 더 둔다.

이 계층의 목적은 다음과 같다.

- 반복 제출 집단의 longitudinal feature engineering
- 새 변수 후보 실험과 버전 관리
- clustering / segmentation 입력 테이블 생성
- snapshot layer와 downstream experiment 결과를 분리

핵심은 "원본 metric snapshot"과 "실험용 feature row"를 같은 테이블에 섞지 않는 것이다.

## 2. Layer Model

v2의 연구 데이터 계층은 아래 3단으로 나눈다.

1. `subject_metric_snapshots`
   source-preserving snapshot layer
   `1 row = 1 subject x 1 source artifact x 1 measured_at`

2. `subject_feature_sets`
   experiment-ready derived feature layer
   `1 row = 1 subject x 1 anchor snapshot/window x 1 feature spec version`

3. `cluster_runs`
   clustering/segmentation 결과 layer
   `1 row = 1 feature set row x 1 clustering run`

이번 카드의 직접 범위는 2단 설계다.

## 3. Why Another Layer Is Needed

`subject_metric_snapshots`만으로도 export와 비교는 가능하지만, 아래 요구를 직접 수용하기에는 경계가 맞지 않는다.

- 동일 subject의 시점간 변화율 계산
- CPET / INSCYD 혼합 feature 생성
- 최근 2회, 최근 90일 같은 window feature 계산
- 실험별 feature set 비교
- clustering 입력용 matrix 재생성

이 계산을 snapshot table에 직접 적재하면 원본 snapshot의 의미가 오염된다.

따라서 derived feature는 별도 read model로 분리해야 한다.

## 4. Design Principles

### Source-preserving first

- snapshot layer는 원본 metric 추출 결과만 저장한다.
- derived layer에서만 rate-of-change, ratios, rolling stats를 계산한다.

### Spec-versioned features

- 파생변수는 항상 `feature_spec_key + feature_spec_version`으로 식별한다.
- 같은 subject, 같은 anchor snapshot이라도 spec 버전이 다르면 별도 row다.

### Rebuildable, not hand-edited

- feature rows는 언제든 snapshot layer에서 재생성 가능해야 한다.
- 사용자가 수동 수정하는 canonical table로 쓰지 않는다.

### Payload-first for experiments

- 초기에는 100개 이상의 flat feature column을 만들지 않는다.
- stable identifier / provenance / selection key만 컬럼으로 두고 feature 값은 JSON payload에 둔다.

### Frontend is for validation

- 첫 UI 목적은 예쁜 분석 대시보드가 아니라 feature row 검증이다.
- 어떤 snapshot들이 입력됐고 어떤 spec으로 계산됐는지 보여줘야 한다.

## 5. Proposed Tables

### 5.1 `subject_feature_sets`

```sql
CREATE TABLE IF NOT EXISTS subject_feature_sets (
    feature_row_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL REFERENCES subjects(id),

    feature_spec_key TEXT NOT NULL,
    feature_spec_version TEXT NOT NULL,

    anchor_snapshot_id TEXT REFERENCES subject_metric_snapshots(snapshot_id),
    anchor_measured_at TEXT NOT NULL,
    window_label TEXT,

    input_snapshot_ids_json TEXT NOT NULL DEFAULT '[]',
    input_source_kinds_json TEXT NOT NULL DEFAULT '[]',

    feature_payload_json TEXT NOT NULL DEFAULT '{}',
    quality_flags_json TEXT NOT NULL DEFAULT '[]',

    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(subject_id, feature_spec_key, feature_spec_version, anchor_snapshot_id, window_label)
);

CREATE INDEX IF NOT EXISTS idx_sfs_subject_anchor
ON subject_feature_sets(subject_id, anchor_measured_at DESC);

CREATE INDEX IF NOT EXISTS idx_sfs_spec
ON subject_feature_sets(feature_spec_key, feature_spec_version, anchor_measured_at DESC);
```

### 5.2 `cluster_runs`

```sql
CREATE TABLE IF NOT EXISTS cluster_runs (
    cluster_run_id TEXT PRIMARY KEY,
    feature_spec_key TEXT NOT NULL,
    feature_spec_version TEXT NOT NULL,
    algorithm_key TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    run_params_json TEXT NOT NULL DEFAULT '{}',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 5.3 `cluster_memberships`

```sql
CREATE TABLE IF NOT EXISTS cluster_memberships (
    cluster_run_id TEXT NOT NULL REFERENCES cluster_runs(cluster_run_id),
    feature_row_id TEXT NOT NULL REFERENCES subject_feature_sets(feature_row_id),
    cluster_label TEXT NOT NULL,
    score REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (cluster_run_id, feature_row_id)
);
```

`cluster_runs`와 `cluster_memberships`는 후속 구현 대상이고, 이번 설계에서는 reserved 상태다.

## 6. Row Grain

`subject_feature_sets`의 grain:

`1 row = 1 subject x 1 anchor snapshot/window x 1 feature spec version`

예시:

- `subject A`, `anchor=2026-03-20 cpet snapshot`, `spec=endurance_core`, `v1`
- `subject A`, `anchor=2026-03-20 cpet snapshot`, `spec=endurance_core`, `v2`
- `subject A`, `anchor=2026-03-20 cpet snapshot`, `spec=longitudinal_delta`, `v1`

즉 파생변수의 정체성은 subject만이 아니라 "어떤 spec으로 계산됐는가"까지 포함한다.

## 7. Feature Spec Contract

각 feature spec은 아래 계약을 가진다.

- `feature_spec_key`
  예: `endurance_core`, `substrate_balance`, `longitudinal_delta_90d`

- `feature_spec_version`
  예: `v1`, `v2`

- `input rule`
  어떤 snapshot source와 몇 개의 시점이 필요한지

- `output schema`
  payload JSON 안에 어떤 key들이 들어가는지

- `quality rule`
  누락 source, 시간 간격 부족, metric missing을 어떤 flag로 남기는지

## 8. Recommended Initial Specs

처음부터 clustering 알고리즘보다, feature spec 몇 개를 안정화하는 게 우선이다.

### `endurance_core_v1`

입력:

- 단일 anchor snapshot

출력 후보:

- `vo2max_rel`
- `lt1_power_w`
- `lt2_power_w`
- `fatmax_power_w`
- `vlamax`
- `at_power_w`
- `source_kind`

용도:

- 단일 시점 feature matrix
- subject 간 baseline clustering

### `longitudinal_delta_v1`

입력:

- 동일 subject의 최근 2개 snapshot

출력 후보:

- `days_since_previous`
- `delta_vo2max_rel`
- `delta_lt1_power_w`
- `delta_fatmax_power_w`
- `delta_vlamax`
- `pct_delta_vo2max_rel`
- `pct_delta_lt1_power_w`

용도:

- 변화량 기반 grouping
- training response 실험

### `snapshot_window_v1`

입력:

- 동일 subject의 최근 N일 / 최근 N개 snapshot

출력 후보:

- `snapshot_count_90d`
- `mean_vo2max_rel_90d`
- `max_lt2_power_w_90d`
- `latest_minus_mean_vo2max_rel_90d`

용도:

- longitudinal smoothing
- 불안정한 단일 시점 노이즈 완화

## 9. Payload Shape

초기 `feature_payload_json` 예시는 아래처럼 둔다.

```json
{
  "spec": {
    "key": "longitudinal_delta",
    "version": "v1"
  },
  "inputs": {
    "anchor_snapshot_id": "sms_current",
    "comparison_snapshot_id": "sms_previous",
    "days_between": 48
  },
  "features": {
    "delta_vo2max_rel": 3.5,
    "pct_delta_vo2max_rel": 6.12,
    "delta_fatmax_power_w": 15.0
  }
}
```

원칙:

- top-level에 `spec`, `inputs`, `features`를 분리한다.
- feature key는 가능한 ASCII snake_case로 유지한다.
- clustering 입력은 `features` object만 추출하면 되게 만든다.

## 10. Quality Flags

`quality_flags_json`는 아래 같은 경고를 담는다.

- `missing_previous_snapshot`
- `insufficient_window_size`
- `mixed_source_compare`
- `missing_vlamax`
- `days_between_too_large`
- `anchor_snapshot_missing_metric`

이 flag는 실험용 row를 버리기 위한 것이 아니라, downstream filtering 기준을 제공하기 위한 것이다.

## 11. Non-goals

이번 설계에서 하지 않는 것:

- derived feature를 `subject_metric_snapshots`에 직접 컬럼 추가
- 모든 feature를 wide fixed schema로 확정
- ML model training metadata까지 한 번에 포함
- notebook output을 canonical DB row로 저장
- cohort percentile / ranking engine 동시 설계

## 12. UI Direction

후속 UI는 `snapshot explorer`와 동일하게 검증용 탐색기를 먼저 만든다.

우선순위:

1. feature row list
2. spec / version / subject filter
3. row detail payload
4. input snapshot trace
5. CSV / JSON export

즉 첫 화면은 "cluster result 시각화"보다 "어떤 feature row가 어떻게 계산됐는지 검증"이 먼저다.

## 13. Execution Plan

권장 후속 카드는 아래 순서다.

1. `subject_feature_sets SQLite 스키마 설계/구현`
2. `endurance_core_v1 feature builder`
3. `longitudinal_delta_v1 feature builder`
4. `feature set backfill / refresh runner`
5. `feature explorer UI`
6. `cluster run metadata layer`

## 14. Decision

v2에서 파생변수 계층은 "snapshot table에 컬럼을 계속 붙이는 방식"으로 가지 않는다.

대신 아래 방향으로 고정한다.

- `subject_metric_snapshots`
  source-preserving canonical snapshot layer

- `subject_feature_sets`
  spec-versioned derived feature layer

- `cluster_runs` / `cluster_memberships`
  downstream experiment result layer

이렇게 해야 snapshot의 의미를 보존하면서도, feature engineering과 clustering을 반복 실험 가능한 형태로 관리할 수 있다.
