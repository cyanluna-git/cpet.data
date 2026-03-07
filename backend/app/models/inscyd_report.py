"""INSCYD metabolic profile report model."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.subject import Subject


class InscydReport(Base):
    """Structured INSCYD PDF report data."""

    __tablename__ = "inscyd_reports"

    report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
    )

    external_test_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    report_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    sport: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    test_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    athlete_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    coach_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    body_mass_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    body_height_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    body_mass_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    projected_bsa_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    body_fat_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    body_fat_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat_free_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat_free_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    vo2max_abs_ml_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vo2max_rel_ml_kg_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vlamax_mmol_l_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mfo_abs_kcal_h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mfo_rel_kcal_h_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fatmax_watt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbmax_abs_watt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbmax_rel_w_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    at_abs_watt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    at_rel_w_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    at_pct_vo2max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    glycogen_abs_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    glycogen_rel_g_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hr_max_bpm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pwc150_watt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    training_zones: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    test_data_rows: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    weighted_regression: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    raw_sections: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_upload_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    parsing_status: Mapped[str] = mapped_column(String(50), default="success")
    parsing_warnings: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    subject: Mapped["Subject"] = relationship("Subject", back_populates="inscyd_reports")

    __table_args__ = (
        Index("idx_inscyd_reports_subject_id", "subject_id"),
        Index("idx_inscyd_reports_report_date", "report_date"),
        Index("idx_inscyd_reports_subject_date", "subject_id", "report_date"),
    )
