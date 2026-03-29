# Two-Block CPET Fuel Split Guide

2블럭 CPET에서 `RQ 1.0 도달 전까지의 총 에너지 중 지방과 탄수화물이 각각 몇 kcal, 몇 %를 기여했는가`를 계산하는 기준 문서입니다.

이 문서는 현재 `pipeline/analysis.py`, `pipeline/report.py`, `pipeline/schema.py`, `pipeline/parsers/cosmed.py`에 반영된 계산 규칙을 설명합니다.

## 목적

이번 프로토콜은 아래 두 블럭으로 구성됩니다.

- Block 1: FatMax 측정을 위한 완만한 램프
- Block 2: VO2max 확인을 위한 10초 ramp-up

이 프로토콜에서는 FatMax, VO2max, VT1/VT2와 함께 아래 값을 같이 해석합니다.

- `RQ 1.0 crossing`
- `RQ 1.0 이전 total kcal`
- `그 total kcal 중 지방과 탄수화물이 각각 차지하는 kcal 및 비율`

핵심 질문은 이것입니다.

- `RQ가 1.0이 되기 전까지 몸이 쓴 에너지 중 지방은 몇 %, 탄수화물은 몇 %였는가?`

## 계산에 사용한 공식

간접열량측정 기반 substrate oxidation은 Frayn (1983) 식을 사용합니다.

- Fat oxidation, g/min  
  `fat_g/min = 1.67 * VO2(L/min) - 1.67 * VCO2(L/min)`

- Carbohydrate oxidation, g/min  
  `CHO_g/min = 4.55 * VCO2(L/min) - 3.21 * VO2(L/min)`

전제:

- protein oxidation은 무시
- VO2, VCO2는 `L/min` 단위로 변환 후 계산

출처:

- Frayn KN. *Calculation of substrate oxidation rates in vivo from gaseous exchange.* J Appl Physiol. 1983;55(2):628-634.  
  https://pubmed.ncbi.nlm.nih.gov/6618956/

운동 중 kcal 환산은 아래 계수를 사용합니다.

- Fat: `9.75 kcal/g`
- CHO: `4.07 kcal/g`

출처:

- Jeukendrup AE, Wallis GA. *Measurement of substrate oxidation during exercise by means of gas exchange measurements.* Int J Sports Med. 2005;26 Suppl 1:S28-S37.  
  https://pubmed.ncbi.nlm.nih.gov/15702454/

## 계산 절차

### 1. 활성 BxB window 선택

`analysis.py`의 active exercise window를 먼저 사용합니다.

- 운동 전/후 resting 구간 제외
- 실제 운동 breath-by-breath row만 사용

### 2. substrate column 정규화

일부 COSMED export는 `Fat`, `CHO` 열 이름은 g/min처럼 보이지만 실제 값이 `mg/min scale`로 들어오는 경우가 있습니다.

예:

- `2338` 는 실제로는 `2.338 g/min`에 가까운 스케일

현재 구현은 아래 기준으로 이를 탐지합니다.

- positive median이 `20 g/min`보다 비현실적으로 크면 suspicious로 판단

이 경우는 raw `Fat/CHO`를 그대로 믿지 않고, `VO2/VCO2`에서 다시 계산합니다.

즉 현재 기준은:

- raw substrate가 정상 범위면 그대로 사용
- raw substrate 단위가 의심되면 `VO2/VCO2` 기반으로 재계산
- `Fat`만 비어 있고 `CHO`만 이상 단위인 경우도 둘 다 재계산

### 3. RQ 1.0 crossing 찾기

`rq >= 1.0` 이 처음 성립하는 지점을 찾습니다.

만약 정확히 1.0인 샘플이 없고,

- 직전 row는 `< 1.0`
- 다음 row는 `> 1.0`

이면 두 row 사이를 선형 보간해서 `exact crossing time`을 계산합니다.

같이 보간하는 값:

- `t_s`
- `fat_gmin`
- `cho_gmin`
- `bike_power_w`
- `hr_bpm`

### 4. RQ 1.0 전 구간 적분

cutoff row까지의 substrate rate를 kcal/min으로 바꾼 뒤 적분합니다.

- `fat_kcal_rate = fat_gmin * 9.75`
- `cho_kcal_rate = cho_gmin * 4.07`

적분은 trapezoid rule로 수행합니다.

- x축: `t_s / 60` 즉 분(min)
- y축: `kcal/min`

따라서:

- `fat_kcal = integral(fat_kcal_rate over time_min)`
- `cho_kcal = integral(cho_kcal_rate over time_min)`
- `total_kcal = fat_kcal + cho_kcal`

마지막으로 비율을 계산합니다.

- `fat_pct = fat_kcal / total_kcal * 100`
- `cho_pct = cho_kcal / total_kcal * 100`

## 이번 Changmo Hwang 케이스 적용 결과

입력 파일:

- `20260106 Changmo Hwang (CPET Mixing Chamber)_20260106105300.xlsx`
- `2026-01-06-10-29-23 (1).fit`

프로토콜 해석:

- Block 1: `80W -> 160W` steady / slow ramp 성격
- Block 2: `180W`부터 시작하는 10초 ramp로 VO2max 확인

리포트 기준 결과:

- Protocol name: `Two-Block FatMax + VO2max CPET`
- VO2max: `35.8 mL/kg/min`
- FatMax: `68 W`
- VT1: `96 W`
- VT2: `119 W`

RQ 1.0 fuel split:

- `crossing_time_s`: `874.9 s`
- `crossing_power_w`: `180 W`
- `crossing_hr_bpm`: `173 bpm`
- `fat_kcal`: `66.71 kcal`
- `cho_kcal`: `96.74 kcal`
- `total_kcal`: `163.45 kcal`
- `fat_pct`: `40.8 %`
- `cho_pct`: `59.2 %`

해석:

- RQ 1.0 이전 전체 에너지 사용량은 `163.45 kcal`
- 이 중 지방이 `40.8%`, 탄수화물이 `59.2%`
- 즉 이 케이스는 FatMax block을 지나 VO2max block으로 넘어가기 전까지, 지방 우세 상태만 유지된 것이 아니라 상당한 비율의 탄수화물 기여가 이미 같이 올라온 상태였습니다.

## 왜 raw CHO 열을 그대로 쓰지 않았는가

이번 COSMED 파일의 raw `CHO` 열은 초반부터 아래처럼 매우 큰 값을 보였습니다.

- 예: `2338`, `2149`, `1849`

이 값은 일반적인 운동 중 `g/min`으로는 비현실적입니다.  
그래서 현재 구현은 이를 suspicious substrate unit으로 보고, `VO2/VCO2` 기반으로 재계산합니다.

이 판단이 없으면 다음 문제가 생깁니다.

- `RQ 1.0 이전 total kcal`가 수십만 kcal로 비정상 폭증
- report insight가 완전히 왜곡

따라서 이번 케이스에서 최종 채택된 값은:

- raw CHO column 직접값이 아니라
- `VO2/VCO2 -> Frayn equation -> kcal integration`

입니다.

## 구현 위치

- parser time normalization: [pipeline/parsers/cosmed.py](../../pipeline/parsers/cosmed.py)
- protocol inference: [pipeline/schema.py](../../pipeline/schema.py)
- substrate normalization / RQ 1.0 split: [pipeline/analysis.py](../../pipeline/analysis.py)
- report summary / fallback substrate rendering: [pipeline/report.py](../../pipeline/report.py)

## 운영 메모

이번 기능 반영으로 리포트는 아래 URL에 게시되었습니다.

- https://cpet.cyanluna.com/report/changmo-hwang-20260106/

운영 게시 기준으로도 아래 문구가 포함되어 있습니다.

- `RQ 1.0 이전 에너지 기여는 지방 40.8% / 탄수화물 59.2%`
- `RQ 1.0 전 총 163.4 kcal`
