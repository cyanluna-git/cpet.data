"""Calculation Accuracy Tests for Energy System 3-pathway Analysis.

Verifies each formula against hardcoded reference values from the
professor's formulas (Beneke 2002 / di Prampero 1999).
Each result must be within +/-1% of the expected value.
"""

import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import List

import numpy as np
import pytest

# Direct file import to avoid loading full app.services chain
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "energy_system_analysis",
    Path(__file__).parent.parent / "app" / "services" / "energy_system_analysis.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

CALORIC_EQUIVALENT_KJ_PER_L = _mod.CALORIC_EQUIVALENT_KJ_PER_L
EnergySystemAnalyzer = _mod.EnergySystemAnalyzer
MonoExpFitResult = _mod.MonoExpFitResult
RecoveryWindow = _mod.RecoveryWindow


def _within_pct(actual: float, expected: float, tolerance_pct: float = 1.0) -> bool:
    """Check if actual is within tolerance_pct of expected."""
    if expected == 0:
        return actual == 0
    return abs(actual - expected) / abs(expected) * 100 <= tolerance_pct


class TestOxidativeAccuracy:
    """Oxidative energy formula: E_ox = integral(VO2 L/s * dt) * 20.9 kJ/L"""

    def test_reference_case(self) -> None:
        """VO2=2000 mL/min, 600s => E_ox = 418.0 kJ (+/-1%)."""
        analyzer = EnergySystemAnalyzer()

        vo2_ml_min = 2000.0
        duration = 600  # seconds

        # Expected: (2000/1000/60) * 600 * 20.9 = 0.03333 * 600 * 20.9 = 418.0 kJ
        expected_kj = (vo2_ml_min / 1000.0 / 60.0) * duration * CALORIC_EQUIVALENT_KJ_PER_L

        t_sec = np.arange(0, duration + 1, 1.0)
        vo2_ml = np.full_like(t_sec, vo2_ml_min)

        result = analyzer.calc_oxidative_energy(t_sec, vo2_ml, 0, duration)

        assert _within_pct(result, expected_kj, 1.0), (
            f"Oxidative: {result:.4f} kJ, expected {expected_kj:.4f} kJ "
            f"(error {abs(result - expected_kj) / expected_kj * 100:.2f}%)"
        )

    def test_high_vo2_athlete(self) -> None:
        """VO2=4500 mL/min (elite), 480s => check within 1%."""
        analyzer = EnergySystemAnalyzer()

        vo2_ml_min = 4500.0
        duration = 480

        expected_kj = (vo2_ml_min / 1000.0 / 60.0) * duration * CALORIC_EQUIVALENT_KJ_PER_L

        t_sec = np.arange(0, duration + 1, 1.0)
        vo2_ml = np.full_like(t_sec, vo2_ml_min)

        result = analyzer.calc_oxidative_energy(t_sec, vo2_ml, 0, duration)
        assert _within_pct(result, expected_kj, 1.0)

    def test_ramp_protocol(self) -> None:
        """Linearly ramping VO2 from 500 to 3500 mL/min over 600s.

        Average VO2 = 2000 mL/min => same as constant case.
        """
        analyzer = EnergySystemAnalyzer()

        duration = 600
        t_sec = np.arange(0, duration + 1, 1.0)
        vo2_ml = np.linspace(500.0, 3500.0, len(t_sec))

        # Exact trapezoidal integral: average = 2000 mL/min
        expected_kj = (2000.0 / 1000.0 / 60.0) * duration * CALORIC_EQUIVALENT_KJ_PER_L

        result = analyzer.calc_oxidative_energy(t_sec, vo2_ml, 0, duration)
        assert _within_pct(result, expected_kj, 1.0)


class TestGlycolyticAccuracy:
    """Glycolytic energy formula: E_gly = delta_La * 3 * BW / 1000 * 20.9 kJ/L"""

    def test_reference_case(self) -> None:
        """delta_La=10, BW=70 => E_gly = 43.89 kJ (+/-1%)."""
        analyzer = EnergySystemAnalyzer()

        delta_la = 10.0
        bw = 70.0

        # Expected: 10 * 3 * 70 / 1000 * 20.9 = 43.89 kJ
        expected_kj = delta_la * 3.0 * bw / 1000.0 * CALORIC_EQUIVALENT_KJ_PER_L

        result = analyzer.calc_glycolytic_energy(delta_lactate=delta_la, body_weight_kg=bw)

        assert _within_pct(result, expected_kj, 1.0), (
            f"Glycolytic: {result:.4f} kJ, expected {expected_kj:.4f} kJ "
            f"(error {abs(result - expected_kj) / expected_kj * 100:.2f}%)"
        )

    def test_low_lactate_response(self) -> None:
        """delta_La=2, BW=65 => check within 1%."""
        analyzer = EnergySystemAnalyzer()

        delta_la = 2.0
        bw = 65.0
        expected_kj = delta_la * 3.0 * bw / 1000.0 * CALORIC_EQUIVALENT_KJ_PER_L

        result = analyzer.calc_glycolytic_energy(delta_lactate=delta_la, body_weight_kg=bw)
        assert _within_pct(result, expected_kj, 1.0)

    def test_heavy_athlete(self) -> None:
        """delta_La=12, BW=100 => check within 1%."""
        analyzer = EnergySystemAnalyzer()

        delta_la = 12.0
        bw = 100.0
        expected_kj = delta_la * 3.0 * bw / 1000.0 * CALORIC_EQUIVALENT_KJ_PER_L

        result = analyzer.calc_glycolytic_energy(delta_lactate=delta_la, body_weight_kg=bw)
        assert _within_pct(result, expected_kj, 1.0)


class TestPhosphagenAccuracy:
    """Phosphagen energy formula: E_PCr = A * tau / 60 * 20.9 kJ/L"""

    def test_reference_case(self) -> None:
        """A=1.5 L/min, tau=30s => E_PCr = 15.675 kJ (+/-1%)."""
        analyzer = EnergySystemAnalyzer()

        amplitude = 1.5  # L/min
        tau = 30.0       # seconds

        # Expected: 1.5 * 30 / 60 * 20.9 = 0.75 * 20.9 = 15.675 kJ
        expected_kj = amplitude * tau / 60.0 * CALORIC_EQUIVALENT_KJ_PER_L

        fit = MonoExpFitResult(
            amplitude=amplitude,
            tau=tau,
            baseline=0.5,
            r_squared=0.95,
            n_points=100,
        )
        result = analyzer.calc_phosphagen_energy(fit)

        assert _within_pct(result, expected_kj, 1.0), (
            f"Phosphagen: {result:.4f} kJ, expected {expected_kj:.4f} kJ "
            f"(error {abs(result - expected_kj) / expected_kj * 100:.2f}%)"
        )

    def test_fast_recovery(self) -> None:
        """A=2.0, tau=20s (fast kinetics) => check within 1%."""
        analyzer = EnergySystemAnalyzer()

        amplitude = 2.0
        tau = 20.0
        expected_kj = amplitude * tau / 60.0 * CALORIC_EQUIVALENT_KJ_PER_L

        fit = MonoExpFitResult(
            amplitude=amplitude, tau=tau, baseline=0.4,
            r_squared=0.98, n_points=60,
        )
        result = analyzer.calc_phosphagen_energy(fit)
        assert _within_pct(result, expected_kj, 1.0)

    def test_slow_recovery(self) -> None:
        """A=1.0, tau=45s (slow kinetics) => check within 1%."""
        analyzer = EnergySystemAnalyzer()

        amplitude = 1.0
        tau = 45.0
        expected_kj = amplitude * tau / 60.0 * CALORIC_EQUIVALENT_KJ_PER_L

        fit = MonoExpFitResult(
            amplitude=amplitude, tau=tau, baseline=0.6,
            r_squared=0.92, n_points=120,
        )
        result = analyzer.calc_phosphagen_energy(fit)
        assert _within_pct(result, expected_kj, 1.0)


class TestFullPipelineAccuracy:
    """Full analysis pipeline accuracy: percentage distribution check."""

    def test_total_energy_equals_sum_of_pathways(self) -> None:
        """total_kj must equal sum of individual pathway kJ values."""
        analyzer = EnergySystemAnalyzer()

        # Build synthetic data with known parameters
        duration = 600
        vo2_ml_min = 2000.0
        dt = 1.0

        data = []
        # Exercise phase
        for i in range(duration):
            data.append(SimpleNamespace(
                t_sec=float(i), vo2=vo2_ml_min, bike_power=200.0,
            ))
        # Recovery phase (180s)
        amplitude = vo2_ml_min - 500.0
        for i in range(180):
            t = duration + i
            vo2 = amplitude * math.exp(-i / 30.0) + 500.0
            data.append(SimpleNamespace(
                t_sec=float(t), vo2=vo2, bike_power=0.0,
            ))

        result = analyzer.analyze(
            breath_data=data,
            body_weight_kg=70.0,
            resting_lactate=1.0,
            peak_lactate=8.0,
            exercise_start_sec=0.0,
            exercise_end_sec=float(duration),
        )

        assert result.total_kj is not None
        pathway_sum = (
            (result.oxidative_kj or 0.0)
            + (result.glycolytic_kj or 0.0)
            + (result.phosphagen_kj or 0.0)
        )

        assert _within_pct(result.total_kj, pathway_sum, 1.0), (
            f"total_kj={result.total_kj:.2f} != sum={pathway_sum:.2f}"
        )

    def test_oxidative_dominates(self) -> None:
        """For a 10-min constant effort, oxidative should be >80% of total."""
        analyzer = EnergySystemAnalyzer()

        duration = 600
        data = []
        for i in range(duration):
            data.append(SimpleNamespace(
                t_sec=float(i), vo2=2000.0, bike_power=200.0,
            ))
        for i in range(180):
            t = duration + i
            vo2 = 1500.0 * math.exp(-i / 30.0) + 500.0
            data.append(SimpleNamespace(
                t_sec=float(t), vo2=vo2, bike_power=0.0,
            ))

        result = analyzer.analyze(
            breath_data=data,
            body_weight_kg=70.0,
            resting_lactate=1.0,
            peak_lactate=8.0,
            exercise_start_sec=0.0,
            exercise_end_sec=float(duration),
        )

        assert result.oxidative_pct is not None
        assert result.oxidative_pct > 80.0, (
            f"Oxidative {result.oxidative_pct:.1f}% should dominate for 10-min effort"
        )

    def test_percentages_always_sum_to_100(self) -> None:
        """With all 3 pathways present, percentages sum to 100% (+/- 0.1)."""
        analyzer = EnergySystemAnalyzer()

        duration = 300
        data = []
        for i in range(duration):
            data.append(SimpleNamespace(
                t_sec=float(i), vo2=3000.0, bike_power=250.0,
            ))
        for i in range(180):
            t = duration + i
            vo2 = 2500.0 * math.exp(-i / 25.0) + 500.0
            data.append(SimpleNamespace(
                t_sec=float(t), vo2=vo2, bike_power=0.0,
            ))

        result = analyzer.analyze(
            breath_data=data,
            body_weight_kg=80.0,
            resting_lactate=0.8,
            peak_lactate=14.0,
            exercise_start_sec=0.0,
            exercise_end_sec=float(duration),
        )

        total_pct = (
            (result.oxidative_pct or 0)
            + (result.glycolytic_pct or 0)
            + (result.phosphagen_pct or 0)
        )
        assert abs(total_pct - 100.0) < 0.2, (
            f"Percentages sum to {total_pct:.2f}%, expected 100%"
        )


class TestBoundaryConditions:
    """Boundary and degenerate inputs for individual calculation methods."""

    def test_oxidative_empty_window_returns_zero(self) -> None:
        """calc_oxidative_energy with start == end returns 0 (empty slice)."""
        analyzer = EnergySystemAnalyzer()

        t_sec = np.arange(0, 601, 1.0)
        vo2_ml = np.full_like(t_sec, 2000.0)

        result = analyzer.calc_oxidative_energy(t_sec, vo2_ml, 300.0, 300.0)
        assert result == 0.0

    def test_oxidative_single_point_returns_zero(self) -> None:
        """calc_oxidative_energy with only one matching point returns 0.0."""
        analyzer = EnergySystemAnalyzer()

        t_sec = np.array([300.0])
        vo2_ml = np.array([2000.0])

        result = analyzer.calc_oxidative_energy(t_sec, vo2_ml, 300.0, 300.0)
        assert result == 0.0

    def test_glycolytic_zero_delta_lactate(self) -> None:
        """delta_lactate == 0 => glycolytic energy is 0."""
        analyzer = EnergySystemAnalyzer()

        result = analyzer.calc_glycolytic_energy(delta_lactate=0.0, body_weight_kg=70.0)
        assert result == 0.0

    def test_glycolytic_very_small_delta(self) -> None:
        """Very small delta_lactate (0.1 mmol/L) still produces a non-negative result."""
        analyzer = EnergySystemAnalyzer()

        result = analyzer.calc_glycolytic_energy(delta_lactate=0.1, body_weight_kg=70.0)
        assert result >= 0.0
        expected = 0.1 * 3.0 * 70.0 / 1000.0 * CALORIC_EQUIVALENT_KJ_PER_L
        assert _within_pct(result, expected, 1.0)

    def test_phosphagen_near_zero_amplitude(self) -> None:
        """Near-zero amplitude => phosphagen energy is proportionally tiny but still correct."""
        analyzer = EnergySystemAnalyzer()

        amplitude = 0.001  # L/min
        tau = 30.0
        fit = MonoExpFitResult(
            amplitude=amplitude, tau=tau, baseline=0.5,
            r_squared=0.99, n_points=100,
        )
        result = analyzer.calc_phosphagen_energy(fit)
        expected = amplitude * tau / 60.0 * CALORIC_EQUIVALENT_KJ_PER_L
        assert result >= 0.0
        assert _within_pct(result, expected, 1.0)


class TestFullPipelineBoundary:
    """Full-pipeline edge cases: no body weight, negative delta lactate, noisy fit."""

    def test_no_body_weight_skips_glycolytic(self) -> None:
        """Without body_weight_kg, glycolytic pathway is skipped with a warning."""
        analyzer = EnergySystemAnalyzer()

        duration = 300
        data = []
        for i in range(duration):
            data.append(SimpleNamespace(t_sec=float(i), vo2=2500.0, bike_power=220.0))
        for i in range(180):
            t = duration + i
            vo2 = 2000.0 * math.exp(-i / 30.0) + 500.0
            data.append(SimpleNamespace(t_sec=float(t), vo2=vo2, bike_power=0.0))

        result = analyzer.analyze(
            breath_data=data,
            body_weight_kg=None,      # no weight provided
            resting_lactate=1.0,
            peak_lactate=9.0,
            exercise_start_sec=0.0,
            exercise_end_sec=float(duration),
        )

        # Glycolytic should be absent; warning must be present
        assert result.glycolytic_kj is None
        assert any("weight" in w.lower() or "glycolytic" in w.lower() for w in result.warnings)

    def test_negative_delta_lactate_sets_glycolytic_zero(self) -> None:
        """peak_lactate < resting_lactate => delta_la <= 0 => glycolytic_kj == 0."""
        analyzer = EnergySystemAnalyzer()

        duration = 300
        data = []
        for i in range(duration):
            data.append(SimpleNamespace(t_sec=float(i), vo2=2500.0, bike_power=220.0))
        for i in range(180):
            t = duration + i
            vo2 = 2000.0 * math.exp(-i / 30.0) + 500.0
            data.append(SimpleNamespace(t_sec=float(t), vo2=vo2, bike_power=0.0))

        # Inverted lactate: resting > peak
        result = analyzer.analyze(
            breath_data=data,
            body_weight_kg=70.0,
            resting_lactate=5.0,
            peak_lactate=3.0,   # peak < resting
            exercise_start_sec=0.0,
            exercise_end_sec=float(duration),
        )

        assert result.has_lactate is True
        assert result.glycolytic_kj == 0.0
        assert any("delta lactate" in w.lower() or "glycolytic" in w.lower() for w in result.warnings)

    def test_low_r_squared_adds_warning(self) -> None:
        """A noisy recovery curve (low R²) still returns a result but includes a warning."""
        analyzer = EnergySystemAnalyzer()

        duration = 300
        rng = np.random.default_rng(seed=42)
        data = []
        for i in range(duration):
            data.append(SimpleNamespace(t_sec=float(i), vo2=2500.0, bike_power=220.0))

        # Recovery with heavy noise — will almost certainly yield R² < 0.80
        for i in range(120):
            t = duration + i
            signal = 2000.0 * math.exp(-i / 30.0) + 500.0
            noisy_vo2 = float(signal + rng.normal(0, 600.0))
            noisy_vo2 = max(noisy_vo2, 0.0)
            data.append(SimpleNamespace(t_sec=float(t), vo2=noisy_vo2, bike_power=0.0))

        result = analyzer.analyze(
            breath_data=data,
            body_weight_kg=70.0,
            resting_lactate=1.0,
            peak_lactate=8.0,
            exercise_start_sec=0.0,
            exercise_end_sec=float(duration),
        )

        # Either the fit failed (no phosphagen) or R² is low (warning present)
        if result.has_phosphagen and result.mono_exp_fit:
            r2 = result.mono_exp_fit.get("r_squared", 1.0)
            if r2 < 0.8:
                assert any("r²" in w.lower() or "fit quality" in w.lower() for w in result.warnings)
        else:
            # Fit failed entirely; there must be at least one warning
            assert len(result.warnings) > 0

    def test_insufficient_breath_data_returns_warning(self) -> None:
        """Fewer than 10 breath data points returns early with a warning."""
        analyzer = EnergySystemAnalyzer()

        data = [SimpleNamespace(t_sec=float(i), vo2=2000.0, bike_power=200.0) for i in range(5)]

        result = analyzer.analyze(
            breath_data=data,
            body_weight_kg=70.0,
            resting_lactate=1.0,
            peak_lactate=8.0,
        )

        assert result.total_kj is None or result.total_kj == 0.0
        assert len(result.warnings) > 0
        assert result.oxidative_kj is None
