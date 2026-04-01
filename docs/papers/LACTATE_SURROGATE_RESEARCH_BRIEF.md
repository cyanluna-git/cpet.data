# Lactate Surrogate Model Research Brief

이 문서는 `CPET + 호흡가스 + 심박 + 파워`로 혈중 젖산 반응을 얼마나 근사할 수 있는지에 대한 연구를, ZeLIA 데이터 구조에 맞춰 별도 주제로 분리해 정리한 내부 메모다.

핵심 질문은 단순하다.

- 정말 `채혈 없이` lactate를 예측할 수 있는가?
- 아니면 더 현실적으로는 `threshold zone`, `lactate turning point`, `high-lactate risk band` 정도까지만 맞출 수 있는가?

이 주제는 매우 매력적이지만, 동시에 가장 과장되기 쉬운 주제다.  
그래서 연구 framing은 `lactate replacement`보다 `surrogate feasibility study`가 맞다.

## 왜 별도 페이지로 빼는가

다른 주제들은 비교적 고전적인 exercise physiology 논문 구조로 방어가 가능하다.  
하지만 이 주제는 다음이 동시에 필요하다.

1. 운동생리 해석
2. 시계열 데이터 정렬
3. 모델링 전략
4. leakage 방지
5. 임상/현장 해석 한계

즉, 같은 “석사 주제 후보” 카드 안에 넣기에는 너무 많은 설계 요소가 붙는다.

## 연구 주제 한 줄 정의

> CPET 중 수집되는 호흡가스, 심박, 파워, 시간축 정보를 사용해 혈중 젖산 반응 또는 threshold-relevant lactate zone을 예측할 수 있는지 평가하는 연구

## 연구 질문

1. VO2, VCO2, VE, RER, HR, power만으로 stage별 blood lactate를 어느 정도까지 추정할 수 있는가?
2. 절대 lactate 값 회귀보다 `LT1/LT2 relevant zone classification`이 더 안정적인가?
3. subject-specific calibration을 추가하면 성능이 유의하게 좋아지는가?
4. surrogate model은 어떤 조건에서 잘 맞고, 어떤 조건에서 실패하는가?

## 권장 framing

좋은 제목 예시:

- `CPET-derived respiratory and power features를 이용한 blood lactate surrogate model의 가능성 평가`
- `Threshold-aware surrogate modeling of blood lactate response during graded exercise testing`

피해야 할 제목:

- `Blood lactate can be replaced by AI`
- `Non-invasive lactate measurement without blood sampling`

## 왜 어려운가

- lactate는 stage 수가 적으면 label 자체가 거칠다.
- 사람마다 baseline이 달라 subject leakage가 쉽게 생긴다.
- 숫자가 맞아도 생리학적으로 말이 안 되는 예측이 나올 수 있다.
- 실제 현장에서는 “정확도 몇 %”보다 “threshold를 잘 잡는가”가 더 중요하다.

## 그래서 권장하는 1차 목표

1. 절대 lactate 회귀는 `exploratory`
2. 메인 평가는 `zone / threshold-aware classification`
3. global model과 subject-calibrated model을 둘 다 비교
4. 성능뿐 아니라 `실패 패턴`도 같이 보고
5. “대체 가능”이 아니라 “어디까지 근사 가능한가”를 결론으로 둔다

## Gemini Deep Research에 요청할 핵심 범위

- exercise physiology에서 blood lactate surrogate 관련 선행연구
- lactate threshold prediction / machine learning / non-invasive surrogate 연구
- CPET, cycling, graded exercise test 기반 데이터셋 구조
- 어떤 입력 변수 조합이 자주 쓰였는지
- absolute lactate regression vs threshold classification의 장단점
- subject-wise validation, external validation, calibration 전략
- 관련 저널과 발표 venue
- 지금 시점에서 novelty gap이 어디에 남아 있는지

## Gemini Deep Research Prompt

아래 프롬프트를 그대로 넣고, 필요하면 마지막에 우리 쪽 제약을 추가하면 된다.

```text
You are preparing a deep research report for a master's thesis in exercise physiology / sports data science.

Topic:
Building and evaluating a surrogate model for blood lactate response during graded exercise testing using CPET-derived variables such as VO2, VCO2, VE, RER, heart rate, power, and time-series structure.

Important framing:
- Do NOT frame this as “AI fully replaces blood lactate measurement.”
- Frame it as a feasibility study or surrogate modeling problem.
- Distinguish between:
  1) absolute blood lactate regression
  2) threshold-aware zone classification
  3) prediction of lactate turning points / LT1-LT2 relevant transitions

My real-world context:
- I have CPET data, respiratory gas data, stage/ramp metadata, heart rate, power, and some tests with measured blood lactate.
- Some subjects are measured repeatedly over time.
- My goal is to identify a defensible master's thesis direction, not to exaggerate clinical readiness.

Please produce a rigorous research report with the following sections:

1. Research landscape overview
- Summarize the overall state of the field on lactate estimation, lactate threshold prediction, and surrogate modeling from exercise test data.
- Separate classical physiology studies from machine learning studies.
- Explain what is already well established and what remains uncertain.

2. Prior literature mapping
- Identify and summarize the most relevant prior studies.
- Include studies on:
  - ventilatory threshold vs lactate threshold comparison
  - machine learning prediction of lactate or lactate threshold
  - non-invasive lactate estimation approaches
  - CPET / cycling / graded exercise modeling papers
- For each important paper, provide:
  - citation
  - study design
  - sample size
  - inputs
  - outputs
  - modeling approach
  - validation strategy
  - key findings
  - limitations

3. Methodology patterns in the literature
- Compare common modeling choices:
  - linear / ridge / lasso
  - tree-based models
  - sequence models
  - hybrid physiology-informed models
- Explain what targets were modeled:
  - blood lactate concentration
  - lactate threshold
  - anaerobic threshold
  - zone classification
- Explain which validation strategies are defensible and which are weak.
- Pay special attention to subject-wise split, leakage risk, and calibration.

4. What kind of thesis is actually defensible
- Based on the literature, assess whether a master's thesis should aim for:
  - absolute lactate regression
  - threshold-aware classification
  - subject-specific calibration study
  - feasibility study only
- Tell me which framing is most realistic and defensible for a master's thesis with limited data.

5. Data requirement analysis
- Estimate the approximate amount of data needed for each possible study design:
  - absolute regression
  - threshold zone classification
  - subject-calibrated modeling
- Distinguish between number of subjects, number of tests, and number of stage-level paired samples.
- Explain what minimum data might be publishable and what would be considered strong evidence.

6. Novelty gap
- Identify what gaps still remain in the field.
- Tell me where a small but meaningful contribution is still possible.
- Explicitly distinguish:
  - crowded topics
  - still-open questions
  - topics likely to be too ambitious for a master's thesis

7. Publication path
- Recommend suitable conferences and journals for this topic.
- Separate:
  - safest domestic / lower-risk venues
  - realistic English-language journals
  - ambitious journals
- Explain why each venue fits this topic.

8. Recommended thesis directions
- Give me 3 concrete thesis direction options:
  - conservative option
  - balanced option
  - ambitious option
- For each option provide:
  - suggested thesis title
  - core hypothesis
  - required data
  - analysis plan
  - main risks
  - expected contribution

9. Bottom-line recommendation
- If you were advising a master's student with limited but growing CPET + lactate data, what exact version of this topic would you recommend?
- Be explicit and pragmatic.

Output requirements:
- Write clearly enough for a non-expert graduate student to follow.
- Use structured headings and tables where useful.
- Include direct links or DOIs for key papers when possible.
- Prioritize primary papers, strong reviews, and reputable journals.
- Do not overclaim.
- Be honest about weak evidence and common failure modes.
```

## 기대 산출물

Gemini 결과가 잘 나오면, 다음 단계는 보통 아래 셋 중 하나다.

1. 논문 제목 2~3개로 압축
2. 변수표와 데이터 사전 초안 작성
3. 실제 ZeLIA 데이터 기준으로 “지금 가능한 버전”과 “추가 수집 후 가능한 버전” 분리
