"""Coze-based OCR adapter for the local math demo."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv


load_dotenv()

MAX_COZE_RESPONSE_BYTES = 512 * 1024
COZE_API_BASE = os.getenv("COZE_API_BASE", "https://api.coze.cn").strip().rstrip("/")
COZE_API_TOKEN = os.getenv("COZE_API_TOKEN", "").strip()
COZE_BOT_ID = os.getenv("COZE_BOT_ID", "").strip()
COZE_TIMEOUT_SECONDS = max(
    5.0,
    min(90.0, float(os.getenv("COZE_TIMEOUT_SECONDS", "60") or 60)),
)
COZE_POLL_INTERVAL_SECONDS = max(
    0.0,
    min(5.0, float(os.getenv("COZE_POLL_INTERVAL_SECONDS", "0.8") or 0.8)),
)

COZE_OCR_PROMPT = """
请使用 OCR / Image2text 插件识别学生上传的高等数学题目图片。

要求：
1. 默认尽力识别，不要求图片特别清晰；只要题目主体可见，即使有轻微模糊、倾斜、阴影或手写标注，也应尝试完整转录。
2. 只输出题目原文，不计算、不判题、不解释、不补充图中没有的条件。
3. 保留题号、数字、正负号、系数、上下标、函数名、变量和积分上下限。
4. 公式使用纯文本表达，例如 x^2、sqrt(x)、pi、lim x->0 sin(x)/x。
5. 个别符号不清晰时，优先结合上下文给出最可能的读法，并在该符号后用括号标注“疑似”；不要因为局部不清就省略整道题。
6. 不要输出 Markdown、代码块、LaTeX 定界符或额外说明。
7. 只有题目主体严重模糊、关键区域被遮挡或图片不是题目时，才回复：识别可能不准确，请重新上传清晰、完整的题目图片。
""".strip()

_FAILED_CHAT_STATUSES = {"failed", "canceled", "requires_action"}
_ASSISTANT_TRAILING_NOTES = {
    "请确认识别是否正确。",
    "请确认识别是否正确，再继续帮我解题。",
    "请确认图片识别结果是否正确。",
    "请核对识别结果是否正确。",
    "请确认识别结果是否正确，再继续解题。",
}


def coze_ocr_configured() -> bool:
    """Return whether the Coze OCR route has both required credentials."""
    return bool(COZE_API_TOKEN and COZE_BOT_ID)


class CozeConfigurationError(RuntimeError):
    """Raised when the Coze OCR route has not been configured."""


class CozeUpstreamError(RuntimeError):
    """Raised when Coze cannot return a usable OCR transcription."""


def transcribe_question_image(data: bytes, mime_type: str) -> str:
    """Transcribe a math question image through the published Coze bot."""
    _require_configuration()
    file_id = _upload_image(data, mime_type)
    chat_data = _create_chat(file_id)
    conversation_id = str(chat_data.get("conversation_id") or "").strip()
    chat_id = str(chat_data.get("id") or chat_data.get("chat_id") or "").strip()
    if not conversation_id or not chat_id:
        raise CozeUpstreamError("图片识别服务没有返回有效的会话信息，请稍后重试。")

    _wait_for_chat(
        conversation_id,
        chat_id,
        str(chat_data.get("status") or "").strip().lower(),
    )
    messages = _list_messages(conversation_id, chat_id)
    text = _extract_answer(messages).strip()
    if not text:
        raise CozeUpstreamError(
            "图片中没有识别到可用题目，请重新上传清晰、完整的图片。"
        )
    return _clean_transcription(text)[:2000]


def _require_configuration() -> None:
    missing: list[str] = []
    if not COZE_API_TOKEN:
        missing.append("COZE_API_TOKEN")
    if not COZE_BOT_ID:
        missing.append("COZE_BOT_ID")
    if missing:
        names = "、".join(missing)
        raise CozeConfigurationError(
            f"图片识别服务未配置，请在服务器环境变量中设置 {names}，然后重新加载服务。"
        )


def _upload_image(data: bytes, mime_type: str) -> str:
    boundary = f"----codex-coze-{uuid.uuid4().hex}"
    extension = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
    }.get(mime_type, "png")
    filename = f"question.{extension}"
    body = b"".join(
        (
            f"--{boundary}\r\n".encode("ascii"),
            (
                f'Content-Disposition: form-data; name="file"; '
                f'filename="{filename}"\r\n'
            ).encode("ascii"),
            f"Content-Type: {mime_type}\r\n\r\n".encode("ascii"),
            data,
            f"\r\n--{boundary}--\r\n".encode("ascii"),
        )
    )
    payload = _request_json(
        f"{COZE_API_BASE}/v1/files/upload",
        method="POST",
        headers={
            "Authorization": f"Bearer {COZE_API_TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        body=body,
    )
    response_data = _response_data(payload, "上传图片")
    file_id = str(response_data.get("id") or response_data.get("file_id") or "").strip()
    if not file_id:
        raise CozeUpstreamError("图片上传成功，但没有获得有效的文件标识。")
    return file_id


def _create_chat(file_id: str) -> dict[str, Any]:
    content = json.dumps(
        [
            {"type": "text", "text": COZE_OCR_PROMPT},
            {"type": "image", "file_id": file_id},
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    payload = _request_json(
        f"{COZE_API_BASE}/v3/chat",
        method="POST",
        headers={
            "Authorization": f"Bearer {COZE_API_TOKEN}",
            "Content-Type": "application/json; charset=utf-8",
        },
        body=json.dumps(
            {
                "bot_id": COZE_BOT_ID,
                "user_id": "local-web-demo",
                "stream": False,
                "auto_save_history": True,
                "additional_messages": [
                    {
                        "role": "user",
                        "type": "question",
                        "content_type": "object_string",
                        "content": content,
                    }
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8"),
    )
    return _response_data(payload, "创建识别任务")


def _wait_for_chat(
    conversation_id: str,
    chat_id: str,
    initial_status: str,
) -> None:
    status = initial_status
    deadline = time.monotonic() + COZE_TIMEOUT_SECONDS
    while status != "completed":
        if status in _FAILED_CHAT_STATUSES:
            raise CozeUpstreamError("图片识别任务未完成，请重新上传图片后再试。")
        if time.monotonic() >= deadline:
            raise CozeUpstreamError("图片识别超时，请稍后重试。")
        if COZE_POLL_INTERVAL_SECONDS:
            time.sleep(COZE_POLL_INTERVAL_SECONDS)

        query = urlencode(
            {
                "conversation_id": conversation_id,
                "chat_id": chat_id,
            }
        )
        payload = _request_json(
            f"{COZE_API_BASE}/v3/chat/retrieve?{query}",
            method="POST",
            headers={"Authorization": f"Bearer {COZE_API_TOKEN}"},
        )
        response_data = _response_data(payload, "查询识别状态")
        status = str(response_data.get("status") or "").strip().lower()


def _list_messages(conversation_id: str, chat_id: str) -> list[dict[str, Any]]:
    query = urlencode(
        {
            "conversation_id": conversation_id,
            "chat_id": chat_id,
        }
    )
    payload = _request_json(
        f"{COZE_API_BASE}/v3/chat/message/list?{query}",
        method="GET",
        headers={"Authorization": f"Bearer {COZE_API_TOKEN}"},
    )
    data = payload.get("data")
    if not isinstance(data, list):
        raise CozeUpstreamError("图片识别服务返回了无法读取的消息内容。")
    return [item for item in data if isinstance(item, dict)]


def _extract_answer(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        if message.get("type") != "answer":
            continue
        text = _content_as_text(message.get("content")).strip()
        if text:
            return text
    return ""


def _content_as_text(content: Any) -> str:
    if isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith(("[", "{")):
            try:
                return _content_as_text(json.loads(stripped))
            except (TypeError, ValueError, json.JSONDecodeError):
                return content
        return content
    if isinstance(content, dict):
        for key in ("text", "content", "value"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""
    if isinstance(content, list):
        parts = [_content_as_text(item).strip() for item in content]
        return "\n".join(part for part in parts if part)
    return ""


def _clean_transcription(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 2:
            cleaned = "\n".join(lines[1:-1]).strip()
    lines = cleaned.splitlines()
    while lines and (
        not lines[-1].strip() or lines[-1].strip() in _ASSISTANT_TRAILING_NOTES
    ):
        lines.pop()
    return "\n".join(lines).strip()


def _response_data(payload: dict[str, Any], action: str) -> dict[str, Any]:
    code = payload.get("code")
    if code not in (None, 0, "0"):
        message = str(payload.get("msg") or payload.get("message") or "").strip()
        detail = f"：{message[:200]}" if message else ""
        raise CozeUpstreamError(f"{action}失败{detail}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise CozeUpstreamError(f"{action}时没有返回有效数据。")
    return data


def _request_json(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    body: bytes | None = None,
) -> dict[str, Any]:
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=COZE_TIMEOUT_SECONDS) as response:
            raw_response = response.read(MAX_COZE_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        detail = _http_error_detail(exc)
        suffix = f"：{detail}" if detail else ""
        raise CozeUpstreamError(
            f"图片识别服务返回错误（{exc.code}）{suffix}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise CozeUpstreamError("暂时无法连接图片识别服务，请稍后重试。") from exc

    if len(raw_response) > MAX_COZE_RESPONSE_BYTES:
        raise CozeUpstreamError("图片识别服务返回内容过大，请重新上传图片。")
    try:
        payload = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CozeUpstreamError("图片识别服务返回了无法读取的内容。") from exc
    if not isinstance(payload, dict):
        raise CozeUpstreamError("图片识别服务返回了无法识别的数据结构。")
    return payload


def _http_error_detail(exc: HTTPError) -> str:
    try:
        raw = exc.read(MAX_COZE_RESPONSE_BYTES)
        payload = json.loads(raw.decode("utf-8"))
    except (AttributeError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    message = payload.get("msg") or payload.get("message") or payload.get("error")
    return str(message).strip()[:200]
