# Platform Readiness QA Harness v1

> Date: 2026-04-04
>
> Status: active
>
> Kanban: `#2177 Create seeded platform-readiness QA checks for dashboard manage explorers and reports`

## 1. Purpose

이 문서는 seeded demo environment를 기준으로 플랫폼이 실제 운영 밀도에서도 읽히고 관리 가능한지를 반복 점검하는 QA harness 기준을 정의한다.

핵심 질문:

- dashboard / reports / manage / explorer가 dense cohort에서도 비어 보이지 않는가
- duplicate / repeated / mixed-source / sparse subject가 동시에 있어도 화면과 read model이 일관적인가
- 발견된 gap을 후속 태스크로 바로 전환할 수 있는가

## 2. Harness Shape

하나의 harness는 아래 3개를 같이 본다.

1. `DB coherence`
2. `authenticated page / partial smoke`
3. `follow-up candidate generation`

즉 단순 HTTP `200`이 아니라, seeded data가 실제로 충분히 “보이는지”와 orphan/stale row가 없는지도 함께 검사한다.

## 3. Minimum Coverage

### 3.1 Dashboard / Reports

- `/dashboard?tab=reports`
- `/api/jobs/partial?group_by=subject`

확인할 것:

- grouped report rendering
- duplicate badge visibility
- dense repeated subject readability

### 3.2 Manage

- `/manage?tab=submissions`
- `/manage?tab=snapshots`
- `/manage?tab=feature_sets`

확인할 것:

- submission linking / duplicate surface
- snapshot explorer density
- feature set explorer density

### 3.3 Report Rendering

- seeded published report URL 1건 이상

확인할 것:

- published report HTML이 실제로 열리는가
- seed된 report layer가 catalog와 일치하는가

## 4. DB Coherence Rules

최소 점검 항목:

- subject / user / submission / job / report_catalog row count
- snapshot / feature row count
- duplicate candidate count
- repeated subject count
- mixed source kind 존재 여부
- orphan snapshot / orphan feature anchor 여부

## 5. Follow-up Output

harness 결과는 아래 두 종류를 낸다.

- `ready: true/false`
- `suggested_follow_up_tasks[]`

이 배열은 후속 kanban task 초안으로 바로 복사 가능한 형태를 유지한다.

## 6. Operator Entrypoint

```bash
python scripts/check_platform_readiness_demo.py --seed-if-missing
```

선택적으로 JSON 저장:

```bash
python scripts/check_platform_readiness_demo.py \
  --seed-if-missing \
  --output-json tmp/platform-validation-demo/readiness-report.json
```
