"""Energy System Analysis Service - CPET 3-pathway 에너지 시스템 분석

Calculates oxidative, glycolytic, and phosphagen energy contributions
from CPET breath-by-breath data and blood lactate measurements.

Three-pathway model:
1. Oxidative (E_ox): VO2 integral over exercise duration
2. Glycolytic (E_gly): Delta lactate × body weight conversion
3. Phosphagen (E_PCr): Mono-exponential fit on recovery VO2

References:
- Beneke et al. (2002) Energetics of karate kumite
- Gastin (2001) Energy system interaction and relative contribution
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Caloric equivalent of O2 (kJ/L O2) - assumes mixed substrate
CALORIC_EQUIVALENT_KJ_PER_L = 20.9


@dataclass
class RecoveryWindow:
    """Recovery phase time window"""
    start_sec: float
    end_sec: float
    is_manual_override: bool = False


@dataclass
class MonoExpFitResult:
    """Result of mono-exponential curve fit on recovery VO2"""
    amplitude: float       # A (L/min above baseline)
    tau: float             # Time constant (seconds)
    baseline: float        # VO2 baseline (L/min)
    r_squared: float       # Goodness of fit
    n_points: int          # Number of data points used
    fit_successful: bool = True
    error_message: Optional[str] = None


@dataclass
class EnergySystemResult:
    """Complete energy system analysis result"""
    # Oxidative pathway
    oxidative_kj: Optional[float] = None
    oxidative_pct: Optional[float] = None

    # Glycolytic pathway (requires lactate)
    glycolytic_kj: Optional[float] = None
    glycolytic_pct: Optional[float] = None
    delta_lactate: Optional[float] = None     # mmol/L
    has_lactate: bool = False

    # Phosphagen pathway (requires recovery data)
    phosphagen_kj: Optional[float] = None
    phosphagen_pct: Optional[float] = None
    has_phosphagen: bool = False

    # Mono-exponential fit details
    mono_exp_fit: Optional[Dict[str, Any]] = None

    # Recovery window used
    recovery_window: Optional[Dict[str, float]] = None

    # Total
    total_kj: Optional[float] = None

    # Metadata
    exercise_duration_sec: Optional[float] = None
    body_weight_kg: Optional[float] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        pathways = []
        if self.oxidative_kj is not None:
            pathways.append({
                "name": "Oxidative",
                "energy_kj": round(self.oxidative_kj, 2),
                "percentage": round(self.oxidative_pct, 1) if self.oxidative_pct else None,
                "color": "#3B82F6",  # blue
            })
        if self.has_lactate and self.glycolytic_kj is not None:
            pathways.append({
                "name": "Glycolytic",
                "energy_kj": round(self.glycolytic_kj, 2),
                "percentage": round(self.glycolytic_pct, 1) if self.glycolytic_pct else None,
                "color": "#EF4444",  # red
            })
        if self.has_phosphagen and self.phosphagen_kj is not None:
            pathways.append({
                "name": "Phosphagen",
                "energy_kj": round(self.phosphagen_kj, 2),
                "percentage": round(self.phosphagen_pct, 1) if self.phosphagen_pct else None,
                "color": "#10B981",  # green
            })

        return {
            "pathways": pathways,
            "total_kj": round(self.total_kj, 2) if self.total_kj else None,
            "has_lactate": self.has_lactate,
            "has_phosphagen": self.has_phosphagen,
            "delta_lactate": round(self.delta_lactate, 2) if self.delta_lactate else None,
            "exercise_duration_sec": self.exercise_duration_sec,
            "body_weight_kg": self.body_weight_kg,
            "mono_exp_fit": self.mono_exp_fit,
            "recovery_window": self.recovery_window,
            "warnings": self.warnings,
        }


class EnergySystemAnalyzer:
    """Analyzes CPET data to determine energy system contributions."""

    def analyze(
        self,
        breath_data: List[Any],
        body_weight_kg: Optional[float] = None,
        resting_lactate: Optional[float] = None,
        peak_lactate: Optional[float] = None,
        recovery_override: Optional[RecoveryWindow] = None,
        exercise_start_sec: Optional[float] = None,
        exercise_end_sec: Optional[float] = None,
    ) -> EnergySystemResult:
        """Run full 3-pathway energy system analysis.

        Args:
            breath_data: List of BreathData ORM objects with t_sec, vo2 (mL/min), bike_power
            body_weight_kg: Subject body weight (kg), required for glycolytic calculation
            resting_lactate: Resting blood lactate (mmol/L)
            peak_lactate: Peak blood lactate (mmol/L)
            recovery_override: Optional manual recovery window override
            exercise_start_sec: Optional exercise start time (seconds)
            exercise_end_sec: Optional exercise end time (seconds)

        Returns:
            EnergySystemResult with pathway energies and percentages
        """
        result = EnergySystemResult()
        result.body_weight_kg = body_weight_kg

        if not breath_data or len(breath_data) < 10:
            result.warnings.append("Insufficient breath data for analysis")
            return result

        # Extract time-VO2 arrays
        t_sec_arr, vo2_ml_arr, power_arr = self._extract_arrays(breath_data)

        if len(t_sec_arr) < 10:
            result.warnings.append("Insufficient valid data points after filtering")
            return result

        # Detect analysis window (exercise phase)
        ex_start, ex_end = self._detect_analysis_window(
            t_sec_arr, power_arr, exercise_start_sec, exercise_end_sec
        )
        result.exercise_duration_sec = ex_end - ex_start

        # 1. Oxidative energy
        result.oxidative_kj = self.calc_oxidative_energy(
            t_sec_arr, vo2_ml_arr, ex_start, ex_end
        )

        # 2. Glycolytic energy (if lactate data available)
        delta_la = None
        if resting_lactate is not None and peak_lactate is not None:
            delta_la = peak_lactate - resting_lactate
            result.delta_lactate = delta_la
            result.has_lactate = True

            if body_weight_kg and delta_la > 0:
                result.glycolytic_kj = self.calc_glycolytic_energy(
                    delta_la, body_weight_kg
                )
            elif delta_la <= 0:
                result.glycolytic_kj = 0.0
                result.warnings.append(
                    "Delta lactate <= 0; glycolytic energy set to 0"
                )
            else:
                result.warnings.append(
                    "Body weight required for glycolytic energy calculation"
                )

        # 3. Phosphagen energy (recovery VO2 fit)
        recovery_window = self._detect_recovery_window(
            t_sec_arr, power_arr, ex_end, recovery_override
        )

        if recovery_window:
            result.recovery_window = {
                "start_sec": recovery_window.start_sec,
                "end_sec": recovery_window.end_sec,
                "is_manual_override": recovery_window.is_manual_override,
            }

            fit_result = self.fit_mono_exponential(
                t_sec_arr, vo2_ml_arr, recovery_window
            )

            if fit_result.fit_successful:
                result.phosphagen_kj = self.calc_phosphagen_energy(fit_result)
                result.has_phosphagen = True
                result.mono_exp_fit = {
                    "amplitude_l_min": round(fit_result.amplitude, 4),
                    "tau_sec": round(fit_result.tau, 2),
                    "baseline_l_min": round(fit_result.baseline, 4),
                    "r_squared": round(fit_result.r_squared, 4),
                    "n_points": fit_result.n_points,
                }

                if fit_result.r_squared < 0.8:
                    result.warnings.append(
                        f"Low mono-exponential fit quality (R²={fit_result.r_squared:.3f} < 0.80). "
                        "Phosphagen estimate may be unreliable."
                    )
            else:
                result.warnings.append(
                    f"Phosphagen calculation unavailable: {fit_result.error_message}"
                )
        else:
            result.warnings.append(
                "Recovery phase too short or not detected; phosphagen energy unavailable"
            )

        # Calculate percentages
        self._calculate_percentages(result)

        return result

    def calc_oxidative_energy(
        self,
        t_sec: np.ndarray,
        vo2_ml: np.ndarray,
        start_sec: float,
        end_sec: float,
    ) -> float:
        """Calculate oxidative energy via VO2 integration.

        E_ox = integral(VO2 in L/s × dt) × 20.9 kJ/L

        IMPORTANT: vo2 in breath_data is mL/min. Convert to L/s before integration.
        VO2 (L/s) = VO2 (mL/min) / 1000 / 60

        Args:
            t_sec: Time array (seconds)
            vo2_ml: VO2 array (mL/min)
            start_sec: Exercise start time (seconds)
            end_sec: Exercise end time (seconds)

        Returns:
            Oxidative energy in kJ
        """
        mask = (t_sec >= start_sec) & (t_sec <= end_sec)
        t_ex = t_sec[mask]
        vo2_ex = vo2_ml[mask]

        if len(t_ex) < 2:
            return 0.0

        # Convert mL/min -> L/s
        vo2_l_per_s = vo2_ex / 1000.0 / 60.0

        # Trapezoidal integration: integral of VO2 (L/s) × dt (s) = total L of O2
        # np.trapz was renamed to np.trapezoid in NumPy 2.0
        _trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))
        total_o2_liters = float(_trapz(vo2_l_per_s, t_ex))

        return total_o2_liters * CALORIC_EQUIVALENT_KJ_PER_L

    def calc_glycolytic_energy(
        self,
        delta_lactate: float,
        body_weight_kg: float,
    ) -> float:
        """Calculate glycolytic energy from blood lactate accumulation.

        E_gly = delta_La (mmol/L) × 3 (mL O2 per mmol/L/kg) / 1000 × BW (kg) × 20.9 (kJ/L)

        The factor 3 mL O2 per mmol/L/kg is the O2 equivalent of lactate
        accumulation per unit body mass (di Prampero & Ferretti, 1999).

        Args:
            delta_lactate: Peak - resting lactate (mmol/L)
            body_weight_kg: Subject body weight (kg)

        Returns:
            Glycolytic energy in kJ
        """
        # 3 mL O2 per mmol/L per kg body weight
        o2_ml = delta_lactate * 3.0 * body_weight_kg
        o2_liters = o2_ml / 1000.0
        return o2_liters * CALORIC_EQUIVALENT_KJ_PER_L

    def calc_phosphagen_energy(
        self,
        fit: MonoExpFitResult,
    ) -> float:
        """Calculate phosphagen energy from mono-exponential fit on recovery VO2.

        E_PCr = A × tau / 60 × 20.9 (kJ/L)

        Where A is the fast component amplitude (L/min above baseline)
        and tau is the time constant (seconds).

        A × tau gives the integral of the fast component in L/min × seconds.
        Dividing by 60 converts to liters of O2.

        Args:
            fit: MonoExpFitResult from mono-exponential curve fit

        Returns:
            Phosphagen energy in kJ
        """
        # A (L/min) × tau (s) / 60 (s/min) = total O2 liters for PCr resynthesis
        o2_liters = fit.amplitude * fit.tau / 60.0
        return o2_liters * CALORIC_EQUIVALENT_KJ_PER_L

    def fit_mono_exponential(
        self,
        t_sec: np.ndarray,
        vo2_ml: np.ndarray,
        recovery: RecoveryWindow,
    ) -> MonoExpFitResult:
        """Fit mono-exponential decay to recovery VO2 data.

        Model: VO2(t) = A × exp(-(t-t0)/tau) + baseline

        Args:
            t_sec: Full time array (seconds)
            vo2_ml: Full VO2 array (mL/min)
            recovery: Recovery phase window

        Returns:
            MonoExpFitResult with fit parameters and R²
        """
        try:
            from scipy.optimize import curve_fit
        except ImportError:
            return MonoExpFitResult(
                amplitude=0, tau=0, baseline=0, r_squared=0, n_points=0,
                fit_successful=False, error_message="scipy not available",
            )

        # Extract recovery phase data
        mask = (t_sec >= recovery.start_sec) & (t_sec <= recovery.end_sec)
        t_rec = t_sec[mask]
        vo2_rec = vo2_ml[mask]

        if len(t_rec) < 10:
            return MonoExpFitResult(
                amplitude=0, tau=0, baseline=0, r_squared=0, n_points=len(t_rec),
                fit_successful=False,
                error_message=f"Insufficient recovery data points ({len(t_rec)} < 10)",
            )

        # Convert to L/min for fitting
        vo2_rec_lmin = vo2_rec / 1000.0

        # Normalize time to start at 0
        t_norm = t_rec - t_rec[0]

        # Initial guesses
        a_guess = float(vo2_rec_lmin[0] - vo2_rec_lmin[-1])
        tau_guess = 30.0  # typical PCr recovery ~30s
        baseline_guess = float(np.min(vo2_rec_lmin))

        def mono_exp(t: np.ndarray, a: float, tau: float, bl: float) -> np.ndarray:
            return a * np.exp(-t / tau) + bl

        try:
            popt, _ = curve_fit(
                mono_exp,
                t_norm,
                vo2_rec_lmin,
                p0=[a_guess, tau_guess, baseline_guess],
                bounds=([0, 1, 0], [10, 300, 5]),
                maxfev=5000,
            )

            a_fit, tau_fit, bl_fit = popt

            # Calculate R²
            vo2_pred = mono_exp(t_norm, a_fit, tau_fit, bl_fit)
            ss_res = float(np.sum((vo2_rec_lmin - vo2_pred) ** 2))
            ss_tot = float(np.sum((vo2_rec_lmin - np.mean(vo2_rec_lmin)) ** 2))
            r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

            return MonoExpFitResult(
                amplitude=float(a_fit),
                tau=float(tau_fit),
                baseline=float(bl_fit),
                r_squared=r_squared,
                n_points=len(t_rec),
            )

        except (RuntimeError, ValueError) as e:
            return MonoExpFitResult(
                amplitude=0, tau=0, baseline=0, r_squared=0, n_points=len(t_rec),
                fit_successful=False,
                error_message=f"Curve fitting failed: {str(e)}",
            )

    def _extract_arrays(
        self, breath_data: List[Any]
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Extract numpy arrays from breath data, filtering NaN values.

        Args:
            breath_data: List of BreathData ORM objects

        Returns:
            Tuple of (t_sec, vo2_ml, power) numpy arrays
        """
        t_vals: list[float] = []
        vo2_vals: list[float] = []
        power_vals: list[float] = []

        for bd in breath_data:
            t = getattr(bd, "t_sec", None)
            vo2 = getattr(bd, "vo2", None)
            power = getattr(bd, "bike_power", None)

            if t is None or vo2 is None:
                continue
            if math.isnan(t) or math.isnan(vo2):
                continue

            t_vals.append(float(t))
            vo2_vals.append(float(vo2))
            power_vals.append(float(power) if power is not None and not math.isnan(power) else 0.0)

        return (
            np.array(t_vals),
            np.array(vo2_vals),
            np.array(power_vals),
        )

    def _detect_analysis_window(
        self,
        t_sec: np.ndarray,
        power: np.ndarray,
        manual_start: Optional[float],
        manual_end: Optional[float],
    ) -> Tuple[float, float]:
        """Detect exercise analysis window.

        Uses manual overrides if provided, otherwise auto-detects
        based on power data.

        Args:
            t_sec: Time array
            power: Power array
            manual_start: Optional manual start time
            manual_end: Optional manual end time

        Returns:
            Tuple of (start_sec, end_sec)
        """
        if manual_start is not None and manual_end is not None:
            return manual_start, manual_end

        # Auto-detect: find where power > 0 sustained
        if len(power) == 0:
            return float(t_sec[0]), float(t_sec[-1])

        # Exercise start: first point where power > 20W
        power_above = np.where(power > 20)[0]
        if len(power_above) == 0:
            start = float(t_sec[0])
        else:
            start = float(t_sec[power_above[0]])

        # Exercise end: last point before power drops (use peak power time + short buffer)
        peak_idx = int(np.argmax(power))
        # Find where power drops to < 20% of peak after peak
        peak_power = power[peak_idx]
        if peak_power > 0:
            post_peak = power[peak_idx:]
            dropout_idx = np.where(post_peak < peak_power * 0.2)[0]
            if len(dropout_idx) > 0:
                end = float(t_sec[peak_idx + dropout_idx[0]])
            else:
                end = float(t_sec[-1])
        else:
            end = float(t_sec[-1])

        if manual_start is not None:
            start = manual_start
        if manual_end is not None:
            end = manual_end

        return start, end

    def _detect_recovery_window(
        self,
        t_sec: np.ndarray,
        power: np.ndarray,
        exercise_end_sec: float,
        override: Optional[RecoveryWindow],
    ) -> Optional[RecoveryWindow]:
        """Detect recovery phase window using power dropout.

        Recovery is detected as the period after exercise_end_sec where
        power drops significantly. Does NOT rely on breath_by_breath.phase
        column (which is NULL in real data).

        Args:
            t_sec: Time array
            power: Power array
            exercise_end_sec: Exercise end time (seconds)
            override: Optional manual override

        Returns:
            RecoveryWindow or None if recovery phase not detected/too short
        """
        if override is not None:
            return override

        # Find data after exercise end
        post_exercise_mask = t_sec > exercise_end_sec
        post_t = t_sec[post_exercise_mask]
        post_power = power[post_exercise_mask]

        if len(post_t) < 10:
            return None

        # Recovery starts where power drops to < 30W after exercise
        low_power_mask = post_power < 30
        if not np.any(low_power_mask):
            return None

        recovery_start_idx = np.where(low_power_mask)[0][0]
        recovery_start = float(post_t[recovery_start_idx])
        recovery_end = float(post_t[-1])

        # Need at least 30 seconds of recovery data
        if recovery_end - recovery_start < 30:
            return None

        # Cap recovery window at 5 minutes (300s) for better fit
        recovery_end = min(recovery_end, recovery_start + 300)

        return RecoveryWindow(
            start_sec=recovery_start,
            end_sec=recovery_end,
        )

    def _calculate_percentages(self, result: EnergySystemResult) -> None:
        """Calculate pathway percentages from kJ values."""
        components: list[float] = []

        if result.oxidative_kj is not None:
            components.append(result.oxidative_kj)
        if result.has_lactate and result.glycolytic_kj is not None:
            components.append(result.glycolytic_kj)
        if result.has_phosphagen and result.phosphagen_kj is not None:
            components.append(result.phosphagen_kj)

        total = sum(components)
        result.total_kj = total

        if total > 0:
            if result.oxidative_kj is not None:
                result.oxidative_pct = (result.oxidative_kj / total) * 100
            if result.has_lactate and result.glycolytic_kj is not None:
                result.glycolytic_pct = (result.glycolytic_kj / total) * 100
            if result.has_phosphagen and result.phosphagen_kj is not None:
                result.phosphagen_pct = (result.phosphagen_kj / total) * 100
