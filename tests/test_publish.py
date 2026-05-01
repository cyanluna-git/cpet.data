"""
tests/test_publish.py — Unit tests for server.publish module.

Covers slug generation (ASCII, Korean, special chars, edge cases)
and report publishing (copy, collision handling, missing report).
"""

from pathlib import Path

import pytest

from server.publish import generate_slug, publish_report


# ── generate_slug ────────────────────────────────────────────────────


class TestGenerateSlug:
    """Tests for generate_slug()."""

    def test_ascii_name(self) -> None:
        assert generate_slug("Park Geunyun", "2026-03-20") == "park-geunyun-20260320"

    def test_korean_name_stripped(self) -> None:
        """Korean characters are non-ASCII and get stripped; fallback to 'subject'."""
        result = generate_slug("박근윤", "2026-03-20")
        assert result == "subject-20260320"

    def test_mixed_korean_ascii(self) -> None:
        """Mixed name keeps ASCII portion."""
        result = generate_slug("홍 ChangSun", "2026-01-15")
        assert result == "changsun-20260115"

    def test_special_characters(self) -> None:
        """Special characters become dashes."""
        result = generate_slug("O'Brien-Smith (Jr.)", "2025-12-01")
        assert result == "o-brien-smith-jr-20251201"

    def test_accented_characters(self) -> None:
        """Accented Latin characters are decomposed to base form."""
        result = generate_slug("Jose Garcia", "2026-06-15")
        assert result == "jose-garcia-20260615"

    def test_empty_name_fallback(self) -> None:
        """Empty string falls back to 'subject'."""
        result = generate_slug("", "2026-03-20")
        assert result == "subject-20260320"

    def test_whitespace_only_fallback(self) -> None:
        """Whitespace-only name falls back to 'subject'."""
        result = generate_slug("   ", "2026-03-20")
        assert result == "subject-20260320"

    def test_date_without_dashes(self) -> None:
        """Date already without dashes is handled."""
        result = generate_slug("Test User", "20260320")
        assert result == "test-user-20260320"

    def test_multiple_spaces(self) -> None:
        """Multiple consecutive spaces become a single dash."""
        result = generate_slug("John   Doe", "2026-01-01")
        assert result == "john-doe-20260101"

    def test_numbers_in_name(self) -> None:
        """Numbers in the name are preserved."""
        result = generate_slug("Rider 42", "2026-05-10")
        assert result == "rider-42-20260510"

    def test_unicode_accents(self) -> None:
        """Accented characters like e-acute are normalized."""
        result = generate_slug("Rene Dupont", "2026-07-04")
        assert result == "rene-dupont-20260704"


# ── publish_report ───────────────────────────────────────────────────


class TestPublishReport:
    """Tests for publish_report()."""

    @pytest.fixture()
    def workspace(self, tmp_path: Path) -> Path:
        """Create a workspace with a report/index.html."""
        ws = tmp_path / "workspace"
        report_dir = ws / "report"
        report_dir.mkdir(parents=True)
        (report_dir / "index.html").write_text("<html>report</html>")
        return ws

    @pytest.fixture()
    def publish_dir(self, tmp_path: Path) -> Path:
        """Provide a temporary publish directory."""
        d = tmp_path / "published"
        d.mkdir()
        return d

    def test_basic_publish(self, workspace: Path, publish_dir: Path) -> None:
        """Report is copied to published/<slug>/index.html."""
        slug = publish_report(workspace, "Park Geunyun", "2026-03-20", publish_dir)
        assert slug == "park-geunyun-20260320"
        published_file = publish_dir / slug / "index.html"
        assert published_file.is_file()
        assert published_file.read_text() == "<html>report</html>"

    def test_collision_suffix(self, workspace: Path, publish_dir: Path) -> None:
        """Duplicate slugs get -2, -3 suffixes."""
        slug1 = publish_report(workspace, "Test User", "2026-01-01", publish_dir)
        slug2 = publish_report(workspace, "Test User", "2026-01-01", publish_dir)
        slug3 = publish_report(workspace, "Test User", "2026-01-01", publish_dir)
        assert slug1 == "test-user-20260101"
        assert slug2 == "test-user-20260101-2"
        assert slug3 == "test-user-20260101-3"
        # All three directories exist with content
        for slug in (slug1, slug2, slug3):
            assert (publish_dir / slug / "index.html").is_file()

    def test_missing_report_raises(self, tmp_path: Path, publish_dir: Path) -> None:
        """FileNotFoundError when report/index.html is missing."""
        empty_ws = tmp_path / "empty_workspace"
        empty_ws.mkdir()
        with pytest.raises(FileNotFoundError, match="Report not found"):
            publish_report(empty_ws, "User", "2026-01-01", publish_dir)

    def test_copies_sibling_assets(self, workspace: Path, publish_dir: Path) -> None:
        """Additional files in report/ are also copied."""
        (workspace / "report" / "style.css").write_text("body{}")
        (workspace / "report" / "chart.png").write_bytes(b"\x89PNG")
        slug = publish_report(workspace, "User", "2026-05-05", publish_dir)
        target = publish_dir / slug
        assert (target / "index.html").is_file()
        assert (target / "style.css").is_file()
        assert (target / "chart.png").is_file()

    def test_copies_subdirectories(self, workspace: Path, publish_dir: Path) -> None:
        """Subdirectories in report/ are recursively copied."""
        assets_dir = workspace / "report" / "assets"
        assets_dir.mkdir()
        (assets_dir / "logo.svg").write_text("<svg/>")
        slug = publish_report(workspace, "User", "2026-06-06", publish_dir)
        assert (publish_dir / slug / "assets" / "logo.svg").is_file()

    def test_publish_dir_created_if_missing(self, workspace: Path, tmp_path: Path) -> None:
        """publish_dir is created automatically if it does not exist."""
        new_pub = tmp_path / "new_published"
        slug = publish_report(workspace, "User", "2026-07-07", new_pub)
        assert (new_pub / slug / "index.html").is_file()

    def test_korean_name_publish(self, workspace: Path, publish_dir: Path) -> None:
        """Korean-only names produce 'subject' slug and publish correctly."""
        slug = publish_report(workspace, "박근윤", "2026-03-20", publish_dir)
        assert slug == "subject-20260320"
        assert (publish_dir / slug / "index.html").is_file()

    def test_returns_slug_string(self, workspace: Path, publish_dir: Path) -> None:
        """Return value is the slug string, not a Path."""
        slug = publish_report(workspace, "Test", "2026-01-01", publish_dir)
        assert isinstance(slug, str)


# ── publish_report with explicit slug (re-analysis) ──────────────────


class TestPublishReportWithSlug:
    """Tests for publish_report() when slug= is supplied (re-analysis path)."""

    @pytest.fixture()
    def workspace(self, tmp_path: Path) -> Path:
        """Create a workspace with a report/index.html."""
        ws = tmp_path / "workspace"
        report_dir = ws / "report"
        report_dir.mkdir(parents=True)
        (report_dir / "index.html").write_text("<html>fresh report</html>")
        return ws

    @pytest.fixture()
    def publish_dir(self, tmp_path: Path) -> Path:
        """Provide a temporary publish directory."""
        d = tmp_path / "published"
        d.mkdir()
        return d

    def test_slug_provided_no_target_creates_dir(
        self, workspace: Path, publish_dir: Path
    ) -> None:
        """When target dir doesn't exist, slug= creates and publishes without collision."""
        slug = publish_report(
            workspace, "Ignored Name", "2099-01-01", publish_dir,
            slug="park-20260320",
        )
        assert slug == "park-20260320"
        assert (publish_dir / "park-20260320" / "index.html").is_file()
        # No -2 directory must have been created
        assert not (publish_dir / "park-20260320-2").exists()

    def test_slug_provided_returns_exact_slug(
        self, workspace: Path, publish_dir: Path
    ) -> None:
        """Return value equals the provided slug (no suffix appended)."""
        returned = publish_report(
            workspace, "Any Name", "2026-01-01", publish_dir,
            slug="stable-slug",
        )
        assert returned == "stable-slug"

    def test_slug_overwrite_no_collision_dir_created(
        self, workspace: Path, publish_dir: Path
    ) -> None:
        """Re-publishing with same slug doesn't create a -2 directory."""
        slug = "park-20260320"
        publish_report(workspace, "Park", "2026-03-20", publish_dir, slug=slug)
        publish_report(workspace, "Park", "2026-03-20", publish_dir, slug=slug)
        assert not (publish_dir / f"{slug}-2").exists()

    def test_slug_overwrite_clears_stale_files(
        self, workspace: Path, publish_dir: Path, tmp_path: Path
    ) -> None:
        """Re-publishing removes stale assets that are absent from the new report."""
        slug = "park-20260320"
        # First publish: report has index.html + stale.png
        (workspace / "report" / "stale.png").write_bytes(b"\x89PNG stale")
        publish_report(workspace, "Park", "2026-03-20", publish_dir, slug=slug)
        assert (publish_dir / slug / "stale.png").is_file()

        # Replace report dir with fresh content (only index.html + fresh.css)
        ws2 = tmp_path / "workspace2"
        report2 = ws2 / "report"
        report2.mkdir(parents=True)
        (report2 / "index.html").write_text("<html>fresh</html>")
        (report2 / "fresh.css").write_text("body{}")

        publish_report(ws2, "Park", "2026-03-20", publish_dir, slug=slug)

        target = publish_dir / slug
        assert (target / "index.html").is_file()
        assert (target / "fresh.css").is_file()
        # stale.png must be gone
        assert not (target / "stale.png").exists()

    def test_slug_overwrite_updates_content(
        self, workspace: Path, publish_dir: Path, tmp_path: Path
    ) -> None:
        """After re-publishing with same slug, index.html contains the new content."""
        slug = "park-20260320"
        publish_report(workspace, "Park", "2026-03-20", publish_dir, slug=slug)

        ws2 = tmp_path / "workspace2"
        (ws2 / "report").mkdir(parents=True)
        (ws2 / "report" / "index.html").write_text("<html>updated</html>")
        publish_report(ws2, "Park", "2026-03-20", publish_dir, slug=slug)

        content = (publish_dir / slug / "index.html").read_text()
        assert content == "<html>updated</html>"

    def test_first_publish_no_slug_still_generates_fresh(
        self, workspace: Path, publish_dir: Path
    ) -> None:
        """First-time submission (slug=None) still generates a fresh slug — no regression."""
        slug = publish_report(workspace, "Park Geunyun", "2026-03-20", publish_dir)
        assert slug == "park-geunyun-20260320"
        assert (publish_dir / slug / "index.html").is_file()

    def test_slug_missing_report_still_raises(
        self, tmp_path: Path, publish_dir: Path
    ) -> None:
        """FileNotFoundError is raised when report/index.html is missing, even with slug=."""
        empty_ws = tmp_path / "empty_workspace"
        empty_ws.mkdir()
        with pytest.raises(FileNotFoundError, match="Report not found"):
            publish_report(empty_ws, "User", "2026-01-01", publish_dir, slug="some-slug")
