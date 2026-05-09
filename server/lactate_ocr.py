"""
server.lactate_ocr — Claude Vision OCR service for handwritten lactate sheets.

Extracts tabular blood sample data from a photo of a handwritten lactate
measurement sheet using the Anthropic Claude vision API.
"""

from __future__ import annotations

import base64
import os
from typing import Any

_anthropic_client: Any = None


class LactateOcrError(Exception):
    """Raised when OCR extraction fails (API error, timeout, or bad response)."""


def _get_client() -> Any:
    """Lazy-initialize the Anthropic client. Raises LactateOcrError if key is missing."""
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise LactateOcrError("ANTHROPIC_API_KEY is not set")
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise LactateOcrError("anthropic package not installed") from exc
    _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client


_SYSTEM_PROMPT = """\
You are a sports-science data entry assistant.
You will receive a photo of a handwritten lactate test measurement sheet.
Extract all blood-sample rows from the table and return them as a JSON array.

Each element must have exactly these 7 keys (use null for cells that are
unreadable, blank, or not clearly present — do NOT guess or invent values):

  step          : string  — e.g. "0", "1-1", "2-1", "3-1"
  load_w        : number or null  — watts
  duration_min  : number or null  — minutes
  kst_time      : string or null  — e.g. "09:12" in HH:MM format
  hr_bpm        : number or null  — heart-rate in bpm
  lactate_mmol  : number or null  — lactate in mmol/L
  glucose_mmol  : number or null  — glucose in mmol/L

Return ONLY a valid JSON array — no prose, no markdown fences, no extra keys.
"""


def extract_lactate_table(image_bytes: bytes, mime: str) -> list[dict]:
    """Call Claude Vision to extract a lactate table from an image.

    Args:
        image_bytes: Raw image content (JPEG or PNG).
        mime: MIME type string, e.g. "image/jpeg".

    Returns:
        List of row dicts with 7 keys each.

    Raises:
        LactateOcrError: When the API key is missing, the request fails,
                         times out, or the response cannot be parsed as JSON.
    """
    import json  # noqa: PLC0415
    import anthropic  # noqa: PLC0415

    client = _get_client()
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime,
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extract the lactate measurement table from this image.",
                        },
                    ],
                }
            ],
            timeout=30,
        )
    except anthropic.APITimeoutError as exc:
        raise LactateOcrError(f"Claude API timed out: {exc}") from exc
    except anthropic.APIError as exc:
        raise LactateOcrError(f"Claude API error: {exc}") from exc
    except Exception as exc:
        raise LactateOcrError(f"Unexpected OCR error: {exc}") from exc

    raw_text = response.content[0].text.strip()

    # Strip optional markdown code fences
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        raw_text = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    try:
        rows = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise LactateOcrError(f"Could not parse Claude response as JSON: {exc}") from exc

    if not isinstance(rows, list):
        raise LactateOcrError("Claude response is not a JSON array")

    return rows
