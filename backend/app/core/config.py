"""Application configuration settings"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "CPET Platform"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://cpet_user:cpet_password@localhost:5432/cpet_db"

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ENCRYPTION_KEY: str = ""  # For encrypting PII data

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # File upload
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    UPLOAD_DIR: str = "./uploads"

    # Analysis settings
    DEFAULT_SMOOTHING_WINDOW: int = 10  # seconds
    DEFAULT_CALC_METHOD: str = "Frayn"  # or "Jeukendrup"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
