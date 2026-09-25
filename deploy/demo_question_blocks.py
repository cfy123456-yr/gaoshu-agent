"""Detect independent question blocks and whole-page image layouts."""

from __future__ import annotations

import re
from typing import Any


_ARABIC_NUMBER_TOKEN = r"\d{1,2}"
_CHINESE_NUMBER_TOKEN = r"[一二三四五六七八九十百]+"
_NUMBER_TOKEN = rf"(?:{_ARABIC_NUMBER_TOKEN}|{_CHINESE_NUMBER_TOKEN})"
_QUESTION_SEPARATOR_PATTERN = r"[、.．,，;；:：)）]"
_QUESTION_START_RE = re.compile(
    rf"(?m)(?P<prefix>^[ \t]*(?:"
    rf"第\s*(?P<named_label>{_NUMBER_TOKEN})\s*题"
    rf"|(?P<bare_number>{_ARABIC_NUMBER_TOKEN})"
    rf"\s*{_QUESTION_SEPARATOR_PATTERN}(?!\d)"
    rf")\s*)"
)
_UNPUNCTUATED_QUESTION_START_RE = re.compile(
    rf"(?m)(?P<prefix>^[ \t]*"
    rf"(?P<bare_number>{_ARABIC_NUMBER_TOKEN})[ \t]+(?=\S))"
)
_SECTION_HEADING_RE = re.compile(
    r"^(?:"
    r"选\s*择\s*题|填\s*空\s*题|判\s*断\s*题|"
    r"计\s*算\s*题|解\s*答\s*题|证\s*明\s*题|"
    r"应\s*用\s*题|综\s*合\s*题|简\s*答\s*题|"
    r"单\s*选\s*题|多\s*选\s*题|论\s*述\s*题|作\s*图\s*题"
    r")"
    r"(?:\s*[（(][^）)\n]*(?:每小题|共\s*\d+\s*分|满分)"
    r"[^）)\n]*[）)]?)?"
    r"\s*[.。]?\s*$"
)
_SECTION_LINE_RE = re.compile(
    rf"^[ \t]*(?:第\s*{_NUMBER_TOKEN}\s*题|"
    rf"{_NUMBER_TOKEN}\s*{_QUESTION_SEPARATOR_PATTERN})"
    rf"\s*(?P<remainder>.*)$"
)
_SECTION_SEPARATOR_CHARS = "、.．)）:：,，。;；"
_QUESTION_CONTENT_RE = re.compile(r"[^\W\d_]")


def extract_question_blocks(text: str) -> list[dict[str, Any]]:
    """Split OCR text into top-level numbered question blocks.

    Parenthesized subparts such as ``(1)`` and ``(2)`` are intentionally left
    inside their parent question. The function only reports a split when at
    least two independent numbered starts are present.
    """

    value = str(text or "").strip()
    if not value:
        return []

    punctuated_matches = _question_start_matches(value, _QUESTION_START_RE)
    unpunctuated_matches = [
        match
        for match in _question_start_matches(
            value,
            _UNPUNCTUATED_QUESTION_START_RE,
        )
        if _looks_like_unpunctuated_question(value, match)
    ]
    combined_matches = _collapse_repeated_question_labels(
        _merge_question_start_matches(
            punctuated_matches,
            unpunctuated_matches,
        )
    )

    matches = punctuated_matches
    if (
        len(combined_matches) > len(punctuated_matches)
        and _is_consecutive_arabic_sequence(combined_matches)
    ):
        matches = combined_matches
    elif (
        len(matches) < 2
        and _is_consecutive_arabic_sequence(unpunctuated_matches)
    ):
        matches = unpunctuated_matches
    if len(matches) < 2:
        return []

    blocks: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        block_text = _trim_trailing_section_headings(value[start:end].strip())
        if not block_text:
            continue
        groups = match.groupdict()
        label = groups.get("named_label") or groups.get("bare_number") or ""
        blocks.append(
            {
                "index": len(blocks) + 1,
                "label": label.strip(),
                "text": block_text,
            }
        )

    return blocks if len(blocks) >= 2 else []


def strip_question_number_prefix(text: str) -> str:
    """Remove one leading top-level question label from OCR text."""

    value = str(text or "").strip()
    match = _QUESTION_START_RE.match(value)
    if match is None:
        candidate = _UNPUNCTUATED_QUESTION_START_RE.match(value)
        if candidate is not None and _looks_like_unpunctuated_question(
            value,
            candidate,
        ):
            match = candidate
    if match is None or _is_section_heading(value, match):
        return value

    remainder = value[match.end() :].lstrip()
    if not remainder or remainder[0] in "+-*/^=),]":
        return value
    return remainder


def _is_section_heading(value: str, match: re.Match[str]) -> bool:
    """Return whether a numbered line is a section heading, not a question."""

    line_end = value.find("\n", match.end())
    if line_end == -1:
        line_end = len(value)
    remainder = value[match.end() : line_end].strip().lstrip(
        _SECTION_SEPARATOR_CHARS
    )
    return bool(_SECTION_HEADING_RE.match(remainder))


def _question_start_matches(
    value: str,
    pattern: re.Pattern[str],
) -> list[re.Match[str]]:
    """Return non-heading question starts produced by one start pattern."""

    return [
        match
        for match in pattern.finditer(value)
        if not _is_section_heading(value, match)
    ]


def _looks_like_unpunctuated_question(
    value: str,
    match: re.Match[str],
) -> bool:
    """Reject arithmetic or fragment lines while accepting OCR question text."""

    line_end = value.find("\n", match.end())
    if line_end == -1:
        line_end = len(value)
    remainder = value[match.end() : line_end].strip()
    if len(remainder) < 2 or remainder[0] in "+-*/^=),]":
        return False
    return bool(_QUESTION_CONTENT_RE.search(remainder))


def _is_consecutive_arabic_sequence(matches: list[re.Match[str]]) -> bool:
    """Require OCR-only bare numbering to form a complete consecutive run."""

    if len(matches) < 2:
        return False
    bare_labels = [match.groupdict().get("bare_number") for match in matches]
    if any(label is None for label in bare_labels):
        return False
    labels = [int(label) for label in bare_labels]
    return all(
        current - previous == 1
        for previous, current in zip(labels, labels[1:])
    )


def _merge_question_start_matches(
    *match_groups: list[re.Match[str]],
) -> list[re.Match[str]]:
    """Merge overlapping numbering styles without duplicating one line."""

    ordered = sorted(
        (match for group in match_groups for match in group),
        key=lambda match: (match.start(), -(match.end() - match.start())),
    )
    merged: list[re.Match[str]] = []
    for match in ordered:
        if merged and match.start() < merged[-1].end():
            continue
        merged.append(match)
    return merged


def _collapse_repeated_question_labels(
    matches: list[re.Match[str]],
) -> list[re.Match[str]]:
    """Keep the first start when OCR repeats a question number on later lines."""

    collapsed: list[re.Match[str]] = []
    previous_bare_number: str | None = None
    for match in matches:
        bare_number = match.groupdict().get("bare_number")
        if bare_number is not None and bare_number == previous_bare_number:
            continue
        collapsed.append(match)
        previous_bare_number = bare_number
    return collapsed


def _trim_trailing_section_headings(text: str) -> str:
    """Keep a following section title out of the preceding question block."""

    lines = text.splitlines(keepends=True)
    while lines:
        stripped = lines[-1].strip()
        if not stripped:
            lines.pop()
            continue
        section_match = _SECTION_LINE_RE.match(lines[-1])
        if section_match and _SECTION_HEADING_RE.match(
            section_match.group("remainder").strip()
        ):
            lines.pop()
            continue
        break
    return "".join(lines).rstrip()


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
