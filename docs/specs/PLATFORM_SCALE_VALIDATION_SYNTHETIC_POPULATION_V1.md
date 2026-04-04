# Platform Scale Validation Synthetic Population v1

> Date: 2026-04-04
>
> Status: active design draft
>
> Kanban: `#2174 Design synthetic demo population model for platform validation`

## 1. Purpose

이 문서는 현재 데이터가 적은 상태에서도 CPET 플랫폼이 미래의 운영 밀도를 잘 감당할 수 있는지 검증하기 위한 synthetic demo population 설계를 정의한다.

핵심 목적은 `생리학적 정답 데이터셋`을 만드는 것이 아니라, 다음 제품 질문에 답할 수 있는 `플랫폼 검증용 가상 운영 환경`을 만드는 것이다.

- 대시보드가 dense cohort에서도 읽히는가
- 리포트 grouping / filtering / duplicate UX가 실제 운영 볼륨에서도 버티는가
- `subject_metric_snapshots`와 `subject_feature_sets`가 분석용 그릇으로 충분한가
- repeated measures / mixed-source / partial data / duplicate candidate가 함께 쌓여도 운영자가 감당 가능한가
- 앞으로 데이터가 계속 쌓였을 때 지금의 explorer / report / manage 화면이 어떤 모습이 되는지 미리 볼 수 있는가

이 설계는 논문용 통계 분석 설계보다 먼저, `플랫폼 완성형 시뮬레이션`을 만드는 데 초점을 둔다.

## 2. Decision Summary

### Validation strategy

`synthetic-first, hybrid-later`

실행 순서:

1. synthetic demo population으로 플랫폼 밀도 검증
2. 소수 real golden corpus로 parser/report realism 잠금
3. seeded QA / E2E로 platform-readiness 회귀화

### Primary goal

`parser 완전 재현보다 platform UX / analytics density 검증 우선`

즉 이 population의 주된 역할은 다음을 눈으로 보이게 만드는 것이다.

- cohort analytics card 밀도
- reports / manage list의 스캔성
- duplicate cluster 크기와 정리 UX
- snapshot / feature set explorer의 실제 운영 usefulness
- longitudinal 흐름의 해석 가능성

### Database mode

`운영 DB와 분리된 demo DB`

이유:

- synthetic row가 운영 데이터와 섞이면 실제 운영 신뢰도를 해친다
- 반복 seed / reset이 가능해야 한다
- QA / screenshot / PM review 용도로 안전하게 재생성 가능해야 한다

### Target cohort size

`약 300명`

이 정도가 적절한 이유:

- 현재 UI에서 sparse cohort가 아닌 dense cohort 동작을 충분히 드러낸다
- repeated measure, duplicate cluster, mixed source를 섞어도 전체 수가 과도하지 않다
- local/demo 환경에서도 seed / reset / smoke test가 과도하게 무겁지 않다

### Source mix

기본 비율:

- `CPET only`: 55%
- `CPET + FIT`: 25%
- `INSCYD + FIT`: 15%
- `standalone linked published only` 또는 partial artifact 중심: 5%

이 비율은 운영 초기에 가장 가능성이 높은 현실을 반영한다.

- CPET가 주력 입력
- 일부만 FIT가 붙는다
- INSCYD는 소수지만 분석상 중요하다
- 일부는 raw pipeline 없이 linked report로만 들어온다

## 3. Platform Questions This Population Must Answer

이 synthetic cohort는 아래 질문에 답할 수 있어야 한다.

### 3.1 Dashboard

- subject count가 커졌을 때 overview card가 여전히 의미 있는가
- analytics partial이 dense cohort에서 비어 보이지 않는가
- grouped report list가 repeated subject 상황에서 읽히는가
- duplicate badge / duplicate-only filter가 실제로 useful한가

### 3.2 Manage

- 검사 데이터 연결 탭에서 unlinked / linked / duplicate-prone submission이 섞여도 운영 가능한가
- subject linking / user linking이 repeated measures와 mixed source에서 자연스럽게 작동하는가
- snapshot explorer / feature set explorer 필터가 실제 운영 밀도에서 충분한가

### 3.3 Report Layer

- published report catalog가 large list에서도 관리 가능한가
- report delete / relink / rename / note flow가 dense dataset에서도 일관적인가
- grouped report headers가 repeated subject 상황에서 충분히 명확한가

### 3.4 Analytics Layer

- `subject_metric_snapshots` row grain이 mixed-source repeated subject를 수용하는가
- `subject_feature_sets`가 longitudinal / baseline / clustering 준비 계층으로 충분한가
- sparse subject와 dense subject가 같이 있어도 summary logic이 깨지지 않는가

## 4. Population Design

### 4.1 Subject distribution

총 `300 subjects`

권장 분포:

- `single-test subjects`: 150
- `2-3 tests subjects`: 105
- `4-6 tests subjects`: 35
- `7+ tests subjects`: 10

이 분포의 목적:

- 절반은 실제 운영 초반처럼 single-shot
- 나머지는 repeated measure가 충분히 섞여 longitudinal 기능을 드러냄
- 소수 heavy-history subject가 있어서 trend chart / compare / progression UX를 강하게 테스트할 수 있음

### 4.2 Source distribution

권장 건수 분포:

- `cpet_submission`: majority anchor source
- `inscyd_report`: minority but non-trivial source
- `published standalone report`: small supporting source

동일 subject 안에서 허용되는 조합:

- CPET only
- CPET + CPET repeated
- CPET + FIT-backed sessions
- CPET + INSCYD on different dates
- CPET + INSCYD same-date mixed-source
- standalone linked report only

### 4.3 Duplicate candidate distribution

총 subject 중 최소 `15-20%`는 duplicate-like artifact를 포함해야 한다.

duplicate 유형:

- exact duplicate-like:
  - 같은 subject
  - 같은 test_date
  - slug만 다른 report
- likely duplicate:
  - 같은 subject
  - 같은 날짜 또는 ±1일
  - source mix가 유사
- operator-confusing duplicate:
  - grouped view에서 사람이 정리 필요해 보이는 케이스

### 4.4 Missing / incomplete scenarios

총 subject 중 최소 `20%`는 일부 누락 시나리오를 포함해야 한다.

예:

- CPET 있지만 FIT 없음
- INSCYD 있지만 supporting fit evidence 약함
- report note / override 없음
- linked user 없음
- subject는 있으나 name normalization이 지저분함
- repeated subject인데 일부 시점만 materialization 가능한 상태

### 4.5 Longitudinal patterns

반복 측정 subject는 아래 4 패턴으로 분산한다.

- clear improver
- stable maintainer
- regressor
- noisy / non-monotonic

이유:

- trend card와 compare UI가 “개선만 보이는 가짜 세계”에 맞춰져 있으면 위험하다
- 실제 운영은 노이즈와 역행 케이스가 섞인다

## 5. Scenario Classes

최소 보장해야 할 scenario class:

1. `CPET-only baseline subject`
2. `CPET + FIT supported subject`
3. `INSCYD + FIT subject`
4. `same-day CPET + INSCYD mixed-source subject`
5. `duplicate-prone subject`
6. `linked standalone report subject`
7. `repeated subject with clear improvement`
8. `repeated subject with flat/noisy progression`
9. `partially linked subject (user/subject/report link mismatch)`
10. `sparse subject with missing analytics fields`

## 6. Mapping Rules Across Layers

### 6.1 Users / Subjects

- 모든 synthetic subject가 user를 가질 필요는 없다
- 권장:
  - `linked user present`: 70%
  - `subject only`: 20%
  - `report-linked only`: 10%

이유:

- 관리 화면은 perfect linkage가 아니라 imperfect linkage를 견뎌야 한다

### 6.2 Submissions / Jobs

- CPET 중심 scenario는 `submission + job`을 가진다
- 일부는 completed job 이후 published report까지 존재한다
- 일부는 incomplete 또는 partial metadata 상태를 가진다

### 6.3 Published report catalog

- dashboard/operator 검증 목적상 대부분의 seeded scenario는 published row까지 갖는 편이 좋다
- 단, 일부는 draft/incomplete 느낌을 주기 위해 catalog나 link가 빠진 상태를 남길 수 있다

### 6.4 subject_metric_snapshots

- synthetic population은 최종적으로 snapshot density를 충분히 만들어야 한다
- 동일 subject 내에서:
  - CPET snapshot 여러 개
  - INSCYD snapshot 0~2개
  - same-date mixed-source coexistence 일부

권장 목표:

- 총 snapshot row 수: `450~700`

### 6.5 subject_feature_sets

feature set은 최소 두 spec이 보이도록 한다.

- `endurance_core`
- `longitudinal_delta`

권장 목표:

- 총 feature row 수: `700~1200`

이 정도가 있어야:

- feature explorer
- summary count
- compare/export
- dashboard feature analytics

가 sparse하지 않게 보인다.

## 7. What Must Be Realistic vs. What May Be Synthetic

### 반드시 plausibility를 가져야 하는 것

- subject naming / grouping behavior
- measured_at / test_date chronology
- source_kind 분포
- repeated measure progression 형태
- duplicate cluster 구조
- snapshot/feature row 존재 방식
- dashboard / explorer가 읽는 핵심 flat metric 값의 범위

### 직접 raw parser truth를 재현하지 않아도 되는 것

- 실제 breath-by-breath waveform
- 완전한 COSMED 원본 구조
- 실제 FIT 바이너리의 모든 내부 필드
- INSCYD PDF 페이지 단위 rendering fidelity

즉 synthetic population은 “parser benchmark”가 아니라 “platform simulation”이다.

## 8. Metric Plausibility Heuristics

synthetic row는 아래 수준의 plausibility만 맞추면 된다.

### CPET-like ranges

- `vo2max_rel`: 대략 28~78
- `lt1_power_w`: 대략 80~260
- `lt2_power_w`: 대략 120~380
- `fatmax_power_w`: `lt1_power_w` 근처 또는 약간 아래
- `fatmax_gmin`: 대략 0.2~1.4

### INSCYD-like ranges

- `vlamax`: 대략 0.2~0.9
- `at_power_w`: 대략 140~360
- `carbmax_w`: AT 이상
- `glycogen_g`: 양수 범위

### Longitudinal constraints

- 대부분의 변화량은 “조금씩” 움직이는 쪽이 자연스럽다
- 소수 heavy-change subject만 눈에 띄는 improvement/regression을 가진다
- noisy subject는 일부 metric만 반대로 움직이게 두는 편이 좋다

## 9. Naming and Labeling Conventions

운영자 눈으로 보기 쉬워야 하므로 synthetic naming은 규칙적이어야 한다.

### Subject naming

- 기본:
  - `Synthetic 001`
  - `Synthetic 002`
- 사람이 보기 쉬운 alias도 허용:
  - `Demo Rider 014`
  - `Demo Mixed 027`

### Report slugs

- source/type가 보이게 한다
- 예:
  - `synthetic-014-cpet-20260401`
  - `synthetic-014-cpet-20260401-dup`
  - `synthetic-027-inscyd-20260315`

### Notes / labels

- 일부 row에는 운영 힌트형 note를 넣는다
- 예:
  - `duplicate candidate`
  - `fit missing`
  - `same-day mixed source`

이유:

- UI의 메모/배지/필터가 실제로 읽히는지 검증할 수 있다

## 10. Density Targets Per Surface

### Dashboard reports

- grouped headers가 여러 페이지 분량으로 나타날 정도의 row 수
- repeated subject가 충분해 grouping benefit이 명확해야 한다

### Dashboard analytics

- percentile / cohort card가 비어 보이지 않을 정도의 subject 수
- repeated measure subject가 enough 해서 trend narratives가 생겨야 한다

### Manage submissions

- linked / unlinked / duplicate-prone가 모두 섞인 상태
- operator가 정말 정리해야 할 목록처럼 보여야 한다

### Snapshot explorer

- source_kind filter가 실제 의미를 가질 정도의 mixed-source row 수
- compare / export를 눌러볼 만한 다양성이 있어야 한다

### Feature set explorer

- `endurance_core`와 `longitudinal_delta`가 모두 non-trivial count를 가져야 한다
- 일부 subject는 previous snapshot이 없어 delta가 안 생기는 케이스도 포함해야 한다

## 11. Explicit Non-Goals

이번 synthetic population 설계는 아래를 목표로 하지 않는다.

- 실제 논문용 inference quality 입증
- physiology-accurate simulator 구축
- 완전한 public dataset 대체
- parser 레이어 단독 정답셋 구축

이 문서는 제품 검증용 `densified operating environment` 설계다.

## 12. Deliverables Expected From This Spec

후속 태스크는 이 문서를 기반으로 아래를 구현해야 한다.

1. demo DB seeder
2. seeded platform QA harness
3. E2E validation suite
4. real golden corpus intake

즉 이 문서는 synthetic platform validation의 계약서 역할을 한다.

## 13. Acceptance Checklist

- synthetic cohort 규모가 `약 300명`으로 고정돼 있다
- mixed source / duplicate / repeated measure / missing-data scenario가 정의돼 있다
- users / subjects / submissions / reports / snapshots / feature sets로의 mapping 규칙이 정의돼 있다
- density target이 surface별로 정의돼 있다
- parser truth와 platform simulation의 경계가 명확하다
- 후속 seeder 구현이 이 문서만으로 시작 가능하다
