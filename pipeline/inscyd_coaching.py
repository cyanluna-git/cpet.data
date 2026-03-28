"""Deterministic coaching payloads for INSCYD interpretation reports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pipeline.inscyd_workspace import ParsedInscydWorkspace


def _fmt_power(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}W"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.0f}%"


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _aerobic_tier(vo2max_rel: float | None) -> tuple[str, str]:
    if vo2max_rel is None:
        return "unknown", "VO2max 근거가 부족합니다."
    if vo2max_rel >= 65:
        return "very_high", "유산소 ceiling은 매우 높은 편입니다."
    if vo2max_rel >= 55:
        return "high", "유산소 ceiling은 강한 편입니다."
    if vo2max_rel >= 45:
        return "moderate", "유산소 ceiling은 중간 이상입니다."
    return "developing", "유산소 ceiling은 아직 더 올릴 여지가 큽니다."


def _anaerobic_tier(vlamax: float | None) -> tuple[str, str]:
    if vlamax is None:
        return "unknown", "VLamax 근거가 부족합니다."
    if vlamax >= 0.70:
        return "high", "무산소 기여와 가속 성향이 큰 편입니다."
    if vlamax >= 0.50:
        return "balanced_high", "무산소 punch가 분명한 올라운더 쪽입니다."
    if vlamax >= 0.35:
        return "balanced_low", "무산소 기여는 중간 수준입니다."
    return "low", "무산소 punch보다 지속 효율 쪽 특성이 강합니다."


def _fat_support_tier(fatmax_watt: float | None, at_watt: float | None) -> tuple[str, str, float | None]:
    if fatmax_watt is None or at_watt in (None, 0):
        return "unknown", "FatMax/AT 비율을 계산할 근거가 부족합니다.", None
    ratio = fatmax_watt / at_watt
    if ratio >= 0.70:
        return "high", "FatMax가 threshold 대비 높아 장시간 지구력 기반이 안정적입니다.", ratio
    if ratio >= 0.60:
        return "moderate", "FatMax는 실전 지구력 anchor로 쓸 수 있지만 더 올릴 여지가 있습니다.", ratio
    return "low", "FatMax가 threshold 대비 낮아 장시간 효율 개선 여지가 큽니다.", ratio


def _alignment_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "coverage": "low",
            "short_ratio": None,
            "long_ratio": None,
            "headline": "업로드된 FIT 근거가 없어 수행 대조는 제한적입니다.",
            "notes": ["FIT evidence가 없어서 reported metric 중심으로 해석합니다."],
        }

    short_ratios: list[float] = []
    long_ratios: list[float] = []
    for row in rows:
        reported = row.get("reported_average_power_watt")
        fit_best = row.get("fit_best_power_w")
        duration = int(row.get("duration_sec") or 0)
        try:
            if reported in (None, 0) or fit_best is None:
                continue
            ratio = float(fit_best) / float(reported)
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if duration <= 30:
            short_ratios.append(ratio)
        elif duration >= 150:
            long_ratios.append(ratio)

    short_ratio = _mean(short_ratios)
    long_ratio = _mean(long_ratios)
    coverage_count = len(short_ratios) + len(long_ratios)
    if coverage_count >= 3:
        coverage = "high"
    elif coverage_count >= 1:
        coverage = "medium"
    else:
        coverage = "low"

    notes: list[str] = []
    if short_ratio is not None:
        if short_ratio >= 1.05:
            notes.append("짧은 all-out 파워는 업로드된 FIT 근거에서 더 강하게 확인됩니다.")
        elif short_ratio <= 0.90:
            notes.append("짧은 sprint power는 reported 값 대비 FIT 근거가 낮습니다.")
        else:
            notes.append("짧은 all-out 파워는 reported 값과 대체로 유사합니다.")
    if long_ratio is not None:
        if long_ratio >= 1.00:
            notes.append("3-8분 구간은 reported 수치와 잘 맞거나 조금 더 좋게 재현됩니다.")
        elif long_ratio >= 0.90:
            notes.append("3-8분 구간은 reported 수치를 거의 재현합니다.")
        else:
            notes.append("3-8분 구간은 uploaded FIT에서 reported 수치보다 낮게 나타납니다.")
    if not notes:
        notes.append("FIT 비교 근거가 제한적이어서 reported metric 중심으로 읽는 편이 안전합니다.")

    if coverage == "high":
        headline = "업로드된 FIT 근거는 비교적 충분합니다."
    elif coverage == "medium":
        headline = "업로드된 FIT 근거는 일부 duration만 뒷받침합니다."
    else:
        headline = "FIT 근거가 제한적이라 수행 비교 신뢰도는 높지 않습니다."

    return {
        "coverage": coverage,
        "short_ratio": short_ratio,
        "long_ratio": long_ratio,
        "headline": headline,
        "notes": notes,
    }


def _athlete_archetype(aerobic: str, anaerobic: str, fat_support: str) -> tuple[str, str]:
    if aerobic in {"high", "very_high"} and fat_support == "high" and anaerobic in {"low", "balanced_low"}:
        return "지구력 중심형", "긴 지구력과 경제성 기반이 강한 프로파일입니다."
    if aerobic in {"high", "very_high"} and anaerobic in {"balanced_high", "high"}:
        return "올라운더형", "유산소 ceiling과 무산소 punch가 함께 보이는 복합형입니다."
    if anaerobic == "high" and aerobic in {"moderate", "developing"}:
        return "스프린트 편향형", "짧은 가속과 punch가 돋보이고 장시간 효율은 따로 관리가 필요합니다."
    return "균형 개발형", "여러 에너지 시스템이 함께 보이며 우선순위를 두고 다듬을 여지가 있습니다."


def _build_training_directions(
    report: Any,
    focus: str,
    fat_support: str,
    alignment: dict[str, Any],
    aerobic: str,
    anaerobic: str,
) -> list[dict[str, str]]:
    directions: list[dict[str, str]] = []

    if fat_support in {"low", "moderate"} or focus == "fat":
        directions.append(
            {
                "priority": "primary",
                "title": "FatMax / base economy 확장",
                "why": "FatMax anchor를 더 안정적으로 쓰기 위해 zone 2 전후의 지방 대사 기반을 키우는 편이 좋습니다.",
                "session": f"{_fmt_power(report.fatmax_watt)} 전후로 60-120분 steady ride, 후반부 cadence와 nutrition 반응까지 같이 점검합니다.",
            }
        )

    if report.at_abs_watt is not None:
        directions.append(
            {
                "priority": "secondary" if directions else "primary",
                "title": "Threshold support 정리",
                "why": "AT 근처 지속 능력은 실전 페이스와 직접 연결되므로 주간 기준 anchor로 유지할 가치가 큽니다.",
                "session": f"{_fmt_power(max((report.at_abs_watt or 0) - 10, 0))} - {_fmt_power(report.at_abs_watt)} 범위에서 2 x 16-20min 또는 3 x 10-12min.",
            }
        )

    if anaerobic in {"high", "balanced_high"}:
        directions.append(
            {
                "priority": "support",
                "title": "무산소 punch는 유지, 과잉 비중은 제한",
                "why": "VLamax가 이미 분명해 짧은 강점은 살리되, 전체 블록의 대부분을 여기에 쓰는 것은 비효율적일 수 있습니다.",
                "session": "주 1회 8-12초 sprint 4-6회 정도로 sharpness만 유지하고, 나머지 고강도는 threshold 또는 VO2 쪽으로 배분합니다.",
            }
        )
    elif anaerobic == "low":
        directions.append(
            {
                "priority": "support",
                "title": "짧은 가속 반응 보강",
                "why": "무산소 punch가 낮은 편이면 레이스 가속이나 언덕 출구 가속에서 손해를 볼 수 있습니다.",
                "session": "완전 회복을 두고 8-10초 standing sprint 4-6회, 또는 30초 punch 인터벌을 소량 추가합니다.",
            }
        )

    if alignment["coverage"] == "low":
        directions.append(
            {
                "priority": "review",
                "title": "다음 업로드에서는 FIT 근거를 더 확보",
                "why": "코칭 추천은 가능하지만 실제 수행 근거가 부족하면 confidence가 낮아집니다.",
                "session": "20초, 3분, 8분 effort를 각각 담은 FIT를 모두 함께 남기면 다음 해석이 더 정확해집니다.",
            }
        )
    elif alignment["long_ratio"] is not None and alignment["long_ratio"] < 0.90:
        directions.append(
            {
                "priority": "review",
                "title": "reported endurance와 실제 수행 재현 차이 점검",
                "why": "3-8분 구간 FIT가 reported보다 낮으면 이번 업로드만으로는 long effort 재현도가 충분하지 않을 수 있습니다.",
                "session": "컨디션이 비슷한 날 3분/8분 effort를 다시 수집해 reported metric과의 차이를 재확인합니다.",
            }
        )

    return directions[:4]


def _build_coach_brief(
    archetype_title: str,
    focus: str,
    confidence: str,
    alignment: dict[str, Any],
    fat_support: str,
    anaerobic: str,
) -> str:
    if focus == "fat":
        core = "이번 블록은 threshold를 억지로 끌어올리기보다 FatMax와 base economy를 먼저 넓히는 편이 맞습니다."
    elif focus == "threshold":
        core = "지금은 endurance 기반을 유지하면서 threshold 지속 능력을 깔끔하게 올리는 블록이 가장 효율적입니다."
    elif focus == "anaerobic":
        core = "무산소 punch를 살리되, 전체 블록은 sprint 유지 + threshold support 균형으로 가져가는 편이 좋습니다."
    else:
        core = "지금 프로파일은 한쪽만 과하게 밀기보다 endurance와 threshold를 함께 정리하는 올라운드 블록이 어울립니다."

    if fat_support == "low":
        core += " 특히 장시간 효율 쪽은 다음 단계에서 가장 큰 체감 개선을 줄 가능성이 큽니다."
    if anaerobic == "high":
        core += " 짧은 punch는 이미 강점이라 유지 볼륨만 남겨도 됩니다."
    if confidence == "low":
        core += " 다만 uploaded FIT 근거가 약해 이번 제안은 review 성격으로 보는 편이 안전합니다."
    elif alignment["coverage"] == "high":
        core += " uploaded FIT 비교 근거도 있어 추천 신뢰도는 비교적 괜찮습니다."

    return f"{archetype_title} 기준으로 보면, {core}"


def _build_example_microcycle(
    report: Any,
    focus: str,
    confidence: str,
    anaerobic: str,
    fat_support: str,
) -> list[dict[str, str]]:
    if confidence == "low":
        return []

    fat_anchor = _fmt_power(report.fatmax_watt)
    at_anchor = _fmt_power(report.at_abs_watt)
    at_minus = _fmt_power(max((report.at_abs_watt or 0) - 10, 0))
    sprint_text = "8-12초 all-out sprint 4-6회, 완전 회복"
    threshold_text = f"{at_minus} - {at_anchor} 범위 2 x 16-20min"
    endurance_text = f"{fat_anchor} 전후 75-120분 steady ride"
    recovery_text = "아주 가볍게 45-60분 또는 완전 휴식"
    long_text = f"{fat_anchor} 전후로 2-3시간 long endurance"

    if focus == "fat":
        return [
            {"day": "Day 1", "title": "Base Economy", "intent": "지방 대사 기반 확장", "session": endurance_text},
            {"day": "Day 2", "title": "Recovery / Mobility", "intent": "피로 정리", "session": recovery_text},
            {"day": "Day 3", "title": "Threshold Support", "intent": "지속 강도 유지", "session": threshold_text},
            {"day": "Day 4", "title": "Long Ride", "intent": "지구력 anchor 고정", "session": long_text},
        ]
    if focus == "threshold":
        return [
            {"day": "Day 1", "title": "Threshold Main", "intent": "실전 지속 강도 향상", "session": threshold_text},
            {"day": "Day 2", "title": "Recovery / Easy", "intent": "고강도 회복", "session": recovery_text},
            {"day": "Day 3", "title": "Endurance Support", "intent": "threshold 아래 aerobic support", "session": endurance_text},
            {"day": "Day 4", "title": "Maintenance Punch", "intent": "짧은 sharpness 유지", "session": sprint_text if anaerobic in {'high', 'balanced_high'} else "30초 punch 4-6회, 긴 회복"},
        ]
    if focus == "anaerobic":
        return [
            {"day": "Day 1", "title": "Neuromuscular Sprint", "intent": "짧은 punch 유지", "session": sprint_text},
            {"day": "Day 2", "title": "Endurance Reset", "intent": "기반 유지", "session": endurance_text},
            {"day": "Day 3", "title": "Threshold Support", "intent": "지속 능력 보완", "session": threshold_text},
            {"day": "Day 4", "title": "Recovery / Easy", "intent": "과부하 누적 방지", "session": recovery_text},
        ]

    support_long = long_text if fat_support in {"high", "moderate"} else endurance_text
    return [
        {"day": "Day 1", "title": "Endurance Main", "intent": "기반 체력 유지/확장", "session": support_long},
        {"day": "Day 2", "title": "Threshold Main", "intent": "지속 강도 정리", "session": threshold_text},
        {"day": "Day 3", "title": "Recovery / Easy", "intent": "회복과 다음 질세션 준비", "session": recovery_text},
        {"day": "Day 4", "title": "Top-end Maintenance", "intent": "짧은 반응성 유지", "session": sprint_text if anaerobic in {'high', 'balanced_high'} else "1-2분 VO2 style effort 4-5회"},
    ]


def build_coaching_payload(parsed: ParsedInscydWorkspace) -> dict[str, Any]:
    report = parsed.report
    focus_source = " ".join(
        [
            str(parsed.submission_context.get("description") or ""),
            str(parsed.submission_context.get("protocol_summary") or ""),
            str(parsed.submission_context.get("protocol_context", {}).get("primary_goal") or ""),
        ]
    ).lower()
    focus = "balanced"
    if any(token in focus_source for token in ("fat", "지방", "fatmax")):
        focus = "fat"
    elif any(token in focus_source for token in ("threshold", "ftp", "역치", "at")):
        focus = "threshold"
    elif any(token in focus_source for token in ("vlamax", "무산소", "스프린트")):
        focus = "anaerobic"

    alignment_rows = parsed.zwo_summary.get("fit_alignment") or []
    alignment = _alignment_summary(alignment_rows)
    aerobic_tier, aerobic_note = _aerobic_tier(report.vo2max_rel_ml_kg_min)
    anaerobic_tier, anaerobic_note = _anaerobic_tier(report.vlamax_mmol_l_s)
    fat_support_tier, fat_support_note, fat_ratio = _fat_support_tier(report.fatmax_watt, report.at_abs_watt)
    archetype_title, archetype_summary = _athlete_archetype(aerobic_tier, anaerobic_tier, fat_support_tier)

    confidence = "medium"
    if alignment["coverage"] == "low":
        confidence = "low"
    elif alignment["coverage"] == "high":
        ratios = [value for value in (alignment["short_ratio"], alignment["long_ratio"]) if value is not None]
        if ratios and min(ratios) >= 0.90:
            confidence = "high"
        else:
            confidence = "medium"

    strengths: list[str] = []
    limiters: list[str] = []

    if aerobic_tier in {"high", "very_high"}:
        strengths.append(aerobic_note)
    else:
        limiters.append(aerobic_note)

    if fat_support_tier == "high":
        strengths.append(fat_support_note)
    elif fat_support_tier in {"low", "moderate"}:
        limiters.append(fat_support_note)

    if anaerobic_tier in {"high", "balanced_high"}:
        strengths.append(anaerobic_note)
    elif anaerobic_tier == "low":
        limiters.append("짧은 가속/스프린트 punch는 상대적으로 약할 수 있습니다.")
    else:
        strengths.append(anaerobic_note)

    zone_headline = "zone 2-3 전환부에서 지방/탄수화물 분담을 읽으며 endurance와 threshold 사이의 연결을 보는 편이 좋습니다."
    if fat_ratio is not None:
        if fat_ratio >= 0.70:
            zone_headline = "FatMax가 threshold 대비 높아 지구력 세션 anchor는 비교적 명확합니다."
        elif fat_ratio >= 0.60:
            zone_headline = "FatMax는 usable하지만 threshold 대비 간격이 커서 base economy를 더 다듬을 여지가 있습니다."
        else:
            zone_headline = "Threshold 대비 FatMax 위치가 낮아 장시간 효율 개선이 다음 블록의 우선 과제입니다."
    zone_notes = [
        f"FatMax anchor는 {_fmt_power(report.fatmax_watt)}이고 AT는 {_fmt_power(report.at_abs_watt)}입니다.",
        "medio 이후 CHO 비중이 빠르게 높아지면 threshold 전후 훈련의 연료 의존도 관리가 중요합니다.",
    ]
    if parsed.report.training_zones:
        first_zone = parsed.report.training_zones[0]
        zone_notes.append(
            f"가장 낮은 zone의 지방 기여는 {_fmt_pct(first_zone.get('fat_percent'))} 수준으로 시작합니다."
        )

    effort_headline = alignment["headline"]
    effort_notes = list(alignment["notes"])
    if alignment["short_ratio"] is not None and alignment["long_ratio"] is not None:
        effort_notes.append(
            "짧은 effort와 3-8분 effort를 같이 보면, punch와 sustained power가 같은 방향으로 움직이는지 확인할 수 있습니다."
        )

    training_directions = _build_training_directions(
        report=report,
        focus=focus,
        fat_support=fat_support_tier,
        alignment=alignment,
        aerobic=aerobic_tier,
        anaerobic=anaerobic_tier,
    )
    microcycle = _build_example_microcycle(
        report=report,
        focus=focus,
        confidence=confidence,
        anaerobic=anaerobic_tier,
        fat_support=fat_support_tier,
    )
    coach_brief = _build_coach_brief(
        archetype_title=archetype_title,
        focus=focus,
        confidence=confidence,
        alignment=alignment,
        fat_support=fat_support_tier,
        anaerobic=anaerobic_tier,
    )

    return {
        "focus": focus,
        "confidence": confidence,
        "coach_brief": coach_brief,
        "archetype": {
            "title": archetype_title,
            "summary": archetype_summary,
            "strengths": strengths[:3],
            "limiters": limiters[:3],
            "evidence": [
                f"VO2max {report.vo2max_rel_ml_kg_min:.1f} mL/kg/min" if report.vo2max_rel_ml_kg_min is not None else "VO2max -",
                f"VLamax {report.vlamax_mmol_l_s:.2f} mmol/L/s" if report.vlamax_mmol_l_s is not None else "VLamax -",
                f"FatMax/AT ratio {fat_ratio:.2f}" if fat_ratio is not None else "FatMax/AT ratio -",
            ],
        },
        "chart_commentary": {
            "training_zones": {
                "headline": zone_headline,
                "notes": zone_notes,
            },
            "test_rows": {
                "headline": effort_headline,
                "notes": effort_notes,
            },
        },
        "training_directions": training_directions,
        "microcycle": microcycle,
        "alignment": alignment,
    }
