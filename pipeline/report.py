"""
pipeline.report — Static HTML report generator.

Renders a standalone Korean analysis report from SQLite outputs.
No hardcoded paths; db_path and output_dir are passed as parameters.

Canonical source: hong.changsun/analysis/report.py
"""

from __future__ import annotations

import html
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


def _safe_mean(values: list[float]) -> float | None:
    """Return the arithmetic mean when at least one value exists."""
    if not values:
        return None
    return mean(values)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _substrate_from_row(row: dict[str, Any], key: str) -> float | None:
    """Read stored substrate values or derive them from VO2/VCO2."""
    direct = row.get(key)
    should_derive = row.get("fat_gmin") is None or row.get("cho_gmin") is None
    if direct is not None:
        try:
            value = float(direct)
            if value > 20.0:
                should_derive = True
            elif not should_derive:
                return value
        except (TypeError, ValueError):
            should_derive = True

    vo2_ml = row.get("vo2_ml")
    vco2_ml = row.get("vco2_ml")
    try:
        vo2_l = float(vo2_ml) / 1000.0
        vco2_l = float(vco2_ml) / 1000.0
    except (TypeError, ValueError):
        return None

    if key == "fat_gmin":
        return max(0.0, 1.67 * vo2_l - 1.67 * vco2_l)
    if key == "cho_gmin":
        return max(0.0, 4.55 * vco2_l - 3.21 * vo2_l)
    return None


def decode_value(value: Any) -> Any:
    """Best-effort decode for mixed text / JSON payloads stored in SQLite."""
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value

    text = str(value).strip()
    if not text:
        return ""

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def fetch_rows(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Return query results as a list of dict rows."""
    cursor = conn.execute(query, params)
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def format_number(value: Any, decimals: int = 0) -> str:
    """Format numeric values consistently for Korean report text."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "예" if value else "아니오"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    if decimals == 0:
        if abs(num - round(num)) < 1e-9:
            return f"{int(round(num))}"
        return f"{num:.1f}"
    return f"{num:.{decimals}f}"


def format_datetime_text(value: str | None) -> str:
    """Normalize stored datetime text into Korean-friendly display."""
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return str(value)


def html_text(value: Any) -> str:
    """Escape arbitrary values for HTML text nodes."""
    if value is None:
        return ""
    return html.escape(str(value))


def build_protocol_summary(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group protocol stages by block for header summary cards."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in stages:
        grouped[row["block"]].append(row)

    summary: list[dict[str, Any]] = []
    for block, rows in grouped.items():
        summary.append(
            {
                "block": block,
                "steps": len(rows),
                "duration_min": round(sum(float(r["duration_s"] or 0) for r in rows) / 60.0, 1),
                "targets": _stage_targets(rows),
            }
        )
    return summary


def stage_target_w(row: dict[str, Any], ftp_w: float | None = None) -> int | None:
    """Render protocol target watts from either normalized or absolute stage values."""
    raw = row.get("power_normalized")
    if raw is None:
        return None
    value = float(raw)
    if value <= 2.0:
        if not ftp_w:
            return None
        return int(round(value * float(ftp_w)))
    return int(round(value))


def _stage_targets(rows: list[dict[str, Any]]) -> str:
    """Return a compact target range label per protocol block."""
    powers = [stage_target_w(row) for row in rows]
    powers = [power for power in powers if power is not None]
    if not powers:
        return "-"
    if min(powers) == max(powers):
        return f"{min(powers)}W"
    return f"{min(powers)}-{max(powers)}W"


def summarize_bxb_stages(bxb_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize BxB ramp data into readable stage rows."""
    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in bxb_rows:
        power = row.get("bike_power_w")
        vo2 = row.get("vo2_ml")
        if power is None or vo2 is None:
            continue
        if power <= 0 or vo2 <= 0:
            continue
        bucket = int(round(float(power) / 25.0) * 25)
        buckets[bucket].append(row)

    summary: list[dict[str, Any]] = []
    for bucket in sorted(buckets):
        rows = buckets[bucket]
        vo2_values = [
            v for v in (_coerce_float(r.get("vo2_ml")) for r in rows) if v is not None
        ]
        hr_values = [
            v for v in (_coerce_float(r.get("hr_bpm")) for r in rows) if v is not None
        ]
        rq_values = [
            v for v in (_coerce_float(r.get("rq")) for r in rows) if v is not None
        ]
        fat_values = [
            value
            for value in (_substrate_from_row(r, "fat_gmin") for r in rows)
            if value is not None
        ]
        cho_values = [
            value
            for value in (_substrate_from_row(r, "cho_gmin") for r in rows)
            if value is not None
        ]
        summary.append(
            {
                "power_w": bucket,
                "n": len(rows),
                "vo2_ml": round(_safe_mean(vo2_values) or 0.0, 1),
                "hr_bpm": round(_safe_mean(hr_values) or 0.0, 1),
                "rq": round(_safe_mean(rq_values) or 0.0, 2),
                "fat_gmin": round(_safe_mean(fat_values) or 0.0, 2),
                "cho_gmin": round(_safe_mean(cho_values) or 0.0, 2),
            }
        )
    return summary


def sample_workout_rows(rows: list[dict[str, Any]], step_s: int = 10) -> list[dict[str, Any]]:
    """Downsample workout rows for charting without losing stage flow."""
    sampled: list[dict[str, Any]] = []
    last_bucket: int | None = None
    for row in rows:
        elapsed = row.get("elapsed_s")
        if elapsed is None:
            continue
        bucket = int(float(elapsed) // step_s)
        if bucket != last_bucket:
            sampled.append(row)
            last_bucket = bucket
    return sampled


def smooth_numeric_series(
    values: list[Any],
    *,
    radius: int = 2,
    rel_threshold: float = 0.35,
    abs_threshold: float = 0.0,
    smooth_window: int = 5,
) -> list[float | None]:
    """Remove isolated local spikes and return a gently smoothed series."""
    numeric: list[float | None] = []
    for value in values:
        if value is None:
            numeric.append(None)
            continue
        try:
            numeric.append(float(value))
        except (TypeError, ValueError):
            numeric.append(None)

    cleaned = list(numeric)
    for idx, value in enumerate(numeric):
        if value is None:
            continue
        start = max(0, idx - radius)
        end = min(len(numeric), idx + radius + 1)
        window = [candidate for candidate in numeric[start:end] if candidate is not None]
        if len(window) < 3:
            continue
        local_median = median(window)
        allowed_delta = max(abs_threshold, abs(local_median) * rel_threshold)
        if abs(value - local_median) > allowed_delta:
            cleaned[idx] = float(local_median)

    smoothed: list[float | None] = []
    smooth_radius = max(0, smooth_window // 2)
    for idx, value in enumerate(cleaned):
        if value is None:
            smoothed.append(None)
            continue
        start = max(0, idx - smooth_radius)
        end = min(len(cleaned), idx + smooth_radius + 1)
        window = [candidate for candidate in cleaned[start:end] if candidate is not None]
        if not window:
            smoothed.append(value)
            continue
        smoothed.append(round(sum(window) / len(window), 4))

    return smoothed


def smooth_chart_series(
    series: dict[str, Any],
    field_configs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Apply field-specific smoothing rules to a chart series payload."""
    smoothed = dict(series)
    for field, config in field_configs.items():
        values = series.get(field)
        if not isinstance(values, list):
            continue
        smoothed[field] = smooth_numeric_series(values, **config)
    return smoothed


def rolling_mean_list(values: list[float], window: int = 5) -> list[float]:
    """Return a centered rolling mean for a short numeric list."""
    if not values:
        return []
    radius = max(0, window // 2)
    smoothed: list[float] = []
    for idx in range(len(values)):
        start = max(0, idx - radius)
        end = min(len(values), idx + radius + 1)
        window_values = values[start:end]
        smoothed.append(sum(window_values) / len(window_values))
    return smoothed


def interpolate_series(x_points: list[float], y_points: list[float], targets: list[float]) -> list[float | None]:
    """Linearly interpolate y values for the given target x coordinates."""
    if not x_points or not y_points or len(x_points) != len(y_points):
        return [None for _ in targets]

    interpolated: list[float | None] = []
    for target in targets:
        if target <= x_points[0]:
            interpolated.append(y_points[0])
            continue
        if target >= x_points[-1]:
            interpolated.append(y_points[-1])
            continue
        for idx in range(len(x_points) - 1):
            left_x = x_points[idx]
            right_x = x_points[idx + 1]
            if left_x <= target <= right_x:
                left_y = y_points[idx]
                right_y = y_points[idx + 1]
                if right_x == left_x:
                    interpolated.append(left_y)
                else:
                    ratio = (target - left_x) / (right_x - left_x)
                    interpolated.append(left_y + ratio * (right_y - left_y))
                break
    return interpolated


def interpolate_at(x_points: list[float], y_points: list[float], target: float | None) -> float | None:
    """Interpolate a single y value for the given target x."""
    if target is None:
        return None
    values = interpolate_series(x_points, y_points, [float(target)])
    return values[0] if values else None


def format_duration_hhmm(hours: float) -> str:
    """Format duration hours into H:MM."""
    whole_hours = int(hours)
    minutes = int(round((hours - whole_hours) * 60))
    if minutes == 60:
        whole_hours += 1
        minutes = 0
    return f"{whole_hours}:{minutes:02d}"


def estimate_tss(power_w: float | None, ftp_w: float | None, duration_h: float) -> int | None:
    """Estimate cycling TSS from power, FTP, and duration."""
    if not power_w or not ftp_w or ftp_w <= 0:
        return None
    intensity = float(power_w) / float(ftp_w)
    return int(round(duration_h * intensity * intensity * 100.0))


def build_metabolism_chart_payload(
    analysis: dict[str, dict[str, Any]],
    bxb_rows: list[dict[str, Any]],
    subject: dict[str, Any],
    has_blood: bool,
) -> dict[str, Any]:
    """Build the annotated metabolism chart payload used by the standalone report."""
    substrate = analysis["substrate"]
    curve = substrate.get("metabolism_power_curve") or {}
    markers = substrate.get("metabolism_markers") or {}
    power_axis = [float(value) for value in curve.get("power_w", [])]
    if not power_axis:
        return {}

    energy_buckets: dict[float, list[float]] = defaultdict(list)
    for row in bxb_rows:
        power = row.get("bike_power_w")
        ee_kcal = row.get("ee_kcal")
        vo2_ml = row.get("vo2_ml")
        rq = row.get("rq")
        if power is None or ee_kcal is None or vo2_ml is None or rq is None:
            continue
        if float(power) < 40 or float(vo2_ml) <= 100 or float(rq) >= 1.6:
            continue
        power_bin = round(float(power) / 5.0) * 5.0
        energy_buckets[power_bin].append(float(ee_kcal) / 24.0)

    energy_x = sorted(energy_buckets)
    energy_y = rolling_mean_list([median(energy_buckets[power]) for power in energy_x], window=5)
    kcal_h = interpolate_series(energy_x, energy_y, power_axis)
    valid_kcal_h = [value for value in kcal_h if value is not None]

    ftp_power = (
        float(subject.get("ftp_w"))
        if has_blood and subject.get("ftp_w") is not None
        else None
    )
    fatmax_power = markers.get("fatmax_power_w")
    fatmax_kcal_h = interpolate_at(power_axis, kcal_h, fatmax_power) if valid_kcal_h else None
    ftp_kcal_h = interpolate_at(power_axis, kcal_h, ftp_power) if valid_kcal_h else None
    fatmax_duration_h = 2.0

    return {
        "power_w": [round(value, 1) for value in power_axis],
        "fat_gmin": curve.get("fat_gmin", []),
        "cho_gmin": curve.get("cho_gmin", []),
        "kcal_h": [round(float(value), 2) if value is not None else None for value in kcal_h],
        "fatmax": {
            "power_w": fatmax_power,
            "gmin": markers.get("fatmax_gmin"),
            "zone_min_w": markers.get("fatmax_zone_min_w"),
            "zone_max_w": markers.get("fatmax_zone_max_w"),
            "kcal_h": round(float(fatmax_kcal_h), 1) if fatmax_kcal_h is not None else None,
        },
        "primary_crossover": markers.get("primary_crossover"),
        "ftp_anchor": {
            "power_w": ftp_power,
            "kcal_h": round(float(ftp_kcal_h), 1) if ftp_kcal_h is not None else None,
            "duration_h": 1.0,
        },
        "session_anchor": {
            "duration_label": format_duration_hhmm(fatmax_duration_h),
            "tss": estimate_tss(fatmax_power, ftp_power, fatmax_duration_h),
        },
        "energy_note": "Energy line uses COSMED EEkc values converted from day-scale output to kcal/h (/24).",
    }


def build_metabolic_flexibility_payload(context: dict[str, Any]) -> dict[str, Any]:
    """Build a custom metabolic flexibility summary for any CPET with RQ1 split."""
    analysis = context["analysis"]
    substrate = analysis["substrate"]
    rq1 = substrate.get("rq1_fuel_split") or {}
    status = rq1.get("status")
    if status != "computed":
        if status == "no_rq1_crossing":
            note = "이번 테스트에서는 RQ 1.0에 도달하지 않아 연료 기여율을 RQ1 기준으로 계산할 수 없습니다."
            crossing_label = "미도달"
        elif status == "insufficient_data":
            note = "RQ 1.0 기준 연료 기여율을 계산하기에 호흡 데이터가 충분하지 않습니다."
            crossing_label = "데이터 부족"
        else:
            note = "RQ 1.0 기준 연료 기여율은 이번 테스트에서 계산되지 않았습니다."
            crossing_label = "계산 불가"
        return {
            "status": status or "unavailable",
            "available": False,
            "note": note,
            "crossing_label": crossing_label,
            "formula_note": "RQ 1.0 도달 시점이 확인되면 그 지점까지의 누적 kcal를 기준으로 지방/탄수화물 기여율을 계산합니다.",
        }

    vt = analysis["ventilatory_thresholds"]
    markers = substrate.get("metabolism_markers") or {}
    fat_pct = float(rq1.get("fat_pct") or 0.0)
    cho_pct = float(rq1.get("cho_pct") or 0.0)
    crossing_power = float(rq1.get("crossing_power_w") or 0.0)
    crossover_power = float(
        (markers.get("primary_crossover") or {}).get("power_w")
        or substrate.get("crossover_power_w")
        or 0.0
    )
    fatmax_power = float(substrate.get("fatmax_power_w") or 0.0)
    vt1_power = float(vt.get("vt1_power_w") or 0.0)

    fat_share_score = min(max(fat_pct / 50.0, 0.0), 1.0) * 45.0
    crossover_score = (
        min(max(crossover_power / crossing_power, 0.0), 1.0) * 35.0
        if crossing_power > 0
        else 0.0
    )
    fatmax_score = (
        min(max(fatmax_power / vt1_power, 0.0), 1.0) * 20.0
        if vt1_power > 0
        else 0.0
    )
    score = round(fat_share_score + crossover_score + fatmax_score, 1)

    if score >= 75:
        band = "high"
        note = "지방 산화 유지와 탄수화물 전환 타이밍이 비교적 안정적인 편입니다."
    elif score >= 55:
        band = "moderate"
        note = "기본적인 전환 능력은 있으나 고강도 진입 전 탄수화물 의존이 다소 빠르게 올라옵니다."
    else:
        band = "low"
        note = "저중강도 지방 활용과 고강도 전환 사이 간격을 더 다듬을 필요가 있습니다."

    return {
        "status": "computed",
        "available": True,
        "score": score,
        "band": band,
        "note": note,
        "fat_contribution_pct": round(fat_pct, 1),
        "cho_contribution_pct": round(cho_pct, 1),
        "crossing_power_w": rq1.get("crossing_power_w"),
        "crossing_hr_bpm": rq1.get("crossing_hr_bpm"),
        "crossing_time_s": rq1.get("crossing_time_s"),
        "total_kcal": rq1.get("total_kcal"),
        "crossover_power_w": round(crossover_power, 1) if crossover_power else None,
        "fatmax_power_w": round(fatmax_power, 1) if fatmax_power else None,
        "vt1_power_w": round(vt1_power, 1) if vt1_power else None,
        "formula_note": "Custom score = fat share before RQ 1.0 (45) + crossover proximity to RQ1 power (35) + FatMax proximity to VT1 (20).",
    }


def _get_suitability(context: dict[str, Any], metric_key: str) -> dict[str, Any]:
    """Fetch protocol-aware suitability metadata for a metric."""
    return (context.get("analysis", {}).get("suitability", {}) or {}).get(metric_key, {})


def _power_band_text(band: dict[str, Any] | None) -> str | None:
    """Render a watt band when both boundaries exist."""
    if not isinstance(band, dict):
        return None
    low = band.get("low")
    high = band.get("high")
    if low is None or high is None:
        return None
    return f"{format_number(low, 1)}-{format_number(high, 1)}W"


def _vo2_range_text(payload: dict[str, Any]) -> str | None:
    """Render a relative VO2max range from suitability metadata."""
    range_rel = payload.get("range_rel_ml_kg_min")
    if not isinstance(range_rel, dict):
        return None
    low = range_rel.get("low")
    high = range_rel.get("high")
    if low is None or high is None:
        return None
    return f"{format_number(low, 1)}-{format_number(high, 1)} mL/kg/min"


def _fatmax_summary_copy(context: dict[str, Any]) -> dict[str, str]:
    """Build conservative FatMax copy from suitability metadata."""
    analysis = context["analysis"]
    substrate = analysis["substrate"]
    suitability = _get_suitability(context, "fatmax")
    status = suitability.get("status")
    band_text = _power_band_text(suitability.get("band_power_w"))
    point_power = suitability.get("point_power_w") or substrate.get("fatmax_power_w")
    point_gmin = suitability.get("point_gmin") or substrate.get("fatmax_gmin")

    if status in {"low_confidence", "indirect"} and band_text:
        headline = f"FatMax 근사 band {band_text}"
        note = f"point {format_number(point_power, 1)}W · {format_number(point_gmin, 2)} g/min"
    else:
        headline = f"FatMax {format_number(point_power, 1)}W"
        note = (
            f"Band {band_text} · {format_number(point_gmin, 2)} g/min"
            if band_text
            else f"{format_number(point_gmin, 2)} g/min"
        )
    return {"headline": headline, "note": note}


def _lt2_reference_copy(context: dict[str, Any]) -> str:
    """Render a conservative LT2 note."""
    analysis = context["analysis"]
    suitability = _get_suitability(context, "lt2")
    reference_vt2 = suitability.get("reference_vt2_power_w")
    basis = str(suitability.get("basis") or "")
    if reference_vt2 is not None:
        return (
            f"직접 lactate LT2가 아니라 {basis or '추정 LT2/FTP'} 기반 참고치이며, "
            f"가스교환 VT2는 {format_number(reference_vt2)}W입니다."
        )
    return (
        f"직접 lactate LT2가 아니라 {basis or '추정 LT2/FTP'} 기반의 보수적 기준입니다. "
        f"현재 참고치는 {format_number(analysis['training_zones'].get('lt2_power_w'))}W입니다."
    )


def build_insights(context: dict[str, Any]) -> list[str]:
    """Create short interpretation bullets for the dashboard header."""
    subject = context["subject"]
    lactate = context["analysis"]["lactate"]
    vo2max = context["analysis"]["vo2max"]
    substrate = context["analysis"]["substrate"]
    clearance = context["analysis"]["clearance"]
    hr = context["analysis"]["hr"]
    vt = context["analysis"]["ventilatory_thresholds"]
    fatmax_copy = _fatmax_summary_copy(context)
    lt1_suitability = _get_suitability(context, "lt1")
    vo2_suitability = _get_suitability(context, "vo2max")
    if not context["blood_samples"]:
        rq1_fuel = substrate.get("rq1_fuel_split") or {}
        fuel_text = (
            f"RQ 1.0 이전 총 {format_number(rq1_fuel.get('total_kcal'), 1)} kcal에서 지방 {format_number(rq1_fuel.get('fat_pct'), 1)}%, 탄수화물 {format_number(rq1_fuel.get('cho_pct'), 1)}% 비율로 에너지가 공급되었습니다."
            if rq1_fuel.get("status") == "computed"
            else "RQ 1.0 이전 연료 기여율은 안정적으로 계산되지 않았습니다."
        )
        return [
            "혈액 샘플이 없는 CPET로 해석했기 때문에 threshold와 FatMax는 직접 lactate 값이 아닌 보수적 참고치 위주로 정리했습니다.",
            f"VO2max는 {format_number(vo2max.get('vo2max_rel'), 1)} mL/kg/min로 읽히지만, 해석 근거는 {html.unescape(str(vo2_suitability.get('basis') or 'peak average'))}입니다.",
            f"{fatmax_copy['headline']} · {fatmax_copy['note']}",
            fuel_text,
            (
                f"LT1는 직접 lactate point 대신 VT1 {format_number(vt.get('vt1_power_w'))}W surrogate로만 제시합니다."
                if lt1_suitability.get("status") == "indirect"
                else f"환기 기준 VT1/VT2는 {format_number(vt.get('vt1_power_w'))}W / {format_number(vt.get('vt2_power_w'))}W로 관찰되었습니다."
            ),
        ]
    crossover = (
        (substrate.get("metabolism_markers") or {}).get("primary_crossover")
        or substrate.get("crossover_power_w")
    )
    if isinstance(crossover, dict):
        crossover_text = f"안정적인 crossover는 {format_number(crossover.get('power_w'), 1)}W로 정리되었습니다."
    elif crossover is not None:
        crossover_text = f"crossover는 {format_number(crossover)}W로 확인되었습니다."
    else:
        crossover_text = "안정적인 substrate crossover는 관찰되지 않았습니다."

    insights = [
        f"LT1는 고정값 {format_number(lactate.get('lt1_fixed_power_w'), 1)}W, D-max {format_number(lactate.get('lt1_dmax_power_w'), 1)}W로 사전 예상 {format_number(subject.get('est_lt1_w'))}W보다 약간 높게 형성되었습니다.",
        f"VO2max는 {format_number(vo2max.get('vo2max_rel'), 1)} mL/kg/min, peak power는 {format_number(vo2max.get('peak_power_achieved_w'))}W로 측정되었습니다.",
        f"{fatmax_copy['headline']}이며, {crossover_text}",
        f"Block 3에서 최저 lactate는 {format_number(clearance.get('best_clearance_power_w'))}W에서 관찰되었고, 실제 최대 심박수는 {format_number(hr.get('actual_max_hr'))}bpm입니다.",
    ]
    return insights


def build_coach_summary(context: dict[str, Any]) -> dict[str, Any]:
    """Build a concise coach-facing summary for the top of the report."""
    analysis = context["analysis"]
    lactate = analysis["lactate"]
    vo2max = analysis["vo2max"]
    substrate = analysis["substrate"]
    clearance = analysis["clearance"]
    vt = analysis["ventilatory_thresholds"]
    zones = analysis["training_zones"]
    hr = analysis["hr"]
    fatmax_copy = _fatmax_summary_copy(context)
    vo2_suitability = _get_suitability(context, "vo2max")
    if not context["blood_samples"]:
        rq1_fuel = substrate.get("rq1_fuel_split") or {}
        fuel_note = (
            f"RQ 1.0 이전 에너지 기여는 지방 {format_number(rq1_fuel.get('fat_pct'), 1)}% / 탄수화물 {format_number(rq1_fuel.get('cho_pct'), 1)}%입니다."
            if rq1_fuel.get("status") == "computed"
            else "RQ 1.0 이전 연료 기여율은 추가 확인이 필요합니다."
        )
        return {
            "headline": "2블럭 CPET 코칭 요약",
            "subheadline": "혈액 샘플이 없는 CPET이므로 직접 lactate threshold 대신 ventilatory surrogate와 범위형 연료 anchor를 우선 정리한 압축 메모입니다.",
            "bullets": [
                f"{fatmax_copy['headline']}로 보여 steady endurance는 point보다 해당 band 전후에서 연료 효율을 확인하는 편이 안전합니다.",
                fuel_note,
                f"VO2max {format_number(vo2max.get('vo2max_rel'), 1)} mL/kg/min는 {vo2_suitability.get('basis') or 'peak average'} 기반 참고치이며, VT2 {format_number(vt.get('vt2_power_w'))}W와 함께 상단 유산소 반응을 읽는 데 활용합니다.",
                f"두 번째 블럭의 10초 램프는 {format_number(vo2max.get('peak_power_achieved_w'))}W까지 올라가며 peak HR {format_number(hr.get('actual_max_hr'))}bpm를 기록했습니다.",
            ],
            "lt2_note": _lt2_reference_copy(context),
        }

    lt1_power = lactate.get("lt1_dmax_power_w") or lactate.get("lt1_fixed_power_w")
    lt2_power = zones.get("lt2_power_w")
    vt2_power = vt.get("vt2_power_w")

    return {
        "headline": "사이클링 코칭 요약",
        "subheadline": "훈련 처방과 레이스 준비 관점에서 이번 테스트를 바로 해석한 압축 메모입니다.",
        "bullets": [
            f"LT1는 {format_number(lt1_power, 1)}W 전후로 형성되어 있어 지구력 메인 볼륨은 165~180W 범위에서 가장 안정적으로 쌓는 해석이 적절합니다.",
            f"{fatmax_copy['headline']}로 읽혀 롱라이드와 연료 효율 목적의 Z2 세션은 {fatmax_copy['note']} 범위를 참고하는 편이 좋습니다.",
            f"VO2max {format_number(vo2max.get('vo2max_rel'), 1)} mL/kg/min, VT2 {format_number(vt2_power)}W를 보면 상단 유산소 용량과 고강도 대응력은 충분히 좋은 편입니다.",
            f"VO2max 직후 clearance block에서는 {format_number(clearance.get('best_clearance_power_w'))}W가 가장 낮은 lactate를 보여 회복성 tempo와 과부하 후 정렬 구간의 출발점으로 참고할 수 있습니다.",
        ],
        "lt2_note": _lt2_reference_copy(context),
    }


def build_report_registry(context: dict[str, Any]) -> dict[str, Any]:
    """Compile protocol-aware KPI and section visibility rules."""
    analysis = context["analysis"]
    report_profile = context["report_profile"]
    has_blood = bool(report_profile.get("has_blood"))
    is_two_block_cpet = bool(report_profile.get("is_two_block_cpet"))

    vo2 = _get_suitability(context, "vo2max")
    lt1 = _get_suitability(context, "lt1")
    lt2 = _get_suitability(context, "lt2")
    fatmax = _get_suitability(context, "fatmax")
    clearance = _get_suitability(context, "clearance")

    vo2_note = (
        f"{_vo2_range_text(vo2)} range"
        if vo2.get("status") == "low_confidence" and _vo2_range_text(vo2)
        else f"절대값 {format_number(analysis['vo2max'].get('vo2max_ml'), 1)} mL/min"
    )

    kpis: list[dict[str, Any]] = [
        {
            "label": "VO2max",
            "value": format_number(analysis["vo2max"].get("vo2max_rel"), 1),
            "unit": "mL/kg/min",
            "note": vo2_note,
        }
    ]

    if lt1.get("status") == "supported":
        kpis.append(
            {
                "label": "LT1 (D-max)",
                "value": format_number(analysis["lactate"].get("lt1_dmax_power_w"), 1),
                "unit": "W",
                "note": f"고정값 {format_number(analysis['lactate'].get('lt1_fixed_power_w'), 1)}W",
            }
        )
    elif lt1.get("status") == "indirect":
        kpis.append(
            {
                "label": "VT1 (간접)",
                "value": format_number(analysis["ventilatory_thresholds"].get("vt1_power_w"), 1),
                "unit": "W",
                "note": "직접 lactate LT1 없음 · ventilatory surrogate",
            }
        )

    fatmax_band = _power_band_text(fatmax.get("band_power_w"))
    if fatmax.get("status") in {"low_confidence", "indirect"} and fatmax_band:
        fatmax_value = fatmax_band
        fatmax_label = "FatMax band"
        fatmax_note = f"point {format_number(fatmax.get('point_power_w'), 1)}W"
    else:
        fatmax_value = format_number(analysis["substrate"].get("fatmax_power_w"))
        fatmax_label = "FatMax"
        fatmax_note = (
            f"{format_number((analysis['substrate'].get('rq1_fuel_split') or {}).get('fat_pct'), 1)}% fat"
            if ((analysis["substrate"].get("rq1_fuel_split") or {}).get("status") == "computed")
            else f"{format_number(analysis['substrate'].get('fatmax_gmin'), 2)} g/min"
        )
    if fatmax.get("status") != "unsupported":
        kpis.append(
            {
                "label": fatmax_label,
                "value": fatmax_value,
                "unit": "W",
                "note": fatmax_note,
            }
        )

    if lt2.get("status") != "unsupported":
        kpis.append(
            {
                "label": "LT2 참고치",
                "value": format_number(analysis["training_zones"].get("lt2_power_w")),
                "unit": "W",
                "note": (
                    f"VT2 {format_number(lt2.get('reference_vt2_power_w'))}W · 간접 기준"
                    if lt2.get("reference_vt2_power_w") is not None
                    else f"HR {format_number(analysis['training_zones'].get('lt2_hr_bpm'))} bpm · 간접 기준"
                ),
            }
        )

    kpis.extend(
        [
            {
                "label": "Peak HR",
                "value": format_number(analysis["hr"].get("actual_max_hr")),
                "unit": "bpm",
                "note": f"예측치 {format_number(analysis['hr'].get('predicted_max_hr'))} bpm",
            },
            {
                "label": "Peak Power",
                "value": format_number(analysis["vo2max"].get("peak_power_achieved_w")),
                "unit": "W",
                "note": f"VO2max 시점 {format_number(analysis['vo2max'].get('peak_power_vo2max'))}W",
            },
        ]
    )

    # CPM indices: add 4 summary KPI cards when supported
    cpm = analysis.get("cpm_indices", {})
    o2_pulse = cpm.get("o2_pulse_ml_beat", {})
    if o2_pulse.get("supported"):
        kpis.append(
            {
                "label": "O₂ Pulse",
                "value": format_number(o2_pulse.get("value"), 2),
                "unit": o2_pulse.get("unit", "mL/beat"),
                "note": o2_pulse.get("note", "VO2max / actual_max_hr"),
            }
        )

    ve_vco2 = cpm.get("ve_vco2_slope", {})
    if ve_vco2.get("supported"):
        kpis.append(
            {
                "label": "VE/VCO₂ Slope",
                "value": format_number(ve_vco2.get("value"), 1),
                "unit": ve_vco2.get("unit", ""),
                "note": ve_vco2.get("note", ""),
            }
        )

    oues = cpm.get("oues", {})
    if oues.get("supported"):
        kpis.append(
            {
                "label": "OUES",
                "value": format_number(oues.get("value"), 0),
                "unit": oues.get("unit", "mL/log(L/min)"),
                "note": oues.get("note", "Oxygen Uptake Efficiency Slope"),
            }
        )

    weber = cpm.get("weber_class", {})
    if weber.get("supported"):
        kpis.append(
            {
                "label": "Weber Class",
                "value": str(weber.get("value", "-")),
                "unit": weber.get("unit", "class"),
                "note": weber.get("note", ""),
            }
        )

    return {
        "kpis": kpis,
        "show_clearance": has_blood and clearance.get("status") == "supported",
        "show_lactate_block": has_blood,
        "hero_eyebrow": "FatMax Ramp · VO2max Ramp · CPET" if is_two_block_cpet else "Belgium Protocol · Lactate · CPET",
        "hero_heading": "Two-Block CPET Analysis" if is_two_block_cpet else "Belgium Lactate Test Analysis",
        "hero_description": (
            "혈액 샘플 없이 수행한 CPET라 direct lactate turnpoint 대신 ventilatory threshold와 substrate band를 중심으로 보수적으로 정리했습니다."
            if is_two_block_cpet or not has_blood
            else "호흡별 대사 데이터, 혈중 lactate/glucose 샘플, 워크아웃 전 구간 FIT 기록을 통합해 direct lactate와 ventilatory evidence를 함께 읽습니다."
        ),
        "block2_description": (
            "Block 1 substrate window와 Block 2 peak ramp를 나눠서 읽고, 직접 lactate가 없는 지표는 band·surrogate 중심으로 표현했습니다."
            if is_two_block_cpet or not has_blood
            else "호흡별 산소 섭취, 환기, RER, 기질 산화, VE/VO2 · VE/VCO2 변화를 통해 direct lactate와 ventilatory thresholds를 함께 검토합니다."
        ),
        "metabolism_intro": (
            "Power 축에서 Fat, CHO, energy를 함께 보되 FatMax는 point보다 band 해석을 우선하고, crossover도 참고 근거로만 표시합니다."
            if fatmax.get("status") in {"low_confidence", "indirect"}
            else "Power 축에서 Fat, CHO, energy를 함께 보고 FatMax band와 FTP 기준 hourly cost를 코칭 관점으로 해석합니다."
        ),
    }


def build_cpm_panel(cpm_indices: dict[str, Any]) -> str:
    """Build the CPM Composite Indices HTML section with 5 subsection panels.

    Returns an empty string when cpm_indices is empty or missing.
    Supported indices are shown as full cards; unsupported ones as grayed-out stubs.
    """
    if not cpm_indices:
        return ""

    def _cpm_card(key: str, label: str) -> str:
        entry = cpm_indices.get(key, {})
        if entry.get("supported"):
            value = entry.get("value")
            unit = html_text(entry.get("unit") or "")
            note = html_text(entry.get("note") or "")
            if isinstance(value, float):
                display = format_number(value, 2)
            else:
                display = html_text(str(value)) if value is not None else "-"
            return (
                f'<article class="kpi-card">'
                f'<span class="kpi-label">{html_text(label)}</span>'
                f'<strong class="kpi-value">{display}</strong>'
                f'<span class="kpi-unit">{unit}</span>'
                f'<p class="kpi-note">{note}</p>'
                f"</article>"
            )
        else:
            blocker = html_text(entry.get("blocker") or "데이터 미수집")
            return (
                f'<article class="kpi-card" style="opacity:0.45;">'
                f'<span class="kpi-label">{html_text(label)}</span>'
                f'<strong class="kpi-value" style="font-size:1rem;color:var(--muted,#60707a);">—</strong>'
                f'<span class="kpi-unit"></span>'
                f'<p class="kpi-note" style="font-size:0.75rem;">{blocker}</p>'
                f"</article>"
            )

    def _subsection(tag: str, title: str, desc: str, keys_labels: list[tuple[str, str]]) -> str:
        cards = "".join(_cpm_card(k, lbl) for k, lbl in keys_labels)
        return f"""
    <div style="margin-top:24px;">
      <h3 style="font-size:0.9rem;font-weight:600;color:var(--muted,#60707a);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">{html_text(tag)}</h3>
      <p style="font-size:0.85rem;color:var(--muted,#60707a);margin-bottom:12px;">{html_text(desc)}</p>
      <div class="kpi-grid">{cards}</div>
    </div>"""

    cardiac_pulmonary = _subsection(
        "Cardiac × Pulmonary",
        "심장·폐 지표",
        "심폐 효율성 — 환기 반응, 심박 반응성",
        [
            ("ve_vco2_slope", "VE/VCO₂ Slope"),
            ("chronotropic_index", "Chronotropic Index"),
            ("hr_ve_ratio", "HR/VE Ratio"),
            ("vt_hr_ve_ratio", "VT×HR/VE"),
        ],
    )

    cardiac_metabolic = _subsection(
        "Cardiac × Metabolic",
        "심장·대사 지표",
        "심박출량과 대사 효율의 통합 지표",
        [
            ("o2_pulse_ml_beat", "O₂ Pulse"),
            ("vo2_w_slope", "VO₂/W Slope"),
            ("mce", "MCE"),
            ("fatmax_hr_at_ratio", "FatMax/VT1-HR"),
            ("weber_class", "Weber Class"),
            ("rci", "Recovery Cardiac Index"),
        ],
    )

    pulmonary_metabolic = _subsection(
        "Pulmonary × Metabolic",
        "폐·대사 지표",
        "환기 효율과 기질 산화 연관 지표",
        [
            ("oues", "OUES"),
            ("ve_vo2_nadir", "VE/VO₂ Nadir"),
            ("foi", "Fat Oxidation Index"),
            ("vmsi", "VMSI"),
            ("abr", "Aerobic Base Ratio"),
            ("bcr", "Buffer Capacity Ratio"),
            ("breathing_pattern_eff", "Breathing Pattern Eff"),
            ("vd_vt_mean", "VD/VT Mean"),
        ],
    )

    three_domain = _subsection(
        "3-Domain Composite",
        "3-도메인 복합 지표",
        "심장·폐·대사를 통합한 복합 효율 지표",
        [
            ("aer", "Aerobic Efficiency Ratio"),
            ("sci", "Substrate-Cardiac Index"),
            ("tau_hr_slope", "τ × HR Slope"),
            ("epoc_vo2peak", "EPOC/VO₂peak"),
            ("hrr1_ve_vco2_product", "HRR1 × VE/VCO₂"),
        ],
    )

    blocker_keys = [
        ("rpp", "RPP"),
        ("ventilatory_power", "Ventilatory Power"),
        ("rpp_ve_ratio", "RPP/VE Ratio"),
        ("sv_vd_vt", "SV·VD/VT"),
        ("sv_ge", "SV GE"),
        ("cardiac_metabolic_output", "Cardiac Metabolic Output"),
        ("vd_vt_at_vt2", "VD/VT @ VT2"),
        ("vd_vt_ee", "VD/VT × EE"),
        ("delta_la_delta_hr", "ΔLa/ΔHR"),
        ("lactate_hr_slope", "Lactate-HR Slope"),
        ("breathing_reserve", "Breathing Reserve"),
        ("fzi_cardiopulmonary", "FZI Cardiopulmonary"),
        ("mri_composite", "MRI Composite"),
        ("iee", "IEE"),
        ("lpi", "LPI"),
        ("longevity_pi", "Longevity PI"),
    ]
    blocker_section = _subsection(
        "Blocker Indices",
        "블로커 지수 (데이터 미수집)",
        "혈압·스트로크볼륨·Phase3/4·독점 알고리즘 등 현재 프로토콜에서 수집되지 않는 지표",
        blocker_keys,
    )

    return f"""
    <section class="section" id="cpm-indices">
      <div class="section-header">
        <div>
          <span class="section-tag">CPM Composite Indices</span>
          <h2>CPM 복합 지표</h2>
          <p>심장(Cardiac) · 폐(Pulmonary) · 대사(Metabolic) 도메인을 교차한 복합 생리지표입니다. 지원되지 않는 지표는 회색으로 표시됩니다.</p>
        </div>
      </div>
      {cardiac_pulmonary}
      {cardiac_metabolic}
      {pulmonary_metabolic}
      {three_domain}
      {blocker_section}
    </section>"""


def build_report_context(db_path: Path) -> dict[str, Any]:
    """Load all report data from SQLite and normalize it for rendering."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    subject = fetch_rows(conn, "SELECT * FROM subject LIMIT 1")[0]
    session = fetch_rows(conn, "SELECT * FROM test_session LIMIT 1")[0]
    protocol_stages = fetch_rows(conn, "SELECT * FROM protocol_stages ORDER BY id")
    workout_rows = fetch_rows(conn, "SELECT * FROM workout_data ORDER BY elapsed_s")
    blood_samples = fetch_rows(conn, "SELECT * FROM blood_samples ORDER BY id")
    bxb_rows = fetch_rows(conn, "SELECT * FROM breath_by_breath ORDER BY t_s")

    raw_results = fetch_rows(conn, "SELECT category, key, value FROM analysis_results ORDER BY category, key")
    conn.close()

    analysis: dict[str, dict[str, Any]] = defaultdict(dict)
    for row in raw_results:
        analysis[row["category"]][row["key"]] = decode_value(row["value"])

    workout_sampled = sample_workout_rows(workout_rows, step_s=10)
    bxb_summary = summarize_bxb_stages(bxb_rows)
    protocol_summary = build_protocol_summary(protocol_stages)

    has_blood = bool(blood_samples)
    protocol_name = str(session.get("protocol_name") or "")
    protocol_meta = analysis.get("protocol", {})
    protocol_family = str(protocol_meta.get("protocol_family") or "")
    is_two_block_cpet = protocol_family == "two_block_cpet" or ((not has_blood) and ("Two-Block" in protocol_name))

    context = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "report_title": (
                "Two-Block CPET Analysis Report"
                if is_two_block_cpet
                else "Belgium Lactate Test Analysis Report"
            ),
            "chart_count": 10,
        },
        "subject": subject,
        "session": session,
        "protocol_summary": protocol_summary,
        "protocol_stages": protocol_stages,
        "blood_samples": blood_samples,
        "bxb_summary": bxb_summary,
        "workout_sampled": workout_sampled,
        "analysis": analysis,
        "report_profile": {
            "has_blood": has_blood,
            "is_two_block_cpet": is_two_block_cpet,
            "protocol_name": protocol_name,
            "protocol_family": protocol_family or ("belgium_lactate_cpet" if has_blood else "cpet"),
        },
    }
    context["fuel_flex"] = build_metabolic_flexibility_payload(context)
    context["insights"] = build_insights(context)
    context["coach_summary"] = build_coach_summary(context)
    context["report_registry"] = build_report_registry(context)
    context["kpis"] = context["report_registry"]["kpis"]
    context["chart_data"] = build_chart_data(context, bxb_rows)
    return context


def build_chart_data(context: dict[str, Any], bxb_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Prepare serializable chart datasets for the HTML frontend."""
    analysis = context["analysis"]
    blood = context["blood_samples"]
    lactate_points = analysis["lactate"].get("lactate_points", [])
    adjusted_lactate_points = analysis["lactate"].get("lactate_curve_points_adjusted", [])
    vo2_timeseries = smooth_chart_series(
        analysis["vo2max"].get("bxb_series", {}),
        {
            "vo2": {"radius": 2, "rel_threshold": 0.28, "abs_threshold": 700.0, "smooth_window": 5},
            "vco2": {"radius": 2, "rel_threshold": 0.28, "abs_threshold": 700.0, "smooth_window": 5},
            "ve": {"radius": 2, "rel_threshold": 0.3, "abs_threshold": 28.0, "smooth_window": 5},
            "rq": {"radius": 2, "rel_threshold": 0.14, "abs_threshold": 0.12, "smooth_window": 5},
        },
    )
    rer_progression = {
        "t_s": vo2_timeseries.get("t_s", []),
        "rq": vo2_timeseries.get("rq", []),
        "vo2_plateau": analysis["vo2max"].get("vo2_plateau"),
        "vo2max_time_s": analysis["substrate"].get("fatmax_time_s"),
    }
    substrate_series = smooth_chart_series(
        analysis["substrate"].get("substrate_series", {}),
        {
            "fat_gmin": {"radius": 2, "rel_threshold": 0.45, "abs_threshold": 0.28, "smooth_window": 7},
            "cho_gmin": {"radius": 2, "rel_threshold": 0.22, "abs_threshold": 0.8, "smooth_window": 7},
        },
    )
    metabolism_chart = build_metabolism_chart_payload(
        analysis,
        bxb_rows,
        context["subject"],
        bool(context["blood_samples"]),
    )
    vt_series = smooth_chart_series(
        analysis["ventilatory_thresholds"].get("vt_series", {}),
        {
            "ve_vo2": {"radius": 2, "rel_threshold": 0.2, "abs_threshold": 6.0, "smooth_window": 7},
            "ve_vco2": {"radius": 2, "rel_threshold": 0.18, "abs_threshold": 4.5, "smooth_window": 7},
        },
    )

    block1_points = [
        point
        for point in lactate_points
        if point.get("block") in {"rest", "block_1"}
    ]
    block3_points = [
        point
        for point in lactate_points
        if point.get("block") == "block_3"
    ]
    block3_blood = [
        row
        for row in blood
        if row.get("block") == "block_3"
        and row.get("load_w") is not None
        and row.get("hr_bpm") is not None
        and row.get("lactate_mmol") is not None
    ]

    return {
        "lactate_curve": {
            "measured_lt_points": block1_points,
            "adjusted_points": adjusted_lactate_points,
            "adjusted_curve": adjusted_lactate_points,
            "fixed_threshold": analysis["lactate"].get("fixed_threshold_value"),
            "lt1_fixed": analysis["lactate"].get("lt1_fixed_power_w"),
            "lt1_dmax": analysis["lactate"].get("lt1_dmax_power_w"),
        },
        "block1_overlay": {
            "labels": [f"{format_number(p.get('power_w'))}W" for p in block1_points],
            "hr": [p.get("hr") for p in block1_points],
            "lactate": [p.get("lactate") for p in block1_points],
        },
        "glucose_response": {
            "labels": [f"{format_number(p.get('power_w'))}W" for p in block1_points + block3_points],
            "glucose": [p.get("glucose") for p in block1_points + block3_points],
            "blocks": [p.get("block") for p in block1_points + block3_points],
        },
        "vo2_timeseries": vo2_timeseries,
        "rer_progression": rer_progression,
        "substrate": substrate_series,
        "metabolism": metabolism_chart,
        "ventilatory_thresholds": {
            **vt_series,
            "vt1_time_s": analysis["ventilatory_thresholds"].get("vt1_time_s"),
            "vt2_time_s": analysis["ventilatory_thresholds"].get("vt2_time_s"),
            "vt1_power_w": analysis["ventilatory_thresholds"].get("vt1_power_w"),
            "vt2_power_w": analysis["ventilatory_thresholds"].get("vt2_power_w"),
        },
        "clearance": {
            "points": analysis["clearance"].get("clearance_points", []),
            "post_vo2max_lactate": analysis["clearance"].get("post_vo2max_lactate"),
            "rates": analysis["clearance"].get("clearance_rates", []),
        },
        "ftp_overlay": {
            "labels": [row.get("ftp_pct") or row.get("step") for row in block3_blood],
            "hr": [row.get("hr_bpm") for row in block3_blood],
            "lactate": [row.get("lactate_mmol") for row in block3_blood],
            "power": [row.get("load_w") for row in block3_blood],
        },
        "workout_timeline": analysis["hr"].get("hr_timeline", {}),
        "zones": analysis["training_zones"].get("zones", []),
    }


def render_table(headers: list[str], rows: list[list[Any]]) -> str:
    """Render a generic striped HTML table."""
    thead = "".join(f"<th>{html_text(cell)}</th>" for cell in headers)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{html_text(cell)}</td>" for cell in row)
        body_rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def render_kpi_cards(kpis: list[dict[str, Any]]) -> str:
    """Render dashboard KPI cards."""
    cards = []
    for kpi in kpis:
        cards.append(
            f"""
            <article class="kpi-card">
              <span class="kpi-label">{html_text(kpi['label'])}</span>
              <strong class="kpi-value">{html_text(kpi['value'])}</strong>
              <span class="kpi-unit">{html_text(kpi['unit'])}</span>
              <p class="kpi-note">{html_text(kpi['note'])}</p>
            </article>
            """
        )
    return "".join(cards)


def render_protocol_summary(rows: list[dict[str, Any]]) -> str:
    """Render protocol summary blocks."""
    items = []
    for row in rows:
        items.append(
            f"""
            <div class="protocol-pill">
              <span class="protocol-block">{html_text(row['block'])}</span>
              <span>{html_text(row['steps'])} stages</span>
              <span>{html_text(format_number(row['duration_min'], 1))} min</span>
              <span>{html_text(row['targets'])}</span>
            </div>
            """
        )
    return "".join(items)


def _json_safe(value: Any) -> Any:
    """Recursively replace NaN and infinities so embedded JSON stays valid."""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        if hasattr(value, "item"):
            scalar = value.item()
            if scalar is not value:
                return _json_safe(scalar)
    except Exception:
        pass
    return value


def render_html(context: dict[str, Any]) -> str:
    """Render the full standalone HTML document."""
    subject = context["subject"]
    session = context["session"]
    analysis = context["analysis"]
    coach_summary = context["coach_summary"]
    metabolism = context["chart_data"].get("metabolism", {})
    report_registry = context.get("report_registry") or {}
    report_profile = context.get("report_profile") or {}
    has_blood = bool(report_profile.get("has_blood"))
    is_two_block_cpet = bool(report_profile.get("is_two_block_cpet"))
    safe_chart_data = _json_safe(context["chart_data"])
    safe_context = _json_safe(context)
    chart_json = json.dumps(safe_chart_data, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    data_json = json.dumps(safe_context, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    report_title = context["meta"].get("report_title") or "CPET Analysis Report"
    hero_eyebrow = report_registry.get("hero_eyebrow") or ("FatMax Ramp · VO2max Ramp · CPET" if is_two_block_cpet else "Belgium Protocol · Lactate · CPET")
    hero_heading = report_registry.get("hero_heading") or ("Two-Block CPET Analysis" if is_two_block_cpet else "Belgium Lactate Test Analysis")
    hero_description = report_registry.get("hero_description") or (
        "첫 번째 블럭은 FatMax와 연료 효율 구간을 확인하기 위한 완만한 램프, 두 번째 블럭은 VO2max 확인을 위한 10초 램프입니다. "
        "호흡별 대사 데이터와 FIT 파워를 통합해 기질 산화, RQ 1.0 이전 연료 기여율, 환기 반응을 한 문서로 정리했습니다."
        if is_two_block_cpet
        else "호흡별 대사 데이터, 혈중 lactate/glucose 샘플, 워크아웃 전 구간 FIT 기록을 하나의 정적 문서로 통합한 스포츠과학 리포트입니다. 젖산 역치, 환기 역치, 기질 산화, lactate clearance, 심박 반응, 트레이닝 존을 한 화면에서 검토할 수 있게 구성했습니다."
    )

    fuel_flex = context.get("fuel_flex") or {}
    es = analysis.get("energy_system", {})
    fuel_contribution_section = ""
    energy_system_section = ""
    if fuel_flex:
        fuel_available = bool(fuel_flex.get("available"))
        crossing_display = (
            format_number(fuel_flex.get("crossing_power_w"))
            if fuel_available
            else (fuel_flex.get("crossing_label") or "-")
        )
        crossing_unit = "W" if fuel_available else ""
        crossing_note = (
            f"HR {html_text(format_number(fuel_flex.get('crossing_hr_bpm')))} bpm · 총 {html_text(format_number(fuel_flex.get('total_kcal'), 1))} kcal"
            if fuel_available
            else html_text(fuel_flex.get("note"))
        )
        fuel_chart_block = (
            '<div class="chart-shell chart-shell--compact"><canvas id="chart-fuel-split"></canvas><div class="chart-fallback" data-fallback="chart-fuel-split"></div></div>'
            if fuel_available
            else f'<div class="note-card" style="min-height:220px;display:flex;align-items:center;"><p>{html_text(fuel_flex.get("note"))}</p></div>'
        )
        fuel_contribution_section = f"""
    <section class="section" id="fuel-flex">
      <div class="section-header">
        <div>
          <span class="section-tag">Fuel Contribution</span>
          <h2>RQ 1.0 기준 연료 기여율</h2>
          <p>RQ 1.0 도달 전까지 지방과 탄수화물이 실제로 얼마나 기여했는지를 별도 섹션으로 정리합니다. lactate 기반 3-pathway energy 해석과는 독립적으로 함께 읽습니다.</p>
        </div>
      </div>
      <div class="kpi-grid">
        <article class="kpi-card">
          <span class="kpi-label">Fat Contribution</span>
          <strong class="kpi-value">{html_text(format_number(fuel_flex.get('fat_contribution_pct'), 1) if fuel_available else '-')}</strong>
          <span class="kpi-unit">%</span>
          <p class="kpi-note">RQ 1.0 이전 지방 기여율</p>
        </article>
        <article class="kpi-card">
          <span class="kpi-label">CHO Contribution</span>
          <strong class="kpi-value">{html_text(format_number(fuel_flex.get('cho_contribution_pct'), 1) if fuel_available else '-')}</strong>
          <span class="kpi-unit">%</span>
          <p class="kpi-note">RQ 1.0 이전 탄수화물 기여율</p>
        </article>
        <article class="kpi-card">
          <span class="kpi-label">RQ 1.0 Crossing</span>
          <strong class="kpi-value">{html_text(crossing_display)}</strong>
          <span class="kpi-unit">{crossing_unit}</span>
          <p class="kpi-note">{crossing_note}</p>
        </article>
        <article class="kpi-card">
          <span class="kpi-label">Metabolic Flexibility Index</span>
          <strong class="kpi-value">{html_text(format_number(fuel_flex.get('score'), 1) if fuel_available else '-')}</strong>
          <span class="kpi-unit">{'/100' if fuel_available else ''}</span>
          <p class="kpi-note">{html_text(fuel_flex.get('note'))}</p>
        </article>
      </div>
      <div class="chart-grid" style="margin-top:18px;">
        <article class="chart-card chart-card--full">
          <h3>Fuel Split Before RQ 1.0</h3>
          <p>RQ 1.0 도달 전까지 누적된 총 kcal에서 지방과 탄수화물 기여 비율을 바로 읽을 수 있도록 도넛 차트로 표시합니다.</p>
          {fuel_chart_block}
        </article>
      </div>
      <div class="note-card" style="margin-top:18px;">
        <strong>Custom definition</strong>
        <p>{html_text(fuel_flex.get('formula_note'))}</p>
      </div>
    </section>"""
    if es.get("status") == "computed" and es.get("total_kj"):
        colors = {"oxidative": "#3B82F6", "glycolytic": "#EF4444", "phosphagen": "#10B981"}
        labels = {"oxidative": "Oxidative (산화적)", "glycolytic": "Glycolytic (해당과정)", "phosphagen": "Phosphagen (인원질)"}
        pathways = []
        for key in ("oxidative", "glycolytic", "phosphagen"):
            kj, pct = es.get(f"{key}_kj"), es.get(f"{key}_pct")
            if kj is not None and pct is not None:
                pathways.append({"key": key, "label": labels[key], "kj": kj, "pct": pct, "color": colors[key]})
        if pathways:
            bar_segs = "".join(f'<div style="width:{p["pct"]:.1f}%;background:{p["color"]};height:100%;display:inline-block;" title="{html_text(p["label"])}: {p["pct"]:.1f}%"></div>' for p in pathways)
            rows_html = "".join(f'<tr><td><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{p["color"]};margin-right:8px;vertical-align:middle;"></span>{html_text(p["label"])}</td><td style="text-align:right;font-weight:600;">{p["kj"]:.1f} kJ</td><td style="text-align:right;font-weight:600;">{p["pct"]:.1f}%</td></tr>' for p in pathways)
            delta_la_html = f'<span style="color:var(--muted);font-size:0.85rem;margin-left:16px;">ΔLa: {es["delta_lactate"]:.2f} mmol/L</span>' if es.get("has_lactate") and es.get("delta_lactate") is not None else ""
            fit = es.get("mono_exp_fit")
            fit_html = ""
            if fit:
                r_sq = fit.get("r_squared", 0)
                r_label = f'{r_sq:.3f}' + (' ⚠️' if r_sq < 0.8 else ' ✓')
                fit_html = f'<div style="margin-top:16px;padding:16px;background:var(--paper-strong,#f9fafb);border-radius:12px;"><strong style="font-size:0.85rem;color:var(--muted,#6b7280);">Mono-exponential Fit (EPOC Fast Component)</strong><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:8px;"><div><span style="color:var(--muted,#6b7280);font-size:0.8rem;">Amplitude</span><br><strong>{fit.get("amplitude_l_min",0):.3f} L/min</strong></div><div><span style="color:var(--muted,#6b7280);font-size:0.8rem;">Tau (τ)</span><br><strong>{fit.get("tau_sec",0):.1f} sec</strong></div><div><span style="color:var(--muted,#6b7280);font-size:0.8rem;">Baseline</span><br><strong>{fit.get("baseline_l_min",0):.3f} L/min</strong></div><div><span style="color:var(--muted,#6b7280);font-size:0.8rem;">R²</span><br><strong>{r_label}</strong></div></div></div>'
            warnings_html = ""
            ws = es.get("warnings", [])
            if ws:
                w_items = "".join(f"<li>{html_text(w)}</li>" for w in ws)
                warnings_html = f'<div style="margin-top:12px;padding:12px;background:#fef3c7;border-radius:8px;font-size:0.85rem;"><strong>⚠ Notes:</strong><ul style="margin:4px 0 0 16px;padding:0;">{w_items}</ul></div>'
            energy_system_section = f"""
    <section class="section" id="energy-system">
      <div class="section-header"><div><span class="section-tag">Energy System</span><h2>에너지 시스템 기여도 (3-Pathway)</h2><p>산화적(Oxidative), 해당과정(Glycolytic), 인원질(Phosphagen) 에너지 시스템의 기여 비율을 정량 분석합니다.</p></div></div>
      <div style="background:white;border-radius:var(--radius,12px);padding:24px;box-shadow:var(--shadow,0 1px 3px rgba(0,0,0,0.1));">
        <div style="height:32px;border-radius:8px;overflow:hidden;background:#e5e7eb;display:flex;">{bar_segs}</div>
        <table style="width:100%;margin-top:16px;border-collapse:collapse;"><thead><tr style="border-bottom:2px solid var(--line,#e5e7eb);"><th style="text-align:left;padding:8px 0;">Pathway</th><th style="text-align:right;padding:8px 0;">Energy</th><th style="text-align:right;padding:8px 0;">Contribution</th></tr></thead><tbody>{rows_html}<tr style="border-top:2px solid var(--line,#e5e7eb);font-weight:700;"><td style="padding:8px 0;">Total{delta_la_html}</td><td style="text-align:right;padding:8px 0;">{es["total_kj"]:.1f} kJ</td><td style="text-align:right;padding:8px 0;">100%</td></tr></tbody></table>
        {fit_html}{warnings_html}
      </div>
    </section>"""

    cpm_panel_section = build_cpm_panel(analysis.get("cpm_indices", {}))

    blood_table = render_table(
        ["Block", "Step", "Load", "%FTP", "Duration", "HR", "Lactate", "Glucose", "Notes"],
        [
            [
                row.get("block"),
                row.get("step"),
                f"{format_number(row.get('load_w'))}W" if row.get("load_w") is not None else "-",
                row.get("ftp_pct") or "-",
                f"{format_number(row.get('duration_min'), 1)} min" if row.get("duration_min") is not None else "-",
                f"{format_number(row.get('hr_bpm'))} bpm" if row.get("hr_bpm") is not None else "-",
                format_number(row.get("lactate_mmol"), 2) if row.get("lactate_mmol") is not None else "-",
                format_number(row.get("glucose_mmol"), 2) if row.get("glucose_mmol") is not None else "-",
                row.get("notes") or "-",
            ]
            for row in context["blood_samples"]
        ],
    )

    bxb_table = render_table(
        ["Power", "N", "VO2", "HR", "RQ", "Fat", "CHO"],
        [
            [
                f"{row['power_w']}W",
                row["n"],
                f"{format_number(row['vo2_ml'], 1)} mL/min",
                f"{format_number(row['hr_bpm'], 1)} bpm",
                format_number(row["rq"], 2),
                f"{format_number(row['fat_gmin'], 2)} g/min",
                f"{format_number(row['cho_gmin'], 2)} g/min",
            ]
            for row in context["bxb_summary"]
        ],
    )

    stage_table = render_table(
        ["Block", "Step", "Target", "Duration", "Type"],
        [
            [
                row.get("block"),
                row.get("step"),
                f"{format_number(stage_target_w(row, subject.get('ftp_w')))}W",
                f"{format_number((row.get('duration_s') or 0) / 60.0, 1)} min",
                row.get("stage_type"),
            ]
            for row in context["protocol_stages"]
        ],
    )

    zone_rows = "".join(
        f"""
        <tr>
          <td>{html_text(zone['zone'])}</td>
          <td>{html_text(zone['name'])}</td>
          <td>{html_text(zone['power_range'])}</td>
          <td>{html_text(zone['hr_range'])}</td>
          <td>{html_text(zone['description'])}</td>
        </tr>
        """
        for zone in context["chart_data"]["zones"]
    )

    insight_items = "".join(f"<li>{html_text(line)}</li>" for line in context["insights"])
    coach_items = "".join(f"<li>{html_text(line)}</li>" for line in coach_summary["bullets"])
    metabolism_fatmax = metabolism.get("fatmax", {})
    metabolism_ftp = metabolism.get("ftp_anchor", {})
    metabolism_session = metabolism.get("session_anchor", {})
    metabolism_crossover = metabolism.get("primary_crossover") or {}
    metabolism_ftp_line = (
        f"<span>1h @ FTP {html_text(format_number(metabolism_ftp.get('power_w'), 1))}W ≈ {html_text(format_number(metabolism_ftp.get('kcal_h'), 0))} kcal/h</span>"
        if metabolism_ftp.get("power_w") is not None and metabolism_ftp.get("kcal_h") is not None
        else "<span>Measured FTP unavailable for this protocol</span>"
    )
    rq1_fuel_split = analysis["substrate"].get("rq1_fuel_split") or {}
    crossover_label = (
        f"Crossover {format_number(metabolism_crossover.get('power_w'), 1)}W"
        if metabolism_crossover
        else "Stable crossover not observed"
    )
    rq1_summary = ""
    if rq1_fuel_split.get("status") == "computed":
        rq1_summary = (
            f"<span>RQ 1.0 전 총 {html_text(format_number(rq1_fuel_split.get('total_kcal'), 1))} kcal · "
            f"Fat {html_text(format_number(rq1_fuel_split.get('fat_pct'), 1))}% / "
            f"CHO {html_text(format_number(rq1_fuel_split.get('cho_pct'), 1))}%</span>"
        )
    fatmax_copy = _fatmax_summary_copy(context)
    metabolism_intro = report_registry.get("metabolism_intro") or "Power 축에서 Fat, CHO, energy를 함께 보고 FatMax band와 FTP 기준 hourly cost를 코칭 관점으로 해석합니다."
    metabolism_summary = f"""
      <div class="metabolism-summary">
        <strong>{html_text(fatmax_copy['headline'])}</strong>
        <span>{html_text(fatmax_copy['note'])}</span>
        <span>{html_text(format_number(metabolism_session.get('duration_label')))} ride anchor · TSS {html_text(format_number(metabolism_session.get('tss')))}</span>
        {metabolism_ftp_line}
        {rq1_summary}
        <span>{html_text(crossover_label)}</span>
      </div>
      <p class="metabolism-note">{html_text(metabolism.get('energy_note'))}</p>
    """

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_text(report_title)}</title>
  <style>
    :root {{
      --paper: #f4efe6;
      --paper-strong: #efe6d8;
      --ink: #162028;
      --muted: #5f6d74;
      --line: rgba(22, 32, 40, 0.12);
      --accent: #8f3b2f;
      --accent-soft: rgba(143, 59, 47, 0.12);
      --teal: #184e59;
      --gold: #a17b37;
      --shadow: 0 24px 60px rgba(17, 25, 32, 0.12);
      --radius: 22px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top left, rgba(143, 59, 47, 0.08), transparent 32%),
        radial-gradient(circle at top right, rgba(24, 78, 89, 0.10), transparent 28%),
        linear-gradient(180deg, #f7f2ea 0%, #f2ece2 100%);
      color: var(--ink);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      line-height: 1.55;
      word-break: keep-all;
      overflow-wrap: break-word;
    }}
    .page {{
      max-width: 1320px;
      margin: 0 auto;
      padding: 40px 24px 80px;
    }}
    .coach-brief {{
      position: relative;
      overflow: hidden;
      margin-bottom: 24px;
      padding: 30px 32px;
      border-radius: 34px;
      background: linear-gradient(135deg, rgba(22, 32, 40, 0.96), rgba(24, 78, 89, 0.94));
      color: #f7f1e7;
      box-shadow: var(--shadow);
    }}
    .coach-brief::after {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        radial-gradient(circle at top right, rgba(255, 255, 255, 0.14), transparent 32%),
        linear-gradient(135deg, rgba(161, 123, 55, 0.2), transparent 42%);
      pointer-events: none;
    }}
    .hero {{
      position: relative;
      overflow: hidden;
      background: rgba(255, 255, 255, 0.58);
      backdrop-filter: blur(18px);
      border: 1px solid rgba(255, 255, 255, 0.5);
      border-radius: 34px;
      padding: 36px;
      box-shadow: var(--shadow);
    }}
    .hero::after {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(135deg, rgba(24, 78, 89, 0.08), transparent 40%),
        linear-gradient(315deg, rgba(161, 123, 55, 0.07), transparent 35%);
      pointer-events: none;
    }}
    .eyebrow {{
      display: inline-flex;
      gap: 10px;
      align-items: center;
      padding: 8px 14px;
      border-radius: 999px;
      background: rgba(22, 32, 40, 0.06);
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }}
    .coach-grid {{
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(260px, 0.65fr);
      gap: 24px;
      align-items: start;
    }}
    .coach-brief h2 {{
      font-size: clamp(2rem, 3.2vw, 3rem);
      line-height: 1;
      margin-top: 12px;
    }}
    .coach-brief p {{
      margin: 14px 0 0;
      color: rgba(247, 241, 231, 0.82);
      max-width: 64ch;
    }}
    .coach-list {{
      margin: 20px 0 0;
      padding-left: 20px;
    }}
    .coach-list li + li {{
      margin-top: 8px;
    }}
    .coach-note {{
      padding: 18px;
      border-radius: 22px;
      background: rgba(255, 255, 255, 0.1);
      border: 1px solid rgba(255, 255, 255, 0.14);
      color: rgba(247, 241, 231, 0.94);
    }}
    .coach-note strong {{
      display: block;
      margin-bottom: 8px;
      color: #f2d7a6;
      font-size: 0.82rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    h1, h2, h3 {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    h1 {{
      margin-top: 18px;
      font-size: clamp(2.2rem, 3.5vw, 3.4rem);
      line-height: 1.05;
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.8fr) minmax(320px, 1fr);
      gap: 28px;
      margin-top: 24px;
      position: relative;
      z-index: 1;
    }}
    .hero-copy p {{
      max-width: 64ch;
      color: var(--muted);
      margin: 18px 0 0;
      font-size: 1.05rem;
    }}
    .info-card {{
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 0;
      padding: 28px 26px;
      border-radius: 24px;
      background: rgba(22, 32, 40, 0.92);
      color: #f5efe7;
    }}
    .info-card h2 {{
      margin-bottom: 18px;
    }}
    .info-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px 20px;
      font-size: 1rem;
    }}
    .info-grid span {{
      display: block;
      color: rgba(245, 239, 231, 0.68);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 4px;
    }}
    .protocol-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 20px;
    }}
    .protocol-pill {{
      display: grid;
      gap: 4px;
      min-width: 162px;
      padding: 16px 18px;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.62);
      border: 1px solid rgba(22, 32, 40, 0.08);
    }}
    .protocol-block {{
      color: var(--teal);
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .section {{
      margin-top: 28px;
      padding: 28px;
      border-radius: 28px;
      background: rgba(255, 255, 255, 0.72);
      border: 1px solid rgba(255, 255, 255, 0.42);
      box-shadow: var(--shadow);
      break-inside: avoid;
    }}
    .section-header {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: end;
      margin-bottom: 22px;
    }}
    .section-header p {{
      margin: 8px 0 0;
      color: var(--muted);
      max-width: 68ch;
    }}
    .section-tag {{
      color: var(--accent);
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 0.75rem;
    }}
    .insight-box {{
      margin-top: 22px;
      padding: 18px 20px;
      border-radius: 20px;
      background: linear-gradient(135deg, rgba(24, 78, 89, 0.08), rgba(143, 59, 47, 0.08));
      border: 1px solid rgba(22, 32, 40, 0.08);
    }}
    .insight-box ul {{
      margin: 0;
      padding-left: 20px;
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 16px;
    }}
    .kpi-card {{
      min-height: 170px;
      padding: 18px;
      border-radius: 22px;
      background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(240, 233, 222, 0.86));
      border: 1px solid rgba(22, 32, 40, 0.08);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .kpi-label {{
      color: var(--muted);
      font-size: 0.84rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .kpi-value {{
      font-size: 2.2rem;
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
      line-height: 1;
      margin-top: 10px;
    }}
    .kpi-unit {{
      color: var(--accent);
      font-weight: 700;
      margin-top: 6px;
    }}
    .kpi-note {{
      margin: 18px 0 0;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .chart-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }}
    .chart-card {{
      padding: 18px 18px 14px;
      border-radius: 22px;
      background: rgba(255, 255, 255, 0.86);
      border: 1px solid var(--line);
      break-inside: avoid;
    }}
    .chart-card--full {{
      grid-column: 1 / -1;
    }}
    .chart-card h3 {{
      font-size: 1.25rem;
      margin-bottom: 4px;
    }}
    .chart-card p {{
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 0.94rem;
    }}
    .metabolism-summary {{
      display: grid;
      gap: 4px;
      margin: 14px 0 8px;
      text-align: center;
    }}
    .metabolism-summary strong {{
      font-size: 1.9rem;
      line-height: 1.1;
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
    }}
    .metabolism-summary span {{
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .metabolism-note {{
      margin-top: 6px;
      text-align: center;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .chart-shell {{
      position: relative;
      min-height: var(--chart-height, 320px);
      height: var(--chart-height, 320px);
    }}
    .chart-shell--tall {{
      --chart-height: 380px;
    }}
    .chart-shell--compact {{
      --chart-height: 280px;
    }}
    canvas {{
      width: 100% !important;
      height: 100% !important;
    }}
    .analysis-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) minmax(280px, 0.7fr);
      gap: 18px;
    }}
    .metric-stack {{
      display: grid;
      gap: 12px;
    }}
    .metric-card {{
      padding: 18px;
      border-radius: 20px;
      background: rgba(24, 78, 89, 0.08);
      border: 1px solid rgba(24, 78, 89, 0.12);
    }}
    .metric-card strong {{
      display: block;
      font-size: 1.4rem;
      margin-top: 6px;
      font-family: "Iowan Old Style", "Palatino Linotype", serif;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.82);
      font-size: 0.94rem;
    }}
    th, td {{
      padding: 11px 12px;
      border-bottom: 1px solid rgba(22, 32, 40, 0.08);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      position: sticky;
      top: 0;
      background: var(--paper-strong);
      color: var(--ink);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    tbody tr:nth-child(even) {{
      background: rgba(22, 32, 40, 0.03);
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    .zone-table {{
      margin-top: 18px;
    }}
    .footer-note {{
      margin-top: 28px;
      color: var(--muted);
      font-size: 0.92rem;
      text-align: right;
    }}
    .chart-fallback {{
      display: none;
      padding: 16px;
      border-radius: 16px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 0.92rem;
    }}
    .chart-fallback.active {{
      display: block;
    }}
    .no-script {{
      margin-top: 18px;
      padding: 14px 16px;
      border-radius: 18px;
      background: rgba(143, 59, 47, 0.08);
      color: var(--accent);
    }}
    @media (max-width: 1040px) {{
      .page {{
        padding: 28px 18px 64px;
      }}
      .hero,
      .coach-brief,
      .section {{
        padding: 24px;
      }}
      .coach-grid,
      .hero-grid,
      .analysis-grid,
      .chart-grid {{
        grid-template-columns: 1fr;
      }}
      .kpi-grid {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
      }}
      .kpi-card {{
        min-height: 148px;
      }}
      .chart-shell {{
        --chart-height: 300px;
      }}
      .chart-shell--tall {{
        --chart-height: 340px;
      }}
      .chart-shell--compact {{
        --chart-height: 260px;
      }}
    }}
    @media (max-width: 720px) {{
      body {{
        font-size: 15px;
      }}
      .page {{
        padding: 18px 12px 40px;
      }}
      .hero,
      .coach-brief,
      .section {{
        padding: 18px;
        border-radius: 22px;
      }}
      .coach-grid,
      .hero-grid,
      .analysis-grid,
      .chart-grid,
      .info-grid {{
        grid-template-columns: 1fr;
      }}
      .kpi-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
      }}
      .section-header {{
        flex-direction: column;
        align-items: flex-start;
        margin-bottom: 16px;
      }}
      .section-header p,
      .hero-copy p,
      .coach-brief p {{
        max-width: none;
      }}
      .coach-list {{
        margin-top: 16px;
        padding-left: 18px;
      }}
      .info-card,
      .kpi-card,
      .metric-card,
      .chart-card,
      .protocol-pill,
      .coach-note {{
        padding: 16px;
        border-radius: 18px;
      }}
      .protocol-pill {{
        min-width: 0;
      }}
      .kpi-card {{
        min-height: 124px;
        padding: 14px;
      }}
      .kpi-label {{
        font-size: 0.72rem;
      }}
      .kpi-value {{
        font-size: 1.72rem;
        margin-top: 8px;
      }}
      .kpi-unit {{
        margin-top: 4px;
        font-size: 0.92rem;
      }}
      .kpi-note {{
        margin-top: 10px;
        font-size: 0.8rem;
        line-height: 1.35;
      }}
      .chart-card h3 {{
        font-size: 1.08rem;
      }}
      .chart-card p,
      .metabolism-note,
      .metabolism-summary span,
      .footer-note {{
        font-size: 0.88rem;
      }}
      .metabolism-summary strong {{
        font-size: 1.5rem;
      }}
      .chart-shell {{
        --chart-height: 260px;
      }}
      .chart-shell--tall {{
        --chart-height: 300px;
      }}
      .chart-shell--compact {{
        --chart-height: 240px;
      }}
      th, td {{
        padding: 10px 9px;
        font-size: 0.85rem;
      }}
    }}
    @media (max-width: 520px) {{
      .eyebrow,
      .section-tag,
      .kpi-label,
      .info-grid span,
      .coach-note strong,
      th {{
        letter-spacing: 0.05em;
      }}
      .chart-shell {{
        --chart-height: 232px;
      }}
      .chart-shell--tall {{
        --chart-height: 272px;
      }}
      .chart-shell--compact {{
        --chart-height: 220px;
      }}
    }}
    @media (max-width: 390px) {{
      .kpi-grid {{
        grid-template-columns: 1fr;
      }}
    }}
    @media print {{
      body {{
        background: #fff;
      }}
      .page {{
        max-width: none;
        padding: 0;
      }}
      .hero,
      .section {{
        box-shadow: none;
        border: 1px solid rgba(0, 0, 0, 0.12);
        background: #fff;
      }}
      .chart-card,
      .kpi-card,
      .metric-card,
      .protocol-pill {{
        break-inside: avoid;
      }}
      canvas {{
        height: 280px !important;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="coach-brief" id="coach-summary">
      <div class="coach-grid">
        <div>
          <span class="eyebrow">Coach Summary</span>
          <h2>{html_text(coach_summary["headline"])}</h2>
          <p>{html_text(coach_summary["subheadline"])}</p>
          <ul class="coach-list">{coach_items}</ul>
        </div>
        <aside class="coach-note">
          <strong>LT2 Confidence</strong>
          <p>{html_text(coach_summary["lt2_note"])}</p>
        </aside>
      </div>
    </section>

    <section class="hero">
      <span class="eyebrow">{html_text(hero_eyebrow)}</span>
      <div class="hero-grid">
        <div class="hero-copy">
          <h1>{html_text(hero_heading)}</h1>
          <p>{html_text(hero_description)}</p>
          <div class="protocol-row">{render_protocol_summary(context["protocol_summary"])}</div>
          <div class="insight-box">
            <strong>핵심 해석 메모</strong>
            <ul>{insight_items}</ul>
          </div>
        </div>
        <aside class="info-card">
          <h2>피험자 및 테스트 정보</h2>
          <div class="info-grid">
            <div><span>Name</span>{html_text(subject.get("name"))}</div>
            <div><span>Gender</span>{html_text(subject.get("gender"))}</div>
            <div><span>Age</span>{html_text(format_number(subject.get("age"), 1))} yr</div>
            <div><span>Body Size</span>{html_text(format_number(subject.get("height_cm")))} cm / {html_text(format_number(subject.get("weight_kg"), 1))} kg</div>
            <div><span>FTP</span>{html_text(format_number(subject.get("ftp_w")))} W</div>
            <div><span>Max HR</span>{html_text(format_number(subject.get("max_hr")))} bpm</div>
            <div><span>Test Date</span>{html_text(session.get("test_date"))}</div>
            <div><span>Time Window</span>{html_text(format_datetime_text(session.get("start_time_kst")))} → {html_text(format_datetime_text(session.get("end_time_kst")))}</div>
            <div><span>Environment</span>{html_text(format_number(session.get("ambient_temp_c"), 1))}°C / {html_text(format_number(session.get("humidity_pct"), 1))}%</div>
            <div><span>Pressure</span>{html_text(format_number(session.get("baro_pressure_mmhg"), 1))} mmHg</div>
          </div>
        </aside>
      </div>
    </section>

    <section class="section" id="dashboard">
      <div class="section-header">
        <div>
          <span class="section-tag">Overview</span>
          <h2>주요 지표 대시보드</h2>
          <p>Phase 4 계산 결과를 기준으로 가장 먼저 확인해야 할 핵심 수치들을 카드 형태로 정리했습니다.</p>
        </div>
      </div>
      <div class="kpi-grid">{render_kpi_cards(context["kpis"])}</div>
    </section>

    <section class="section" id="block1"{' style="display:none;"' if not has_blood else ''}>
      <div class="section-header">
        <div>
          <span class="section-tag">Block 1</span>
          <h2>젖산 역치 분석</h2>
          <p>Power-lactate 커브와 심박 반응을 함께 보면서 LT1 추정과 glucose 반응을 검토합니다.</p>
        </div>
      </div>
      <div class="chart-grid">
        <article class="chart-card">
          <h3>Power vs Lactate Curve</h3>
          <p>LT1 추정에 사용한 측정점만 표시하고, Block 3는 baseline-adjusted 기준점으로 별도 표기합니다.</p>
          <div class="chart-shell chart-shell--compact"><canvas id="chart-lactate"></canvas><div class="chart-fallback" data-fallback="chart-lactate"></div></div>
        </article>
        <article class="chart-card">
          <h3>Power vs HR + Lactate Overlay</h3>
          <p>Block 1의 steady-state 심박 상승과 lactate 반응을 이중축으로 표시합니다.</p>
          <div class="chart-shell chart-shell--compact"><canvas id="chart-overlay"></canvas><div class="chart-fallback" data-fallback="chart-overlay"></div></div>
        </article>
        <article class="chart-card">
          <h3>Glucose Response</h3>
          <p>혈당 변화를 부하 증가와 lactate clearance 구간까지 이어서 보여줍니다.</p>
          <div class="chart-shell chart-shell--compact"><canvas id="chart-glucose"></canvas><div class="chart-fallback" data-fallback="chart-glucose"></div></div>
        </article>
      </div>
    </section>

    <section class="section" id="block2">
      <div class="section-header">
        <div>
          <span class="section-tag">Block 2</span>
          <h2>{html_text('두 블럭 CPET 핵심 분석' if is_two_block_cpet else 'VO2max 및 환기 역치 분석')}</h2>
          <p>{html_text(report_registry.get('block2_description') or ('Block 1의 FatMax 완만 램프와 Block 2의 10초 VO2max 램프를 한 번에 묶어, 기질 산화·RER·환기 역치와 연료 전환 지점을 같이 검토합니다.' if is_two_block_cpet else '호흡별 산소 섭취, 환기, RER, 기질 산화, VE/VO2 · VE/VCO2 변화를 통해 최대 유산소 반응과 ventilatory thresholds를 검토합니다.'))}</p>
        </div>
      </div>
      <div class="chart-grid">
        <article class="chart-card">
          <h3>VO2 / VCO2 / VE Time Series</h3>
          <p>말하기 등으로 생긴 isolated spike를 억제하고 전체 ramp 추세가 읽히도록 부드럽게 표시했습니다.</p>
          <div class="chart-shell chart-shell--tall"><canvas id="chart-vo2"></canvas><div class="chart-fallback" data-fallback="chart-vo2"></div></div>
        </article>
        <article class="chart-card">
          <h3>RER Progression</h3>
          <p>국소 이상치를 제거한 RER 흐름으로 metabolic transition을 읽기 쉽게 정리했습니다.</p>
          <div class="chart-shell chart-shell--compact"><canvas id="chart-rer"></canvas><div class="chart-fallback" data-fallback="chart-rer"></div></div>
        </article>
        <article class="chart-card chart-card--full">
          <h3>Metabolism Power Profile</h3>
          <p>{html_text(metabolism_intro)}</p>
          <div class="chart-shell chart-shell--tall"><canvas id="chart-metabolism"></canvas><div class="chart-fallback" data-fallback="chart-metabolism"></div></div>
          {metabolism_summary}
        </article>
        <article class="chart-card chart-card--full">
          <h3>Ventilatory Threshold Detection</h3>
          <p>VE/VO2, VE/VCO2 곡선을 스무딩해 VT1/VT2 시점이 더 읽기 쉽게 보이도록 했습니다.</p>
          <div class="chart-shell chart-shell--tall"><canvas id="chart-vt"></canvas><div class="chart-fallback" data-fallback="chart-vt"></div></div>
        </article>
      </div>
    </section>

    <section class="section" id="block3"{' style="display:none;"' if not report_registry.get('show_clearance', has_blood) else ''}>
      <div class="section-header">
        <div>
          <span class="section-tag">Block 3</span>
          <h2>젖산 클리어런스</h2>
          <p>VO2max 직후부터 FTP 기반 clearance 단계에서 lactate와 심박이 어떻게 재정렬되는지 봅니다.</p>
        </div>
      </div>
      <div class="chart-grid">
        <article class="chart-card">
          <h3>Lactate Clearance Curve</h3>
          <p>VO2max 종료 직후 샘플을 포함해 각 단계의 lactate 변화를 연결합니다.</p>
          <div class="chart-shell chart-shell--compact"><canvas id="chart-clearance"></canvas><div class="chart-fallback" data-fallback="chart-clearance"></div></div>
        </article>
        <article class="chart-card">
          <h3>FTP% HR vs Lactate</h3>
          <p>Clearance 단계의 %FTP별 심박과 lactate를 이중축으로 표시합니다.</p>
          <div class="chart-shell chart-shell--compact"><canvas id="chart-ftp"></canvas><div class="chart-fallback" data-fallback="chart-ftp"></div></div>
        </article>
      </div>
      <div class="analysis-grid" style="margin-top:18px;">
        <article class="chart-card">
          <h3>Training Zones Summary</h3>
          <p>젖산·HR 기반 threshold를 한 표로 정리했습니다.</p>
          <div class="table-wrap zone-table">
            <table>
              <thead>
                <tr><th>Zone</th><th>Name</th><th>Power</th><th>HR</th><th>Description</th></tr>
              </thead>
              <tbody>{zone_rows}</tbody>
            </table>
          </div>
        </article>
        <aside class="metric-stack">
          <div class="metric-card">
            <span>Clearance Lowest Point</span>
            <strong>{html_text(format_number(analysis['clearance'].get('best_clearance_power_w')))}W</strong>
            <p>{html_text(analysis['clearance'].get('b3_lactate_range'))} mmol/L 범위에서 형성</p>
          </div>
          <div class="metric-card">
            <span>Gross Efficiency Peak</span>
            <strong>{html_text(format_number(analysis['efficiency'].get('peak_gross_efficiency_pct'), 2))}%</strong>
            <p>{html_text(format_number(analysis['efficiency'].get('peak_gross_efficiency_power_w')))}W submax stage</p>
          </div>
          <div class="metric-card">
            <span>VO2-Power Slope</span>
            <strong>{html_text(format_number(analysis['efficiency'].get('vo2_power_slope_ml_per_w'), 2))} mL/W</strong>
            <p>Economy {html_text(format_number(analysis['efficiency'].get('economy_w_per_l_o2'), 1))} W/L O₂</p>
          </div>
        </aside>
      </div>
    </section>

    <section class="section" id="integrated">
      <div class="section-header">
        <div>
          <span class="section-tag">Integrated</span>
          <h2>통합 분석</h2>
          <p>전체 워크아웃의 심박/파워 흐름과 threshold 기반 해석을 함께 검토합니다.</p>
        </div>
      </div>
      <div class="chart-grid">
        <article class="chart-card chart-card--full">
          <h3>Full Workout Timeline</h3>
          <p>FIT 2,972 포인트를 10초 간격으로 다운샘플링한 HR + Power 타임라인입니다.</p>
          <div class="chart-shell chart-shell--tall"><canvas id="chart-workout"></canvas><div class="chart-fallback" data-fallback="chart-workout"></div></div>
        </article>
      </div>
    </section>

    {fuel_contribution_section}

    {energy_system_section}

    {cpm_panel_section}

    <section class="section" id="tables">
      <div class="section-header">
        <div>
          <span class="section-tag">Source Data</span>
          <h2>데이터 테이블</h2>
          <p>혈액 샘플 원본, BxB 요약, 프로토콜 스테이지를 인쇄 가능한 표로 제공합니다.</p>
        </div>
      </div>
      <div class="table-wrap">{blood_table}</div>
      <div class="table-wrap" style="margin-top:18px;">{bxb_table}</div>
      <div class="table-wrap" style="margin-top:18px;">{stage_table}</div>
    </section>

    <p class="footer-note">Generated at {html_text(context["meta"]["generated_at"])} · Source DB: analysis.db</p>

    <noscript>
      <div class="no-script">JavaScript가 비활성화되어 차트가 렌더링되지 않았습니다. 표와 핵심 수치는 그대로 읽을 수 있으며, 차트를 보려면 JavaScript를 활성화한 브라우저에서 이 파일을 열어주세요.</div>
    </noscript>
  </main>

  <script id="report-data" type="application/json">{data_json}</script>
  <script id="chart-data" type="application/json">{chart_json}</script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <script>
    const reportData = JSON.parse(document.getElementById('report-data').textContent);
    const chartData = JSON.parse(document.getElementById('chart-data').textContent);
    const palette = {{
      ink: '#162028',
      muted: '#60707a',
      accent: '#8f3b2f',
      teal: '#184e59',
      gold: '#a17b37',
      rose: '#b56a5c',
      fog: 'rgba(22,32,40,0.16)',
      fillTeal: 'rgba(24,78,89,0.16)',
      fillAccent: 'rgba(143,59,47,0.14)',
      fillGold: 'rgba(161,123,55,0.16)'
    }};

    function fallback(id, message) {{
      const canvas = document.getElementById(id);
      if (canvas) canvas.style.display = 'none';
      const box = document.querySelector(`[data-fallback="${{id}}"]`);
      if (box) {{
        box.classList.add('active');
        box.textContent = message;
      }}
    }}

    function markerDataset(label, x, y, color) {{
      if (x == null || y == null) return null;
      return {{
        type: 'scatter',
        label,
        data: [{{ x, y }}],
        pointRadius: 6,
        pointHoverRadius: 7,
        backgroundColor: color,
        borderColor: color
      }};
    }}

    function createChart(id, config) {{
      const el = document.getElementById(id);
      if (!el) return;
      if (!window.Chart) {{
        fallback(id, 'Chart.js CDN을 불러오지 못해 차트를 렌더링하지 못했습니다. 네트워크 연결 후 새로고침하거나 표 데이터를 사용해 해석해 주세요.');
        return;
      }}
      try {{
        new Chart(el, config);
      }} catch (error) {{
        console.error('Chart render failed:', id, error);
        fallback(id, '차트 데이터가 충분하지 않아 이 시각화는 생략되었습니다.');
      }}
    }}

    function isCompactViewport() {{
      return window.matchMedia('(max-width: 720px)').matches;
    }}

    function isNarrowViewport() {{
      return window.matchMedia('(max-width: 1040px)').matches;
    }}

    function axisTickOptions(kind = 'default') {{
      if (!isCompactViewport()) {{
        return {{
          color: palette.muted,
          maxRotation: 0
        }};
      }}
      return {{
        color: palette.muted,
        autoSkip: true,
        maxTicksLimit: kind === 'linear' ? 5 : 6,
        maxRotation: kind === 'time' ? 55 : 0,
        minRotation: kind === 'time' ? 55 : 0,
        padding: 6,
        font: {{ size: 10 }}
      }};
    }}

    function axisTitle(text) {{
      return {{
        display: true,
        text,
        color: palette.ink,
        font: {{ size: isCompactViewport() ? 11 : 12 }}
      }};
    }}

    function defaultOptions(title) {{
      return {{
        responsive: true,
        maintainAspectRatio: false,
        layout: {{
          padding: isCompactViewport()
            ? {{ top: 4, right: 4, bottom: 0, left: 0 }}
            : {{ top: 8, right: 8, bottom: 0, left: 0 }}
        }},
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
          legend: {{
            position: 'bottom',
            labels: {{
              usePointStyle: true,
              color: palette.ink,
              boxWidth: isCompactViewport() ? 8 : 10,
              padding: isCompactViewport() ? 10 : 14,
              font: {{ size: isCompactViewport() ? 10 : 11 }}
            }}
          }},
          title: {{
            display: !!title,
            text: title,
            color: palette.ink,
            padding: {{ bottom: isCompactViewport() ? 8 : 12 }},
            font: {{ family: 'Iowan Old Style, Palatino Linotype, serif', size: isCompactViewport() ? 13 : 15 }}
          }}
        }},
        scales: {{
          x: {{
            ticks: axisTickOptions(),
            grid: {{ color: 'rgba(22,32,40,0.06)' }}
          }},
          y: {{
            ticks: axisTickOptions('linear'),
            grid: {{ color: 'rgba(22,32,40,0.06)' }}
          }}
        }}
      }};
    }}

    createChart('chart-lactate', {{
      type: 'scatter',
      data: {{
        datasets: [
          {{
            label: 'Measured LT Samples',
            data: chartData.lactate_curve.measured_lt_points.map(p => ({{ x: p.power_w, y: p.lactate }})),
            backgroundColor: palette.accent,
            borderColor: palette.accent,
            showLine: false,
            pointRadius: 5
          }},
          {{
            label: 'Adjusted D-max Anchors',
            data: chartData.lactate_curve.adjusted_points.map(p => ({{ x: p.power_w, y: p.lactate }})),
            backgroundColor: '#f4efe6',
            borderColor: palette.teal,
            borderWidth: 2,
            showLine: false,
            pointRadius: 6
          }},
          {{
            type: 'line',
            label: 'Adjusted Curve',
            data: chartData.lactate_curve.adjusted_curve.map(p => ({{ x: p.power_w, y: p.lactate }})),
            borderColor: palette.teal,
            backgroundColor: palette.fillTeal,
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.28
          }},
          {{
            type: 'line',
            label: 'Fixed Threshold',
            data: chartData.lactate_curve.adjusted_curve.map(p => ({{ x: p.power_w, y: chartData.lactate_curve.fixed_threshold }})),
            borderColor: palette.gold,
            borderDash: [6, 6],
            pointRadius: 0,
            tension: 0
          }},
          markerDataset('LT1 Fixed', chartData.lactate_curve.lt1_fixed, chartData.lactate_curve.fixed_threshold, palette.gold),
          markerDataset('LT1 D-max', chartData.lactate_curve.lt1_dmax, reportData.analysis.lactate.lt1_dmax_lactate, palette.teal)
        ].filter(Boolean)
      }},
      options: {{
        ...defaultOptions('Power vs Lactate'),
        scales: {{
          x: {{ title: axisTitle('Power (W)'), ticks: axisTickOptions('linear'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }},
          y: {{ title: axisTitle('Lactate (mmol/L)'), ticks: axisTickOptions('linear'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }}
        }}
      }}
    }});

    createChart('chart-overlay', {{
      type: 'bar',
      data: {{
        labels: chartData.block1_overlay.labels,
        datasets: [
          {{
            type: 'line',
            label: 'HR',
            data: chartData.block1_overlay.hr,
            yAxisID: 'y',
            borderColor: palette.teal,
            backgroundColor: palette.fillTeal,
            tension: 0.3
          }},
          {{
            type: 'line',
            label: 'Lactate',
            data: chartData.block1_overlay.lactate,
            yAxisID: 'y1',
            borderColor: palette.accent,
            backgroundColor: palette.fillAccent,
            tension: 0.3
          }}
        ]
      }},
      options: {{
        ...defaultOptions('Block 1 HR + Lactate'),
        scales: {{
          x: {{ ticks: axisTickOptions(), grid: {{ color: 'rgba(22,32,40,0.06)' }} }},
          y: {{ position: 'left', title: axisTitle('HR (bpm)'), ticks: axisTickOptions('linear'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }},
          y1: {{ position: 'right', title: axisTitle('Lactate (mmol/L)'), ticks: axisTickOptions('linear'), grid: {{ drawOnChartArea: false }} }}
        }}
      }}
    }});

    createChart('chart-glucose', {{
      type: 'line',
      data: {{
        labels: chartData.glucose_response.labels,
        datasets: [{{
          label: 'Glucose',
          data: chartData.glucose_response.glucose,
          borderColor: palette.gold,
          backgroundColor: palette.fillGold,
          pointRadius: 4,
          tension: 0.28
        }}]
      }},
      options: {{
        ...defaultOptions('Glucose Response'),
        scales: {{
          x: {{ ticks: axisTickOptions(), grid: {{ color: 'rgba(22,32,40,0.06)' }} }},
          y: {{ title: axisTitle('Glucose (mmol/L)'), ticks: axisTickOptions('linear'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }}
        }}
      }}
    }});

    createChart('chart-vo2', {{
      type: 'line',
      data: {{
        labels: chartData.vo2_timeseries.t_s,
        datasets: [
          {{ label: 'VO2', data: chartData.vo2_timeseries.vo2, borderColor: palette.teal, yAxisID: 'y', pointRadius: 0, tension: 0.2 }},
          {{ label: 'VCO2', data: chartData.vo2_timeseries.vco2, borderColor: palette.accent, yAxisID: 'y', pointRadius: 0, tension: 0.2 }},
          {{ label: 'VE', data: chartData.vo2_timeseries.ve, borderColor: palette.gold, yAxisID: 'y1', pointRadius: 0, tension: 0.2 }}
        ]
      }},
      options: {{
        ...defaultOptions('VO2 / VCO2 / VE'),
        scales: {{
          x: {{ title: axisTitle('Time (s)'), ticks: axisTickOptions('time'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }},
          y: {{ position: 'left', title: axisTitle('VO2 / VCO2 (mL/min)'), ticks: axisTickOptions('linear'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }},
          y1: {{ position: 'right', title: axisTitle('VE (L/min)'), ticks: axisTickOptions('linear'), grid: {{ drawOnChartArea: false }} }}
        }}
      }}
    }});

    createChart('chart-rer', {{
      type: 'line',
      data: {{
        labels: chartData.rer_progression.t_s,
        datasets: [{{
          label: 'RER',
          data: chartData.rer_progression.rq,
          borderColor: palette.rose,
          backgroundColor: palette.fillAccent,
          pointRadius: 0,
          tension: 0.25
        }}]
      }},
      options: {{
        ...defaultOptions(`RER Progression · VO2 plateau: ${{reportData.analysis.vo2max.vo2_plateau ? 'Yes' : 'No'}}`),
        scales: {{
          x: {{ title: axisTitle('Time (s)'), ticks: axisTickOptions('time'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }},
          y: {{ title: axisTitle('RER'), ticks: axisTickOptions('linear'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }}
        }}
      }}
    }});

    const metabolismOverlayPlugin = {{
      id: 'metabolismOverlay',
      beforeDatasetsDraw(chart, args, opts) {{
        if (!opts || !opts.fatmaxZone) return;
        const xScale = chart.scales.x;
        const chartArea = chart.chartArea;
        if (!xScale || !chartArea) return;
        const x1 = xScale.getPixelForValue(opts.fatmaxZone.min);
        const x2 = xScale.getPixelForValue(opts.fatmaxZone.max);
        chart.ctx.save();
        chart.ctx.fillStyle = 'rgba(161,123,55,0.12)';
        chart.ctx.fillRect(x1, chartArea.top, x2 - x1, chartArea.bottom - chartArea.top);
        chart.ctx.restore();
      }},
      afterDatasetsDraw(chart, args, opts) {{
        if (!opts) return;
        const xScale = chart.scales.x;
        const yScale = chart.scales.y;
        const y1Scale = chart.scales.y1;
        if (!xScale || !yScale || !y1Scale) return;
        const chartArea = chart.chartArea;
        const ctx = chart.ctx;

        function drawVerticalMarker(power, color, label, yOffset = 0) {{
          if (power == null) return;
          const x = xScale.getPixelForValue(power);
          ctx.save();
          ctx.setLineDash([5, 5]);
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(x, chartArea.top);
          ctx.lineTo(x, chartArea.bottom);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.fillStyle = color;
          ctx.font = isCompactViewport()
            ? '600 9px Avenir Next, Segoe UI, sans-serif'
            : '600 11px Avenir Next, Segoe UI, sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(label, x, chartArea.top + 14 + yOffset);
          ctx.restore();
        }}

        const fatmaxLabel = isCompactViewport()
          ? 'FM ' + Math.round(opts.fatmaxPower) + 'W'
          : 'FatMax ' + Math.round(opts.fatmaxPower) + 'W';
        const ftpLabel = 'FTP ' + Math.round(opts.ftpPower) + 'W';
        const crossoverLabel = isCompactViewport()
          ? 'XO ' + Math.round(opts.crossoverPower) + 'W'
          : 'Crossover ' + Math.round(opts.crossoverPower) + 'W';

        drawVerticalMarker(opts.fatmaxPower, palette.accent, fatmaxLabel);
        drawVerticalMarker(opts.ftpPower, palette.fog, ftpLabel, isCompactViewport() ? 12 : 16);
        if (opts.crossoverPower != null) {{
          drawVerticalMarker(opts.crossoverPower, palette.teal, crossoverLabel, isCompactViewport() ? 24 : 32);
        }}
      }}
    }};

    const metabolismPowerMax = Math.max(
      ...(chartData.metabolism.power_w || []).filter(value => Number.isFinite(value)),
      chartData.metabolism.ftp_anchor.power_w || 0,
      chartData.metabolism.fatmax.zone_max_w || 0,
      0
    );
    const metabolismAxisStep = metabolismPowerMax <= 300 ? 25 : 50;
    const metabolismAxisMax = metabolismPowerMax > 0
      ? Math.ceil(metabolismPowerMax / metabolismAxisStep) * metabolismAxisStep
      : 400;

    createChart('chart-metabolism', {{
      type: 'line',
      data: {{
        datasets: [
          {{
            label: 'Fat Oxidation',
            data: chartData.metabolism.power_w.map((power, idx) => ({{ x: power, y: chartData.metabolism.fat_gmin[idx] }})),
            parsing: false,
            borderColor: palette.accent,
            backgroundColor: 'rgba(241, 194, 93, 0.20)',
            fill: true,
            pointRadius: 0,
            tension: 0.18,
            yAxisID: 'y'
          }},
          {{
            label: 'CHO Oxidation',
            data: chartData.metabolism.power_w.map((power, idx) => ({{ x: power, y: chartData.metabolism.cho_gmin[idx] }})),
            parsing: false,
            borderColor: palette.teal,
            backgroundColor: 'rgba(24, 78, 89, 0.10)',
            fill: true,
            pointRadius: 0,
            tension: 0.18,
            yAxisID: 'y'
          }},
          {{
            label: 'Energy Cost',
            data: chartData.metabolism.power_w.map((power, idx) => ({{ x: power, y: chartData.metabolism.kcal_h[idx] }})),
            parsing: false,
            borderColor: palette.fog,
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.12,
            yAxisID: 'y1'
          }}
        ]
      }},
      options: {{
        ...defaultOptions('Metabolism Power Profile'),
        scales: {{
          x: {{
            type: 'linear',
            min: 0,
            max: metabolismAxisMax,
            title: axisTitle('Power (W)'),
            ticks: axisTickOptions('linear'),
            grid: {{ color: 'rgba(22,32,40,0.06)' }}
          }},
          y: {{ title: axisTitle('Oxidation (g/min)'), ticks: axisTickOptions('linear'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }},
          y1: {{ position: 'right', title: axisTitle(isCompactViewport() ? 'kcal/h' : 'Energy (kcal/h)'), ticks: axisTickOptions('linear'), grid: {{ drawOnChartArea: false }} }}
        }},
        plugins: {{
          ...defaultOptions('').plugins,
          metabolismOverlay: {{
            fatmaxZone: {{
              min: chartData.metabolism.fatmax.zone_min_w,
              max: chartData.metabolism.fatmax.zone_max_w
            }},
            fatmaxPower: chartData.metabolism.fatmax.power_w,
            ftpPower: chartData.metabolism.ftp_anchor.power_w,
            crossoverPower: chartData.metabolism.primary_crossover ? chartData.metabolism.primary_crossover.power_w : null
          }}
        }}
      }},
      plugins: [metabolismOverlayPlugin]
    }});

    const vtSeriesMax = Math.max(
      ...(chartData.ventilatory_thresholds.ve_vo2 || [0]),
      ...(chartData.ventilatory_thresholds.ve_vco2 || [0]),
      0
    );

    createChart('chart-vt', {{
      type: 'line',
      data: {{
        labels: chartData.ventilatory_thresholds.t_s,
        datasets: [
          {{ label: 'VE/VO2', data: chartData.ventilatory_thresholds.ve_vo2, borderColor: palette.teal, pointRadius: 0, tension: 0.2 }},
          {{ label: 'VE/VCO2', data: chartData.ventilatory_thresholds.ve_vco2, borderColor: palette.gold, pointRadius: 0, tension: 0.2 }},
          {{
            label: 'VT1',
            data: [
              {{ x: chartData.ventilatory_thresholds.vt1_time_s, y: 0 }},
              {{ x: chartData.ventilatory_thresholds.vt1_time_s, y: vtSeriesMax }}
            ],
            parsing: false,
            borderColor: palette.teal,
            borderDash: [5, 5],
            pointRadius: 0,
            tension: 0
          }},
          {{
            label: 'VT2',
            data: [
              {{ x: chartData.ventilatory_thresholds.vt2_time_s, y: 0 }},
              {{ x: chartData.ventilatory_thresholds.vt2_time_s, y: vtSeriesMax }}
            ],
            parsing: false,
            borderColor: palette.accent,
            borderDash: [5, 5],
            pointRadius: 0,
            tension: 0
          }}
        ].filter(Boolean)
      }},
      options: {{
        ...defaultOptions(`VT1 ${{reportData.analysis.ventilatory_thresholds.vt1_power_w}}W · VT2 ${{reportData.analysis.ventilatory_thresholds.vt2_power_w}}W`),
        scales: {{
          x: {{ title: axisTitle('Time (s)'), ticks: axisTickOptions('time'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }},
          y: {{ title: axisTitle(isCompactViewport() ? 'VE eq.' : 'Ventilatory Equivalents'), ticks: axisTickOptions('linear'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }}
        }},
        plugins: {{
          ...defaultOptions('').plugins
        }}
      }}
    }});

    createChart('chart-clearance', {{
      type: 'line',
      data: {{
        labels: ['VO2max End', ...chartData.clearance.points.map(p => `${{Math.round(p.power_w)}}W`)],
        datasets: [{{
          label: 'Lactate',
          data: [chartData.clearance.post_vo2max_lactate, ...chartData.clearance.points.map(p => p.lactate)],
          borderColor: palette.accent,
          backgroundColor: palette.fillAccent,
          pointRadius: 4,
          tension: 0.2
        }}]
      }},
      options: {{
        ...defaultOptions('Lactate Clearance'),
        scales: {{
          x: {{ ticks: axisTickOptions(), grid: {{ color: 'rgba(22,32,40,0.06)' }} }},
          y: {{ title: axisTitle('Lactate (mmol/L)'), ticks: axisTickOptions('linear'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }}
        }}
      }}
    }});

    createChart('chart-ftp', {{
      type: 'line',
      data: {{
        labels: chartData.ftp_overlay.labels,
        datasets: [
          {{ label: 'HR', data: chartData.ftp_overlay.hr, borderColor: palette.teal, yAxisID: 'y', tension: 0.25 }},
          {{ label: 'Lactate', data: chartData.ftp_overlay.lactate, borderColor: palette.accent, yAxisID: 'y1', tension: 0.25 }}
        ]
      }},
      options: {{
        ...defaultOptions('FTP% HR vs Lactate'),
        scales: {{
          x: {{ ticks: axisTickOptions(), grid: {{ color: 'rgba(22,32,40,0.06)' }} }},
          y: {{ position: 'left', title: axisTitle('HR (bpm)'), ticks: axisTickOptions('linear') }},
          y1: {{ position: 'right', title: axisTitle('Lactate (mmol/L)'), ticks: axisTickOptions('linear'), grid: {{ drawOnChartArea: false }} }}
        }}
      }}
    }});

    createChart('chart-workout', {{
      type: 'line',
      data: {{
        labels: chartData.workout_timeline.elapsed_s,
        datasets: [
          {{ label: 'HR', data: chartData.workout_timeline.hr, borderColor: palette.teal, yAxisID: 'y', pointRadius: 0, tension: 0.15 }},
          {{ label: 'Power', data: chartData.workout_timeline.power, borderColor: palette.accent, yAxisID: 'y1', pointRadius: 0, tension: 0.15 }}
        ]
      }},
      options: {{
        ...defaultOptions('Workout Timeline'),
        scales: {{
          x: {{ title: axisTitle(isNarrowViewport() ? 'Elapsed (s)' : 'Elapsed Time (s)'), ticks: axisTickOptions('time'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }},
          y: {{ position: 'left', title: axisTitle('HR (bpm)'), ticks: axisTickOptions('linear'), grid: {{ color: 'rgba(22,32,40,0.06)' }} }},
          y1: {{ position: 'right', title: axisTitle('Power (W)'), ticks: axisTickOptions('linear'), grid: {{ drawOnChartArea: false }} }}
        }}
      }}
    }});

    const fuelFlex = reportData.fuel_flex || {{}};
    if (Number.isFinite(fuelFlex.fat_contribution_pct) && Number.isFinite(fuelFlex.cho_contribution_pct)) {{
      createChart('chart-fuel-split', {{
        type: 'doughnut',
        data: {{
          labels: ['Fat', 'CHO'],
          datasets: [{{
            data: [fuelFlex.fat_contribution_pct, fuelFlex.cho_contribution_pct],
            backgroundColor: [palette.gold, palette.teal],
            borderColor: ['rgba(255,255,255,0.95)', 'rgba(255,255,255,0.95)'],
            borderWidth: 3,
            hoverOffset: 6
          }}]
        }},
        options: {{
          ...defaultOptions('Fuel Split Before RQ 1.0'),
          cutout: '62%',
          plugins: {{
            ...defaultOptions('').plugins,
            legend: {{
              position: 'bottom',
              labels: {{
                color: palette.muted,
                font: {{ family: 'Avenir Next, Segoe UI, sans-serif', size: 12 }},
                padding: 16
              }}
            }},
            tooltip: {{
              callbacks: {{
                label(context) {{
                  const pct = Number(context.raw || 0);
                  const totalKcal = Number(fuelFlex.total_kcal || 0);
                  const kcal = totalKcal > 0 ? (totalKcal * pct) / 100 : 0;
                  return `${{context.label}}: ${{pct.toFixed(1)}}% · ${{kcal.toFixed(1)}} kcal`;
                }}
              }}
            }}
          }}
        }}
      }});
    }}
  </script>
</body>
</html>
"""


def generate_report(db_path: Path, output_dir: Path) -> Path:
    """Build context, render HTML, and write the report file.

    Args:
        db_path: Path to the analysis.db file.
        output_dir: Directory where index.html will be written.

    Returns:
        Path to the generated report file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "index.html"

    context = build_report_context(db_path)
    output_path.write_text(render_html(context), encoding="utf-8")
    return output_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.report <db_path> [output_dir]")
        sys.exit(1)
    db = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else db.parent / "report"
    path = generate_report(db, out)
    print(f"Report written to {path}")
