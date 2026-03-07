"""INSCYD report API routes."""

from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUser, DBSession, ResearcherUser
from app.models import Subject
from app.schemas.inscyd import InscydReportResponse, InscydUploadAutoResponse
from app.services.inscyd import InscydService

router = APIRouter(prefix="/inscyd", tags=["INSCYD"])


@router.post(
    "/upload-auto",
    response_model=InscydUploadAutoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_inscyd_auto(
    db: DBSession,
    current_user: CurrentUser,
    file: UploadFile = File(..., description="INSCYD PDF report"),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported for INSCYD upload",
        )

    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds 20MB limit",
        )

    service = InscydService(db)

    if current_user.role in ("user", "subject"):
        if current_user.subject_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No subject profile linked to your account",
            )
        subject_id = current_user.subject_id
        subject_created = False
        subject = await db.get(Subject, subject_id)
        subject_name = (
            subject.encrypted_name or subject.research_id if subject else current_user.email
        )
    else:
        import os
        import tempfile
        from pathlib import Path
        from app.services.inscyd_parser import InscydParser

        suffix = Path(file.filename).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        try:
            preview = InscydParser().parse_file(tmp_path)
        finally:
            os.unlink(tmp_path)

        subject, subject_created = await service.find_or_create_subject_from_athlete(
            preview.athlete_name or ""
        )
        subject_id = subject.id
        subject_name = subject.encrypted_name or subject.research_id

    report = await service.upload_and_parse(
        file_content=contents,
        filename=file.filename,
        subject_id=subject_id,
    )

    return InscydUploadAutoResponse(
        report_id=report.report_id,
        subject_id=report.subject_id,
        subject_created=subject_created,
        subject_name=subject_name,
        source_filename=file.filename,
        parsing_status=report.parsing_status,
        parsing_warnings=report.parsing_warnings,
        created_at=report.created_at,
    )


@router.get(
    "/subject/{subject_id}",
    response_model=list[InscydReportResponse],
)
async def list_subject_inscyd_reports(
    subject_id: UUID,
    db: DBSession,
    current_user: ResearcherUser,
):
    service = InscydService(db)
    reports = await service.get_by_subject(subject_id)
    return [InscydReportResponse.model_validate(report) for report in reports]
