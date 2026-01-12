"""CohortStats model - 코호트 통계"""

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import String, Integer, Float, UniqueConstraint, Index, DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CohortStats(Base):
    """코호트 통계 테이블"""

    __tablename__ = "cohort_stats"

    stat_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    age_group: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    training_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Statistical values
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False)
    mean_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    median_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    std_dev: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percentile_10: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percentile_25: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percentile_75: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percentile_90: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    sample_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "gender",
            "age_group",
            "training_level",
            "metric_name",
            name="uq_cohort_stats_lookup",
        ),
        Index(
            "idx_cohort_stats_lookup",
            "gender",
            "age_group",
            "training_level",
            "metric_name",
        ),
    )

    def __repr__(self) -> str:
        return f"<CohortStats(metric={self.metric_name}, gender={self.gender}, age_group={self.age_group})>"
