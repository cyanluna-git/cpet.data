"""BloodSample model - 혈액 샘플 데이터 (lactate/glucose)"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cpet_test import CPETTest


class BloodSample(Base):
    """혈액 샘플 테이블 (lactate/glucose 측정 데이터)"""

    __tablename__ = "blood_samples"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    cpet_test_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cpet_tests.test_id", ondelete="CASCADE"),
        nullable=False,
    )

    # Sample identification
    block: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    step: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Exercise load
    load_w: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ftp_pct: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    duration_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Timing
    sample_time_kst: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    elapsed_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Measurements
    hr_bpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lactate_mmol: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    glucose_mmol: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationship
    cpet_test: Mapped["CPETTest"] = relationship(
        "CPETTest", back_populates="blood_samples"
    )

    __table_args__ = (
        Index("idx_blood_samples_cpet_test_id", "cpet_test_id"),
        Index("idx_blood_samples_block", "cpet_test_id", "block"),
    )

    def __repr__(self) -> str:
        return (
            f"<BloodSample(id={self.id}, test_id={self.cpet_test_id}, "
            f"lactate={self.lactate_mmol}, block={self.block})>"
        )
