# 프로덕션 배포 환경 구축

## 개요
CPET Platform을 프로덕션 환경에 배포하기 위해 Supabase(DB) + Google Cloud Run(백엔드) + Vercel(프론트엔드) 아키텍처를 구성했습니다. 로컬 PostgreSQL 데이터를 Supabase로 마이그레이션 완료했으며, 프론트엔드-백엔드 API 연결 문제를 디버깅 중입니다.

## 주요 변경사항

### 1. Google Cloud Run 백엔드 배포
- `backend/Dockerfile` 생성 (Python 3.12-slim 기반)
- `backend/.dockerignore` 생성
- `backend/requirements.txt`에 PostgreSQL 드라이버 추가 (asyncpg, psycopg2-binary)
- Cloud Run 배포 완료: `https://cpet-backend-633144088361.asia-northeast3.run.app`

### 2. Supabase 데이터베이스 마이그레이션
- 로컬 PostgreSQL → Supabase로 전체 데이터 이전
- subjects (18건), users (15건), cpet_tests (75건), breath_data (51,827건), processed_metabolism (5건)
- TimescaleDB hypertable → 일반 PostgreSQL 테이블 변환
- 스키마 차이 수정 (protocol_type varchar(10) → varchar(20))

### 3. Vercel 프론트엔드 설정
- `frontend/vite.config.ts` 수정: 환경변수 주입 방식 개선
- `VITE_API_URL` 환경변수를 통한 백엔드 URL 설정

### 4. 배포 가이드 문서화
- `docs/DEPLOYMENT_GUIDE.md` 생성

## 핵심 코드

```typescript
// frontend/vite.config.ts - 환경변수 주입
define: {
  'import.meta.env.VITE_API_URL': JSON.stringify(apiUrl),
}
```

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc libpq-dev
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
```

## 결과
- ✅ Cloud Run 백엔드 배포 성공
- ✅ Supabase 데이터 마이그레이션 완료
- ✅ Vercel 빌드 성공
- ⏳ 프론트엔드 API URL 주입 문제 해결 중

## 다음 단계
1. **Vercel 빌드 로그 확인**: `[vite.config] Building with API URL:` 메시지에서 올바른 URL이 출력되는지 확인
2. **환경변수 검증**: Vercel 대시보드에서 `VITE_API_URL` 설정 재확인
3. **API 연결 테스트**: 프론트엔드에서 Cloud Run 백엔드로 요청이 정상적으로 가는지 확인
4. **CORS 설정 검증**: 필요시 Cloud Run의 CORS 설정 조정
