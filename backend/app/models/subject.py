"""Subject model - 피험자 정보"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import String, Integer, Float, Text, Index, DateTime, Uuid, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cpet_test import CPETTest
    from app.models.user import User


class Subject(Base):
    """피험자/사용자 정보 테이블"""

    __tablename__ = "subjects"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    research_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    encrypted_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    birth_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    job_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    medical_history: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    training_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    height_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    tests: Mapped[list["CPETTest"]] = relationship(
        "CPETTest", back_populates="subject", cascade="all, delete-orphan"
    )
    user: Mapped[Optional["User"]] = relationship("User", back_populates="subject")

    __table_args__ = (Index("idx_subjects_gender_birth_year", "gender", "birth_year"),)

    def __repr__(self) -> str:
        return f"<Subject(research_id={self.research_id})>"
