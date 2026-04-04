"""
Build a deterministic demo DB for platform-scale validation.

This seeder intentionally prioritizes platform density and operational realism
over parser-perfect raw file realism. It creates a separate SQLite database,
workspace/raw placeholders, published demo reports, and downstream snapshot /
feature tables so dashboard/manage/explorer surfaces become meaningfully dense.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from server.db import (
    backfill_endurance_core_feature_sets,
    backfill_longitudinal_delta_feature_sets,
    complete_onboarding,
    create_job,
    create_subject,
    create_submission,
    init_db,
    link_report_to_user,
    link_user_to_subject,
    set_report_name_override,
    set_report_note,
    update_job_status,
    update_user_role,
    upsert_report_catalog_entry,
    upsert_subject_metric_snapshot,
    upsert_user,
    upsert_user_profile,
)

DEFAULT_SEED = 20260404
DEFAULT_SUBJECT_COUNT = 300

KOREAN_FAMILY = [
    "김", "이", "박", "최", "정", "조", "윤", "장", "임", "한",
    "신", "서", "권", "황", "안", "송", "오", "전", "홍", "유",
]
KOREAN_GIVEN = [
    "민준", "서준", "도윤", "예준", "지호", "하준", "시우", "우진", "주원", "건우",
    "서연", "서윤", "지우", "하은", "민서", "지유", "채원", "가은", "수아", "예린",
    "동욱", "대순", "금현", "정인", "양우", "현진", "근윤", "정훈", "우찬", "창선",
]
ENGLISH_FIRST = [
    "Miso", "Jongku", "Gerald", "Brian", "Youngsu", "Jordan", "Kai", "Ethan",
    "Mina", "Chloe", "Sora", "Noah", "Olivia", "Liam", "Emma", "Lucas",
]
ENGLISH_LAST = [
    "Kim", "Lee", "Park", "Joo", "Hong", "Yoo", "Han", "Cho", "Seo", "Lim",
]
TRAINING_LEVELS = ["초보", "중급", "상급"]
GENDERS = ["남성", "여성"]


@dataclass(frozen=True)
class SeedPaths:
    root: Path
    db_path: Path
    workspaces_dir: Path
    published_dir: Path


@dataclass(frozen=True)
class ScenarioCounters:
    subject_count: int
    cpet_only: int
    cpet_fit: int
    inscyd_fit: int
    mixed_same_day: int
    standalone_only: int


def _slugify(value: str) -> str:
    safe = []
    for char in value.lower():
        if char.isalnum():
            safe.append(char)
        elif char in {" ", "-", "_"}:
            safe.append("-")
    slug = "".join(safe).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "subject"


def _ensure_clean_root(root: Path, reset: bool) -> None:
    if root.exists():
        if not reset:
            raise SystemExit(
                f"Refusing to seed into existing demo root without --reset: {root}"
            )
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)


def _seed_paths(output_root: Path) -> SeedPaths:
    return SeedPaths(
        root=output_root,
        db_path=output_root / "cpet_platform_demo.db",
        workspaces_dir=output_root / "workspaces",
        published_dir=output_root / "published",
    )


def _scenario_counters(subject_count: int) -> ScenarioCounters:
    standalone_only = max(1, round(subject_count * 0.05))
    mixed_same_day = max(1, round(subject_count * 0.10))
    inscyd_fit = max(1, round(subject_count * 0.15))
    cpet_fit = max(1, round(subject_count * 0.25))
    cpet_only = subject_count - standalone_only - mixed_same_day - inscyd_fit - cpet_fit
    return ScenarioCounters(
        subject_count=subject_count,
        cpet_only=cpet_only,
        cpet_fit=cpet_fit,
        inscyd_fit=inscyd_fit,
        mixed_same_day=mixed_same_day,
        standalone_only=standalone_only,
    )


def _build_demo_report_html(
    *,
    subject_name: str,
    report_slug: str,
    measured_at: str,
    source_label: str,
    metrics: dict[str, float | str | None],
    scenario_label: str,
) -> str:
    rows = []
    for label, value in (
        ("VO2max rel", metrics.get("vo2max_rel")),
        ("LT1 Power", metrics.get("lt1_power_w")),
        ("LT2 Power", metrics.get("lt2_power_w")),
        ("FatMax Power", metrics.get("fatmax_power_w")),
        ("VLaMax", metrics.get("vlamax")),
    ):
        display = "—" if value is None else value
        rows.append(f"<tr><th>{label}</th><td>{display}</td></tr>")
    body = "\n".join(rows)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{subject_name} Demo Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px; color: #0f172a; }}
    .card {{ max-width: 840px; margin: 0 auto; padding: 32px; border: 1px solid #e2e8f0; border-radius: 18px; }}
    .eyebrow {{ color: #2563eb; font-weight: 700; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 24px; }}
    th, td {{ border-bottom: 1px solid #e2e8f0; padding: 10px 0; text-align: left; }}
    th {{ width: 180px; color: #475569; font-weight: 600; }}
    .meta {{ color: #64748b; font-size: 14px; }}
    .slug {{ color: #94a3b8; font-size: 13px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="eyebrow">Demo Validation Report</div>
    <h1>{subject_name}</h1>
    <p class="meta">{measured_at} · {source_label} · {scenario_label}</p>
    <p class="slug">{report_slug}</p>
    <table>{body}</table>
  </div>
</body>
</html>
"""


def _write_workspace_files(workspace_path: Path, manifest: list[dict]) -> None:
    raw_dir = workspace_path / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for item in manifest:
        filename = str(item["name"])
        content = str(item.get("content") or "").encode("utf-8")
        (raw_dir / filename).write_bytes(content)


def _manifest_entry(name: str, content: str) -> dict:
    data = content.encode("utf-8")
    return {
        "name": name,
        "extension": Path(name).suffix.lstrip("."),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "content": content,
    }


def _file_manifest(
    *,
    subject_slug: str,
    measured_at: str,
    include_fit: bool = False,
    include_inscyd: bool = False,
    include_lactate: bool = False,
    duplicate_payload_key: str = "",
) -> list[dict]:
    date_token = measured_at.replace("-", "")
    payload_key = duplicate_payload_key or f"{subject_slug}-{date_token}"
    manifest = [
        _manifest_entry(
            f"{subject_slug}-{date_token}.xlsx",
            f"CPET demo payload::{payload_key}::{date_token}",
        )
    ]
    if include_fit:
        manifest.append(
            _manifest_entry(
                f"{subject_slug}-{date_token}.fit",
                f"FIT demo payload::{payload_key}::{date_token}",
            )
        )
    if include_inscyd:
        manifest.append(
            _manifest_entry(
                f"{subject_slug}-{date_token}.pdf",
                f"INSCYD demo payload::{payload_key}::{date_token}",
            )
        )
    if include_lactate:
        manifest.append(
            _manifest_entry(
                f"{subject_slug}-{date_token}-lactate.csv",
                f"lactate demo payload::{payload_key}::{date_token}",
            )
        )
    return manifest


def _source_signature(manifest: list[dict]) -> str:
    tags = []
    for item in manifest:
        ext = f".{item['extension'].lower()}"
        if ext == ".xlsx":
            tags.append("CPET")
        elif ext == ".fit":
            tags.append("FIT")
        elif ext == ".pdf":
            tags.append("INSCYD")
        elif ext == ".csv":
            tags.append("Lactate")
    return "+".join(sorted(set(tags)))


def _submission_fingerprint(manifest: list[dict]) -> str:
    parts = []
    for item in sorted(manifest, key=lambda row: str(row["name"]).lower()):
        parts.append(f"{item['name'].lower()}:{item['sha256']}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _duplicate_group_key(anchor: str, measured_at: str, source_signature: str) -> str:
    if not anchor:
        return ""
    raw = f"{anchor}|{measured_at}|{source_signature}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _name_for_index(index: int) -> str:
    if index % 5 in (0, 1, 2):
        family = KOREAN_FAMILY[index % len(KOREAN_FAMILY)]
        given = KOREAN_GIVEN[index % len(KOREAN_GIVEN)]
        return f"{family}{given}"
    first = ENGLISH_FIRST[index % len(ENGLISH_FIRST)]
    last = ENGLISH_LAST[(index // len(ENGLISH_FIRST)) % len(ENGLISH_LAST)]
    return f"{first} {last}"


def _base_date_for_subject(index: int) -> date:
    return date(2025, 1, 5) + timedelta(days=(index * 3) % 420)


def _history_length(index: int, rng: random.Random) -> int:
    if index < 150:
        return 1
    if index < 255:
        return rng.choice([2, 2, 3, 3])
    if index < 290:
        return rng.choice([4, 5, 6])
    return rng.choice([7, 8, 9])


def _source_mode(index: int, counters: ScenarioCounters) -> str:
    thresholds = (
        counters.cpet_only,
        counters.cpet_only + counters.cpet_fit,
        counters.cpet_only + counters.cpet_fit + counters.inscyd_fit,
        counters.cpet_only + counters.cpet_fit + counters.inscyd_fit + counters.mixed_same_day,
    )
    if index < thresholds[0]:
        return "cpet_only"
    if index < thresholds[1]:
        return "cpet_fit"
    if index < thresholds[2]:
        return "inscyd_fit"
    if index < thresholds[3]:
        return "mixed_same_day"
    return "standalone_only"


def _trend_pattern(rng: random.Random, history_length: int) -> str:
    if history_length <= 1:
        return "baseline"
    return rng.choices(
        ["improver", "stable", "regressor", "noisy"],
        weights=[0.35, 0.3, 0.15, 0.2],
        k=1,
    )[0]


def _next_metrics(
    *,
    rng: random.Random,
    previous: dict[str, float] | None,
    pattern: str,
    source_kind: str,
    missing: bool,
    measured_at: str,
    subject_id: str,
    source_ref_id: str,
    submission_id: str | None,
) -> tuple[dict, dict[str, float]]:
    if previous is None:
        state = {
            "vo2max_rel": round(rng.uniform(34, 67), 1),
            "lt1_power_w": round(rng.uniform(120, 245), 1),
            "lt2_power_w": round(rng.uniform(170, 320), 1),
            "fatmax_power_w": round(rng.uniform(100, 220), 1),
            "fatmax_gmin": round(rng.uniform(0.22, 0.68), 2),
            "vlamax": round(rng.uniform(0.25, 0.85), 2),
            "at_power_w": round(rng.uniform(160, 300), 1),
            "carbmax_w": round(rng.uniform(240, 420), 1),
            "glycogen_g": round(rng.uniform(260, 620), 1),
        }
    else:
        trend_map = {
            "improver": (1.4, 8.5),
            "stable": (0.2, 2.5),
            "regressor": (-1.2, -6.0),
            "noisy": (rng.uniform(-0.9, 1.1), rng.uniform(-8.0, 8.0)),
            "baseline": (0.0, 0.0),
        }
        vo2_delta, power_delta = trend_map[pattern]
        state = {
            "vo2max_rel": round(previous["vo2max_rel"] + vo2_delta + rng.uniform(-0.4, 0.5), 1),
            "lt1_power_w": round(previous["lt1_power_w"] + power_delta + rng.uniform(-4, 5), 1),
            "lt2_power_w": round(previous["lt2_power_w"] + power_delta * 1.2 + rng.uniform(-5, 6), 1),
            "fatmax_power_w": round(previous["fatmax_power_w"] + power_delta * 0.8 + rng.uniform(-4, 4), 1),
            "fatmax_gmin": round(max(0.16, previous["fatmax_gmin"] + rng.uniform(-0.04, 0.04)), 2),
            "vlamax": round(max(0.15, previous["vlamax"] + rng.uniform(-0.08, 0.08)), 2),
            "at_power_w": round(previous["at_power_w"] + power_delta + rng.uniform(-5, 5), 1),
            "carbmax_w": round(previous["carbmax_w"] + power_delta * 1.3 + rng.uniform(-6, 6), 1),
            "glycogen_g": round(max(180, previous["glycogen_g"] + rng.uniform(-35, 35)), 1),
        }

    if source_kind == "inscyd_report":
        state["vlamax"] = round(max(0.15, state["vlamax"] + rng.uniform(-0.03, 0.03)), 2)
        state["fatmax_gmin"] = round(max(0.14, state["fatmax_gmin"] + rng.uniform(-0.02, 0.02)), 2)
    elif source_kind == "published_cpet_report":
        state["vo2max_rel"] = round(state["vo2max_rel"] + rng.uniform(-0.5, 0.5), 1)

    payload = {
        "subject_id": subject_id,
        "source_kind": source_kind,
        "source_ref_id": source_ref_id,
        "submission_id": submission_id,
        "measured_at": measured_at,
        "protocol_type": (
            "INSCYD Report" if source_kind == "inscyd_report" else "Belgium Lactate Test Elite"
        ),
        "vo2max_ml": round(state["vo2max_rel"] * rng.uniform(3000, 4500) / 55, 1),
        "vo2max_rel": state["vo2max_rel"],
        "lt1_power_w": state["lt1_power_w"],
        "lt2_power_w": state["lt2_power_w"],
        "fatmax_power_w": state["fatmax_power_w"],
        "fatmax_gmin": state["fatmax_gmin"],
        "vlamax": state["vlamax"],
        "at_power_w": state["at_power_w"],
        "carbmax_w": state["carbmax_w"],
        "glycogen_g": state["glycogen_g"],
        "extraction_version": "demo_seed_v1",
        "quality_flags_json": json.dumps(["synthetic_demo"] + (["partial_case"] if missing else [])),
        "payload_json": json.dumps(
            {
                "demo": True,
                "source": source_kind,
                "metrics": state,
            },
            ensure_ascii=True,
            sort_keys=True,
        ),
    }

    if missing:
        payload["fatmax_gmin"] = None
        payload["vlamax"] = None if source_kind != "inscyd_report" else payload["vlamax"]
        payload["glycogen_g"] = None

    return payload, state


def _publish_report(
    paths: SeedPaths,
    *,
    report_slug: str,
    subject_name: str,
    measured_at: str,
    source_label: str,
    scenario_label: str,
    metrics: dict,
) -> str:
    report_dir = paths.published_dir / report_slug
    report_dir.mkdir(parents=True, exist_ok=True)
    html = _build_demo_report_html(
        subject_name=subject_name,
        report_slug=report_slug,
        measured_at=measured_at,
        source_label=source_label,
        metrics=metrics,
        scenario_label=scenario_label,
    )
    (report_dir / "index.html").write_text(html, encoding="utf-8")
    return f"/report/{report_slug}/"


def seed_demo_platform_validation(
    *,
    output_root: Path,
    subject_count: int = DEFAULT_SUBJECT_COUNT,
    seed: int = DEFAULT_SEED,
    reset: bool = False,
) -> dict:
    rng = random.Random(seed)
    paths = _seed_paths(output_root)
    _ensure_clean_root(paths.root, reset=reset)
    paths.workspaces_dir.mkdir(parents=True, exist_ok=True)
    paths.published_dir.mkdir(parents=True, exist_ok=True)

    init_db(paths.db_path)
    counters = _scenario_counters(subject_count)

    admin = upsert_user(
        paths.db_path,
        google_id="demo-admin",
        email="demo-admin@cpet.local",
        display_name="Demo Admin",
    )
    complete_onboarding(paths.db_path, admin["id"], "Demo Admin")
    update_user_role(paths.db_path, admin["id"], "admin")

    for idx in range(3):
        user = upsert_user(
            paths.db_path,
            google_id=f"demo-researcher-{idx}",
            email=f"demo-researcher-{idx}@cpet.local",
            display_name=f"Demo Researcher {idx + 1}",
        )
        complete_onboarding(paths.db_path, user["id"], user["display_name"])
        update_user_role(paths.db_path, user["id"], "researcher")

    summary = {
        "seed": seed,
        "subject_count": subject_count,
        "users_seeded": 4,
        "submissions_seeded": 0,
        "jobs_seeded": 0,
        "reports_seeded": 0,
        "snapshots_seeded": 0,
        "duplicate_candidates": 0,
    }

    for index in range(subject_count):
        name = _name_for_index(index)
        subject_slug = _slugify(name)
        gender = GENDERS[index % len(GENDERS)]
        birth_year = 1968 + (index % 32)
        height_cm = round(158 + (index % 23) + rng.uniform(0, 0.9), 1)
        weight_kg = round(50 + (index % 31) + rng.uniform(0, 0.9), 1)
        training_level = TRAINING_LEVELS[index % len(TRAINING_LEVELS)]
        subject = create_subject(
            paths.db_path,
            name=name,
            gender=gender,
            birth_year=birth_year,
            height_cm=height_cm,
            weight_kg=weight_kg,
            bmi=round(weight_kg / ((height_cm / 100) ** 2), 1),
            training_level=training_level,
            notes="synthetic-demo subject",
        )

        mode = _source_mode(index, counters)
        history_length = _history_length(index, rng)
        pattern = _trend_pattern(rng, history_length)
        missing_case = (index % 5 == 0)
        duplicate_case = (index % 6 == 0)
        user = None

        if index < round(subject_count * 0.7) or mode in {"mixed_same_day", "standalone_only"}:
            user = upsert_user(
                paths.db_path,
                google_id=f"demo-user-{index:04d}",
                email=f"demo-user-{index:04d}@cpet.local",
                display_name=name,
            )
            complete_onboarding(paths.db_path, user["id"], name)
            upsert_user_profile(
                paths.db_path,
                user["id"],
                weight_kg=weight_kg,
                height_cm=height_cm,
                body_fat_pct=round(rng.uniform(9.5, 28.0), 1),
                skeletal_muscle_mass=round(rng.uniform(23.0, 39.0), 1),
                bmi=round(weight_kg / ((height_cm / 100) ** 2), 1),
                birth_year=birth_year,
                gender=gender,
                training_level=training_level,
                measured_at=str(_base_date_for_subject(index)),
            )
            link_user_to_subject(paths.db_path, user["id"], subject["id"])
            summary["users_seeded"] += 1

        state = None
        subject_anchor = user["id"] if user else subject["id"]
        start_date = _base_date_for_subject(index)

        if mode == "standalone_only":
            report_slug = f"{subject_slug}-{start_date.strftime('%Y%m%d')}-demo"
            metrics, state = _next_metrics(
                rng=rng,
                previous=state,
                pattern=pattern,
                source_kind="published_cpet_report",
                missing=missing_case,
                measured_at=str(start_date),
                subject_id=subject["id"],
                source_ref_id=report_slug,
                submission_id=None,
            )
            report_url = _publish_report(
                paths,
                report_slug=report_slug,
                subject_name=name,
                measured_at=str(start_date),
                source_label="Standalone Published",
                scenario_label=mode,
                metrics=metrics,
            )
            upsert_report_catalog_entry(
                paths.db_path,
                report_slug=report_slug,
                subject_name=name,
                test_date=str(start_date),
                analysis_method="Synthetic CPET Demo",
                report_version="demo-v1",
                report_url=report_url,
                completed_at=f"{start_date}T09:00:00+00:00",
                file_tags=["CPET"],
            )
            if user:
                link_report_to_user(paths.db_path, report_slug, user["id"])
            if index % 9 == 0:
                set_report_note(paths.db_path, report_slug, "Demo standalone report note")
            if index % 13 == 0:
                set_report_name_override(paths.db_path, report_slug, name)
            upsert_subject_metric_snapshot(paths.db_path, metrics)
            summary["reports_seeded"] += 1
            summary["snapshots_seeded"] += 1
            continue

        for test_idx in range(history_length):
            measured_date = start_date + timedelta(days=test_idx * rng.choice([18, 28, 35, 42]))
            measured_at = str(measured_date)
            include_fit = mode in {"cpet_fit", "inscyd_fit", "mixed_same_day"} and (test_idx % 2 == 0 or mode != "cpet_fit")
            include_lactate = test_idx % 3 == 0
            use_inscyd = mode == "inscyd_fit" and (test_idx == history_length - 1 or test_idx % 2 == 1)

            manifest = _file_manifest(
                subject_slug=subject_slug,
                measured_at=measured_at,
                include_fit=include_fit,
                include_inscyd=use_inscyd,
                include_lactate=include_lactate,
            )
            source_signature = _source_signature(manifest)
            submission_fingerprint = _submission_fingerprint(manifest)
            duplicate_group_key = _duplicate_group_key(subject_anchor, measured_at, source_signature)
            workspace_path = paths.workspaces_dir / f"{subject_slug}-{measured_date.strftime('%Y%m%d')}-{test_idx}"
            _write_workspace_files(workspace_path, manifest)
            submission_id = create_submission(
                paths.db_path,
                description=f"Synthetic {mode} session for {name}",
                file_manifest=[{k: v for k, v in item.items() if k != "content"} for item in manifest],
                workspace_path=str(workspace_path),
                subject_name=name,
                test_date=measured_at,
                user_id=user["id"] if user else None,
                subject_id=subject["id"],
                uploaded_by_user_id=admin["id"],
                source_signature=source_signature,
                submission_fingerprint=submission_fingerprint,
                duplicate_confidence="likely" if duplicate_case else "",
                duplicate_group_key=duplicate_group_key if duplicate_case else "",
            )
            summary["submissions_seeded"] += 1

            job_id = create_job(paths.db_path, submission_id)
            summary["jobs_seeded"] += 1

            report_slug = f"{subject_slug}-{measured_date.strftime('%Y%m%d')}"
            if test_idx:
                report_slug = f"{report_slug}-{test_idx + 1}"
            source_kind = "inscyd_report" if use_inscyd else "cpet_submission"
            report_label = "INSCYD + FIT" if use_inscyd else "CPET"

            metrics, state = _next_metrics(
                rng=rng,
                previous=state,
                pattern=pattern,
                source_kind=source_kind,
                missing=missing_case and test_idx % 2 == 0,
                measured_at=measured_at,
                subject_id=subject["id"],
                source_ref_id=submission_id,
                submission_id=submission_id,
            )
            upsert_subject_metric_snapshot(paths.db_path, metrics)
            summary["snapshots_seeded"] += 1

            report_url = _publish_report(
                paths,
                report_slug=report_slug,
                subject_name=name,
                measured_at=measured_at,
                source_label=report_label,
                scenario_label=mode,
                metrics=metrics,
            )
            update_job_status(
                paths.db_path,
                job_id,
                "done",
                report_slug=report_slug,
                report_url=report_url,
            )
            upsert_report_catalog_entry(
                paths.db_path,
                report_slug=report_slug,
                subject_name=name,
                test_date=measured_at,
                analysis_method="Synthetic INSCYD Demo" if use_inscyd else "Synthetic CPET Demo",
                report_version="demo-v1",
                report_url=report_url,
                completed_at=f"{measured_at}T10:00:00+00:00",
                file_tags=source_signature.split("+") if source_signature else [],
            )
            summary["reports_seeded"] += 1
            if index % 8 == 0 and test_idx == 0:
                set_report_note(paths.db_path, report_slug, "초기 베이스라인 메모")
            if index % 17 == 0 and test_idx == 0:
                set_report_name_override(paths.db_path, report_slug, name)

            if mode == "mixed_same_day" and test_idx == max(0, history_length - 2):
                mixed_manifest = _file_manifest(
                    subject_slug=subject_slug,
                    measured_at=measured_at,
                    include_fit=True,
                    include_inscyd=True,
                )
                mixed_submission_id = create_submission(
                    paths.db_path,
                    description=f"Synthetic mixed-source same-day INSCYD session for {name}",
                    file_manifest=[{k: v for k, v in item.items() if k != "content"} for item in mixed_manifest],
                    workspace_path=str(paths.workspaces_dir / f"{subject_slug}-{measured_date.strftime('%Y%m%d')}-mixed"),
                    subject_name=name,
                    test_date=measured_at,
                    user_id=user["id"] if user else None,
                    subject_id=subject["id"],
                    uploaded_by_user_id=admin["id"],
                    source_signature=_source_signature(mixed_manifest),
                    submission_fingerprint=_submission_fingerprint(mixed_manifest),
                    duplicate_confidence="likely",
                    duplicate_group_key=_duplicate_group_key(subject_anchor, measured_at, _source_signature(mixed_manifest)),
                )
                _write_workspace_files(paths.workspaces_dir / f"{subject_slug}-{measured_date.strftime('%Y%m%d')}-mixed", mixed_manifest)
                mixed_job_id = create_job(paths.db_path, mixed_submission_id)
                mixed_slug = f"{report_slug}-inscyd"
                mixed_metrics, state = _next_metrics(
                    rng=rng,
                    previous=state,
                    pattern="noisy",
                    source_kind="inscyd_report",
                    missing=False,
                    measured_at=measured_at,
                    subject_id=subject["id"],
                    source_ref_id=mixed_submission_id,
                    submission_id=mixed_submission_id,
                )
                upsert_subject_metric_snapshot(paths.db_path, mixed_metrics)
                mixed_report_url = _publish_report(
                    paths,
                    report_slug=mixed_slug,
                    subject_name=name,
                    measured_at=measured_at,
                    source_label="Same-day INSCYD",
                    scenario_label=mode,
                    metrics=mixed_metrics,
                )
                update_job_status(
                    paths.db_path,
                    mixed_job_id,
                    "done",
                    report_slug=mixed_slug,
                    report_url=mixed_report_url,
                )
                upsert_report_catalog_entry(
                    paths.db_path,
                    report_slug=mixed_slug,
                    subject_name=name,
                    test_date=measured_at,
                    analysis_method="Synthetic Mixed Source Demo",
                    report_version="demo-v1",
                    report_url=mixed_report_url,
                    completed_at=f"{measured_at}T11:00:00+00:00",
                    file_tags=["FIT", "INSCYD"],
                )
                summary["submissions_seeded"] += 1
                summary["jobs_seeded"] += 1
                summary["reports_seeded"] += 1
                summary["snapshots_seeded"] += 1
                summary["duplicate_candidates"] += 1

            if duplicate_case and test_idx == 0:
                duplicate_manifest = _file_manifest(
                    subject_slug=subject_slug,
                    measured_at=measured_at,
                    include_fit=include_fit,
                    include_inscyd=use_inscyd,
                    include_lactate=include_lactate,
                    duplicate_payload_key=f"{subject_slug}-{measured_date.strftime('%Y%m%d')}-dupcluster",
                )
                dup_workspace = paths.workspaces_dir / f"{subject_slug}-{measured_date.strftime('%Y%m%d')}-dup"
                _write_workspace_files(dup_workspace, duplicate_manifest)
                duplicate_submission_id = create_submission(
                    paths.db_path,
                    description=f"Synthetic duplicate candidate for {name}",
                    file_manifest=[{k: v for k, v in item.items() if k != 'content'} for item in duplicate_manifest],
                    workspace_path=str(dup_workspace),
                    subject_name=name,
                    test_date=measured_at,
                    user_id=user["id"] if user else None,
                    subject_id=subject["id"],
                    uploaded_by_user_id=admin["id"],
                    source_signature=source_signature,
                    submission_fingerprint=submission_fingerprint,
                    duplicate_confidence="exact",
                    duplicate_group_key=duplicate_group_key,
                )
                duplicate_job_id = create_job(paths.db_path, duplicate_submission_id)
                duplicate_slug = f"{report_slug}-dup"
                duplicate_metrics = dict(metrics)
                duplicate_metrics["source_ref_id"] = duplicate_submission_id
                duplicate_metrics["submission_id"] = duplicate_submission_id
                duplicate_metrics["payload_json"] = metrics["payload_json"]
                upsert_subject_metric_snapshot(paths.db_path, duplicate_metrics)
                duplicate_report_url = _publish_report(
                    paths,
                    report_slug=duplicate_slug,
                    subject_name=name,
                    measured_at=measured_at,
                    source_label=f"{report_label} Duplicate",
                    scenario_label="duplicate_case",
                    metrics=duplicate_metrics,
                )
                update_job_status(
                    paths.db_path,
                    duplicate_job_id,
                    "done",
                    report_slug=duplicate_slug,
                    report_url=duplicate_report_url,
                )
                upsert_report_catalog_entry(
                    paths.db_path,
                    report_slug=duplicate_slug,
                    subject_name=name,
                    test_date=measured_at,
                    analysis_method="Synthetic Duplicate Demo",
                    report_version="demo-v1",
                    report_url=duplicate_report_url,
                    completed_at=f"{measured_at}T12:00:00+00:00",
                    file_tags=source_signature.split("+") if source_signature else [],
                )
                summary["submissions_seeded"] += 1
                summary["jobs_seeded"] += 1
                summary["reports_seeded"] += 1
                summary["snapshots_seeded"] += 1
                summary["duplicate_candidates"] += 1

    feature_endurance = backfill_endurance_core_feature_sets(paths.db_path)
    feature_longitudinal = backfill_longitudinal_delta_feature_sets(paths.db_path)
    summary["feature_rows_seeded"] = (
        int(feature_endurance["inserted"])
        + int(feature_endurance["updated"])
        + int(feature_longitudinal["inserted"])
        + int(feature_longitudinal["updated"])
    )
    summary["db_path"] = str(paths.db_path)
    summary["published_dir"] = str(paths.published_dir)
    return summary


def _count_rows(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        tables = [
            "subjects",
            "users",
            "submissions",
            "jobs",
            "report_catalog",
            "subject_metric_snapshots",
            "subject_feature_sets",
        ]
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic platform validation demo DB.")
    parser.add_argument(
        "--output-root",
        default="tmp/platform-validation-demo",
        help="Directory that will contain the isolated demo DB, workspaces, and published reports.",
    )
    parser.add_argument(
        "--subject-count",
        type=int,
        default=DEFAULT_SUBJECT_COUNT,
        help="How many demo subjects to generate.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Deterministic RNG seed.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete an existing output root before rebuilding the demo DB.",
    )
    args = parser.parse_args()

    summary = seed_demo_platform_validation(
        output_root=Path(args.output_root),
        subject_count=args.subject_count,
        seed=args.seed,
        reset=args.reset,
    )
    counts = _count_rows(Path(summary["db_path"]))
    print(json.dumps({"summary": summary, "counts": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
