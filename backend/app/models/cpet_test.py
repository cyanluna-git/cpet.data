"""CPETTest model - CPET 테스트 메타데이터"""

from datetime import datetime
from datetime import time as time_type
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import (
    String,
    Integer,
    Float,
    Text,
    ForeignKey,
    Index,
    DateTime,
    Time,
    Uuid,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.subject import Subject
    from app.models.breath_data import BreathData


class CPETTest(Base):
    """CPET 테스트 메타데이터 테이블"""

    __tablename__ = "cpet_tests"

    test_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
    )
    test_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    test_time: Mapped[Optional[time_type]] = mapped_column(Time, nullable=True)
    protocol_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    protocol_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    test_type: Mapped[str] = mapped_column(String(20), default="Maximal")
    maximal_effort: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    test_duration: Mapped[Optional[time_type]] = mapped_column(Time, nullable=True)
    exercise_duration: Mapped[Optional[time_type]] = mapped_column(Time, nullable=True)

    # Environmental conditions
    barometric_pressure: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ambient_temp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ambient_humidity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    device_temp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Body measurements at test time
    weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bsa: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bmi: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Main analysis results
    vo2_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vo2_max_rel: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vco2_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hr_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # FATMAX related
    fat_max_hr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fat_max_watt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat_max_g_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Threshold related
    vt1_hr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    vt1_vo2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vt2_hr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    vt2_vo2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Analysis configuration
    calc_method: Mapped[str] = mapped_column(String(20), default="Frayn")
    smoothing_window: Mapped[int] = mapped_column(Integer, default=10)

    # Phase information
    warmup_end_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    test_end_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # File tracking
    source_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_upload_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    parsing_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    parsing_errors: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Other
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    subject: Mapped["Subject"] = relationship("Subject", back_populates="tests")
    breath_data: Mapped[list["BreathData"]] = relationship(
        "BreathData", back_populates="test", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_cpet_tests_subject_id", "subject_id"),
        Index("idx_cpet_tests_test_date", "test_date"),
        Index("idx_cpet_tests_subject_date", "subject_id", "test_date"),
    )

    def __repr__(self) -> str:
        return f"<CPETTest(test_id={self.test_id}, subject_id={self.subject_id}, date={self.test_date})>"
