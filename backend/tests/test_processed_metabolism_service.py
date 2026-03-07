"""Tests for ProcessedMetabolismService failure diagnostics."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pytest

from app.models import CPETTest
from app.services.metabolism_analysis import AnalysisConfig
from app.services.processed_metabolism import ProcessedMetabolismService


@dataclass
class FakeBreathData:
    bike_power: Optional[float] = None
    fat_oxidation: Optional[float] = None
    cho_oxidation: Optional[float] = None
    vo2: Optional[float] = None
    vco2: Optional[float] = None
    hr: Optional[float] = None
    ve_vo2: Optional[float] = None
    ve_vco2: Optional[float] = None
    rer: Optional[float] = None
    vo2_rel: Optional[float] = None
    t_sec: Optional[float] = None
    phase: str = "Exercise"


@pytest.mark.asyncio
async def test_save_raises_specific_reason_for_missing_metabolic_rows(async_db, test_subject):
    test = CPETTest(
        subject_id=test_subject.id,
        test_date=datetime(2026, 1, 1),
        protocol_type="RAMP",
        parsing_status="success",
    )
    async_db.add(test)
    await async_db.commit()
    await async_db.refresh(test)

    breath_data = [
        FakeBreathData(
            bike_power=120.0,
            hr=130.0,
            t_sec=60.0 + idx * 10.0,
            phase="Exercise",
        )
        for idx in range(12)
    ]

    service = ProcessedMetabolismService(async_db)

    with pytest.raises(ValueError, match="No usable metabolic rows"):
        await service.save(
            test_id=test.test_id,
            breath_data=breath_data,
            config=AnalysisConfig(auto_trim_enabled=False, exclude_initial_hyperventilation=False),
        )

    await async_db.refresh(test)
    assert test.processing_status == "failed"
