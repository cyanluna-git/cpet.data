# CPET Platform 배포 가이드

Supabase (DB) → Google Cloud Run (Backend) → Vercel (Frontend) 배포 가이드

---

## 목차

1. [사전 준비](#1-사전-준비)
2. [Step 1: Supabase 설정](#step-1-supabase-설정)
3. [Step 2: Google Cloud Run 배포](#step-2-google-cloud-run-배포)
4. [Step 3: Vercel 배포](#step-3-vercel-배포)
5. [배포 후 확인](#배포-후-확인)
6. [트러블슈팅](#트러블슈팅)

---

## 1. 사전 준비

### 필요한 계정
- [Supabase](https://supabase.com) 계정 (GitHub 로그인)
- [Google Cloud](https://console.cloud.google.com) 계정
- [Vercel](https://vercel.com) 계정 (GitHub 로그인)
- GitHub에 프로젝트가 push 되어 있어야 함

### 로컬 도구 설치
```bash
# Google Cloud CLI 설치 (macOS)
brew install google-cloud-sdk

# 또는 직접 다운로드
# https://cloud.google.com/sdk/docs/install

# gcloud 초기화
gcloud init
```

---

## Step 1: Supabase 설정

### 1.1 프로젝트 생성

1. https://supabase.com 접속 → **Start your project**
2. GitHub 로그인
3. **New Project** 클릭
4. 프로젝트 설정:
   - **Organization**: 선택 또는 생성
   - **Project name**: `cpet-db`
   - **Database Password**: 강력한 비밀번호 입력 (⚠️ 반드시 저장!)
   - **Region**: `Northeast Asia (Seoul)` 선택
5. **Create new project** 클릭 (2-3분 소요)

### 1.2 연결 정보 확인

프로젝트 Dashboard에서 **Settings** → **Database** 이동

**Connection string** 섹션에서:

| 항목 | 용도 |
|------|------|
| **URI (Transaction mode, 포트 6543)** | Cloud Run용 (⭐ 이것 사용) |
| **URI (Session mode, 포트 5432)** | 로컬 개발용 |

예시:
```
postgresql://postgres.[project-ref]:[YOUR-PASSWORD]@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres
```

### 1.3 백엔드용 DATABASE_URL 변환

SQLAlchemy asyncpg 드라이버를 사용하므로 URL 스키마 변경 필요:

```bash
# 원본 (Supabase에서 복사)
postgresql://postgres.[ref]:[password]@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres

# 변환 후 (이것을 사용)
postgresql+asyncpg://postgres.[ref]:[password]@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres
```

### 1.4 테이블 생성

**방법 A: 백엔드 앱에서 자동 생성 (권장)**

백엔드 최초 실행 시 SQLAlchemy가 자동으로 테이블 생성. 추가 작업 불필요.

**방법 B: SQL Editor에서 직접 생성**

Supabase Dashboard → **SQL Editor** → **New query**

```sql
-- UUID 확장 활성화
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. subjects 테이블
CREATE TABLE IF NOT EXISTS subjects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    research_id VARCHAR(50) UNIQUE NOT NULL,
    encrypted_name VARCHAR(255),
    birth_year INTEGER,
    birth_date DATE,
    gender VARCHAR(10),
    job_category VARCHAR(50),
    medical_history JSONB,
    training_level VARCHAR(20),
    weight_kg FLOAT,
    height_cm FLOAT,
    body_fat_percent FLOAT,
    skeletal_muscle_mass FLOAT,
    bmi FLOAT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_subjects_research_id ON subjects(research_id);
CREATE INDEX IF NOT EXISTS idx_subjects_gender_birth_year ON subjects(gender, birth_year);

-- 2. users 테이블
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    subject_id UUID REFERENCES subjects(id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_subject_id ON users(subject_id);

-- 3. cpet_tests 테이블
CREATE TABLE IF NOT EXISTS cpet_tests (
    test_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    test_date TIMESTAMP NOT NULL,
    test_time TIME,
    protocol_name VARCHAR(100),
    protocol_type VARCHAR(10),
    test_type VARCHAR(20) DEFAULT 'Maximal',
    maximal_effort VARCHAR(20),
    test_duration TIME,
    exercise_duration TIME,
    barometric_pressure FLOAT,
    ambient_temp FLOAT,
    ambient_humidity FLOAT,
    device_temp FLOAT,
    age FLOAT,
    height_cm FLOAT,
    weight_kg FLOAT,
    bsa FLOAT,
    bmi FLOAT,
    vo2_max FLOAT,
    vo2_max_rel FLOAT,
    vco2_max FLOAT,
    hr_max INTEGER,
    fat_max_hr INTEGER,
    fat_max_watt FLOAT,
    fat_max_g_min FLOAT,
    vt1_hr INTEGER,
    vt1_vo2 FLOAT,
    vt2_hr INTEGER,
    vt2_vo2 FLOAT,
    calc_method VARCHAR(20) DEFAULT 'Frayn',
    smoothing_window INTEGER DEFAULT 10,
    warmup_end_sec INTEGER,
    test_end_sec INTEGER,
    source_filename VARCHAR(255),
    file_upload_timestamp TIMESTAMP,
    parsing_status VARCHAR(50),
    parsing_errors JSONB,
    phase_metrics JSONB,
    notes TEXT,
    data_quality_score FLOAT,
    processing_status VARCHAR(20) DEFAULT 'none',
    last_analysis_version VARCHAR(20),
    analysis_saved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cpet_tests_subject_id ON cpet_tests(subject_id);
CREATE INDEX IF NOT EXISTS idx_cpet_tests_test_date ON cpet_tests(test_date);
CREATE INDEX IF NOT EXISTS idx_cpet_tests_subject_date ON cpet_tests(subject_id, test_date);

-- 4. breath_data 테이블
CREATE TABLE IF NOT EXISTS breath_data (
    time TIMESTAMP NOT NULL,
    test_id UUID NOT NULL REFERENCES cpet_tests(test_id) ON DELETE CASCADE,
    t_sec FLOAT,
    rf FLOAT,
    vt FLOAT,
    vo2 FLOAT,
    vco2 FLOAT,
    ve FLOAT,
    hr INTEGER,
    vo2_hr FLOAT,
    bike_power INTEGER,
    bike_torque FLOAT,
    cadence INTEGER,
    feo2 FLOAT,
    feco2 FLOAT,
    feto2 FLOAT,
    fetco2 FLOAT,
    ve_vo2 FLOAT,
    ve_vco2 FLOAT,
    rer FLOAT,
    fat_oxidation FLOAT,
    cho_oxidation FLOAT,
    pro_oxidation FLOAT,
    vo2_rel FLOAT,
    mets FLOAT,
    ee_total FLOAT,
    ee_kcal_day FLOAT,
    is_valid BOOLEAN DEFAULT TRUE,
    phase VARCHAR(20),
    raw_t_value TIME,
    data_source VARCHAR(10),
    PRIMARY KEY (time, test_id)
);
CREATE INDEX IF NOT EXISTS idx_breath_data_test_id ON breath_data(test_id, time);
CREATE INDEX IF NOT EXISTS idx_breath_data_phase ON breath_data(test_id, phase);

-- 5. cohort_stats 테이블
CREATE TABLE IF NOT EXISTS cohort_stats (
    stat_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    gender VARCHAR(10),
    age_group VARCHAR(20),
    training_level VARCHAR(20),
    metric_name VARCHAR(50) NOT NULL,
    mean_value FLOAT,
    median_value FLOAT,
    std_dev FLOAT,
    percentile_10 FLOAT,
    percentile_25 FLOAT,
    percentile_75 FLOAT,
    percentile_90 FLOAT,
    sample_size INTEGER,
    last_updated TIMESTAMP DEFAULT NOW(),
    UNIQUE(gender, age_group, training_level, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_cohort_stats_lookup ON cohort_stats(gender, age_group, training_level, metric_name);

-- 6. processed_metabolism 테이블
CREATE TABLE IF NOT EXISTS processed_metabolism (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cpet_test_id UUID NOT NULL REFERENCES cpet_tests(test_id) ON DELETE CASCADE,
    bin_size INTEGER DEFAULT 10,
    aggregation_method VARCHAR(20) DEFAULT 'median',
    loess_frac FLOAT DEFAULT 0.25,
    smoothing_method VARCHAR(20) DEFAULT 'loess',
    exclude_rest BOOLEAN DEFAULT TRUE,
    exclude_warmup BOOLEAN DEFAULT TRUE,
    exclude_recovery BOOLEAN DEFAULT TRUE,
    min_power_threshold INTEGER,
    trim_start_sec FLOAT,
    trim_end_sec FLOAT,
    is_manual_override BOOLEAN DEFAULT FALSE,
    raw_series JSONB,
    binned_series JSONB,
    smoothed_series JSONB,
    trend_series JSONB,
    fatmax_power INTEGER,
    fatmax_mfo FLOAT,
    fatmax_zone_min INTEGER,
    fatmax_zone_max INTEGER,
    fatmax_zone_threshold FLOAT DEFAULT 0.90,
    crossover_power INTEGER,
    crossover_fat_value FLOAT,
    crossover_cho_value FLOAT,
    total_data_points INTEGER,
    exercise_data_points INTEGER,
    binned_data_points INTEGER,
    processing_warnings JSONB,
    processing_status VARCHAR(20) DEFAULT 'pending',
    processed_at TIMESTAMP,
    algorithm_version VARCHAR(20) DEFAULT '1.0.0',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_processed_metabolism_cpet_test_id ON processed_metabolism(cpet_test_id);
CREATE INDEX IF NOT EXISTS idx_processed_metabolism_status ON processed_metabolism(processing_status);
```

### 1.5 저장할 정보 체크리스트

| 항목 | 예시 | 저장 여부 |
|------|------|----------|
| Project Ref | `abcdefghijkl` | ☐ |
| Database Password | `your-password` | ☐ |
| DATABASE_URL (asyncpg) | `postgresql+asyncpg://...` | ☐ |

---

## Step 2: Google Cloud Run 배포

### 2.1 사전 준비

```bash
# Google Cloud 프로젝트 생성 또는 선택
gcloud projects create cpet-platform --name="CPET Platform"
# 또는 기존 프로젝트 선택
gcloud config set project cpet-platform

# 필요한 API 활성화
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com

# 리전 설정
gcloud config set run/region asia-northeast3  # 서울
```

### 2.2 Dockerfile 생성

`backend/Dockerfile` 파일 생성:

```dockerfile
# Python 3.12 slim 이미지
FROM python:3.12-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 의존성 설치 (PostgreSQL 클라이언트 라이브러리)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 파일 복사
COPY requirements.txt .

# 의존성 설치
RUN pip install --no-cache-dir -r requirements.txt

# asyncpg 추가 설치 (PostgreSQL async 드라이버)
RUN pip install --no-cache-dir asyncpg psycopg2-binary

# 애플리케이션 코드 복사
COPY . .

# 포트 설정 (Cloud Run은 PORT 환경변수 사용)
ENV PORT=8080

# 서버 실행
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
```

### 2.3 .dockerignore 생성

`backend/.dockerignore` 파일 생성:

```
__pycache__
*.pyc
*.pyo
*.pyd
.Python
.env
.env.*
.venv
venv/
.git
.gitignore
*.md
tests/
.pytest_cache/
.mypy_cache/
*.db
*.sqlite3
uploads/
```

### 2.4 requirements.txt 업데이트

`backend/requirements.txt`에 추가:

```
# PostgreSQL async driver (Supabase용)
asyncpg==0.29.0
psycopg2-binary==2.9.9
```

### 2.5 로컬 Docker 테스트 (선택)

```bash
cd backend

# 이미지 빌드
docker build -t cpet-backend .

# 로컬 테스트 실행
docker run -p 8080:8080 \
  -e DATABASE_URL="postgresql+asyncpg://..." \
  -e SECRET_KEY="your-secret-key" \
  -e DEBUG="false" \
  cpet-backend

# 테스트
curl http://localhost:8080/health
```

### 2.6 Cloud Run 배포

**방법 A: gcloud CLI 사용 (권장)**

```bash
cd backend

# Cloud Run에 직접 배포 (소스 코드에서 빌드)
gcloud run deploy cpet-backend \
  --source . \
  --region asia-northeast3 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "DATABASE_URL=postgresql+asyncpg://postgres.[ref]:[password]@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres" \
  --set-env-vars "SECRET_KEY=your-production-secret-key-change-this" \
  --set-env-vars "DEBUG=false" \
  --set-env-vars "ALLOWED_ORIGINS=https://your-frontend.vercel.app" \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --timeout 300
```

**방법 B: Google Cloud Console 사용**

1. https://console.cloud.google.com/run 접속
2. **Create Service** 클릭
3. **Continuously deploy from a repository** 선택
4. GitHub 연결 → Repository 선택 → Branch: `main`
5. Build Configuration:
   - **Dockerfile** 선택
   - Source location: `/backend/Dockerfile`
6. Service settings:
   - Service name: `cpet-backend`
   - Region: `asia-northeast3 (Seoul)`
   - Authentication: `Allow unauthenticated invocations`
7. **Container, Networking, Security** 확장:
   - Memory: `512 MiB`
   - CPU: `1`
   - Request timeout: `300`
   - Min instances: `0`
   - Max instances: `10`
8. **Variables & Secrets** 탭에서 환경변수 추가:

| Name | Value |
|------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres.[ref]:[password]@...` |
| `SECRET_KEY` | `your-production-secret-key` (32자 이상 랜덤 문자열) |
| `DEBUG` | `false` |
| `ALLOWED_ORIGINS` | `https://your-frontend.vercel.app` (나중에 수정) |

9. **Create** 클릭

### 2.7 배포 확인

```bash
# 배포된 서비스 URL 확인
gcloud run services describe cpet-backend --region asia-northeast3 --format='value(status.url)'

# 예: https://cpet-backend-xxxxx-an.a.run.app

# Health check
curl https://cpet-backend-xxxxx-an.a.run.app/health
# 응답: {"status":"healthy"}

# API 문서 확인
# https://cpet-backend-xxxxx-an.a.run.app/api/docs
```

### 2.8 저장할 정보

| 항목 | 예시 | 저장 여부 |
|------|------|----------|
| Cloud Run URL | `https://cpet-backend-xxxxx-an.a.run.app` | ☐ |

---

## Step 3: Vercel 배포

### 3.1 Vercel 프로젝트 설정

1. https://vercel.com 접속 → GitHub 로그인
2. **Add New** → **Project**
3. GitHub Repository 선택: `cpet.data`
4. 설정:
   - **Framework Preset**: `Vite`
   - **Root Directory**: `frontend` (Edit 클릭하여 변경)
   - **Build Command**: `npm run build` (자동 감지)
   - **Output Directory**: `dist` (자동 감지)

### 3.2 환경변수 설정

**Environment Variables** 섹션 확장:

| Name | Value |
|------|-------|
| `VITE_API_URL` | `https://cpet-backend-xxxxx-an.a.run.app` |

### 3.3 Deploy

**Deploy** 버튼 클릭

배포 완료 후 URL 확인:
- Production: `https://cpet-data.vercel.app` (또는 자동 생성된 URL)

### 3.4 Cloud Run CORS 업데이트

Vercel URL을 받은 후, Cloud Run의 `ALLOWED_ORIGINS` 환경변수 업데이트:

```bash
gcloud run services update cpet-backend \
  --region asia-northeast3 \
  --set-env-vars "ALLOWED_ORIGINS=https://cpet-data.vercel.app,https://your-custom-domain.com"
```

또는 Google Cloud Console → Cloud Run → cpet-backend → **Edit & Deploy New Revision** → Variables에서 수정

### 3.5 커스텀 도메인 설정 (선택)

**Vercel:**
1. Project Settings → Domains
2. 도메인 추가 (예: `cpet.yourdomain.com`)
3. DNS 설정 안내에 따라 CNAME 레코드 추가

**Cloud Run:**
```bash
gcloud run domain-mappings create \
  --service cpet-backend \
  --region asia-northeast3 \
  --domain api.yourdomain.com
```

---

## 배포 후 확인

### 전체 시스템 확인 체크리스트

```bash
# 1. Supabase 연결 확인
# Cloud Run 로그에서 DB 연결 성공 확인
gcloud run services logs read cpet-backend --region asia-northeast3 --limit 50

# 2. Backend API 확인
curl https://cpet-backend-xxxxx-an.a.run.app/health
curl https://cpet-backend-xxxxx-an.a.run.app/api/docs

# 3. Frontend 확인
# 브라우저에서 https://cpet-data.vercel.app 접속
# 개발자 도구 (F12) → Network 탭에서 API 호출 확인
```

### 초기 Admin 계정 생성

백엔드 API를 통해 첫 번째 관리자 계정 생성:

```bash
curl -X POST https://cpet-backend-xxxxx-an.a.run.app/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "your-secure-password",
    "role": "admin"
  }'
```

---

## 트러블슈팅

### Cloud Run 관련

**문제: "Cloud SQL connection failed"**
- Supabase는 Cloud SQL이 아님. DATABASE_URL이 Supabase URL인지 확인

**문제: "Connection refused" 또는 타임아웃**
- Supabase URL이 Transaction mode (포트 6543)인지 확인
- `postgresql+asyncpg://` 스키마 사용 확인

**문제: "ModuleNotFoundError: asyncpg"**
- Dockerfile에서 `asyncpg` 설치 확인
- requirements.txt에 `asyncpg==0.29.0` 추가

### Vercel 관련

**문제: API 호출 실패 (CORS)**
- Cloud Run의 `ALLOWED_ORIGINS`에 Vercel URL 추가 확인
- URL 끝에 `/` 없이 입력 (`https://cpet-data.vercel.app` ✓)

**문제: 환경변수가 적용 안 됨**
- Vite는 `VITE_` prefix가 필요
- 환경변수 변경 후 **Redeploy** 필요

### Supabase 관련

**문제: "FATAL: password authentication failed"**
- Database Password 재확인
- URL 인코딩 문제: 특수문자가 있으면 URL 인코딩 필요
  - `@` → `%40`
  - `#` → `%23`

**문제: "too many connections"**
- Transaction mode (포트 6543) 사용 확인
- Cloud Run min-instances를 0으로 설정하여 유휴 연결 해제

---

## 환경변수 요약

### Backend (Cloud Run)

| 환경변수 | 설명 | 예시 |
|----------|------|------|
| `DATABASE_URL` | Supabase 연결 문자열 | `postgresql+asyncpg://...` |
| `SECRET_KEY` | JWT 서명 키 (32자+) | `abc123...` |
| `DEBUG` | 디버그 모드 | `false` |
| `ALLOWED_ORIGINS` | CORS 허용 도메인 | `https://cpet.vercel.app` |

### Frontend (Vercel)

| 환경변수 | 설명 | 예시 |
|----------|------|------|
| `VITE_API_URL` | Backend API URL | `https://cpet-backend-xxx.run.app` |

---

## 비용 예상

| 서비스 | 무료 티어 | 예상 비용 |
|--------|-----------|-----------|
| **Supabase** | 500MB DB, 무제한 API | $0 (무료) |
| **Cloud Run** | 월 200만 요청, 360,000 GB-초 | $0~5 (소규모) |
| **Vercel** | 무제한 배포, 100GB 대역폭 | $0 (Hobby) |

**총 예상 비용: $0 ~ $5/월** (소규모 사용 기준)

---

## 배포 완료 체크리스트

- [ ] Supabase 프로젝트 생성 완료
- [ ] Supabase DATABASE_URL 저장
- [ ] Backend Dockerfile 생성
- [ ] Cloud Run 배포 완료
- [ ] Cloud Run URL 저장
- [ ] Vercel 프로젝트 생성
- [ ] Vercel VITE_API_URL 설정
- [ ] Vercel 배포 완료
- [ ] Cloud Run ALLOWED_ORIGINS 업데이트
- [ ] 전체 시스템 연동 테스트 완료
- [ ] Admin 계정 생성 완료
