"""Energy System API Router - 3-pathway 에너지 시스템 분석 API"""

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession, ResearcherUser
from app.models import BreathData, CPETTest, ProcessedMetabolism
from app.models.blood_sample import BloodSample
from app.services.energy_system_analysis import (
    EnergySystemAnalyzer,
    RecoveryWindow,
)

router = APIRouter(
    prefix="/tests/{test_id}/energy-system", tags=["Energy System"]
)


class EnergySystemResponse(BaseModel):
    """Energy system analysis response"""

    pathways: list[Dict[str, Any]] = Field(
        ..., description="Energy pathway results (name, energy_kj, percentage, color)"
    )
    total_kj: Optional[float] = Field(None, description="Total energy (kJ)")
    has_lactate: bool = Field(False, description="Whether lactate data was available")
    has_phosphagen: bool = Field(
        False, description="Whether phosphagen could be calculated"
    )
    delta_lactate: Optional[float] = Field(
        None, description="Peak - resting lactate (mmol/L)"
    )
    exercise_duration_sec: Optional[float] = None
    body_weight_kg: Optional[float] = None
    mono_exp_fit: Optional[Dict[str, Any]] = Field(
        None, description="Mono-exponential fit parameters"
    )
    recovery_window: Optional[Dict[str, Any]] = Field(
        None, description="Recovery phase window used"
    )
    warnings: list[str] = Field(default_factory=list)


class EnergySystemRequest(BaseModel):
    """Energy system analysis request (optional overrides)"""

    recovery_start_sec: Optional[float] = Field(
        None, ge=0, description="Manual recovery start (seconds)"
    )
    recovery_end_sec: Optional[float] = Field(
        None, ge=0, description="Manual recovery end (seconds)"
    )
    exercise_start_sec: Optional[float] = Field(
        None, ge=0, description="Manual exercise start (seconds)"
    )
    exercise_end_sec: Optional[float] = Field(
        None, ge=0, description="Manual exercise end (seconds)"
    )
    save: bool = Field(
        default=False,
        description="Whether to save results to processed_metabolism.energy_system",
    )


@router.get("", response_model=EnergySystemResponse)
async def get_energy_system(
    test_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> EnergySystemResponse:
    """
    Get energy system analysis for a test.

    Returns saved results if available, otherwise calculates on the fly.
    Results include oxidative, glycolytic (if lactate data exists),
    and phosphagen (if recovery data is sufficient) pathways.
    """
    test = await _get_test_with_access_check(db, test_id, current_user)

    # Check for saved results in processed_metabolism
    pm_result = await db.execute(
        select(ProcessedMetabolism).where(
            ProcessedMetabolism.cpet_test_id == test_id
        )
    )
    pm = pm_result.scalar_one_or_none()

    if pm and pm.energy_system:
        return EnergySystemResponse(**pm.energy_system)

    # Calculate on the fly
    result = await _calculate_energy_system(db, test_id, test)
    return EnergySystemResponse(**result.to_dict())


@router.post("", response_model=EnergySystemResponse, status_code=status.HTTP_200_OK)
async def calculate_energy_system(
    test_id: UUID,
    data: EnergySystemRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> EnergySystemResponse:
    """
    Calculate energy system analysis with optional overrides.

    Supports manual recovery window override for better phosphagen estimation.
    Set save=true (researcher+ only) to persist results.
    """
    test = await _get_test_with_access_check(db, test_id, current_user)

    # Build recovery override
    recovery_override = None
    if data.recovery_start_sec is not None and data.recovery_end_sec is not None:
        if data.recovery_end_sec <= data.recovery_start_sec:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="recovery_end_sec must be greater than recovery_start_sec",
            )
        recovery_override = RecoveryWindow(
            start_sec=data.recovery_start_sec,
            end_sec=data.recovery_end_sec,
            is_manual_override=True,
        )

    result = await _calculate_energy_system(
        db,
        test_id,
        test,
        recovery_override=recovery_override,
        exercise_start_sec=data.exercise_start_sec,
        exercise_end_sec=data.exercise_end_sec,
    )

    # Save if requested (researcher+ only)
    if data.save:
        if current_user.role not in ("admin", "researcher"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only researchers or admins can save energy system results",
            )

        pm_result = await db.execute(
            select(ProcessedMetabolism).where(
                ProcessedMetabolism.cpet_test_id == test_id
            )
        )
        pm = pm_result.scalar_one_or_none()

        if pm:
            pm.energy_system = result.to_dict()
            await db.commit()
        else:
            # No processed_metabolism record yet; cannot save standalone
            result.warnings.append(
                "No processed_metabolism record exists. "
                "Run substrate analysis first, then save energy system."
            )

    return EnergySystemResponse(**result.to_dict())


# ============ Helper Functions ============


async def _get_test_with_access_check(
    db: DBSession, test_id: UUID, user: CurrentUser
) -> CPETTest:
    """Get test and verify user access"""
    result = await db.execute(select(CPETTest).where(CPETTest.test_id == test_id))
    test = result.scalar_one_or_none()

    if not test:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test not found",
        )

    if user.role in ("user", "subject"):
        if test.subject_id != user.subject_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    return test


async def _calculate_energy_system(
    db: DBSession,
    test_id: UUID,
    test: CPETTest,
    recovery_override: Optional[RecoveryWindow] = None,
    exercise_start_sec: Optional[float] = None,
    exercise_end_sec: Optional[float] = None,
):
    """Calculate energy system analysis for a test."""
    # Get breath data
    result = await db.execute(
        select(BreathData)
        .where(BreathData.test_id == test_id)
        .order_by(BreathData.t_sec)
    )
    breath_data = list(result.scalars().all())

    if not breath_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No breath data found for this test",
        )

    # Get blood samples for lactate
    bs_result = await db.execute(
        select(BloodSample)
        .where(BloodSample.cpet_test_id == test_id)
        .order_by(BloodSample.elapsed_sec.asc().nullslast())
    )
    blood_samples = list(bs_result.scalars().all())

    # Extract lactate values
    resting_lactate = None
    peak_lactate = None
    if blood_samples:
        lactate_values = [
            s.lactate_mmol for s in blood_samples if s.lactate_mmol is not None
        ]
        resting_samples = [
            s.lactate_mmol
            for s in blood_samples
            if s.block == "rest" and s.lactate_mmol is not None
        ]
        if resting_samples:
            resting_lactate = resting_samples[0]
        if lactate_values:
            peak_lactate = max(lactate_values)

    # Get body weight
    body_weight_kg = test.weight_kg

    # Use exercise window from test if available
    if exercise_start_sec is None and test.warmup_end_sec is not None:
        exercise_start_sec = float(test.warmup_end_sec)
    if exercise_end_sec is None and test.test_end_sec is not None:
        exercise_end_sec = float(test.test_end_sec)

    # Run analysis
    analyzer = EnergySystemAnalyzer()
    return analyzer.analyze(
        breath_data=breath_data,
        body_weight_kg=body_weight_kg,
        resting_lactate=resting_lactate,
        peak_lactate=peak_lactate,
        recovery_override=recovery_override,
        exercise_start_sec=exercise_start_sec,
        exercise_end_sec=exercise_end_sec,
    )
