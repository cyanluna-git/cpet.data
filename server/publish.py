"""
server.publish — Report publishing: copy generated reports to a public directory.

Handles slug generation from subject names (including Korean/unicode),
collision avoidance, and file copying.
"""

import re
import shutil
import unicodedata
from pathlib import Path


def generate_slug(subject_name: str, test_date: str) -> str:
    """Generate a URL-safe slug from subject name and test date.

    Args:
        subject_name: Display name (may contain Korean, spaces, special chars).
        test_date: ISO date string, e.g. "2026-03-20".

    Returns:
        Slug like "park-geunyun-20260320" or "subject-20260320".
    """
    # Normalize unicode (NFC → NFD for decomposition, then strip accents)
    name = unicodedata.normalize("NFD", subject_name)
    # Remove combining characters (accents, diacritics)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    # Strip any remaining non-ASCII (Korean characters, etc.)
    name = name.encode("ascii", "ignore").decode("ascii")
    # Lowercase
    name = name.lower()
    # Replace non-alphanumeric runs with a single dash
    name = re.sub(r"[^a-z0-9]+", "-", name)
    # Strip leading/trailing dashes
    name = name.strip("-")
    # Fallback if name is empty after stripping
    if not name:
        name = "subject"

    # Normalize date: "2026-03-20" → "20260320"
    date_part = test_date.replace("-", "")

    return f"{name}-{date_part}"


def publish_report(
    workspace: Path,
    subject_name: str,
    test_date: str,
    publish_dir: Path = Path("published"),
    slug: str | None = None,
) -> str:
    """Copy the generated report to the public directory.

    Copies workspace/report/index.html (and any sibling assets) to
    publish_dir/<slug>/. Handles slug collisions by appending -2, -3, etc.

    When slug is provided, skips generation and overwrites the target directory
    in place (clears it first) so the published URL stays stable across
    re-analysis runs.

    Args:
        workspace: Path to the workspace root (contains report/ subdirectory).
        subject_name: Display name for slug generation.
        test_date: ISO date string for slug generation.
        publish_dir: Root directory for published reports.
        slug: Existing slug to reuse; when None a fresh slug is generated.

    Returns:
        The final slug (directory name under publish_dir).

    Raises:
        FileNotFoundError: If workspace/report/index.html does not exist.
    """
    report_dir = workspace / "report"
    index_file = report_dir / "index.html"

    if not index_file.is_file():
        raise FileNotFoundError(
            f"Report not found at {index_file}"
        )

    if slug is None:
        base_slug = generate_slug(subject_name, test_date)
        slug = base_slug
        counter = 2

        # Handle collision: append -2, -3, etc.
        while (publish_dir / slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

    target_dir = publish_dir / slug
    shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy all files from report/ to published/<slug>/
    for item in report_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, target_dir / item.name)
        elif item.is_dir():
            shutil.copytree(item, target_dir / item.name)

    return slug
