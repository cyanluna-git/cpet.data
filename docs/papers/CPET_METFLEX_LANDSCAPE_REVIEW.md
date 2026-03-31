# CPET-Derived Metabolic Flexibility Metric

**Date:** 2026-03-31  
**Purpose:** 논문 탐색 결과를 바탕으로 ZeLIA/CPET 리포트에 적용할 수 있는 해석 포인트와 IP 리스크를 내부용으로 정리한다.  
**Audience:** researcher, admin, product owner  
**Source:** `docs/papers/CPET-Derived Metabolic Flexibility Metric_ Literature and Patent Landscape.pdf`

## 0. 아주 쉽게 말하면

이 논문은 “사람이 운동할 때 지방을 잘 쓰는지, 탄수화물로 빨리 넘어가는지”를 CPET 데이터로 더 정교하게 설명해보자는 제안이다.

초심자 기준으로 바꾸면 이렇게 이해하면 된다.

- `VO2`는 산소를 얼마나 쓰는지다.
- `VCO2`는 이산화탄소를 얼마나 내보내는지다.
- `RER`는 `VCO2 / VO2` 비율이다.
- 운동 강도가 올라가면 보통 지방보다 탄수화물 의존도가 커진다.
- 그래서 `RER`가 1.0에 가까워질수록 “이제 지방보다는 탄수화물 쪽으로 많이 넘어왔구나”라고 해석할 수 있다.

이 논문은 바로 이 과정을 숫자로 요약해서 하나의 `metabolic flexibility` 지표처럼 써보려는 것이다.

하지만 중요한 점은:

- 이 아이디어 자체가 완전히 새로운 과학은 아니다.
- 기존에 알려진 수식과 개념을 잘 묶은 것이다.
- 그래서 제품 기능으로는 좋지만, “우리가 완전히 새로운 생리학 지표를 발명했다”고 말하기는 어렵다.

## 0-1. 용어 풀이

- `VO2`: 산소 섭취량. 몸이 에너지를 만들기 위해 산소를 얼마나 쓰는지
- `VCO2`: 이산화탄소 배출량
- `RER`: `VCO2 / VO2`. 연료 사용 상태를 볼 때 쓰는 비율
- `FatMax`: 지방 산화가 가장 높게 나오는 운동 강도
- `crossover`: 지방 중심에서 탄수화물 중심으로 넘어가는 전환 지점
- `lactate coupling`: 젖산 반응을 같이 읽어서 연료 사용 전환을 해석하는 접근

## 1. One-Page Conclusion

이 문서의 결론은 명확하다. `VO2/VCO2`에서 기질 산화를 구하고, `RER = 1.0` 이전까지 지방/탄수화물 기여를 적분하고, `FatMax`, `crossover`, `lactate coupling`을 조합해 하나의 metabolic flexibility metric을 만드는 아이디어 자체는 새로운 생리학적 발견이 아니다.

반대로, 제품 기능으로는 충분히 가치가 있다. 이유는 아래와 같다.

- 기초 수식은 이미 확립돼 있다.
- `RER <= 1.0`까지 분석하는 관행도 학술적으로 널리 받아들여진다.
- `lactate + gas exchange`를 같이 보는 해석도 충분한 과학적 근거가 있다.
- 따라서 리포트 기능으로는 설득력이 높고, 해석형 제품으로는 바로 사용할 수 있다.

문제는 `특허`와 `독점적 주장`이다.

- broad claim은 매우 어렵다.
- 특히 2025년 graded exercise 논문이 `RER < 1.0` 구간까지 fat/CHO oxidation과 lactate AUC를 함께 계산해, novelty/obviousness에 가장 큰 압박을 준다.
- 남는 차별화 지점은 `breath-by-breath interpolation`, `partial-interval integration`, `artifact handling`, `lactate-informed correction`, `repeatability validation` 같은 구현 세부와 검증 데이터다.

즉, 현재 ZeLIA의 방향은 이렇게 잡는 편이 맞다.

- `RQ 1.0 fuel contribution`은 제품 기능으로 유지
- 단일 `metabolic flexibility score`는 연구용/실험용 레이어로 분리
- 제품 문구는 `설명 가능한 해석형 feature` 중심으로 유지
- 특허 가능성은 `기본 공식`이 아니라 `강건한 처리 파이프라인 + 검증 결과`에 걸어야 한다

## 1-1. 이 결론을 더 쉽게 풀면

ZeLIA 입장에서는 이렇게 이해하면 된다.

- 좋은 점:
  - 지금 만들고 있는 `RQ 1.0 이전 지방/탄수화물 기여율`, `FatMax`, `crossover` 같은 기능은 충분히 가치 있다.
  - 사용자에게 “당신은 어느 강도까지 지방을 잘 쓰고, 언제부터 탄수화물 의존이 커지는가”를 설명해줄 수 있다.
- 조심할 점:
  - 이런 기능을 “검증 완료된 새 바이오마커”처럼 말하면 과하다.
  - 특히 단일 점수 하나로 사람의 metabolic flexibility를 다 말할 수 있다고 주장하면 방어가 약하다.

즉, 이 논문은 “이 기능을 계속 밀어도 된다. 다만 말하는 방식은 조심해라”에 가깝다.

## 2. What the Paper Actually Defines

논문은 최종 점수 공식을 명시하지 않는다. 대신 `metric definition` 관점에서 아래 파이프라인을 정의한다.

### Inputs

- breath-by-breath 또는 고빈도 `VO2`, `VCO2`, timestamp
- external workload: cycling power 또는 treadmill speed/grade
- optional heart rate
- optional blood lactate with time or stage alignment

### Core pipeline

- `RER = VCO2 / VO2` 계산
- 보통 `RER <= 1.0`의 submax domain 선택
- stoichiometric equation으로 fat oxidation / CHO oxidation 계산
- 이를 `kcal/min`으로 변환
- `RER = 1.0` crossing 시점과 강도를 interpolation
- 시작 시점부터 그 crossing까지 trapezoidal integration
- `FatMax`, `MFO`, `crossover`, `RQ kinetics`, `lactate-coupled features` 추출
- 마지막에 composite metabolic flexibility score 구성

### Important observation

여기서 정말 구체적인 것은 `pipeline`이지, 최종 score formula는 아니다. 따라서 novelty가 생긴다면 점수 이름보다는 아래가 중요하다.

- exact crossing interpolation
- partial interval integration
- noise/artifact handling
- lactate-informed correction near acidosis
- validation showing better repeatability or discrimination

## 3. Closest Scientific Prior Art

문서는 “가장 가까운 선행기술”을 꽤 분명하게 정리한다.

### Foundational science

- Weir 1949: energy expenditure from `VO2/VCO2`
- Frayn 1983: substrate oxidation from gas exchange
- Péronnet–Massicotte 1991: non-protein RQ tables and stoichiometric basis
- Jeukendrup & Wallis 2005: practical guidance and limitations

이 네 축만으로도 `VO2/VCO2 -> fat/CHO oxidation`은 이미 공지기술임이 분명하다.

### Exercise metabolism concepts already established

- crossover concept: intensity가 올라갈수록 지방에서 탄수화물 우세로 이동
- FatMax / MFO: graded exercise에서 관측되는 well-known output
- lactate accumulation vs fat oxidation: 음의 상관 관계가 잘 보고됨

즉, 아래 개별 요소는 대부분 이미 잘 알려져 있다.

- `FatMax`
- `crossover`
- `RER = 1.0 boundary`
- lactate와 substrate oxidation의 결합 해석

### The most important prior-art pressure point

문서가 가장 경계하는 것은 2025년 graded-exercise intervention study다.

이 논문은 이미:

- `RER = 1.00`까지 fat/CHO oxidation 계산
- `RER < 1.00` 구간의 total energy 계산
- fat oxidation, CHO oxidation, lactate의 AUC 계산

을 수행한다.

우리와 차이가 있다면:

- stage-averaged values 기반이라는 점
- breath-by-breath trapezoidal integration + interpolated crossing이 아니라는 점

즉 차별점은 “개념”이 아니라 “계산 정밀도와 구현” 쪽이다.

## 4. Patent Landscape Read

논문은 patent landscape도 같이 읽는다. 요지는 다음과 같다.

### Older zone / threshold patents

- `US5297558A`
- `US6554776B1`

둘 다 RER, fat-metabolization curve, training zone, threshold 같은 주제를 다루며, 문서상 expired로 보인다. 직접 집행 리스크는 낮을 수 있지만, novelty reference로는 강하다.

### Abandoned metabolic fuel type application

- `US20160338618A1`

`metabolic switch point`, exhaled `O2/CO2`, fuel-type estimation, calorie estimation 등 우리가 생각하는 서술과 개념적으로 상당히 가깝다. abandoned라 enforceable right는 약하지만, “이미 누군가 이렇게 생각했다”는 prior art로는 충분하다.

### KR acidosis-aware RQ/RER filing

- `KR20160127161A`

`RQ vs RER distinction`, acidosis, excess CO2, fuel-use inference가 붙어 있어 개념상 꽤 인접하다. 다만 문서는 legal status 확정 없이 conceptually adjacent라고만 본다.

### Practical reading for us

지금 단계에서 broad patent narrative는 위험하다. 특히 아래 문장은 피해야 한다.

- “We invented calculating metabolic flexibility from CPET gas exchange.”
- “We invented using RER 1.0 as the integration boundary.”
- “We invented lactate-coupled substrate flexibility interpretation.”

더 안전한 포지션은 이렇다.

- 우리는 established science를 ZeLIA report feature로 operationalize한다.
- novelty가 있다면 robust processing / interpolation / correction / validation 레벨에 있다.

## 5. Implications for the Current Repo

현재 repo는 이미 논문에서 말하는 핵심 제품 기능 중 일부를 구현했다.

### Already aligned with the paper

- `RQ 1.0` 이전 연료 기여율 계산
- exact crossing handling
- `FatMax`, `crossover` 등 해석형 output
- 일부 리포트에서 `Metabolic Flexibility Index` 카드 제공

### What this paper says about our current positioning

현재 기능은 제품으로서는 충분히 의미가 있다. 하지만 표현을 조심해야 한다.

- `RQ 1.0 fuel contribution`
- `submax fuel-use summary`
- `crossover / FatMax / lactate-coupled interpretation`

이 정도는 설명 가능한 product feature다.

반면 아래는 아직 과하다.

- “validated metabolic flexibility biomarker”
- “novel proprietary physiology metric”
- “patentable composite score”

### Why the current score should stay experimental

현재 단일 점수는 알려진 output의 weighted combination처럼 읽힐 수 있다.

- fat share
- crossing proximity
- FatMax proximity to VT1

논문 관점에서는 이런 방식이 가장 `obvious aggregation`으로 공격받기 쉽다. 따라서 score는:

- research label 유지
- raw observables보다 subordinate
- reproducibility/versioning/QC 함께 노출

이 방향이 맞다.

## 5-1. 지금 리포트에서 어떻게 읽으면 되는가

현재 ZeLIA 리포트를 보는 사람 기준으로는 아래처럼 연결하면 이해가 쉽다.

- `RQ 1.0 fuel contribution`
  - “고강도로 완전히 넘어가기 전까지 지방과 탄수화물을 얼마나 썼는가”
- `FatMax`
  - “지방을 가장 잘 쓰는 강도는 어디쯤인가”
- `crossover`
  - “지방보다 탄수화물 의존이 더 커지기 시작하는 지점은 어디인가”
- `Metabolic Flexibility Index`
  - “위 값들을 요약해본 연구용 점수”

즉 현재 사용자에게 가장 바로 전달하기 좋은 것은 raw component다.
단일 score는 보조 설명 정도로만 두는 편이 맞다.

## 6. Recommended Product and Research Position

### Product message

ZeLIA는 지금 당장 이렇게 말하는 것이 가장 안전하다.

- CPET 기반 `RQ 1.0 fuel contribution`
- `FatMax`, `crossover`, `lactate-coupled` summary
- protocol-aware, report-oriented interpretation

### Research / IP message

연구용으로는 아래를 더 발전시킬 가치가 있다.

- breath-by-breath artifact handling
- boundary-confidence around `RER = 1.0`
- lactate-informed correction near acidosis
- protocol robustness across ramp/stage variants
- test-retest reliability vs stage-based AUC methods

### What would make a stronger future claim

- 동일 프로토콜 반복 측정에서 CV/ICC 개선
- stage-based summary보다 더 안정적임을 증명
- lactate correction이 `RER > 1.0` 인접 구간 해석을 개선함을 증명
- 여러 protocol에서 일관되게 작동함을 증명

즉 앞으로 필요한 것은 “더 멋진 이름”이 아니라 “더 강한 validation”이다.

## 7. Recommended Internal Guardrails

이 논문을 읽은 뒤 내부적으로 최소한 아래 원칙은 잡아두는 편이 좋다.

- `RQ`와 `RER`는 구현/리포트에서 혼용하지 않는다.
- `RER = 1.0` boundary는 convention이자 practical cutoff로 설명한다.
- no crossing, noisy breath data, missing lactate, protocol mismatch에는 explicit warning을 둔다.
- score는 반드시 versioned experimental layer로 둔다.
- raw observables와 composite interpretation을 분리한다.

## 8. Suggested Next Steps

### Immediate

- 현재 ZeLIA 리포트의 `Metabolic Flexibility Index` 표현을 연구용 톤으로 조정
- `RQ 1.0 fuel contribution`과 score를 분리된 레이어로 설명
- `boundary-confidence` / `no crossing` / `protocol suitability` 메시지 추가

### Short-term research

- repeated-test reliability study
- protocol sensitivity study
- lactate-aligned correction experiment
- stage-AUC vs breath-by-breath interpolation comparison

### If IP is ever revisited

- broad claim은 지양
- 구현 세부 + technical effect + validation 데이터 중심으로만 검토
- KR/US family status는 변리사와 최신 데이터로 재검토

## 9. Primary Sources Mentioned in the Paper

- Weir 1949
- Frayn 1983
- Péronnet & Massicotte 1991
- Jeukendrup & Wallis 2005
- San-Millán & Brooks 2018
- Murru et al. 2024
- Kripp et al. 2025
- US5297558A
- US6554776B1
- US20160338618A1
- KR20160127161A

## 10. ZeLIA Takeaway

이 논문은 ZeLIA가 지금 하는 일을 멈추라고 말하지 않는다. 오히려 제품 기능으로는 충분히 설득력 있다고 본다.

다만 말하는 방식은 바꿔야 한다.

- `설명 가능한 연료/대사 해석 feature`로는 강하다.
- `독점적이고 새로운 biomarker`처럼 말하면 약하다.

따라서 지금의 최선은:

- feature는 계속 제품화
- score는 연구용으로 보수적 운영
- validation이 쌓이면 그때 더 강한 주장 검토
