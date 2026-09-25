"""Detect independent question blocks and whole-page image layouts."""

from __future__ import annotations

import re
from typing import Any


_NUMBER_TOKEN = r"(?:\d{1,2}|[一二三四五六七八九十百]+)"
_QUESTION_START_RE = re.compile(
    rf"(?m)(?P<prefix>^[ \t]*(?:"
    rf"第\s*{_NUMBER_TOKEN}\s*题"
    rf"|{_NUMBER_TOKEN}\s*[、.．)）](?!\d)"
    rf")\s*)"
)
_LABEL_RE = re.compile(
    rf"(?:第\s*(?P<label>{_NUMBER_TOKEN})\s*题|"
    rf"(?P<number>{_NUMBER_TOKEN})\s*[、.．)）])"
)


def extract_question_blocks(text: str) -> list[dict[str, Any]]:
    """Split OCR text into top-level numbered question blocks.

    Parenthesized subparts such as ``(1)`` and ``(2)`` are intentionally left
    inside their parent question. The function only reports a split when at
    least two independent numbered starts are present.
    """

    value = str(text or "").strip()
    if not value:
        return []

    matches = list(_QUESTION_START_RE.finditer(value))
    if len(matches) < 2:
        return []

    blocks: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        block_text = value[start:end].strip()
        if not block_text:
            continue
        label_match = _LABEL_RE.search(match.group("prefix"))
        label = ""
        if label_match:
            label = label_match.group("label") or label_match.group("number") or ""
        blocks.append(
            {
                "index": len(blocks) + 1,
                "label": label.strip(),
                "text": block_text,
            }
        )

    return blocks if len(blocks) >= 2 else []


def extract_question_blocks_from_payload(value: Any) -> list[dict[str, Any]]:
    """Normalize question blocks received from an adapter or cached payload."""

    if not isinstance(value, list):
        return []
    blocks: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        label = str(item.get("label") or "").strip()
        blocks.append(
            {
                "index": len(blocks) + 1,
                "label": label,
                "text": text,
            }
        )
    return blocks if len(blocks) >= 2 else []


def image_layout_hint(data: bytes, mime_type: str) -> dict[str, Any]:
    """Return image dimensions and a conservative whole-page hint.

    The detector reads only image headers, so it has no Pillow/OpenCV
    dependency. A tall image is not proof of multiple questions; callers must
    treat the hint as a request for review rather than as a definitive count.
    """

    normalized = str(mime_type or "").lower().split(";", 1)[0].strip()
    dimensions = _image_dimensions(data, normalized)
    if dimensions is None:
        return {
            "width": None,
            "height": None,
            "aspect_ratio": None,
            "suspected_multi": False,
        }

    width, height = dimensions
    aspect_ratio = height / width if width else None
    suspected_multi = bool(
        width > 0
        and height >= 1800
        and aspect_ratio is not None
        and aspect_ratio >= 1.85
    )
    return {
        "width": width,
        "height": height,
        "aspect_ratio": round(aspect_ratio, 3) if aspect_ratio is not None else None,
        "suspected_multi": suspected_multi,
    }


def _image_dimensions(data: bytes, mime_type: str) -> tuple[int, int] | None:
    if mime_type == "image/png":
        return _png_dimensions(data)
    if mime_type == "image/gif":
        return _gif_dimensions(data)
    if mime_type == "image/jpeg":
        return _jpeg_dimensions(data)
    if mime_type == "image/webp":
        return _webp_dimensions(data)
    return None


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    if data[12:16] != b"IHDR":
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return (width, height) if width > 0 and height > 0 else None


def _gif_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 10 or not data.startswith((b"GIF87a", b"GIF89a")):
        return None
    width = int.from_bytes(data[6:8], "little")
    height = int.from_bytes(data[8:10], "little")
    return (width, height) if width > 0 and height > 0 else None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or not data.startswith(b"\xff\xd8"):
        return None

    position = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while position + 3 < len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            break
        marker = data[position]
        position += 1
        if marker in {0x01, *range(0xD0, 0xD9)}:
            continue
        if marker in {0xDA, 0xD9}:
            break
        if position + 2 > len(data):
            break
        segment_length = int.from_bytes(data[position : position + 2], "big")
        if segment_length < 2 or position + segment_length > len(data):
            break
        if marker in sof_markers and segment_length >= 7:
            height = int.from_bytes(data[position + 3 : position + 5], "big")
            width = int.from_bytes(data[position + 5 : position + 7], "big")
            if width > 0 and height > 0:
                return (width, height)
            return None
        position += segment_length
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if (
        len(data) < 30
        or not data.startswith(b"RIFF")
        or data[8:12] != b"WEBP"
    ):
        return None
    if data[12:16] != b"VP8X":
        return None
    width = 1 + int.from_bytes(data[24:27], "little")
    height = 1 + int.from_bytes(data[27:30], "little")
    return (width, height) if width > 0 and height > 0 else None
