# Lactate & Glucose Manual Recording Data

> 사진에서 전사한 데이터입니다. 잘못 읽은 값이 있으면 직접 수정해주세요.
> 수정 완료 후 알려주시면 이 파일을 파싱하여 사용합니다.

## Subject Info

| Field | Value |
|-------|-------|
| Name | 박근윤 (Park Geunyun) |
| Test Date | 2026-03-20 |
| Start Time | 13:13 KST |
| End Time | 14:05 KST |
| FTP | 253 W |
| Max HR | 186 bpm |
| 예상 LT1 | 160 W |
| 예상 LT2 | 270 W |
| Low LC | 165 mm |

## Block 0 — Rest (baseline)

| Step | Load(W) | Duration | KST | HR(bpm) | Lactate(mmol/L) | Glucose(mmol/L) | Notes |
|------|---------|----------|------|---------|-----------------|-----------------|-------|
| 0 | 0 | n/a | 13:13 | 84 | 1.58 | 2.95 | baseline |

## Block 1 — LT1 (8min per step, 40W increments)

| Step | Load(W) | Duration(min) | KST | HR(bpm) | Lactate(mmol/L) | Glucose(mmol/L) | Notes |
|------|---------|---------------|------|---------|-----------------|-----------------|-------|
| 1-1 | 100 | 8 | 13:21 | 118 | 1.85 | 8.63 | |
| 1-2 | 140 | 8 | 13:30 | 124 | 1.69 | 6.01 | |
| 1-3 | 180 | 8 | 13:39 | 130 | 2.19 | 4.88 | |
| 1-4 | 220 | 8 | — | — | — | — | LT1넘음 중단 |
| 1-5 | 260 | 8 | — | — | — | — | 체혈 없음 |
| 1-6 | 300 | 8 | — | — | — | — | 체혈 없음 |

## Block 2 — VO2max (30s ramp, no blood sampling)

| Step | Load(W) | Duration(min) | KST | HR(bpm) | Lactate(mmol/L) | Glucose(mmol/L) | Notes |
|------|---------|---------------|------|---------|-----------------|-----------------|-------|
| end | 425 | 0.5 | 13:53 | 190 | 9.30 | 3.96 | VO2Max End 시 채혈 |

## Block 3 — Clearance (3min per step, %FTP increments)

| Step | %FTP | Load(W) | Duration(min) | KST | HR(bpm) | Lactate(mmol/L) | Glucose(mmol/L) | Notes |
|------|------|---------|---------------|------|---------|-----------------|-----------------|-------|
| 3-1 | 85% | 215 | 3 | 13:57 | 157 | 13.70 | 5.35 | |
| 3-2 | 90% | 228 | 3 | 14:00 | 162 | 13.91 | 5.55 | |
| 3-3 | 95% | 240 | 3 | 14:03 | 168 | 13.04 | 5.43 | |
| 3-4 | 100% | 253 | 3 | 14:06 | 173 | 13.50 | 5.44 | |
| 3-5 | 105% | 267 | 3 | — | — | — | — | 중단 |
| 3-6 | 110% | 279 | 3 | — | — | — | — | 중단 |
| 3-7 | 115% | 292 | 3 | — | — | — | — | 중단 |
