"""Backend VO2max smoothing unit tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

BACKEND_ROOT = Path(__file__).parent.parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.cosmed_parser import COSMEDParser
from app.services.test import TestService as BackendTestService


def _build_triplet_outlier_df() -> pd.DataFrame:
    vo2_values = [
        3600.0,
        3800.0,
        4000.0,
        4150.0,
        4250.0,
        4320.0,
        4586.2,
        4591.8,
        4306.5,
        4307.5,
        4275.1,
        4446.6,
        4305.8,
        1229.7,
        4425.9,
        4368.6,
    ]
    return pd.DataFrame(
        {
            "t_sec": list(range(1, len(vo2_values) + 1)),
            "vo2": vo2_values,
            "vo2_rel": [round(v / 67.1, 1) for v in vo2_values],
            "vco2": [round(v * 1.08, 1) for v in vo2_values],
            "hr": [160] * len(vo2_values),
            "rer": [1.08] * len(vo2_values),
        }
    )


def test_cosmed_parser_uses_triplet_smoothing_with_outlier_rejection() -> None:
    parser = COSMEDParser()
    result = parser.find_vo2max(_build_triplet_outlier_df())

    assert round(result["vo2_max"], 1) == 4376.2
    assert round(result["vo2_max_rel"], 1) == 65.2
    assert result["vo2max_method"] == "triplet_mean_local_median_filter"
    assert result["vo2max_outliers_removed"] == 1
    assert result["vo2max_triplet_fallback_used"] is False
    assert result["vo2max_triplet_values"] == [4446.6, 4305.8, 1229.7]
    assert result["vo2max_triplet_used_values"] == [4446.6, 4305.8]


def test_test_service_matches_parser_conclusion_for_same_case() -> None:
    parser = COSMEDParser()
    df = _build_triplet_outlier_df()
    parser_result = parser.find_vo2max(df)

    service = BackendTestService(None)
    breath_data = [
        SimpleNamespace(
            t_sec=row.t_sec,
            vo2=row.vo2,
            vo2_rel=row.vo2_rel,
            vco2=row.vco2,
            hr=row.hr,
            rer=row.rer,
        )
        for row in df.itertuples(index=False)
    ]
    test = SimpleNamespace(
        weight_kg=67.1,
        smoothing_window=10,
        vo2_max=None,
        vo2_max_rel=None,
        vco2_max=None,
        hr_max=None,
    )

    service_result = service._find_vo2max_info(breath_data, test)

    assert round(service_result["vo2_max"], 1) == round(parser_result["vo2_max"], 1)
    assert round(service_result["vo2_max_rel"], 1) == round(
        parser_result["vo2_max_rel"], 1
    )
    assert service_result["vo2max_method"] == parser_result["vo2max_method"]
    assert (
        service_result["vo2max_outliers_removed"]
        == parser_result["vo2max_outliers_removed"]
    )
    assert service_result["vo2max_triplet_values"] == parser_result["vo2max_triplet_values"]
    assert (
        service_result["vo2max_triplet_used_values"]
        == parser_result["vo2max_triplet_used_values"]
    )


def test_test_service_falls_back_when_triplet_has_too_few_usable_points() -> None:
    service = BackendTestService(None)
    breath_data = [
        SimpleNamespace(t_sec=1.0, vo2=3500.0, vo2_rel=50.0, vco2=3600.0, hr=150, rer=1.0),
        SimpleNamespace(t_sec=2.0, vo2=4100.0, vo2_rel=58.6, vco2=4200.0, hr=155, rer=1.02),
        SimpleNamespace(t_sec=3.0, vo2=4300.0, vo2_rel=61.4, vco2=4400.0, hr=160, rer=1.05),
        SimpleNamespace(t_sec=4.0, vo2=8000.0, vo2_rel=114.3, vco2=8100.0, hr=164, rer=1.08),
        SimpleNamespace(t_sec=5.0, vo2=1200.0, vo2_rel=17.1, vco2=1250.0, hr=166, rer=1.1),
    ]
    test = SimpleNamespace(
        weight_kg=70.0,
        smoothing_window=2,
        vo2_max=None,
        vo2_max_rel=None,
        vco2_max=None,
        hr_max=None,
    )

    result = service._find_vo2max_info(breath_data, test)

    assert result["vo2max_method"] == "rolling_peak_fallback"
    assert result["vo2max_triplet_fallback_used"] is True
    assert result["vo2max_outliers_removed"] == 2
    assert round(result["vo2_max"], 1) == 6150.0
    assert round(result["vo2_max_rel"], 1) == 87.9
