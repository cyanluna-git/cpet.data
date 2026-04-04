"""
pipeline.cli — Command-line interface for the CPET analysis pipeline.

Usage:
    python -m pipeline --workspace ./tests/fixtures/park_geunyun/
    python -m pipeline --workspace ./data/ --skip-report --verbose
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Any


def _detect_workspace_mode(workspace: Path) -> str:
    """Return the analysis mode implied by raw files in the workspace."""
    raw_dir = workspace / "raw"
    search_dir = raw_dir if raw_dir.is_dir() else workspace

    suffixes = {path.suffix.lower() for path in search_dir.iterdir() if path.is_file()}
    if ".pdf" in suffixes and ".xlsx" not in suffixes:
        return "standalone_inscyd"
    return "cpet"


def main(argv: list[str] | None = None) -> int:
    """Run the pipeline CLI.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 = success).
    """
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="CPET analysis pipeline: parse, analyze, report.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="Path to workspace directory containing raw data files.",
    )
    parser.add_argument(
        "--skip-report",
        action="store_true",
        help="Skip HTML report generation.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output.",
    )

    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()

    if not workspace.is_dir():
        print(f"Error: workspace directory does not exist: {workspace}")
        return 1

    t0 = time.time()

    print(f"\n{'=' * 60}")
    print(f"PIPELINE: {workspace.name}")
    print(f"{'=' * 60}")

    analysis_mode = _detect_workspace_mode(workspace)
    if analysis_mode == "standalone_inscyd":
        from pipeline.inscyd_workspace import parse_inscyd_workspace

        print("\n[1/2] Parsing standalone INSCYD workspace...")
        parsed = parse_inscyd_workspace(workspace)
        print(f"  Athlete: {parsed.report.athlete_name}")
        print(f"  Test type: {parsed.report.test_type}")
        print(f"  FIT: {'yes' if parsed.fit_sessions else 'no'}")
        print(f"  ZWO: {'yes' if parsed.zwo_summary else 'no'}")

        if args.skip_report:
            print("\n[2/2] Report generation skipped.")
        else:
            from pipeline.inscyd_report import generate_inscyd_report

            print("\n[2/2] Generating INSCYD interpretation report...")
            report_dir = workspace / "report"
            report_path = generate_inscyd_report(workspace, report_dir)
            print(f"  -> {report_path}")
    else:
        # Step 1: Parse
        from pipeline.parsers import parse_workspace

        print("\n[1/4] Parsing workspace...")
        parsed = parse_workspace(workspace)

        print(f"  COSMED: {len(parsed.cosmed_df)} BxB records")
        print(f"  FIT: {'yes' if parsed.has_fit else 'no'}")
        print(f"  Protocol: {'yes' if parsed.has_protocol else 'no'}")
        print(f"  Lactate: {'yes' if parsed.has_lactate else 'no'}")

        if args.verbose:
            print(f"  Subject: {parsed.subject_info.get('name')}")
            if parsed.has_fit and parsed.workout_df is not None:
                print(f"  Workout records: {len(parsed.workout_df)}")
            if parsed.has_lactate and parsed.blood_df is not None:
                print(f"  Blood samples: {len(parsed.blood_df)}")

        # Step 2: Create database
        from pipeline.schema import create_database

        print("\n[2/4] Creating database...")
        db_path = create_database(workspace, parsed)
        print(f"  -> {db_path}")

        # Step 3: Run analysis
        from pipeline.analysis import run_analysis

        print("\n[3/4] Running analysis...")
        run_analysis(db_path)

        # Step 4: Generate report
        if not args.skip_report:
            from pipeline.report import generate_report

            print("\n[4/4] Generating report...")
            report_dir = workspace / "report"
            report_path = generate_report(db_path, report_dir)
            print(f"  -> {report_path}")
        else:
            print("\n[4/4] Report generation skipped.")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")

    if analysis_mode == "cpet":
        # Verify tables
        _verify_db(db_path, args.verbose)

    return 0


def _verify_db(db_path: Path, verbose: bool = False) -> None:
    """Print database table counts for verification."""
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    tables = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()

    table_count = len(tables)
    print(f"\nVerification: {table_count} tables in {db_path.name}")
    if verbose:
        for (name,) in tables:
            count = cursor.execute(
                f"SELECT COUNT(*) FROM {name}"
            ).fetchone()[0]
            print(f"  {name}: {count} rows")
    conn.close()
