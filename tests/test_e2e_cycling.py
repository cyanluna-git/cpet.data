"""
tests/test_e2e_cycling.py — End-to-end tests for cycling-native performance models.

Verifies the full pipeline output across fixture workspaces:
  - combined_guidance is always stored in analysis DB
  - cycling panel renders correctly (or is absent) in generated HTML
  - no fake CP values appear when model abstains
  - COSMED-only workspace has no cycling panel
  - protocol suitability and cycling guidance coexist without collision

Fixtures:
  - park_geunyun: 1 FIT file + COSMED (CP model likely abstains — single FIT)
  - hong_changsun: 1 FIT file + COSMED (CP model likely abstains — single FIT)
  - cosmed_only:   no FIT file (cycling features must be fully absent)

Note: The fixture FIT files live under `raw/` subdirectories. The analysis pipeline
globs `*.fit` from the workspace root only, so cp_model is absent for the shared
fixture workspaces. TestCyclingPanelHTML uses a scratch workspace (tmp_path) that
copies a FIT file to the root, enabling cp_model ingestion and panel rendering.
"""

import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
PARK_WS = FIXTURES / "park_geunyun"
HONG_WS = FIXTURES / "hong_changsun"
COSMED_WS = FIXTURES / "cosmed_only"


def _run_pipeline(workspace: Path) -> dict[str, Any]:
    """Run full pipeline and return the raw results dict from run_analysis."""
    from pipeline.parsers import parse_workspace
    from pipeline.schema import create_database
    from pipeline.analysis import run_analysis

    parsed = parse_workspace(workspace)
    db_path = create_database(workspace, parsed)
    return run_analysis(db_path)


def _build_scratch_workspace(tmp_path: Path, source_ws: Path) -> Path:
    """Clone source_ws into tmp_path and copy its raw/*.fit files to the workspace root.

    This enables analysis.py to detect FIT files (it globs workspace/*.fit) without
    mutating the shared fixtures.
    """
    scratch = tmp_path / "workspace"
    shutil.copytree(source_ws, scratch)

    # Move any FIT files from raw/ to workspace root so the pipeline can find them
    raw_dir = scratch / "raw"
    if raw_dir.is_dir():
        for fit_file in raw_dir.glob("*.fit"):
            shutil.copy2(fit_file, scratch / fit_file.name)

    # Remove stale analysis.db so create_database starts fresh
    stale_db = scratch / "analysis.db"
    if stale_db.exists():
        stale_db.unlink()

    return scratch


# =====================================================================
# Group 1: combined_guidance always stored in analysis DB
# =====================================================================


class TestCombinedGuidanceStorage:
    """combined_guidance is stored in analysis_results after run_analysis."""

    @pytest.fixture(autouse=True)
    def run(self) -> None:
        self._results = _run_pipeline(PARK_WS)

    def test_combined_guidance_key_present(self) -> None:
        """combined_guidance key always exists in results."""
        assert "combined_guidance" in self._results

    def test_combined_guidance_has_status(self) -> None:
        """combined_guidance always has a status field with a valid value."""
        cg = self._results["combined_guidance"]
        assert cg.get("status") in {"supported", "low_confidence", "abstain"}, (
            f"Unexpected combined_guidance status: {cg.get('status')!r}"
        )

    def test_combined_guidance_has_narrative(self) -> None:
        """Narrative always has non-empty headline and body strings."""
        narrative = self._results["combined_guidance"].get("narrative", {})
        assert isinstance(narrative.get("headline"), str)
        assert isinstance(narrative.get("body"), str)
        assert len(narrative["headline"]) > 0, "headline must not be empty"
        assert len(narrative["body"]) > 0, "body must not be empty"

    def test_combined_guidance_stored_in_db(self) -> None:
        """combined_guidance keys are persisted to analysis_results table."""
        db_path = PARK_WS / "analysis.db"
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT key, value FROM analysis_results WHERE category='combined_guidance'"
        ).fetchall()
        conn.close()
        assert len(rows) > 0, "combined_guidance must have rows in analysis_results"


# =====================================================================
# Group 2: Report HTML — cycling panel behavior
# =====================================================================


class TestCyclingPanelHTML:
    """Cycling panel renders correctly in final HTML when FIT data is present.

    Uses a scratch workspace (tmp_path) cloned from hong_changsun with its FIT
    file copied to the workspace root, so the pipeline detects it and produces
    a cycling panel section (in the abstained state, given only 1 FIT session).
    """

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path_factory: pytest.TempPathFactory) -> None:
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database
        from pipeline.analysis import run_analysis
        from pipeline.report import generate_report

        tmp = tmp_path_factory.mktemp("cycling_panel")
        scratch = _build_scratch_workspace(tmp, HONG_WS)

        parsed = parse_workspace(scratch)
        db_path = create_database(scratch, parsed)
        self._results = run_analysis(db_path)
        report_path = generate_report(db_path, scratch / "report")
        self._html = report_path.read_text(encoding="utf-8")

    def test_no_fake_cp_values_when_abstained(self) -> None:
        """When CP model abstains, panel must show withheld text, not numeric CP value.

        When CP model produces a value, numeric W values must appear in the panel.
        The test branches on the actual cp_w anchor so the assertion matches reality.
        """
        if 'id="cycling-panel"' not in self._html:
            pytest.skip("No cycling panel rendered (CPET-only or no FIT)")

        # Locate the cycling panel content (~5 000 chars is sufficient for the section)
        panel_start = self._html.index('id="cycling-panel"')
        panel_chunk = self._html[panel_start : panel_start + 5000]

        cg = self._results.get("combined_guidance", {})
        cp_w = cg.get("anchors", {}).get("cp_w")

        if cp_w is None:
            # Model abstained — panel must show withheld text, no stray numeric W values
            withheld_terms = ["보류", "이력", "withheld", "abstain", "insufficient"]
            has_withheld = any(t in panel_chunk for t in withheld_terms)
            assert has_withheld, (
                "Cycling panel with abstained CP must show withheld/보류 messaging"
            )
            # Ensure no raw numeric CP is displayed next to "Critical Power" label
            cp_label_pos = panel_chunk.find("Critical Power")
            if cp_label_pos != -1:
                vicinity = panel_chunk[cp_label_pos : cp_label_pos + 200]
                has_numeric_w = bool(re.search(r"\d+\s*W", vicinity))
                assert not has_numeric_w, (
                    "Abstained cycling panel must not display a numeric W value "
                    f"near 'Critical Power'. Found: {vicinity!r}"
                )
        else:
            # Model computed — numeric values must appear
            has_numeric = bool(re.search(r"\d+\s*W", panel_chunk))
            assert has_numeric, (
                f"Cycling panel with CP={cp_w}W must display numeric W value"
            )

    def test_existing_vo2max_section_unaffected(self) -> None:
        """Adding cycling panel does not break VO2max rendering in the report."""
        assert "VO2max" in self._html or "vo2max" in self._html.lower(), (
            "VO2max section must be present in the report HTML"
        )

    def test_cycling_panel_not_present_in_cosmed_only(self) -> None:
        """COSMED-only report must not show cycling-panel section."""
        from pipeline.parsers import parse_workspace
        from pipeline.schema import create_database
        from pipeline.analysis import run_analysis
        from pipeline.report import generate_report

        parsed = parse_workspace(COSMED_WS)
        db_path = create_database(COSMED_WS, parsed)
        run_analysis(db_path)
        report_path = generate_report(db_path, COSMED_WS / "report")
        html = report_path.read_text(encoding="utf-8")
        assert 'id="cycling-panel"' not in html, (
            "COSMED-only report must not include id='cycling-panel'"
        )


# =====================================================================
# Group 3: Protocol + cycling gating coexistence
# =====================================================================


def test_protocol_suitability_and_cycling_guidance_coexist() -> None:
    """Protocol suitability results and cycling guidance can both be present without conflict."""
    results = _run_pipeline(PARK_WS)

    assert "suitability" in results
    assert "combined_guidance" in results

    suitability = results["suitability"]
    combined = results["combined_guidance"]

    assert isinstance(suitability, dict), "suitability must be a dict"
    assert isinstance(combined, dict), "combined_guidance must be a dict"

    # combined_guidance must not absorb or overwrite any suitability metric keys
    suitability_metric_keys = {
        "vo2max", "lt1", "lt2", "fatmax", "clearance", "efficiency", "vt1", "vt2"
    }
    guidance_keys = set(combined.keys())
    collision = guidance_keys & suitability_metric_keys
    assert not collision, (
        f"combined_guidance must not contain suitability metric keys; "
        f"collisions found: {collision}"
    )


def test_combined_guidance_consistent_across_workspaces() -> None:
    """combined_guidance status is valid for both park_geunyun and hong_changsun."""
    valid_statuses = {"supported", "low_confidence", "abstain"}
    for ws_name, ws_path in [("park_geunyun", PARK_WS), ("hong_changsun", HONG_WS)]:
        results = _run_pipeline(ws_path)
        cg = results.get("combined_guidance", {})
        status = cg.get("status")
        assert status in valid_statuses, (
            f"{ws_name}: combined_guidance.status={status!r} not in {valid_statuses}"
        )
        # Anchors block always present
        assert "anchors" in cg, f"{ws_name}: combined_guidance missing 'anchors'"
        # Narrative always present
        narrative = cg.get("narrative", {})
        assert isinstance(narrative.get("headline"), str), (
            f"{ws_name}: combined_guidance.narrative.headline must be str"
        )


def test_cp_model_not_present_in_cosmed_only_results() -> None:
    """COSMED-only workspace has no cp_model key — no FIT files processed."""
    results = _run_pipeline(COSMED_WS)
    assert "cp_model" not in results, (
        "COSMED-only workspace must not have cp_model in analysis results"
    )
    # combined_guidance still present but should abstain (no CP data available)
    cg = results.get("combined_guidance", {})
    assert cg.get("status") == "abstain", (
        f"COSMED-only combined_guidance must abstain, got: {cg.get('status')!r}"
    )
