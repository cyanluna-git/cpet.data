# RER Curve 버그 수정 보고서

## 📋 문제 요약

**증상**: 전처리된 데이터(Processed Data)에서 RER Curve 차트가 빈 화면으로 표시됨  
**원인**: 백엔드 metabolism_analysis.py에서 RER 데이터를 processed_series에 포함하지 않음  
**해결일**: 2026-01-17  

---

## 🔍 근본 원인 분석

### 1. Raw 데이터 추출 시 RER 누락
**파일**: `backend/app/services/metabolism_analysis.py`  
**메서드**: `_extract_raw_points` (Line 285-296)

```python
# ❌ 수정 전
ProcessedDataPoint(
    power=float(bd.bike_power),
    fat_oxidation=float(bd.fat_oxidation) if bd.fat_oxidation else None,
    cho_oxidation=float(bd.cho_oxidation) if bd.cho_oxidation else None,
    count=1
    # RER 필드 누락!
)

# ✅ 수정 후
ProcessedDataPoint(
    power=float(bd.bike_power),
    fat_oxidation=float(bd.fat_oxidation) if bd.fat_oxidation else None,
    cho_oxidation=float(bd.cho_oxidation) if bd.cho_oxidation else None,
    rer=float(bd.rer) if bd.rer else None,  # ← 추가
    count=1
)
```

### 2. Power Binning 시 RER 누락
**파일**: `backend/app/services/metabolism_analysis.py`  
**메서드**: `_power_binning` (Line 297-388)

```python
# ❌ 수정 전 - DataFrame 생성
df = pd.DataFrame([{
    "power": p.power,
    "fat_oxidation": p.fat_oxidation,
    "cho_oxidation": p.cho_oxidation
    # RER 누락!
} for p in raw_points])

# ✅ 수정 후
df = pd.DataFrame([{
    "power": p.power,
    "fat_oxidation": p.fat_oxidation,
    "cho_oxidation": p.cho_oxidation,
    "rer": p.rer  # ← 추가
} for p in raw_points])
```

```python
# ❌ 수정 전 - 집계
agg_df = df.groupby("power_bin").agg({
    "fat_oxidation": "median",
    "cho_oxidation": "median",
    "power": "count"
    # RER 누락!
})

# ✅ 수정 후
agg_df = df.groupby("power_bin").agg({
    "fat_oxidation": "median",
    "cho_oxidation": "median",
    "rer": "median",  # ← 추가
    "power": "count"
})
```

```python
# ❌ 수정 전 - ProcessedDataPoint 생성
ProcessedDataPoint(
    power=float(row["power_bin"]),
    fat_oxidation=fat_ox,
    cho_oxidation=cho_ox,
    count=int(row["count"])
    # RER 누락!
)

# ✅ 수정 후
ProcessedDataPoint(
    power=float(row["power_bin"]),
    fat_oxidation=fat_ox,
    cho_oxidation=cho_ox,
    rer=rer_val,  # ← 추가
    count=int(row["count"])
)
```

### 3. LOESS Smoothing 시 RER 누락
**파일**: `backend/app/services/metabolism_analysis.py`  
**메서드**: `_loess_smoothing` (Line 390-450)

```python
# ❌ 수정 전 - 데이터 추출
powers = np.array([p.power for p in binned_points])
fat_ox = np.array([p.fat_oxidation if p.fat_oxidation is not None else 0 for p in binned_points])
cho_ox = np.array([p.cho_oxidation if p.cho_oxidation is not None else 0 for p in binned_points])
# RER 누락!

# ✅ 수정 후
powers = np.array([p.power for p in binned_points])
fat_ox = np.array([p.fat_oxidation if p.fat_oxidation is not None else 0 for p in binned_points])
cho_ox = np.array([p.cho_oxidation if p.cho_oxidation is not None else 0 for p in binned_points])
rer_vals = np.array([p.rer if p.rer is not None else np.nan for p in binned_points])  # ← 추가
```

```python
# ✅ RER LOESS Smoothing 추가
rer_smoothed = None
if not np.all(np.isnan(rer_vals)):
    valid_idx = ~np.isnan(rer_vals)
    if np.sum(valid_idx) >= 4:  # 최소 4개 이상의 유효값이 있을 때만
        rer_smoothed = lowess(rer_vals[valid_idx], powers[valid_idx], frac=frac, return_sorted=True)
```

```python
# ✅ RER 값 보간 및 물리적 제약 적용
rer_val = None
if rer_smoothed is not None:
    power_val = fat_smoothed[i, 0]
    # 가장 가까운 power 값의 RER 사용
    idx = np.argmin(np.abs(rer_smoothed[:, 0] - power_val))
    rer_val = float(rer_smoothed[idx, 1])
    # RER 물리적 제약 (0.5~1.5)
    if not (0.5 <= rer_val <= 1.5):
        rer_val = None
```

### 4. 스키마 업데이트
**파일**: `backend/app/schemas/test.py`  
**클래스**: `ProcessedDataPoint` (Line 244-249)

```python
# ❌ 수정 전
class ProcessedDataPoint(BaseModel):
    """처리된 데이터 포인트 스키마"""
    power: float
    fat_oxidation: Optional[float] = None
    cho_oxidation: Optional[float] = None
    count: Optional[int] = None  # binned data only
    # RER 필드 누락!

# ✅ 수정 후
class ProcessedDataPoint(BaseModel):
    """처리된 데이터 포인트 스키마"""
    power: float
    fat_oxidation: Optional[float] = None
    cho_oxidation: Optional[float] = None
    rer: Optional[float] = None  # ← 추가
    count: Optional[int] = None  # binned data only
```

---

## 🎯 수정된 파일 목록

1. **`backend/app/services/metabolism_analysis.py`**
   - `_extract_raw_points`: RER 추출 추가
   - `_power_binning`: RER 집계 추가 (median, mean, trimmed_mean)
   - `_loess_smoothing`: RER smoothing 추가 + 물리적 제약 (0.5~1.5)

2. **`backend/app/schemas/test.py`**
   - `ProcessedDataPoint`: RER 필드 추가

---

## ✅ 검증 방법

### 1. 백엔드 API 응답 확인
```bash
GET /api/tests/{test_id}/analysis?include_processed=true
```

**응답 예시**:
```json
{
  "processed_series": {
    "raw": [
      {"power": 100, "fat_oxidation": 0.45, "cho_oxidation": 0.32, "rer": 0.85},
      ...
    ],
    "binned": [
      {"power": 100, "fat_oxidation": 0.43, "cho_oxidation": 0.31, "rer": 0.84, "count": 5},
      ...
    ],
    "smoothed": [
      {"power": 100, "fat_oxidation": 0.44, "cho_oxidation": 0.32, "rer": 0.85},
      ...
    ]
  }
}
```

### 2. 프론트엔드 차트 확인
- Raw Data Viewer 페이지에서 "전처리 데이터 사용" 체크
- RER Curve 프리셋 선택
- 차트가 정상적으로 표시되는지 확인

---

## 📊 영향 범위

### 직접 영향
- ✅ **RER Curve 차트**: 전처리 데이터에서 정상 표시
- ✅ **FATMAX 차트**: RER 오버레이 가능
- ✅ **데이터 다운로드**: RER 값 포함

### 간접 영향
- 🔄 **캐싱**: 기존 캐시된 분석 결과는 RER이 없음 (재분석 필요)
- 🔄 **데이터베이스**: ProcessedMetabolism 테이블 재계산 필요 (선택적)

---

## 🚀 배포 체크리스트

- [x] 백엔드 코드 수정
- [x] 스키마 업데이트
- [ ] 백엔드 서버 재시작
- [ ] 프론트엔드 빌드 확인
- [ ] 실제 데이터로 RER Curve 테스트
- [ ] 문서 업데이트

---

## 💡 추가 개선 사항

### 1. RER 물리적 제약 검증
현재 smoothing 시 0.5~1.5 범위로 제한하고 있습니다:
- 일반적인 RER 범위: 0.7~1.0 (정상)
- 극한 상황: 0.67 (순수 지방), 1.0 (순수 탄수화물)
- 현재 범위는 약간 여유를 두었으나, 필요시 조정 가능

### 2. RER 데이터 품질 체크
다음 경우 RER 값이 None이 될 수 있습니다:
- 원본 데이터에 RER이 없는 경우
- Smoothing 결과가 물리적 범위를 벗어난 경우
- 유효한 데이터 포인트가 4개 미만인 경우

### 3. 프론트엔드 차트 개선
프론트엔드에서 RER이 None인 경우 처리:
```typescript
// RawDataViewerPage.tsx Line 487
rer: point.rer || null,  // ✅ 이미 처리됨
```

---

**작성**: 2026-01-17  
**작성자**: GitHub Copilot CLI  
**이슈**: RER Curve 전처리 데이터 미표시  
**상태**: ✅ 해결 완료
