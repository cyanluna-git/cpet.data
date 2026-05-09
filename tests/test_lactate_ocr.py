"""
tests/test_lactate_ocr.py — Tests for lactate OCR service and API endpoint.

Covers:
  (a) Roundtrip: generated markdown → parse_lactate() → non-empty blood_df
  (b) 503 when ANTHROPIC_API_KEY is missing
  (c) 502 on Claude API exception
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from server.db import complete_onboarding, init_db, upsert_user
from server.main import app


# ── App state fixture ────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _setup_app_state(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "cpet_platform.db"
    init_db(db_path)

    app.state.db_path = db_path
    app.state.data_dir = data_dir
    app.state.channel_url = "http://127.0.0.1:9999"
    app.state.published_dir = tmp_path / "published"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _login_user(client: TestClient, google_id: str = "ocr-test-user") -> None:
    """Simulate Google OAuth callback to create a real session cookie."""
    db_path = app.state.db_path
    user = upsert_user(
        db_path,
        google_id=google_id,
        email=f"{google_id}@example.com",
        display_name="OCR Test User",
        avatar_url="",
    )
    complete_onboarding(db_path, user["id"], "OCR Test User")
    with patch(
        "server.auth.oauth.google.authorize_access_token",
        new_callable=AsyncMock,
    ) as mock_token:
        mock_token.return_value = {
            "userinfo": {
                "sub": google_id,
                "email": f"{google_id}@example.com",
                "name": "OCR Test User",
                "picture": "",
            }
        }
        client.get("/auth/google/callback", follow_redirects=False)


@pytest.fixture()
def logged_in_client() -> TestClient:
    """TestClient with a real session obtained via OAuth mock login."""
    c = TestClient(app, raise_server_exceptions=False)
    _login_user(c)
    return c


# ── (a) Roundtrip test ───────────────────────────────────────────────


def _make_ocr_rows() -> list[dict]:
    """Return a representative OCR result with rows from all 4 blocks."""
    return [
        {"step": "0",   "load_w": 0,   "duration_min": None, "kst_time": None, "hr_bpm": 60,  "lactate_mmol": 0.8,  "glucose_mmol": 5.5},
        {"step": "1-1", "load_w": 100, "duration_min": 4,    "kst_time": "09:05", "hr_bpm": 110, "lactate_mmol": 1.1, "glucose_mmol": 6.0},
        {"step": "1-2", "load_w": 140, "duration_min": 4,    "kst_time": "09:10", "hr_bpm": 125, "lactate_mmol": 1.5, "glucose_mmol": 6.2},
        {"step": "2-1", "load_w": 380, "duration_min": 0.5,  "kst_time": "09:30", "hr_bpm": 182, "lactate_mmol": 10.2, "glucose_mmol": 7.8},
        {"step": "3-1", "load_w": 170, "duration_min": 3,    "kst_time": "09:35", "hr_bpm": 155, "lactate_mmol": 12.0, "glucose_mmol": 8.0},
        {"step": "3-2", "load_w": 190, "duration_min": 3,    "kst_time": "09:38", "hr_bpm": 160, "lactate_mmol": 11.0, "glucose_mmol": 7.5},
    ]


def _serialize_ocr_rows_to_md(rows: list[dict]) -> str:
    """Replicate the JS serialization logic in Python for test purposes."""
    BLOCKS = {
        "rest":    {"label": "Block 0 — Rest (baseline)",                          "is_block3": False},
        "block_1": {"label": "Block 1 — LT1 (4min per step)",                     "is_block3": False},
        "block_2": {"label": "Block 2 — VO2max (30s ramp, sampled at end)",       "is_block3": False},
        "block_3": {"label": "Block 3 — Clearance (3min per step, %FTP sheet label)", "is_block3": True},
    }
    ORDER = ["rest", "block_1", "block_2", "block_3"]

    def detect_block(step: str | None) -> str:
        if not step:
            return "rest"
        s = str(step).strip()
        if s == "0":
            return "rest"
        if s.startswith("1-"):
            return "block_1"
        if s.startswith("2-"):
            return "block_2"
        if s.startswith("3-"):
            return "block_3"
        return "rest"

    def cell(v: object) -> str:
        if v is None or str(v).strip() == "":
            return "—"
        return str(v).strip()

    grouped: dict[str, list[dict]] = {k: [] for k in ORDER}
    for row in rows:
        block = detect_block(row.get("step"))
        grouped[block].append(row)

    md = "# Lactate & Glucose Manual Recording Data\n\n"
    md += "> AI OCR로 파싱된 데이터입니다. 사용 전 반드시 원본과 대조하세요.\n\n"

    for block_key in ORDER:
        info = BLOCKS[block_key]
        block_rows = grouped[block_key]
        if not block_rows:
            continue
        md += f"## {info['label']}\n\n"
        if info["is_block3"]:
            md += "| Step | %FTP | Load(W) | Duration(min) | KST | HR(bpm) | Lactate(mmol/L) | Glucose(mmol/L) | Notes |\n"
            md += "|------|------|---------|---------------|------|---------|-----------------|-----------------|-------|\n"
            for row in block_rows:
                md += (
                    f"| {cell(row.get('step'))} | — "
                    f"| {cell(row.get('load_w'))} "
                    f"| {cell(row.get('duration_min'))} "
                    f"| {cell(row.get('kst_time'))} "
                    f"| {cell(row.get('hr_bpm'))} "
                    f"| {cell(row.get('lactate_mmol'))} "
                    f"| {cell(row.get('glucose_mmol'))} "
                    "| |\n"
                )
        else:
            md += "| Step | Load(W) | Duration(min) | KST | HR(bpm) | Lactate(mmol/L) | Glucose(mmol/L) | Notes |\n"
            md += "|------|---------|---------------|------|---------|-----------------|-----------------|-------|\n"
            for row in block_rows:
                md += (
                    f"| {cell(row.get('step'))} "
                    f"| {cell(row.get('load_w'))} "
                    f"| {cell(row.get('duration_min'))} "
                    f"| {cell(row.get('kst_time'))} "
                    f"| {cell(row.get('hr_bpm'))} "
                    f"| {cell(row.get('lactate_mmol'))} "
                    f"| {cell(row.get('glucose_mmol'))} "
                    "| |\n"
                )
        md += "\n"

    return md


class TestRoundtrip:
    def test_serialized_md_roundtrips_through_parse_lactate(self, tmp_path: Path) -> None:
        """Markdown generated by the JS serializer logic round-trips through parse_lactate."""
        from pipeline.parsers.lactate import parse_lactate

        rows = _make_ocr_rows()
        md = _serialize_ocr_rows_to_md(rows)

        md_path = tmp_path / "lactate_data.md"
        md_path.write_text(md, encoding="utf-8")

        blood_df, _ = parse_lactate(md_path=md_path)
        assert not blood_df.empty, "blood_df should not be empty after roundtrip"

        # All four block types present
        blocks = set(blood_df["block"].tolist())
        assert "rest" in blocks
        assert "block_1" in blocks
        assert "block_2" in blocks
        assert "block_3" in blocks

        # block_3 rows must survive (requires 9-col format)
        b3 = blood_df[blood_df["block"] == "block_3"]
        assert len(b3) == 2, f"Expected 2 block_3 rows, got {len(b3)}"

        # ftp_pct column must be present; block_3 serializer writes "—" → parsed as None
        assert "ftp_pct" in blood_df.columns
        assert b3["ftp_pct"].isna().all(), "block_3 ftp_pct should be None for OCR-generated rows"

        # Numeric values parsed correctly
        row0 = blood_df[blood_df["block"] == "rest"].iloc[0]
        assert row0["lactate_mmol"] == pytest.approx(0.8)

    def test_fixture_lactate_md_parses(self) -> None:
        """Existing fixture lactate_data.md must parse to a non-empty blood_df."""
        from pipeline.parsers.lactate import parse_lactate

        fixture = Path(__file__).parent / "fixtures" / "hong_changsun" / "raw" / "lactate_data.md"
        if not fixture.exists():
            pytest.skip("fixture not present")
        blood_df, subject_info = parse_lactate(md_path=fixture)
        assert not blood_df.empty
        assert subject_info


# ── (b) 503 when API key is missing ─────────────────────────────────


class TestOcrEndpoint503:
    def test_returns_503_when_api_key_missing(self, logged_in_client: TestClient) -> None:
        """POST /api/lactate/ocr → 503 when ANTHROPIC_API_KEY is unset."""
        img_bytes = _make_minimal_png()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            # Reset the cached client so the missing key is detected
            import server.lactate_ocr as ocr_mod  # noqa: PLC0415
            ocr_mod._anthropic_client = None
            resp = logged_in_client.post(
                "/api/lactate/ocr",
                files={"image": ("test.png", io.BytesIO(img_bytes), "image/png")},
            )
        assert resp.status_code == 503
        assert "error" in resp.json()

    def test_returns_401_when_not_logged_in(self, client: TestClient) -> None:
        """POST /api/lactate/ocr → 401 when not logged in."""
        img_bytes = _make_minimal_png()
        resp = client.post(
            "/api/lactate/ocr",
            files={"image": ("test.png", io.BytesIO(img_bytes), "image/png")},
        )
        assert resp.status_code == 401


# ── (c) 502 on Claude API exception ─────────────────────────────────


class TestOcrEndpoint502:
    def test_returns_502_on_api_exception(self, logged_in_client: TestClient) -> None:
        """POST /api/lactate/ocr → 502 when extract_lactate_table raises LactateOcrError."""
        from server.lactate_ocr import LactateOcrError

        img_bytes = _make_minimal_png()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"}, clear=False):
            with patch(
                "server.lactate_ocr.extract_lactate_table",
                side_effect=LactateOcrError("Claude API error: 500"),
            ):
                # Reset cached client so the key check passes
                import server.lactate_ocr as ocr_mod  # noqa: PLC0415
                ocr_mod._anthropic_client = None
                resp = logged_in_client.post(
                    "/api/lactate/ocr",
                    files={"image": ("test.png", io.BytesIO(img_bytes), "image/png")},
                )
        assert resp.status_code == 502
        assert "error" in resp.json()

    def test_returns_400_for_invalid_mime(self, logged_in_client: TestClient) -> None:
        """POST /api/lactate/ocr → 400 for unsupported file type."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"}, clear=False):
            resp = logged_in_client.post(
                "/api/lactate/ocr",
                files={"image": ("test.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
            )
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_returns_400_for_oversized_image(self, logged_in_client: TestClient) -> None:
        """POST /api/lactate/ocr → 400 when image exceeds 10 MB."""
        big_png = _make_minimal_png() + b"\x00" * (11 * 1024 * 1024)
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"}, clear=False):
            resp = logged_in_client.post(
                "/api/lactate/ocr",
                files={"image": ("big.png", io.BytesIO(big_png), "image/png")},
            )
        assert resp.status_code == 400
        assert "error" in resp.json()


# ── Happy path with mocked Claude ────────────────────────────────────


class TestOcrEndpointSuccess:
    def test_returns_rows_on_success(self, logged_in_client: TestClient) -> None:
        """POST /api/lactate/ocr → 200 {"rows": [...]} when extract succeeds."""
        img_bytes = _make_minimal_png()
        expected_rows = [
            {"step": "0", "load_w": 0, "duration_min": None, "kst_time": None,
             "hr_bpm": 60, "lactate_mmol": 0.8, "glucose_mmol": 5.5},
        ]
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"}, clear=False):
            with patch(
                "server.lactate_ocr.extract_lactate_table",
                return_value=expected_rows,
            ):
                import server.lactate_ocr as ocr_mod  # noqa: PLC0415
                ocr_mod._anthropic_client = MagicMock()
                resp = logged_in_client.post(
                    "/api/lactate/ocr",
                    files={"image": ("sheet.jpg", io.BytesIO(img_bytes), "image/jpeg")},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert "rows" in data
        assert len(data["rows"]) == 1
        assert data["rows"][0]["step"] == "0"


# ── ALLOWED_EXTENSIONS regression ────────────────────────────────────


class TestAllowedExtensionsUnchanged:
    def test_jpg_direct_submit_is_rejected(self, logged_in_client: TestClient) -> None:
        """.jpg files sent to /api/submit must still be rejected (ALLOWED_EXTENSIONS unchanged).

        Adding image support to /api/lactate/ocr must not accidentally
        change the global ALLOWED_EXTENSIONS set used by /api/submit.
        """
        from server.api import ALLOWED_EXTENSIONS

        assert ".jpg" not in ALLOWED_EXTENSIONS, (
            ".jpg was added to ALLOWED_EXTENSIONS — this breaks the /api/submit contract"
        )
        assert ".jpeg" not in ALLOWED_EXTENSIONS, (
            ".jpeg was added to ALLOWED_EXTENSIONS"
        )
        assert ".png" not in ALLOWED_EXTENSIONS, (
            ".png was added to ALLOWED_EXTENSIONS"
        )

        img_bytes = _make_minimal_png()
        resp = logged_in_client.post(
            "/api/submit",
            data={"subject_name": "Test", "test_date": "2024-01-01"},
            files={"files": ("photo.jpg", io.BytesIO(img_bytes), "image/jpeg")},
        )
        assert resp.status_code == 400, (
            f"Expected 400 for .jpg upload to /api/submit, got {resp.status_code}"
        )
        body = resp.json()
        assert "error" in body


# ── Page route ────────────────────────────────────────────────────────


class TestLactateOcrPage:
    def test_page_redirects_when_not_logged_in(self, client: TestClient) -> None:
        """GET /lactate-ocr → redirect to login when not authenticated."""
        resp = client.get("/lactate-ocr", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/google/login" in resp.headers.get("location", "")

    def test_page_renders_when_logged_in(self, logged_in_client: TestClient) -> None:
        """GET /lactate-ocr → 200 HTML when authenticated."""
        resp = logged_in_client.get("/lactate-ocr")
        assert resp.status_code == 200
        assert b"lactate_data.md" in resp.content


# ── Helpers ──────────────────────────────────────────────────────────


def _make_minimal_png() -> bytes:
    """Return a minimal valid 1×1 PNG file."""
    import struct, zlib  # noqa: PLC0415, E401
    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00\xff\xff\xff"  # filter byte + RGB
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return signature + ihdr + idat + iend
