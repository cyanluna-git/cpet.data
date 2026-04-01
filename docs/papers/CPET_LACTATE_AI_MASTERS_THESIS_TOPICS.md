# CPET + Lactate + AI 기반 석사 논문 주제 후보

이 문서는 현재 ZeLIA/CPET 플랫폼에서 축적 중인 `CPET + 호흡가스 + 젖산염(lactate) + 일부 반복 측정 + 부가 센서(FIT/ZWO)` 데이터를 바탕으로,
현실적으로 수행 가능한 석사 논문 주제 후보를 정리한 초안이다.

정리 기준은 다음과 같다.

- 현재 실제 수집 가능한 데이터와 잘 맞는가
- 석사 논문으로서 질문이 명확한가
- 너무 거대한 연구가 아니라 `1년 내외`에 끝낼 수 있는가
- 제품/리포트 기능과도 연결될 수 있는가

---

## 1. CPET와 혈중 젖산을 통합한 개인별 LT1/LT2 추정 모델 비교

### 한 줄 설명

호흡가스 기반 threshold와 젖산 기반 threshold가 얼마나 일치하는지, 그리고 언제 차이가 커지는지를 정량적으로 비교하는 연구다.

### 왜 중요한가

운동생리 현장에서는 `LT1`, `LT2`, `VT1`, `VT2` 같은 지표를 많이 쓰지만, 실제로는 계산 방식이 다르고 개인에 따라 결과가 다르게 나온다.  
이 주제는 “어떤 threshold가 더 맞다”를 단정하기보다, `어떤 조건에서 서로 일치하고 언제 어긋나는지`를 보여주는 데 의미가 있다.

### 연구문제

1. 호흡가스 기반 LT1/LT2와 혈중 젖산 기반 LT1/LT2는 개인 수준에서 어느 정도 일치하는가?
2. 두 방법의 차이는 성별, 체격, 훈련 수준, 프로토콜 유형, 반복 측정 여부에 따라 달라지는가?
3. 단일 방식보다 `통합 추정 모델`이 더 안정적인 개인별 threshold를 제시할 수 있는가?

### 가설

- 가설 1: 호흡가스 기반 threshold와 젖산 기반 threshold는 집단 평균에서는 유사하지만, 개인별로는 유의한 차이가 존재한다.
- 가설 2: 프로토콜 구조가 복잡하거나, lactate curve가 완만한 피험자일수록 두 방식의 차이가 커진다.
- 가설 3: 호흡가스와 젖산 지표를 함께 쓰는 통합 추정 모델은 단일 방식보다 재검사 간 변동성이 낮다.

### 필요한 데이터

- CPET BxB 데이터
  - VO2, VCO2, VE, RER/RQ, HR, Power
- 젖산 측정 데이터
  - stage별 lactate 값
- 테스트 메타데이터
  - protocol type, ramp/block 구조, test date
- 피험자 프로필
  - 성별, 나이/출생연도, 체중, 체지방률, 훈련 수준
- 반복 측정 데이터
  - 가능하면 동일 피험자의 2회 이상 테스트

### 분석방법

1. 각 테스트에서 아래 지표를 각각 산출한다.
   - 호흡가스 기반 LT1/LT2
   - 젖산 기반 LT1/LT2
2. 두 방식의 차이를 power, HR, VO2 기준으로 계산한다.
3. Bland-Altman plot, ICC, 재검사 오차, mixed-effect model로 일치도를 평가한다.
4. 입력 변수로 `VE, VCO2, RER, lactate slope, body composition, protocol metadata`를 넣어 통합 threshold 추정 모델을 만든다.
5. 모델 비교:
   - 단일 호흡가스 방식
   - 단일 젖산 방식
   - 통합 방식

### 예상 한계

- 젖산 채혈 포인트가 충분히 촘촘하지 않으면 threshold 추정이 흔들릴 수 있다.
- 프로토콜이 서로 다르면 threshold 자체가 완전히 동등 비교가 어려울 수 있다.
- 데이터 수가 많지 않으면 통합 모델은 과적합 위험이 있다.

### 이 주제가 잘 맞는 경우

- 교수님이 운동생리/스포츠과학 배경일 때
- 임상적 해석 가능성을 중요하게 볼 때
- “AI를 쓰되 해석 가능한 수준”을 원할 때

---

## 2. FatMax, crossover, lactate threshold를 이용한 대사 유연성 지표 개발

### 한 줄 설명

지방산화와 탄수화물 전환 능력을 여러 지표로 묶어, 개인의 `metabolic flexibility`를 설명하는 새 composite index를 개발하는 연구다.

### 왜 중요한가

보통 사람의 대사 상태를 `VO2max 하나`로 설명하기 어렵다.  
어떤 사람은 VO2max는 높지 않아도 지방을 오래 잘 쓰고, 어떤 사람은 threshold는 높은데 탄수화물 의존이 빠르게 올라간다.  
이 주제는 그런 복합 특성을 `하나의 해석 가능한 점수`로 만들려는 시도다.

### 연구문제

1. FatMax, crossover, LT1, LT2, RQ 1.0 이전 연료 기여율은 서로 어떤 구조적 관계를 가지는가?
2. 이들을 결합한 composite index가 단일 지표보다 개인의 대사 상태를 더 잘 설명하는가?
3. 반복 측정에서 이 composite index는 훈련 적응을 추적하는 데 유용한가?

### 가설

- 가설 1: 높은 metabolic flexibility를 가진 피험자는 FatMax가 상대적으로 높고, crossover가 늦게 나타나며, LT1 부근까지 지방 기여율이 더 잘 유지된다.
- 가설 2: composite index는 VO2max 단독보다 피험자 간 대사 차이를 더 잘 설명한다.
- 가설 3: 반복 측정에서 composite index는 훈련 적응에 따라 일관된 방향으로 변한다.

### 필요한 데이터

- CPET 기반 substrate 데이터
  - fat oxidation, CHO oxidation, RQ/RER
- FatMax, crossover, LT1, LT2
- RQ 1.0 crossing point
- body composition
  - 체중, 체지방률, skeletal muscle mass
- 반복 측정 데이터
  - 같은 피험자의 longitudinal data
- 가능하면 lactate 데이터
  - threshold 해석 보강용

### 분석방법

1. 기본 지표를 정규화한다.
   - FatMax power
   - Fat share before RQ 1.0
   - crossover power
   - FatMax-to-LT1 proximity
   - LT1/LT2 relative power
2. 지표 간 상관구조를 본다.
   - Pearson/Spearman correlation
   - PCA 또는 factor analysis
3. composite score 후보를 2~3개 만든다.
   - rule-based weighted score
   - PCA-based score
   - regularized regression 기반 score
4. 반복 측정에서 score가 실제 훈련 변화와 같은 방향으로 움직이는지 본다.
5. 기존 단일 지표(VO2max, LT2 등) 대비 설명력을 비교한다.

### 예상 한계

- metabolic flexibility 자체에 대한 gold standard가 불분명하다.
- 지표 weighting은 연구자 주관이 일부 개입될 수 있다.
- 논문 심사에서 “새 점수를 왜 이렇게 정의했는가” 질문을 받을 가능성이 높다.

### 이 주제가 잘 맞는 경우

- 당신처럼 실제 리포트/제품 기능으로 이어가고 싶은 경우
- “새 지표를 정의하고 검증”하는 작업에 흥미가 있을 때
- AI를 `설명 가능한 feature engineering` 쪽으로 쓰고 싶을 때

### 한 줄 판단

현재 가진 데이터와 제품 구조를 기준으로는 가장 잘 맞는 주제다.

---

## 3. 반복 CPET 데이터에서 개인별 대사 적응 궤적(longitudinal trajectory) 분석

### 한 줄 설명

같은 사람이 여러 번 CPET를 했을 때, 어떤 지표가 먼저 변하고 어떤 지표가 늦게 따라오는지를 시간축에서 분석하는 연구다.

### 왜 중요한가

실제 훈련에서는 한 사람이 한 번 검사받고 끝나는 경우보다, 여러 번 검사받으며 변화 추이를 보는 것이 더 의미 있을 때가 많다.  
이 연구는 “개선이 있다/없다”가 아니라, `개선의 순서와 패턴`을 보는 데 초점이 있다.

### 연구문제

1. 반복 측정에서 VO2max, LT1, LT2, FatMax, lactate curve는 어떤 순서로 변하는가?
2. 개인별 변화 패턴은 하나가 아니라 여러 유형으로 나뉘는가?
3. 특정 baseline phenotype이 이후 변화 궤적을 예측할 수 있는가?

### 가설

- 가설 1: 초기 적응은 VO2max보다 LT1/FatMax 같은 submaximal 지표에서 먼저 나타난다.
- 가설 2: 피험자의 baseline 대사 특성에 따라 변화 궤적 유형이 다르다.
- 가설 3: 반복 측정이 있는 집단에서는 단일 시점 지표보다 `trajectory feature`가 상태 변화를 더 잘 설명한다.

### 필요한 데이터

- 동일 피험자의 반복 CPET
  - 최소 2회, 가능하면 3회 이상
- 호흡가스 및 substrate 지표
  - VO2max, LT1, LT2, FatMax, crossover
- 젖산 데이터
  - 반복 측정 시 lactate curve
- 피험자 프로필
  - body composition, training level
- 테스트 간 시간 간격
  - days since previous test

### 분석방법

1. `subject x time` 형태로 snapshot table 정리
2. 각 지표의 absolute change, relative change, slope를 계산
3. mixed-effect model 또는 growth curve model로 시간 효과를 본다.
4. trajectory feature를 만든다.
   - change velocity
   - early responder / late responder
   - metabolic shift pattern
5. 피험자를 trajectory pattern에 따라 군집화하거나 rule-based subtype으로 분류한다.

### 예상 한계

- 반복 측정이 충분히 많은 피험자가 적을 수 있다.
- 측정 간 기간이 불규칙하면 longitudinal 해석이 어려워진다.
- 훈련 내용, 식이, 컨디션 같은 외생 변수를 충분히 통제하기 어렵다.

### 이 주제가 잘 맞는 경우

- 반복 제출하는 집단 데이터가 꾸준히 쌓이고 있을 때
- snapshot/feature table을 이미 만들어 둔 현재 시스템을 논문에 활용하고 싶을 때
- “한 번의 검사”보다 “변화 패턴”을 더 중요하게 보고 싶을 때

---

## 4. 호흡가스 + 심박 + 파워로 혈중 젖산 반응을 추정하는 surrogate model

### 한 줄 설명

젖산을 매번 채혈하지 않아도, CPET 중 수집되는 호흡가스/심박/파워 정보만으로 젖산 반응을 얼마나 잘 추정할 수 있는지 보는 연구다.

### 왜 중요한가

이 주제는 가장 “AI다운” 느낌이 있다.  
현장에서 젖산 측정은 번거롭고 비용이 들기 때문에, 만약 surrogate model이 어느 정도 맞아준다면 검사 프로세스를 단순화할 수 있다.  
다만 가장 조심해야 할 주제이기도 하다. “대체 가능하다”보다 “어디까지 근사 가능한가”로 잡아야 안전하다.

### 연구문제

1. 호흡가스, 심박, 파워, 시간축 정보만으로 stage별 lactate 값을 추정할 수 있는가?
2. surrogate model이 lactate threshold 구간의 변곡점을 어느 정도 재현할 수 있는가?
3. 개인 맞춤형 보정(subject-specific calibration)이 있으면 성능이 얼마나 개선되는가?

### 가설

- 가설 1: VO2, VCO2, VE, HR, power, RER를 사용하면 stage별 lactate를 유의미한 오차 범위 내에서 추정할 수 있다.
- 가설 2: 개인별 baseline calibration을 추가하면 일반 모델보다 성능이 개선된다.
- 가설 3: 절대 lactate 수치 예측보다 `threshold zone 분류`가 더 안정적으로 가능하다.

### 필요한 데이터

- stage별 또는 시점별 lactate 값
- 같은 시점의 CPET 변수
  - VO2, VCO2, VE, RER, HR, power
- protocol metadata
  - stage duration, ramp type, protocol family
- 피험자 프로필
  - 성별, 체중, 체지방률, training level
- 가능하면 반복 검사 데이터
  - 개인 보정 모델 검증용

### 분석방법

1. 입력-출력 쌍을 만든다.
   - 입력: 시계열/스테이지 CPET feature
   - 출력: measured lactate
2. 비교 모델을 만든다.
   - baseline linear / ridge regression
   - tree-based model (XGBoost/LightGBM)
   - sequence model (RNN/temporal model)은 부가 실험
3. 평가 지표를 분리한다.
   - lactate absolute error
   - LT1/LT2 zone classification accuracy
   - subject-wise cross validation
4. 개인별 calibration 실험을 한다.
   - global model
   - global + subject adaptation
5. explainability를 본다.
   - SHAP, feature importance, calibration plots

### 예상 한계

- 데이터 수가 작으면 모델이 아주 쉽게 과적합된다.
- 채혈 시점이 적으면 정확한 lactate curve 복원이 어렵다.
- 모델이 숫자는 맞춰도 생리학적 해석이 약할 수 있다.
- 심사 과정에서 “실제 측정을 대체할 수 있느냐” 질문이 강하게 들어올 수 있다.

### 이 주제가 잘 맞는 경우

- 당신처럼 AI 모델링에 흥미가 클 때
- 논문에서 machine learning 색을 좀 더 강하게 내고 싶을 때
- 다만 결과를 제품에 바로 넣기보다 “연구용 surrogate”로 두고 싶을 때

### 한 줄 판단

가장 재미있고 AI스럽지만, 가장 위험도 높은 주제다.  
석사에서는 `젖산 완전 대체`보다 `threshold-aware surrogate feasibility study`로 범위를 줄이는 것이 좋다.

---

## 5. CPET-derived feature를 이용한 대사 phenotype clustering

### 한 줄 설명

CPET, substrate, threshold, lactate 지표를 이용해 피험자를 몇 가지 대사 phenotype으로 나누고, 그 군집이 어떤 생리적 의미를 가지는지 해석하는 연구다.

### 왜 중요한가

실무에서는 “이 사람은 지방을 잘 쓰는 편이다”, “이 사람은 threshold는 높은데 탄수화물 의존이 빠르다” 같은 직관적 분류가 자주 등장한다.  
이 주제는 그 직관을 데이터 기반의 phenotype으로 정리하려는 시도다.

### 연구문제

1. CPET + lactate + substrate feature를 이용하면 재현 가능한 phenotype cluster가 형성되는가?
2. 각 군집은 threshold 구조, 연료 사용 패턴, body composition에서 어떻게 다른가?
3. baseline cluster가 이후 longitudinal response를 예측하는 데 도움이 되는가?

### 가설

- 가설 1: 피험자는 무작위가 아니라 몇 가지 대사 phenotype으로 묶인다.
- 가설 2: 군집은 단순히 VO2max 고저가 아니라 `fat use`, `threshold spacing`, `lactate response`의 조합으로 구분된다.
- 가설 3: baseline cluster는 이후 훈련 적응 패턴과 연결될 가능성이 있다.

### 필요한 데이터

- CPET feature set
  - VO2max, LT1, LT2, FatMax, crossover, RQ 1.0 이전 fuel split
- lactate curve feature
  - lactate rise slope, peak lactate, threshold-adjacent lactate change
- 피험자 프로필
  - 성별, 체중, 체지방률, training level
- 가능하면 반복 측정 데이터
  - cluster stability 및 future response 해석용

### 분석방법

1. clustering용 feature table을 만든다.
2. scaling과 결측치 처리 전략을 먼저 고정한다.
3. K-means, Gaussian mixture, hierarchical clustering 같은 기본 모델을 비교한다.
4. silhouette score, Davies-Bouldin index, bootstrap stability로 군집의 안정성을 본다.
5. 각 cluster의 특징을 해석 가능한 언어로 번역한다.
6. 반복 측정이 있다면 cluster transition 또는 baseline cluster별 변화 패턴도 본다.

### 예상 한계

- 군집은 예쁘게 나와도 생리학적 의미가 약하면 논문 가치가 떨어진다.
- 데이터 수가 적으면 군집 수가 연구자 주관에 크게 좌우될 수 있다.
- 외부 검증 데이터가 없으면 “내 데이터셋 안에서만 성립하는 cluster”일 수 있다.

### 이 주제가 잘 맞는 경우

- feature engineering과 해석을 함께 하고 싶을 때
- 현재 만든 `subject_feature_sets`를 논문에 직접 활용하고 싶을 때
- 개인화 리포트나 phenotype labeling으로 확장하고 싶을 때

### 한 줄 판단

매력적인 주제지만, 석사에서는 “군집 생성” 자체보다 “군집의 의미와 안정성 검증”이 더 중요하다.

---

## 각 주제에서 AI가 기여할 수 있는 부분

### 1. LT1/LT2 통합 추정 비교

- 호흡가스 지표와 lactate 지표를 함께 쓰는 `통합 threshold estimator`를 만들 수 있다.
- 어떤 feature가 두 방식의 차이를 가장 잘 설명하는지 feature selection으로 찾을 수 있다.
- mixed-effect model, regularized model을 이용해 개인차와 집단 경향을 분리할 수 있다.

### 2. 대사 유연성 지표 개발

- PCA, factor analysis, regularized regression 같은 차원축소/가중치 학습이 핵심 기여 포인트다.
- 반복 측정 데이터가 쌓이면 score update rule을 학습형으로 보정할 수 있다.
- explainability를 통해 score가 어떤 입력 변수에 민감한지 보여줄 수 있다.

### 3. 반복 측정 longitudinal 분석

- time-series feature engineering이 중요하다.
- 단순 전후 비교가 아니라 change velocity, momentum, delayed response 같은 파생변수를 만들 수 있다.
- early responder detection, future response prediction 같은 예측 실험으로 확장 가능하다.

### 4. lactate surrogate model

- 가장 직접적인 AI 주제다.
- 회귀, tree-based model, sequence model을 비교하면서 surrogate 가능성을 정량화할 수 있다.
- subject-specific calibration, uncertainty estimation, SHAP 기반 해석이 핵심 기여 포인트다.

### 5. phenotype clustering

- 비지도학습 자체가 중심이다.
- clustering, dimensionality reduction, cluster stability analysis가 핵심 분석 도구가 된다.
- 단순 군집 생성보다 “해석 가능한 군집 라벨링”과 “향후 변화 예측 연결”까지 가면 AI 기여가 분명해진다.

---

## 다섯 주제 요약 비교

| 순위 | 주제 | 강점 | 약점 | 추천도 |
|---|---|---|---|---|
| 1 | LT1/LT2 통합 추정 비교 | 해석 쉽고 논문 구조 안정적 | 새로움이 상대적으로 약할 수 있음 | 매우 높음 |
| 2 | 대사 유연성 지표 개발 | 현재 데이터와 제품에 가장 잘 맞음 | 점수 정의의 타당성 설명 필요 | 매우 높음 |
| 3 | 반복 측정 longitudinal 분석 | snapshot/feature 구조와 잘 맞음 | 반복 측정 수가 부족하면 약함 | 높음 |
| 4 | lactate surrogate model | AI 느낌이 강하고 매력적 | 과적합/임상 설득력 문제 | 중간~높음 |
| 5 | phenotype clustering | 개인화 전략으로 확장 가능 | 군집 안정성과 해석 타당성 확보가 어려움 | 중간~높음 |

---

## 개인적인 추천

당신이 4번을 끌린다고 했기 때문에, 현실적인 석사 설계는 아래 세 가지 중 하나가 좋다.

### 옵션 A

`메인 논문 주제는 2번(대사 유연성 지표 개발)`으로 가고,  
부가 실험으로 `4번(lactate surrogate)`를 exploratory analysis로 넣는다.

장점:

- 메인 메시지가 안정적이다.
- AI 실험을 넣되 논문 전체를 과도하게 위험하게 만들지 않는다.

### 옵션 B

`4번`을 메인으로 하되, 제목과 범위를 아래처럼 줄인다.

> CPET-derived respiratory and power features를 이용한 혈중 젖산 반응 surrogate model의 가능성 평가

즉,

- “대체 모델 개발”이 아니라
- “가능성 평가와 한계 분석”으로 잡는 것이다.

이렇게 해야 석사 논문으로 방어가 훨씬 쉬워진다.

### 옵션 C

`5번 군집화`를 메인으로 하고, `2번 대사 유연성 지표`를 cluster 해석 변수로 넣는다.

장점:

- 지금 만든 `snapshot/feature` 구조와 매우 잘 맞는다.
- 개인화 리포트나 phenotype labeling으로 확장하기 좋다.

주의:

- 군집 수를 예쁘게 만드는 것보다, 그 군집이 무엇을 의미하는지 설명하는 것이 더 중요하다.

---

## 다음 단계 제안

다음 단계에서는 아래 중 하나로 바로 구체화할 수 있다.

1. 위 5개 중 `최종 1~2개`를 골라 실제 논문 제목 초안 작성
2. 각 주제별 `연구모형도`, `변수표`, `통계 분석계획서` 초안 작성
3. 지도교수 상담용 `2페이지 제안서` 형태로 요약
