"""
pipeline.combined_guidance — Cycling-specific guidance by combining CPET and CP model results.

Provides:
  - compute_combined_guidance(cpet_results, cp_model_result) → dict

References:
  Jones & Vanhatalo (2017): CP sits at ~95-110% of VT2 in trained cyclists.
  Coggan FTP convention: FTP ≈ CP in trained cyclists (within ~5%).
"""

from __future__ import annotations

from typing import Any

# Jones & Vanhatalo 2017 review: CP typically sits at ~95-110% of VT2
CP_VT2_RATIO_RANGE = (0.95, 1.10)
# Coggan FTP convention: FTP ≈ CP in trained cyclists (within ~5%)
CP_FTP_RATIO_RANGE = (1.00, 1.10)
# Physiological sanity: CP shouldn't exceed ~85% of peak sprint power
CP_PEAK_RATIO_RANGE = (0.60, 0.85)
# 10% tolerance for agreement classification
DISAGREEMENT_TOLERANCE_PCT = 0.10

# Disagreement table: (pair_name, numerator_anchor, denominator_anchor, expected_ratio_range)
_PAIRS = [
    ("cp_vs_vt2", "cp_w", "vt2_power_w", CP_VT2_RATIO_RANGE),
    ("cp_vs_ftp", "cp_w", "ftp_w", CP_FTP_RATIO_RANGE),
    ("cp_vs_peak", "cp_w", "peak_power_w", CP_PEAK_RATIO_RANGE),
]


def _extract_anchors(cpet_results: dict, cp_model_result: dict | None) -> dict:
    """Extract all anchor values from cpet and CP model results (no mutation)."""
    vt = cpet_results.get("ventilatory_thresholds", {})
    lactate = cpet_results.get("lactate", {})
    vo2max = cpet_results.get("vo2max", {})
    cpm = cpet_results.get("cpm_indices", {})

    vt2_power_w = vt.get("vt2_power_w")
    vt2_power_w = float(vt2_power_w) if vt2_power_w is not None else None

    lt1_power_w = lactate.get("lt1_dmax_power_w") or lactate.get("lt1_fixed_power_w")
    lt1_power_w = float(lt1_power_w) if lt1_power_w is not None else None

    peak_power_w = vo2max.get("peak_power_achieved_w")
    peak_power_w = float(peak_power_w) if peak_power_w is not None else None

    # ftp_w in cpm_indices is a CPM index dict: {"supported": True, "value": float, ...}
    ftp_entry = cpm.get("ftp_w")
    if isinstance(ftp_entry, dict) and ftp_entry.get("supported"):
        ftp_w = ftp_entry.get("value")
        ftp_w = float(ftp_w) if ftp_w is not None else None
    else:
        ftp_w = None

    cp_w = None
    w_prime_j = None
    if cp_model_result is not None and cp_model_result.get("status") == "computed":
        cp_raw = cp_model_result.get("cp_w")
        cp_w = float(cp_raw) if cp_raw is not None else None
        wp_raw = cp_model_result.get("w_prime_j")
        w_prime_j = float(wp_raw) if wp_raw is not None else None

    return {
        "cp_w": cp_w,
        "w_prime_j": w_prime_j,
        "vt2_power_w": vt2_power_w,
        "ftp_w": ftp_w,
        "lt1_power_w": lt1_power_w,
        "peak_power_w": peak_power_w,
    }


def _assess_cp_model_quality(cp_model_result: dict | None) -> str:
    """Return cp_model_quality: 'point' | 'band' | 'hidden' | 'missing'."""
    if cp_model_result is None:
        return "missing"
    if cp_model_result.get("status") != "computed":
        return "missing"
    suitability = cp_model_result.get("suitability", {})
    status = suitability.get("status", "hidden")
    if status in ("point", "band", "hidden"):
        return status
    return "hidden"


def _assess_cpet_quality(cpet_results: dict) -> str:
    """Return cpet_quality: 'high' | 'medium' | 'low'.

    Based on suitability dict: count keys where status == 'supported'.
    high if ≥70%, medium if ≥40%, low otherwise.
    """
    suitability = cpet_results.get("suitability", {})
    total = len(suitability)
    if total == 0:
        return "low"
    direct = sum(
        1 for v in suitability.values()
        if isinstance(v, dict) and v.get("status") == "supported"
    )
    ratio = direct / total
    if ratio >= 0.70:
        return "high"
    elif ratio >= 0.40:
        return "medium"
    return "low"


def _evaluate_disagreements(anchors: dict) -> list[dict]:
    """Evaluate each pair in _PAIRS and return a list of disagreement dicts."""
    results = []
    for pair_name, num_key, denom_key in [(p[0], p[1], p[2]) for p in _PAIRS]:
        expected_range = next(p[3] for p in _PAIRS if p[0] == pair_name)
        num_val = anchors.get(num_key)
        denom_val = anchors.get(denom_key)

        if num_val is None or denom_val is None or denom_val == 0:
            results.append({
                "pair": pair_name,
                "status": "abstain_missing",
                "ratio": None,
                "expected_range": list(expected_range),
                "note": f"{'numerator' if num_val is None else 'denominator'} anchor missing",
            })
            continue

        ratio = round(float(num_val) / float(denom_val), 4)
        lo, hi = expected_range
        # Use tolerance: agree if ratio is within expected_range bounds (±DISAGREEMENT_TOLERANCE_PCT)
        tol = DISAGREEMENT_TOLERANCE_PCT
        if (lo * (1 - tol)) <= ratio <= (hi * (1 + tol)):
            status = "agree"
            note = f"ratio {ratio:.3f} within expected [{lo}, {hi}]"
        else:
            status = "disagree"
            if ratio < lo * (1 - tol):
                note = f"ratio {ratio:.3f} below expected range [{lo}, {hi}]"
            else:
                note = f"ratio {ratio:.3f} above expected range [{lo}, {hi}]"

        results.append({
            "pair": pair_name,
            "status": status,
            "ratio": ratio,
            "expected_range": list(expected_range),
            "note": note,
        })
    return results


def _build_summary_card(
    status: str,
    anchors: dict,
    cpet_quality: str,
    cp_model_quality: str,
) -> dict:
    """Build a summary card dict for report rendering."""
    cp_w = anchors.get("cp_w")
    vt2_power_w = anchors.get("vt2_power_w")
    ftp_w = anchors.get("ftp_w")

    if status == "supported" and cp_w is not None:
        point_w = round(cp_w, 1)
        band_w = None
        label = "Critical Power (supported)"
    elif status == "low_confidence":
        point_w = None
        # band from non-None values of cp_w, vt2, ftp
        candidates = [v for v in [cp_w, vt2_power_w, ftp_w] if v is not None]
        band_w = [round(min(candidates), 1), round(max(candidates), 1)] if len(candidates) >= 2 else None
        label = "Functional Threshold Range (low confidence)"
    else:  # abstain
        point_w = None
        band_w = None
        label = "CPET-only (no CP model)"

    badges = []
    if cpet_quality == "high":
        badges.append("CPET: High Quality")
    elif cpet_quality == "medium":
        badges.append("CPET: Medium Quality")
    else:
        badges.append("CPET: Low Quality")

    if cp_model_quality == "point":
        badges.append("CP Model: Point Estimate")
    elif cp_model_quality == "band":
        badges.append("CP Model: Band Estimate")
    elif cp_model_quality == "hidden":
        badges.append("CP Model: Low Fit Quality")
    else:
        badges.append("CP Model: Not Available")

    if status == "supported":
        headline = f"CP confirmed at {point_w:.0f} W" if point_w is not None else "Critical Power supported"
    elif status == "low_confidence":
        if band_w is not None:
            headline = f"Threshold range {band_w[0]:.0f}–{band_w[1]:.0f} W (low confidence)"
        else:
            headline = "Threshold estimate unavailable (low confidence)"
    else:
        headline = "CPET analysis complete — no CP model fit available"

    return {
        "headline": headline,
        "point_w": point_w,
        "band_w": band_w,
        "label": label,
        "badges": badges,
    }


def _build_narrative(
    status: str,
    anchors: dict,
    disagreements: list[dict],
    cpet_quality: str,
    cp_model_quality: str,
) -> dict:
    """Build a narrative dict with headline, body, and warnings."""
    warnings: list[str] = []
    cp_w = anchors.get("cp_w")
    vt2_power_w = anchors.get("vt2_power_w")
    ftp_w = anchors.get("ftp_w")

    disagree_pairs = [d["pair"] for d in disagreements if d["status"] == "disagree"]

    if status == "supported":
        headline = "Critical Power and CPET thresholds are in agreement"
        body_parts = [
            f"The fitted Critical Power ({cp_w:.0f} W) is consistent with "
            "CPET-derived thresholds, providing high confidence in the cycling "
            "performance anchor."
        ]
        if vt2_power_w is not None:
            body_parts.append(
                f"VT2 at {vt2_power_w:.0f} W aligns with CP within the expected physiological range."
            )
    elif status == "low_confidence":
        headline = "CPET and CP model results show partial agreement"
        body_parts = [
            "Some disagreement was detected between the fitted Critical Power "
            "and CPET-derived thresholds. A performance range is provided "
            "rather than a point estimate."
        ]
        if disagree_pairs:
            body_parts.append(
                f"Disagreements found in: {', '.join(disagree_pairs)}."
            )
    else:  # abstain
        headline = "CPET analysis complete — Critical Power model not available"
        body_parts = [
            "No Critical Power fit was computed from FIT file workout history. "
            "CPET-derived thresholds (VT2, FTP proxy) are available for training guidance."
        ]
        if vt2_power_w is not None:
            body_parts.append(
                f"VT2 at {vt2_power_w:.0f} W can serve as the primary threshold anchor."
            )

    if cpet_quality == "low":
        warnings.append("CPET data quality is low — threshold estimates may be unreliable.")
    if cp_model_quality == "hidden":
        warnings.append("CP model R² below 0.80 — fit quality insufficient for point estimate.")
    for d in disagreements:
        if d["status"] == "disagree":
            warnings.append(f"Disagreement: {d['pair']} ratio {d['ratio']:.3f} — {d['note']}")

    return {
        "headline": headline,
        "body": " ".join(body_parts),
        "warnings": warnings,
    }


def compute_combined_guidance(
    cpet_results: dict[str, Any],
    cp_model_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute cycling-specific combined guidance from CPET and CP model results.

    This function is pure — it does not mutate either input dict.

    Args:
        cpet_results: The ``all_results`` dict from ``run_analysis()``.
            Expected keys: ``ventilatory_thresholds``, ``lactate``, ``vo2max``,
            ``cpm_indices``, ``suitability``.
        cp_model_result: The dict returned by ``compute_cp_model()``, or None.
            Expected keys: ``status``, ``cp_w``, ``w_prime_j``, ``suitability``.

    Returns:
        A dict conforming to the combined guidance payload schema.
        Always returns a valid payload — gracefully degrades when CP model
        is missing or abstained.
    """
    # Extract anchors (read-only, no mutation)
    anchors = _extract_anchors(cpet_results, cp_model_result)

    # Quality assessments
    cpet_quality = _assess_cpet_quality(cpet_results)
    cp_model_quality = _assess_cp_model_quality(cp_model_result)

    # Disagreement evaluation
    disagreements = _evaluate_disagreements(anchors)

    # Confidence counts
    agree_count = sum(1 for d in disagreements if d["status"] == "agree")
    disagree_count = sum(1 for d in disagreements if d["status"] == "disagree")
    total_pairs = len(disagreements)

    # Status decision logic
    cp_available = (
        cp_model_result is not None
        and cp_model_result.get("status") == "computed"
    )

    if not cp_available:
        status = "abstain"
    elif agree_count == 0:
        # Vacuous agreement (all pairs are abstain_missing) — no real evidence
        status = "abstain"
    elif (
        disagree_count == 0
        and cp_model_quality in ("point", "band")
        and cpet_quality != "low"
    ):
        status = "supported"
    else:
        status = "low_confidence"

    # Majority disagree override
    if cp_available and disagree_count > agree_count and cp_model_quality != "hidden":
        status = "abstain"

    # Build output sub-sections
    summary_card = _build_summary_card(status, anchors, cpet_quality, cp_model_quality)
    narrative = _build_narrative(status, anchors, disagreements, cpet_quality, cp_model_quality)

    return {
        "status": status,
        "anchors": {
            "cp_w": round(anchors["cp_w"], 2) if anchors["cp_w"] is not None else None,
            "w_prime_j": round(anchors["w_prime_j"], 2) if anchors["w_prime_j"] is not None else None,
            "vt2_power_w": round(anchors["vt2_power_w"], 2) if anchors["vt2_power_w"] is not None else None,
            "ftp_w": round(anchors["ftp_w"], 2) if anchors["ftp_w"] is not None else None,
            "lt1_power_w": round(anchors["lt1_power_w"], 2) if anchors["lt1_power_w"] is not None else None,
            "peak_power_w": round(anchors["peak_power_w"], 2) if anchors["peak_power_w"] is not None else None,
        },
        "disagreements": disagreements,
        "confidence": {
            "cpet_quality": cpet_quality,
            "cp_model_quality": cp_model_quality,
            "agreement_count": agree_count,
            "total_pairs": total_pairs,
        },
        "summary_card": summary_card,
        "narrative": narrative,
        "version": "1",
    }
