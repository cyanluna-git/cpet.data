# Real CPET Golden Corpus Intake v1

> Date: 2026-04-04
>
> Status: active
>
> Kanban: `#2176 Add small real CPET golden corpus intake for parser realism checks`

## 1. Purpose

이 문서는 synthetic demo population과 별도로, 공개 실데이터 기반의 작은 CPET golden corpus를 로컬에 intake하는 기준을 정의한다.

목적은 다음과 같다.

- parser / extractor / analytics 설계가 완전히 가짜 분포에만 맞춰지는 것을 방지
- 실제 CPET 시계열과 메타데이터 분포를 소량이라도 참조 가능하게 유지
- demo platform validation에서 `현실적인 값의 범위`를 sanity check할 기준 확보

이 corpus는 `운영 업로드 포맷의 완전 재현`이 아니라, `실제 공개 CPET 데이터의 작은 curated subset`이다.

## 2. Selected Sources

### 2.1 ACTES

- Source: PhysioNet
- Landing page: <https://physionet.org/content/actes-cycloergometer-exercise/1.0.0/>
- Download base: <https://physionet.org/files/actes-cycloergometer-exercise/1.0.0/>

왜 선택했는가:

- cycle ergometer 기반으로 현재 플랫폼의 CPET 맥락과 잘 맞음
- `subject-info.csv`와 `test_measure.csv` 구조가 단순해서 빠르게 intake 가능
- 데이터셋 전체 크기가 작아 `golden corpus`로 쓰기 적당함

제한:

- 호흡 가스 변수는 `VO2`, `RR`, `power` 중심이라 현재 parser 입력 포맷과 동일하지 않음
- raw `.xlsx` 업로드 재현용이 아니라 `reference realism`용에 더 가깝다

### 2.2 Treadmill exercise cardiorespiratory dataset

- Source: PhysioNet
- Landing page: <https://physionet.org/content/treadmill-exercise-cardioresp/1.0.1/>
- Download base: <https://physionet.org/files/treadmill-exercise-cardioresp/1.0.1/>

왜 선택했는가:

- `VO2`, `VCO2`, `HR`, `RR`, `VE`, `Speed`를 포함한 richer time-series 구조
- multi-test / repeated `ID_test` 구조라 curation에 적합
- small curated subset을 만들기 쉽다

제한:

- treadmill 기반이라 cycle CPET와 직접 동일시하면 안 됨
- age distribution이 건강한 소아/청소년 중심이라 성인 athlete cohort와 다름

## 3. Intake Strategy

원칙:

1. raw 다운로드는 공개 URL에서 재현 가능해야 한다.
2. repo에는 대용량 원본을 커밋하지 않는다.
3. 로컬/CI에서 반복 가능한 `curated subset + manifest`를 만든다.
4. golden corpus는 parser truth set이 아니라 realism reference set이다.

## 4. Directory Layout

기본 출력 경로:

`tmp/real-cpet-golden-corpus`

하위 구조:

- `raw/actes-cycloergometer-exercise/`
- `raw/treadmill-exercise-cardioresp/`
- `curated/actes-cycloergometer-exercise/`
- `curated/treadmill-exercise-cardioresp/`
- `manifests/real_cpet_golden_corpus_manifest.json`

## 5. Curation Rules

### 5.1 ACTES

- `subject-info.csv` 전체 유지
- `test_measure.csv` 전체 유지

이유:

- 총 subject 수가 작음
- cycle ergometer reference로 dataset 전체를 유지해도 부담이 적음

### 5.2 Treadmill

- `subject-info.csv`를 age / `ID_test` 기준 정렬
- 전체 `ID_test` 중 deterministic even sample로 소수 선택
- 선택된 `ID_test`에 해당하는 `subject-info.csv`, `test_measure.csv`만 curated subset에 유지

기본 선택 크기:

- `12 tests`

이유:

- raw는 크지만 curated subset은 작게 유지 가능
- repeated / varied demographic 분포를 일부 유지할 수 있음

## 6. Operator Entrypoint

```bash
python scripts/intake_real_cpet_golden_corpus.py --reset
```

기본 동작:

- 두 PhysioNet 소스의 CSV를 다운로드
- curated subset 생성
- manifest 작성

빠른 smoke:

```bash
python scripts/intake_real_cpet_golden_corpus.py --reset --datasets actes
```

설명:

- `ACTES`는 작아서 빠른 sanity check에 적합
- `treadmill`의 `test_measure.csv`는 더 커서 full intake 시간이 더 길 수 있다

## 7. Non-goals

- 현재 업로드 parser가 바로 먹는 `.xlsx`, `.pdf`, `.fit` 포맷 완전 대체
- training dataset 규모 확보
- 연구 논문용 통계 분석용 본 corpus 구축

## 8. Expected Use

이 corpus는 아래에 쓰인다.

- extractor / metric naming sanity check
- dashboard/demo card의 값 범위 sanity check
- future importer prototype validation
- synthetic population generator tuning reference

## 9. Acceptance

- 한 번의 명령으로 raw download + curated subset + manifest가 생성된다
- output이 `운영 DB/운영 data dir`와 분리된다
- source URL과 curation decision이 manifest에 남는다
- curated subset 크기가 작아 반복 QA에 부담이 없다
