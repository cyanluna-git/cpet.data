"""BreathData model - 호흡 데이터 (TimescaleDB Hypertable)"""

from datetime import datetime
from datetime import time as time_type
from typing import TYPE_CHECKING, Optional
import uuid

from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, Index, DateTime, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cpet_test import CPETTest


class BreathData(Base):
    """호흡 데이터 테이블 (TimescaleDB Hypertable)"""

    __tablename__ = "breath_data"

    # Composite primary key for TimescaleDB
    time: Mapped[datetime] = mapped_column(DateTime, primary_key=True, nullable=False)
    test_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cpet_tests.test_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    # Raw measurements from COSMED K5
    t_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rf: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Respiratory frequency
    vt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Tidal volume
    vo2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Oxygen consumption
    vco2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # CO2 production
    ve: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Minute ventilation
    hr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Heart rate
    vo2_hr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Oxygen pulse

    # Exercise load
    bike_power: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Watts
    bike_torque: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cadence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # RPM

    # Gas fractions
    feo2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feco2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feto2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fetco2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Ventilation ratios
    ve_vo2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ve_vco2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Calculated metrics
    rer: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Respiratory exchange ratio
    fat_oxidation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # g/min
    cho_oxidation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # g/min
    pro_oxidation: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # g/min
    vo2_rel: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # ml/kg/min
    mets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Energy expenditure
    ee_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ee_kcal_day: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Quality indicators
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    phase: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # Rest, Warmup, Exercise, Peak, Recovery
    raw_t_value: Mapped[Optional[time_type]] = mapped_column(Time, nullable=True)
    data_source: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # BxB or MIX

    # Relationships
    test: Mapped["CPETTest"] = relationship("CPETTest", back_populates="breath_data")

    __table_args__ = (
        Index("idx_breath_data_test_id", "test_id", "time"),
        Index("idx_breath_data_phase", "test_id", "phase"),
    )

    def __repr__(self) -> str:
        return f"<BreathData(test_id={self.test_id}, time={self.time}, hr={self.hr})>"
