# CPET 데이터 파이프라인 로드맵

> 작성일: 2026-01-16  
> 상태: Phase 1 진행 중

---

## 현황 분석

### 데이터 현황
| 항목 | 상태 |
|------|------|
| CPET_data 폴더 Excel 파일 | **73개** (14명 피험자) |
| DB에 로드된 테스트 | **0개** (아직 미로드) |
| 분석 알고리즘 | ✅ 구현 완료 |
| 업로드 API (Backend) | ✅ 구현 완료 |
| 업로드 UI (Frontend) | ⚠️ 미구현 |
| 재분석 API | ❌ 없음 |
| 정제 데이터셋 (Processed Series) | ❌ 없음 |

### 피험자별 파일 현황
| 피험자 | 파일 수 | 기간 |
|--------|---------|------|
| Park Yongdoo | 38 | 2022-10 ~ 2025-05 |
| Hong Changsun | 10 | 2024-04 ~ 2024-12 |
| Kim Dongwook | 6 | 2022-12 ~ 2024-06 |
| Seok Woochan | 4 | 2022-12 ~ 2025-01 |
| Park Geunyun | 4 | 2024-03 ~ 2024-11 |
| Kim Daesoon | 3 | 2024-06 ~ 2024-12 |
| Joo Sungjun | 3 | 2024-03 ~ 2024-12 |
| Chung Sunghoon | 2 | 2024-07 ~ 2024-08 |
| Shin Haesung | 2 | 2024-04 |
| 기타 (4명) | 4 | - |

---

## Phase 1: 알고리즘 검증 및 데이터 로드 (1일)

### 목표
- CPET_data 폴더의 73개 Excel 파일을 DB에 일괄 로드
- 분석 결과를 CSV로 출력하여 수동 검증
- 알고리즘 정확도 확인

### 작업 항목

#### 1.1 배치 임포트 스크립트 ✅
- [ ] `scripts/bulk_import_cpet_data.py` 생성
- [ ] CPET_data 폴더 재귀 스캔
- [ ] 파일명에서 피험자 매칭
- [ ] 업로드 API 호출하여 DB 저장
- [ ] 진행률 표시 및 에러 로깅
- [ ] API page_size 제한(≤100) 준수

#### 1.2 검증 리포트 생성
- [ ] `scripts/generate_validation_report.py` 생성
- [ ] 각 테스트의 분석 결과 CSV 출력
  - test_id, subject, date, VO2MAX, FATMAX, VT1_HR, VT2_HR
- [ ] 이상치 자동 감지 (예: VO2MAX < 1000 또는 > 6000)

#### 1.3 알고리즘 비교 검증
- [ ] Park Yongdoo 38개 테스트로 시계열 일관성 확인
- [ ] 동일 피험자의 FATMAX/VO2MAX 변화 추이 그래프

### 완료 기준
- [ ] 73개 파일 중 95% 이상 성공적으로 로드
- [ ] 검증 리포트 CSV 생성
- [ ] 이상치 0건 또는 원인 파악

### 안정성 메모
- 대량 시딩 시 서버가 중단되는 이슈가 있었음.
  - page_size 제한 초과(>100) 요청 시 422 발생
  - 대량 요청으로 인한 메모리/커넥션 압박 가능성
  - 시딩 시에는 --reload 비활성 권장

---

## Phase 2: 재분석 API 구현 (2일)

### 목표
- 알고리즘 변경 시 기존 데이터 재분석 지원
- 분석 버전 관리

### 작업 항목

#### 2.1 재분석 엔드포인트
```
PATCH /api/tests/{test_id}/reanalyze
```
- 요청: `{ calc_method, smoothing_window, vt_method }`
- 기존 breath_data 기반으로 재계산
- cpet_tests 테이블 업데이트

#### 2.2 분석 버전 관리
- cpet_test.py 모델에 필드 추가:
  - `analysis_version: int`
  - `analysis_params: JSON` (사용된 파라미터)
  - `analyzed_at: datetime`

#### 2.3 일괄 재분석 API
```
POST /api/admin/reanalyze-all
```
- 관리자 전용
- 모든 테스트 또는 특정 조건 필터링
- 백그라운드 작업으로 실행

### 완료 기준
- [ ] 단일 테스트 재분석 API 동작
- [ ] 일괄 재분석 API 동작
- [ ] 분석 버전 이력 추적 가능

---

## Phase 2.5: 정제 데이터셋 구축 (2일)

### 목표
- 차트 전용으로 정제/보간된 데이터셋 생성
- Raw 데이터와 분리된 저장소를 통해 안정적인 시각화

### 작업 항목
- [ ] Phase trimming (Rest/Warm-up/Recovery 제거)
- [ ] Power binning (5–10W, median/trimmed mean)
- [ ] Interpolation (PCHIP/Akima 또는 LOESS)
- [ ] `breath_data_processed` 테이블 설계 및 적재
- [ ] 테스트 유형 자동 태깅(프로토콜/패턴 기반)

### 완료 기준
- [ ] 모든 테스트에 대해 processed series 생성
- [ ] 메타볼릭 차트가 processed series 기준으로 동작

---

## Phase 3: Frontend 업로드 UI (3-4일)

### 목표
- 웹 UI에서 CPET 파일 업로드 및 분석

### 작업 항목

#### 3.1 업로드 페이지 컴포넌트
- `frontend/src/components/pages/UploadTestPage.tsx`
- Drag & Drop 파일 선택
- 피험자 선택 드롭다운
- 분석 옵션 설정 폼:
  - calc_method: Frayn / Peronnet / Jeukendrup
  - smoothing_window: 5 / 10 / 15 / 20
  - vt_method: v_slope / ventilatory_equivalent / rer

#### 3.2 업로드 진행 상태
- 파일 검증 → 파싱 → 분석 → 저장 단계 표시
- Progress bar
- 에러 시 상세 메시지

#### 3.3 업로드 결과 화면
- 분석 결과 요약 카드
- "상세 보기" 버튼 → MetabolismPage로 이동

### 완료 기준
- [ ] 파일 업로드 후 DB 저장 성공
- [ ] 분석 결과 즉시 확인 가능
- [ ] 에러 핸들링 완료

---

## Phase 4: 분석 결과 시각화 고도화 (4-5일)

### 목표
- 상세 분석 뷰 및 비교 기능

### 작업 항목

#### 4.1 테스트 목록 페이지
- 피험자별 필터링
- 날짜 범위 필터
- 정렬 (날짜, VO2MAX, FATMAX)
- 비교할 테스트 다중 선택

#### 4.2 분석 상세 페이지
- Phase 구간별 색상 구분
- VT1/VT2 수직선 마커
- FATMAX 포인트 하이라이트
- 인터랙티브 줌/패닝
- 데이터 포인트 툴팁

#### 4.3 비교 분석 뷰
- 2-4개 테스트 오버레이 차트
- 지표별 비교 테이블
- 시간 정렬 (시작점 동기화)

#### 4.4 VT 수동 보정 (선택)
- 자동 감지된 VT 위치를 드래그로 조정
- 수동 보정 값 저장

### 완료 기준
- [ ] 상세 분석 페이지 완성
- [ ] 비교 분석 기능 동작
- [ ] 차트 인터랙션 완료

---

## Phase 5: 고급 기능 (추후)

### 5.1 PDF 리포트 생성
- 분석 결과 PDF 다운로드
- 차트 이미지 포함
- 트레이닝 존 권장사항

### 5.2 트레이닝 존 계산
- VT1/VT2 기반 5존 자동 계산
- HR/Power 존 표시

### 5.3 시계열 트렌드 분석
- 동일 피험자 장기 추이
- VO2MAX, FATMAX 변화 그래프

### 5.4 코호트 분석
- 그룹별 평균 비교
- 통계 분석 (t-test 등)

---

## 실행 명령어 참조

### Phase 1 실행
```bash
# 배치 임포트
cd /Users/cyanluna-pro16/dev/cpet.db
source .venv/bin/activate
python scripts/bulk_import_cpet_data.py

# 검증 리포트 생성
python scripts/generate_validation_report.py
```

### 서버 실행
```bash
# Backend
cd backend && python -m uvicorn app.main:app --reload --port 8100

# Frontend
cd frontend && npm run dev
```

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-01-16 | 초안 작성, Phase 1 시작 |
