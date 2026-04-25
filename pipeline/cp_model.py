"""
pipeline.cp_model — Critical Power and W-prime 2-parameter hyperbolic model.

Provides:
  - compute_cp_model(history: dict) → dict
    Fits the linearized P = CP + W'·(1/t) model from workout best-effort bins.

Reference:
    Monod & Scherrer (1965), Hill (1993) — linearisation:
        y[i] = P[i],  X[i] = [1, 1/t[i]],  β = [CP, W']
"""

from __future__ import annotations

from typing import Any

import numpy as np


def compute_cp_model(history: dict[str, Any]) -> dict[str, Any]:
    """Fit a 2-parameter hyperbolic Critical Power model from workout history.

    Linearisation:
        P = CP + W' · (1/t)
        y[i] = P[i],  X[i] = [1, 1/t[i]],  β = [CP, W']

    Solver: ``numpy.linalg.lstsq`` (rcond=None).

    Abstain conditions (evaluated in order):
        1. Fewer than 3 filled duration bins → abstain
        2. Fitted W' < 0 → abstain
        3. Fitted CP < 50 W → abstain
        4. Constant power input (ss_tot == 0 but ss_res != 0) → abstain

    Args:
        history: Output of :func:`pipeline.fit_history.extract_workout_bests`.
            Must contain ``bins`` mapping ``{str(duration_s): {"best_w": float, ...} | None}``
            and ``coverage.filled_count``.

    Returns:
        Result dict with keys:
            ``status``      "computed" or "abstained"
            ``model``       "2-parameter-hyperbolic"
            ``cp_w``        fitted CP in watts (float or None)
            ``w_prime_j``   fitted W' in joules (float or None)
            ``r_squared``   coefficient of determination (float or None)
            ``rmse``        root-mean-square error in watts (float or None)
            ``points_used`` number of filled bins used (int)
            ``durations_used_s``    list of durations (seconds) contributing to fit
            ``powers_used_w``       list of best powers (watts) corresponding to durations
            ``suitability`` {"status": "point" | "band" | "hidden"}
            ``abstain_reason``      explanation string when abstained, else None
    """
    bins: dict[str, Any | None] = history.get("bins", {})

    # Collect filled (duration_s, best_w) pairs, sorted by duration ascending.
    filled: list[tuple[int, float]] = []
    for key, value in bins.items():
        if value is not None:
            try:
                t = int(key)
                w = float(value["best_w"])
                filled.append((t, w))
            except (KeyError, ValueError, TypeError):
                continue
    filled.sort(key=lambda x: x[0])

    points_used = len(filled)

    def _abstain(reason: str) -> dict[str, Any]:
        return {
            "status": "abstained",
            "model": "2-parameter-hyperbolic",
            "cp_w": None,
            "w_prime_j": None,
            "r_squared": None,
            "rmse": None,
            "points_used": points_used,
            "durations_used_s": [t for t, _ in filled],
            "powers_used_w": [w for _, w in filled],
            "suitability": {"status": "hidden"},
            "abstain_reason": reason,
        }

    # --- Abstain condition 1: fewer than 3 filled bins ---
    if points_used < 3:
        return _abstain("fewer than 3 duration bins")

    durations = np.array([t for t, _ in filled], dtype=float)
    powers = np.array([w for _, w in filled], dtype=float)

    # --- Degenerate-input check: constant power (must precede W' sign check) ---
    ss_tot = float(np.sum((powers - powers.mean()) ** 2))
    if ss_tot == 0.0:
        # Constant y: lstsq will likely assign W'≈0 or slightly negative.
        # R² is undefined (or 0/0); treat as degenerate regardless.
        return _abstain("degenerate input (constant power)")

    # --- Linearised fit: y = CP + W'·(1/t) ---
    inv_t = 1.0 / durations
    X = np.column_stack([np.ones(len(durations)), inv_t])  # shape (n, 2)
    y = powers  # shape (n,)

    beta, _residuals, _rank, _sv = np.linalg.lstsq(X, y, rcond=None)
    cp_w = float(beta[0])
    w_prime_j = float(beta[1])

    # --- Abstain condition 2: W' negative ---
    if w_prime_j < 0:
        return _abstain("W′ is negative — insufficient anaerobic reserve in data")

    # --- Abstain condition 3: CP below physiological minimum ---
    if cp_w < 50.0:
        return _abstain("CP below physiological minimum")

    # --- Goodness-of-fit metrics ---
    y_pred = X @ beta
    ss_res = float(np.sum((powers - y_pred) ** 2))

    # ss_tot guaranteed > 0 here (degenerate branch handled above)
    r_squared = float(np.clip(1.0 - ss_res / ss_tot, 0.0, 1.0))
    rmse = float(np.sqrt(ss_res / points_used))

    # --- Suitability ---
    if r_squared >= 0.95:
        suitability_status = "point"
    elif r_squared >= 0.80:
        suitability_status = "band"
    else:
        suitability_status = "hidden"

    return {
        "status": "computed",
        "model": "2-parameter-hyperbolic",
        "cp_w": round(cp_w, 2),
        "w_prime_j": round(w_prime_j, 2),
        "r_squared": round(r_squared, 6),
        "rmse": round(rmse, 4),
        "points_used": points_used,
        "durations_used_s": [int(t) for t in durations],
        "powers_used_w": [float(w) for w in powers],
        "suitability": {"status": suitability_status},
        "abstain_reason": None,
    }
