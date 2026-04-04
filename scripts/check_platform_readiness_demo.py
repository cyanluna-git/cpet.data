"""
Run platform-readiness QA checks against the seeded demo DB.

This harness validates both data coherence and operator-facing surfaces so the
demo environment can expose missing product capabilities before real volume
arrives.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.staticfiles import StaticFiles

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.seed_demo_platform_validation import seed_demo_platform_validation
from server.main import app


def _count(conn: sqlite3.Connection, query: str, params: tuple = ()) -> int:
    return int(conn.execute(query, params).fetchone()[0])


def _db_checks(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        counts = {
            table: _count(conn, f"SELECT COUNT(*) FROM {table}")
            for table in (
                "subjects",
                "users",
                "submissions",
                "jobs",
                "report_catalog",
                "subject_metric_snapshots",
                "subject_feature_sets",
            )
        }
        duplicate_submissions = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM submissions
            WHERE duplicate_confidence IN ('exact', 'likely')
            """,
        )
        repeated_subjects = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM (
                SELECT subject_id
                FROM subject_metric_snapshots
                GROUP BY subject_id
                HAVING COUNT(*) >= 2
            )
            """,
        )
        missing_submission_snapshots = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM subject_metric_snapshots sms
            LEFT JOIN submissions s ON sms.submission_id = s.id
            WHERE sms.submission_id IS NOT NULL AND s.id IS NULL
            """,
        )
        missing_subject_snapshots = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM subject_metric_snapshots sms
            LEFT JOIN subjects sub ON sms.subject_id = sub.id
            WHERE sub.id IS NULL
            """,
        )
        feature_anchor_orphans = _count(
            conn,
            """
            SELECT COUNT(*)
            FROM subject_feature_sets sfs
            LEFT JOIN subject_metric_snapshots sms ON sfs.anchor_snapshot_id = sms.snapshot_id
            WHERE sfs.anchor_snapshot_id IS NOT NULL AND sms.snapshot_id IS NULL
            """,
        )
        linked_reports = _count(conn, "SELECT COUNT(*) FROM report_user_links")
        notes = _count(conn, "SELECT COUNT(*) FROM report_notes")
        source_kinds = _count(conn, "SELECT COUNT(DISTINCT source_kind) FROM subject_metric_snapshots")
    finally:
        conn.close()

    checks = [
        {
            "name": "dense_subjects_present",
            "ok": counts["subjects"] >= 100,
            "detail": counts["subjects"],
        },
        {
            "name": "snapshots_materialized",
            "ok": counts["subject_metric_snapshots"] > counts["subjects"],
            "detail": counts["subject_metric_snapshots"],
        },
        {
            "name": "feature_sets_materialized",
            "ok": counts["subject_feature_sets"] >= counts["subject_metric_snapshots"],
            "detail": counts["subject_feature_sets"],
        },
        {
            "name": "duplicates_visible",
            "ok": duplicate_submissions >= 10,
            "detail": duplicate_submissions,
        },
        {
            "name": "repeated_subjects_visible",
            "ok": repeated_subjects >= 20,
            "detail": repeated_subjects,
        },
        {
            "name": "mixed_sources_present",
            "ok": source_kinds >= 3,
            "detail": source_kinds,
        },
        {
            "name": "linked_reports_present",
            "ok": linked_reports >= 5,
            "detail": linked_reports,
        },
        {
            "name": "notes_present",
            "ok": notes >= 5,
            "detail": notes,
        },
        {
            "name": "no_orphan_snapshots",
            "ok": missing_submission_snapshots == 0 and missing_subject_snapshots == 0,
            "detail": {
                "missing_submission_snapshots": missing_submission_snapshots,
                "missing_subject_snapshots": missing_subject_snapshots,
            },
        },
        {
            "name": "no_orphan_feature_anchors",
            "ok": feature_anchor_orphans == 0,
            "detail": feature_anchor_orphans,
        },
    ]
    return {"counts": counts, "checks": checks}


def _http_checks(db_path: Path, data_root: Path, published_dir: Path) -> dict:
    os.environ["ENABLE_LOCAL_DEV_LOGIN"] = "1"
    os.environ["DEV_LOGIN_EMAIL"] = "demo-admin@cpet.local"

    app.state.db_path = db_path
    app.state.data_dir = data_root
    app.state.published_dir = published_dir
    app.state.channel_url = "http://127.0.0.1:9999"
    client = TestClient(app, raise_server_exceptions=False)
    client.get("/auth/dev-login?email=demo-admin@cpet.local&next=/dashboard?tab=reports", follow_redirects=False)

    report_page = client.get("/dashboard?tab=reports")
    manage_submissions = client.get("/manage?tab=submissions")
    manage_snapshots = client.get("/manage?tab=snapshots")
    manage_feature_sets = client.get("/manage?tab=feature_sets")
    jobs_partial = client.get("/api/jobs/partial?group_by=subject")

    report_path = None
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT report_url FROM report_catalog ORDER BY report_slug ASC LIMIT 1").fetchone()
        if row and row[0]:
            report_path = str(row[0])
    finally:
        conn.close()
    report_resp = _check_published_report_route(published_dir, report_path)

    checks = [
        {
            "name": "dashboard_reports_page_renders",
            "ok": report_page.status_code == 200 and "Reports" in report_page.text,
            "detail": report_page.status_code,
        },
        {
            "name": "grouped_reports_visible",
            "ok": jobs_partial.status_code == 200 and "중복" in jobs_partial.text,
            "detail": jobs_partial.status_code,
        },
        {
            "name": "manage_submissions_renders",
            "ok": manage_submissions.status_code == 200 and "검사 데이터 연결" in manage_submissions.text,
            "detail": manage_submissions.status_code,
        },
        {
            "name": "snapshot_explorer_renders",
            "ok": manage_snapshots.status_code == 200 and "subject_metric_snapshots" in manage_snapshots.text,
            "detail": manage_snapshots.status_code,
        },
        {
            "name": "feature_set_explorer_renders",
            "ok": manage_feature_sets.status_code == 200 and "subject_feature_sets" in manage_feature_sets.text,
            "detail": manage_feature_sets.status_code,
        },
        {
            "name": "published_report_renders",
            "ok": bool(report_resp and report_resp.status_code == 200 and "Demo Validation Report" in report_resp.text),
            "detail": report_resp.status_code if report_resp else None,
        },
    ]
    return {"checks": checks}


def _check_published_report_route(published_dir: Path, report_path: str | None):
    if not report_path:
        return None
    report_app = FastAPI()
    report_app.mount("/report", StaticFiles(directory=str(published_dir), html=True), name="report")
    report_client = TestClient(report_app, raise_server_exceptions=False)
    return report_client.get(report_path)


def _follow_up_candidates(report: dict) -> list[dict]:
    candidates: list[dict] = []
    for section in ("db", "http"):
        for check in report[section]["checks"]:
            if check["ok"]:
                continue
            candidates.append(
                {
                    "title": f"[Gap] {check['name']}",
                    "detail": check["detail"],
                }
            )
    return candidates


def build_platform_readiness_report(
    *,
    demo_root: Path,
    seed_if_missing: bool = False,
    subject_count: int = 300,
) -> dict:
    db_path = demo_root / "cpet_platform_demo.db"
    published_dir = demo_root / "published"
    if seed_if_missing and not db_path.exists():
        seed_demo_platform_validation(
            output_root=demo_root,
            subject_count=subject_count,
            reset=True,
        )

    report = {
        "demo_root": str(demo_root),
        "db": _db_checks(db_path),
        "http": _http_checks(db_path, demo_root, published_dir),
    }
    report["suggested_follow_up_tasks"] = _follow_up_candidates(report)
    report["ready"] = not report["suggested_follow_up_tasks"]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run platform-readiness QA checks against the demo DB.")
    parser.add_argument(
        "--demo-root",
        default="tmp/platform-validation-demo",
        help="Root directory of the seeded demo DB.",
    )
    parser.add_argument(
        "--seed-if-missing",
        action="store_true",
        help="Build the demo DB first if it does not exist.",
    )
    parser.add_argument(
        "--subject-count",
        type=int,
        default=300,
        help="Used only when --seed-if-missing triggers demo seeding.",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional path to persist the QA report JSON.",
    )
    args = parser.parse_args()

    report = build_platform_readiness_report(
        demo_root=Path(args.demo_root),
        seed_if_missing=args.seed_if_missing,
        subject_count=args.subject_count,
    )
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
