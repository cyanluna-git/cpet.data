"""
server.protocol_context — helpers for structured CPET upload context.
"""

from __future__ import annotations

from typing import Any


PRIMARY_GOAL_LABELS = {
    "fatmax": "FatMax 중심 평가",
    "thresholds": "LT1/LT2 중심 평가",
    "vo2max": "VO2max 중심 평가",
    "ftp_check": "FTP/현장 강도 비교",
    "mixed": "복합 대사 프로파일 확인",
    "other": "기타 목적",
}

TARGET_OUTPUT_LABELS = {
    "fatmax": "FatMax",
    "vo2max": "VO2max",
    "lt1": "LT1",
    "lt2": "LT2",
    "ftp": "FTP 비교",
    "clearance": "Lactate clearance",
    "economy": "Efficiency/Economy",
}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        text = _clean_text(value)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _normalize_block_intents(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []

    cleaned: list[dict[str, str]] = []
    for idx, value in enumerate(values, start=1):
        if isinstance(value, dict):
            label = _clean_text(value.get("label")) or f"블럭 {idx}"
            intent = _clean_text(value.get("intent"))
        else:
            label = f"블럭 {idx}"
            intent = _clean_text(value)

        if not intent:
            continue
        cleaned.append({"label": label, "intent": intent})
    return cleaned


def normalize_protocol_context(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize partial form input into a stable payload shape."""
    raw = raw or {}

    context = {
        "primary_goal": _clean_text(raw.get("primary_goal")),
        "fasting_hours": _clean_text(raw.get("fasting_hours")),
        "meal_state": _clean_text(raw.get("meal_state")),
        "caffeine_state": _clean_text(raw.get("caffeine_state")),
        "prior_training_state": _clean_text(raw.get("prior_training_state")),
        "protocol_outline": _clean_text(raw.get("protocol_outline")),
        "block_intents": _normalize_block_intents(raw.get("block_intents")),
        "target_outputs": _clean_list(raw.get("target_outputs")),
        "operator_notes": _clean_text(raw.get("operator_notes")),
    }

    return context


def has_protocol_context(context: dict[str, Any] | None) -> bool:
    """Return True when protocol context contains meaningful operator input."""
    context = normalize_protocol_context(context)
    return any(
        (
            context["primary_goal"],
            context["fasting_hours"],
            context["meal_state"],
            context["caffeine_state"],
            context["prior_training_state"],
            context["protocol_outline"],
            context["block_intents"],
            context["target_outputs"],
            context["operator_notes"],
        )
    )


def _goal_text(primary_goal: str) -> str:
    if not primary_goal:
        return ""
    return PRIMARY_GOAL_LABELS.get(primary_goal, primary_goal)


def _target_text(target_outputs: list[str]) -> str:
    labels = [TARGET_OUTPUT_LABELS.get(item, item) for item in target_outputs]
    return ", ".join(labels)


def compose_claude_protocol_summary(context: dict[str, Any] | None) -> str:
    """Compose a concise Korean narrative for Claude from normalized context."""
    context = normalize_protocol_context(context)
    if not has_protocol_context(context):
        return ""

    parts: list[str] = []

    goal = _goal_text(context["primary_goal"])
    if goal:
        parts.append(f"주요 검사 목적은 {goal}입니다.")

    pretest_bits: list[str] = []
    if context["fasting_hours"]:
        pretest_bits.append(f"공복 {context['fasting_hours']}시간")
    if context["meal_state"]:
        pretest_bits.append(f"식사 상태는 {context['meal_state']}")
    if context["caffeine_state"]:
        pretest_bits.append(f"카페인 상태는 {context['caffeine_state']}")
    if context["prior_training_state"]:
        pretest_bits.append(f"직전 운동 상태는 {context['prior_training_state']}")
    if pretest_bits:
        parts.append("검사 전 상태는 " + ", ".join(pretest_bits) + "입니다.")

    if context["protocol_outline"]:
        parts.append(f"프로토콜 개요는 {context['protocol_outline']} 입니다.")

    if context["block_intents"]:
        block_text = "; ".join(
            f"{item['label']}: {item['intent']}" for item in context["block_intents"]
        )
        parts.append(f"블럭별 의도는 {block_text} 입니다.")

    targets = _target_text(context["target_outputs"])
    if targets:
        parts.append(f"특히 확인하고 싶은 출력은 {targets} 입니다.")

    if context["operator_notes"]:
        parts.append(f"추가 메모: {context['operator_notes']}")

    return " ".join(parts).strip()


def build_protocol_intent_summary(context: dict[str, Any] | None) -> str:
    """Return a compact operator-facing one-line summary."""
    context = normalize_protocol_context(context)
    if not has_protocol_context(context):
        return ""

    pieces: list[str] = []
    goal = _goal_text(context["primary_goal"])
    if goal:
        pieces.append(goal)
    if context["fasting_hours"]:
        pieces.append(f"공복 {context['fasting_hours']}h")

    targets = _target_text(context["target_outputs"])
    if targets:
        pieces.append(targets)

    if context["block_intents"]:
        pieces.append(
            " / ".join(item["intent"] for item in context["block_intents"][:2])
        )
    elif context["protocol_outline"]:
        pieces.append(context["protocol_outline"])

    return " · ".join(piece for piece in pieces if piece)
