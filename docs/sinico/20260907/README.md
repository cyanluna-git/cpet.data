# 2026-09-07 sinico 자료 정리

이 폴더에 들어온 5개 파일을 전부 열어서 읽고 정리한 문서다. 다섯 자료는 서로 다른 물건처럼
보이지만 실제로는 **하나의 시스템을 다섯 층위에서 찍은 스냅샷**이다 —
논문(왜 이렇게 만들었나) · 온톨로지(무엇을 모델에 넣나) · 리포트 생성기(측정을 사람에게 보이나) ·
코칭 폐루프(처방을 실제로 돌리나) · 로스터 현황(현장에서 실제로 무슨 일이 일어나나).

| 파일 | 종류 | 크기 | SHA-256 (앞 16) |
|---|---|---|---|
| `Manuscript_R5.docx` | 학술 원고 (영문, 약 12,100 단어) | 796K | `167a3e5b7bdb0938…` |
| `FZI 32지수 온톨로지.webarchive` | Claude 아티팩트 저장본 (HTML) | 2.8M | `310e65f1eb0baf29…` |
| `argo_easy_report .pyz` | Python zipapp (단일 실행 파일, 8.5K 줄) | 252K | `b947a8062040aed9…` |
| `zelia_coach.zip` | 코칭 폐루프 소스 트리 (Python) | 768K | `88c9d0f249783807…` |
| `Roster_Status_2026-09-07.html` | 로스터 운동 현황 리포트 | 56K | `69cf0775603557bd…` |

> ⚠ **PHI 주의.** `Roster_Status_*.html` 은 실명·측정값을 담고 있고 문서 하단에 "외부 공유 금지"가
> 명시돼 있다. `argo_easy_report.pyz` 자체에는 대상자 자료가 없지만(코드·템플릿·CSS·Chart.js 만)
> **산출되는 HTML 에는 실명과 측정값이 들어간다**. `zelia_coach` 는 실제 선수 ID·API 경로를 포함한다.
>
> 이 저장소의 `origin` 은 **공개(public) 리포지토리**다. 따라서:
> - 위 표의 **원본 5개 파일은 git 에 추적되지 않는다** (`.gitignore` 로 제외). 같은 폴더에 파일로만 존재한다.
> - **이 문서 안의 선수 실명은 전부 `선수 A`~`선수 R` 로 익명화**했다. 대조표는 만들지 않았다 —
>   실제 이름이 필요하면 원본 `Roster_Status_2026-09-07.html` 을 직접 열어야 한다.
> - 논문 저자명은 공개 학술 저자표기이므로 그대로 둔다.

---

## 1. Manuscript_R5.docx — 한계요인 우선(limiter-first) 처방 엔진 논문

**제목**: *A Limiter-First, Evidence-Governed Exercise Prescription Engine: Development Findings,
the Architecture They Forced, and a Falsifiable Validation Framework*
**저자**: Yongdoo Park (고려대 의대 의공학교실). 초안 R5 — 2026-09-01 회람본.

### 논문이 주장하는 것과 주장하지 않는 것

주장하지 **않는** 것을 먼저 못박아 둔 논문이다. 자동 처방·근거기반 처방·다변량 생리 모델링은
전부 선행기술로 돌리고, 임상 유효성·안전성 우위·성능 우위는 명시적으로 주장하지 않는다.
주장하는 것은 하나 — **엔진의 각 설계 계약(contract)이 개발 중 실제로 반증된 결과에서 강제된 것이며
그 유래가 추적 가능하다**는 점.

### 데이터 (§2.2)

| 코퍼스 | 내용 |
|---|---|
| Coach A | 처방 세션 107건 / 선수 3명 / 153 athlete-days. 분모 3종을 따로 선언 — 107(처방) · 103(세션부하 산출가능) · 100(스텝구조 완전). FTP 앵커 304 / 243 / 152 W, 프로그램 12 / 6 / 4주 |
| Coach B | 워크아웃 파일 200개 → 바이트 유일 159, 구조 유일 159, 총 270.8 h. 메인세트 강도 해석 가능 117/159 |
| 보조 | CPET 75건(2명) · 대사 프로파일 리포트 148건 · 수행 활동 파일 20건 |

두 코치 코퍼스는 **닫혀 있다** — 개발 중 코치 접근이 종료돼 전향적 코치 대 엔진 비교가 불가능하다.

### 6개 개발 발견(D1–D6)과 그것이 강제한 계약

| # | 기각된 대안 | 발견 | 강제된 계약 |
|---|---|---|---|
| **D1** | 전문가 처방 = 개루프 캘린더 정책 T, 잔차 r 이 전문성의 유일한 담지자 | 개루프 모델 out-of-sample **R² = −0.503**. 동일 규모 합성 세계 30개는 0.36 (0.17–0.55) → 표본 탓 아님. 그러나 **짝지은 합성 세계 40개에서 상태의존 0.777 vs 비의존 0.774** — 개루프 적합도는 둘을 구분 못 한다 | 잔차 기반 정책 식별 전략 **철회**. 코치 코퍼스는 `HISTORICAL_TEMPLATE_PRIOR` 로만 진입 — 형태·반복구조·회복배치·용량범위만 제공, 정책은 학습하지 않음 |
| **D2** | 두 코치의 pyramidal vs polarized 대비 = 훈련 철학 차이 | 강도분포는 사실상 동일(91.4:8.7 vs 91.6:8.4). 대비 전체가 **측정된 적 없는 75% 컷포인트** 하나에서 나왔다. 3방향 삼각검증이 **78–85%** 로 수렴 — 처방밀도 골짜기 83%, CPET P@VT1:P@VT2 중앙값 0.816, 대사리포트 하한 80%. 75%는 밀도 **최대점**(local/mean 11.77)에 놓여 있었다. 경계를 75→80% 로 6%p 옮기자 한 선수 Z3 점유율이 **31.4% → 1.9%** (48%p 스윙) | 앵커는 **가중치가 아니라 게이트**. P@VT1 미측정 시 경계는 78–85% 밴드로 보고하고, 그 안의 점추정을 요구하는 후보는 생성 자체가 막힌다 |
| **D3** | 인터벌 구조가 선수별로 설계된다 | 분모를 **선수 내 주간변동**으로 바꾸자 4축 중 3축에서 선수 간 차이가 더 작았다 — 반복수 0.40 · 워크길이 0.67 · 총시간 0.66 · 강도 1.51. 한 세션은 3명 모두 사실상 동일(20×1.8분, 70분, FTP 1% 이내) | 개인화를 3층으로 분리 — L1 앵커 · L2 주간 볼륨 · L3 세션별 반응추종. **L3 는 기능이 아니라 미해결 역량 공백으로 선언** |
| **D4** | 강도분포 라벨이 주 판별자 | 경계에 독립인 판별자를 찾자 **세션 순도**가 갈렸다 — 다중타깃 세션 25.3–26.3% vs 3.1–3.8%(약 7배), 키셋 전 6분 초과 오염 10.1–21.1% vs 0.0%, 평균 순도 0.81 vs 0.97. 75/80/83 어느 경계에서도 안정 | 세션 구성 정책 10규칙이 정확히 3기능만 소유 — 주타깃 단일성 · 구조후보 스크리닝 · 오염 가드. 패밀리 선택·용량 예산에는 권한 없음 |
| **D5** | 과거 결론 3건이 유효하다 | 전부 **베이스라인 없는 관찰의 산물**로 철회. (a) 반복 피크 블록 = 날짜까지 바이트 동일한 파일 중복 → 코퍼스 113→107 (b) 훈련 철학 = D2 의 경계 문제 (c) 선수별 설계 = D3 의 분모 문제. 더해서 하드코딩 상수 — 라이브러리 크기 148이 어떤 계산값과도 불일치(재계산 159), 존점유 배열 7개 중 1개만 재현, `(이름, 총시간)` 키 중복제거 로더가 서로 다른 3개 메인세트 강도를 하나로 뭉갬 | 프로베넌스를 **모듈이 아니라 개별 필드·규칙**에 부착. 출처 미확정 규칙은 `PENDING_AUDIT` 로 격리. 철회는 supersedes-with-reason 으로 기록. 중복탐지·분모선언·원본 재계산은 상시 게이트 |
| **D6** | 활동 파일이 있으니 수행을 분석할 수 있다 | 활동 파일 20개는 있었지만 처방기록과 겹치는 (선수, 날짜) 쌍이 **0**. 파일의 존재와 쌍의 존재는 다른 사실이다 | 처방 인스턴스에 불변 ID 부여, 재생성 금지, export→delivery→execution→pairing 전 구간 보존. 페어링 3단 사다리로 학습 권한 게이팅 |

### 구현된 결정 아키텍처 (§3.2)

- **4개 결정 질문의 분리** — 무엇을 처방할까 / 그 후보가 허용되는가 / 왜 그렇게 결정했나 / 수행 후 무엇을 배워도 되는가. 모듈이 "숫자가 좋아서" 권한을 얻는 것을 막기 위한 구조.
- **4축 처방 좌표계** — 강도 uS · 워크대회복 밀도 uR · 토크 uτ · 용량. 회복축은 워크-레스트 구조에서만 유도(강도 가중 유도판은 r = 0.978 공선성 또는 스프린트 불변성 위반). 토크는 좌표만 추가했을 때 케이던스 잔차가 0.991 → 0.75–1.00 으로 **악화**했고, 4-basis 분해 재구축 + 독립 토크 판정을 만든 뒤에야 0.000 이 됐다. → *좌표계에 축을 더하는 일과 결정구조에 축을 더하는 일은 별개의 작업이다.*
- **한계요인 해소** — `Gap = Demand − State`. 가장 큰 갭도, 가장 낮은 점수도 자동으로 한계요인이 아니다. 주 한계요인 = **개입 시 가장 많이 개선될 변수**(lowest-metric fallacy 회피). 하드 적격성은 Layer 0 게이트이고 절대 보상 가능한 효용항으로 변환되지 않는다. 한계요인→세션종류 1:1 고정 매핑 금지. 남는 것은 gate-then-Pareto.
- **과제 요구 = 라벨이 아니라 지문(6축)** — 지속시간 · 강도분포 · 결정구간(종류+위치분율) · 토크/케이던스 · 내구성 · 에너지 물류. 이벤트 라벨은 기본값 제공 프리셋으로만 생존. 미지 축은 중립값 대체 금지 → 게이트 발동.
- **6종 출처 클래스** — `PEER_REVIEWED_LITERATURE`(자격/제한/거부) · `MEASURED_EMPIRICAL`(허용 인스턴스 캘리브레이션) · `SYSTEM_SAFETY_CONSTRAINT`(하류 약화 불가) · `DEVELOPER_AUTHORED`(선언 필수) · `HISTORICAL_TEMPLATE_PRIOR`(형태·용량범위 prior 만) · `CLOSED_LOOP_UPDATED`.
- **근거 자격판정 실측** — 후보 규칙 12건 → qualified 1 · restricted 5 · abstained 4 · 미확인 4번째 코드 2. 기권 4건은 결함이 아니라 **지식베이스 커버리지 측정**(당시 코칭실무 10건, 훈련효과 0건). 기권율과 자격/제한율은 다른 질문에 답하므로 합산 금지.
- **4계정 부하 원장** — 외부 일 · 자극 벡터 · 내부 부하 · 예측 회복비용. 단일 점수 금지 이유 두 가지: 인터벌 워크분 합계를 주간 부하로 제시했더니 +57 / +213 / +460% 의 허위 스윙이 나왔고, HR 가중 단일 채널은 표현형에 중립적이지 않아 약 40% 과소추정이 관측됐다. 보고 금지 3항 — 워크분 합계를 주간 부하로 / 단일 스칼라 부하 점수만으로 / RPE 단독.
- **페어링 3단 사다리** — append 는 무조건, 평가는 exact 또는 probable, **행동·캘리브레이션·학습은 exact 만**. 이벤트 클래스도 둘로 분리: 일반 세션 관찰 이벤트는 한계요인을 재정렬할 수 **없고**, 사전등록된 재검사/프로브(limiter evaluation event)만 활성화·비활성화·재순위를 할 수 있다.
- **결정 원장 + 결정론적 재생** — 선택되지 **않은** 후보까지 저장한다(사후 ablation 을 위해). 재생 가능성은 타당성이 아니지만 해석 가능한 검증의 전제조건.

### 검증·결함 (§3.3)

- 처방 컨트롤러 **22 모듈 · 247/247 테스트 통과**. 프로모션 게이트 결과 **16 unchanged / 3 intentional tightening / 0 loosening / 0 safety leak**. loosening 경로는 계약 증거가 0이므로 검증된 것으로 읽으면 안 되며, 잠정 검증기는 loosening 을 자동 승인이 아니라 수동 리뷰로 캡한다.
- **결함 12건 등록부**(6건 외부 코드리뷰, 6건 내부) — 각 항목이 재발하는 실패 *부류*라서 기록됐다. 대표 교훈:
  - 게이트는 **인식된 실패**가 아니라 **인식 못 한 입력**에서 닫혀야 한다(오타 값이 자동승인으로 통과).
  - 차원 가드는 호출부가 아니라 벡터 연산 안에 있어야 한다 — 호출부를 하나씩 막으면 새 호출자마다 구멍이 다시 열린다.
  - **검증은 자신이 검증할 출력을 소비하면 안 된다**(loosening 정당화가 분류기 판정을 읽던 순환 검증 → 원시 처방값과 정책 스냅샷에서 독립 재계산, 음성테스트 8/8 통과).
  - 임계값의 중복 구현은 값이 둘인 임계값이다(비교 함수 두 개가 3% 경계에서 부동소수점만으로 갈라져 6패밀리 중 5개를 쪼갬).
  - 넓은 예외 처리는 증상을 원인에서 떼어 놓는다. 조용한 테스트 하네스는 조용한 결함을 만든다.
- **세션 가드 시뮬레이션** — 정상 내 드리프트 항이 없는 기대 HR 모델은 240세션에서 **오경보 240건**. 1 Hz 잔차에 연속초 규칙은 필터가 아니라 도달 불가능한 논리곱(사전탐지 0.000, 30초 평활 상수 필수). 경고 임계값 ≠ 행동 임계값(리드타임 774 s / 348 s / 탐지율 0.325). **파워를 읽는 트리거는 리드타임을 주장할 수 없다**(HR-only 348 s vs HR+파워 사전탐지 0). 온도 생략 시 watch 상태 위양성 0.000 → 0.142.

### 검증 프레임워크 (§4) — 6가설 × 3플랫폼 사다리

H1 한계요인 식별가능성 · H2 증분 결정가치 · H3 목표자극 도달 · H4 근거거버넌스 가치 ·
H5 통제학습 안정성 · H6 기권 품질. 각 가설은 **반증 가능한 가장 싼 플랫폼**에 배정되고
낮은 단계에서 기각되면 위 단계 지출을 멈춘다.

- **P1 Replay** — 원장 재생 + 합성 코호트, 반사실 비교, 반-합성 섭동(활동 누락·중복 업로드·지연 보고·센서 노이즈·모호한 페어링 등)
- **P2 Shadow** — 10–20명 8–12주 파일럿, 제안은 기록만 하고 적용하지 않음
- **P3 Acute 2×2** — 컴파일러 전용 자극 예측 검증

베이스라인 3종(존 적응형 / 부하+레디니스 / 생리·스트레인 인지)과 **ablation 9종**을 미리 정의.
보고는 DECIDE-AI(의사결정지원 워크플로) + TRIPOD+AI(개별 예측 서브모델) 기준을 따른다.

### 제출 전 미해결 (원고 말미 명시)

1. §3.2.6 — 자격판정 export 의 4번째 결과 코드가 VETO 인지 소스 스키마로 확인
2. 참고문헌 26 — 96.5% 검사율과 59/34 응답수는 전문(full-text) 수치라 초록 수준 기록으로는 미확인
3. §2.2/§3.1.1 — 중복탐지 게이트 추가 후 재계산된 103 수치 재확인
4. 저자/소속/CRediT/펀딩/이해상충, 데이터·코드 공개 범위, Supplementary Methods(정확한 out-of-sample 분할·시드 목록·시뮬레이터 파라미터·밀도추정 대역폭·최대노력 조작적 기준·세션 순도 점수의 수학적 정의)

---

## 2. FZI 32지수 온톨로지 (.webarchive)

Claude 아티팩트(`claude.ai/code/artifact/35391a58-…`)를 Safari 로 저장한 것. 실제 내용은
iframe 안에 있고, 본문은 `FZCare · ontology v0.1.0 · source-reconciled` 로 표기돼 있다.

### 핵심 계약

32개 지수를 **순서가 고정된 32칸 레지스터**로 직렬화해 베이스 모델에 넘긴다.
핵심은 지수 목록이 아니라 **게이트** — 각 슬롯 산식이 어느 정도로 확정됐는지가 그 값이
모델에 들어갈지를 결정한다. 특허 기준본 2건 + `engine_spec.json` 대조로 미결 산식 13건을 확정,
통과 슬롯이 **23 → 28** 로 늘었다.

규모: Metric 38(core 32 + 보조 6) · formula/method 47 · variable 27 · 원문 발췌 59 · 출처 파일 19(SHA-256 고정).

### 파이프라인 (6단계, 각 단계는 앞 단계 산출물만 읽는다)

```
원문 19종(SHA-256) → catalog.json → ontology.ttl/.jsonld(dependsOn 그래프)
  → model_input.schema(고정 32슬롯, draft 2020-12) → 검증기(단위·method·provenance 강제)
  → X(8,32) float32 + mask bool (결측 NaN)
```

**저장된 수식 문자열은 어디서도 실행되지 않는다** — 지식 표현과 계산의 분리가 설계 전제.

### status 게이트

| status | 수 | 처리 |
|---|---|---|
| `documented` | 28 | 통과 (정본 대조로 23→28) |
| `provisional` | 3 | `vlamax_indirect` · `fdi` · `mvdf` — `--allow-provisional` 로만 |
| `underspecified` | 1 | `map_wkg` 차단 — t_vo2max 와 load alignment 규칙이 어느 정본에도 없다 |
| `conflicted` | 0 | `delta_fat` 이 특허로 확정되며 해소. 구 정의는 변형으로 강등해 계속 차단 |

차단된 값은 0으로 채우지 않고 **null + mask=0 + reason** 으로 보존한다.
기본 28/32 관측, `--allow-provisional` 시 31/32.

### 32 슬롯 (position 0–31, 이 순서가 계약)

`00 vo2max` · `01 map_wkg` · `02 o2pulse` · `03 vlamax_indirect` · `04 peak_la` · `05 delta_la` ·
`06 vt1_power`★ · `07 vt2_power`★ · `08 vo2_at_vt2` · `09 lt1_power` · `10 lmp_lt2_power` ·
`11 mdc_energy`★ · `12 mdi_fat`★ · `13 lifp` · `14 delta_fat`★ · `15 fdi` · `16 fatmax_rate` ·
`17 fatmax_pct` · `18 m_lo`★ · `19 oxi_pct` · `20 gly_pct` · `21 pcr_pct` · `22 ve_vco2_nadir` ·
`23 ve_vo2_nadir` · `24 vdi`★ · `25 m_hi`★ · `26 mdi_drift`★ · `27 atf` · `28 mvdf` ·
`29 rer_terminal` · `30 ve_peak` · `31 engine_size`  (★ = 정본 근거, 9개)

### 정본 대조로 확정된 것

| 지점 | 확정 | 근거 |
|---|---|---|
| MDC 이름충돌 | 역치 분율은 **ATF** 로 명명, 종래 MDC 표기 폐기. P1 의 MDC 는 이중경계 총에너지로 별도 유지 | P2 약어 · P1 §6.5 |
| ATF 단위 | `ATF = VO₂@VT2 / VO₂max` 무차원. 엔진의 3/50=0.06 원값 나눗셈은 단위 오류 | P2 §3.2.2 |
| VT2 검출 | 3단 cascade — M1 RQ>1.00 연속5(초기 RQ<0.80 **또는** 상승폭<0.30 이면 배제) → M2 VE/VCO₂ nadir 후 연속3 상승 → M3 V-slope 는 **합의 확인용** | P2 §3.2.2 |
| VT1 검출 | VE/VO₂ 최저점 이후 첫 지속상승 → RER 0.85 이상 지속 시작 → 호흡수 급상승 시작 | P1 §6.10 |
| VO₂max 판정 | 3기준 **모두(AND)** — RER≥1.10(마지막 60초 중앙값) · HR≥0.95×(208−0.7×연령) · ΔVO₂<150 mL/min plateau. **HTML 의 OR 기준 폐기** | P1 §6.1 |
| MDC 적분식 | `∫(FatE+CHOE)dt / 체중` — **기질 합**이며 Weir EE 적분이 아니다 | P1 §6.5 |
| 에너지 환산 | 지방 **9.75** kcal/g · 탄수화물 4.00. 종래 9.0 폐기 → MDC 평균 **+5.17%** 변동 | P1 §6.2 |
| CHO 계수 | **4.585 / 3.226** 확정. `physiology.py` 의 4.210/2.962 는 엔진 변형으로만 보존 | P1 §6.2 |
| ΔFat | `ΔFat = Fat_Lo − Fat_Hi`. 기존 `m_hi − m_lo` 는 **부호가 반대**라 legacy 강등 | P1 §6.6 |
| MDI 분모·집계 | Fat_Hi 는 **비율의 평균**, 분모는 기질 합. Weir EE 분모 아님. VT2 검출 불요 | P1 §6.4 |
| MDI drift 창 | plateau = 검사 **35~75%** 구간 90퍼센타일 (post-VT2 아님) | P2 §3.2.3 |
| dual-cut 경계 | 하한 `max(30%VO₂peak, 180초)`, 상한 **FSL** = RER≥1.00 **AND** 강도≥50%VO₂peak 연속5표본. 평활지연 (창−1)/2 보정, 90%VO₂peak fallback | P1 §6.3 |
| VDI 스케일 | **10⁷ 확정** — 특허의 10⁴ 가 아니라 `engine_spec.json` 이 정본. slope 는 15–85% 등탄산 완충구간 R²≥0.90, raw_range 5,000~40,000 | engine_spec |

### 미해결

- `WOxi·WGly·WPCr`, 0.0627 — 해당 특허 P4(에너지 시스템 분리)가 **HWP 평문 추출 실패**(509,430자 중 한글 0자). 한글 프로그램에서 변환 필요.
- VLamax · LT1/LT2/MLSS · MAP — 특허 기준본에도 engine_spec 에도 없다.

### 설계상 함정 두 가지 (문서가 직접 경고)

1. **VDI 이중 detrend.** slot 24 는 raw 램프 스냅샷만 싣는다. 하류 Durability Index 파이프라인이 이 채널을 capacity anchor 에 LOWESS detrend 해서 체력과 직교하는 잔차를 만든다 — 사후 상관 확인이 아니라 **구성 시점에 직교성을 강제**하는 방식. 그 잔차가 같은 슬롯으로 돌아오면 이중 detrend 가 된다. raw `vdi` 와 `vo2max` 를 같은 32칸에 함께 넣으면 모델이 DI 가 제거한 capacity 교란을 다시 학습할 수 있다. 정속(CWR) 시간영역의 `VDI_CWR` 도 "MVDF VDI ≠ VDI_CWR, 서로 다른 축" 이므로 입력 금지.
2. **Derived-from 사슬.** 32칸이 독립 측정 32개가 아니다. 에너지 3분율(`oxi_pct`/`gly_pct`/`pcr_pct`)은 core 슬롯이지만 값은 비-core 보조 지수(WGly·WOxi·WPCr·WTotal)에서 나오고, WGly 는 다시 core 슬롯 `delta_la` 로 거슬러 올라간다 — **4단 사슬**. 세 분율 합이 항상 100%인 것도 이 구조 탓. 이 구간은 어느 정본도 다루지 않아 그대로 남았다.

또한 슬롯 ID 를 유지한 결과 `mdi_fat` 과 `m_hi` 가 같은 구간을 다른 집계로 계산하며,
검증기가 두 값이 겹치지 않는지 확인한다. **모든 대상자 수치는 합성 fixture 이고
베이스 모델 추론은 수행되지 않았다** (`model_inference_executed: false`).

---

## 3. argo_easy_report .pyz — ARGO 쉬운리포트 생성기

Python 3.9+ 표준 라이브러리만으로 도는 **단일 실행 파일**(zipapp). 총 8,485줄.

```bash
python3 argo_easy_report.pyz all <배치폴더> -d <출력폴더>
python3 argo_easy_report.pyz analyze <배치폴더> -o <argo.json> [--sheet 이름] [--lactate x.json]
python3 argo_easy_report.pyz report <argo.json> -d <출력폴더>
```

### 입력 배치 폴더

| 파일 | 조건 |
|---|---|
| BxB 가스 xlsx | 파일명에 `CPET BxB` 포함이어야 인식 |
| ARGO 젖산 시트 xlsx | 위 조건에 안 맞는 xlsx 를 시트로 간주 |
| 심전도 RR csv | 선택 — 없으면 자율신경 탭이 「산출 불가」로 접힌다 |
| 자전거 .fit | 선택 — 가스 파일에 파워 채널이 없으면 여기서 끌어온다 (`fitparse` 필요) |

**가드**: 한 배치에 2명 이상이고 스텝 HR 이 비슷하면 시트 자동배정이 **멈춘다**(남의 젖산이 실리는 것 방지).
그때는 사람별 폴더 분리 + `--sheet` 로 명시 배정.

### 구조

```
__main__.py
argo_easy/     lmt_analysis.py (1761) · easy_report.py (2156) · lmt_report.py (1401)
               fitpower.py · svgplot.py · lt_estimator_v3_port.py
               argo_easy_tpl/*.html (16종) · argo_easy_style.css · vendor/chart.umd.min.js
fzi_engine/    registry.py · resolver.py · context.py · provenance.py · state0.py
               modalities.py · protocols.py · lt_estimator.py · uncoupling.py
               indices/ confirmed.py · durability.py · lactate_thresholds.py · stubs.py
```

### 리포트 10탭 (2026-08-29 수기 산출물을 원자 단위로 분해해 재현)

`00 한눈에 보기` · `01 검사 개요·핵심` · `02 1단계 계단검사` · `03 2단계 최대검사` ·
`04 경계선(역치)` · `05 연료 사용` · `06 에너지·자율신경` · `06b 장기 추적 ★` ·
`07 운동 처방` · `용어 사전`

컴포넌트 원자: card / trow / kpi(+easy) / note(b·y·r·g) / badge / qa / score_row / agebar /
chartbox / chip / h2·h2-sub·h3. 차트 14종(Chart.js 인라인).

### 두 개의 규율이 코드에 박혀 있다

- **환산 규율** — 펜타곤 5축 점수·체력나이·백분위 막대는 *이해를 돕는 참고 환산*이다. 측정으로 확정된 값은 「또래 상위10% 대비 달성률」과 「자기 최고치 대비 유지율」 **둘뿐**이고 나머지는 문헌 구간을 100점으로 편 것 — 리포트 본문에도 그렇게 명시한다.
- **없는 값은 지어내지 않는다** — 종단 탭은 `ARGO_DATA_DIR/cpet/processed/cpet_summary.csv` 가 있어야 나오고, 없으면 「단일 측정」으로 접힌다. RR csv 가 없으면 자율신경 탭은 「산출 불가」.

### fzi_engine

`@register` 데코레이터 기반 지수 레지스트리. `IndexSpec` 에 `inputs`(의존) · `requires`(모달리티) ·
`unit` · `spec` · `tier`(MDF/MVDF/VEF/역치/에너지/VLamax/검증/running) ·
`reliability`(직접/계산/간접/실험/검증중/stub) · `doc` 를 달고, 중복 등록은 예외로 막는다.
`confirmed.py` 에 VDI · ATF · MVDF · dFat · FDI · dLa · WGly · WOxi · WPCr · WTotal ·
Oxi_pct · Gly_pct · PCr_pct · FatMax 가 등록돼 있다 — **§2 온톨로지 문서의 슬롯과 직접 대응**한다.

`state0.py` 는 **State₀ 32→5 collapse** 구현(SSOT = `Library/rules/state_pentagon/State0_spec_v2.md`).
지수 벡터 → 5도메인 좌표 `O=(z_met, z_vent, z_neu, z_rec, z_struct)` + `D_session`.
파이프라인: 방향 통일(나쁜 방향 부호반전) → 연령·성별 보정 z → 누수 보정(`z_neu ⟂ struct`, `z_rec ⟂ met`)
→ 도메인 결합(이론/앵커 가중, **도메인 간 PCA 금지**).
가드레일: **결측 축 0 대체 금지 → None + 불확실성 플래그**. 가중치는 잠정값(`WEIGHTS_PROVISIONAL = True`).

---

## 4. zelia_coach.zip — ZeLiA/ARGO 코칭 폐루프

THE Heart Lab · ZeLiA 코칭 시스템의 **지능 레이어**(측정→처방→수행→적응 폐루프).
정본 스펙은 `~/FZCare/Library/rules/coaching system.md`, 이 트리는 그 스펙의 코드화.

### 설계 원칙 (스펙 §0)

1. **생리 정확성과 순응도 분리** — "무엇을 자극(클래스)"은 고정, "어떤 형태(변이)"는 LRU 로테이션
2. **모든 결손을 보상하지 않음** — Z2/템포는 잊고, 핵심은 옮기고, 피로면 내린다
3. **객관 데이터 우선** — 주관이 아니라 수행데이터(HR·파워·EF)로 피로/과부하 판정
4. **사전 신호는 보조** — 웰니스는 주간 트렌드로만, 단독 트리거 금지. 부하 상승 = 게이팅(FRESH 요구), 하강 = 지속·코로보일 때만

엔지니어링 원칙: 상수는 `config.py` `SCHEMA_VERSION` 아래 **단일 진실원**, 순수함수,
결정 함수는 근거(notes/provenance)를 반환.

### 폐루프

```
intervals.icu (실측)
  → weekly_assess.py   측정 읽기 + 적응 결정(decide_next_week) + HTML       [읽기전용]
  → plan_adapt.py      같은 결정으로 다음주 워크아웃 실제 변형(경계 내)      [코치 승인 --apply]
  → note_upload.py     4섹션 리치 코칭노트                                   [전달]
```

핵심은 **노트와 플랜이 하나의 결정에서 나와 말과 실제가 어긋나지 않는다**는 것.

측정 쪽 루프: `CPET/FZI → 10축 [+PDC 필드보정] → weak_axes → 클래스 점수(결손×가중) →
pick_variation(LRU) → 처방(.zwo/intervals) → 수행(.fit→NP·TSS·EF) → 적응(decide_next_week) ↺`

### 모듈

| 계층 | 파일 |
|---|---|
| 코어 엔진 (`zelia/`) | `config.py`(버전드 상수·존·10축·클래스 밴딩) · `catalog.py` · `axes.py` · `rotation.py` · `adapt.py` · `recommend.py` · `plan.py` · `limiter.py` · `ceq.py` · `engine_contracts.py` · `policy_provenance.py` · `adaptation_action_ssot.py` · `evidence/coaching_evidence_v1.json` |
| 운영 스크립트 | `weekly_assess.py` · `plan_adapt.py` · `note_upload.py` · `run_weekly.sh`(오케스트레이터) · `install_cron.sh` · `reproduce_check.sh` |
| 거버넌스 | `observation.py` · `identity_gate.py` · `execution_pairing.py` · `prescription_lineage.py` · `mod_ledger.py` · `response_evidence.py` · `activation_projection.py` · `input_manifest.py` · `system_snapshot.py` · `snapshot_replay.py` · `pipeline_outcome.py` · `delivery.py` · `dispatch.py` |
| 테스트 | 24개 파일 — `test_golden_replay` · `test_cross_ledger_replay` · `test_crash_matrix` · `test_policy_provenance` · `test_identity_gate` · `test_execution_pairing` · `test_ceq` / `test_ceq_engine` · `test_limiter` 등 + `golden_world.py` · `crash_child.py` · `replay_child.py` |

데이터 배선: 백엔드 풀 = `workout_catalog_2000.csv` (2000개, 12 카테고리).
자극 클래스는 로드 시 도출(`intervals_icu_text` 파싱 → work% · 렙길이 → `{cat}|I{밴드}|D{밴드}`).
현재 **92 클래스**(스펙 87 근사, 데이터 도출), 싱글톤 2.

### 논문 아키텍처와의 1:1 대응

| 논문 계약 | 구현 |
|---|---|
| limiter-first, 미측정 시 abstain | `limiter.py` — DECIDED/ABSTAIN, `REQUIRED_STATE_FIELDS` 8개, PRIORITY 7단계(`Doubly_limited` → `Base_thin` → `Engine_low` → `Durability_gap` → `VO2max_ceiling` → `Threshold_base` → `High_VLa`). *"Missing measurement is never treated as absence of a limiter"* |
| 근거 자격판정 (qualified/restricted/abstained/veto) | `ceq.py` — **claim-level evidence qualification**. `decide_next_week` 의 *결정*과 선수에게 가는 *문장*을 분리하고, 문장이 근거가 허가하는 최대 표현을 넘으면 QUALIFY/REJECT, 근거가 없으면 ABSTAIN. **fail-closed** — 근거 미연결·규칙 미일치·상한 공집합은 전부 차단. 공감·지시·안전경고는 `kind="non_evidential"` 로 명시 면제하되 면제가 어휘로 고정되고 테스트가 분류 자체를 검사 |
| 프로베넌스·SSOT | `policy_provenance.py` · `adaptation_action_ssot.py` · `config.SCHEMA_VERSION` |
| 불변 인스턴스 ID · 페어링 게이트 | `identity_gate.py` · `execution_pairing.py` · `prescription_lineage.py` |
| 결정 원장 · 결정론적 재생 | `mod_ledger.py` · `snapshot_replay.py` · `test_golden_replay` · `test_cross_ledger_replay` |
| 처방 규칙 드리프트 게이트 | `scripts/prescription_laws.py` — 법칙 **56개** 레지스트리 + 드리프트 검증 (`--verify-only`) |

### 가드레일 ("적당한 선")

- **비대칭 권한** — 통증·부상·수행데이터(객관) = 강도조정 권한 / 순수 주관(힘듦·자책) = 소폭 1개만
- **프레임 보호** — 자극 축(class) 고정, 강도/형태만 완화. 블록·주기화 재작성·주 삭제 금지
- **경계** — 주당 조정 ≤2, 강도 ≥−10%, 신호 없으면 원플랜, 이미 `(ARGO조정)` 태그면 skip
- 통증이 있으면 엔진 mode 가 hold 여도 **override**(안전 우선)

### 코칭 노트 패턴 (`NOTE_PATTERN.md`, SSOT)

4섹션 필수 — ① 기본 지표(이번주 vs 지난주) ② 워크아웃 수행평가(파워·심박·EF, 세션별
`날짜·이름·분·NP(W)·평균HR·EF(+디커플링)`) ③ 선수 노트 답변 ④ 이번주 계획 + 코멘트.
`qc_note` 게이트가 4섹션·인사·서명·(활동 있으면)파워/심박 평가 포함 여부를 매 전달마다 검사하고,
누락 시 `⚠QC` 로 표시해 **품질이 조용히 떨어지는 것**을 막는다.

원칙: 사실 나열 금지(수치는 반드시 평가·해석·다음 행동과 함께) · 선수가 남긴 말은 반드시 응답 ·
통증 최우선 · 미이행을 질책하지 않고 원인·다음 행동으로 전환. 힘든 얘기엔
**① 감정적 공감 → ② 재구성/안심 → ③ 구체적 대안** 순서.

멱등: `external_id = zelia-note-{aid}-{월요일}`, 기존 `[ARGO]`/`[ZeLiA]` NOTE 삭제 후 POST.
크론은 매일 20:00 (assess + note).

### 미구현 TODO

- `profile_io.py` — CPET 리포트 → 10축 자동채움 (수동입력 제거)
- `pdc.py` — 파워커브 → 필드 축 보정. 최신성 게이트·CPET 충돌 재검 플래그. **CPET 전용 축(fatmax·mdc·efficiency·kinetics·cardiac·substrate)은 PDC 가 못 건드림**
- fresh vs 피로 파워커브(X kJ 후) → durability 필드 신호
- `intervals_io.py` — pull(활동·웰니스·파워커브) / push(캘린더 upsert 멱등)
- FastAPI 앱(§9) + SQLite + `.fit` 인제스트(NP 30s 롤링⁴·TSS·EF)
- 약한축 기반 16주 플랜 자동생성기
- TSB/HRV 밴드 50+ 코호트 캘리브레이션 (Coggan −30 바닥 미사용, placeholder 해소)

### 운영 주의

연구·코칭 프로토타입이며 임상(FZCare/IRB)은 데이터 거버넌스상 자체 서버·인증·감사로그로 분리.
intervals.icu 네트워크는 해당 환경에서 차단 — push 는 로컬 실행, API 키는 인자/환경변수로만(`~/.icu_key`).
권한이 없는 일부 선수는 403 → 제외 검토 대상.

---

## 5. Roster_Status_2026-09-07.html — 로스터 운동 현황

코치 로스터 **46명**, 2026-06-15 ~ 2026-09-07 (12주).
intervals.icu 활동 × 계획 이벤트 대조. 강도 3존 = 저(Z1-2) / 중(Z3·SS·Z4) / 고(Z5-7), **시간 기준**.

### 구간 분포 (46명)

| 구간 | 인원 | 정의 |
|---|---|---|
| 이행 | 12 | 계획 세션의 80%+ 실제 수행 — 처방이 훈련을 지배 |
| 자율 | 3 | 훈련은 하는데 계획을 안 따름 — 계획일에 다른 운동 |
| 이탈 | 11 | 계획일 다수가 무활동 — 처방 이전에 참여 회복이 먼저 |
| 관측불가 | 4 | 가시성 50% 미만 — 이행 판정 자체가 성립 안 함 |
| 미처방 | 10 | |
| 미가동 | 6 | |

### 우선 조치 (이행률과 직교 — 이행률 100%여도 과부하일 수 있다)

| 플래그 | 기준 | 해당 |
|---|---|---|
| 참여이탈 | 계획일 무활동 25일+ | **10명** — 선수 K(34일) · 선수 I(55일) · 선수 L(31일) · 선수 M(33일) · 선수 N(33일) · 선수 J(32일) · 선수 O(25일) · 선수 P(34일) · 선수 Q(50일) · 선수 R(29일) |
| 과부하 | 폼 < −25 또는 램프 > +5 | **4명** — 선수 A(−24·+5.4) · 선수 B(−32·+6.3) · 선수 C(−53·+13.2) · 선수 D(−37·+8.0) |
| 자체증량 | 페어세션 실제/계획 TSS ≥ 1.4 | **4명** — 선수 A(1.4) · 선수 E(1.52) · 선수 F(1.72) · 선수 G(1.45) |
| 고강도부족 | Z5+ < 3% 인데 주 250 TSS+ | **3명** — 선수 A(고 2%·378TSS) · 선수 E(고 1%·261TSS) · 선수 H(고 2%·369TSS) |
| 미시작 | 계획은 있고 활동 0 | **2명** — 선수 I(계획 55건 대기) · 선수 J(32건 대기) |

선수 A 은 과부하·자체증량·고강도부족 3개 플래그에 동시에 걸린다 —
이행률 100%(8/8)인데 실제/계획 TSS 1.4, 고강도 2%, 폼 −24.

### 리포트가 스스로 붙인 해석 규칙

- **[관찰] 이행률의 정의** — intervals.icu 가 계획 세션과 활동을 `paired_activity_id` 로 페어링한 비율. 같은 날 다른 운동을 하면 페어링되지 않으므로 **이행률 낮음 ≠ 훈련 안 함** → 그래서 「자율/무활동」을 나눠 실었다.
- **[관찰] 가시성** — Strava 연결 + 상세 공유제한 선수는 활동 날짜만 보이고 시간·존·부하가 빈다. 가시성 50% 미만은 별도 구간(관측불가)으로 분리했고 이들의 TSS·분포는 **과소계상**이다.
- **[추론] 계획 IF 를 같이 읽어야 하는 이유** — 양극화 처방이면 계획 IF 는 대개 60~68 에 앉는다. 계획 IF 가 74 이상인데 선수가 성실히 수행하면 결과는 **역치형**이 된다 — 이때 중강도 과다는 선수의 일탈이 아니라 **처방의 성질**이다. 「처방세션 분포」 열이 직접 증거.
- **[관찰] 실제/계획 TSS** — 1.3 이상은 자체 증량, 0.8 이하는 축소 실행. 페어링된 세션만으로 계산.
- 존 경계는 선수 본인 설정 FTP/HR 존 기준이라 **캘리브레이션 차이가 남는다**.

---

## 다섯 자료를 관통하는 것

같은 인식론적 규율이 논문·온톨로지·리포트 생성기·코칭 엔진·현장 리포트 다섯 군데에서
동일한 문장으로 반복된다. 이게 이 자료 묶음의 실질이다.

| 규율 | 논문 | 온톨로지 | 쉬운리포트 | ZeLiA | 로스터 |
|---|---|---|---|---|---|
| **없는 값을 지어내지 않는다** | 미지 축은 중립값 대체 금지 → 게이트 발동 | 차단 값은 0 채움 금지 → `null + mask=0 + reason` | RR 없으면 자율신경 「산출 불가」, 종단자료 없으면 「단일 측정」 | 결측 축 0 대체 금지 → None + 불확실성 플래그 | 가시성 50% 미만은 판정 자체를 안 함 (관측불가 분리) |
| **fail-closed** | 게이트는 인식 못 한 입력에서 닫힌다. legacy 자동 폴백 금지 → 수동 리뷰 | status 게이트가 통과·차단 결정, provisional 은 플래그로만 | 배치에 2명 이상 HR 유사 시 시트 자동배정 정지 | CEQ 근거 미연결·규칙 미일치 = 전부 차단, 통과가 기본 아님 | — |
| **분모를 선언한다** | 107/103/100 세 분모 병기, 선수 내 변동을 분모로 | 38 metric = core 32 + 보조 6 명시, derived-from 사슬 공개 | 「또래 상위10% 대비」와 「자기 최고 대비」만 측정 확정값 | 클래스 92개는 스펙 87 아닌 **데이터 도출값**으로 표기 | 이행률·가시성·실제/계획 TSS 를 각각 다른 분모로 |
| **출처 클래스를 섞지 않는다** | 6종 프로베넌스 + PENDING_AUDIT 격리 | 정본(특허·engine_spec) vs 강등된 legacy 변형 보존 | 참고 환산 vs 측정 확정값을 본문에 명시 | policy_provenance · evidence KB · template prior 분리 | [관찰] / [추론] 태그로 각 문장을 분류 |
| **예측 ≠ 관측** | 처방용량 ≠ 예측자극 ≠ 관측수행 ≠ 관측반응, 4계정 원장 | `model_inference_executed: false` 명시 | — | 결정(규칙)과 발화(문장)를 CEQ 로 분리 | 계획 IF vs 실제 IF 를 나란히 |
| **재현 가능성** | 결정론적 재생, 미선택 후보까지 저장 | 원문 19종 SHA-256 고정, 수식 문자열은 실행되지 않음 | 표준 라이브러리만, 단일 파일 | `reproduce_check.sh` 전체 자가검증, golden replay | 매 실행 원본 재계산 |

**요약**: 논문(§1)이 왜 이 규율들이 필요한지를 6개 반증 결과로 논증하고, 온톨로지(§2)가
모델 입력 계약으로, 쉬운리포트(§3)가 대상자 대면 산출물로, ZeLiA(§4)가 실행 폐루프로,
로스터(§5)가 현장 관측으로 각각 구현한다. 로스터의 "계획 IF 74 이상이면 중강도 과다는
선수 일탈이 아니라 처방의 성질" 이라는 문장은 논문 D2(경계가 대비를 만든다)와 D4(순도가 진짜
판별자다)의 현장판이다.

## 남은 작업 (자료 전체 기준)

1. **HWP 평문 추출** — 특허 P4(에너지 시스템 분리) 509,430자 중 한글 0자. `WOxi·WGly·WPCr` 과 0.0627 이 여기 막혀 있다. 한글 프로그램에서 변환 필요.
2. **`map_wkg` 산식** — t_vo2max 와 load alignment 규칙이 어느 정본에도 없어 32슬롯 중 유일한 `underspecified`.
3. **VLamax · LT1/LT2/MLSS · MAP** — 특허 기준본에도 engine_spec 에도 근거 없음.
4. **원고 제출 전 4건** — VETO 코드 매핑 확인 · 참고문헌 26 전문 수치 확인 · 103 재확인 · Supplementary Methods(시드·분할·순도 점수 정의).
5. **ZeLiA 측정 자동화** — `profile_io.py` / `pdc.py` 미구현으로 10축이 아직 수동 입력.
6. **로스터 조치** — 참여이탈 10명은 처방 이전에 참여 회복, 과부하 4명은 부하 하향, 미시작 2명(계획 87건 대기)은 전달 경로 점검.

---

*정리 기준일 2026-09-07. 원본 5개 파일은 이 폴더에 그대로 있고, 이 문서는 그 내용을 읽어 요약한 것이다.*
