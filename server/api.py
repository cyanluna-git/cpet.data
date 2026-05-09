"""
server.api — REST endpoints for CPET submission and job management.

Endpoints:
    POST /api/submit       — Upload files and create a new job
    GET  /api/jobs          — List jobs (optional status filter)
    GET  /api/jobs/partial  — HTMX partial for job list
    GET  /api/jobs/{job_id} — Get a single job by ID
"""

import logging
import json
import sqlite3
import uuid
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import threading

import httpx
from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from server.db import (
    create_job,
    create_submission,
    create_subject,
    delete_report_catalog_entry,
    get_job,
    get_job_by_submission,
    get_prior_report_slug,
    get_subject,
    get_submission,
    get_user,
    list_duplicate_submission_candidates,
    list_jobs,
    list_jobs_by_user,
    list_report_catalog,
    list_submissions_by_ids,
    list_submissions_with_users,
    list_subjects,
    refresh_targeted_materializations,
    restore_submission_files,
    save_submission_files,
    upsert_report_catalog_entry,
    store_report_html,
    update_submission_duplicate_metadata,
    update_job_status,
)
from server.publish import publish_report
from server.workspace import create_workspace, list_files

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {".fit", ".zwo", ".xlsx", ".md", ".csv", ".pdf"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

REPORT_DATA_RE = re.compile(
    r'<script id="report-data" type="application/json">(.*?)</script>',
    re.DOTALL,
)
SUBJECT_NAME_ALIASES = {
    "Geunyun Park": "박근윤",
    "changsun Hong": "홍창선",
    "Changsun Hong": "홍창선",
    "Daesoon Kim": "김대순",
}

# ── Dependencies ─────────────────────────────────────────────────────


def get_db_path(request: Request) -> Path:
    """Resolve platform database path from app state."""
    return request.app.state.db_path


def get_data_dir(request: Request) -> Path:
    """Resolve data directory from app state."""
    return request.app.state.data_dir


def get_channel_url(request: Request) -> str:
    """Resolve channel webhook URL from app state."""
    return request.app.state.channel_url


def get_published_dir(request: Request) -> Path:
    """Resolve published report directory from app state."""
    published_dir = getattr(request.app.state, "published_dir", None)
    if published_dir is not None:
        return Path(published_dir)
    return Path(__file__).resolve().parent.parent / "published"


def _source_tags_from_manifest(file_manifest: list[dict]) -> list[str]:
    """Return normalized source tags from a file manifest."""
    tags: set[str] = set()
    for item in file_manifest:
        name = str(item.get("name") or "").lower()
        ext = f".{str(item.get('extension') or '').lower().lstrip('.')}"
        if ext == ".xlsx":
            tags.add("CPET")
        elif ext == ".fit":
            tags.add("FIT")
        elif ext == ".zwo":
            tags.add("ZWO")
        elif ext == ".csv" or "lact" in name:
            tags.add("Lactate")
        elif ext == ".pdf":
            tags.add("INSCYD")
    return sorted(tags)


def _source_signature_from_manifest(file_manifest: list[dict]) -> str:
    """Build a compact source signature from normalized file tags."""
    return "+".join(_source_tags_from_manifest(file_manifest))


def _submission_fingerprint_from_manifest(file_manifest: list[dict]) -> str:
    """Build a stable fingerprint from file hashes when available."""
    parts: list[str] = []
    for item in sorted(file_manifest, key=lambda row: str(row.get("name") or "").lower()):
        file_hash = str(item.get("sha256") or "").strip()
        if not file_hash:
            continue
        parts.append(f"{str(item.get('name') or '').lower()}:{file_hash}")
    if not parts:
        return ""
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _has_file_extension(file_pairs: list[tuple[str, bytes]], extension: str) -> bool:
    """Return whether any uploaded file uses the given lowercase suffix."""
    normalized = extension.lower()
    return any(Path(filename).suffix.lower() == normalized for filename, _ in file_pairs)


def _duplicate_group_key(
    *,
    user_id: str = "",
    subject_id: str = "",
    test_date: str = "",
    source_signature: str = "",
) -> str:
    """Return a stable duplicate cluster key for likely duplicates."""
    if not test_date or not source_signature:
        return ""
    anchor = user_id.strip() or subject_id.strip()
    if not anchor:
        return ""
    raw = f"{anchor}|{test_date.strip()}|{source_signature.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _build_file_manifest_from_pairs(file_pairs: list[tuple[str, bytes]]) -> list[dict]:
    """Build file manifest with content hashes from uploaded files."""
    manifest: list[dict] = []
    for filename, content in file_pairs:
        safe_name = Path(filename).name
        manifest.append({
            "name": safe_name,
            "extension": Path(safe_name).suffix.lstrip("."),
            "size_bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        })
    return sorted(manifest, key=lambda row: str(row.get("name") or "").lower())


def _serialize_duplicate_candidates(candidates: list[dict]) -> list[dict]:
    """Convert DB rows into duplicate preflight payloads."""
    payload: list[dict] = []
    for item in candidates:
        payload.append({
            "submission_id": str(item.get("id") or ""),
            "report_slug": str(item.get("report_slug") or ""),
            "report_url": str(item.get("report_url") or ""),
            "subject_name": str(
                item.get("linked_subject_name")
                or item.get("linked_user_name")
                or item.get("subject_name")
                or ""
            ),
            "test_date": str(item.get("test_date") or ""),
            "confidence": str(item.get("duplicate_confidence") or ""),
            "source_signature": str(item.get("source_signature") or ""),
        })
    return payload


def sync_submission_duplicate_metadata(db_path: Path) -> None:
    """Backfill duplicate metadata for existing submissions from workspaces."""
    rows = list_submissions_with_users(db_path)
    for row in rows:
        workspace_path = Path(str(row.get("workspace_path") or ""))
        if not workspace_path:
            continue
        manifest = row.get("file_manifest") or []
        if not isinstance(manifest, list):
            manifest = []
        missing_hash = any(not str(item.get("sha256") or "").strip() for item in manifest)
        source_signature = str(row.get("source_signature") or "").strip()
        submission_fingerprint = str(row.get("submission_fingerprint") or "").strip()
        if not missing_hash and source_signature and submission_fingerprint:
            continue
        raw_dir = workspace_path / "raw"
        if not raw_dir.is_dir():
            continue
        file_pairs: list[tuple[str, bytes]] = []
        for file_path in sorted(raw_dir.iterdir()):
            if file_path.is_file():
                file_pairs.append((file_path.name, file_path.read_bytes()))
        if not file_pairs:
            continue
        manifest_with_hash = _build_file_manifest_from_pairs(file_pairs)
        update_submission_duplicate_metadata(
            db_path,
            str(row["id"]),
            source_signature=_source_signature_from_manifest(manifest_with_hash),
            submission_fingerprint=_submission_fingerprint_from_manifest(manifest_with_hash),
            duplicate_confidence=str(row.get("duplicate_confidence") or ""),
            duplicate_group_key=_duplicate_group_key(
                user_id=str(row.get("user_id") or ""),
                subject_id=str(row.get("subject_id") or ""),
                test_date=str(row.get("test_date") or ""),
                source_signature=_source_signature_from_manifest(manifest_with_hash),
            ),
        )


def _find_duplicate_candidates_for_submission(
    db_path: Path,
    *,
    file_manifest: list[dict],
    user_id: str = "",
    subject_id: str = "",
    test_date: str = "",
    exclude_submission_id: str = "",
) -> tuple[list[dict], str, str, str]:
    """Find exact and likely duplicate candidates for a submission payload."""
    source_signature = _source_signature_from_manifest(file_manifest)
    submission_fingerprint = _submission_fingerprint_from_manifest(file_manifest)
    group_key = _duplicate_group_key(
        user_id=user_id,
        subject_id=subject_id,
        test_date=test_date,
        source_signature=source_signature,
    )
    candidates = list_duplicate_submission_candidates(
        db_path,
        user_id=user_id,
        subject_id=subject_id,
        test_date=test_date,
        source_signature=source_signature,
        submission_fingerprint=submission_fingerprint,
        exclude_submission_id=exclude_submission_id,
    )
    return candidates, source_signature, submission_fingerprint, group_key


def _describe_generation_method(report_payload: dict | None) -> str:
    """Return a compact dashboard label for how the report was generated."""
    if not report_payload:
        return "알 수 없음"

    meta = report_payload.get("meta") or {}
    if meta.get("analysis_method"):
        return str(meta["analysis_method"])

    analysis = report_payload.get("analysis") or {}
    suitability = analysis.get("suitability") or {}

    if suitability:
        return "CPET 프로토콜 보정"
    if analysis:
        return "기본 CPET"
    return "알 수 없음"


def _describe_report_version(report_slug: str | None) -> str:
    """Convert a slug suffix into a compact dashboard version label."""
    if not report_slug:
        return "—"
    parts = str(report_slug).split("-")
    if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) <= 2:
        return f"v{parts[-1]}"
    return "v1"


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    """Best-effort parse of stored ISO timestamps."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _describe_processing_state(started_at: str | None) -> tuple[str, str, int]:
    """Return stage copy for in-progress jobs based on elapsed seconds."""
    started_dt = _parse_iso_timestamp(started_at)
    if started_dt is None:
        return ("워크스페이스 준비 중", "수집 파일과 분석 컨텍스트를 정렬하고 있습니다.", 0)

    elapsed = max(
        0,
        int((datetime.now(timezone.utc) - started_dt.astimezone(timezone.utc)).total_seconds()),
    )
    if elapsed < 12:
        return ("호흡 데이터 정렬 중", "COSMED, FIT, lactate 파일을 하나의 분석 세션으로 결합하고 있습니다.", elapsed)
    if elapsed < 26:
        return ("젖산·가스교환 지표 추정 중", "LT1, LT2, FatMax, VO2max 후보를 보수적으로 재평가하고 있습니다.", elapsed)
    if elapsed < 45:
        return ("리포트 빌드 중", "차트, 지표 설명, 신뢰도 레이어를 HTML 리포트로 조립하고 있습니다.", elapsed)
    return ("발행 패키징 중", "최종 리포트 URL과 대시보드 상태를 마감하고 있습니다.", elapsed)


def _report_identity(index_file: Path) -> tuple[int, str]:
    """Return a cheap identity for an HTML report file."""
    content = index_file.read_bytes()
    return (len(content), hashlib.sha256(content).hexdigest())


def _find_published_slug_for_report(report_index: Path, published_dir: Path) -> str | None:
    """Find a published slug whose index.html matches the generated workspace report."""
    if not report_index.is_file() or not published_dir.exists():
        return None

    report_identity = _report_identity(report_index)
    for report_dir in sorted(published_dir.iterdir()):
        if not report_dir.is_dir():
            continue
        published_index = report_dir / "index.html"
        if not published_index.is_file():
            continue
        try:
            if _report_identity(published_index) == report_identity:
                return report_dir.name
        except Exception:
            continue
    return None


def _sort_jobs_for_subject_groups(entries: list[dict]) -> list[dict]:
    """Group dashboard rows by subject and keep the newest rows first within each group."""
    items = list(entries)
    items.sort(
        key=lambda item: str(item.get("report_slug") or item.get("id") or ""),
        reverse=True,
    )
    items.sort(
        key=lambda item: str(
            item.get("test_date") or item.get("created_at") or item.get("completed_at") or ""
        ),
        reverse=True,
    )
    items.sort(
        key=lambda item: (
            1 if not str(item.get("group_name") or "").strip() else 0,
            str(item.get("group_name") or "").strip().lower(),
        )
    )
    return items


def _cluster_key_for_row(row: dict) -> str:
    """Return a duplicate cluster key for enriched dashboard rows."""
    exact_fingerprint = str(row.get("submission_fingerprint") or "").strip()
    if exact_fingerprint:
        return f"exact:{exact_fingerprint}"

    group_key = str(row.get("duplicate_group_key") or "").strip()
    if group_key:
        return f"likely:{group_key}"

    group_name = str(row.get("group_name") or row.get("linked_user_name") or row.get("subject_name") or "").strip()
    test_date = str(row.get("test_date") or "").strip()
    source_signature = str(row.get("source_signature") or "").strip()
    if not source_signature:
        tags = row.get("file_tags") or []
        if isinstance(tags, list):
            source_signature = "+".join(sorted(str(tag) for tag in tags if str(tag).strip()))
    if group_name and test_date and source_signature:
        return f"likely:{hashlib.sha256(f'{group_name}|{test_date}|{source_signature}'.encode('utf-8')).hexdigest()[:16]}"
    return ""


def _annotate_duplicate_rows(rows: list[dict]) -> None:
    """Annotate rows in-place with duplicate cluster metadata."""
    clusters: dict[str, list[dict]] = {}
    for row in rows:
        row["duplicate_cluster_key"] = ""
        row["duplicate_cluster_count"] = 0
        row["duplicate_badge"] = ""
        key = _cluster_key_for_row(row)
        if not key:
            continue
        clusters.setdefault(key, []).append(row)

    for key, items in clusters.items():
        if len(items) < 2:
            continue
        badge = "exact" if key.startswith("exact:") else "likely"
        for row in items:
            row["duplicate_cluster_key"] = key
            row["duplicate_cluster_count"] = len(items)
            row["duplicate_badge"] = badge


_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_SLUG_DATE_RE = re.compile(r"(\d{4})(\d{2})(\d{2})")


def _extract_report_metadata(index_file: Path) -> dict[str, str]:
    """Read a published report and extract dashboard metadata."""
    subject_name = ""
    test_date = ""
    analysis_method = "알 수 없음"

    try:
        import html as html_mod
        html = index_file.read_text(encoding="utf-8")
        match = REPORT_DATA_RE.search(html)
        if match:
            raw_json = html_mod.unescape(match.group(1))
            payload = json.loads(raw_json)
            subject_name = (payload.get("subject") or {}).get("name") or ""
            test_date = (payload.get("session") or {}).get("test_date") or ""
            analysis_method = _describe_generation_method(payload)

        # Fallback: extract date from HTML content if not found in JSON payload
        if not test_date:
            date_match = _DATE_RE.search(html[:5000])
            if date_match:
                test_date = date_match.group(0)
    except Exception:
        pass

    # Fallback: extract date from slug (e.g. keumhyun-kim-20260314 → 2026-03-14)
    if not test_date:
        slug_name = index_file.parent.name
        slug_match = _SLUG_DATE_RE.search(slug_name)
        if slug_match:
            y, m, d = slug_match.groups()
            if 2020 <= int(y) <= 2030:
                test_date = f"{y}-{m}-{d}"

    return {
        "subject_name": SUBJECT_NAME_ALIASES.get(subject_name, subject_name),
        "test_date": test_date,
        "analysis_method": analysis_method,
    }


def _reconcile_job_artifacts(
    request: Request,
    job: dict,
    submission: dict | None,
) -> dict:
    """Promote non-done jobs to done once their report artifacts exist."""
    if submission is None:
        return job

    if str(job.get("status") or "") == "done" and job.get("report_slug"):
        return job

    workspace = Path(str(submission.get("workspace_path") or ""))
    report_index = workspace / "report" / "index.html"
    if not report_index.is_file():
        # Timeout: if processing > 10 minutes with no report, mark as failed
        if str(job.get("status") or "") == "processing" and job.get("started_at"):
            try:
                started = datetime.fromisoformat(str(job["started_at"]))
                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                if elapsed > 600:  # 10 minutes
                    update_job_status(
                        get_db_path(request), str(job["id"]), "failed",
                        error_message=f"타임아웃 ({int(elapsed)}초) — 재분석을 시도하세요",
                    )
                    job = {**job, "status": "failed", "error_message": f"타임아웃 ({int(elapsed)}초)"}
            except (ValueError, TypeError):
                pass
        return job

    published_dir = get_published_dir(request)
    metadata = _extract_report_metadata(report_index)
    subject_name = (
        str(submission.get("subject_name") or "")
        or metadata.get("subject_name")
        or "subject"
    )
    test_date = (
        str(submission.get("test_date") or "")
        or metadata.get("test_date")
        or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )

    prior_slug = get_prior_report_slug(
        get_db_path(request),
        str(submission["id"]),
        exclude_job_id=str(job["id"]),
    )
    if prior_slug:
        slug = prior_slug
        publish_report(workspace, subject_name, test_date, published_dir, slug=prior_slug)
    else:
        slug = _find_published_slug_for_report(report_index, published_dir)
        if slug is None:
            slug = publish_report(workspace, subject_name, test_date, published_dir)
        else:
            publish_report(workspace, subject_name, test_date, published_dir, slug=slug)

    upsert_report_catalog_entry(
        get_db_path(request),
        report_slug=slug,
        subject_name=subject_name,
        test_date=test_date,
        analysis_method=str(metadata.get("analysis_method") or "알 수 없음"),
        report_version=_describe_report_version(slug),
        report_url=f"/report/{slug}/",
        completed_at=datetime.now(timezone.utc).isoformat(),
        file_tags=_get_file_tags(submission, str(workspace)),
    )
    try:
        store_report_html(get_db_path(request), slug, report_index.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to store report HTML in DB for slug %s", slug)

    update_job_status(
        get_db_path(request),
        str(job["id"]),
        "done",
        error_message=None,
        report_slug=slug,
        report_url=f"/report/{slug}/",
    )
    try:
        refresh_targeted_materializations(
            get_db_path(request),
            submission_ids=[str(submission["id"])],
            data_dir=get_data_dir(request),
        )
    except Exception:
        logger.exception(
            "Failed targeted materialization refresh after job reconcile for submission %s",
            str(submission["id"]),
        )
    refreshed = get_job(get_db_path(request), str(job["id"]))
    return refreshed or job


def _build_channel_payload(job: dict, submission: dict) -> dict:
    """Reconstruct the webhook payload used for automatic analysis."""
    file_tags = _get_file_tags(submission, submission.get("workspace_path"))
    analysis_mode = (
        "standalone_inscyd"
        if "INSCYD" in file_tags and "CPET" not in file_tags
        else "cpet"
    )
    return {
        "submission_id": submission["id"],
        "job_id": job["id"],
        "workspace_path": submission["workspace_path"],
        "description": submission.get("description") or "",
        "files": submission.get("file_manifest") or [],
        "file_tags": file_tags,
        "analysis_mode": analysis_mode,
        "report_type_hint": "inscyd" if analysis_mode == "standalone_inscyd" else "cpet",
    }


def _run_pipeline_job(
    db_path: Path,
    job_id: str,
    submission_id: str,
    workspace_path: str,
    subject_name: str,
    test_date: str,
    publish_dir: Path,
    data_dir: Path | None = None,
    report_url_prefix: str = "/report",
) -> None:
    """Run the standalone pipeline and mark the job done/failed."""
    try:
        workspace = Path(workspace_path).resolve()
        file_tags = _get_file_tags(None, str(workspace))
        is_standalone_inscyd = "INSCYD" in file_tags and "CPET" not in file_tags

        if is_standalone_inscyd:
            from pipeline.inscyd_report import generate_inscyd_report

            generate_inscyd_report(workspace, workspace / "report")
        else:
            from pipeline.analysis import run_analysis
            from pipeline.parsers import parse_workspace
            from pipeline.report import generate_report
            from pipeline.schema import create_database

            parsed = parse_workspace(workspace)
            analysis_db = create_database(workspace, parsed)
            run_analysis(analysis_db)
            generate_report(analysis_db, workspace / "report")

        safe_subject = subject_name or "subject"
        safe_test_date = test_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        slug = publish_report(workspace, safe_subject, safe_test_date, publish_dir)
        report_index = workspace / "report" / "index.html"
        metadata = _extract_report_metadata(report_index)
        upsert_report_catalog_entry(
            db_path,
            report_slug=slug,
            subject_name=safe_subject,
            test_date=safe_test_date,
            analysis_method=str(metadata.get("analysis_method") or "알 수 없음"),
            report_version=_describe_report_version(slug),
            report_url=f"{report_url_prefix.rstrip('/')}/{slug}/",
            completed_at=datetime.now(timezone.utc).isoformat(),
            file_tags=file_tags,
        )
        try:
            store_report_html(db_path, slug, report_index.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to store report HTML in DB for slug %s", slug)
        update_job_status(
            db_path,
            job_id,
            "done",
            error_message=None,
            report_slug=slug,
            report_url=f"{report_url_prefix.rstrip('/')}/{slug}/",
        )
        try:
            refresh_targeted_materializations(
                db_path,
                submission_ids=[submission_id],
                data_dir=data_dir,
            )
        except Exception:
            logger.exception(
                "Failed targeted materialization refresh after fallback pipeline for submission %s",
                submission_id,
            )
    except Exception as exc:
        logger.exception("Manual analysis fallback failed for job %s", job_id)
        update_job_status(
            db_path,
            job_id,
            "failed",
            error_message=str(exc)[:500],
            report_slug=None,
            report_url=None,
        )


def _ensure_workspace(
    data_dir: Path,
    db_path: Path,
    submission: dict,
) -> Path | None:
    """Return the workspace Path, restoring raw/ from DB if the directory is missing or empty.

    Returns None if the workspace cannot be reconstructed (no DB files stored).
    """
    workspace_path = submission.get("workspace_path")
    if workspace_path:
        workspace = Path(workspace_path)
        raw_dir = workspace / "raw"
        if raw_dir.is_dir() and any(raw_dir.iterdir()):
            return workspace

    # Attempt to restore from submission_files
    submission_id = str(submission["id"])
    stored_files = restore_submission_files(db_path, submission_id)
    if not stored_files:
        return None

    workspace = create_workspace(data_dir, submission_id, stored_files)
    return workspace


def _start_fallback_analysis(
    db_path: Path,
    job: dict,
    submission: dict,
    publish_dir: Path,
    data_dir: Path | None = None,
) -> threading.Thread:
    """Run fallback analysis in a daemon thread so the dashboard can keep polling."""
    thread = threading.Thread(
        target=_run_pipeline_job,
        kwargs={
            "db_path": db_path,
            "job_id": str(job["id"]),
            "submission_id": str(submission["id"]),
            "workspace_path": str(submission["workspace_path"]),
            "subject_name": str(submission.get("subject_name") or ""),
            "test_date": str(submission.get("test_date") or ""),
            "publish_dir": publish_dir,
            "data_dir": data_dir,
        },
        daemon=True,
        name=f"cpet-job-{str(job['id'])[:8]}",
    )
    thread.start()
    return thread


_FILE_TAG_MAP = {
    ".fit": "FIT",
    ".zwo": "ZWO",
    ".xlsx": "CPET",
    ".md": "Lactate",
    ".csv": "Lactate",
    ".pdf": "INSCYD",
}


def _extract_file_tags_from_workspace(workspace_path: str | None) -> list[str]:
    """Extract file type tags from actual files in workspace/raw/ directory."""
    if not workspace_path:
        return []
    raw_dir = Path(workspace_path) / "raw"
    if not raw_dir.is_dir():
        return []

    seen: set[str] = set()
    tags: list[str] = []
    for f in sorted(raw_dir.iterdir()):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        tag = _FILE_TAG_MAP.get(ext)
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def _extract_file_tags_from_manifest(sub: dict | None) -> list[str]:
    """Fallback: extract tags from submission file_manifest JSON."""
    if not sub:
        return []
    manifest = sub.get("file_manifest")
    if not manifest:
        return []
    if isinstance(manifest, str):
        try:
            manifest = json.loads(manifest)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(manifest, list):
        return []

    seen: set[str] = set()
    tags: list[str] = []
    for f in manifest:
        ext = "." + str(f.get("extension", "") or f.get("name", "").rsplit(".", 1)[-1]).lower()
        tag = _FILE_TAG_MAP.get(ext)
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def _get_file_tags(sub: dict | None, workspace_path: str | None) -> list[str]:
    """Get file tags: prefer workspace scan, fall back to manifest."""
    tags = _extract_file_tags_from_workspace(workspace_path)
    if tags:
        return tags
    return _extract_file_tags_from_manifest(sub)


def _scan_published_reports(published_dir: Path) -> list[dict]:
    """Scan published/ and build dashboard-like rows for standalone reports."""
    if not published_dir.exists():
        return []

    rows: list[dict] = []
    for report_dir in sorted(published_dir.iterdir()):
        if not report_dir.is_dir():
            continue
        index_file = report_dir / "index.html"
        if not index_file.is_file():
            continue

        metadata = _extract_report_metadata(index_file)
        subject_name = metadata["subject_name"] or report_dir.name
        test_date = metadata["test_date"]

        modified_at_dt = datetime.fromtimestamp(
            index_file.stat().st_mtime,
            tz=timezone.utc,
        )
        modified_at = modified_at_dt.isoformat()

        rows.append(
            {
                "id": report_dir.name,
                "display_id": hashlib.md5(report_dir.name.encode("utf-8")).hexdigest()[:8],
                "submission_id": "",
                "status": "done",
                "error_message": None,
                "report_slug": report_dir.name,
                "report_url": f"/report/{report_dir.name}/",
                "started_at": None,
                "completed_at": modified_at,
                "created_at": modified_at,
                "created_at_display": modified_at_dt.strftime("%Y-%m-%d %H:%M"),
                "subject_name": subject_name,
                "test_date": test_date,
                "analysis_method": metadata["analysis_method"],
                "report_version": _describe_report_version(report_dir.name),
                "is_latest": False,
                "file_tags": [],  # filled later from workspace scan
            }
        )

    return rows


def sync_published_report_catalog(db_path: Path, published_dir: Path) -> None:
    """Sync published HTML metadata into the SQLite report catalog.

    For each report found on disk, upsert catalog metadata and store HTML in DB.
    DB entries that have html_content are never deleted (they are DB-primary);
    entries without html_content whose file is missing are pruned.
    """
    current_slugs: set[str] = set()
    for row in _scan_published_reports(published_dir):
        report_slug = str(row["report_slug"])
        current_slugs.add(report_slug)
        upsert_report_catalog_entry(
            db_path,
            report_slug=report_slug,
            subject_name=str(row["subject_name"] or ""),
            test_date=str(row["test_date"] or ""),
            analysis_method=str(row["analysis_method"] or "알 수 없음"),
            report_version=str(row["report_version"] or "기본 리포트"),
            report_url=str(row["report_url"] or f"/report/{report_slug}/"),
            completed_at=str(row["completed_at"] or ""),
            file_tags=list(row.get("file_tags") or []),
        )
        # Persist HTML into DB if not already stored
        html_file = published_dir / report_slug / "index.html"
        if html_file.is_file():
            try:
                store_report_html(db_path, report_slug, html_file.read_text(encoding="utf-8"))
            except Exception:
                logger.exception("Failed to store report HTML for %s during sync", report_slug)

    for row in list_report_catalog(db_path):
        report_slug = str(row["report_slug"])
        if report_slug not in current_slugs:
            # Keep entries that already have HTML stored in DB
            if row.get("html_content"):
                continue
            delete_report_catalog_entry(db_path, report_slug)


def _list_dashboard_entries(
    request: Request, status: str | None = None, user_id: str | None = None,
) -> list[dict]:
    """Merge DB jobs with standalone published reports for dashboard views.

    When user_id is provided, only jobs whose submission belongs to that user
    are returned (the published-directory scan is skipped).
    """
    db_path = get_db_path(request)
    jobs = list_jobs(db_path, status=status)
    submission_ids = [str(job["submission_id"]) for job in jobs if job.get("submission_id")]
    submissions_by_id = list_submissions_by_ids(db_path, submission_ids)

    enriched: list[dict] = []
    job_slugs: set[str] = set()
    published_rows: list[dict] = []
    published_by_slug: dict[str, dict] = {}
    if status in (None, "done"):
        published_rows = list_report_catalog(db_path)
        published_by_slug = {
            str(item["report_slug"]): item for item in published_rows if item.get("report_slug")
        }

    for job in jobs:
        sub = submissions_by_id.get(str(job["submission_id"]))
        job = _reconcile_job_artifacts(request, job, sub)
        report_slug = str(job.get("report_slug") or "")
        analysis_method = "대기 중"
        if report_slug:
            if report_slug not in published_by_slug:
                refreshed_catalog = {
                    str(item["report_slug"]): item
                    for item in list_report_catalog(db_path)
                    if item.get("report_slug")
                }
                published_by_slug.update(refreshed_catalog)
            analysis_method = (
                published_by_slug.get(report_slug, {}).get("analysis_method")
                or analysis_method
            )
        elif job.get("status") == "processing":
            analysis_method = "생성 중"
        elif job.get("status") == "failed":
            analysis_method = "생성 실패"
        processing_stage, processing_note, processing_seconds = _describe_processing_state(
            str(job.get("started_at") or "")
        )
        enriched_job = {
            **job,
            "display_id": str(job["id"])[:8],
            "created_at_display": str(job.get("created_at") or "")[:16].replace("T", " "),
            "subject_name": SUBJECT_NAME_ALIASES.get(
                sub["subject_name"] if sub else "",
                sub["subject_name"] if sub else "",
            ),
            "test_date": sub["test_date"] if sub else "",
            "analysis_method": analysis_method,
            "report_version": _describe_report_version(job.get("report_slug")),
            "is_latest": False,
            "can_trigger": bool(
                sub
                and str(job.get("status") or "") in {"pending", "failed"}
            ),
            "processing_stage": processing_stage,
            "processing_note": processing_note,
            "processing_seconds": processing_seconds,
            "submission_user_id": sub.get("user_id") if sub else None,
            "submission_subject_id": sub.get("subject_id") if sub else None,
            "subject_id": sub.get("subject_id") if sub else None,
            "source_signature": sub.get("source_signature") if sub else "",
            "submission_fingerprint": sub.get("submission_fingerprint") if sub else "",
            "duplicate_confidence": sub.get("duplicate_confidence") if sub else "",
            "duplicate_group_key": sub.get("duplicate_group_key") if sub else "",
            "file_tags": _get_file_tags(sub, sub.get("workspace_path") if sub else None),
        }
        enriched.append(enriched_job)
        if job.get("report_slug"):
            job_slugs.add(str(job["report_slug"]))

    if status not in (None, "done"):
        return enriched

    for row in published_rows:
        if row["report_slug"] in job_slugs:
            continue
        row["source_signature"] = ""
        row["submission_fingerprint"] = ""
        row["duplicate_confidence"] = ""
        row["duplicate_group_key"] = ""
        enriched.append(row)

    # Mark ownership via submission.user_id, subject_id, and report_user_links
    from server.db import get_report_user_links
    report_links = get_report_user_links(db_path)
    user_name_cache: dict[str, str] = {}
    subject_name_cache: dict[str, str] = {}

    def resolve_subject_name(subject_id_value: str | None) -> str:
        subject_id_str = str(subject_id_value or "").strip()
        if not subject_id_str:
            return ""
        if subject_id_str not in subject_name_cache:
            subject = get_subject(db_path, subject_id_str)
            subject_name_cache[subject_id_str] = str((subject or {}).get("name") or "").strip()
        return subject_name_cache[subject_id_str]

    def resolve_user_display_name(user_id_value: str | None) -> str:
        user_id_str = str(user_id_value or "").strip()
        if not user_id_str:
            return ""
        if user_id_str not in user_name_cache:
            user = get_user(db_path, user_id_str)
            subject_name = ""
            subject_id = str((user or {}).get("subject_id") or "").strip()
            if subject_id:
                subject = get_subject(db_path, subject_id)
                subject_name = str((subject or {}).get("name") or "").strip()
            user_name_cache[user_id_str] = str(
                subject_name
                or (user or {}).get("display_name")
                or (user or {}).get("email")
                or ""
            ).strip()
        return user_name_cache[user_id_str]

    # Get current session user_id and their subject_id for is_mine calculation
    session_user_id = None
    session_subject_id = None
    if hasattr(request, "session"):
        session_user_id = request.session.get("user_id")
    if session_user_id:
        session_user = get_user(db_path, session_user_id)
        if session_user:
            session_subject_id = session_user.get("subject_id")

    for row in enriched:
        is_mine = False
        if session_user_id:
            if row.get("submission_user_id") == session_user_id:
                is_mine = True
            # Check subject_id match: user.subject_id == submission.subject_id
            if session_subject_id and row.get("submission_subject_id") == session_subject_id:
                is_mine = True
            slug = row.get("report_slug", "")
            if slug and report_links.get(slug) == session_user_id:
                is_mine = True
        row["is_mine"] = is_mine

    # When filtering by user, keep only mine
    if user_id:
        enriched = [row for row in enriched if row.get("is_mine")]

    # Apply name overrides + notes
    from server.db import get_report_name_overrides, get_report_notes
    name_overrides = get_report_name_overrides(db_path)
    report_notes = get_report_notes(db_path)
    for row in enriched:
        slug = row.get("report_slug", "")
        linked_subject_name = resolve_subject_name(row.get("submission_subject_id"))
        linked_user_name = resolve_user_display_name(row.get("submission_user_id"))
        if not linked_user_name and slug:
            linked_user_name = resolve_user_display_name(report_links.get(slug))
        row["linked_user_name"] = linked_user_name
        if slug and slug in name_overrides:
            row["subject_name"] = name_overrides[slug]
        row["note"] = report_notes.get(slug, "") if slug else ""
        row["group_name"] = (
            linked_subject_name
            or str(row.get("subject_name") or "").strip()
            or "미연결 리포트"
        )

    _annotate_duplicate_rows(enriched)

    enriched.sort(
        key=lambda row: str(row.get("test_date") or row.get("created_at") or ""),
        reverse=True,
    )

    # Deduplicate: for same subject+date+report_slug, keep only the newest
    seen_slugs: dict[str, int] = {}
    deduped: list[dict] = []
    for i, row in enumerate(enriched):
        slug = row.get("report_slug", "")
        if slug and slug in seen_slugs:
            # Skip older duplicate with same slug
            continue
        if slug:
            seen_slugs[slug] = i
        deduped.append(row)

    return deduped


# ── Channel dispatch ─────────────────────────────────────────────────


async def notify_channel(channel_url: str, payload: dict) -> None:
    """POST job payload to channel server. Fails gracefully."""
    async with httpx.AsyncClient() as client:
        try:
            await client.post(channel_url, json=payload, timeout=5.0)
        except (httpx.ConnectError, httpx.TimeoutException):
            logger.warning("Channel server not reachable at %s", channel_url)


async def _channel_is_healthy(channel_url: str) -> bool:
    """Check whether the local channel server is reachable."""
    health_url = f"{channel_url.rstrip('/')}/health"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(health_url, timeout=2.0)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            return False
    return resp.status_code == 200


async def _read_upload_file_pairs(files: list[UploadFile]) -> tuple[list[tuple[str, bytes]], JSONResponse | None]:
    """Read upload files once and validate extension/size."""
    if not files:
        return [], JSONResponse(status_code=400, content={"error": "no files provided"})

    file_pairs: list[tuple[str, bytes]] = []
    for f in files:
        filename = f.filename or "unnamed"
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return [], JSONResponse(status_code=400, content={"error": f"invalid file extension: {ext}"})
        content = await f.read()
        if len(content) > MAX_FILE_SIZE:
            return [], JSONResponse(
                status_code=413,
                content={"error": f"file too large: {filename} ({len(content)} bytes, max {MAX_FILE_SIZE})"},
            )
        file_pairs.append((filename, content))
    return file_pairs, None


# ── POST /api/submit ─────────────────────────────────────────────────


@router.post("/api/submit/preflight")
async def submit_preflight(
    request: Request,
    files: list[UploadFile],
    subject_name: str = Form(""),
    test_date: str = Form(""),
    target_user_id: str = Form(""),
    subject_id: str = Form(""),
) -> JSONResponse:
    """Inspect a pending upload and return duplicate candidates before submit."""
    db_path = get_db_path(request)
    sync_submission_duplicate_metadata(db_path)

    file_pairs, error = await _read_upload_file_pairs(files)
    if error:
        return error

    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "로그인이 필요합니다"})

    session_role = request.session.get("role", "user") if hasattr(request, "session") else "user"
    effective_user_id = user_id
    if target_user_id and target_user_id != "__new__" and session_role in ("researcher", "admin"):
        effective_user_id = target_user_id

    effective_subject_id = subject_id or None
    if not effective_subject_id and session_role not in ("researcher", "admin"):
        current_user = get_user(db_path, user_id)
        if current_user and current_user.get("subject_id"):
            effective_subject_id = str(current_user["subject_id"])
    if effective_subject_id and not subject_name:
        subj = get_subject(db_path, effective_subject_id)
        if subj:
            subject_name = str(subj.get("name") or "")

    manifest = _build_file_manifest_from_pairs(file_pairs)
    candidates, source_signature, submission_fingerprint, group_key = _find_duplicate_candidates_for_submission(
        db_path,
        file_manifest=manifest,
        user_id=str(effective_user_id or ""),
        subject_id=str(effective_subject_id or ""),
        test_date=test_date.strip(),
    )

    return JSONResponse({
        "ok": True,
        "subject_name": subject_name,
        "test_date": test_date.strip(),
        "source_signature": source_signature,
        "submission_fingerprint": submission_fingerprint,
        "duplicate_group_key": group_key,
        "duplicates": _serialize_duplicate_candidates(candidates),
        "has_duplicates": bool(candidates),
    })


@router.post("/api/submit", status_code=201)
async def submit(
    request: Request,
    files: list[UploadFile] = File(default_factory=list),
    description: str = Form(""),
    subject_name: str = Form(""),
    test_date: str = Form(""),
    target_user_id: str = Form(""),
    subject_id: str = Form(""),
    primary_goal: str = Form(""),
    fasting_hours: str = Form(""),
    meal_state: str = Form(""),
    caffeine_state: str = Form(""),
    prior_training_state: str = Form(""),
    protocol_outline: str = Form(""),
    operator_notes: str = Form(""),
    override_duplicates: str = Form(""),
    reanalyze: str | None = Query(default=None),
) -> JSONResponse:
    """Upload files, create workspace/submission/job, dispatch to channel.

    If reanalyze=<submission_id>, adds files to the existing workspace
    and creates a new job for re-analysis.
    """
    db_path = get_db_path(request)
    data_dir = get_data_dir(request)
    channel_url = get_channel_url(request)
    sync_submission_duplicate_metadata(db_path)
    # Reanalyze-only mode: empty multipart is allowed (skip file-pair read).
    # Non-reanalyze paths still require files (helper returns 400 on empty).
    if reanalyze and not files:
        file_pairs: list[tuple[str, bytes]] = []
    else:
        file_pairs, error = await _read_upload_file_pairs(files)
        if error:
            return error

    # Login required for uploads
    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    if not user_id:
        return JSONResponse(
            status_code=401,
            content={"error": "로그인이 필요합니다"},
        )

    # Determine target user: researcher can upload for others
    effective_user_id = user_id  # default: self
    session_role = request.session.get("role", "user") if hasattr(request, "session") else "user"
    if target_user_id and target_user_id != "__new__" and session_role in ("researcher", "admin"):
        effective_user_id = target_user_id

    # Resolve subject_id
    effective_subject_id = subject_id or None
    if not effective_subject_id and session_role not in ("researcher", "admin"):
        # Regular user: auto-link to their own subject
        current_user = get_user(db_path, user_id)
        if current_user and current_user.get("subject_id"):
            effective_subject_id = current_user["subject_id"]
    # If researcher selected a subject, also populate subject_name from it
    if effective_subject_id and not subject_name:
        subj = get_subject(db_path, effective_subject_id)
        if subj:
            subject_name = subj.get("name", "")

    # Re-analysis mode: add files to existing workspace
    if reanalyze:
        existing_sub = get_submission(db_path, reanalyze)
        if existing_sub and existing_sub.get("workspace_path"):
            # Ownership check: researcher/admin, legacy user_id owner, or a
            # user whose subject_id matches the submission's subject_id.
            allowed = session_role in ("researcher", "admin")
            if not allowed:
                owner_id = str(existing_sub.get("user_id") or "")
                if owner_id and owner_id == str(user_id):
                    allowed = True
            if not allowed:
                actor = get_user(db_path, user_id) or {}
                actor_subject_id = str(actor.get("subject_id") or "")
                sub_subject_id = str(existing_sub.get("subject_id") or "")
                if actor_subject_id and actor_subject_id == sub_subject_id:
                    allowed = True
            if not allowed:
                return JSONResponse(
                    status_code=403,
                    content={"error": "권한이 없습니다"},
                )

            workspace = Path(existing_sub["workspace_path"])
            raw_dir = workspace / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)

            # Write new files into existing workspace (skipped for reanalyze-only)
            if file_pairs:
                for filename, content in file_pairs:
                    (raw_dir / filename).write_bytes(content)

            # Remove old analysis.db and report to force fresh analysis
            # (always runs — this is the whole point of reanalyze)
            for cleanup in [workspace / "analysis.db", workspace / "report"]:
                if cleanup.is_file():
                    cleanup.unlink()
                elif cleanup.is_dir():
                    import shutil
                    shutil.rmtree(cleanup, ignore_errors=True)

            if file_pairs:
                # Persist the full raw/ state (original + newly added files) to DB
                all_raw_pairs = [
                    (p.name, p.read_bytes())
                    for p in sorted(raw_dir.iterdir())
                    if p.is_file()
                ]
                save_submission_files(db_path, reanalyze, all_raw_pairs)

                # Update submission manifest + description
                manifest = list_files(workspace)
                conn = sqlite3.connect(str(db_path))
                conn.execute(
                    "UPDATE submissions SET file_manifest = ?, description = ? WHERE id = ?",
                    (json.dumps(manifest), description, reanalyze),
                )
                conn.commit()
                conn.close()

            # Create new job for re-analysis
            job_id = create_job(db_path, reanalyze)
            prior_slug = get_prior_report_slug(db_path, reanalyze, exclude_job_id=job_id)
            if prior_slug:
                update_job_status(
                    db_path,
                    job_id,
                    "pending",
                    report_slug=prior_slug,
                    report_url=f"/report/{prior_slug}/",
                )
            refreshed_sub = get_submission(db_path, reanalyze) or existing_sub
            payload = _build_channel_payload(
                {"id": job_id},
                refreshed_sub,
            )

            await notify_channel(
                channel_url,
                payload,
            )

            return JSONResponse(
                status_code=201,
                content={"job_id": job_id, "status": "pending"},
            )

    # Normal submission: require either COSMED xlsx or standalone INSCYD pdf
    has_xlsx = _has_file_extension(file_pairs, ".xlsx")
    has_pdf = _has_file_extension(file_pairs, ".pdf")
    if not has_xlsx and not has_pdf:
        return JSONResponse(
            status_code=400,
            content={"error": "at least one .xlsx (COSMED) or .pdf (INSCYD) file required"},
        )

    manifest = _build_file_manifest_from_pairs(file_pairs)
    duplicate_candidates, source_signature, submission_fingerprint, duplicate_group_key = _find_duplicate_candidates_for_submission(
        db_path,
        file_manifest=manifest,
        user_id=str(effective_user_id or ""),
        subject_id=str(effective_subject_id or ""),
        test_date=test_date.strip(),
    )
    if duplicate_candidates and override_duplicates != "1":
        return JSONResponse(
            status_code=409,
            content={
                "error": "duplicate candidates found",
                "duplicates": _serialize_duplicate_candidates(duplicate_candidates),
                "source_signature": source_signature,
                "submission_fingerprint": submission_fingerprint,
                "duplicate_group_key": duplicate_group_key,
            },
        )

    # Create workspace first to determine submission_id
    submission_id = str(uuid.uuid4())
    workspace = create_workspace(data_dir, submission_id, file_pairs)

    # Save protocol context to workspace metadata + auto-compose description
    from server.protocol_context import normalize_protocol_context, compose_claude_protocol_summary
    protocol_context = normalize_protocol_context({
        "primary_goal": primary_goal, "fasting_hours": fasting_hours,
        "meal_state": meal_state, "caffeine_state": caffeine_state,
        "prior_training_state": prior_training_state,
        "protocol_outline": protocol_outline, "operator_notes": operator_notes,
        "block_intents": [], "target_outputs": [],
    })
    protocol_summary = compose_claude_protocol_summary(protocol_context)

    # Auto-compose description from protocol context if user left it empty
    if not description.strip() and protocol_summary:
        description = protocol_summary

    metadata_dir = workspace / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "submission_context.json").write_text(
        json.dumps({
            "protocol_context": protocol_context,
            "protocol_summary": protocol_summary,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Build file manifest
    manifest = _build_file_manifest_from_pairs(file_pairs)

    # Create submission and job
    create_submission(
        db_path,
        description,
        manifest,
        str(workspace),
        subject_name=subject_name,
        test_date=test_date,
        submission_id=submission_id,
        user_id=effective_user_id,
        subject_id=effective_subject_id,
        uploaded_by_user_id=user_id,
        source_signature=source_signature,
        submission_fingerprint=submission_fingerprint,
        duplicate_confidence="exact" if any(item.get("duplicate_confidence") == "exact" for item in duplicate_candidates) else ("likely" if duplicate_candidates else ""),
        duplicate_group_key=duplicate_group_key,
    )
    save_submission_files(db_path, submission_id, file_pairs)
    job_id = create_job(db_path, submission_id)
    created_submission = get_submission(db_path, submission_id)
    payload = _build_channel_payload(
        {"id": job_id},
        created_submission or {
            "id": submission_id,
            "workspace_path": str(workspace),
            "description": description,
            "file_manifest": manifest,
        },
    )

    # Dispatch to channel (fire-and-forget, graceful on failure)
    await notify_channel(channel_url, payload)

    return JSONResponse(
        status_code=201,
        content={"job_id": job_id, "status": "pending"},
    )


# ── GET /api/jobs ────────────────────────────────────────────────────


@router.get("/api/jobs")
async def jobs_list(
    request: Request,
    status: str | None = None,
) -> list[dict]:
    """List jobs, optionally filtered by status."""
    return _list_dashboard_entries(request, status=status)


# ── GET /api/jobs/partial (HTMX) ────────────────────────────────────
# Must be registered BEFORE /api/jobs/{job_id} to avoid path conflict.


@router.get("/api/jobs/partial", response_class=HTMLResponse)
async def jobs_partial(
    request: Request,
    status: str | None = None,
    filter: str | None = None,
    group_by: str | None = None,
) -> HTMLResponse:
    """Return an HTML partial of the job list for HTMX polling.

    When filter=mine, restrict to jobs created by the current session user.
    """
    templates = request.app.state.templates
    current_user_id: str | None = None
    if hasattr(request, "session"):
        current_user_id = request.session.get("user_id")

    filter_user_id: str | None = None
    if filter == "mine" and current_user_id:
        filter_user_id = current_user_id

    enriched = _list_dashboard_entries(
        request, status=status, user_id=filter_user_id,
    )
    grouped_by_subject = group_by == "subject"
    if grouped_by_subject:
        enriched = _sort_jobs_for_subject_groups(enriched)

    current_user_role = ""
    if hasattr(request, "session"):
        current_user_role = request.session.get("role", "")
        if current_user_role == "admin" and request.session.get("preview_as_user"):
            current_user_role = "user"

    return templates.TemplateResponse(
        request,
        "partials/job_list.html",
        {
            "jobs": enriched,
            "current_user_id": current_user_id,
            "current_user_role": current_user_role,
            "grouped_by_subject": grouped_by_subject,
        },
    )


@router.post(
    "/api/jobs/{job_id}/trigger",
    response_class=HTMLResponse,
    response_model=None,
)
async def trigger_job(
    request: Request,
    job_id: str,
) -> HTMLResponse:
    """Manually trigger analysis for a pending/failed job."""
    db_path = get_db_path(request)
    channel_url = get_channel_url(request)
    templates = request.app.state.templates
    published_dir = get_published_dir(request)

    job = get_job(db_path, job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"job not found: {job_id}"},
        )

    if str(job.get("status") or "") == "done":
        return JSONResponse(
            status_code=409,
            content={"error": "completed jobs cannot be retriggered — use 추가 분석"},
        )

    if str(job.get("status") or "") == "processing":
        return JSONResponse(
            status_code=409,
            content={"error": "job is already processing"},
        )

    submission = get_submission(db_path, str(job["submission_id"]))
    if submission is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"submission not found for job: {job_id}"},
        )

    data_dir = get_data_dir(request)
    restored_workspace = _ensure_workspace(data_dir, db_path, submission)
    if restored_workspace is None:
        update_job_status(
            db_path,
            job_id,
            "failed",
            error_message="workspace missing and no source files stored in DB — cannot trigger",
            report_slug=None,
            report_url=None,
        )
        return JSONResponse(
            status_code=409,
            content={"error": "workspace missing and no source files available to restore"},
        )

    # Patch submission with the (possibly restored) workspace path so that the
    # fallback runner and channel payload carry the correct path.
    if str(submission.get("workspace_path") or "") != str(restored_workspace):
        submission = dict(submission)
        submission["workspace_path"] = str(restored_workspace)

    canonical_job = get_job_by_submission(db_path, str(submission["id"])) or job
    payload = _build_channel_payload(canonical_job, submission)
    update_job_status(
        db_path,
        job_id,
        "processing",
        error_message=None,
        report_slug=None,
        report_url=None,
    )

    if await _channel_is_healthy(channel_url):
        await notify_channel(channel_url, payload)
        logger.info("Manual trigger sent to channel for job %s", job_id)
    else:
        _start_fallback_analysis(
            db_path=db_path,
            job=canonical_job,
            submission=submission,
            publish_dir=published_dir,
            data_dir=data_dir,
        )
        logger.info("Manual trigger started local fallback for job %s", job_id)

    current_user_id: str | None = None
    if hasattr(request, "session"):
        current_user_id = request.session.get("user_id")

    current_user_role = ""
    if hasattr(request, "session"):
        current_user_role = request.session.get("role", "")
        if current_user_role == "admin" and request.session.get("preview_as_user"):
            current_user_role = "user"

    enriched = _list_dashboard_entries(request)
    return templates.TemplateResponse(
        request,
        "partials/job_list.html",
        {
            "jobs": enriched,
            "current_user_id": current_user_id,
            "current_user_role": current_user_role,
            "grouped_by_subject": False,
        },
    )


# ── GET /api/jobs/{job_id} ───────────────────────────────────────────


@router.get("/api/jobs/{job_id}")
async def job_detail(
    request: Request,
    job_id: str,
) -> JSONResponse:
    """Get a single job by ID."""
    db_path = get_db_path(request)
    job = get_job(db_path, job_id)

    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"job not found: {job_id}"},
        )

    return JSONResponse(content=job)


# ── POST /api/subjects ──────────────────────────────────────────────


@router.post("/api/subjects", status_code=201)
async def create_subject_endpoint(
    request: Request,
    name: str = Form(""),
    gender: str = Form(""),
    birth_year: str = Form(""),
    height_cm: str = Form(""),
    weight_kg: str = Form(""),
) -> JSONResponse:
    """Create a new subject. Returns the created subject as JSON."""
    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    if not user_id:
        return JSONResponse(
            status_code=401,
            content={"error": "로그인이 필요합니다"},
        )

    if not name.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "이름은 필수입니다"},
        )
    if not gender.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "성별은 필수입니다"},
        )
    if not birth_year.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "출생년도는 필수입니다"},
        )

    db_path = get_db_path(request)

    birth_year_int: int | None = None
    try:
        birth_year_int = int(birth_year)
    except (ValueError, TypeError):
        return JSONResponse(
            status_code=400,
            content={"error": "출생년도는 숫자여야 합니다"},
        )

    height_val: float | None = None
    if height_cm.strip():
        try:
            height_val = float(height_cm)
        except (ValueError, TypeError):
            pass

    weight_val: float | None = None
    if weight_kg.strip():
        try:
            weight_val = float(weight_kg)
        except (ValueError, TypeError):
            pass

    subject = create_subject(
        db_path,
        name=name.strip(),
        gender=gender.strip(),
        birth_year=birth_year_int,
        height_cm=height_val,
        weight_kg=weight_val,
    )

    return JSONResponse(
        status_code=201,
        content={"data": subject},
    )


# ── GET /api/subjects ───────────────────────────────────────────────


@router.get("/api/subjects")
async def list_subjects_endpoint(
    request: Request,
) -> JSONResponse:
    """List all subjects."""
    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    if not user_id:
        return JSONResponse(
            status_code=401,
            content={"error": "로그인이 필요합니다"},
        )
    db_path = get_db_path(request)
    subjects = list_subjects(db_path)
    return JSONResponse(content={"data": subjects})


# ── POST /api/lactate/ocr ────────────────────────────────────────────

_LACTATE_OCR_ALLOWED_MIME = {"image/jpeg", "image/png"}
_LACTATE_OCR_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/api/lactate/ocr")
async def lactate_ocr(
    request: Request,
    image: UploadFile = File(...),
) -> JSONResponse:
    """Accept an image of a handwritten lactate sheet, return parsed rows via Claude Vision.

    Returns:
        200 {"rows": [...]}
        400 for unsupported MIME / oversized file
        401 if not logged in
        502 for Claude API errors or timeout
        503 if ANTHROPIC_API_KEY is not configured
    """
    user_id = request.session.get("user_id") if hasattr(request, "session") else None
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "로그인이 필요합니다"})

    mime = image.content_type or ""
    if mime not in _LACTATE_OCR_ALLOWED_MIME:
        ext = Path(image.filename or "").suffix.lower()
        if ext in {".jpg", ".jpeg"}:
            mime = "image/jpeg"
        elif ext == ".png":
            mime = "image/png"
        else:
            return JSONResponse(
                status_code=400,
                content={"error": f"지원하지 않는 이미지 형식입니다: {mime or ext}. JPG 또는 PNG만 허용됩니다."},
            )

    content = await image.read()
    if len(content) > _LACTATE_OCR_MAX_BYTES:
        return JSONResponse(
            status_code=400,
            content={"error": f"이미지 파일이 너무 큽니다 ({len(content) // 1024 // 1024} MB). 최대 10 MB."},
        )

    from server.lactate_ocr import LactateOcrError, extract_lactate_table  # noqa: PLC0415

    import os  # noqa: PLC0415
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return JSONResponse(
            status_code=503,
            content={"error": "ANTHROPIC_API_KEY가 설정되지 않았습니다. 서버 관리자에게 문의하세요."},
        )

    try:
        rows = extract_lactate_table(content, mime)
    except LactateOcrError as exc:
        msg = str(exc)
        if "API key" in msg or "ANTHROPIC_API_KEY" in msg:
            return JSONResponse(status_code=503, content={"error": msg})
        return JSONResponse(status_code=502, content={"error": msg})
    except Exception as exc:
        logger.exception("Unexpected error in lactate OCR")
        return JSONResponse(status_code=502, content={"error": f"OCR 처리 중 오류가 발생했습니다: {exc}"})

    return JSONResponse(content={"rows": rows})
