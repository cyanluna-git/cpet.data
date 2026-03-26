"""
pipeline.analysis — Analysis algorithms for CPET data.

Computes all derivable metrics from the unified SQLite database:
lactate thresholds, VO2max, ventilatory thresholds, substrate utilization,
efficiency, heart rate analysis, and training zones.

No hardcoded paths; db_path is passed as a parameter.

Canonical source: analysis/analysis.py (identical in both subjects)
"""

import json as _json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator


def load_data(db_path: Path) -> dict[str, pd.DataFrame]:
    """Load all tables from SQLite into DataFrames.

    Args:
        db_path: Path to the analysis.db file.

    Returns:
        Dict mapping table name to DataFrame.
    """
    conn = sqlite3.connect(str(db_path))
    tables = {}
    for name in [
        "subject",
        "test_session",
        "protocol_stages",
        "workout_data",
        "breath_by_breath",
        "blood_samples",
    ]:
        try:
            tables[name] = pd.read_sql(f"SELECT * FROM {name}", conn)
        except Exception:
            tables[name] = pd.DataFrame()
    conn.close()
    return tables


def _active_bxb_window(bxb: pd.DataFrame) -> pd.DataFrame:
    """Keep only active exercise breaths and trim recovery artifacts."""
    if bxb.empty or "vo2_ml" not in bxb.columns or "rq" not in bxb.columns:
        return pd.DataFrame()
    valid = bxb[(bxb["vo2_ml"] > 100) & (bxb["rq"] < 1.6)].copy()
    if valid.empty:
        return valid

    if "bike_power_w" in valid.columns:
        active = valid[valid["bike_power_w"].fillna(0) > 0].copy()
        if not active.empty:
            valid = active

    return valid.sort_values("t_s").reset_index(drop=True)


def _json_default(value: Any) -> Any:
    """Convert numpy/pandas scalars to plain Python values for JSON storage."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(
        f"Object of type {value.__class__.__name__} is not JSON serializable"
    )


# ========================================================================
# 1. Lactate Threshold Analysis
# ========================================================================


def analyze_lactate(blood: pd.DataFrame) -> dict[str, Any]:
    """Compute LT1 via fixed-threshold and D-max methods."""
    results: dict[str, Any] = {}

    if blood.empty or "lactate_mmol" not in blood.columns or "load_w" not in blood.columns:
        return results

    valid = blood[blood["lactate_mmol"].notna()].copy()
    valid = valid[valid["load_w"].notna()].copy()

    if valid.empty:
        return results

    baseline = valid[valid["block"] == "rest"]
    baseline_lactate = (
        baseline["lactate_mmol"].iloc[0] if not baseline.empty else 1.58
    )

    results["baseline_lactate"] = baseline_lactate

    b1 = valid[valid["block"].isin(["rest", "block_1"])].copy()
    b3 = valid[valid["block"] == "block_3"].copy()
    vo2max_end = valid[valid["block"] == "block_2"]

    # --- Fixed threshold method ---
    threshold = baseline_lactate + 0.5
    results["fixed_threshold_value"] = threshold

    if len(b1) >= 2:
        for i in range(len(b1) - 1):
            lac1 = b1.iloc[i]["lactate_mmol"]
            lac2 = b1.iloc[i + 1]["lactate_mmol"]
            w1 = b1.iloc[i]["load_w"]
            w2 = b1.iloc[i + 1]["load_w"]
            if lac1 <= threshold <= lac2:
                frac = (
                    (threshold - lac1) / (lac2 - lac1) if lac2 != lac1 else 0.5
                )
                lt1_power = w1 + frac * (w2 - w1)
                results["lt1_fixed_power_w"] = round(lt1_power, 1)
                break
        else:
            if b1["lactate_mmol"].max() > threshold:
                results["lt1_fixed_power_w"] = float(
                    b1[b1["lactate_mmol"] > threshold].iloc[0]["load_w"]
                )
            else:
                results["lt1_fixed_power_w"] = None

    # --- D-max method ---
    if not vo2max_end.empty and not b3.empty:
        post_vo2max_lactate = float(vo2max_end.iloc[0]["lactate_mmol"])
        b3 = b3.copy()
        b3["lactate_dmax"] = baseline_lactate + (
            b3["lactate_mmol"] - post_vo2max_lactate
        )
        results["block3_baseline_adjustment_mmol"] = round(
            post_vo2max_lactate - baseline_lactate, 2
        )
    else:
        b3 = b3.copy()
        b3["lactate_dmax"] = b3["lactate_mmol"]

    b1 = b1.copy()
    b1["lactate_dmax"] = b1["lactate_mmol"]

    all_data = (
        pd.concat(
            [b1[["load_w", "lactate_dmax"]], b3[["load_w", "lactate_dmax"]]],
            ignore_index=True,
        )
        .dropna()
        .sort_values("load_w")
    )

    if len(all_data) >= 4 and all_data["load_w"].nunique() >= 4:
        x = all_data["load_w"].to_numpy(dtype=float)
        y = all_data["lactate_dmax"].to_numpy(dtype=float)

        try:
            curve = PchipInterpolator(x, y)
            x_line = np.linspace(x[0], x[-1], 1000)
            y_curve = curve(x_line)

            x0, y0 = x[0], y[0]
            x1, y1 = x[-1], y[-1]
            dx = x1 - x0
            dy = y1 - y0
            line_len = np.sqrt(dx**2 + dy**2)

            if line_len > 0:
                distances = (
                    np.abs(dy * x_line - dx * y_curve + x1 * y0 - y1 * x0)
                    / line_len
                )
                dmax_idx = int(np.argmax(distances))
                dmax_power = x_line[dmax_idx]
                dmax_lactate = y_curve[dmax_idx]

                results["lt1_dmax_power_w"] = round(float(dmax_power), 1)
                results["lt1_dmax_lactate"] = round(float(dmax_lactate), 2)
                results["lt1_dmax_method"] = (
                    "PCHIP D-max with Block 3 baseline adjustment"
                )
                results["lactate_curve_points_adjusted"] = [
                    {"power_w": float(px), "lactate": round(float(py), 3)}
                    for px, py in zip(x, y)
                ]
        except ValueError:
            results["lt1_dmax_power_w"] = None

    # Power-lactate data points for charting
    results["lactate_points"] = [
        {
            "power_w": float(r["load_w"]),
            "lactate": float(r["lactate_mmol"]),
            "hr": float(r["hr_bpm"]) if pd.notna(r["hr_bpm"]) else None,
            "glucose": (
                float(r["glucose_mmol"]) if pd.notna(r["glucose_mmol"]) else None
            ),
            "block": r["block"],
        }
        for _, r in valid.iterrows()
    ]

    return results


# ========================================================================
# 2. Lactate Clearance (Block 3)
# ========================================================================


def analyze_clearance(blood: pd.DataFrame) -> dict[str, Any]:
    """Analyze lactate clearance during Block 3."""
    results: dict[str, Any] = {}

    vo2max_end = blood[
        (blood["block"] == "block_2") & blood["lactate_mmol"].notna()
    ]
    b3 = blood[
        (blood["block"] == "block_3") & blood["lactate_mmol"].notna()
    ].copy()

    if not vo2max_end.empty:
        results["post_vo2max_lactate"] = float(vo2max_end.iloc[0]["lactate_mmol"])

    if not b3.empty and not vo2max_end.empty:
        lactate_vals = b3["lactate_mmol"].values
        power_vals = b3["load_w"].values

        results["clearance_points"] = [
            {"power_w": float(p), "lactate": float(lac)}
            for p, lac in zip(power_vals, lactate_vals)
        ]

        vo2_lac = float(vo2max_end.iloc[0]["lactate_mmol"])
        first_b3_lac = lactate_vals[0]
        last_b3_lac = lactate_vals[-1]

        results["clearance_initial_rise"] = round(first_b3_lac - vo2_lac, 2)
        results["clearance_during_exercise"] = round(
            last_b3_lac - first_b3_lac, 2
        )
        results["b3_lactate_range"] = (
            f"{min(lactate_vals):.2f} - {max(lactate_vals):.2f}"
        )
        results["best_clearance_power_w"] = int(
            b3.loc[b3["lactate_mmol"].idxmin(), "load_w"]
        )

        clearance_rates = []
        previous_lactate = vo2_lac
        for _, row in b3.iterrows():
            duration_min = (
                float(row["duration_min"])
                if pd.notna(row["duration_min"])
                else 3.0
            )
            delta = float(row["lactate_mmol"] - previous_lactate)
            clearance_rates.append(
                {
                    "power_w": float(row["load_w"]),
                    "delta_mmol": round(delta, 2),
                    "rate_mmol_per_min": round(delta / duration_min, 3),
                }
            )
            previous_lactate = float(row["lactate_mmol"])
        results["clearance_rates"] = clearance_rates

    return results


# ========================================================================
# 3. VO2max Analysis (Block 2 BxB)
# ========================================================================


def analyze_vo2max(
    bxb: pd.DataFrame, subject: pd.DataFrame
) -> dict[str, Any]:
    """Compute VO2max and related metrics from breath-by-breath data."""
    results: dict[str, Any] = {}

    weight = float(subject.iloc[0]["weight_kg"]) if not subject.empty else 74.2

    valid = _active_bxb_window(bxb)
    if valid.empty:
        return results

    window = min(10, len(valid))
    valid = valid.copy()
    valid["vo2_rolling"] = valid["vo2_ml"].rolling(window, min_periods=1).mean()
    valid["vco2_rolling"] = (
        valid["vco2_ml"].rolling(window, min_periods=1).mean()
    )
    valid["ve_rolling"] = (
        valid["ve_lmin"].rolling(window, min_periods=1).mean()
    )

    peak_idx = valid["vo2_rolling"].idxmax()
    results["vo2max_ml"] = round(float(valid.loc[peak_idx, "vo2_rolling"]), 1)
    results["vo2max_rel"] = round(
        float(valid.loc[peak_idx, "vo2_rolling"]) / weight, 1
    )
    results["vco2max_ml"] = round(
        float(valid.loc[peak_idx, "vco2_rolling"]), 1
    )
    results["ve_max"] = round(float(valid["ve_rolling"].max()), 1)
    results["rer_max"] = round(float(valid["rq"].max()), 2)
    hr_max = valid["hr_bpm"].max() if "hr_bpm" in valid.columns else float("nan")
    if pd.notna(hr_max):
        results["hr_max_bxb"] = int(hr_max)

    if "bike_power_w" in valid.columns:
        peak_power = valid.loc[peak_idx, "bike_power_w"]
        if pd.notna(peak_power):
            results["peak_power_vo2max"] = int(peak_power)

    results["time_to_exhaustion_s"] = round(
        float(valid["t_s"].max() - valid["t_s"].min()), 1
    )
    if "bike_power_w" in valid.columns:
        peak_power_max = valid["bike_power_w"].max()
        if pd.notna(peak_power_max):
            results["peak_power_achieved_w"] = int(peak_power_max)

    if len(valid) > 20:
        last_20 = valid.tail(20)["vo2_rolling"]
        first_half = last_20.head(10).mean()
        second_half = last_20.tail(10).mean()
        plateau_diff = second_half - first_half
        results["vo2_plateau"] = abs(plateau_diff) < 150
        results["vo2_plateau_diff_ml"] = round(float(plateau_diff), 1)

    results["bxb_series"] = {
        "t_s": valid["t_s"].tolist(),
        "vo2": valid["vo2_ml"].tolist(),
        "vco2": valid["vco2_ml"].tolist(),
        "ve": valid["ve_lmin"].tolist(),
        "rq": valid["rq"].tolist(),
        "hr": valid["hr_bpm"].tolist(),
        "power": (
            valid["bike_power_w"].tolist()
            if "bike_power_w" in valid.columns
            else []
        ),
    }

    return results


# ========================================================================
# 4. Ventilatory Thresholds (VT1/VT2)
# ========================================================================


def analyze_ventilatory_thresholds(bxb: pd.DataFrame) -> dict[str, Any]:
    """Detect VT1 and VT2 from VE/VO2 and VE/VCO2 slope breakpoints."""
    results: dict[str, Any] = {}

    valid = _active_bxb_window(bxb)
    if len(valid) < 20:
        return results

    window = 7
    valid = valid.copy()
    valid["ve_vo2_smooth"] = (
        valid["ve_vo2"].rolling(window, min_periods=1).mean()
    )
    valid["ve_vco2_smooth"] = (
        valid["ve_vco2"].rolling(window, min_periods=1).mean()
    )

    ve_vo2 = valid["ve_vo2_smooth"].values
    t = valid["t_s"].values

    min_idx = np.argmin(ve_vo2[: len(ve_vo2) * 3 // 4])
    if min_idx > 0:
        vt1_time = t[min_idx]
        vt1_row = valid.iloc[min_idx]
        results["vt1_time_s"] = round(float(vt1_time), 1)
        results["vt1_vo2_ml"] = round(float(vt1_row["vo2_ml"]), 1)
        results["vt1_hr"] = int(vt1_row["hr_bpm"])
        if "bike_power_w" in valid.columns and pd.notna(
            vt1_row["bike_power_w"]
        ):
            results["vt1_power_w"] = int(vt1_row["bike_power_w"])

    ve_vco2 = valid["ve_vco2_smooth"].values
    min_idx2 = np.argmin(ve_vco2[: len(ve_vco2) * 3 // 4])
    if min_idx2 > 0:
        vt2_time = t[min_idx2]
        vt2_row = valid.iloc[min_idx2]
        results["vt2_time_s"] = round(float(vt2_time), 1)
        results["vt2_vo2_ml"] = round(float(vt2_row["vo2_ml"]), 1)
        results["vt2_hr"] = int(vt2_row["hr_bpm"])
        if "bike_power_w" in valid.columns and pd.notna(
            vt2_row["bike_power_w"]
        ):
            results["vt2_power_w"] = int(vt2_row["bike_power_w"])

    results["vt_series"] = {
        "t_s": valid["t_s"].tolist(),
        "ve_vo2": valid["ve_vo2_smooth"].tolist(),
        "ve_vco2": valid["ve_vco2_smooth"].tolist(),
    }

    return results


# ========================================================================
# 5. Substrate Utilization
# ========================================================================


def _rolling_mean(values: pd.Series, window: int = 5) -> pd.Series:
    """Return a centered rolling mean for compact metabolism series."""
    return values.rolling(window=window, center=True, min_periods=1).mean()


def _build_power_domain_substrate(valid: pd.DataFrame) -> dict[str, Any]:
    """Build a chart-ready power-domain substrate contract from breath data."""
    required = ["bike_power_w", "fat_gmin", "cho_gmin"]
    power_domain = valid.dropna(subset=required).copy()
    power_domain = power_domain[power_domain["bike_power_w"] >= 40].copy()
    if power_domain.empty:
        return {}

    power_domain["fat_gmin"] = power_domain["fat_gmin"].clip(lower=0)
    power_domain["cho_gmin"] = power_domain["cho_gmin"].clip(lower=0)
    power_domain["power_bin_w"] = (
        (power_domain["bike_power_w"] / 5.0).round() * 5.0
    )

    grouped = (
        power_domain.groupby("power_bin_w", as_index=False)
        .agg(
            fat_gmin=("fat_gmin", "median"),
            cho_gmin=("cho_gmin", "median"),
            hr_bpm=("hr_bpm", "median"),
            vo2_kg=("vo2_kg", "median"),
            sample_count=("bike_power_w", "size"),
        )
        .sort_values("power_bin_w")
        .reset_index(drop=True)
    )

    for column in ["fat_gmin", "cho_gmin", "hr_bpm", "vo2_kg"]:
        grouped[column] = _rolling_mean(grouped[column], window=5)

    x = grouped["power_bin_w"].to_numpy(dtype=float)
    dense_power = x.copy()
    dense_fat = grouped["fat_gmin"].to_numpy(dtype=float)
    dense_cho = grouped["cho_gmin"].to_numpy(dtype=float)
    dense_hr = grouped["hr_bpm"].to_numpy(dtype=float)
    dense_vo2 = grouped["vo2_kg"].to_numpy(dtype=float)

    if len(grouped) >= 4 and grouped["power_bin_w"].nunique() >= 4:
        dense_power = np.arange(float(x[0]), float(x[-1]) + 0.5, 0.5)
        dense_fat = PchipInterpolator(x, dense_fat)(dense_power)
        dense_cho = PchipInterpolator(x, dense_cho)(dense_power)
        dense_hr = PchipInterpolator(x, dense_hr)(dense_power)
        dense_vo2 = PchipInterpolator(x, dense_vo2)(dense_power)

    dense_fat = np.clip(dense_fat, 0, None)
    dense_cho = np.clip(dense_cho, 0, None)

    fatmax_idx = int(np.argmax(dense_fat))
    fatmax_power = float(dense_power[fatmax_idx])
    fatmax_value = float(dense_fat[fatmax_idx])
    fatmax_threshold = fatmax_value * 0.90
    fatmax_mask = dense_fat >= fatmax_threshold
    if fatmax_mask.any():
        zone_min = float(dense_power[np.where(fatmax_mask)[0][0]])
        zone_max = float(dense_power[np.where(fatmax_mask)[0][-1]])
    else:
        zone_min = max(float(dense_power[0]), fatmax_power - 10.0)
        zone_max = min(float(dense_power[-1]), fatmax_power + 10.0)
    if zone_max - zone_min < 8.0:
        zone_min = max(float(dense_power[0]), fatmax_power - 10.0)
        zone_max = min(float(dense_power[-1]), fatmax_power + 10.0)

    diff = dense_fat - dense_cho
    crossovers: list[dict[str, Any]] = []
    for idx in range(len(diff) - 1):
        d1 = float(diff[idx])
        d2 = float(diff[idx + 1])
        if not ((d1 > 0 >= d2) or (d1 >= 0 > d2)):
            continue
        p1 = float(dense_power[idx])
        p2 = float(dense_power[idx + 1])
        t = 0.0 if d1 == d2 else (-d1 / (d2 - d1))
        crossovers.append(
            {
                "power_w": round(p1 + t * (p2 - p1), 1),
                "fat_gmin": round(
                    float(
                        dense_fat[idx]
                        + t * (dense_fat[idx + 1] - dense_fat[idx])
                    ),
                    4,
                ),
                "cho_gmin": round(
                    float(
                        dense_cho[idx]
                        + t * (dense_cho[idx + 1] - dense_cho[idx])
                    ),
                    4,
                ),
                "confidence": round(abs(d1 - d2), 4),
            }
        )

    primary_crossover = None
    if crossovers:
        crossovers.sort(key=lambda marker: marker["confidence"], reverse=True)
        primary_crossover = crossovers[0]

    return {
        "metabolism_power_curve": {
            "power_w": [round(float(v), 1) for v in dense_power.tolist()],
            "fat_gmin": [round(float(v), 4) for v in dense_fat.tolist()],
            "cho_gmin": [round(float(v), 4) for v in dense_cho.tolist()],
            "hr_bpm": [round(float(v), 1) for v in dense_hr.tolist()],
            "vo2_kg": [round(float(v), 2) for v in dense_vo2.tolist()],
        },
        "metabolism_power_bins": {
            "power_w": [
                round(float(v), 1) for v in grouped["power_bin_w"].tolist()
            ],
            "fat_gmin": [
                round(float(v), 4) for v in grouped["fat_gmin"].tolist()
            ],
            "cho_gmin": [
                round(float(v), 4) for v in grouped["cho_gmin"].tolist()
            ],
            "sample_count": [
                int(v) for v in grouped["sample_count"].tolist()
            ],
        },
        "metabolism_markers": {
            "fatmax_power_w": round(fatmax_power, 1),
            "fatmax_gmin": round(fatmax_value, 4),
            "fatmax_zone_min_w": round(zone_min, 1),
            "fatmax_zone_max_w": round(zone_max, 1),
            "primary_crossover": primary_crossover,
            "all_crossovers": crossovers,
        },
    }


def analyze_substrate(bxb: pd.DataFrame) -> dict[str, Any]:
    """Analyze fat and CHO oxidation rates."""
    results: dict[str, Any] = {}

    valid = _active_bxb_window(bxb)
    if valid.empty:
        return results

    fat = valid["fat_gmin"].clip(lower=0)
    cho = valid["cho_gmin"].clip(lower=0)

    fatmax_idx = fat.idxmax()
    results["fatmax_gmin"] = round(float(fat.loc[fatmax_idx]), 3)
    results["fatmax_time_s"] = round(float(valid.loc[fatmax_idx, "t_s"]), 1)
    if "bike_power_w" in valid.columns and pd.notna(
        valid.loc[fatmax_idx, "bike_power_w"]
    ):
        results["fatmax_power_w"] = int(valid.loc[fatmax_idx, "bike_power_w"])
    results["fatmax_hr"] = int(valid.loc[fatmax_idx, "hr_bpm"])

    diff = fat.values - cho.values
    crossover_candidates = np.where(np.diff(np.sign(diff)) != 0)[0]
    if len(crossover_candidates) > 0:
        cx_idx = crossover_candidates[0]
        cx_row = valid.iloc[cx_idx]
        results["crossover_time_s"] = round(float(cx_row["t_s"]), 1)
        if "bike_power_w" in valid.columns and pd.notna(
            cx_row["bike_power_w"]
        ):
            results["crossover_power_w"] = int(cx_row["bike_power_w"])
        results["crossover_hr"] = int(cx_row["hr_bpm"])

    results["substrate_series"] = {
        "t_s": valid["t_s"].tolist(),
        "fat_gmin": fat.tolist(),
        "cho_gmin": cho.tolist(),
    }

    results.update(_build_power_domain_substrate(valid))

    if "ee_tot" in valid.columns:
        results["total_energy_kcal"] = round(
            float(valid["ee_tot"].iloc[-1]), 1
        )

    return results


# ========================================================================
# 6. Efficiency Metrics
# ========================================================================


def analyze_efficiency(bxb: pd.DataFrame) -> dict[str, Any]:
    """Estimate oxygen cost and gross efficiency from the submax ramp window."""
    results: dict[str, Any] = {}

    valid = _active_bxb_window(bxb)
    if valid.empty or "bike_power_w" not in valid.columns:
        return results

    eff = valid[
        valid["bike_power_w"].fillna(0).between(125, 250)
        & valid["vo2_ml"].fillna(0).between(1200, 5000)
    ].copy()
    if eff.empty:
        return results

    eff["gross_efficiency_pct"] = (
        eff["bike_power_w"].clip(lower=1) * 60.0
        / (eff["vo2_ml"].clip(lower=1) * 20.9)
    ) * 100.0
    eff["stage_power_w"] = (
        (eff["bike_power_w"] / 25.0).round().astype(int) * 25
    )

    stage_stats = (
        eff.groupby("stage_power_w")
        .agg(
            mean_power_w=("bike_power_w", "mean"),
            median_vo2_ml=("vo2_ml", "median"),
            median_hr_bpm=("hr_bpm", "median"),
            gross_efficiency_pct=("gross_efficiency_pct", "median"),
        )
        .reset_index()
        .sort_values("stage_power_w")
    )

    if len(stage_stats) >= 2:
        slope, intercept = np.polyfit(
            stage_stats["mean_power_w"], stage_stats["median_vo2_ml"], 1
        )
        results["vo2_power_slope_ml_per_w"] = round(float(slope), 2)
        results["vo2_power_intercept_ml"] = round(float(intercept), 1)
        if slope > 0:
            results["economy_w_per_l_o2"] = round(1000.0 / float(slope), 1)

    best_stage = stage_stats.loc[stage_stats["gross_efficiency_pct"].idxmax()]
    results["peak_gross_efficiency_pct"] = round(
        float(best_stage["gross_efficiency_pct"]), 2
    )
    results["peak_gross_efficiency_power_w"] = int(
        best_stage["stage_power_w"]
    )
    results["efficiency_by_stage"] = [
        {
            "power_w": int(row["stage_power_w"]),
            "median_vo2_ml": round(float(row["median_vo2_ml"]), 1),
            "median_hr_bpm": round(float(row["median_hr_bpm"]), 1),
            "gross_efficiency_pct": round(
                float(row["gross_efficiency_pct"]), 2
            ),
        }
        for _, row in stage_stats.iterrows()
    ]
    results["efficiency_window"] = "Submax ramp stages 125-250W"

    return results


# ========================================================================
# 7. Heart Rate Analysis
# ========================================================================


def analyze_hr(
    workout: pd.DataFrame, subject: pd.DataFrame
) -> dict[str, Any]:
    """Analyze heart rate dynamics across the full workout."""
    results: dict[str, Any] = {}

    if workout.empty:
        return results

    age = float(subject.iloc[0]["age"]) if not subject.empty else 41
    max_hr_recorded = (
        float(subject.iloc[0]["max_hr"]) if not subject.empty else 186
    )
    predicted_max = 220 - age

    results["predicted_max_hr"] = round(predicted_max, 0)
    results["recorded_max_hr"] = int(max_hr_recorded)
    results["actual_max_hr"] = int(workout["hr_bpm"].max())
    results["hr_reserve"] = int(
        results["actual_max_hr"] - workout["hr_bpm"].min()
    )

    hr_by_block: dict[str, dict[str, Any]] = {}
    for block in workout["block"].unique():
        bd = workout[workout["block"] == block]
        hr_by_block[block] = {
            "mean": round(float(bd["hr_bpm"].mean()), 1),
            "max": int(bd["hr_bpm"].max()),
            "min": int(bd["hr_bpm"].min()),
        }
    results["hr_by_block"] = hr_by_block

    recovery_metrics: dict[str, dict[str, Any]] = {}
    for block in ["recovery_1", "recovery_2"]:
        bd = workout[workout["block"] == block]
        if bd.empty:
            continue
        start_hr = float(bd.head(min(5, len(bd)))["hr_bpm"].mean())
        end_hr = float(bd.tail(min(5, len(bd)))["hr_bpm"].mean())
        recovery_metrics[block] = {
            "start_hr_bpm": round(start_hr, 1),
            "end_hr_bpm": round(end_hr, 1),
            "delta_bpm": round(end_hr - start_hr, 1),
        }
    results["hr_recovery"] = recovery_metrics

    b1 = workout[workout["block"] == "block_1"]
    hr_drift: dict[str, float] = {}
    for step in sorted(b1["step"].unique()):
        stage = b1[b1["step"] == step]
        if len(stage) > 60:
            first_min = stage.head(60)["hr_bpm"].mean()
            last_min = stage.tail(60)["hr_bpm"].mean()
            drift = last_min - first_min
            target = stage["target_power_w"].iloc[0]
            hr_drift[f"{int(target)}W"] = round(float(drift), 1)
    results["hr_drift_block1"] = hr_drift

    if len(b1) > 100:
        b1_means = (
            b1.groupby("step")
            .agg({"hr_bpm": "mean", "target_power_w": "first"})
            .dropna()
        )
        if len(b1_means) >= 2:
            from numpy.polynomial import polynomial as P

            coeffs = P.polyfit(
                b1_means["target_power_w"].values,
                b1_means["hr_bpm"].values,
                1,
            )
            results["hr_power_slope"] = round(float(coeffs[1]), 3)
            results["hr_power_intercept"] = round(float(coeffs[0]), 1)

    sampled = workout.iloc[::10][
        ["elapsed_s", "hr_bpm", "power_w", "block"]
    ].copy()
    results["hr_timeline"] = {
        "elapsed_s": sampled["elapsed_s"].tolist(),
        "hr": sampled["hr_bpm"].tolist(),
        "power": sampled["power_w"].tolist(),
        "block": sampled["block"].tolist(),
    }

    return results


# ========================================================================
# 8. Training Zones
# ========================================================================


def compute_training_zones(
    lactate_results: dict[str, Any],
    hr_results: dict[str, Any],
    vt_results: dict[str, Any],
    subject: pd.DataFrame,
) -> dict[str, Any]:
    """Define threshold-based training zones from lactate + HR + power data."""
    results: dict[str, Any] = {}

    ftp = int(subject.iloc[0]["ftp_w"]) if not subject.empty else 253
    max_hr = hr_results.get("actual_max_hr", 190)

    lt1_power = lactate_results.get(
        "lt1_dmax_power_w"
    ) or lactate_results.get("lt1_fixed_power_w")
    est_lt2_power = (
        int(subject.iloc[0]["est_lt2_w"]) if not subject.empty else 270
    )

    lt2_candidates = [
        candidate
        for candidate in [est_lt2_power, ftp]
        if candidate and candidate > (lt1_power or 0)
    ]
    lt2_power = min(lt2_candidates) if lt2_candidates else ftp

    lt1_hr = vt_results.get("vt1_hr") or int(max_hr * 0.72)
    lt2_hr = vt_results.get("vt2_hr") or int(max_hr * 0.87)
    if lt2_hr <= lt1_hr:
        lt2_hr = max(lt1_hr + 1, int(max_hr * 0.87))

    zones = []
    if lt1_power:
        lt1 = int(round(float(lt1_power)))
        lt2 = int(round(float(lt2_power)))
        zones = [
            {
                "zone": 1,
                "name": "Below LT1",
                "power_range": f"< {lt1}W",
                "hr_range": f"< {lt1_hr} bpm",
                "description": "Recovery / easy aerobic",
            },
            {
                "zone": 2,
                "name": "LT1 to LT2",
                "power_range": f"{lt1}-{lt2}W",
                "hr_range": f"{lt1_hr}-{lt2_hr} bpm",
                "description": "Steady aerobic to threshold",
            },
            {
                "zone": 3,
                "name": "Above LT2",
                "power_range": f"> {lt2}W",
                "hr_range": f"> {lt2_hr} bpm",
                "description": "High-intensity / VO2 work",
            },
        ]
    results["zones"] = zones
    results["ftp_w"] = ftp
    results["lt1_power_w"] = lt1_power
    results["lt2_power_w"] = lt2_power
    results["lt1_hr_bpm"] = lt1_hr
    results["lt2_hr_bpm"] = lt2_hr
    results["lt2_basis"] = "min(estimated LT2, FTP)"

    return results


# ========================================================================
# Store Results
# ========================================================================


# ========================================================================
# Energy System 3-Pathway Analysis (교수님 공식)
# ========================================================================

CALORIC_EQUIVALENT_KJ_PER_L = 20.9

_trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))


def analyze_energy_system(
    bxb: pd.DataFrame,
    blood: pd.DataFrame,
    subject: pd.DataFrame,
) -> dict[str, Any]:
    """Compute 3-pathway energy system contributions."""
    result: dict[str, Any] = {
        "status": "skipped", "warnings": [],
        "oxidative_kj": None, "glycolytic_kj": None, "phosphagen_kj": None,
        "total_kj": None, "oxidative_pct": None, "glycolytic_pct": None,
        "phosphagen_pct": None, "has_lactate": False, "has_phosphagen": False,
        "delta_lactate": None, "mono_exp_fit": None,
    }
    if bxb.empty or "vo2_ml" not in bxb.columns or "t_s" not in bxb.columns:
        result["warnings"].append("No breath-by-breath data available")
        return result

    valid = bxb.copy()
    for col in ("t_s", "vo2_ml", "bike_power_w"):
        if col in valid.columns:
            valid[col] = pd.to_numeric(valid[col], errors="coerce")
    valid = valid.dropna(subset=["t_s", "vo2_ml"])
    if len(valid) < 10:
        result["warnings"].append("Insufficient breath data (<10 points)")
        return result

    t_sec = valid["t_s"].values.astype(float)
    vo2_ml = valid["vo2_ml"].values.astype(float)
    power = (
        valid["bike_power_w"].fillna(0).values.astype(float)
        if "bike_power_w" in valid.columns else np.zeros(len(t_sec))
    )

    # Detect exercise window
    above = np.where(power > 20)[0]
    if len(above) == 0:
        ex_start, ex_end = float(t_sec[0]), float(t_sec[-1])
    else:
        ex_start = float(t_sec[above[0]])
        peak_idx = int(np.argmax(power))
        peak_power = power[peak_idx]
        if peak_power > 0:
            post_peak = power[peak_idx:]
            dropout = np.where(post_peak < peak_power * 0.2)[0]
            ex_end = float(t_sec[peak_idx + dropout[0]]) if len(dropout) > 0 else float(t_sec[-1])
        else:
            ex_end = float(t_sec[-1])

    result["status"] = "computed"

    # 1. Oxidative energy: VO2 integral × 20.9
    ex_mask = (t_sec >= ex_start) & (t_sec <= ex_end)
    t_ex, vo2_ex = t_sec[ex_mask], vo2_ml[ex_mask]
    if len(t_ex) >= 2:
        vo2_l_per_s = vo2_ex / 1000.0 / 60.0
        result["oxidative_kj"] = round(float(_trapz(vo2_l_per_s, t_ex)) * CALORIC_EQUIVALENT_KJ_PER_L, 2)

    # 2. Glycolytic energy: delta_La × 3 × BW × dist_vol × 20.9
    bw, body_fat_pct = None, None
    if not subject.empty:
        if "weight_kg" in subject.columns:
            w = pd.to_numeric(subject["weight_kg"], errors="coerce").dropna()
            if not w.empty:
                bw = float(w.iloc[0])
        if "body_fat_pct" in subject.columns:
            bf = pd.to_numeric(subject["body_fat_pct"], errors="coerce").dropna()
            if not bf.empty:
                body_fat_pct = float(bf.iloc[0])

    lactate_dist_vol = 0.73 * (1.0 - body_fat_pct / 100.0) if body_fat_pct and 0 < body_fat_pct < 100 else 0.6

    if not blood.empty and "lactate_mmol" in blood.columns:
        la_vals = pd.to_numeric(blood["lactate_mmol"], errors="coerce").dropna()
        if len(la_vals) >= 2:
            la_rest, la_peak = float(la_vals.iloc[0]), float(la_vals.max())
            delta_la = la_peak - la_rest
            result["delta_lactate"] = round(delta_la, 2)
            result["has_lactate"] = True
            if bw and delta_la > 0:
                result["glycolytic_kj"] = round((delta_la * 3.0 * bw * lactate_dist_vol / 1000.0) * CALORIC_EQUIVALENT_KJ_PER_L, 2)
            elif delta_la <= 0:
                result["glycolytic_kj"] = 0.0

    # 3. Phosphagen energy: EPOC fast component mono-exponential fit
    post_mask = t_sec > ex_end
    post_t, post_power, post_vo2 = t_sec[post_mask], power[post_mask], vo2_ml[post_mask]

    if len(post_t) >= 10:
        low_power = np.where(post_power < 30)[0]
        if len(low_power) > 0:
            rec_start = float(post_t[low_power[0]])
            rec_end = min(float(post_t[-1]), rec_start + 300)
            if rec_end - rec_start >= 30:
                rec_mask = (t_sec >= rec_start) & (t_sec <= rec_end)
                t_rec, vo2_rec_lmin = t_sec[rec_mask], vo2_ml[rec_mask] / 1000.0
                if len(t_rec) >= 10:
                    t_norm = t_rec - t_rec[0]
                    try:
                        from scipy.optimize import curve_fit
                        def mono_exp(t, a, tau, bl):
                            return a * np.exp(-t / tau) + bl
                        popt, _ = curve_fit(mono_exp, t_norm, vo2_rec_lmin,
                            p0=[float(vo2_rec_lmin[0] - vo2_rec_lmin[-1]), 30.0, float(np.min(vo2_rec_lmin))],
                            bounds=([0, 1, 0], [10, 300, 5]), maxfev=5000)
                        a_fit, tau_fit, bl_fit = popt
                        vo2_pred = mono_exp(t_norm, a_fit, tau_fit, bl_fit)
                        ss_res = float(np.sum((vo2_rec_lmin - vo2_pred) ** 2))
                        ss_tot = float(np.sum((vo2_rec_lmin - np.mean(vo2_rec_lmin)) ** 2))
                        r_sq = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
                        result["phosphagen_kj"] = round((a_fit * tau_fit / 60.0) * CALORIC_EQUIVALENT_KJ_PER_L, 2)
                        result["has_phosphagen"] = True
                        result["mono_exp_fit"] = {
                            "amplitude_l_min": round(a_fit, 4), "tau_sec": round(tau_fit, 2),
                            "baseline_l_min": round(bl_fit, 4), "r_squared": round(r_sq, 4), "n_points": len(t_rec),
                        }
                        if r_sq < 0.8:
                            result["warnings"].append(f"Low mono-exponential fit quality (R²={r_sq:.3f})")
                    except Exception as e:
                        result["warnings"].append(f"Phosphagen fit failed: {e}")

    # Percentages
    components = []
    if result["oxidative_kj"] is not None:
        components.append(("oxidative", result["oxidative_kj"]))
    if result["has_lactate"] and result["glycolytic_kj"] is not None:
        components.append(("glycolytic", result["glycolytic_kj"]))
    if result["has_phosphagen"] and result["phosphagen_kj"] is not None:
        components.append(("phosphagen", result["phosphagen_kj"]))
    total = sum(v for _, v in components)
    result["total_kj"] = round(total, 2) if total > 0 else None
    if total > 0:
        for name, val in components:
            result[f"{name}_pct"] = round(val / total * 100, 1)
    return result


def store_results(db_path: Path, all_results: dict[str, Any]) -> None:
    """Store analysis results in SQLite.

    Args:
        db_path: Path to the analysis.db file.
        all_results: Dict of category -> key -> value results.
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            UNIQUE(category, key)
        )
    """
    )

    for category, data in all_results.items():
        if isinstance(data, dict):
            for key, value in data.items():
                val_str = (
                    _json.dumps(
                        value, ensure_ascii=False, default=_json_default
                    )
                    if not isinstance(value, str)
                    else value
                )
                cursor.execute(
                    "INSERT OR REPLACE INTO analysis_results (category, key, value) VALUES (?, ?, ?)",
                    (category, key, val_str),
                )

    conn.commit()
    count = cursor.execute(
        "SELECT COUNT(*) FROM analysis_results"
    ).fetchone()[0]
    conn.close()
    print(f"  analysis_results: {count} entries stored")


# ========================================================================
# Main
# ========================================================================


def run_analysis(db_path: Path) -> dict[str, Any]:
    """Run all analysis algorithms and return results.

    Args:
        db_path: Path to the analysis.db file.

    Returns:
        Dict of all analysis results by category.
    """
    print("=" * 60)
    print("ANALYSIS ALGORITHMS")
    print("=" * 60)

    data = load_data(db_path)

    print("\n1. Lactate Threshold Analysis...")
    if not data["blood_samples"].empty:
        lactate_results = analyze_lactate(data["blood_samples"])
        print(
            f"   LT1 (fixed): {lactate_results.get('lt1_fixed_power_w')}W"
        )
        print(
            f"   LT1 (D-max): {lactate_results.get('lt1_dmax_power_w')}W"
        )
        print(
            f"   Baseline lactate: {lactate_results.get('baseline_lactate')} mmol/L"
        )
    else:
        lactate_results = {}
        print("   Skipped (no blood sample data)")

    print("\n2. Lactate Clearance...")
    if not data["blood_samples"].empty:
        clearance_results = analyze_clearance(data["blood_samples"])
        print(
            f"   Post-VO2max lactate: {clearance_results.get('post_vo2max_lactate')} mmol/L"
        )
        print(
            f"   Clearance during exercise: {clearance_results.get('clearance_during_exercise')} mmol/L"
        )
    else:
        clearance_results = {}
        print("   Skipped (no blood sample data)")

    print("\n3. VO2max Analysis...")
    vo2max_results = analyze_vo2max(
        data["breath_by_breath"], data["subject"]
    )
    print(
        f"   VO2max: {vo2max_results.get('vo2max_ml')} mL/min ({vo2max_results.get('vo2max_rel')} mL/min/kg)"
    )
    print(f"   RER max: {vo2max_results.get('rer_max')}")
    print(f"   HR max (BxB): {vo2max_results.get('hr_max_bxb')}")
    print(
        f"   Time to exhaustion: {vo2max_results.get('time_to_exhaustion_s')}s"
    )
    print(f"   VO2 plateau: {vo2max_results.get('vo2_plateau')}")

    print("\n4. Ventilatory Thresholds...")
    vt_results = analyze_ventilatory_thresholds(data["breath_by_breath"])
    print(
        f"   VT1: power={vt_results.get('vt1_power_w')}W, HR={vt_results.get('vt1_hr')}"
    )
    print(
        f"   VT2: power={vt_results.get('vt2_power_w')}W, HR={vt_results.get('vt2_hr')}"
    )

    print("\n5. Substrate Utilization...")
    substrate_results = analyze_substrate(data["breath_by_breath"])
    print(
        f"   FatMax: {substrate_results.get('fatmax_gmin')} g/min at {substrate_results.get('fatmax_power_w')}W"
    )
    print(f"   Crossover: {substrate_results.get('crossover_power_w')}W")

    print("\n6. Efficiency Metrics...")
    efficiency_results = analyze_efficiency(data["breath_by_breath"])
    print(
        f"   Gross efficiency peak: {efficiency_results.get('peak_gross_efficiency_pct')}%"
    )
    print(
        f"   VO2-power slope: {efficiency_results.get('vo2_power_slope_ml_per_w')} mL/W"
    )

    print("\n7. Heart Rate Analysis...")
    if not data["workout_data"].empty:
        hr_results = analyze_hr(data["workout_data"], data["subject"])
        print(
            f"   Max HR: {hr_results.get('actual_max_hr')} (predicted: {hr_results.get('predicted_max_hr')})"
        )
        print(
            f"   HR drift (Block 1): {hr_results.get('hr_drift_block1')}"
        )
    else:
        hr_results = {}
        print("   Skipped (no workout data)")

    print("\n8. Training Zones...")
    zone_results = compute_training_zones(
        lactate_results, hr_results, vt_results, data["subject"]
    )
    for z in zone_results.get("zones", []):
        print(
            f"   Zone {z['zone']} ({z['name']}): {z['power_range']}, {z['hr_range']}"
        )

    print("\n9. Energy System 3-Pathway...")
    energy_system_results = analyze_energy_system(
        data["breath_by_breath"], data["blood_samples"], data["subject"],
    )
    if energy_system_results.get("status") == "computed":
        print(f"   Oxidative: {energy_system_results.get('oxidative_kj')} kJ ({energy_system_results.get('oxidative_pct')}%)")
        if energy_system_results.get("has_lactate"):
            print(f"   Glycolytic: {energy_system_results.get('glycolytic_kj')} kJ ({energy_system_results.get('glycolytic_pct')}%)")
        if energy_system_results.get("has_phosphagen"):
            print(f"   Phosphagen: {energy_system_results.get('phosphagen_kj')} kJ ({energy_system_results.get('phosphagen_pct')}%)")
        print(f"   Total: {energy_system_results.get('total_kj')} kJ")
    else:
        print(f"   Skipped ({', '.join(energy_system_results.get('warnings', []))})")

    all_results = {
        "lactate": lactate_results,
        "clearance": clearance_results,
        "vo2max": vo2max_results,
        "ventilatory_thresholds": vt_results,
        "substrate": substrate_results,
        "efficiency": efficiency_results,
        "hr": hr_results,
        "training_zones": zone_results,
        "energy_system": energy_system_results,
    }

    print("\nStoring results...")
    store_results(db_path, all_results)

    return all_results
