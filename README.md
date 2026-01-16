# CPET Database and Visualization Platform

대사 분석 데이터베이스 및 시각화 플랫폼 - COSMED K5 CPET 데이터 수집, 분석 및 시각화

## 프로젝트 개요

COSMED K5 장비에서 추출된 호흡 가스 분석 데이터(CPET)를 자동 수집하고 데이터베이스화하여, 피험자의 대사 프로파일(FATMAX, VO2MAX 등)을 분석하고 시각화하는 웹 기반 플랫폼입니다.

## 기술 스택

### Backend
- Python 3.11+
- FastAPI
- PostgreSQL 15+ with TimescaleDB Extension
- SQLAlchemy (Async)
- Pandas, NumPy, SciPy

### Frontend
- React 18+
- TypeScript
- Vite
- Recharts
- Axios

### Infrastructure
- Docker & Docker Compose
- PostgreSQL with TimescaleDB (Docker)

## 시작하기

### 사전 요구사항

- Python 3.11 이상
- Node.js 18 이상
- Docker & Docker Compose

### 설치 및 실행

#### 1. 데이터베이스 시작 (PostgreSQL + TimescaleDB)

```bash
docker-compose up -d
```

데이터베이스가 정상적으로 실행되었는지 확인:
```bash
docker ps
docker logs cpet-db
```

#### 2. Backend 설정 및 실행

```bash
# 백엔드 디렉토리로 이동
cd backend

# 가상환경 활성화
source venv/bin/activate  # macOS/Linux
# 또는
.\venv\Scripts\activate  # Windows

# 환경 변수 설정
cp .env.example .env
# .env 파일을 편집하여 필요한 설정 변경

# 서버 실행
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API 문서: http://localhost:8000/docs

#### 3. Frontend 설정 및 실행

```bash
# 프론트엔드 디렉토리로 이동
cd frontend

# 환경 변수 설정
cp .env.example .env

# 개발 서버 실행
npm run dev
```

애플리케이션: http://localhost:5173

## 프로젝트 구조

```
cpet.db/
├── backend/
│   ├── app/
│   │   ├── api/          # API 라우터
│   │   ├── core/         # 핵심 설정 (config, database)
│   │   ├── models/       # 데이터베이스 모델
│   │   ├── services/     # 비즈니스 로직
│   │   ├── utils/        # 유틸리티 함수
│   │   └── main.py       # FastAPI 엔트리포인트
│   ├── tests/            # 테스트
│   ├── venv/             # Python 가상환경
│   └── requirements.txt  # Python 패키지
├── frontend/
│   ├── src/
│   │   ├── components/   # React 컴포넌트
│   │   ├── pages/        # 페이지
│   │   ├── services/     # API 서비스
│   │   └── App.tsx       # 메인 앱
│   └── package.json      # Node 패키지
├── scripts/
│   └── init-db.sql       # 데이터베이스 초기화 스크립트
├── doc/
│   └── srs.md            # 요구사항 정의서
├── CPET_data/            # 샘플 데이터
└── docker-compose.yml    # Docker Compose 설정
```

## 주요 기능

- ✅ COSMED K5 Excel 파일 업로드 및 자동 파싱
- ✅ Breath-by-Breath (BxB) 및 Mixed (MIX) 프로토콜 지원
- ✅ 자동 구간 감지 (Rest, Warm-up, Exercise, Peak, Recovery)
- ✅ FATMAX 및 VO2MAX 자동 계산
- ✅ 지방/탄수화물 연소율 계산 (Frayn 공식)
- ✅ 인터랙티브 차트 시각화
- ✅ 시계열 데이터 비교
- ✅ 코호트 분석 및 통계
- ✅ Raw Data Viewer (피험자/테스트 필터, 컬럼 선택, CSV 다운로드)
- ✅ Raw Data 차트 프리셋 (FATMAX, RER, VO2 Kinetics, VT Analysis)

## 개발 상태

### 완료된 작업 ✅
- [x] 프로젝트 스켈레톤 구조 생성
- [x] Backend: FastAPI 기본 구조 및 설정
- [x] Frontend: React + TypeScript + Vite 초기화
- [x] Docker Compose: PostgreSQL + TimescaleDB 설정
- [x] Database 스키마 설계 (init-db.sql)
- [x] Git 저장소 초기화 및 GitHub 연결
- [x] 기본 문서 작성 (README, SRS)

### 진행 중인 작업 🚧
- 분석 전용 **정제/보간 데이터셋**(Processed Series) 설계
- 메타볼릭 차트용 전처리 파이프라인(구간 자르기, 파워 빈닝, 보간)
- 테스트 유형 자동 태깅

### 다음 단계
자세한 개발 로드맵은 [TODOS.md](./TODOS.md) 참조

## 데이터베이스 스키마

현재 구현된 테이블:
- `subjects`: 피험자/사용자 정보
- `cpet_tests`: 실험 메타데이터
- `breath_data`: 호흡 데이터 (TimescaleDB Hypertable)
- `cohort_stats`: 코호트 통계
- `users`: 사용자 계정 및 인증

추가 예정 (분석/차트 최적화용):
- `breath_data_processed`: 차트 전용 정제 데이터셋 (구간 자르기/빈닝/보간 결과)
- `analysis_tags`: 테스트 유형 및 분석 태깅 (cpet_tests 확장)

자세한 스키마는 [scripts/init-db.sql](./scripts/init-db.sql) 참조

## 주요 알고리즘

### 1. COSMED K5 파일 파싱
- Excel 파일 구조 자동 감지 (BxB vs MIX)
- 메타데이터 추출 (Row 1-10)
- 시계열 데이터 추출 (Row 12~)

### 2. 자동 구간 감지
Bike Power 기반:
- Rest: Power < 20W
- Warm-up: 일정한 낮은 부하
- Exercise: 계단식/선형 증가
- Peak: 최대 부하
- Recovery: 부하 급감

### 3. 대사 지표 계산
- RER = VCO2 / VO2
- Fat Oxidation (Frayn): 1.67 × VO2 - 1.67 × VCO2
- CHO Oxidation (Frayn): 4.55 × VCO2 - 3.21 × VO2
- FATMAX: 지방 연소량 최대 지점
- VO2MAX: 산소 섭취량 최대값

### 4. 차트 전처리 (계획)
- Phase trimming (Rest/Warm-up/Recovery 제거)
- Power binning (5–10W, median/trimmed mean)
- Shape-preserving interpolation (PCHIP/Akima) 또는 LOESS

## 문서

- [요구사항 정의서 (SRS)](./doc/srs.md)
- [개발 TODO 리스트](./TODOS.md)
- [에이전트 가이드](./agent.md.claude.md)
- [API 문서](http://localhost:8000/docs) (서버 실행 시)

## 기여 가이드

### 개발 환경 설정
1. 저장소 클론
```bash
git clone https://github.com/cyanluna-git/cpet.data.git
cd cpet.data
```

2. Backend 설정
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

3. Frontend 설정
```bash
cd frontend
npm install
cp .env.example .env
```

4. Database 시작
```bash
docker-compose up -d
```

### 커밋 메시지 규칙
- `feat:` 새로운 기능
- `fix:` 버그 수정
- `docs:` 문서 변경
- `refactor:` 코드 리팩토링
- `test:` 테스트 추가/수정
- `chore:` 빌드/설정 변경

## 라이선스

MIT License

## 저장소

GitHub: https://github.com/cyanluna-git/cpet.data
