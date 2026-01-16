"""Database connection and session management"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from app.core.config import settings

# Create async engine with connection pool settings
engine = create_async_engine(
    settings.database_url,
    echo=settings.DEBUG,
    future=True,
    # 연결 풀 설정 - 연속 요청에서 안정성 향상
    pool_size=10,          # 기본 연결 풀 크기
    max_overflow=20,       # 추가 연결 허용 수
    pool_timeout=30,       # 연결 대기 타임아웃
    pool_recycle=1800,     # 30분마다 연결 재활용 (stale 연결 방지)
    pool_pre_ping=True,    # 연결 사용 전 유효성 검사
)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


async def get_db() -> AsyncSession:
    """Dependency for getting database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
