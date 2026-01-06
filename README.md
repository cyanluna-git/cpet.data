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

## 개발 상태

현재 스켈레톤 구조가 완성되었으며, 다음 단계로 진행 예정:

- [ ] 데이터베이스 모델 구현
- [ ] API 엔드포인트 구현
- [ ] COSMED K5 파일 파서 개발
- [ ] 대사 지표 계산 엔진 개발
- [ ] 프론트엔드 컴포넌트 개발
- [ ] 인증 및 권한 관리
- [ ] 테스트 작성

## 문서

- [요구사항 정의서 (SRS)](./doc/srs.md)
- API 문서: http://localhost:8000/docs (서버 실행 시)

## 라이선스

MIT License

## 기여자

[작성자명]
