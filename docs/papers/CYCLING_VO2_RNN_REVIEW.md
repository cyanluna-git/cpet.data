# Cycling VO2 RNN Pilot Study Review

**Date:** 2026-03-31  
**Purpose:** `Cycling VO2.pdf`를 읽고, gas analyzer 없이도 VO2 kinetics를 추정하는 sequence model이 ZeLIA에 어떤 의미가 있는지 내부용으로 정리한다.  
**Audience:** researcher, admin, product owner  
**Source:** `docs/papers/Cycling VO2.pdf`

## 1. One-Page Conclusion

이 논문은 “CPET 없이도 VO2를 대신 측정할 수 있다”는 운영 솔루션이라기보다, `HR + power + cadence + respiratory frequency` 같은 비교적 구하기 쉬운 입력으로 `dynamic VO2 response`를 sequence model이 어느 정도 따라갈 수 있음을 보여주는 작은 pilot study다.

핵심 메시지는 다음과 같다.

- `recurrent neural network`로 cycling 중 VO2 kinetics를 추정하는 발상은 흥미롭다.
- 입력은 gas mask 없이도 일부 확보 가능한 값들 중심이다.
- 하지만 sample size가 작고, subject-specific normalization 의존이 강하며, 추가 자료 기준으로는 production deployment를 정당화할 만큼 강한 성능 테이블이 명확히 드러나지 않는다.

즉 ZeLIA에서 이 논문은 “지금 당장 실측 VO2를 대체한다”기보다는, 아래 방향의 연구 힌트로 보는 편이 맞다.

- gas data가 없는 riding session에서 VO2 surrogate를 연구한다.
- 현재 가진 `HR + power + cadence` 신호만으로 어느 정도까지 submax oxygen-demand proxy를 만들 수 있는지 본다.
- 단, measured CPET를 ground truth로 계속 유지하고 surrogate layer는 별도 연구 레이어로 둔다.

## 2. What the Study Actually Did

추가자료 기준으로 연구 설정은 비교적 명확하다.

- 참가자 수: `7명`
- 운동 과제:
  - long graded incremental-to-exhaustion test
  - Wingate test
  - step-change intensity protocols 2종
- 입력:
  - heart rate (`HR`)
  - power output (`P`)
  - respiratory frequency (`RF`)
  - pedalling cadence (`ω`)
- 출력:
  - dynamic `VO2 response`

validation은 두 trial 구조로 설명된다.

- Trial 1:
  `long-graded + Wingate + Test 2`로 학습하고 `Test 1`을 예측
- Trial 2:
  `long-graded + Tests 1 and 2`로 학습하고 `Wingate`를 예측

추가자료 후반부는 “새 참가자를 incremental test 하나로만 학습시켜도 되는가”도 시험한다.

## 3. Why This Paper Is Interesting for ZeLIA

현재 ZeLIA는 CPET와 INSCYD처럼 측정 기반 리포트를 강점으로 가진다. 이 논문은 그 반대편 질문을 던진다.

- gas analyzer가 없을 때 VO2 kinetics를 얼마큼 복원할 수 있는가
- measured CPET가 없는 field ride에서도 oxygen-demand story를 보조적으로 만들 수 있는가

이 관점에서 얻을 수 있는 연구 아이디어는 아래와 같다.

- `subject-specific VO2 surrogate`를 measured CPET로 calibration
- 추후 ride/FIT 데이터에서 `estimated VO2`, `estimated VO2 reserve`, `estimated oxygen cost drift` 같은 보조 지표 연구
- CPET 이후 추적 관찰 세션에서 gas mask 없이도 trend signal을 추정하는 보조 모델 개발

## 4. What Limits Immediate Productization

추가자료만 읽어도 제약이 꽤 분명하다.

### 4.1 Sample size is tiny

- 참가자는 `7명`
- pilot study 수준이라 일반화 근거가 약하다

### 4.2 Input set is not fully cheap in real life

논문 제목은 `easy-to-obtain inputs`라고 말하지만, ZeLIA 관점에서는 `RF`가 늘 쉽게 확보되지는 않는다.

- `HR`, `power`, `cadence`는 ride/FIT에서 흔하다
- `respiratory frequency`는 일반 field setup에서는 흔치 않다

즉 논문 그대로 복제하려면 입력 가용성부터 맞지 않을 수 있다.

### 4.3 Subject-specific normalization dependence

추가자료에서 training/test plot 설명은 각 입력을 individual `.json`의 maximal value로 normalization했다고 밝힌다.

이 구조는 실무에서 다음 문제를 만든다.

- 개인 최대값 사전 정보가 필요함
- calibration protocol이 있어야 함
- 신규 사용자 cold-start가 약함

### 4.4 Additional material is figure-heavy, not deployment-heavy

추가자료는 residual, correlation, Bland-Altman, autocorrelation plot을 풍부하게 주지만,
운영 관점에서 즉시 쓰고 싶은 aggregate benchmark table은 텍스트로 잘 드러나지 않는다.

즉 “그래서 실제로 어느 정도 오차까지 믿을 수 있나?”라는 실무 질문에는 아직 답이 약하다.

## 5. What ZeLIA Should Take From It

이 논문에서 지금 당장 가져갈 핵심은 “VO2 surrogate는 가능성이 있다” 정도이지, “실측 VO2를 대체해도 된다”가 아니다.

권장 해석:

- measured CPET는 gold/reference layer로 유지
- ride/FIT 기반 estimated VO2는 experimental layer로 분리
- 모델의 역할은 diagnosis가 아니라 trend support, oxygen-demand approximation, session annotation 쪽으로 한정

즉 제품 메시지는 아래가 안전하다.

- `estimated oxygen-demand profile`
- `surrogate VO2 kinetics (research)`
- `CPET-calibrated ride interpretation`

반면 아래는 아직 과하다.

- `VO2 without CPET`
- `clinical-grade VO2 prediction`
- `measured VO2 replacement`

## 6. Best-Fit Research Directions for This Repo

### Direction A: HR + power + cadence only baseline

논문과 완전히 같지 않아도, 현재 실제 데이터 가용성에 맞춘 최소 모델부터 보는 편이 낫다.

- 입력: `HR`, `power`, `cadence`, optional `time / protocol stage`
- 타깃: measured CPET `VO2`
- 목표: submax domain에서 usable한가

### Direction B: CPET-derived calibration + field inference

한 사람의 CPET를 calibration anchor로 쓰고, 이후 field session에 subject-specific surrogate를 적용하는 방향이다.

이건 ZeLIA가 현재 가진 강점과 가장 잘 맞는다.

### Direction C: Report helper, not score helper

당장은 surrogate model을 새로운 총점으로 쓰기보다, 리포트 문장과 차트 보조용으로 쓰는 것이 맞다.

- estimated oxygen demand curve
- effort vs oxygen-cost mismatch signal
- decoupling / drift commentary

## 7. Internal Guardrails

- measured gas-exchange와 surrogate model output을 같은 위상으로 놓지 않는다.
- surrogate VO2는 반드시 `experimental` 또는 `research` 레이어로 표기한다.
- input availability 문제를 먼저 해결한다. 특히 `RF`가 없을 때의 degraded model을 별도 설계해야 한다.
- cold-start user에서 쓸 수 있는지, 아니면 calibration-required인지 명확히 분리한다.

## 8. Suggested Next Steps

### Immediate

- 현재 repo에서 어떤 FIT/session에 `HR + power + cadence`가 안정적으로 있는지 inventory
- measured CPET와 같은 subject의 paired session 확보 가능성 조사

### Short-term experiment

- subject-specific baseline model
- RF 없는 reduced-input model
- submax-only prediction quality 비교

### Product boundary

- 초기엔 report helper feature로만 유지
- clinical or diagnostic wording은 금지

## 9. ZeLIA Takeaway

이 논문은 “VO2 surrogate 모델은 연구할 가치가 있다”는 강한 힌트다. 하지만 현재 기준으로는:

- 샘플이 작고
- 입력 요구가 실무와 완전히 맞지 않으며
- calibration 의존성이 있고
- aggregate deployment benchmark가 부족하다

따라서 ZeLIA는 이 논문을 `R&D direction note`로 받아들이는 것이 맞다.  
가장 좋은 다음 단계는 measured CPET를 reference로 삼아 subject-specific surrogate를 실험하고,
그 결과를 ride interpretation 보조 레이어로 붙이는 것이다.
