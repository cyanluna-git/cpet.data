"""Workspace parsing helpers for standalone INSCYD interpretation reports."""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import json
from pathlib import Path
import re
from typing import Any
from contextlib import redirect_stdout

import pandas as pd

from pipeline.inscyd_parser import InscydParser, ParsedInscydReport
from pipeline.parsers.fit import parse_fit, segment_blocks
from pipeline.parsers.zwo import parse_zwo


@dataclass
class ParsedInscydWorkspace:
    """Parsed artifacts required to render an INSCYD interpretation report."""

    report: ParsedInscydReport
    pdf_path: Path
    fit_sessions: list[dict[str, Any]] = field(default_factory=list)
    zwo_summary: dict[str, Any] = field(default_factory=dict)
    submission_context: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def subject_name(self) -> str:
        return (
            str(self.submission_context.get("subject_name") or "").strip()
            or str(self.report.athlete_name or "").strip()
            or "subject"
        )

    @property
    def test_date(self) -> str:
        submission_date = str(self.submission_context.get("test_date") or "").strip()
        if submission_date:
            return submission_date
        if self.report.report_date is not None:
            return self.report.report_date.isoformat()
        return ""


def _search_dir(workspace: Path) -> Path:
    raw_dir = workspace / "raw"
    return raw_dir if raw_dir.is_dir() else workspace


def _find_first(search_dir: Path, patterns: list[str]) -> Path | None:
    for pattern in patterns:
        matches = sorted(search_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def _load_submission_context(workspace: Path) -> dict[str, Any]:
    metadata_dir = workspace / "metadata"
    payload: dict[str, Any] = {}
    for candidate in ("submission_context.json", "protocol_context.json"):
        path = metadata_dir / candidate
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            payload.update(data)
    return payload


def _extract_zwo_name(text: str) -> str:
    patterns = [
        r"<name>(.*?)</name>",
        r"<Name>(.*?)</Name>",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return ""


def _fallback_zwo_summary(zwo_path: Path) -> dict[str, Any]:
    text = zwo_path.read_text(encoding="utf-8", errors="ignore")
    clean = re.sub(r"\s+", " ", text).strip()
    return {
        "name": _extract_zwo_name(text) or zwo_path.stem.replace("_", " "),
        "source": zwo_path.name,
        "stage_count": clean.lower().count("<steadystate") + clean.lower().count("<freeride"),
        "summary": clean[:400],
    }


def _best_rolling_power(workout_df: pd.DataFrame, duration_sec: int) -> float | None:
    if duration_sec <= 0 or workout_df.empty or "power_w" not in workout_df.columns:
        return None
    series = workout_df["power_w"].fillna(0)
    if len(series) < duration_sec:
        return None
    best = series.rolling(window=duration_sec, min_periods=duration_sec).mean().max()
    if pd.isna(best):
        return None
    return float(best)


def _summarize_fit_session(
    fit_path: Path,
    durations: list[int],
) -> tuple[dict[str, Any], list[str]]:
    workout_df, laps_df = parse_fit(fit_path)
    warnings: list[str] = []
    try:
        capture = io.StringIO()
        with redirect_stdout(capture):
            segmented = segment_blocks(workout_df, laps_df)
        warning_text = capture.getvalue().strip()
        if warning_text:
            warnings.extend(
                [line.strip() for line in warning_text.splitlines() if line.strip()]
            )
    except Exception as exc:  # pragma: no cover - defensive
        segmented = workout_df.copy()
        warnings.append(f"FIT segmentation failed for {fit_path.name}: {exc}")

    block_counts = {}
    if "block" in segmented.columns:
        block_counts = {
            str(key): int(value)
            for key, value in segmented["block"].value_counts().to_dict().items()
        }

    rolling_best = {
        str(duration): _best_rolling_power(workout_df, duration)
        for duration in sorted({int(d) for d in durations if d})
    }
    return (
        {
            "filename": fit_path.name,
            "record_count": int(len(workout_df)),
            "lap_count": int(len(laps_df)),
            "duration_sec": int(workout_df["elapsed_s"].max()) if not workout_df.empty else 0,
            "mean_power_w": float(workout_df["power_w"].mean()) if "power_w" in workout_df.columns else None,
            "max_power_w": float(workout_df["power_w"].max()) if "power_w" in workout_df.columns else None,
            "mean_hr_bpm": float(workout_df["hr_bpm"].mean()) if "hr_bpm" in workout_df.columns else None,
            "max_hr_bpm": float(workout_df["hr_bpm"].max()) if "hr_bpm" in workout_df.columns else None,
            "max_target_power_w": float(workout_df["target_power_w"].max()) if "target_power_w" in workout_df.columns else None,
            "block_counts": block_counts,
            "rolling_best_efforts": rolling_best,
        },
        warnings,
    )


def _build_fit_alignment(
    test_rows: list[dict[str, Any]],
    fit_sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    alignments: list[dict[str, Any]] = []
    if not test_rows or not fit_sessions:
        return alignments

    for row in test_rows:
        duration = int(row.get("duration_sec") or 0)
        if duration <= 0:
            continue
        matches: list[dict[str, Any]] = []
        for session in fit_sessions:
            best = session.get("rolling_best_efforts", {}).get(str(duration))
            if best is None:
                continue
            delta = float(best) - float(row.get("average_power_watt") or 0)
            matches.append(
                {
                    "session": session["filename"],
                    "fit_best_power_w": float(best),
                    "delta_w": round(delta, 1),
                }
            )
        if not matches:
            continue
        matches.sort(
            key=lambda item: (
                float(item["fit_best_power_w"]),
                -abs(float(item["delta_w"])),
            ),
            reverse=True,
        )
        best_match = matches[0]
        alignments.append(
            {
                "type": row.get("type"),
                "duration_sec": duration,
                "reported_average_power_watt": row.get("average_power_watt"),
                "fit_session_count": len(matches),
                **best_match,
            }
        )
    return alignments


def parse_inscyd_workspace(workspace: Path) -> ParsedInscydWorkspace:
    """Parse an INSCYD PDF workspace plus optional FIT/ZWO evidence."""
    workspace = Path(workspace).resolve()
    search_dir = _search_dir(workspace)

    pdf_path = _find_first(search_dir, ["*.pdf"])
    if pdf_path is None:
        raise FileNotFoundError(f"No INSCYD PDF found in {search_dir}")

    report = InscydParser().parse_file(pdf_path)
    submission_context = _load_submission_context(workspace)
    durations = [int(row.get("duration_sec") or 0) for row in report.test_data_rows]

    warnings = list(report.parsing_warnings)
    fit_sessions: list[dict[str, Any]] = []
    for fit_path in sorted(search_dir.glob("*.fit")):
        summary, fit_warnings = _summarize_fit_session(fit_path, durations)
        fit_sessions.append(summary)
        warnings.extend(fit_warnings)

    zwo_summary: dict[str, Any] = {}
    zwo_path = _find_first(search_dir, ["*.zwo"])
    if zwo_path is not None:
        try:
            protocol_df = parse_zwo(zwo_path)
            zwo_summary = {
                "name": _fallback_zwo_summary(zwo_path)["name"],
                "source": zwo_path.name,
                "stage_count": int(len(protocol_df)),
                "total_duration_sec": float(protocol_df["duration_s"].sum()) if not protocol_df.empty else 0,
                "stage_types": sorted({str(value) for value in protocol_df.get("stage_type", pd.Series(dtype=str)).dropna().unique()}),
            }
        except Exception as exc:
            zwo_summary = _fallback_zwo_summary(zwo_path)
            warnings.append(f"ZWO parsing fell back to text summary: {exc}")

    fit_alignment = _build_fit_alignment(report.test_data_rows, fit_sessions)
    if fit_alignment:
        zwo_summary["fit_alignment"] = fit_alignment

    return ParsedInscydWorkspace(
        report=report,
        pdf_path=pdf_path,
        fit_sessions=fit_sessions,
        zwo_summary=zwo_summary,
        submission_context=submission_context,
        warnings=warnings,
    )
