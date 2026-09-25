"""Image-to-question adapter for the public math demo."""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from deploy.demo_math_text import normalize_math_text


load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_VISION_RESPONSE_BYTES = 256 * 1024
SUPPORTED_IMAGE_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}

VISION_API_BASE = os.getenv("VISION_API_BASE", "").strip()
VISION_API_URL = os.getenv("VISION_API_URL", "").strip()
VISION_API_KEY = os.getenv("VISION_API_KEY", "").strip()
VISION_MODEL = os.getenv("VISION_MODEL", "").strip()
VISION_TIMEOUT_SECONDS = max(
    5.0,
    min(60.0, float(os.getenv("VISION_TIMEOUT_SECONDS", "30") or 30)),
)

VISION_PROMPT = """
你是高等数学题目转写助手。只识别用户提供的图片，不计算、不讲解、不补充图中没有的条件。
请按画面顺序逐题、逐行识别题号、已知条件、选项和问题。
如果图片包含多道题，必须保留原题号和换行，分别完整转写，不得合并、遗漏或串题。
数学表达式使用纯文本：乘方用 ^，除法用 /，平方根用 sqrt(...)，圆周率用 pi，
无穷用 oo，极限写成 lim x->0 sin(x)/x 这种形式。
必须区分容易混淆的符号：数字 0 与字母 O/o、数字 1 与字母 l/I、字母 x 与乘号 ×、
负号与减号、导数撇号与指数、积分上下限、上下标、绝对值以及向量箭头。
看不清的符号先结合上下文写最可能的读法，并紧跟在括号中标注“疑似”，例如 0（疑似 O）。
不要擅自改正疑似符号，不要遗漏题目中的条件。只有题目主体严重模糊、关键区域被遮挡
或图片不是数学题目时，才回复：无法识别为高等数学题目。
不要使用 Markdown、代码块、LaTeX 定界符或 $ 符号。
""".strip()


VISION_LAYOUT_PROMPT = """
请只判断图片中有几道彼此独立、带不同题号的题目。
不要计算或解题。同一道题内部的小问 (1)(2)、(1)、a)、b) 只算一道题。
只输出一个 JSON，例如：{"question_count": 4}。
如果只有一道题，输出 {"question_count": 1}。
""".strip()


class VisionConfigurationError(RuntimeError):
    """Raised when the vision service has not been configured."""


class VisionUpstreamError(RuntimeError):
    """Raised when the vision service cannot return a usable transcription."""


def _vision_chat_endpoint() -> str:
    """Return the explicit chat URL, or build one from an API base URL."""
    if VISION_API_URL:
        return VISION_API_URL

    base = VISION_API_BASE.rstrip("/")
    if not base:
        return ""
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def vision_ocr_configured() -> bool:
    """Return whether the direct vision route has all required credentials."""
    return bool(_vision_chat_endpoint() and VISION_API_KEY and VISION_MODEL)


def image_matches_type(data: bytes, mime_type: str) -> bool:
    """Check the common image signatures before sending data upstream."""
    normalized = (mime_type or "").lower().split(";", 1)[0].strip()
    if normalized not in SUPPORTED_IMAGE_TYPES:
        return False
    if normalized == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if normalized == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if normalized == "image/gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if normalized == "image/webp":
        return (
            len(data) >= 12
            and data.startswith(b"RIFF")
            and data[8:12] == b"WEBP"
        )
    return False


def transcribe_question_image(
    data: bytes,
    mime_type: str,
    *,
    timeout_seconds: float | None = None,
) -> str:
    """Transcribe a math question image with an OpenAI-compatible vision API."""
    if not vision_ocr_configured():
        raise VisionConfigurationError(
            "图片识别服务未配置，请设置 VISION_API_BASE（或 VISION_API_URL）、"
            "VISION_API_KEY 和 VISION_MODEL。"
        )

    request_timeout = VISION_TIMEOUT_SECONDS
    if timeout_seconds is not None:
        request_timeout = max(0.1, min(VISION_TIMEOUT_SECONDS, timeout_seconds))

    encoded = base64.b64encode(data).decode("ascii")
    payload = {
        "model": VISION_MODEL,
        "temperature": 0,
        "max_tokens": 2048,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{encoded}",
                        },
                    },
                ],
            }
        ],
    }
    if VISION_MODEL.lower().startswith("qwen3"):
        payload["enable_thinking"] = False
    request = Request(
        _vision_chat_endpoint(),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {VISION_API_KEY}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=request_timeout) as response:
            raw_response = response.read(MAX_VISION_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        if exc.code in {401, 403}:
            message = "图片识别服务鉴权失败，请检查 VISION_API_KEY。"
        elif exc.code == 429:
            message = "图片识别请求过于频繁，请稍后重试。"
        else:
            message = f"图片识别服务返回错误（{exc.code}），请稍后重试。"
        raise VisionUpstreamError(message) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise VisionUpstreamError("暂时无法连接图片识别服务，请稍后重试。") from exc

    if len(raw_response) > MAX_VISION_RESPONSE_BYTES:
        raise VisionUpstreamError("图片识别服务返回内容过大，请重新选择图片。")

    try:
        result = json.loads(raw_response.decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise VisionUpstreamError("图片识别服务返回了无法识别的内容。") from exc

    text = _content_as_text(content).strip()
    if not text:
        raise VisionUpstreamError("图片中没有识别到可用题目，请重新拍摄。")
    return _clean_transcription(text)[:4000]


def audit_question_count(
    data: bytes,
    mime_type: str,
    *,
    timeout_seconds: float | None = None,
) -> int | None:
    """Ask the vision model for a page-level independent-question count."""

    if not vision_ocr_configured():
        raise VisionConfigurationError("Vision OCR is not configured")

    request_timeout = VISION_TIMEOUT_SECONDS
    if timeout_seconds is not None:
        request_timeout = max(0.1, min(VISION_TIMEOUT_SECONDS, timeout_seconds))

    encoded = base64.b64encode(data).decode("ascii")
    payload = {
        "model": VISION_MODEL,
        "temperature": 0,
        "max_tokens": 96,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_LAYOUT_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{encoded}",
                        },
                    },
                ],
            }
        ],
    }
    if VISION_MODEL.lower().startswith("qwen3"):
        payload["enable_thinking"] = False
    request = Request(
        _vision_chat_endpoint(),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {VISION_API_KEY}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=request_timeout) as response:
            raw_response = response.read(MAX_VISION_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise VisionUpstreamError("Vision layout audit failed") from exc

    if len(raw_response) > MAX_VISION_RESPONSE_BYTES:
        raise VisionUpstreamError("Vision layout response is too large")
    try:
        result = json.loads(raw_response.decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise VisionUpstreamError("Vision layout response is invalid") from exc
    return _parse_question_count(_content_as_text(content))


def _parse_question_count(text: str) -> int | None:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 2:
            cleaned = "\n".join(lines[1:-1]).strip()
    try:
        parsed = json.loads(cleaned)
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = None
    if isinstance(parsed, dict):
        value = parsed.get("question_count")
        if isinstance(value, bool):
            return None
        try:
            count = int(value)
        except (TypeError, ValueError):
            count = 0
        return count if 1 <= count <= 20 else None

    match = re.search(r'"?question_count"?\D{0,3}(\d{1,2})', cleaned)
    if match is None:
        match = re.fullmatch(r"\s*(\d{1,2})\s*", cleaned)
    if match is None:
        return None
    count = int(match.group(1))
    return count if 1 <= count <= 20 else None


def _content_as_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)


def _clean_transcription(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 2:
            cleaned = "\n".join(lines[1:-1]).strip()
    return normalize_math_text(cleaned)
