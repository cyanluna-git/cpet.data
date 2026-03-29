#!/usr/bin/env python3
"""Patch legacy published CPET reports with the RQ1 fuel contribution section.

This is intended for older standalone published HTML reports that still embed
``report-data`` and ``chart-data`` JSON but are no longer connected to a live
submission/workspace pipeline run.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
from pathlib import Path
from typing import Any


SCRIPT_RE_TEMPLATE = r"<script[^>]*id=[\"']{script_id}[\"'][^>]*>(.*?)</script>"


def extract_embedded_json(doc: str, script_id: str) -> tuple[dict[str, Any], re.Match[str]] | tuple[None, None]:
    pattern = re.compile(SCRIPT_RE_TEMPLATE.format(script_id=re.escape(script_id)), re.DOTALL | re.IGNORECASE)
    match = pattern.search(doc)
    if not match:
        return None, None
    raw = html.unescape(match.group(1))
    return json.loads(raw), match


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _linear_interpolate(x1: float, y1: float, x2: float, y2: float, target_x: float) -> float:
    if x2 == x1:
        return float(y2)
    ratio = (target_x - x1) / (x2 - x1)
    return float(y1 + ratio * (y2 - y1))


def _trapezoid_area(y: list[float], x: list[float]) -> float:
    if len(y) < 2 or len(x) < 2:
        return 0.0
    total = 0.0
    for idx in range(1, len(y)):
        total += (x[idx] - x[idx - 1]) * (y[idx] + y[idx - 1]) * 0.5
    return float(total)


def build_rq1_fuel_split_from_chart(chart_data: dict[str, Any]) -> dict[str, Any]:
    vo2_ts = chart_data.get("vo2_timeseries") or {}
    t_s = vo2_ts.get("t_s") or []
    vo2 = vo2_ts.get("vo2") or []
    vco2 = vo2_ts.get("vco2") or []
    rq = vo2_ts.get("rq") or []
    hr = vo2_ts.get("hr") or []
    power = vo2_ts.get("power") or []

    rows: list[dict[str, float]] = []
    for idx in range(min(len(t_s), len(vo2), len(vco2), len(rq))):
        values = (t_s[idx], vo2[idx], vco2[idx], rq[idx])
        if not all(_is_finite_number(v) for v in values):
            continue
        t_val = float(t_s[idx])
        vo2_val = float(vo2[idx])
        vco2_val = float(vco2[idx])
        rq_val = float(rq[idx])
        if vo2_val <= 100 or rq_val >= 1.6:
            continue
        power_val = float(power[idx]) if idx < len(power) and _is_finite_number(power[idx]) else 0.0
        hr_val = float(hr[idx]) if idx < len(hr) and _is_finite_number(hr[idx]) else 0.0
        rows.append(
            {
                "t_s": t_val,
                "vo2_ml": vo2_val,
                "vco2_ml": vco2_val,
                "rq": rq_val,
                "bike_power_w": power_val,
                "hr_bpm": hr_val,
                "fat_gmin": max(0.0, 1.67 * (vo2_val / 1000.0) - 1.67 * (vco2_val / 1000.0)),
                "cho_gmin": max(0.0, 4.55 * (vco2_val / 1000.0) - 3.21 * (vo2_val / 1000.0)),
            }
        )

    if len(rows) < 2:
        return {"status": "insufficient_data"}

    crossing_idx = next((idx for idx, row in enumerate(rows) if row["rq"] >= 1.0), None)
    if crossing_idx is None:
        return {"status": "no_rq1_crossing"}

    cutoff = [dict(row) for row in rows[: crossing_idx + 1]]
    crossing_time_s = float(rows[crossing_idx]["t_s"])
    crossing_rq = float(rows[crossing_idx]["rq"])

    if crossing_idx > 0 and rows[crossing_idx - 1]["rq"] < 1.0:
        left = rows[crossing_idx - 1]
        right = rows[crossing_idx]
        crossing_time_s = _linear_interpolate(left["rq"], left["t_s"], right["rq"], right["t_s"], 1.0)
        crossing_row = {
            "t_s": crossing_time_s,
            "rq": 1.0,
            "bike_power_w": _linear_interpolate(left["t_s"], left["bike_power_w"], right["t_s"], right["bike_power_w"], crossing_time_s),
            "hr_bpm": _linear_interpolate(left["t_s"], left["hr_bpm"], right["t_s"], right["hr_bpm"], crossing_time_s),
            "fat_gmin": _linear_interpolate(left["t_s"], left["fat_gmin"], right["t_s"], right["fat_gmin"], crossing_time_s),
            "cho_gmin": _linear_interpolate(left["t_s"], left["cho_gmin"], right["t_s"], right["cho_gmin"], crossing_time_s),
        }
        cutoff = [dict(row) for row in rows[:crossing_idx]] + [crossing_row]
        crossing_rq = 1.0

    t_min = [row["t_s"] / 60.0 for row in cutoff]
    fat_kcal_rate = [row["fat_gmin"] * 9.75 for row in cutoff]
    cho_kcal_rate = [row["cho_gmin"] * 4.07 for row in cutoff]
    fat_kcal = _trapezoid_area(fat_kcal_rate, t_min)
    cho_kcal = _trapezoid_area(cho_kcal_rate, t_min)
    total_kcal = fat_kcal + cho_kcal

    return {
        "status": "computed",
        "crossing_time_s": round(crossing_time_s, 1),
        "crossing_rq": round(crossing_rq, 2),
        "crossing_power_w": int(round(cutoff[-1]["bike_power_w"])) if cutoff[-1]["bike_power_w"] > 0 else None,
        "crossing_hr_bpm": int(round(cutoff[-1]["hr_bpm"])) if cutoff[-1]["hr_bpm"] > 0 else None,
        "fat_kcal": round(fat_kcal, 2),
        "cho_kcal": round(cho_kcal, 2),
        "total_kcal": round(total_kcal, 2),
        "fat_pct": round((fat_kcal / total_kcal) * 100.0, 1) if total_kcal > 0 else None,
        "cho_pct": round((cho_kcal / total_kcal) * 100.0, 1) if total_kcal > 0 else None,
    }


def build_fuel_flex(report_data: dict[str, Any], rq1: dict[str, Any]) -> dict[str, Any]:
    analysis = report_data.get("analysis") or {}
    substrate = analysis.get("substrate") or {}
    vt = analysis.get("ventilatory_thresholds") or {}
    markers = substrate.get("metabolism_markers") or {}
    substrate = {**substrate, "rq1_fuel_split": rq1}
    fat_pct = float(rq1.get("fat_pct") or 0.0)
    crossing_power = float(rq1.get("crossing_power_w") or 0.0)
    crossover = markers.get("primary_crossover") or {}
    crossover_power = float(crossover.get("power_w") or substrate.get("crossover_power_w") or 0.0)
    fatmax_power = float(substrate.get("fatmax_power_w") or 0.0)
    vt1_power = float(vt.get("vt1_power_w") or 0.0)

    fat_share_score = min(max(fat_pct / 50.0, 0.0), 1.0) * 45.0
    crossover_score = min(max(crossover_power / crossing_power, 0.0), 1.0) * 35.0 if crossing_power > 0 else 0.0
    fatmax_score = min(max(fatmax_power / vt1_power, 0.0), 1.0) * 20.0 if vt1_power > 0 else 0.0
    score = round(fat_share_score + crossover_score + fatmax_score, 1)

    if score >= 75:
        note = "지방 산화 유지와 탄수화물 전환 타이밍이 비교적 안정적인 편입니다."
    elif score >= 55:
        note = "기본적인 전환 능력은 있으나 고강도 진입 전 탄수화물 의존이 다소 빠르게 올라옵니다."
    else:
        note = "저중강도 지방 활용과 고강도 전환 사이 간격을 더 다듬을 필요가 있습니다."

    return {
        "score": score,
        "note": note,
        "fat_contribution_pct": round(float(rq1.get("fat_pct") or 0.0), 1),
        "cho_contribution_pct": round(float(rq1.get("cho_pct") or 0.0), 1),
        "crossing_power_w": rq1.get("crossing_power_w"),
        "crossing_hr_bpm": rq1.get("crossing_hr_bpm"),
        "total_kcal": rq1.get("total_kcal"),
        "formula_note": "Custom score = fat share before RQ 1.0 (45) + crossover proximity to RQ1 power (35) + FatMax proximity to VT1 (20).",
    }


def format_number(value: Any, decimals: int = 0) -> str:
    if value is None:
        return "-"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if decimals == 0:
        return f"{int(round(num))}" if abs(num - round(num)) < 1e-9 else f"{num:.1f}"
    return f"{num:.{decimals}f}"


def donut_svg(fat_pct: float, cho_pct: float) -> str:
    circumference = 2 * math.pi * 54
    fat_len = circumference * (fat_pct / 100.0)
    cho_len = circumference * (cho_pct / 100.0)
    return f"""
      <svg viewBox="0 0 160 160" width="220" height="220" aria-label="Fuel split donut chart">
        <circle cx="80" cy="80" r="54" fill="none" stroke="#ede7dc" stroke-width="22"></circle>
        <circle cx="80" cy="80" r="54" fill="none" stroke="#a17b37" stroke-width="22" stroke-linecap="butt"
                stroke-dasharray="{fat_len:.3f} {circumference:.3f}" transform="rotate(-90 80 80)"></circle>
        <circle cx="80" cy="80" r="54" fill="none" stroke="#184e59" stroke-width="22" stroke-linecap="butt"
                stroke-dasharray="{cho_len:.3f} {circumference:.3f}" stroke-dashoffset="{-fat_len:.3f}" transform="rotate(-90 80 80)"></circle>
        <circle cx="80" cy="80" r="34" fill="#fffdf8"></circle>
        <text x="80" y="76" text-anchor="middle" style="font: 700 16px system-ui, -apple-system, sans-serif; fill:#162028;">RQ 1.0</text>
        <text x="80" y="96" text-anchor="middle" style="font: 500 11px system-ui, -apple-system, sans-serif; fill:#60707a;">Fuel Split</text>
      </svg>
    """


def render_fuel_section(fuel_flex: dict[str, Any]) -> str:
    fat_pct = float(fuel_flex.get("fat_contribution_pct") or 0.0)
    cho_pct = float(fuel_flex.get("cho_contribution_pct") or 0.0)
    return f"""
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
          <strong class="kpi-value">{html.escape(format_number(fuel_flex.get('fat_contribution_pct'), 1))}</strong>
          <span class="kpi-unit">%</span>
          <p class="kpi-note">RQ 1.0 이전 지방 기여율</p>
        </article>
        <article class="kpi-card">
          <span class="kpi-label">CHO Contribution</span>
          <strong class="kpi-value">{html.escape(format_number(fuel_flex.get('cho_contribution_pct'), 1))}</strong>
          <span class="kpi-unit">%</span>
          <p class="kpi-note">RQ 1.0 이전 탄수화물 기여율</p>
        </article>
        <article class="kpi-card">
          <span class="kpi-label">RQ 1.0 Crossing</span>
          <strong class="kpi-value">{html.escape(format_number(fuel_flex.get('crossing_power_w')))}</strong>
          <span class="kpi-unit">W</span>
          <p class="kpi-note">HR {html.escape(format_number(fuel_flex.get('crossing_hr_bpm')))} bpm · 총 {html.escape(format_number(fuel_flex.get('total_kcal'), 1))} kcal</p>
        </article>
        <article class="kpi-card">
          <span class="kpi-label">Metabolic Flexibility Index</span>
          <strong class="kpi-value">{html.escape(format_number(fuel_flex.get('score'), 1))}</strong>
          <span class="kpi-unit">/100</span>
          <p class="kpi-note">{html.escape(str(fuel_flex.get('note') or ''))}</p>
        </article>
      </div>
      <article class="chart-card chart-card--full" style="margin-top:18px;">
        <h3>Fuel Split Before RQ 1.0</h3>
        <p>RQ 1.0 도달 전까지 누적된 총 kcal에서 지방과 탄수화물 기여 비율을 바로 읽을 수 있도록 도넛 차트로 표시합니다.</p>
        <div style="display:grid;grid-template-columns:minmax(220px,320px) 1fr;gap:24px;align-items:center;padding:8px 0 4px;">
          <div style="display:flex;justify-content:center;align-items:center;">{donut_svg(fat_pct, cho_pct)}</div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;">
            <div style="padding:18px;border-radius:18px;background:#fffdf8;border:1px solid rgba(22,32,40,0.08);">
              <span style="display:block;font-size:0.8rem;letter-spacing:0.08em;color:#60707a;text-transform:uppercase;">Fat</span>
              <strong style="display:block;font-size:2rem;line-height:1.05;color:#162028;margin-top:8px;">{fat_pct:.1f}%</strong>
            </div>
            <div style="padding:18px;border-radius:18px;background:#fffdf8;border:1px solid rgba(22,32,40,0.08);">
              <span style="display:block;font-size:0.8rem;letter-spacing:0.08em;color:#60707a;text-transform:uppercase;">CHO</span>
              <strong style="display:block;font-size:2rem;line-height:1.05;color:#162028;margin-top:8px;">{cho_pct:.1f}%</strong>
            </div>
            <div style="padding:18px;border-radius:18px;background:#fffdf8;border:1px solid rgba(22,32,40,0.08);">
              <span style="display:block;font-size:0.8rem;letter-spacing:0.08em;color:#60707a;text-transform:uppercase;">Legend</span>
              <div style="display:flex;gap:14px;align-items:center;margin-top:12px;font-size:0.95rem;color:#162028;">
                <span style="display:inline-flex;align-items:center;gap:8px;"><span style="width:12px;height:12px;border-radius:999px;background:#a17b37;display:inline-block;"></span>Fat</span>
                <span style="display:inline-flex;align-items:center;gap:8px;"><span style="width:12px;height:12px;border-radius:999px;background:#184e59;display:inline-block;"></span>CHO</span>
              </div>
            </div>
          </div>
        </div>
      </article>
      <div class="note-card" style="margin-top:18px;">
        <strong>Custom definition</strong>
        <p>{html.escape(str(fuel_flex.get('formula_note') or ''))}</p>
      </div>
    </section>"""


def patch_report(index_file: Path) -> bool:
    doc = index_file.read_text(encoding="utf-8", errors="ignore")
    if "RQ 1.0 기준 연료 기여율" in doc:
        return False

    report_data, report_match = extract_embedded_json(doc, "report-data")
    chart_data, _ = extract_embedded_json(doc, "chart-data")
    if not report_data or not chart_data:
        return False
    vo2_ts = chart_data.get("vo2_timeseries") or {}
    if not vo2_ts.get("vo2") or not vo2_ts.get("vco2"):
        return False

    rq1 = build_rq1_fuel_split_from_chart(chart_data)
    if rq1.get("status") != "computed":
        return False

    analysis = report_data.setdefault("analysis", {})
    substrate = analysis.setdefault("substrate", {})
    substrate["rq1_fuel_split"] = rq1
    fuel_flex = build_fuel_flex(report_data, rq1)
    report_data["fuel_flex"] = fuel_flex

    insertion_point = doc.find('<section class="section" id="energy-system">')
    if insertion_point == -1:
        insertion_point = doc.rfind("</main>")
    if insertion_point == -1:
        return False

    section_html = render_fuel_section(fuel_flex)
    patched = doc[:insertion_point] + "\n" + section_html + "\n\n" + doc[insertion_point:]

    if report_match:
        safe_json = json.dumps(report_data, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
        patched = re.sub(
            SCRIPT_RE_TEMPLATE.format(script_id="report-data"),
            f'<script id="report-data" type="application/json">{safe_json}</script>',
            patched,
            count=1,
            flags=re.DOTALL | re.IGNORECASE,
        )

    index_file.write_text(patched, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch legacy published CPET reports with the RQ1 fuel section.")
    parser.add_argument("--published-dir", type=Path, required=True)
    parser.add_argument("--slug", action="append", default=[])
    args = parser.parse_args()

    published_dir = args.published_dir.resolve()
    targets = [published_dir / slug / "index.html" for slug in args.slug] if args.slug else list(published_dir.glob("*/index.html"))

    patched = 0
    for index_file in sorted(targets):
        if not index_file.is_file():
            continue
        if patch_report(index_file):
            patched += 1
            print(index_file.parent.name)

    print(f"patched={patched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
