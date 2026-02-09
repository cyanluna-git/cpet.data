"""ProcessedMetabolism Schemas - 전처리된 대사 데이터 스키마"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class MetabolismConfig(BaseModel):
    """Analysis configuration for metabolism processing"""

    # Binning parameters
    bin_size: int = Field(default=10, ge=5, le=30, description="Power binning size (W)")
    aggregation_method: Literal["median", "mean", "trimmed_mean"] = Field(
        default="median", description="Aggregation method for binning"
    )

    # Smoothing parameters
    loess_frac: float = Field(
        default=0.25, ge=0.1, le=0.5, description="LOESS smoothing fraction"
    )
    smoothing_method: Literal["loess", "savgol", "moving_avg"] = Field(
        default="loess", description="Smoothing method"
    )

    # Phase trimming
    exclude_rest: bool = Field(default=True, description="Exclude Rest phase")
    exclude_warmup: bool = Field(default=True, description="Exclude Warmup phase")
    exclude_recovery: bool = Field(default=True, description="Exclude Recovery phase")
    min_power_threshold: Optional[int] = Field(
        default=None, ge=0, le=200, description="Minimum power threshold (W)"
    )

    # Time-based trimming (analysis window)
    trim_start_sec: Optional[float] = Field(
        default=None, ge=0, description="Manual trim start (seconds)"
    )
    trim_end_sec: Optional[float] = Field(
        default=None, ge=0, description="Manual trim end (seconds)"
    )

    # FatMax zone
    fatmax_zone_threshold: float = Field(
        default=0.90, ge=0.5, le=1.0, description="FatMax zone threshold (% of MFO)"
    )

    # v1.1.0: Outlier detection
    outlier_detection_enabled: bool = Field(
        default=True, description="Enable IQR-based outlier detection"
    )
    outlier_iqr_multiplier: float = Field(
        default=1.5, ge=1.0, le=3.0, description="IQR multiplier for outlier bounds"
    )

    # v1.1.0: Sparse bin merging
    min_bin_count: int = Field(
        default=3, ge=1, le=10, description="Minimum data points per bin"
    )

    # v1.1.0: Adaptive LOESS
    adaptive_loess: bool = Field(
        default=True, description="Auto-adjust LOESS fraction based on data size"
    )

    # v1.1.0: Protocol-aware trimming
    protocol_type: Optional[str] = Field(
        default=None, description="Protocol type: ramp, step, graded, or null"
    )

    # v1.1.0: Adaptive polynomial degree
    adaptive_polynomial: bool = Field(
        default=True, description="Use cross-validation for polynomial degree selection"
    )

    # v1.1.0: FatMax bootstrap CI
    fatmax_confidence_interval: bool = Field(
        default=False, description="Calculate bootstrap confidence interval for FatMax"
    )
    fatmax_bootstrap_iterations: int = Field(
        default=500, ge=100, le=5000, description="Number of bootstrap iterations"
    )

    @model_validator(mode="after")
    def validate_trim_range(self) -> "MetabolismConfig":
        """Ensure trim_end > trim_start and minimum 180 seconds duration"""
        if self.trim_start_sec is not None and self.trim_end_sec is not None:
            if self.trim_end_sec <= self.trim_start_sec:
                raise ValueError("trim_end_sec must be greater than trim_start_sec")
            duration = self.trim_end_sec - self.trim_start_sec
            if duration < 180:
                raise ValueError(
                    f"Trim range must be at least 180 seconds (got {duration:.1f}s)"
                )
        return self


class ProcessedMetabolismCreate(BaseModel):
    """Request schema for creating/updating processed metabolism"""

    config: MetabolismConfig
    is_manual_override: bool = Field(
        default=True, description="Mark as manually configured"
    )


class ProcessedMetabolismResponse(BaseModel):
    """Response schema for processed metabolism data"""

    id: Optional[UUID] = None
    cpet_test_id: UUID

    # Configuration used
    config: MetabolismConfig
    is_manual_override: bool = False

    # Processed series data
    processed_series: Optional[Dict[str, Any]] = Field(
        default=None, description="Processed data series (raw, binned, smoothed, trend)"
    )

    # Metabolic markers
    metabolic_markers: Optional[Dict[str, Any]] = Field(
        default=None, description="Metabolic markers (fat_max, crossover)"
    )

    # Stats
    stats: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Statistics (total_data_points, exercise_data_points, binned_data_points)",
    )

    # Trim range info (from analysis result)
    trim_range: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Applied trim range (start_sec, end_sec, auto_detected, max_power_sec)",
    )

    # Processing metadata
    processing_warnings: Optional[List[str]] = Field(
        default=None, description="Warnings from processing"
    )
    processing_status: str = Field(default="pending", description="Processing status")
    processed_at: Optional[datetime] = Field(
        default=None, description="When processing completed"
    )

    # Algorithm version for reproducibility
    algorithm_version: str = Field(
        default="1.0.0", description="Algorithm version used for processing (read-only)"
    )

    # Persistence state
    is_persisted: bool = Field(
        default=False, description="Whether this data is saved to database"
    )

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
