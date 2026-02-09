# HYBRID 프로토콜 지원: 듀얼 세그먼트 분석 윈도우

## 개요

HYBRID CPET 프로토콜(Ramp 1: FATMAX + Ramp 2: VO2max)에서 두 ramp 구간을 분리하여 분석할 수 있도록, 기존 단일 Analysis Window를 FATMAX/VO2max 두 개의 명명된 세그먼트로 확장했다. 연구자가 개요 차트에서 각 구간을 수동으로 지정할 수 있는 UI를 제공한다.

## 주요 변경사항

### Backend
- **`processed_metabolism.py`**: MetabolismConfig에 `vo2max_start_sec`, `vo2max_end_sec` 필드 추가 + 유효성 검증(end > start, 세그먼트 비겹침)
- **`metabolism_analysis.py`**: AnalysisConfig에 동일 필드 추가 + `to_dict()` 반영
- **`tests.py`**: `/analysis` 엔드포인트에 `vo2max_start_sec`, `vo2max_end_sec` 쿼리 파라미터 추가
- **`test.py`(서비스)**: `get_analysis()` 메서드에 vo2max 파라미터 전달 경로 추가

### Frontend
- **`api.ts`**: `MetabolismConfigApi` 인터페이스에 vo2max 필드 추가
- **`RawDataViewerPage.tsx`**:
  - `vo2maxRange` 상태 + debounce 추가
  - 단일 "Analysis Window" 슬라이더를 파란색 "FATMAX 구간" + 주황색 "VO2max 구간" 2개로 분리
  - 개요 차트에 `ReferenceArea`로 두 세그먼트 색상 오버레이 표시
  - 저장/로드/리셋/dirty state에 vo2max 범위 포함
  - API 요청에 vo2max 쿼리 파라미터 전달

## 결과

- ✅ Backend pytest: 115 passed
- ✅ Frontend build: 성공 (타입 에러 없음)
- ✅ Schema 유효성 검증: end > start, 세그먼트 비겹침 검증 통과

## 다음 단계

- VO2max 세그먼트 데이터로 실제 VO2max 재계산 로직 구현 (현재는 저장/전달만)
- HYBRID 프로토콜 자동 감지 (두 개의 ramp 패턴을 자동으로 분리)
- VO2max 구간 분석 결과를 별도 차트/패널로 시각화
