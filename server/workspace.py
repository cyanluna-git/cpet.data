"""
server.workspace — Workspace directory creation and file management.

Workspaces live under base_dir/workspaces/<submission_id>/ with raw/
and report/ subdirectories. Accepts plain (filename, bytes) tuples
instead of framework-specific UploadFile objects.
"""

import os
from pathlib import Path


def create_workspace(
    base_dir: Path,
    submission_id: str,
    files: list[tuple[str, bytes]],
) -> Path:
    """Create a workspace directory and write uploaded files to raw/.

    Directory structure:
        base_dir/workspaces/<submission_id>/raw/   — uploaded files
        base_dir/workspaces/<submission_id>/report/ — generated reports

    Returns:
        Path to the workspace root (base_dir/workspaces/<submission_id>).
    """
    workspace = base_dir / "workspaces" / submission_id
    raw_dir = workspace / "raw"
    report_dir = workspace / "report"

    raw_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in files:
        file_path = raw_dir / filename
        file_path.write_bytes(content)

    return workspace


def get_workspace(
    base_dir: Path, submission_id: str
) -> Path | None:
    """Return the workspace path if it exists, else None."""
    workspace = base_dir / "workspaces" / submission_id
    if workspace.is_dir():
        return workspace
    return None


def list_files(workspace: Path) -> list[dict]:
    """List files in the workspace raw/ directory.

    Returns:
        List of dicts with keys: name, extension, size_bytes.
    """
    raw_dir = workspace / "raw"
    if not raw_dir.is_dir():
        return []

    result = []
    for entry in sorted(raw_dir.iterdir()):
        if entry.is_file():
            name = entry.name
            extension = entry.suffix.lstrip(".")
            size_bytes = entry.stat().st_size
            result.append({
                "name": name,
                "extension": extension,
                "size_bytes": size_bytes,
            })
    return result
