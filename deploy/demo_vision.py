"""Image-to-question adapter for the public math demo."""

from __future__ import annotations

import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MAX_IMAGE_BYTES = 6 * 1024 * 1024
MAX_VISION_RESPONSE_BYTES = 256 * 1024
SUPPORTED_IMAGE_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}

VISION_API_URL = os.getenv("VISION_API_URL", "").strip()
VISION_API_KEY = os.getenv("VISION_API_KEY", "").strip()
VISION_MODEL = os.getenv("VISION_MODEL", "").strip()
VISION_TIMEOUT_SECONDS = max(
    5.0,
    min(60.0, float(os.getenv("VISION_TIMEOUT_SECONDS", "30") or 30)),
)

VISION_PROMPT = """
你是高等数学题目转写助手。只识别用户提供的图片，不计算、不讲解、不补充图中没有的条件。
请输出一段可以直接发送给解题系统的中文题目文字，保留题号、已知条件、选项和问题。
数学表达式使用纯文本：乘方用 ^，除法用 /，平方根用 sqrt(...)，圆周率用 pi，
无穷用 oo，极限写成 lim x->0 sin(x)/x 这种形式。
不要使用 Markdown、代码块、LaTeX 定界符或 $ 符号。如果图片不是数学题目，
只回复：无法识别为高等数学题目。
""".strip()


class VisionConfigurationError(RuntimeError):
    """Raised when the vision service has not been configured."""


class VisionUpstreamError(RuntimeError):
    """Raised when the vision service cannot return a usable transcription."""


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


def transcribe_question_image(data: bytes, mime_type: str) -> str:
    """Transcribe a math question image with an OpenAI-compatible vision API."""
    if not VISION_API_URL or not VISION_API_KEY or not VISION_MODEL:
        raise VisionConfigurationError(
            "图片识别服务未配置，请设置 VISION_API_URL、VISION_API_KEY 和 VISION_MODEL。"
        )

    encoded = base64.b64encode(data).decode("ascii")
    payload = {
        "model": VISION_MODEL,
        "temperature": 0,
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
    request = Request(
        VISION_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {VISION_API_KEY}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=VISION_TIMEOUT_SECONDS) as response:
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
    return text[:2000]


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
