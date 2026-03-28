"""Standalone HTML interpretation report renderer for INSCYD uploads."""

from __future__ import annotations

import html
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pipeline.inscyd_coaching import build_coaching_payload
from pipeline.inscyd_workspace import ParsedInscydWorkspace, parse_inscyd_workspace


def _text(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _num(value: Any, decimals: int = 1) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _text(value)
    return f"{number:.{decimals}f}"


def _fmt_power(value: Any) -> str:
    return "-" if value is None else f"{_num(value, 1)}W"


def _fmt_pct(value: Any) -> str:
    return "-" if value is None else f"{_num(value, 1)}%"


def _fmt_duration(seconds: Any) -> str:
    try:
        sec = int(seconds)
    except (TypeError, ValueError):
        return "-"
    if sec < 60:
        return f"{sec}s"
    minutes, remainder = divmod(sec, 60)
    if remainder == 0:
        return f"{minutes}m"
    return f"{minutes}m {remainder:02d}s"


def _safe_href(path: str) -> str:
    if not path:
        return ""
    return "/".join(quote(part) for part in path.split("/"))


def _keyword_focus(text: str) -> str:
    haystack = (text or "").lower()
    if any(token in haystack for token in ("vlamax", "무산소", "스프린트")):
        return "anaerobic"
    if any(token in haystack for token in ("fat", "지방", "fatmax")):
        return "fat"
    if any(token in haystack for token in ("vo2", "최대산소", "최대 산소")):
        return "vo2"
    if any(token in haystack for token in ("ftp", "threshold", "at", "역치")):
        return "threshold"
    return "balanced"


def _build_interpretation_cards(parsed: ParsedInscydWorkspace) -> list[dict[str, str]]:
    report = parsed.report
    cards = []
    if report.vo2max_rel_ml_kg_min is not None:
        cards.append(
            {
                "title": "VO2max",
                "value": f"{_num(report.vo2max_rel_ml_kg_min, 1)} mL/kg/min",
                "note": "INSCYD 리포트에 기재된 최대 유산소 능력입니다. 고강도 ceiling과 회복 여지를 읽는 기준으로 사용합니다.",
            }
        )
    if report.vlamax_mmol_l_s is not None:
        cards.append(
            {
                "title": "VLamax",
                "value": f"{_num(report.vlamax_mmol_l_s, 2)} mmol/L/s",
                "note": "해당 수치는 무산소 해당계 기여도를 요약합니다. 높을수록 스프린트/가속 쪽 강점이 있지만 장시간 경제성은 별도로 봐야 합니다.",
            }
        )
    if report.fatmax_watt is not None:
        cards.append(
            {
                "title": "FatMax",
                "value": _fmt_power(report.fatmax_watt),
                "note": "리포트가 제시한 지방산화 효율 중심 강도입니다. 장시간 지구력 세션 anchor로 가장 먼저 참고할 수 있습니다.",
            }
        )
    if report.at_abs_watt is not None:
        cards.append(
            {
                "title": "AT",
                "value": _fmt_power(report.at_abs_watt),
                "note": "INSCYD가 제시한 threshold anchor입니다. 실전 FTP나 훈련 중 지속 가능 강도와 반드시 같이 해석해야 합니다.",
            }
        )
    return cards


def build_widget_registry(
    parsed: ParsedInscydWorkspace,
    coaching_payload: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build renderable widgets with eligibility flags."""
    report = parsed.report
    coaching_payload = coaching_payload or {}
    focus_source = " ".join(
        [
            str(parsed.submission_context.get("description") or ""),
            str(parsed.submission_context.get("protocol_summary") or ""),
            str(parsed.submission_context.get("protocol_context", {}).get("primary_goal") or ""),
        ]
    )
    focus = _keyword_focus(focus_source)

    summary_cards = _build_interpretation_cards(parsed)
    fit_alignment = parsed.zwo_summary.get("fit_alignment") or []

    return {
        "key_metrics": {
            "eligible": bool(summary_cards),
            "cards": summary_cards,
            "focus": focus,
        },
        "coaching_overview": {
            "eligible": bool(coaching_payload.get("archetype", {}).get("summary")),
            "payload": coaching_payload,
            "focus": focus,
        },
        "training_directions": {
            "eligible": bool(coaching_payload.get("training_directions")),
            "payload": coaching_payload,
            "focus": focus,
        },
        "microcycle": {
            "eligible": bool(coaching_payload.get("microcycle")),
            "payload": coaching_payload,
            "focus": focus,
        },
        "training_zones": {
            "eligible": bool(report.training_zones),
            "zones": report.training_zones[:8],
            "commentary": coaching_payload.get("chart_commentary", {}).get("training_zones") or {},
            "focus": "threshold" if focus in {"threshold", "balanced"} else focus,
        },
        "test_rows": {
            "eligible": bool(report.test_data_rows),
            "rows": report.test_data_rows,
            "commentary": coaching_payload.get("chart_commentary", {}).get("test_rows") or {},
            "focus": "anaerobic" if focus == "anaerobic" else "balanced",
        },
        "fit_protocol": {
            "eligible": bool(parsed.fit_sessions),
            "sessions": parsed.fit_sessions,
            "focus": "threshold" if focus == "threshold" else "balanced",
        },
        "fit_alignment": {
            "eligible": bool(fit_alignment),
            "rows": fit_alignment,
            "focus": "threshold" if focus in {"threshold", "anaerobic"} else "balanced",
        },
        "zwo_protocol": {
            "eligible": bool(parsed.zwo_summary),
            "summary": parsed.zwo_summary,
            "focus": "balanced",
        },
        "warnings": {
            "eligible": bool(parsed.warnings),
            "warnings": parsed.warnings,
            "focus": "balanced",
        },
    }


def compile_report_plan(parsed: ParsedInscydWorkspace, registry: dict[str, dict[str, Any]]) -> list[str]:
    """Compile a deterministic widget order before tuning."""
    plan = [
        "key_metrics",
        "coaching_overview",
        "training_directions",
        "microcycle",
        "training_zones",
        "test_rows",
        "fit_alignment",
        "fit_protocol",
        "zwo_protocol",
        "warnings",
    ]
    return [widget_id for widget_id in plan if registry.get(widget_id, {}).get("eligible")]


def tune_report_plan(
    plan: list[str],
    parsed: ParsedInscydWorkspace,
    registry: dict[str, dict[str, Any]],
) -> list[str]:
    """Constrained tuning that reorders only known eligible widgets."""
    focus_source = " ".join(
        [
            str(parsed.submission_context.get("description") or ""),
            str(parsed.submission_context.get("protocol_summary") or ""),
        ]
    )
    focus = _keyword_focus(focus_source)
    tuned = list(plan)

    def move_front(widget_id: str) -> None:
        if widget_id in tuned:
            tuned.remove(widget_id)
            tuned.insert(0, widget_id)

    if focus == "fat":
        for widget_id in ("training_zones", "training_directions", "microcycle", "coaching_overview", "key_metrics"):
            move_front(widget_id)
    elif focus == "threshold":
        for widget_id in ("training_directions", "microcycle", "training_zones", "coaching_overview", "key_metrics"):
            move_front(widget_id)
    elif focus == "anaerobic":
        for widget_id in ("test_rows", "training_directions", "microcycle", "coaching_overview", "key_metrics"):
            move_front(widget_id)

    allowed = {widget_id for widget_id, widget in registry.items() if widget.get("eligible")}
    return [widget_id for widget_id in tuned if widget_id in allowed]


def _scale_width(value: Any, max_value: float | int | None) -> str:
    try:
        numeric = float(value)
        ceiling = float(max_value or 0)
    except (TypeError, ValueError):
        return "0%"
    if ceiling <= 0:
        return "0%"
    ratio = max(0.0, min(1.0, numeric / ceiling))
    return f"{ratio * 100:.1f}%"


def _render_power_bar(label: str, value: Any, max_value: float | int | None, tone: str = "teal") -> str:
    tones = {
        "teal": "linear-gradient(90deg, rgba(15,118,110,0.9), rgba(45,212,191,0.78))",
        "amber": "linear-gradient(90deg, rgba(217,119,6,0.92), rgba(251,191,36,0.82))",
        "slate": "linear-gradient(90deg, rgba(71,85,105,0.92), rgba(148,163,184,0.85))",
    }
    return f"""
    <div class="power-bar-row">
      <div class="power-bar-meta"><span>{_text(label)}</span><strong>{_fmt_power(value)}</strong></div>
      <div class="power-track"><div class="power-fill" style="width:{_scale_width(value, max_value)}; background:{tones.get(tone, tones['teal'])};"></div></div>
    </div>
    """


def _render_key_metrics(registry: dict[str, dict[str, Any]]) -> str:
    cards = registry["key_metrics"]["cards"]
    items = "".join(
        f"""
        <article class="metric-card">
          <div class="metric-label">{_text(card['title'])}</div>
          <div class="metric-value">{_text(card['value'])}</div>
          <p class="metric-note">{_text(card['note'])}</p>
        </article>
        """
        for card in cards
    )
    return f"""
    <section class="widget-card">
      <div class="widget-eyebrow">Reported Metrics</div>
      <h2>INSCYD가 제시한 핵심 지표</h2>
      <div class="metric-grid">{items}</div>
    </section>
    """


def _render_commentary_block(commentary: dict[str, Any], title: str = "Coach Read") -> str:
    headline = str(commentary.get("headline") or "").strip()
    notes = [str(note).strip() for note in (commentary.get("notes") or []) if str(note).strip()]
    if not headline and not notes:
        return ""
    items = "".join(f"<li>{_text(note)}</li>" for note in notes)
    return f"""
    <div class="commentary-card">
      <div class="commentary-title">{_text(title)}</div>
      {f'<p class=\"commentary-headline\">{_text(headline)}</p>' if headline else ''}
      {f'<ul class=\"commentary-list\">{items}</ul>' if items else ''}
    </div>
    """


def _render_coaching_overview(registry: dict[str, dict[str, Any]]) -> str:
    payload = registry["coaching_overview"]["payload"]
    archetype = payload.get("archetype") or {}
    strengths = archetype.get("strengths") or []
    limiters = archetype.get("limiters") or []
    evidence = archetype.get("evidence") or []
    strength_items = "".join(f"<li>{_text(item)}</li>" for item in strengths)
    limiter_items = "".join(f"<li>{_text(item)}</li>" for item in limiters)
    evidence_items = "".join(f"<li>{_text(item)}</li>" for item in evidence)
    confidence = str(payload.get("confidence") or "medium").upper()
    return f"""
    <section class="widget-card">
      <div class="widget-eyebrow">Coaching Overview</div>
      <div class="coaching-header">
        <div>
          <h2>현재 상태</h2>
          <p class="coaching-summary">{_text(archetype.get('summary') or '')}</p>
        </div>
        <span class="confidence-badge confidence-{_text(str(payload.get('confidence') or 'medium'))}">{_text(confidence)}</span>
      </div>
      <div class="overview-hero">
        <div class="overview-title">{_text(archetype.get('title') or '-')}</div>
        <p class="overview-brief">{_text(payload.get('coach_brief') or '')}</p>
      </div>
      <div class="coach-grid">
        <article class="coach-card">
          <div class="coach-card-title">강점</div>
          <ul class="coach-list">{strength_items or '<li>충분한 근거가 모이면 여기에 강점이 정리됩니다.</li>'}</ul>
        </article>
        <article class="coach-card">
          <div class="coach-card-title">보완 포인트</div>
          <ul class="coach-list">{limiter_items or '<li>뚜렷한 제한 요인은 크지 않지만 세부 목적에 따라 우선순위를 조정할 수 있습니다.</li>'}</ul>
        </article>
        <article class="coach-card">
          <div class="coach-card-title">근거 anchor</div>
          <ul class="coach-list">{evidence_items}</ul>
        </article>
      </div>
    </section>
    """


def _render_microcycle(registry: dict[str, dict[str, Any]]) -> str:
    payload = registry["microcycle"]["payload"]
    cards = "".join(
        f"""
        <article class="microcycle-card">
          <div class="microcycle-day">{_text(item.get('day') or '-')}</div>
          <div class="microcycle-title">{_text(item.get('title') or '-')}</div>
          <div class="microcycle-intent">{_text(item.get('intent') or '')}</div>
          <p class="microcycle-session">{_text(item.get('session') or '')}</p>
        </article>
        """
        for item in (payload.get("microcycle") or [])
    )
    return f"""
    <section class="widget-card">
      <div class="widget-eyebrow">Example Week</div>
      <h2>예시 주간 구성</h2>
      <p class="coaching-summary">지금 리포트의 training direction을 실제 훈련 블록으로 옮길 때 참고할 수 있는 간단한 microcycle 예시입니다.</p>
      <div class="microcycle-grid">{cards}</div>
    </section>
    """


def _render_training_directions(registry: dict[str, dict[str, Any]]) -> str:
    payload = registry["training_directions"]["payload"]
    cards = "".join(
        f"""
        <article class="direction-card">
          <div class="direction-head">
            <span class="direction-priority direction-{_text(direction.get('priority') or 'support')}">{_text(direction.get('priority') or 'support')}</span>
            <strong>{_text(direction.get('title') or '-')}</strong>
          </div>
          <p class="direction-why">{_text(direction.get('why') or '')}</p>
          <div class="direction-session">{_text(direction.get('session') or '')}</div>
        </article>
        """
        for direction in (payload.get("training_directions") or [])
    )
    return f"""
    <section class="widget-card">
      <div class="widget-eyebrow">Training Direction</div>
      <h2>향후 훈련 방향</h2>
      <div class="direction-grid">{cards}</div>
    </section>
    """


def _render_training_zones(registry: dict[str, dict[str, Any]]) -> str:
    zones = registry["training_zones"]["zones"]
    max_power = max([float(zone.get("upper_watt") or 0) for zone in zones], default=0)
    min_power = min([float(zone.get("lower_watt") or 0) for zone in zones], default=0)

    def range_row(zone: dict[str, Any]) -> str:
        low = float(zone.get("lower_watt") or 0)
        high = float(zone.get("upper_watt") or low)
        span = max(max_power - min_power, 1)
        left = ((low - min_power) / span) * 100
        width = max(((high - low) / span) * 100, 3)
        fat_pct = float(zone.get("fat_percent") or 0)
        cho_pct = float(zone.get("carbohydrate_percent") or 0)
        has_mix = fat_pct > 0 or cho_pct > 0
        mix_total = fat_pct + cho_pct if has_mix else 0
        fat_width = (fat_pct / mix_total * 100) if mix_total else 0
        cho_width = (cho_pct / mix_total * 100) if mix_total else 0
        mix_html = (
            f"""
            <div class="zone-mix-track">
              <div class="zone-mix-fat" style="width:{fat_width:.1f}%"></div>
              <div class="zone-mix-cho" style="width:{cho_width:.1f}%"></div>
            </div>
            <div class="zone-mix-labels">
              <span>Fat {_fmt_pct(fat_pct)}</span>
              <span>CHO {_fmt_pct(cho_pct)}</span>
            </div>
            """
            if has_mix
            else '<div class="zone-mix-empty">fuel mix unavailable</div>'
        )
        return f"""
        <article class="zone-range-card">
          <div class="zone-range-head">
            <div>
              <div class="zone-range-name">Zone { _text(zone.get('zone_number')) } · { _text(zone.get('name') or zone.get('code') or '-') }</div>
              <div class="zone-range-values">{ _fmt_power(low) } - { _fmt_power(high) }</div>
            </div>
            <div class="zone-range-target">target { _fmt_power(zone.get('target_watt') or high) }</div>
          </div>
          <div class="zone-range-track">
            <div class="zone-range-band" style="left:{left:.1f}%; width:{width:.1f}%"></div>
          </div>
          {mix_html}
        </article>
        """

    rows = "".join(
        f"""
        <tr>
          <td>{_text(zone.get('zone_number'))}</td>
          <td>{_text(zone.get('name') or zone.get('code') or '-')}</td>
          <td>{_fmt_power(zone.get('lower_watt'))} - {_fmt_power(zone.get('upper_watt'))}</td>
          <td>{_fmt_pct(zone.get('fat_percent'))}</td>
          <td>{_fmt_pct(zone.get('carbohydrate_percent'))}</td>
        </tr>
        """
        for zone in zones
    )
    range_cards = "".join(range_row(zone) for zone in zones)
    return f"""
    <section class="widget-card">
      <div class="widget-eyebrow">Zones</div>
      <h2>훈련 강도 구간 해석</h2>
      {_render_commentary_block(registry["training_zones"].get("commentary") or {}, "Zone Coach Note")}
      <div class="zone-range-grid">{range_cards}</div>
      <table class="data-table">
        <thead><tr><th>Zone</th><th>Name</th><th>Power</th><th>Fat %</th><th>CHO %</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _dedupe_effort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("type") or "").strip().lower(),
            int(row.get("duration_sec") or 0),
            str(row.get("average_power_watt") or row.get("reported_average_power_watt") or ""),
            str(row.get("fit_best_power_w") or ""),
            str(row.get("session") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _render_test_rows(registry: dict[str, dict[str, Any]]) -> str:
    rows_data = _dedupe_effort_rows(registry["test_rows"]["rows"])
    alignment_rows = _dedupe_effort_rows(registry.get("fit_alignment", {}).get("rows") or [])
    alignment_map = {
        (
            str(row.get("type") or "").strip().lower(),
            int(row.get("duration_sec") or 0),
            str(row.get("reported_average_power_watt") or ""),
        ): row
        for row in alignment_rows
    }

    compare_rows: list[dict[str, Any]] = []
    for row in rows_data:
        key = (
            str(row.get("type") or "").strip().lower(),
            int(row.get("duration_sec") or 0),
            str(row.get("average_power_watt") or ""),
        )
        aligned = alignment_map.get(key)
        compare_rows.append(
            {
                "type": row.get("type"),
                "duration_sec": row.get("duration_sec"),
                "reported_average_power_watt": row.get("average_power_watt"),
                "fit_best_power_w": aligned.get("fit_best_power_w") if aligned else None,
                "session": aligned.get("session") if aligned else None,
                "fit_session_count": aligned.get("fit_session_count") if aligned else 0,
                "delta_w": aligned.get("delta_w") if aligned else None,
                "additional_value": row.get("additional_value"),
            }
        )

    max_power = max(
        [
            max(float(row.get("reported_average_power_watt") or 0), float(row.get("fit_best_power_w") or 0))
            for row in compare_rows
        ],
        default=0,
    )
    rows = "".join(
        f"""
        <tr>
          <td>{_text(row.get('type'))}</td>
          <td>{_fmt_duration(row.get('duration_sec'))}</td>
          <td>{_fmt_power(row.get('reported_average_power_watt'))}</td>
          <td>{_fmt_power(row.get('fit_best_power_w'))}</td>
          <td>{_fmt_power(row.get('delta_w'))}</td>
        </tr>
        """
        for row in compare_rows
    )
    charts = ""
    for row in compare_rows:
        reported = row.get("reported_average_power_watt")
        fit_best = row.get("fit_best_power_w")
        has_fit = fit_best is not None
        left = _scale_width(reported, max_power)
        right = _scale_width(fit_best, max_power) if has_fit else left
        delta_label = f"Δ {_fmt_power(row.get('delta_w'))}" if has_fit else "FIT best unavailable"
        session_count = int(row.get("fit_session_count") or 0)
        source_label = (
            f"{session_count} uploaded FIT files"
            if session_count > 1
            else ("1 uploaded FIT file" if session_count == 1 else "reported only")
        )
        source_note = f"<div class=\"compare-source\">best source {_text(row.get('session'))}</div>" if row.get("session") else ""
        charts += f"""
        <div class="compare-card">
          <div class="compare-head">
            <span>{_text(row.get('type'))} · {_fmt_duration(row.get('duration_sec'))}</span>
            <strong>{_text(source_label)}</strong>
          </div>
          <div class="dumbbell-row">
            <div class="dumbbell-meta">
              <span>Reported {_fmt_power(reported)}</span>
              <span>{'FIT best ' + _fmt_power(fit_best) if has_fit else 'FIT best -'}</span>
            </div>
            <div class="dumbbell-track">
              <div class="dumbbell-line"></div>
              <div class="dumbbell-dot dumbbell-dot-left" style="left:{left}"></div>
              {f'<div class="dumbbell-dot dumbbell-dot-right" style="left:{right}"></div>' if has_fit else ''}
            </div>
            <div class="dumbbell-delta">{delta_label}</div>
            {source_note}
          </div>
        </div>
        """
    return f"""
    <section class="widget-card">
      <div class="widget-eyebrow">Protocol Evidence</div>
      <h2>Reported vs FIT best effort</h2>
      {_render_commentary_block(registry["test_rows"].get("commentary") or {}, "Effort Coach Note")}
      <div class="compare-grid">{charts}</div>
      <table class="data-table">
        <thead><tr><th>Type</th><th>Duration</th><th>PDF Avg</th><th>FIT Best</th><th>Delta</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def _render_fit_protocol(registry: dict[str, dict[str, Any]]) -> str:
    cards = "".join(
        f"""
        <article class="fit-card">
          <div class="fit-card-title">{_text(session['filename'])}</div>
          <div class="fit-card-meta">duration {_fmt_duration(session.get('duration_sec'))} · max {_fmt_power(session.get('max_power_w'))}</div>
          <div class="fit-card-meta">target ceiling {_fmt_power(session.get('max_target_power_w'))} · laps {_text(session.get('lap_count'))}</div>
        </article>
        """
        for session in registry["fit_protocol"]["sessions"]
    )
    return f"""
    <section class="widget-card">
      <div class="widget-eyebrow">FIT Evidence</div>
      <h2>실제 수행 파일에서 확인된 세션 개요</h2>
      <div class="fit-grid">{cards}</div>
    </section>
    """


def _render_fit_alignment(registry: dict[str, dict[str, Any]]) -> str:
    return ""


def _render_zwo_protocol(registry: dict[str, dict[str, Any]]) -> str:
    summary = registry["zwo_protocol"]["summary"]
    stage_types = summary.get("stage_types") or []
    return f"""
    <section class="widget-card">
      <div class="widget-eyebrow">Planned Protocol</div>
      <h2>프로토콜 설계 참고</h2>
      <div class="stacked-notes">
        <p><strong>{_text(summary.get('name') or summary.get('source') or 'Protocol')}</strong></p>
        <p>source: {_text(summary.get('source') or '-')}</p>
        <p>stages: {_text(summary.get('stage_count') or '-')} · duration: {_fmt_duration(summary.get('total_duration_sec'))}</p>
        {f"<p>stage types: {_text(', '.join(stage_types))}</p>" if stage_types else ""}
      </div>
    </section>
    """


def _render_warnings(registry: dict[str, dict[str, Any]]) -> str:
    items = "".join(f"<li>{_text(item)}</li>" for item in registry["warnings"]["warnings"])
    return f"""
    <section class="widget-card warning-card">
      <div class="widget-eyebrow">Warnings</div>
      <h2>파싱/해석 시 참고사항</h2>
      <ul class="warning-list">{items}</ul>
    </section>
    """


def _render_artifact_pages(context: dict[str, Any]) -> str:
    artifacts = context["report_data"].get("artifacts") or {}
    pages = artifacts.get("page_images") or []
    if not pages:
        return ""
    cards = "".join(
        f"""
        <article class="artifact-card">
          <div class="artifact-card-head">
            <span>Page {int(page.get('page') or 0)}</span>
            <a href="{_safe_href(str(page.get('url') or ''))}" target="_blank" rel="noreferrer">open image</a>
          </div>
          <img src="{_safe_href(str(page.get('url') or ''))}" alt="INSCYD page {int(page.get('page') or 0)}" loading="lazy" />
        </article>
        """
        for page in pages
    )
    return f"""
    <section class="widget-card">
      <div class="widget-eyebrow">Original Pages</div>
      <h2>원본 리포트 페이지 참조</h2>
      <div class="artifact-grid">{cards}</div>
    </section>
    """


def _build_report_artifacts(parsed: ParsedInscydWorkspace, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Any] = {
        "original_pdf_name": parsed.pdf_path.name,
        "original_pdf_file": None,
        "original_pdf_url": None,
        "page_images": [],
    }

    if parsed.pdf_path.is_file():
        pdf_name = "original-inscyd-report.pdf"
        target_pdf = output_dir / pdf_name
        shutil.copy2(parsed.pdf_path, target_pdf)
        artifacts["original_pdf_file"] = pdf_name
        artifacts["original_pdf_url"] = f"./{pdf_name}"

        pdftoppm = shutil.which("pdftoppm")
        if pdftoppm:
            try:
                from pypdf import PdfReader  # type: ignore

                page_count = len(PdfReader(str(parsed.pdf_path)).pages)
            except Exception:
                page_count = 0
            for page_number in range(1, min(page_count, 2) + 1):
                image_name = f"original-page-{page_number}.png"
                image_path = output_dir / image_name
                try:
                    subprocess.run(
                        [
                            pdftoppm,
                            "-png",
                            "-f",
                            str(page_number),
                            "-l",
                            str(page_number),
                            "-singlefile",
                            "-scale-to",
                            "1600",
                            str(parsed.pdf_path),
                            str(image_path.with_suffix("")),
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                except Exception:
                    continue
                if image_path.is_file():
                    artifacts["page_images"].append(
                        {
                            "page": page_number,
                            "file": image_name,
                            "url": f"./{image_name}",
                        }
                    )
    return artifacts


def render_html(context: dict[str, Any]) -> str:
    """Render the final modular INSCYD interpretation report."""
    registry = context["widget_registry"]
    plan = context["report_plan"]
    parsed = context["parsed"]

    renderers = {
        "key_metrics": lambda: _render_key_metrics(registry),
        "coaching_overview": lambda: _render_coaching_overview(registry),
        "training_directions": lambda: _render_training_directions(registry),
        "microcycle": lambda: _render_microcycle(registry),
        "training_zones": lambda: _render_training_zones(registry),
        "test_rows": lambda: _render_test_rows(registry),
        "fit_protocol": lambda: _render_fit_protocol(registry),
        "fit_alignment": lambda: _render_fit_alignment(registry),
        "zwo_protocol": lambda: _render_zwo_protocol(registry),
        "warnings": lambda: _render_warnings(registry),
    }
    sections = "\n".join(renderers[widget_id]() for widget_id in plan if widget_id in renderers)
    data_json = html.escape(json.dumps(context["report_data"], ensure_ascii=False))
    artifacts = context["report_data"].get("artifacts") or {}
    pdf_url = _safe_href(str(artifacts.get("original_pdf_url") or ""))
    pdf_name = _text(artifacts.get("original_pdf_name") or "INSCYD PDF")
    artifact_pages = _render_artifact_pages(context)
    pdf_actions = (
        f"""
        <div class="artifact-actions">
          <a class="artifact-button artifact-button-primary" href="{pdf_url}" target="_blank" rel="noreferrer">원본 PDF 열기</a>
          <a class="artifact-button" href="{pdf_url}" download="{pdf_name}">PDF 다운로드</a>
        </div>
        """
        if pdf_url
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_text(context['report_data']['subject']['name'])} — INSCYD Interpretation Report</title>
  <style>
    :root {{
      --bg: #f6f1e8;
      --paper: rgba(255,255,255,0.9);
      --ink: #1f2937;
      --muted: #6b7280;
      --accent-a: #d97706;
      --accent-b: #0f766e;
      --line: rgba(15, 23, 42, 0.08);
      --shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "SUIT", "Pretendard", -apple-system, BlinkMacSystemFont, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, rgba(245, 158, 11, 0.18), transparent 22%),
        radial-gradient(circle at top left, rgba(13, 148, 136, 0.12), transparent 18%),
        var(--bg);
    }}
    .page {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 40px 24px 72px;
    }}
    .hero {{
      padding: 28px 32px;
      border-radius: 32px;
      background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(255,255,255,0.78));
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
    }}
    .eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.18em;
      font-size: 12px;
      color: #9a3412;
      font-weight: 700;
    }}
    h1 {{
      margin: 14px 0 12px;
      font-size: clamp(34px, 6vw, 64px);
      line-height: 0.96;
      font-family: "Iowan Old Style", "Times New Roman", serif;
    }}
    .hero-grid {{
      display: grid;
      gap: 20px;
      grid-template-columns: 2fr 1fr;
      align-items: end;
    }}
    .hero-note, .meta-list, .lead-note, .stacked-notes p, .fit-card-meta, .warning-list li {{
      color: var(--muted);
      line-height: 1.7;
    }}
    .meta-panel {{
      padding: 18px 20px;
      border-radius: 24px;
      background: rgba(255,255,255,0.74);
      border: 1px solid var(--line);
    }}
    .meta-list {{
      display: grid;
      gap: 8px;
      font-size: 14px;
    }}
    .layout {{
      display: grid;
      gap: 18px;
      margin-top: 20px;
    }}
    .widget-card {{
      border-radius: 28px;
      background: var(--paper);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      padding: 24px;
    }}
    .widget-eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.16em;
      color: #9a3412;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 10px;
    }}
    h2 {{
      margin: 0 0 14px;
      font-family: "Iowan Old Style", "Times New Roman", serif;
      font-size: clamp(26px, 4vw, 38px);
    }}
    .metric-grid, .fit-grid, .microcycle-grid {{
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }}
    .coach-grid, .direction-grid {{
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    }}
    .metric-card, .fit-card {{
      border-radius: 22px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      padding: 18px;
    }}
    .coach-card, .direction-card, .commentary-card {{
      border-radius: 22px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      padding: 18px;
    }}
    .coaching-header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
      margin-bottom: 16px;
    }}
    .coaching-summary {{
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
    }}
    .overview-hero {{
      margin-bottom: 16px;
      padding: 16px 18px;
      border-radius: 22px;
      background: linear-gradient(135deg, rgba(15,118,110,0.10), rgba(217,119,6,0.12));
      border: 1px solid var(--line);
    }}
    .overview-title {{
      font-size: clamp(24px, 3vw, 34px);
      font-family: "Iowan Old Style", "Times New Roman", serif;
      font-weight: 700;
    }}
    .overview-brief {{
      margin: 10px 0 0;
      color: var(--muted);
      line-height: 1.75;
      max-width: 60ch;
    }}
    .coach-card-title, .commentary-title {{
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #9a3412;
      font-weight: 700;
      margin-bottom: 10px;
    }}
    .coach-list, .commentary-list {{
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
      line-height: 1.7;
    }}
    .commentary-card {{
      margin: 0 0 18px;
      background: rgba(248,250,252,0.84);
    }}
    .commentary-headline {{
      margin: 0 0 10px;
      font-weight: 700;
      line-height: 1.6;
    }}
    .direction-head {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }}
    .direction-priority, .confidence-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 28px;
      padding: 0 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .direction-primary, .confidence-high {{
      background: rgba(15,118,110,0.14);
      color: #0f766e;
    }}
    .direction-secondary, .confidence-medium {{
      background: rgba(217,119,6,0.14);
      color: #b45309;
    }}
    .direction-support, .direction-review, .confidence-low {{
      background: rgba(148,163,184,0.18);
      color: #475569;
    }}
    .direction-why {{
      margin: 0 0 12px;
      color: var(--muted);
      line-height: 1.7;
    }}
    .direction-session {{
      font-weight: 700;
      line-height: 1.6;
    }}
    .microcycle-card {{
      border-radius: 22px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      padding: 18px;
    }}
    .microcycle-day {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #9a3412;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .microcycle-title {{
      font-size: 20px;
      font-weight: 800;
      margin-bottom: 8px;
    }}
    .microcycle-intent {{
      color: #0f766e;
      font-weight: 700;
      margin-bottom: 10px;
    }}
    .microcycle-session {{
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
    }}
    .metric-label {{
      font-size: 14px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #9a3412;
      font-weight: 700;
    }}
    .metric-value {{
      margin-top: 10px;
      font-size: clamp(28px, 4vw, 42px);
      font-weight: 800;
      line-height: 1;
    }}
    .metric-note {{
      margin: 12px 0 0;
      color: var(--muted);
      line-height: 1.65;
    }}
    .power-bar-chart {{
      display: grid;
      gap: 12px;
      margin: 0 0 18px;
    }}
    .zone-range-grid {{
      display: grid;
      gap: 14px;
      margin: 0 0 22px;
    }}
    .zone-range-card {{
      border-radius: 22px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      padding: 16px 18px;
    }}
    .zone-range-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: baseline;
      margin-bottom: 12px;
    }}
    .zone-range-name {{
      font-size: 15px;
      font-weight: 700;
      color: var(--ink);
    }}
    .zone-range-values, .zone-range-target {{
      font-size: 14px;
      color: var(--muted);
    }}
    .zone-range-track {{
      position: relative;
      height: 14px;
      overflow: hidden;
      border-radius: 999px;
      background: linear-gradient(90deg, rgba(15,118,110,0.10), rgba(217,119,6,0.12));
      margin-bottom: 12px;
    }}
    .zone-range-band {{
      position: absolute;
      top: 0;
      bottom: 0;
      border-radius: inherit;
      background: linear-gradient(90deg, rgba(15,118,110,0.9), rgba(45,212,191,0.82));
      box-shadow: 0 8px 18px rgba(15,118,110,0.18);
    }}
    .zone-mix-track {{
      display: flex;
      height: 10px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(148,163,184,0.14);
    }}
    .zone-mix-fat {{
      background: linear-gradient(90deg, rgba(217,119,6,0.95), rgba(251,191,36,0.82));
    }}
    .zone-mix-cho {{
      background: linear-gradient(90deg, rgba(15,118,110,0.95), rgba(45,212,191,0.8));
    }}
    .zone-mix-labels {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-top: 8px;
      font-size: 13px;
      color: var(--muted);
    }}
    .zone-mix-empty {{
      margin-top: 8px;
      font-size: 13px;
      color: var(--muted);
    }}
    .power-bar-row {{
      display: grid;
      gap: 8px;
    }}
    .power-bar-meta {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      font-size: 14px;
      color: var(--muted);
    }}
    .power-bar-meta strong {{
      color: var(--ink);
      font-size: 15px;
    }}
    .power-track {{
      height: 12px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(148, 163, 184, 0.18);
    }}
    .power-fill {{
      height: 100%;
      border-radius: inherit;
    }}
    .compare-grid {{
      display: grid;
      gap: 14px;
      margin: 0 0 18px;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    }}
    .compare-card {{
      border-radius: 22px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      padding: 16px;
    }}
    .compare-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
      font-size: 14px;
    }}
    .effort-dot-card {{
      border-radius: 22px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      padding: 16px;
    }}
    .effort-dot-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
      font-size: 14px;
    }}
    .dumbbell-row {{
      display: grid;
      gap: 10px;
    }}
    .dumbbell-meta {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      font-size: 13px;
      color: var(--muted);
    }}
    .dumbbell-track {{
      position: relative;
      height: 28px;
    }}
    .dumbbell-line {{
      position: absolute;
      top: 50%;
      left: 0;
      right: 0;
      height: 4px;
      transform: translateY(-50%);
      border-radius: 999px;
      background: rgba(148,163,184,0.24);
    }}
    .dumbbell-dot {{
      position: absolute;
      top: 50%;
      width: 14px;
      height: 14px;
      margin-left: -7px;
      transform: translateY(-50%);
      border-radius: 999px;
      box-shadow: 0 6px 16px rgba(15,23,42,0.18);
    }}
    .dumbbell-dot-left {{
      background: linear-gradient(180deg, rgba(217,119,6,0.98), rgba(251,191,36,0.86));
    }}
    .dumbbell-dot-right {{
      background: linear-gradient(180deg, rgba(15,118,110,0.98), rgba(45,212,191,0.84));
    }}
    .dumbbell-delta {{
      font-size: 13px;
      color: var(--muted);
      text-align: right;
    }}
    .compare-source {{
      font-size: 12px;
      color: var(--muted);
      text-align: right;
    }}
    .data-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    .data-table th,
    .data-table td {{
      padding: 12px 10px;
      text-align: left;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    .data-table thead th {{
      color: #92400e;
      font-size: 12px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    .warning-card {{
      background: rgba(255, 251, 235, 0.9);
    }}
    .warning-list {{
      margin: 0;
      padding-left: 18px;
    }}
    .artifact-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 18px;
    }}
    .artifact-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      padding: 0 18px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.84);
      color: var(--ink);
      text-decoration: none;
      font-weight: 700;
    }}
    .artifact-button-primary {{
      background: linear-gradient(180deg, rgba(15,118,110,0.98), rgba(45,212,191,0.86));
      color: white;
      border-color: rgba(15,118,110,0.3);
    }}
    .artifact-grid {{
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    }}
    .artifact-card {{
      border-radius: 22px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      padding: 16px;
    }}
    .artifact-card-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
      font-size: 14px;
      color: var(--muted);
    }}
    .artifact-card-head a {{
      color: var(--accent-b);
      text-decoration: none;
      font-weight: 700;
    }}
    .artifact-card img {{
      width: 100%;
      display: block;
      border-radius: 16px;
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
    }}
    @media (max-width: 860px) {{
      .hero-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="eyebrow">INSCYD Interpretation</div>
      <div class="hero-grid">
        <div>
          <h1>{_text(context['report_data']['subject']['name'])}</h1>
          <div class="hero-note">INSCYD 결과와 함께 제출된 수행 파일을 기준으로 핵심 수치와 테스트 evidence를 정리했습니다.</div>
          {pdf_actions}
        </div>
        <aside class="meta-panel">
          <div class="meta-list">
            <div><strong>Method</strong> { _text(context['report_data']['meta']['analysis_method']) }</div>
            <div><strong>Sport</strong> { _text(parsed.report.sport or '-') }</div>
            <div><strong>Type</strong> { _text(parsed.report.test_type or '-') }</div>
            <div><strong>Date</strong> { _text(context['report_data']['session']['test_date'] or '-') }</div>
            <div><strong>Source PDF</strong> { _text(parsed.pdf_path.name) }</div>
          </div>
        </aside>
      </div>
    </section>
    <div class="layout">
      {sections}
      {artifact_pages}
    </div>
  </main>
  <script id="report-data" type="application/json">{data_json}</script>
</body>
</html>"""


def build_report_context(workspace: Path) -> dict[str, Any]:
    """Build report plan, metadata, and embedded report-data payload."""
    parsed = parse_inscyd_workspace(workspace)
    coaching_payload = build_coaching_payload(parsed)
    registry = build_widget_registry(parsed, coaching_payload)
    base_plan = compile_report_plan(parsed, registry)
    report_plan = tune_report_plan(base_plan, parsed, registry)
    report_data = {
        "meta": {
            "analysis_method": "INSCYD 해설 리포트",
            "report_type": "inscyd",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "subject": {
            "name": parsed.subject_name,
            "body_mass_kg": parsed.report.body_mass_kg,
            "body_height_cm": parsed.report.body_height_cm,
        },
        "session": {
            "test_date": parsed.test_date,
            "sport": parsed.report.sport,
            "test_type": parsed.report.test_type,
        },
        "inscyd": {
            "vo2max_rel_ml_kg_min": parsed.report.vo2max_rel_ml_kg_min,
            "vlamax_mmol_l_s": parsed.report.vlamax_mmol_l_s,
            "mfo_abs_kcal_h": parsed.report.mfo_abs_kcal_h,
            "fatmax_watt": parsed.report.fatmax_watt,
            "at_abs_watt": parsed.report.at_abs_watt,
            "training_zones": parsed.report.training_zones,
            "test_data_rows": parsed.report.test_data_rows,
            "weighted_regression": parsed.report.weighted_regression,
        },
        "protocol": {
            "description": parsed.submission_context.get("description") or "",
            "protocol_summary": parsed.submission_context.get("protocol_summary") or "",
            "protocol_context": parsed.submission_context.get("protocol_context") or {},
            "fit_sessions": parsed.fit_sessions,
            "zwo_summary": parsed.zwo_summary,
        },
        "coaching": coaching_payload,
        "report_plan": report_plan,
        "warnings": parsed.warnings,
        "artifacts": {},
    }
    return {
        "parsed": parsed,
        "widget_registry": registry,
        "report_plan": report_plan,
        "report_data": report_data,
    }


def generate_inscyd_report(workspace: Path, output_dir: Path) -> Path:
    """Generate an HTML interpretation report for an INSCYD workspace."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "index.html"
    context = build_report_context(workspace)
    context["report_data"]["artifacts"] = _build_report_artifacts(context["parsed"], output_dir)
    output_path.write_text(render_html(context), encoding="utf-8")
    return output_path
