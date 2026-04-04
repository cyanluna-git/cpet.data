from pathlib import Path

from scripts.check_platform_readiness_demo import build_platform_readiness_report
from scripts.seed_demo_platform_validation import seed_demo_platform_validation


def test_platform_readiness_report_passes_on_seeded_demo(tmp_path: Path) -> None:
    demo_root = tmp_path / "platform-demo"
    seed_demo_platform_validation(
        output_root=demo_root,
        subject_count=120,
        seed=20260404,
        reset=True,
    )

    report = build_platform_readiness_report(demo_root=demo_root)

    assert report["db"]["counts"]["subjects"] == 120
    assert report["db"]["counts"]["subject_metric_snapshots"] > 120
    assert report["db"]["counts"]["subject_feature_sets"] >= report["db"]["counts"]["subject_metric_snapshots"]
    assert report["ready"] is True
    assert report["suggested_follow_up_tasks"] == []
    assert all(check["ok"] for check in report["db"]["checks"])
    assert all(check["ok"] for check in report["http"]["checks"])
