"""ProcessedMetabolism Service - 전처리 대사 데이터 영속성 관리"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProcessedMetabolism
from app.services.metabolism_analysis import AnalysisConfig, MetabolismAnalyzer


class ProcessedMetabolismService:
    """Service for managing processed metabolism data persistence"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_test_id(self, test_id: UUID) -> Optional[ProcessedMetabolism]:
        """Get saved ProcessedMetabolism by test_id"""
        result = await self.db.execute(
            select(ProcessedMetabolism).where(
                ProcessedMetabolism.cpet_test_id == test_id
            )
        )
        return result.scalar_one_or_none()

    async def get_or_calculate(
        self, test_id: UUID, breath_data: List[Any]
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        Get saved data or calculate with defaults.

        Returns:
            Tuple of (result_dict, is_persisted)
            - result_dict: Analysis result as dictionary
            - is_persisted: True if loaded from DB, False if calculated on-the-fly
        """
        # Check for existing saved data
        existing = await self.get_by_test_id(test_id)
        if existing:
            return existing.to_dict(), True

        # Calculate with default config (don't save)
        result = self._calculate_analysis(breath_data, AnalysisConfig())
        return result, False

    async def save(
        self,
        test_id: UUID,
        breath_data: List[Any],
        config: AnalysisConfig,
        is_manual_override: bool = True,
    ) -> ProcessedMetabolism:
        """
        Calculate and save (upsert) processed metabolism data.

        Args:
            test_id: CPET test ID
            breath_data: List of BreathData objects
            config: Analysis configuration
            is_manual_override: Whether user manually saved these settings

        Returns:
            Saved ProcessedMetabolism record

        Raises:
            ValueError: If analysis fails due to insufficient data
        """
        # Calculate analysis
        analysis_result = self._calculate_analysis(breath_data, config)
        if analysis_result is None:
            raise ValueError("Analysis failed - insufficient data")

        # Check for existing record (upsert logic)
        existing = await self.get_by_test_id(test_id)

        if existing:
            record = existing
        else:
            record = ProcessedMetabolism(cpet_test_id=test_id)
            self.db.add(record)

        # Update configuration fields
        record.bin_size = config.bin_size
        record.aggregation_method = config.aggregation_method
        record.loess_frac = config.loess_frac
        record.smoothing_method = getattr(config, "smoothing_method", "loess")
        record.exclude_rest = config.exclude_rest
        record.exclude_warmup = config.exclude_warmup
        record.exclude_recovery = config.exclude_recovery
        record.min_power_threshold = config.min_power_threshold
        record.trim_start_sec = config.trim_start_sec
        record.trim_end_sec = config.trim_end_sec
        record.fatmax_zone_threshold = config.fatmax_zone_threshold
        record.is_manual_override = is_manual_override

        # Update processed data from analysis result
        ps = analysis_result.get("processed_series", {})
        record.raw_series = ps.get("raw")
        record.binned_series = ps.get("binned")
        record.smoothed_series = ps.get("smoothed")
        record.trend_series = ps.get("trend")

        # Update metabolic markers
        markers = analysis_result.get("metabolic_markers", {})
        fat_max = markers.get("fat_max", {})
        record.fatmax_power = fat_max.get("power")
        record.fatmax_mfo = fat_max.get("mfo")
        record.fatmax_zone_min = fat_max.get("zone_min")
        record.fatmax_zone_max = fat_max.get("zone_max")

        crossover = markers.get("crossover", {})
        record.crossover_power = crossover.get("power")
        record.crossover_fat_value = crossover.get("fat_value")
        record.crossover_cho_value = crossover.get("cho_value")

        # Update stats
        stats = analysis_result.get("stats", {})
        record.total_data_points = stats.get("total_data_points")
        record.exercise_data_points = stats.get("exercise_data_points")
        record.binned_data_points = stats.get("binned_data_points")

        # Update processing metadata
        record.processing_warnings = analysis_result.get("warnings")
        record.processing_status = "completed"
        record.processed_at = datetime.utcnow()
        record.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(record)

        return record

    async def delete(self, test_id: UUID) -> bool:
        """
        Delete saved ProcessedMetabolism for a test.

        Returns:
            True if deleted, False if not found
        """
        existing = await self.get_by_test_id(test_id)
        if not existing:
            return False

        await self.db.delete(existing)
        await self.db.commit()
        return True

    def _calculate_analysis(
        self, breath_data: List[Any], config: AnalysisConfig
    ) -> Optional[Dict[str, Any]]:
        """
        Run metabolism analysis and return result dict.

        Args:
            breath_data: List of BreathData objects
            config: Analysis configuration

        Returns:
            Analysis result as dictionary, or None if failed
        """
        analyzer = MetabolismAnalyzer(config=config)
        result = analyzer.analyze(breath_data)

        if result is None:
            return None

        # Convert to dict and add stats
        result_dict = result.to_dict()

        # Add stats from analysis
        result_dict["stats"] = {
            "total_data_points": len(breath_data),
            "exercise_data_points": len(result.processed_series.raw)
            if result.processed_series
            else 0,
            "binned_data_points": len(result.processed_series.binned)
            if result.processed_series
            else 0,
        }

        return result_dict
