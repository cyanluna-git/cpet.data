"""Blood Samples API Router - 혈액 샘플 (lactate/glucose) CRUD API"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, select

from app.api.deps import CurrentUser, DBSession, ResearcherUser
from app.models import CPETTest
from app.models.blood_sample import BloodSample
from app.schemas.blood_sample import (
    BloodSampleBulkCreate,
    BloodSampleCreate,
    BloodSampleListResponse,
    BloodSampleResponse,
)

router = APIRouter(
    prefix="/tests/{test_id}/blood-samples", tags=["Blood Samples"]
)


@router.get("", response_model=BloodSampleListResponse)
async def get_blood_samples(
    test_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> BloodSampleListResponse:
    """
    Get blood samples for a test.

    Returns all blood sample measurements (lactate, glucose, HR) with
    derived metrics (resting, peak, delta lactate).
    """
    await _verify_test_access(db, test_id, current_user)

    result = await db.execute(
        select(BloodSample)
        .where(BloodSample.cpet_test_id == test_id)
        .order_by(BloodSample.elapsed_sec.asc().nullslast(), BloodSample.step.asc())
    )
    samples = list(result.scalars().all())

    # Derive lactate metrics
    lactate_values = [s.lactate_mmol for s in samples if s.lactate_mmol is not None]
    resting_samples = [
        s.lactate_mmol for s in samples
        if s.block == "rest" and s.lactate_mmol is not None
    ]

    resting_lactate = resting_samples[0] if resting_samples else None
    peak_lactate = max(lactate_values) if lactate_values else None
    delta_lactate = (
        peak_lactate - resting_lactate
        if peak_lactate is not None and resting_lactate is not None
        else None
    )

    return BloodSampleListResponse(
        cpet_test_id=test_id,
        samples=[BloodSampleResponse.model_validate(s) for s in samples],
        total=len(samples),
        resting_lactate=resting_lactate,
        peak_lactate=peak_lactate,
        delta_lactate=delta_lactate,
    )


@router.post(
    "",
    response_model=List[BloodSampleResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_blood_samples(
    test_id: UUID,
    data: BloodSampleBulkCreate,
    db: DBSession,
    current_user: ResearcherUser,
) -> List[BloodSampleResponse]:
    """
    Create blood samples for a test (bulk).

    Only Researcher or Admin users can create blood samples.
    """
    await _verify_test_access(db, test_id, current_user)

    created: list[BloodSample] = []
    for sample_data in data.samples:
        sample = BloodSample(
            cpet_test_id=test_id,
            **sample_data.model_dump(),
        )
        db.add(sample)
        created.append(sample)

    await db.commit()
    for s in created:
        await db.refresh(s)

    return [BloodSampleResponse.model_validate(s) for s in created]


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_all_blood_samples(
    test_id: UUID,
    db: DBSession,
    current_user: ResearcherUser,
) -> Response:
    """
    Delete all blood samples for a test.

    Only Researcher or Admin users can delete blood samples.
    """
    await _verify_test_access(db, test_id, current_user)

    await db.execute(
        delete(BloodSample).where(BloodSample.cpet_test_id == test_id)
    )
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{sample_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_blood_sample(
    test_id: UUID,
    sample_id: UUID,
    db: DBSession,
    current_user: ResearcherUser,
) -> Response:
    """
    Delete a single blood sample.

    Only Researcher or Admin users can delete blood samples.
    """
    await _verify_test_access(db, test_id, current_user)

    result = await db.execute(
        select(BloodSample).where(
            BloodSample.id == sample_id,
            BloodSample.cpet_test_id == test_id,
        )
    )
    sample = result.scalar_one_or_none()

    if not sample:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blood sample not found",
        )

    await db.delete(sample)
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============ Helper Functions ============


async def _verify_test_access(db: DBSession, test_id: UUID, user: CurrentUser) -> CPETTest:
    """Verify test exists and user has access"""
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
