"""ProcessedMetabolism model - 가공된 대사 데이터 저장

CPET Raw 데이터에서 전처리된 결과를 저장하여 차트 렌더링 속도를 높이고 분석 재현성을 확보합니다.
"""

from datetime import datetime
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
    Uuid,
    JSON,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cpet_test import CPETTest


class ProcessedMetabolism(Base):
    """가공된 대사 데이터 테이블
    
    CPET 테스트의 원본 호흡 데이터를 처리하여 생성된 결과를 저장합니다.
    - Power binning (10W 단위 Median/Mean)
    - LOESS smoothing
    - FatMax, Crossover Point 마커
    """

    __tablename__ = "processed_metabolism"

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
    
    # Processing configuration (재현성을 위한 파라미터 기록)
    bin_size: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    aggregation_method: Mapped[str] = mapped_column(String(20), default="median", nullable=False)  # median, mean, trimmed_mean
    loess_frac: Mapped[float] = mapped_column(Float, default=0.25, nullable=False)
    smoothing_method: Mapped[str] = mapped_column(String(20), default="loess", nullable=False)  # loess, savgol, moving_avg
    
    # Phase trimming options
    exclude_rest: Mapped[bool] = mapped_column(Boolean, default=True)
    exclude_warmup: Mapped[bool] = mapped_column(Boolean, default=True)
    exclude_recovery: Mapped[bool] = mapped_column(Boolean, default=True)
    min_power_threshold: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # e.g., 50W 미만 제외

    # Time-based trimming (analysis window)
    trim_start_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    trim_end_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Manual override flag (사용자가 직접 저장한 경우 True)
    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False)

    # Processed data series (JSON 저장)
    raw_series: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)      # [{power, fat_oxidation, cho_oxidation}, ...]
    binned_series: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)   # 10W binned data
    smoothed_series: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True) # LOESS smoothed data
    trend_series: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)    # Polynomial trend data
    
    # FatMax marker
    fatmax_power: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # W
    fatmax_mfo: Mapped[Optional[float]] = mapped_column(Float, nullable=True)     # g/min (Maximum Fat Oxidation)
    fatmax_zone_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Zone 하한 (W)
    fatmax_zone_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Zone 상한 (W)
    fatmax_zone_threshold: Mapped[float] = mapped_column(Float, default=0.90)     # MFO 비율 (90%)
    
    # Crossover marker
    crossover_power: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # W
    crossover_fat_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # g/min
    crossover_cho_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # g/min
    
    # Additional metrics
    total_data_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    exercise_data_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    binned_data_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Processing info
    processing_warnings: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, completed, failed
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationship
    cpet_test: Mapped["CPETTest"] = relationship("CPETTest", backref="processed_metabolism")
    
    __table_args__ = (
        Index("idx_processed_metabolism_cpet_test_id", "cpet_test_id"),
        Index("idx_processed_metabolism_status", "processing_status"),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API response"""
        return {
            "id": str(self.id),
            "cpet_test_id": str(self.cpet_test_id),
            "config": {
                "bin_size": self.bin_size,
                "aggregation_method": self.aggregation_method,
                "loess_frac": self.loess_frac,
                "smoothing_method": self.smoothing_method,
                "exclude_rest": self.exclude_rest,
                "exclude_warmup": self.exclude_warmup,
                "exclude_recovery": self.exclude_recovery,
                "min_power_threshold": self.min_power_threshold,
                "trim_start_sec": self.trim_start_sec,
                "trim_end_sec": self.trim_end_sec,
                "fatmax_zone_threshold": self.fatmax_zone_threshold,
            },
            "is_manual_override": self.is_manual_override,
            "processed_series": {
                "raw": self.raw_series,
                "binned": self.binned_series,
                "smoothed": self.smoothed_series,
                "trend": self.trend_series,
            },
            "metabolic_markers": {
                "fat_max": {
                    "power": self.fatmax_power,
                    "mfo": self.fatmax_mfo,
                    "zone_min": self.fatmax_zone_min,
                    "zone_max": self.fatmax_zone_max,
                },
                "crossover": {
                    "power": self.crossover_power,
                    "fat_value": self.crossover_fat_value,
                    "cho_value": self.crossover_cho_value,
                },
            },
            "stats": {
                "total_data_points": self.total_data_points,
                "exercise_data_points": self.exercise_data_points,
                "binned_data_points": self.binned_data_points,
            },
            "processing_warnings": self.processing_warnings,
            "processing_status": self.processing_status,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self) -> str:
        return f"<ProcessedMetabolism(id={self.id}, test_id={self.cpet_test_id}, status={self.processing_status})>"
