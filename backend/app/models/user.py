"""User model - 사용자 계정 및 인증"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import String, Boolean, ForeignKey, Index, DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.subject import Subject


class User(Base):
    """사용자 계정 테이블"""

    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("subjects.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    subject: Mapped[Optional["Subject"]] = relationship(
        "Subject", back_populates="user"
    )

    __table_args__ = (Index("idx_users_subject_id", "subject_id"),)

    def __repr__(self) -> str:
        return f"<User(email={self.email}, role={self.role})>"
