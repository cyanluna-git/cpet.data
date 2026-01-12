"""Application configuration settings"""

from pathlib import Path
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

# 프로젝트 루트 경로 (backend의 부모 디렉토리)
ROOT_DIR = Path(__file__).parent.parent.parent.parent
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        case_sensitive=True,
        extra="ignore",
    )

    # Database - SQLite default
    SQLITE_DB_PATH: str = "cpet.db"

    # Database URL (직접 지정하거나 자동 생성)
    DATABASE_URL: Optional[str] = None

    @computed_field
    @property
    def database_url(self) -> str:
        """DATABASE_URL 생성"""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"sqlite+aiosqlite:///./{self.SQLITE_DB_PATH}"

    # Backend Server
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8100

    # Application
    APP_NAME: str = "CPET Platform"
    DEBUG: bool = False

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ENCRYPTION_KEY: str = ""

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3100"

    @computed_field
    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse ALLOWED_ORIGINS as a list"""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    # File upload
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    UPLOAD_DIR: str = "./uploads"

    # Analysis settings
    DEFAULT_SMOOTHING_WINDOW: int = 10
    DEFAULT_CALC_METHOD: str = "Frayn"

    # Frontend
    FRONTEND_PORT: int = 3100


settings = Settings()
