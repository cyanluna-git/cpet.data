"""
server.schemas — Pydantic models for API request/response contracts.
"""

from typing import Literal

from pydantic import BaseModel


class SubmissionCreate(BaseModel):
    """Payload for creating a new submission."""

    description: str
    subject_name: str = ""
    test_date: str = ""


class JobStatus(BaseModel):
    """Job status response."""

    id: str
    submission_id: str
    status: Literal["pending", "processing", "done", "failed"]
    report_url: str | None = None
    error_message: str | None = None
    created_at: str
    completed_at: str | None = None


class ReportSummary(BaseModel):
    """Summary of a published report."""

    slug: str
    subject_name: str
    test_date: str
    report_url: str
