# API 구현 계획 (Frontend ↔ Backend)

## 개요

FastAPI 백엔드와 React 프론트엔드 간 API 연동 계획입니다.
단계별로 "로그인 → 피험자 → 테스트 → 시계열/요약 → 코호트 분석" 순으로 구현합니다.

---

## 1단계: 기반 설정 및 인증 (완료)

### 엔드포인트

| Method | Path | 설명 | 권한 |
|--------|------|------|------|
| POST | `/api/auth/login` | 로그인 (OAuth2 Password Flow) | Public |
| POST | `/api/auth/register` | 회원가입 | Public |
| GET | `/api/auth/me` | 현재 사용자 정보 | Authenticated |
| POST | `/api/auth/refresh` | 토큰 갱신 | Authenticated |

### 프론트엔드 연동
- [useAuth.tsx](../frontend/src/hooks/useAuth.tsx): 인증 상태 관리
- [LoginPage.tsx](../frontend/src/components/pages/LoginPage.tsx): 로그인 UI
- [api.ts](../frontend/src/lib/api.ts): API 클라이언트

### 구현 파일
- Backend: `backend/app/api/auth.py`, `backend/app/services/auth.py`
- Frontend: `frontend/src/lib/api.ts`

---

## 2단계: 피험자 API (완료)

### 엔드포인트

| Method | Path | 설명 | 권한 |
|--------|------|------|------|
| GET | `/api/subjects` | 피험자 목록 (페이지네이션) | Researcher |
| POST | `/api/subjects` | 피험자 생성 | Researcher |
| GET | `/api/subjects/{id}` | 피험자 상세 (테스트 포함) | Researcher/본인 |
| PATCH | `/api/subjects/{id}` | 피험자 수정 | Researcher |
| DELETE | `/api/subjects/{id}` | 피험자 삭제 | Researcher |

### Query Parameters (GET /subjects)
```
page: int = 1          # 페이지 번호
page_size: int = 20    # 페이지 크기 (max 100)
search: str            # 검색어 (연구ID, 이름)
gender: str            # 성별 필터 (M/F)
training_level: str    # 훈련 수준 필터
```

### 응답 스키마
```json
{
  "items": [
    {
      "id": "uuid",
      "research_id": "SUB001",
      "encrypted_name": "홍**",
      "birth_year": 1990,
      "gender": "M",
      "training_level": "Trained",
      "weight_kg": 70.5,
      "height_cm": 175.0,
      "created_at": "2024-01-15T10:00:00Z"
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 20,
  "total_pages": 8
}
```

### 프론트엔드 연동
- [SubjectListPage.tsx](../frontend/src/components/pages/SubjectListPage.tsx)
- [SubjectDetailPage.tsx](../frontend/src/components/pages/SubjectDetailPage.tsx)
- [SubjectDashboard.tsx](../frontend/src/components/pages/SubjectDashboard.tsx)

---

## 3단계: 테스트 API (완료)

### 엔드포인트

| Method | Path | 설명 | 권한 |
|--------|------|------|------|
| POST | `/api/tests/upload` | COSMED 파일 업로드 | Researcher |
| GET | `/api/tests` | 테스트 목록 | Authenticated |
| GET | `/api/tests/{id}` | 테스트 상세 | Authenticated |
| PATCH | `/api/tests/{id}` | 테스트 수정 | Researcher |
| DELETE | `/api/tests/{id}` | 테스트 삭제 | Researcher |
| GET | `/api/subjects/{id}/tests` | 피험자별 테스트 목록 | Authenticated |

### 파일 업로드 (POST /tests/upload)
```
Content-Type: multipart/form-data

file: File (.xlsx, .xls)  # COSMED Excel 파일
subject_id: UUID          # 피험자 ID
calc_method: str = "Frayn"  # 대사 계산 방법
smoothing_window: int = 10  # 평활화 윈도우
```

### 업로드 응답
```json
{
  "test_id": "uuid",
  "subject_id": "uuid",
  "source_filename": "test_data.xlsx",
  "parsing_status": "success",
  "parsing_errors": null,
  "parsing_warnings": ["Some warnings"],
  "data_points_count": 1500,
  "created_at": "2024-01-15T10:00:00Z"
}
```

### 프론트엔드 연동
- [SingleTestView.tsx](../frontend/src/components/pages/SingleTestView.tsx)
- [ResearcherDashboard.tsx](../frontend/src/components/pages/ResearcherDashboard.tsx) - 업로드 기능

---

## 4단계: 시계열 및 메트릭 API (완료)

### 엔드포인트

| Method | Path | 설명 | 권한 |
|--------|------|------|------|
| GET | `/api/tests/{id}/series` | 시계열 데이터 (다운샘플링) | Authenticated |
| GET | `/api/tests/{id}/metrics` | 테스트 메트릭 요약 | Authenticated |

### 시계열 Query Parameters
```
signals: str = "vo2,vco2,hr"  # 조회할 신호 (콤마 구분)
interval: str = "1s"          # 다운샘플 간격 (1s, 5s, 10s, 30s)
method: str = "mean"          # 집계 방법 (mean, median, max, min)
start_sec: float              # 시작 시간 (초)
end_sec: float                # 종료 시간 (초)
```

### 시계열 응답
```json
{
  "test_id": "uuid",
  "signals": ["vo2", "vco2", "hr"],
  "interval": "1s",
  "data_points": [
    {"t_sec": 0, "vo2": 0.5, "vco2": 0.4, "hr": 75},
    {"t_sec": 1, "vo2": 0.52, "vco2": 0.42, "hr": 76}
  ],
  "total_points": 600,
  "duration_sec": 600
}
```

### 메트릭 응답
```json
{
  "test_id": "uuid",
  "subject_id": "uuid",
  "vo2_max": 4.2,
  "vo2_max_rel": 56.0,
  "hr_max": 185,
  "vt1_hr": 135,
  "vt1_vo2": 2.1,
  "vt2_hr": 165,
  "vt2_vo2": 3.2,
  "fat_max_hr": 128,
  "fat_max_g_min": 0.65,
  "phases": {
    "warmup": {"start_sec": 0, "end_sec": 180},
    "exercise": {"start_sec": 180, "end_sec": 540},
    "recovery": {"start_sec": 540, "end_sec": 720}
  }
}
```

### 프론트엔드 연동
- [MetabolismPage.tsx](../frontend/src/components/pages/MetabolismPage.tsx)
- [MetabolismChart.tsx](../frontend/src/components/pages/MetabolismChart.tsx)
- [MetabolismPatternChart.tsx](../frontend/src/components/pages/MetabolismPatternChart.tsx)

---

## 5단계: 코호트 분석 API (완료)

### 엔드포인트

| Method | Path | 설명 | 권한 |
|--------|------|------|------|
| GET | `/api/cohorts/summary` | 코호트 요약 통계 | Researcher |
| POST | `/api/cohorts/summary` | 코호트 요약 (고급 필터) | Researcher |
| GET | `/api/cohorts/distribution` | 지표 분포 (히스토그램) | Researcher |
| GET | `/api/cohorts/percentile` | 백분위 계산 | Researcher |
| POST | `/api/cohorts/comparison` | 피험자-코호트 비교 | Researcher |
| GET | `/api/cohorts/stats` | 전체 DB 통계 | Researcher |

### 필터 파라미터
```
gender: str           # 성별 (M/F/All)
age_min: int          # 최소 나이
age_max: int          # 최대 나이
training_level: str   # 훈련 수준
```

### 요약 통계 응답
```json
{
  "filters_applied": {"gender": "M", "age_min": 20, "age_max": 40},
  "total_subjects": 45,
  "total_tests": 120,
  "metrics": [
    {
      "metric_name": "vo2_max_rel",
      "mean": 48.5,
      "median": 47.2,
      "std_dev": 8.3,
      "min_value": 32.1,
      "max_value": 65.8,
      "percentile_25": 42.0,
      "percentile_75": 54.5,
      "sample_size": 45
    }
  ],
  "last_updated": "2024-01-15T10:00:00Z"
}
```

### 프론트엔드 연동
- [CohortAnalysisPage.tsx](../frontend/src/components/pages/CohortAnalysisPage.tsx)
- [ResearcherDashboard.tsx](../frontend/src/components/pages/ResearcherDashboard.tsx)

---

## 공통 규약

### API 버저닝
- 모든 엔드포인트는 `/api` 프리픽스 사용
- 향후 버전 변경 시 `/api/v2` 등으로 확장

### 인증 헤더
```
Authorization: Bearer <access_token>
```

### 에러 응답 형식
```json
{
  "detail": "에러 메시지",
  "code": "ERROR_CODE",      // 선택적
  "errors": []               // 유효성 검증 에러
}
```

### HTTP 상태 코드
- `200`: 성공
- `201`: 생성 성공
- `204`: 삭제 성공 (No Content)
- `400`: 잘못된 요청
- `401`: 인증 필요
- `403`: 권한 없음
- `404`: 리소스 없음
- `413`: 파일 크기 초과
- `422`: 유효성 검증 실패

### CORS 설정
```python
allow_origins = ["http://localhost:3100", "http://localhost:5173"]
allow_credentials = True
allow_methods = ["*"]
allow_headers = ["*"]
```

---

## 권한 체계

| 역할 | 설명 | 접근 가능 엔드포인트 |
|------|------|---------------------|
| `admin` | 관리자 | 전체 |
| `researcher` | 연구자 | 대부분 (관리자 기능 제외) |
| `subject` | 피험자 | 본인 데이터만 조회 |

### 의존성 함수
```python
CurrentUser = Annotated[User, Depends(get_current_active_user)]
AdminUser = Annotated[User, Depends(get_current_admin_user)]
ResearcherUser = Annotated[User, Depends(get_researcher_user)]
```

---

## 성능 고려사항

### 대용량 데이터 처리
1. **시계열 다운샘플링**: 클라이언트에서 `interval` 파라미터로 데이터 밀도 조절
2. **페이지네이션**: 모든 목록 API에 페이지네이션 적용
3. **인덱싱**: `subject_id`, `test_date`, `t_sec` 컬럼에 인덱스

### 파일 업로드
- 최대 파일 크기: 50MB
- 지원 형식: `.xlsx`, `.xls`
- 업로드 타임아웃: 120초

---

## 테스트 실행

### 백엔드
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 프론트엔드
```bash
cd frontend
npm install
npm run dev
```

### API 문서
- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

---

## 체크리스트

- [x] 인증 API (login, register, me, refresh)
- [x] 피험자 CRUD API
- [x] 테스트 업로드 및 CRUD API
- [x] 시계열 데이터 API (다운샘플링)
- [x] 테스트 메트릭 API
- [x] 코호트 분석 API
- [x] 프론트엔드 API 클라이언트 업데이트
- [ ] E2E 테스트 작성
- [ ] API 성능 테스트
