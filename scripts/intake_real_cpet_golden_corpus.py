"""
Download and curate a small real CPET golden corpus from public PhysioNet datasets.

This corpus is for parser realism checks and metric plausibility reference.
It is intentionally separate from the synthetic platform-validation demo DB.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import urllib.request
from pathlib import Path

ACTES_BASE = "https://physionet.org/files/actes-cycloergometer-exercise/1.0.0"
TREADMILL_BASE = "https://physionet.org/files/treadmill-exercise-cardioresp/1.0.1"


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _deterministic_even_sample(values: list[str], target_count: int) -> list[str]:
    if target_count <= 0 or not values:
        return []
    deduped = list(dict.fromkeys(values))
    if len(deduped) <= target_count:
        return deduped
    last_index = len(deduped) - 1
    selected: list[str] = []
    for idx in range(target_count):
        pos = round((idx * last_index) / (target_count - 1))
        value = deduped[pos]
        if value not in selected:
            selected.append(value)
    if len(selected) < target_count:
        for value in deduped:
            if value not in selected:
                selected.append(value)
            if len(selected) == target_count:
                break
    return selected[:target_count]


def _curate_actes(raw_dir: Path, curated_dir: Path) -> dict:
    curated_dir.mkdir(parents=True, exist_ok=True)
    subject_info = raw_dir / "subject-info.csv"
    test_measure = raw_dir / "test_measure.csv"
    curated_subject_info = curated_dir / "subject-info.csv"
    curated_test_measure = curated_dir / "test_measure.csv"
    shutil.copy2(subject_info, curated_subject_info)
    shutil.copy2(test_measure, curated_test_measure)

    subject_rows = _read_csv_rows(subject_info)
    measure_rows = _read_csv_rows(test_measure)
    selected_ids = sorted({row["ID"] for row in subject_rows}, key=lambda item: int(item))
    return {
        "dataset": "actes-cycloergometer-exercise",
        "subject_rows": len(subject_rows),
        "measure_rows": len(measure_rows),
        "selected_ids": selected_ids,
        "selection_mode": "all_subjects",
    }


def _curate_treadmill(raw_dir: Path, curated_dir: Path, target_tests: int) -> dict:
    curated_dir.mkdir(parents=True, exist_ok=True)
    subject_info = raw_dir / "subject-info.csv"
    test_measure = raw_dir / "test_measure.csv"
    subject_rows = _read_csv_rows(subject_info)
    measure_rows = _read_csv_rows(test_measure)

    sorted_subject_rows = sorted(
        subject_rows,
        key=lambda row: (
            float(row.get("Age") or 0),
            str(row.get("ID_test") or ""),
        ),
    )
    id_tests = [str(row["ID_test"]) for row in sorted_subject_rows if row.get("ID_test")]
    selected_id_tests = set(_deterministic_even_sample(id_tests, target_tests))

    curated_subject_rows = [row for row in sorted_subject_rows if str(row.get("ID_test")) in selected_id_tests]
    curated_measure_rows = [row for row in measure_rows if str(row.get("ID_test")) in selected_id_tests]

    _write_csv_rows(
        curated_dir / "subject-info.csv",
        curated_subject_rows,
        list(curated_subject_rows[0].keys()) if curated_subject_rows else list(sorted_subject_rows[0].keys()),
    )
    _write_csv_rows(
        curated_dir / "test_measure.csv",
        curated_measure_rows,
        list(curated_measure_rows[0].keys()) if curated_measure_rows else list(measure_rows[0].keys()),
    )

    return {
        "dataset": "treadmill-exercise-cardioresp",
        "subject_rows": len(subject_rows),
        "measure_rows": len(measure_rows),
        "selected_tests": sorted(selected_id_tests),
        "curated_subject_rows": len(curated_subject_rows),
        "curated_measure_rows": len(curated_measure_rows),
        "selection_mode": f"deterministic_even_sample_{target_tests}",
    }


def intake_real_cpet_golden_corpus(
    *,
    output_root: Path,
    treadmill_target_tests: int = 12,
    datasets: tuple[str, ...] = ("actes", "treadmill"),
    reset: bool = False,
) -> dict:
    if output_root.exists():
        if not reset:
            raise SystemExit(f"Refusing to overwrite existing corpus root without --reset: {output_root}")
        shutil.rmtree(output_root)

    raw_root = output_root / "raw"
    curated_root = output_root / "curated"
    manifests_root = output_root / "manifests"
    raw_root.mkdir(parents=True, exist_ok=True)
    curated_root.mkdir(parents=True, exist_ok=True)
    manifests_root.mkdir(parents=True, exist_ok=True)

    actes_raw = raw_root / "actes-cycloergometer-exercise"
    treadmill_raw = raw_root / "treadmill-exercise-cardioresp"

    datasets = tuple(item.strip().lower() for item in datasets if item.strip())
    manifest_sources = []
    curation = {}

    if "actes" in datasets:
        for url, destination in (
            (f"{ACTES_BASE}/subject-info.csv", actes_raw / "subject-info.csv"),
            (f"{ACTES_BASE}/test_measure.csv", actes_raw / "test_measure.csv"),
        ):
            _download(url, destination)
        curation["actes"] = _curate_actes(
            actes_raw,
            curated_root / "actes-cycloergometer-exercise",
        )
        manifest_sources.append(
            {
                "name": "ACTES: A collection of cardiorespiratory measures during exercise on cycloergometer",
                "landing_page": "https://physionet.org/content/actes-cycloergometer-exercise/1.0.0/",
                "download_base": ACTES_BASE,
            }
        )

    if "treadmill" in datasets:
        for url, destination in (
            (f"{TREADMILL_BASE}/subject-info.csv", treadmill_raw / "subject-info.csv"),
            (f"{TREADMILL_BASE}/test_measure.csv", treadmill_raw / "test_measure.csv"),
        ):
            _download(url, destination)
        curation["treadmill"] = _curate_treadmill(
            treadmill_raw,
            curated_root / "treadmill-exercise-cardioresp",
            treadmill_target_tests,
        )
        manifest_sources.append(
            {
                "name": "Treadmill exercise test dataset of healthy children",
                "landing_page": "https://physionet.org/content/treadmill-exercise-cardioresp/1.0.1/",
                "download_base": TREADMILL_BASE,
            }
        )

    manifest = {
        "sources": manifest_sources,
        "curation": curation,
    }
    (manifests_root / "real_cpet_golden_corpus_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "output_root": str(output_root),
        "manifest_path": str(manifests_root / "real_cpet_golden_corpus_manifest.json"),
        **curation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and curate a small real CPET golden corpus.")
    parser.add_argument(
        "--output-root",
        default="tmp/real-cpet-golden-corpus",
        help="Directory that will contain raw downloads, curated subsets, and the manifest.",
    )
    parser.add_argument(
        "--treadmill-target-tests",
        type=int,
        default=12,
        help="How many treadmill ID_test series to keep in the curated subset.",
    )
    parser.add_argument(
        "--datasets",
        default="actes,treadmill",
        help="Comma-separated dataset keys to intake. Supported: actes,treadmill",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing output root before rebuilding the corpus.",
    )
    args = parser.parse_args()
    summary = intake_real_cpet_golden_corpus(
        output_root=Path(args.output_root),
        treadmill_target_tests=args.treadmill_target_tests,
        datasets=tuple(item.strip() for item in args.datasets.split(",") if item.strip()),
        reset=args.reset,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
