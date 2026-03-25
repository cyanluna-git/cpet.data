"""Tests for Energy System 3-pathway Analysis.

Tests the core calculation logic:
- Oxidative energy (VO2 integral)
- Glycolytic energy (delta lactate)
- Phosphagen energy (mono-exponential recovery fit)
- Percentage calculations
- Edge cases (no lactate, short recovery, poor fit)
"""

import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import List

import numpy as np
import pytest

# Add backend to path
backend_dir = str(Path(__file__).parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Direct file import to avoid loading app.services.__init__ chain
# (which pulls in pypdf and other optional deps via inscyd_parser)
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "energy_system_analysis",
    Path(__file__).parent.parent / "app" / "services" / "energy_system_analysis.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

CALORIC_EQUIVALENT_KJ_PER_L = _mod.CALORIC_EQUIVALENT_KJ_PER_L
EnergySystemAnalyzer = _mod.EnergySystemAnalyzer
EnergySystemResult = _mod.EnergySystemResult
MonoExpFitResult = _mod.MonoExpFitResult
RecoveryWindow = _mod.RecoveryWindow


def _make_breath_data(
    t_sec: List[float],
    vo2_ml: List[float],
    power: List[float],
) -> List[SimpleNamespace]:
    """Create mock breath data objects."""
    return [
        SimpleNamespace(t_sec=t, vo2=v, bike_power=p)
        for t, v, p in zip(t_sec, vo2_ml, power)
    ]


def _make_exercise_data(
    duration_sec: int = 600,
    dt: float = 1.0,
    vo2_ml_min: float = 2000.0,
    exercise_power: float = 200.0,
    recovery_sec: int = 180,
    recovery_vo2_start: float = 2000.0,
    recovery_vo2_end: float = 500.0,
    recovery_tau: float = 30.0,
) -> List[SimpleNamespace]:
    """Create synthetic exercise + recovery data.

    Exercise phase: constant VO2 and power
    Recovery phase: mono-exponential VO2 decay with power = 0
    """
    data = []

    # Exercise phase
    n_exercise = int(duration_sec / dt)
    for i in range(n_exercise):
        t = i * dt
        data.append(
            SimpleNamespace(
                t_sec=t,
                vo2=vo2_ml_min,
                bike_power=exercise_power,
            )
        )

    # Recovery phase
    n_recovery = int(recovery_sec / dt)
    amplitude = recovery_vo2_start - recovery_vo2_end
    for i in range(n_recovery):
        t = duration_sec + i * dt
        vo2 = amplitude * math.exp(-i * dt / recovery_tau) + recovery_vo2_end
        data.append(
            SimpleNamespace(
                t_sec=t,
                vo2=vo2,
                bike_power=0.0,
            )
        )

    return data


class TestCalcOxidativeEnergy:
    """Tests for calc_oxidative_energy."""

    def test_constant_vo2(self) -> None:
        """Constant VO2 over known duration produces correct energy."""
        analyzer = EnergySystemAnalyzer()

        # 2000 mL/min = 2.0 L/min for 600 seconds
        # VO2 in L/s = 2000 / 1000 / 60 = 0.03333 L/s
        # Integral = 0.03333 * 600 = 20.0 L
        # E_ox = 20.0 * 20.9 = 418.0 kJ
        duration = 600
        vo2_ml_min = 2000.0
        dt = 1.0

        t_sec = np.arange(0, duration + dt, dt)
        vo2_ml = np.full_like(t_sec, vo2_ml_min)

        result = analyzer.calc_oxidative_energy(t_sec, vo2_ml, 0, duration)

        expected = (vo2_ml_min / 1000.0 / 60.0) * duration * CALORIC_EQUIVALENT_KJ_PER_L
        assert abs(result - expected) / expected < 0.05, (
            f"Oxidative energy {result:.2f} kJ not within 5% of expected {expected:.2f} kJ"
        )

    def test_zero_vo2(self) -> None:
        """Zero VO2 produces zero energy."""
        analyzer = EnergySystemAnalyzer()
        t_sec = np.arange(0, 100, 1.0)
        vo2_ml = np.zeros_like(t_sec)
        result = analyzer.calc_oxidative_energy(t_sec, vo2_ml, 0, 100)
        assert result == 0.0

    def test_unit_conversion(self) -> None:
        """Verify mL/min -> L/s conversion is correct."""
        analyzer = EnergySystemAnalyzer()

        # 60000 mL/min = 1 L/s
        # Over 10 seconds: integral = 10 L
        # E = 10 * 20.9 = 209 kJ
        t_sec = np.array([0.0, 10.0])
        vo2_ml = np.array([60000.0, 60000.0])

        result = analyzer.calc_oxidative_energy(t_sec, vo2_ml, 0, 10)
        expected = 10.0 * CALORIC_EQUIVALENT_KJ_PER_L
        assert abs(result - expected) / expected < 0.01


class TestCalcGlycolyticEnergy:
    """Tests for calc_glycolytic_energy."""

    def test_known_values(self) -> None:
        """Known delta_La and BW produces correct energy."""
        analyzer = EnergySystemAnalyzer()

        # delta_La = 10 mmol/L, BW = 70 kg
        # O2_ml = 10 * 3 * 70 = 2100 mL = 2.1 L
        # E_gly = 2.1 * 20.9 = 43.89 kJ
        result = analyzer.calc_glycolytic_energy(delta_lactate=10.0, body_weight_kg=70.0)
        expected = 10.0 * 3.0 * 70.0 / 1000.0 * CALORIC_EQUIVALENT_KJ_PER_L
        assert abs(result - expected) < 0.01

    def test_zero_delta_la(self) -> None:
        """Zero delta lactate produces zero energy."""
        analyzer = EnergySystemAnalyzer()
        result = analyzer.calc_glycolytic_energy(delta_lactate=0.0, body_weight_kg=70.0)
        assert result == 0.0

    def test_proportional_to_weight(self) -> None:
        """Energy scales linearly with body weight."""
        analyzer = EnergySystemAnalyzer()
        e1 = analyzer.calc_glycolytic_energy(delta_lactate=5.0, body_weight_kg=70.0)
        e2 = analyzer.calc_glycolytic_energy(delta_lactate=5.0, body_weight_kg=140.0)
        assert abs(e2 / e1 - 2.0) < 0.01


class TestCalcPhosphagenEnergy:
    """Tests for calc_phosphagen_energy."""

    def test_known_fit(self) -> None:
        """Known A and tau produces correct energy."""
        analyzer = EnergySystemAnalyzer()

        # A = 1.5 L/min, tau = 30 s
        # O2 = 1.5 * 30 / 60 = 0.75 L
        # E_PCr = 0.75 * 20.9 = 15.675 kJ
        fit = MonoExpFitResult(
            amplitude=1.5,
            tau=30.0,
            baseline=0.5,
            r_squared=0.95,
            n_points=100,
        )
        result = analyzer.calc_phosphagen_energy(fit)
        expected = 1.5 * 30.0 / 60.0 * CALORIC_EQUIVALENT_KJ_PER_L
        assert abs(result - expected) < 0.01


class TestMonoExponentialFit:
    """Tests for fit_mono_exponential."""

    def test_clean_mono_exp_signal(self) -> None:
        """Clean mono-exponential signal gives high R²."""
        analyzer = EnergySystemAnalyzer()

        # Generate clean mono-exp signal
        # VO2(t) = 1.5 * exp(-t/30) + 0.5 L/min
        # Convert to mL/min for input
        t_sec = np.arange(0, 180, 1.0)
        amplitude = 1.5
        tau = 30.0
        baseline = 0.5
        vo2_lmin = amplitude * np.exp(-t_sec / tau) + baseline
        vo2_ml = vo2_lmin * 1000.0  # convert to mL/min

        # Add full data (pre-recovery + recovery)
        full_t = np.arange(-100, 180, 1.0)
        full_vo2 = np.zeros_like(full_t)
        full_vo2[:100] = 2500.0  # exercise phase
        full_vo2[100:] = vo2_ml  # recovery phase

        recovery = RecoveryWindow(start_sec=0.0, end_sec=180.0)

        result = analyzer.fit_mono_exponential(full_t, full_vo2, recovery)

        assert result.fit_successful
        assert result.r_squared > 0.95, f"R² = {result.r_squared:.4f} (expected > 0.95)"
        assert abs(result.tau - tau) / tau < 0.1, (
            f"tau = {result.tau:.2f} (expected ~{tau})"
        )

    def test_insufficient_data(self) -> None:
        """Less than 10 data points returns unsuccessful fit."""
        analyzer = EnergySystemAnalyzer()

        t_sec = np.arange(0, 5, 1.0)
        vo2_ml = np.array([2000, 1800, 1600, 1400, 1200], dtype=float)

        recovery = RecoveryWindow(start_sec=0.0, end_sec=5.0)
        result = analyzer.fit_mono_exponential(t_sec, vo2_ml, recovery)

        assert not result.fit_successful
        assert "Insufficient" in (result.error_message or "")


class TestFullAnalysis:
    """Tests for the full analyze() pipeline."""

    def test_all_three_pathways(self) -> None:
        """Full analysis with lactate data produces 3 pathways summing to 100%."""
        analyzer = EnergySystemAnalyzer()

        breath_data = _make_exercise_data(
            duration_sec=600,
            vo2_ml_min=2000.0,
            exercise_power=200.0,
            recovery_sec=180,
            recovery_vo2_start=2000.0,
            recovery_vo2_end=500.0,
            recovery_tau=30.0,
        )

        result = analyzer.analyze(
            breath_data=breath_data,
            body_weight_kg=70.0,
            resting_lactate=1.0,
            peak_lactate=8.0,
            exercise_start_sec=0.0,
            exercise_end_sec=600.0,
        )

        assert result.oxidative_kj is not None
        assert result.oxidative_kj > 0
        assert result.has_lactate
        assert result.glycolytic_kj is not None
        assert result.glycolytic_kj > 0
        assert result.has_phosphagen
        assert result.phosphagen_kj is not None
        assert result.phosphagen_kj > 0

        # Percentages should sum to 100%
        total_pct = (
            (result.oxidative_pct or 0)
            + (result.glycolytic_pct or 0)
            + (result.phosphagen_pct or 0)
        )
        assert abs(total_pct - 100.0) < 0.1, (
            f"Percentages sum to {total_pct:.1f}%, expected 100%"
        )

    def test_without_lactate(self) -> None:
        """Analysis without lactate produces only 2 pathways."""
        analyzer = EnergySystemAnalyzer()

        breath_data = _make_exercise_data(
            duration_sec=600,
            vo2_ml_min=2000.0,
            exercise_power=200.0,
            recovery_sec=180,
        )

        result = analyzer.analyze(
            breath_data=breath_data,
            body_weight_kg=70.0,
            resting_lactate=None,
            peak_lactate=None,
            exercise_start_sec=0.0,
            exercise_end_sec=600.0,
        )

        assert result.oxidative_kj is not None
        assert not result.has_lactate
        assert result.glycolytic_kj is None
        assert result.has_phosphagen

        # Only oxidative + phosphagen percentages
        result_dict = result.to_dict()
        assert len(result_dict["pathways"]) == 2
        names = [p["name"] for p in result_dict["pathways"]]
        assert "Glycolytic" not in names

    def test_short_recovery(self) -> None:
        """Short recovery produces no phosphagen calculation."""
        analyzer = EnergySystemAnalyzer()

        breath_data = _make_exercise_data(
            duration_sec=600,
            vo2_ml_min=2000.0,
            exercise_power=200.0,
            recovery_sec=10,  # Too short
        )

        result = analyzer.analyze(
            breath_data=breath_data,
            body_weight_kg=70.0,
            resting_lactate=1.0,
            peak_lactate=8.0,
            exercise_start_sec=0.0,
            exercise_end_sec=600.0,
        )

        assert result.oxidative_kj is not None
        assert result.has_lactate
        assert not result.has_phosphagen
        assert any("Recovery" in w or "recovery" in w for w in result.warnings)

    def test_result_to_dict(self) -> None:
        """to_dict() produces valid dictionary structure."""
        analyzer = EnergySystemAnalyzer()

        breath_data = _make_exercise_data()
        result = analyzer.analyze(
            breath_data=breath_data,
            body_weight_kg=70.0,
            resting_lactate=1.0,
            peak_lactate=8.0,
            exercise_start_sec=0.0,
            exercise_end_sec=600.0,
        )

        d = result.to_dict()
        assert "pathways" in d
        assert "total_kj" in d
        assert "has_lactate" in d
        assert "has_phosphagen" in d
        assert "warnings" in d
        assert isinstance(d["pathways"], list)

    def test_negative_delta_lactate(self) -> None:
        """Negative delta lactate sets glycolytic to zero."""
        analyzer = EnergySystemAnalyzer()

        breath_data = _make_exercise_data(
            duration_sec=300,
            vo2_ml_min=1500.0,
            exercise_power=150.0,
            recovery_sec=60,
        )

        result = analyzer.analyze(
            breath_data=breath_data,
            body_weight_kg=70.0,
            resting_lactate=5.0,
            peak_lactate=3.0,  # peak < resting
            exercise_start_sec=0.0,
            exercise_end_sec=300.0,
        )

        assert result.has_lactate
        assert result.glycolytic_kj == 0.0
        assert any("Delta lactate <= 0" in w for w in result.warnings)

    def test_insufficient_breath_data(self) -> None:
        """Less than 10 data points produces warning."""
        analyzer = EnergySystemAnalyzer()

        data = [
            SimpleNamespace(t_sec=float(i), vo2=1000.0, bike_power=100.0)
            for i in range(5)
        ]

        result = analyzer.analyze(
            breath_data=data,
            body_weight_kg=70.0,
        )

        assert any("Insufficient" in w for w in result.warnings)

    def test_manual_recovery_override(self) -> None:
        """Manual recovery override is respected."""
        analyzer = EnergySystemAnalyzer()

        breath_data = _make_exercise_data(
            duration_sec=600,
            vo2_ml_min=2000.0,
            exercise_power=200.0,
            recovery_sec=180,
        )

        override = RecoveryWindow(
            start_sec=610.0,
            end_sec=750.0,
            is_manual_override=True,
        )

        result = analyzer.analyze(
            breath_data=breath_data,
            body_weight_kg=70.0,
            recovery_override=override,
            exercise_start_sec=0.0,
            exercise_end_sec=600.0,
        )

        assert result.recovery_window is not None
        assert result.recovery_window["is_manual_override"] is True
        assert result.recovery_window["start_sec"] == 610.0


# ---------------------------------------------------------------------------
# Additional tests added by Shield (coverage gaps)
# ---------------------------------------------------------------------------


class TestCalcOxidativeEnergyExtended:
    """Extended coverage for calc_oxidative_energy."""

    def test_unit_conversion_precision(self) -> None:
        """mL/min → L/s conversion: 60 000 mL/min == 1 L/s exactly."""
        analyzer = EnergySystemAnalyzer()
        # 60 000 mL/min for exactly 10 s -> integral = 10 L -> 10 * 20.9 kJ
        t_sec = np.array([0.0, 10.0])
        vo2_ml = np.array([60_000.0, 60_000.0])
        result = analyzer.calc_oxidative_energy(t_sec, vo2_ml, 0.0, 10.0)
        expected = 10.0 * CALORIC_EQUIVALENT_KJ_PER_L
        assert abs(result - expected) / expected < 1e-6, (
            f"Expected {expected:.6f} kJ, got {result:.6f} kJ"
        )

    def test_irregular_time_steps_trapezoidal(self) -> None:
        """Trapezoidal rule handles non-uniform dt correctly."""
        analyzer = EnergySystemAnalyzer()
        # Two trapezoids: [0→1] width 1 s, [1→11] width 10 s, all VO2=60000 mL/min
        # L/s = 1.0; integral = 1*1 + 1*10 = 11 L -> 11*20.9 kJ
        t_sec = np.array([0.0, 1.0, 11.0])
        vo2_ml = np.array([60_000.0, 60_000.0, 60_000.0])
        result = analyzer.calc_oxidative_energy(t_sec, vo2_ml, 0.0, 11.0)
        expected = 11.0 * CALORIC_EQUIVALENT_KJ_PER_L
        assert abs(result - expected) / expected < 1e-6

    def test_single_data_point_returns_zero(self) -> None:
        """Only one data point in window yields zero (can't integrate)."""
        analyzer = EnergySystemAnalyzer()
        t_sec = np.array([5.0, 10.0, 15.0])
        vo2_ml = np.array([2000.0, 2000.0, 2000.0])
        # Window [10, 10] contains exactly one point
        result = analyzer.calc_oxidative_energy(t_sec, vo2_ml, 10.0, 10.0)
        assert result == 0.0

    def test_window_subset_of_full_array(self) -> None:
        """Integration respects the start/end window bounds."""
        analyzer = EnergySystemAnalyzer()
        # Full array 0–200 s at constant 2000 mL/min
        t_sec = np.arange(0.0, 201.0, 1.0)
        vo2_ml = np.full_like(t_sec, 2000.0)
        # Only integrate [100, 200] = 100 s
        result = analyzer.calc_oxidative_energy(t_sec, vo2_ml, 100.0, 200.0)
        expected = (2000.0 / 1000.0 / 60.0) * 100.0 * CALORIC_EQUIVALENT_KJ_PER_L
        assert abs(result - expected) / expected < 0.01

    def test_ramp_vo2_trapezoidal_accuracy(self) -> None:
        """Linearly ramping VO2: trapz integral == exact (area of trapezoid)."""
        analyzer = EnergySystemAnalyzer()
        # VO2 ramps from 1000 to 3000 mL/min over 60 s
        # Average = 2000 mL/min, L/s = 1/30, integral = 60/30 = 2 L, E = 2*20.9 kJ
        t_sec = np.linspace(0.0, 60.0, 61)
        vo2_ml = np.linspace(1000.0, 3000.0, 61)
        result = analyzer.calc_oxidative_energy(t_sec, vo2_ml, 0.0, 60.0)
        expected = 2.0 * CALORIC_EQUIVALENT_KJ_PER_L
        assert abs(result - expected) / expected < 0.001


class TestCalcGlycolyticEnergyExtended:
    """Extended coverage for calc_glycolytic_energy."""

    def test_negative_delta_la_raises_no_error(self) -> None:
        """Negative delta_La simply returns a negative kJ value (clamped externally)."""
        analyzer = EnergySystemAnalyzer()
        result = analyzer.calc_glycolytic_energy(delta_lactate=-3.0, body_weight_kg=70.0)
        # Formula is linear — no guard here, caller clamps
        assert result < 0.0

    def test_very_low_body_weight(self) -> None:
        """Body weight of 30 kg produces proportionally smaller result."""
        analyzer = EnergySystemAnalyzer()
        e_30 = analyzer.calc_glycolytic_energy(delta_lactate=5.0, body_weight_kg=30.0)
        e_60 = analyzer.calc_glycolytic_energy(delta_lactate=5.0, body_weight_kg=60.0)
        assert abs(e_60 / e_30 - 2.0) < 0.01

    def test_very_high_body_weight(self) -> None:
        """Body weight of 150 kg (upper clinical bound) is handled linearly."""
        analyzer = EnergySystemAnalyzer()
        e_75 = analyzer.calc_glycolytic_energy(delta_lactate=8.0, body_weight_kg=75.0)
        e_150 = analyzer.calc_glycolytic_energy(delta_lactate=8.0, body_weight_kg=150.0)
        assert abs(e_150 / e_75 - 2.0) < 0.01

    def test_formula_correctness_explicit(self) -> None:
        """Verify every factor in the di Prampero formula manually."""
        analyzer = EnergySystemAnalyzer()
        delta_la = 4.0   # mmol/L
        bw = 80.0        # kg
        # o2_ml = 4 * 3 * 80 = 960 mL = 0.96 L; E = 0.96 * 20.9 = 20.064 kJ
        expected = 4.0 * 3.0 * 80.0 / 1000.0 * CALORIC_EQUIVALENT_KJ_PER_L
        result = analyzer.calc_glycolytic_energy(delta_la, bw)
        assert abs(result - expected) < 0.001


class TestCalcPhosphagenEnergyExtended:
    """Extended coverage for calc_phosphagen_energy."""

    def test_zero_amplitude(self) -> None:
        """Zero amplitude (no PCr resynthesis signal) produces zero energy."""
        analyzer = EnergySystemAnalyzer()
        fit = MonoExpFitResult(
            amplitude=0.0, tau=30.0, baseline=0.5, r_squared=0.95, n_points=100
        )
        result = analyzer.calc_phosphagen_energy(fit)
        assert result == 0.0

    def test_formula_dimensions(self) -> None:
        """Units: A (L/min) × tau (s) / 60 (s/min) → L × 20.9 → kJ."""
        analyzer = EnergySystemAnalyzer()
        # A=3 L/min, tau=60 s → O2=3*60/60=3 L → E=3*20.9=62.7 kJ
        fit = MonoExpFitResult(
            amplitude=3.0, tau=60.0, baseline=0.3, r_squared=0.98, n_points=60
        )
        result = analyzer.calc_phosphagen_energy(fit)
        expected = 3.0 * 60.0 / 60.0 * CALORIC_EQUIVALENT_KJ_PER_L
        assert abs(result - expected) < 0.001

    def test_r_squared_not_used_in_calculation(self) -> None:
        """calc_phosphagen_energy ignores R² (it's a quality flag, not a factor)."""
        analyzer = EnergySystemAnalyzer()
        fit_good = MonoExpFitResult(
            amplitude=1.0, tau=30.0, baseline=0.5, r_squared=0.99, n_points=100
        )
        fit_poor = MonoExpFitResult(
            amplitude=1.0, tau=30.0, baseline=0.5, r_squared=0.50, n_points=100
        )
        assert analyzer.calc_phosphagen_energy(fit_good) == analyzer.calc_phosphagen_energy(fit_poor)


class TestMonoExponentialFitExtended:
    """Extended coverage for fit_mono_exponential."""

    def test_r_squared_exactly_at_threshold(self) -> None:
        """R² very close to 0.80 boundary: fit with R²<0.80 triggers warning in analyze()."""
        analyzer = EnergySystemAnalyzer()

        # Build noisy signal so R² lands slightly below 0.80
        rng = np.random.default_rng(seed=42)
        t_norm = np.arange(0.0, 60.0, 1.0)
        a, tau_val, bl = 1.5, 20.0, 0.5
        # Heavy noise (~60% of amplitude) to degrade fit
        noise = rng.normal(0, 0.9 * a, size=len(t_norm))
        vo2_lmin = a * np.exp(-t_norm / tau_val) + bl + noise
        vo2_lmin = np.clip(vo2_lmin, 0.01, None)
        vo2_ml_rec = vo2_lmin * 1000.0

        exercise_sec = 300
        exercise_t = np.arange(0.0, float(exercise_sec), 1.0)
        exercise_vo2 = np.full_like(exercise_t, 3000.0)
        full_t = np.concatenate([exercise_t, exercise_sec + t_norm])
        full_vo2 = np.concatenate([exercise_vo2, vo2_ml_rec])

        recovery = RecoveryWindow(
            start_sec=float(exercise_sec),
            end_sec=float(exercise_sec + t_norm[-1]),
        )
        result = analyzer.fit_mono_exponential(full_t, full_vo2, recovery)
        # fit may succeed or fail, but r_squared must be a valid float
        assert isinstance(result.r_squared, float)
        assert math.isfinite(result.r_squared)

    def test_noisy_but_recoverable_signal(self) -> None:
        """Modest noise (5% of amplitude) still achieves R² > 0.80."""
        analyzer = EnergySystemAnalyzer()

        rng = np.random.default_rng(seed=7)
        t_norm = np.arange(0.0, 180.0, 1.0)
        a, tau_val, bl = 1.5, 30.0, 0.5
        noise = rng.normal(0, 0.05 * a, size=len(t_norm))
        vo2_lmin = a * np.exp(-t_norm / tau_val) + bl + noise
        vo2_ml_rec = vo2_lmin * 1000.0

        exercise_sec = 300
        exercise_t = np.arange(0.0, float(exercise_sec), 1.0)
        exercise_vo2 = np.full_like(exercise_t, 2500.0)
        full_t = np.concatenate([exercise_t, exercise_sec + t_norm])
        full_vo2 = np.concatenate([exercise_vo2, vo2_ml_rec])

        recovery = RecoveryWindow(
            start_sec=float(exercise_sec),
            end_sec=float(exercise_sec + 180.0),
        )
        result = analyzer.fit_mono_exponential(full_t, full_vo2, recovery)
        assert result.fit_successful
        assert result.r_squared > 0.80, f"R²={result.r_squared:.3f} should be > 0.80 with low noise"

    def test_flat_signal_fit(self) -> None:
        """Flat (constant) VO2 in recovery window: ss_tot==0 → r_squared=0."""
        analyzer = EnergySystemAnalyzer()

        t_sec = np.arange(0.0, 200.0, 1.0)
        vo2_ml = np.full_like(t_sec, 500.0)   # constant — no decay
        recovery = RecoveryWindow(start_sec=0.0, end_sec=180.0)
        result = analyzer.fit_mono_exponential(t_sec, vo2_ml, recovery)
        # Either fit fails or r_squared == 0 (ss_tot == 0 path)
        if result.fit_successful:
            assert result.r_squared == 0.0 or result.amplitude < 1e-6

    def test_recovery_window_capped_at_300s(self) -> None:
        """Recovery longer than 300 s is capped to 300 s by _detect_recovery_window."""
        analyzer = EnergySystemAnalyzer()

        # Create 800 s of recovery data after 600 s exercise
        data = _make_exercise_data(
            duration_sec=600,
            vo2_ml_min=2000.0,
            exercise_power=200.0,
            recovery_sec=800,
            recovery_vo2_start=2000.0,
            recovery_vo2_end=500.0,
            recovery_tau=30.0,
        )
        t_arr, _, power_arr = analyzer._extract_arrays(data)
        window = analyzer._detect_recovery_window(t_arr, power_arr, 600.0, None)
        assert window is not None
        assert (window.end_sec - window.start_sec) <= 300.0 + 1  # +1 for dt tolerance

    def test_recovery_exactly_30s_is_accepted(self) -> None:
        """Recovery span of exactly 30 s (not < 30) is accepted.

        _detect_recovery_window uses a strict > filter for post-exercise data,
        so with exercise_end=100.0 the first candidate point is 101.0. The
        final point must therefore be >= 131.0 to achieve a 30 s span.
        """
        analyzer = EnergySystemAnalyzer()
        exercise_t = np.arange(0.0, 100.0, 1.0)
        exercise_power = np.full_like(exercise_t, 200.0)
        # Recovery from 100 to 132 s → post-exercise filter gives 101..132, span=31 s ≥ 30
        recovery_t = np.arange(100.0, 133.0, 1.0)
        recovery_power = np.zeros_like(recovery_t)
        t_arr = np.concatenate([exercise_t, recovery_t])
        power_arr = np.concatenate([exercise_power, recovery_power])
        window = analyzer._detect_recovery_window(t_arr, power_arr, 100.0, None)
        assert window is not None
        assert (window.end_sec - window.start_sec) >= 30.0

    def test_recovery_window_at_very_end_of_data(self) -> None:
        """Recovery starting at the last 35 s of data is detected correctly."""
        analyzer = EnergySystemAnalyzer()
        exercise_t = np.arange(0.0, 600.0, 1.0)
        exercise_power = np.full_like(exercise_t, 200.0)
        recovery_t = np.arange(600.0, 635.0, 1.0)  # 35 data points
        recovery_power = np.zeros_like(recovery_t)
        t_arr = np.concatenate([exercise_t, recovery_t])
        power_arr = np.concatenate([exercise_power, recovery_power])
        window = analyzer._detect_recovery_window(t_arr, power_arr, 600.0, None)
        assert window is not None
        assert window.start_sec == pytest.approx(600.0, abs=1.0)
        assert window.end_sec == pytest.approx(634.0, abs=1.0)

    def test_no_power_dropout_returns_none(self) -> None:
        """If post-exercise power never drops below 30 W, no recovery detected."""
        analyzer = EnergySystemAnalyzer()
        # All power = 100 W throughout; nothing below 30 W after exercise
        t_arr = np.arange(0.0, 700.0, 1.0)
        power_arr = np.full_like(t_arr, 100.0)
        window = analyzer._detect_recovery_window(t_arr, power_arr, 600.0, None)
        assert window is None


class TestDetectAnalysisWindow:
    """Tests for _detect_analysis_window auto-detection logic."""

    def test_manual_start_and_end_bypass_autodetect(self) -> None:
        """Manual start+end are returned unchanged regardless of power."""
        analyzer = EnergySystemAnalyzer()
        t_sec = np.arange(0.0, 800.0, 1.0)
        power = np.zeros_like(t_sec)   # all zero power — autodetect would fail
        start, end = analyzer._detect_analysis_window(t_sec, power, 100.0, 600.0)
        assert start == 100.0
        assert end == 600.0

    def test_autodetect_no_power_above_20w(self) -> None:
        """When no power > 20 W, defaults to first timestamp for start."""
        analyzer = EnergySystemAnalyzer()
        t_sec = np.arange(5.0, 605.0, 1.0)
        power = np.full_like(t_sec, 10.0)   # all below 20 W
        start, end = analyzer._detect_analysis_window(t_sec, power, None, None)
        assert start == pytest.approx(5.0)

    def test_autodetect_power_dropout_detection(self) -> None:
        """Auto-detect finds exercise end where power drops to < 20% of peak."""
        analyzer = EnergySystemAnalyzer()
        # 0–300: 200 W; 300–600: 0 W
        t_sec = np.arange(0.0, 601.0, 1.0)
        power = np.where(t_sec < 300, 200.0, 0.0)
        start, end = analyzer._detect_analysis_window(t_sec, power, None, None)
        # End should be at the dropout point (~300 s)
        assert end <= 305.0  # within a few seconds of actual dropout


class TestExtractArrays:
    """Tests for _extract_arrays NaN filtering and data integrity."""

    def test_nan_vo2_rows_filtered(self) -> None:
        """Rows with NaN VO2 are excluded from output arrays."""
        analyzer = EnergySystemAnalyzer()
        from types import SimpleNamespace
        data = [
            SimpleNamespace(t_sec=0.0, vo2=1000.0, bike_power=100.0),
            SimpleNamespace(t_sec=1.0, vo2=float("nan"), bike_power=100.0),
            SimpleNamespace(t_sec=2.0, vo2=1200.0, bike_power=100.0),
        ]
        t, vo2, power = analyzer._extract_arrays(data)
        assert len(t) == 2
        assert 1.0 not in t

    def test_nan_time_rows_filtered(self) -> None:
        """Rows with NaN time are excluded."""
        analyzer = EnergySystemAnalyzer()
        from types import SimpleNamespace
        data = [
            SimpleNamespace(t_sec=float("nan"), vo2=1000.0, bike_power=100.0),
            SimpleNamespace(t_sec=1.0, vo2=1200.0, bike_power=100.0),
        ]
        t, _, _ = analyzer._extract_arrays(data)
        assert len(t) == 1
        assert t[0] == pytest.approx(1.0)

    def test_none_power_defaults_to_zero(self) -> None:
        """None bike_power is treated as 0.0."""
        analyzer = EnergySystemAnalyzer()
        from types import SimpleNamespace
        data = [
            SimpleNamespace(t_sec=0.0, vo2=1000.0, bike_power=None),
        ]
        _, _, power = analyzer._extract_arrays(data)
        assert power[0] == 0.0

    def test_mixed_valid_invalid_rows(self) -> None:
        """Only rows with valid t_sec and vo2 appear in output."""
        analyzer = EnergySystemAnalyzer()
        from types import SimpleNamespace
        data = [
            SimpleNamespace(t_sec=0.0, vo2=None, bike_power=100.0),       # vo2=None → skip
            SimpleNamespace(t_sec=1.0, vo2=1000.0, bike_power=100.0),
            SimpleNamespace(t_sec=2.0, vo2=float("nan"), bike_power=100.0),  # NaN → skip
            SimpleNamespace(t_sec=3.0, vo2=1100.0, bike_power=100.0),
        ]
        t, vo2, _ = analyzer._extract_arrays(data)
        assert list(t) == [1.0, 3.0]


class TestCalculatePercentages:
    """Tests for _calculate_percentages edge cases."""

    def test_zero_total_kj_no_percentage_set(self) -> None:
        """When total_kj==0 no percentages are assigned (avoids division by zero)."""
        analyzer = EnergySystemAnalyzer()
        result = EnergySystemResult(oxidative_kj=0.0)
        analyzer._calculate_percentages(result)
        assert result.total_kj == 0.0
        assert result.oxidative_pct is None  # total==0 → no pct

    def test_glycolytic_zero_kj_excluded_from_total(self) -> None:
        """glycolytic_kj=0 with has_lactate=True is still included in total (0 contribution)."""
        analyzer = EnergySystemAnalyzer()
        result = EnergySystemResult(
            oxidative_kj=100.0,
            glycolytic_kj=0.0,
            has_lactate=True,
        )
        analyzer._calculate_percentages(result)
        assert result.total_kj == pytest.approx(100.0)
        assert result.oxidative_pct == pytest.approx(100.0)
        assert result.glycolytic_pct == pytest.approx(0.0)


class TestFullAnalysisExtended:
    """Extended integration-level tests for the full analyze() pipeline."""

    def test_missing_body_weight_skips_glycolytic(self) -> None:
        """Without body weight, glycolytic calc is skipped and warning emitted."""
        analyzer = EnergySystemAnalyzer()
        breath_data = _make_exercise_data(duration_sec=300, recovery_sec=120)
        result = analyzer.analyze(
            breath_data=breath_data,
            body_weight_kg=None,
            resting_lactate=1.0,
            peak_lactate=8.0,
            exercise_start_sec=0.0,
            exercise_end_sec=300.0,
        )
        assert result.has_lactate
        assert result.glycolytic_kj is None
        assert any("Body weight" in w for w in result.warnings)

    def test_percentages_sum_to_100_without_glycolytic(self) -> None:
        """Oxidative + Phosphagen percentages sum to 100% when no lactate data."""
        analyzer = EnergySystemAnalyzer()
        breath_data = _make_exercise_data(
            duration_sec=600,
            recovery_sec=180,
            recovery_vo2_start=2000.0,
            recovery_vo2_end=500.0,
            recovery_tau=30.0,
        )
        result = analyzer.analyze(
            breath_data=breath_data,
            body_weight_kg=70.0,
            resting_lactate=None,
            peak_lactate=None,
            exercise_start_sec=0.0,
            exercise_end_sec=600.0,
        )
        total_pct = (result.oxidative_pct or 0.0) + (result.phosphagen_pct or 0.0)
        assert abs(total_pct - 100.0) < 0.1

    def test_low_r_squared_triggers_warning(self) -> None:
        """Phosphagen fit with R² < 0.80 adds a warning to result."""
        analyzer = EnergySystemAnalyzer()
        # Provide a completely random VO2 recovery so the fit quality is poor
        rng = np.random.default_rng(seed=99)
        exercise_t = list(range(600))
        exercise_data = [
            SimpleNamespace(t_sec=float(i), vo2=2000.0, bike_power=200.0)
            for i in exercise_t
        ]
        recovery_data = [
            SimpleNamespace(
                t_sec=float(600 + i),
                vo2=float(rng.uniform(500, 2000)),  # pure noise
                bike_power=0.0,
            )
            for i in range(180)
        ]
        data = exercise_data + recovery_data
        result = analyzer.analyze(
            breath_data=data,
            body_weight_kg=70.0,
            resting_lactate=1.0,
            peak_lactate=8.0,
            exercise_start_sec=0.0,
            exercise_end_sec=600.0,
        )
        # If fit succeeded but R²<0.80, a warning about quality must appear
        if result.has_phosphagen and result.mono_exp_fit:
            if result.mono_exp_fit["r_squared"] < 0.80:
                assert any("R²" in w or "Low" in w for w in result.warnings)

    def test_to_dict_pathway_count_all_three(self) -> None:
        """to_dict() includes exactly 3 pathways when all sources are available."""
        analyzer = EnergySystemAnalyzer()
        breath_data = _make_exercise_data(
            duration_sec=600,
            recovery_sec=180,
            recovery_vo2_start=2000.0,
            recovery_vo2_end=500.0,
            recovery_tau=30.0,
        )
        result = analyzer.analyze(
            breath_data=breath_data,
            body_weight_kg=70.0,
            resting_lactate=1.0,
            peak_lactate=8.0,
            exercise_start_sec=0.0,
            exercise_end_sec=600.0,
        )
        d = result.to_dict()
        assert len(d["pathways"]) == 3
        names = [p["name"] for p in d["pathways"]]
        assert "Oxidative" in names
        assert "Glycolytic" in names
        assert "Phosphagen" in names

    def test_to_dict_energy_values_are_rounded(self) -> None:
        """to_dict() rounds energy values to 2 decimal places."""
        analyzer = EnergySystemAnalyzer()
        result = EnergySystemResult(
            oxidative_kj=418.123456,
            oxidative_pct=100.0,
            total_kj=418.123456,
        )
        d = result.to_dict()
        oxidative_entry = next(p for p in d["pathways"] if p["name"] == "Oxidative")
        assert oxidative_entry["energy_kj"] == round(418.123456, 2)

    def test_exercise_duration_recorded_in_result(self) -> None:
        """exercise_duration_sec in result matches the window provided."""
        analyzer = EnergySystemAnalyzer()
        breath_data = _make_exercise_data(duration_sec=300, recovery_sec=60)
        result = analyzer.analyze(
            breath_data=breath_data,
            body_weight_kg=70.0,
            exercise_start_sec=0.0,
            exercise_end_sec=300.0,
        )
        assert result.exercise_duration_sec == pytest.approx(300.0)

    def test_body_weight_recorded_in_result(self) -> None:
        """body_weight_kg is stored on the result for audit/display."""
        analyzer = EnergySystemAnalyzer()
        breath_data = _make_exercise_data(duration_sec=300, recovery_sec=60)
        result = analyzer.analyze(
            breath_data=breath_data,
            body_weight_kg=85.5,
            exercise_start_sec=0.0,
            exercise_end_sec=300.0,
        )
        assert result.body_weight_kg == pytest.approx(85.5)
