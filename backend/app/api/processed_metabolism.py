"""Processed Metabolism API Router - 전처리 대사 데이터 API"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, ResearcherUser
from app.models import BreathData, CPETTest
from app.schemas.processed_metabolism import (
    MetabolismConfig,
    ProcessedMetabolismCreate,
    ProcessedMetabolismResponse,
)
from app.services.metabolism_analysis import AnalysisConfig
from app.services.processed_metabolism import ProcessedMetabolismService

router = APIRouter(
    prefix="/tests/{test_id}/processed-metabolism", tags=["Processed Metabolism"]
)


@router.get("", response_model=ProcessedMetabolismResponse)
async def get_processed_metabolism(
    test_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """
    Get processed metabolism data for a test.

    - Returns saved data if available (is_persisted=true)
    - Otherwise calculates with defaults and returns without saving (is_persisted=false)

    This allows users to preview analysis before committing to save.
    """
    # Verify test exists and user has access
    test = await _get_test_with_access_check(db, test_id, current_user)

    # Get breath data
    breath_data = await _get_breath_data(db, test_id)
    if not breath_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No breath data found for this test",
        )

    service = ProcessedMetabolismService(db)
    result_dict, is_persisted = await service.get_or_calculate(test_id, breath_data)

    if result_dict is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Insufficient data for analysis",
        )

    # Build response
    return _build_response(test_id, result_dict, is_persisted)


@router.post("", response_model=ProcessedMetabolismResponse, status_code=status.HTTP_201_CREATED)
async def save_processed_metabolism(
    test_id: UUID,
    data: ProcessedMetabolismCreate,
    db: DBSession,
    current_user: ResearcherUser,  # Researcher+ required for saving
):
    """
    Save/upsert processed metabolism configuration and results.

    - Validates trim range (end > start, minimum 180s duration)
    - Calculates analysis with provided config
    - Saves to database (upserts if exists)

    Only Researcher or Admin users can save configurations.
    """
    # Verify test exists and user has access
    test = await _get_test_with_access_check(db, test_id, current_user)

    # Get breath data
    breath_data = await _get_breath_data(db, test_id)
    if not breath_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No breath data found for this test",
        )

    # Convert schema to AnalysisConfig
    config = _schema_to_analysis_config(data.config)

    service = ProcessedMetabolismService(db)

    try:
        record = await service.save(
            test_id=test_id,
            breath_data=breath_data,
            config=config,
            is_manual_override=data.is_manual_override,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    return _build_response_from_model(record, is_persisted=True)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_processed_metabolism(
    test_id: UUID,
    db: DBSession,
    current_user: ResearcherUser,  # Researcher+ required for deletion
):
    """
    Delete saved processed metabolism record.

    After deletion, GET will return calculated defaults with is_persisted=false.
    Only Researcher or Admin users can delete saved configurations.
    """
    # Verify test exists
    await _get_test_with_access_check(db, test_id, current_user)

    service = ProcessedMetabolismService(db)
    deleted = await service.delete(test_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No saved processed metabolism found for this test",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============ Helper Functions ============


async def _get_test_with_access_check(db: DBSession, test_id: UUID, user) -> CPETTest:
    """Get test and verify user access"""
    result = await db.execute(select(CPETTest).where(CPETTest.test_id == test_id))
    test = result.scalar_one_or_none()

    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found",
        )

    # Subject users can only access their own tests
    if user.role == "subject":
        if test.subject_id != user.subject_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    return test


async def _get_breath_data(db: DBSession, test_id: UUID) -> list:
    """Get breath data for a test"""
    result = await db.execute(
        select(BreathData)
        .where(BreathData.test_id == test_id)
        .order_by(BreathData.t_sec)
    )
    return list(result.scalars().all())


def _schema_to_analysis_config(config: MetabolismConfig) -> AnalysisConfig:
    """Convert Pydantic schema to AnalysisConfig dataclass"""
    return AnalysisConfig(
        bin_size=config.bin_size,
        aggregation_method=config.aggregation_method,
        loess_frac=config.loess_frac,
        fatmax_zone_threshold=config.fatmax_zone_threshold,
        exclude_rest=config.exclude_rest,
        exclude_warmup=config.exclude_warmup,
        exclude_recovery=config.exclude_recovery,
        min_power_threshold=config.min_power_threshold,
        trim_start_sec=config.trim_start_sec,
        trim_end_sec=config.trim_end_sec,
        # Enable auto-trim only if no manual trim is specified
        auto_trim_enabled=(config.trim_start_sec is None and config.trim_end_sec is None),
    )


def _build_response(
    test_id: UUID, result_dict: dict, is_persisted: bool
) -> ProcessedMetabolismResponse:
    """Build response from result dict"""
    config_dict = result_dict.get("config", {})

    return ProcessedMetabolismResponse(
        id=result_dict.get("id"),
        cpet_test_id=test_id,
        config=MetabolismConfig(
            bin_size=config_dict.get("bin_size", 10),
            aggregation_method=config_dict.get("aggregation_method", "median"),
            loess_frac=config_dict.get("loess_frac", 0.25),
            smoothing_method=config_dict.get("smoothing_method", "loess"),
            exclude_rest=config_dict.get("exclude_rest", True),
            exclude_warmup=config_dict.get("exclude_warmup", True),
            exclude_recovery=config_dict.get("exclude_recovery", True),
            min_power_threshold=config_dict.get("min_power_threshold"),
            trim_start_sec=config_dict.get("trim_start_sec"),
            trim_end_sec=config_dict.get("trim_end_sec"),
            fatmax_zone_threshold=config_dict.get("fatmax_zone_threshold", 0.90),
        ),
        is_manual_override=result_dict.get("is_manual_override", False),
        processed_series=result_dict.get("processed_series"),
        metabolic_markers=result_dict.get("metabolic_markers"),
        stats=result_dict.get("stats"),
        trim_range=result_dict.get("trim_range"),
        processing_warnings=result_dict.get("warnings"),
        processing_status=result_dict.get("processing_status", "completed"),
        processed_at=result_dict.get("processed_at"),
        algorithm_version=result_dict.get("algorithm_version", "1.0.0"),
        is_persisted=is_persisted,
        created_at=result_dict.get("created_at"),
        updated_at=result_dict.get("updated_at"),
    )


def _build_response_from_model(record, is_persisted: bool) -> ProcessedMetabolismResponse:
    """Build response from model instance"""
    return _build_response(record.cpet_test_id, record.to_dict(), is_persisted)
