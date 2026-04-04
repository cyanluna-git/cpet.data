from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.check_platform_readiness_demo import build_platform_readiness_report
from scripts.intake_real_cpet_golden_corpus import intake_real_cpet_golden_corpus
from scripts.seed_demo_platform_validation import seed_demo_platform_validation


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_stub_real_corpus_source_tree(root: Path) -> dict[str, Path]:
    actes_subject = """ID,Session,Sex,Age,Height,Weight
1,A,F,31,165,58
2,B,M,36,178,73
"""
    actes_measure = """ID,time,VO2,VCO2,HR
1,0,300,250,88
1,1,450,390,96
2,0,320,260,92
2,1,500,430,104
"""
    treadmill_subject = """ID_test,Age,Gender,Weight,Height
T1,10,F,31,136
T2,12,M,38,142
T3,14,F,45,152
T4,16,M,57,164
"""
    treadmill_measure = """ID_test,time,VO2,VE,HR
T1,0,280,12.1,90
T1,1,340,14.0,98
T2,0,290,12.6,93
T2,1,360,14.4,101
T3,0,310,13.0,95
T3,1,390,15.2,108
T4,0,330,13.8,99
T4,1,420,16.1,114
"""

    actes_dir = root / "actes"
    treadmill_dir = root / "treadmill"
    _write_text(actes_dir / "subject-info.csv", actes_subject)
    _write_text(actes_dir / "test_measure.csv", actes_measure)
    _write_text(treadmill_dir / "subject-info.csv", treadmill_subject)
    _write_text(treadmill_dir / "test_measure.csv", treadmill_measure)
    return {
        "actes/subject-info.csv": actes_dir / "subject-info.csv",
        "actes/test_measure.csv": actes_dir / "test_measure.csv",
        "treadmill/subject-info.csv": treadmill_dir / "subject-info.csv",
        "treadmill/test_measure.csv": treadmill_dir / "test_measure.csv",
    }


def test_platform_validation_harness_end_to_end(monkeypatch, tmp_path: Path) -> None:
    from scripts import intake_real_cpet_golden_corpus as golden_module

    source_tree = _build_stub_real_corpus_source_tree(tmp_path / "stub-remote")

    def fake_download(url: str, destination: Path) -> None:
        key = ""
        if "actes-cycloergometer-exercise" in url:
            key = f"actes/{Path(url).name}"
        elif "treadmill-exercise-cardioresp" in url:
            key = f"treadmill/{Path(url).name}"
        else:
            raise AssertionError(f"Unexpected download URL: {url}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_tree[key], destination)

    monkeypatch.setattr(golden_module, "_download", fake_download)

    golden_root = tmp_path / "golden-corpus"
    golden_summary = intake_real_cpet_golden_corpus(
        output_root=golden_root,
        treadmill_target_tests=2,
        reset=True,
    )
    manifest = json.loads(Path(golden_summary["manifest_path"]).read_text(encoding="utf-8"))
    assert len(manifest["sources"]) == 2
    assert manifest["curation"]["actes"]["subject_rows"] == 2
    assert manifest["curation"]["treadmill"]["curated_subject_rows"] == 2

    demo_root = tmp_path / "platform-demo"
    seed_demo_platform_validation(
        output_root=demo_root,
        subject_count=120,
        seed=20260404,
        reset=True,
    )
    report = build_platform_readiness_report(demo_root=demo_root)

    assert report["ready"] is True
    assert report["suggested_follow_up_tasks"] == []
    assert all(check["ok"] for check in report["db"]["checks"])
    assert all(check["ok"] for check in report["http"]["checks"])
