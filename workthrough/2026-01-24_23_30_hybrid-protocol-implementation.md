# HYBRID 프로토콜 구현 및 테스트 관리 개선

## 개요
CPET 테스트에서 2개의 RAMP 구간(대사 측정용 + VO2max 측정용)을 가진 HYBRID 프로토콜을 자동 감지하고 분석하도록 구현. 추가로 테스트 데이터 중복 업로드 시 override 기능과 Admin 삭제 버튼 추가.

## 주요 변경사항

### 1. HYBRID 프로토콜 지원
- **ProtocolType에 HYBRID 추가** (`schemas/test.py`)
- **세그먼트 분석 로직** (`data_validator.py`)
  - `_detect_segments()`: 상태 머신 기반 ramp/recovery 구간 감지
  - 상대적 Recovery 임계값 (최대 파워의 30%, 최소 50W)
  - 스마트 Phase 선택 (가장 긴 램프 = metabolic, 최고 파워 = vo2max)
- **Phase별 분리 분석** (`test.py`)
  - metabolic_phase → FatMax, VT 분석
  - vo2max_phase → VO2max, HRmax 분석

### 2. 테스트 데이터 관리 개선
- **중복 업로드 override**: 같은 피험자 + 같은 파일명 → 기존 테스트 삭제 후 새로 저장
- **피험자 정보 우선 적용**: `subject.height_cm` → `parsed_data.subject.height_cm` 순

### 3. Admin 삭제 기능
- AdminDataPage에 삭제 버튼 추가 (빨간색 휴지통 아이콘)
- 확인 다이얼로그 포함

## 핵심 코드

```python
# HYBRID 감지 로직 (data_validator.py)
if len(ramp_segments) >= 2 and len(recovery_segments) >= 1:
    metabolic_phase = max(ramp_segments, key=lambda s: (s.end_sec - s.start_sec))
    vo2max_phase = max(ramp_segments, key=lambda s: (s.max_power or 0))
    return ProtocolType.HYBRID, correlation, segments, hybrid_phases
```

## 결과
- ✅ 단순 RAMP 분류 정상 (r=1.0)
- ✅ INTERVAL 분류 정상
- ✅ HYBRID 분류 정상 (2 RAMP + Recovery)
- ✅ 프론트엔드 빌드 성공

## 다음 단계
- HYBRID 프로토콜 테스트 데이터로 FatMax/VO2max 값 검증
- ProcessedMetabolism에 HYBRID 분석 결과 저장 로직 추가
- 차트에서 HYBRID phase 구간 시각화
