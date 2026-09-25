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

from deploy.demo_math_text import normalize_math_text


load_dotenv()

MAX_COZE_RESPONSE_BYTES = 512 * 1024
COZE_API_BASE = os.getenv("COZE_API_BASE", "https://api.coze.cn").strip().rstrip("/")
COZE_API_TOKEN = os.getenv("COZE_API_TOKEN", "").strip()
COZE_BOT_ID = os.getenv("COZE_BOT_ID", "").strip()
COZE_OCR_WORKFLOW_ID = os.getenv("COZE_OCR_WORKFLOW_ID", "").strip()
COZE_OCR_IMAGE_PARAMETER = (
    os.getenv("COZE_OCR_IMAGE_PARAMETER", "image").strip() or "image"
)
COZE_OCR_IMAGE_PARAMETER_FORMAT = os.getenv(
    "COZE_OCR_IMAGE_PARAMETER_FORMAT",
    "file_id",
).strip().lower() or "file_id"
COZE_OCR_OUTPUT_FIELD = os.getenv("COZE_OCR_OUTPUT_FIELD", "").strip()
COZE_OCR_WORKFLOW_BOT_ID = os.getenv(
    "COZE_OCR_WORKFLOW_BOT_ID",
    "",
).strip()
COZE_TIMEOUT_SECONDS = max(
    5.0,
    min(90.0, float(os.getenv("COZE_TIMEOUT_SECONDS", "60") or 60)),
)
COZE_POLL_INTERVAL_SECONDS = max(
    0.0,
    min(5.0, float(os.getenv("COZE_POLL_INTERVAL_SECONDS", "0.8") or 0.8)),
)
COZE_POLL_DELAYS = (0.15, 0.3, 0.5)

COZE_OCR_PROMPT = """
请使用 OCR / Image2text 插件识别学生上传的高等数学题目图片。

要求：
1. 默认尽力识别；只要题目主体可见，即使有轻微模糊、倾斜、阴影或手写标注，也应完整转录。
2. 只输出题目原文，不计算、不判题、不解释、不补充图中没有的条件。
3. 若图片包含多道题，必须按题号逐题分行完整转写，不得合并、遗漏或串题。
4. 保留题号、数字、正负号、系数、上下标、函数名、变量和积分上下限。
5. 必须区分容易混淆的符号：数字 0 与字母 O/o、数字 1 与字母 l/I、字母 x 与乘号 ×、负号与减号、导数撇号与指数、积分上下限、绝对值以及向量箭头。
6. 看不清的符号先结合上下文写最可能的读法，并紧跟括号标注“疑似”，例如 0（疑似 O）；不要擅自改正，也不要因为局部不清就省略整道题。
7. 公式使用纯文本表达，例如 x^2、sqrt(x)、pi、lim x->0 sin(x)/x。
8. 不要输出 Markdown、代码块、LaTeX 定界符或额外说明。
9. 只有题目主体严重模糊、关键区域被遮挡或图片不是题目时，才回复：识别可能不准确，请重新上传清晰、完整的题目图片。
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
    return bool(COZE_API_TOKEN and (COZE_OCR_WORKFLOW_ID or COZE_BOT_ID))


def coze_ocr_mode() -> str:
    """Return the configured Coze OCR route."""
    if COZE_OCR_WORKFLOW_ID:
        return "workflow"
    if COZE_BOT_ID:
        return "bot"
    return "unconfigured"


_NORMALIZED_ASSISTANT_TRAILING_NOTES = {
    normalize_math_text(note) for note in _ASSISTANT_TRAILING_NOTES
}


class CozeConfigurationError(RuntimeError):
    """Raised when the Coze OCR route has not been configured."""


class CozeUpstreamError(RuntimeError):
    """Raised when Coze cannot return a usable OCR transcription."""


def transcribe_question_image(data: bytes, mime_type: str) -> str:
    """Transcribe a math question image through the published Coze bot."""
    _require_configuration()
    if COZE_OCR_WORKFLOW_ID:
        try:
            return _transcribe_with_workflow(data, mime_type)
        except CozeUpstreamError as workflow_error:
            if not COZE_BOT_ID:
                raise
            try:
                return _transcribe_with_bot(data, mime_type)
            except CozeUpstreamError as bot_error:
                raise CozeUpstreamError(
                    "专用识图工作流和机器人回退均失败："
                    f"{workflow_error}；{bot_error}"
                ) from bot_error
    return _transcribe_with_bot(data, mime_type)


def _transcribe_with_bot(
    data: bytes,
    mime_type: str,
    file_id: str | None = None,
    *,
    deadline: float | None = None,
) -> str:
    """Transcribe an image through the general Coze bot conversation."""
    deadline = deadline or time.monotonic() + COZE_TIMEOUT_SECONDS
    if file_id is None:
        file_id = _upload_image(data, mime_type, deadline=deadline)
    chat_data = _create_chat(file_id, deadline=deadline)
    conversation_id = str(chat_data.get("conversation_id") or "").strip()
    chat_id = str(chat_data.get("id") or chat_data.get("chat_id") or "").strip()
    if not conversation_id or not chat_id:
        raise CozeUpstreamError("图片识别服务没有返回有效的会话信息，请稍后重试。")

    _wait_for_chat(
        conversation_id,
        chat_id,
        str(chat_data.get("status") or "").strip().lower(),
        deadline=deadline,
    )
    messages = _list_messages(conversation_id, chat_id, deadline=deadline)
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
    if not COZE_OCR_WORKFLOW_ID and not COZE_BOT_ID:
        missing.append("COZE_BOT_ID")
    if missing:
        names = "、".join(missing)
        raise CozeConfigurationError(
            f"图片识别服务未配置，请在服务器环境变量中设置 {names}，然后重新加载服务。"
        )


def _upload_image(data: bytes, mime_type: str, *, deadline: float) -> str:
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
        deadline=deadline,
    )
    response_data = _response_data(payload, "上传图片")
    file_id = str(response_data.get("id") or response_data.get("file_id") or "").strip()
    if not file_id:
        raise CozeUpstreamError("图片上传成功，但没有获得有效的文件标识。")
    return file_id


def _transcribe_with_workflow(data: bytes, mime_type: str) -> str:
    deadline = time.monotonic() + COZE_TIMEOUT_SECONDS
    file_id = _upload_image(data, mime_type, deadline=deadline)
    try:
        return _run_ocr_workflow(file_id, deadline=deadline)
    except CozeUpstreamError as workflow_error:
        if not COZE_BOT_ID:
            raise
        bot_deadline = time.monotonic() + COZE_TIMEOUT_SECONDS
        try:
            return _transcribe_with_bot(
                b"",
                mime_type,
                file_id=file_id,
                deadline=bot_deadline,
            )
        except CozeUpstreamError as bot_error:
            raise CozeUpstreamError(str(bot_error)) from workflow_error


def _run_ocr_workflow(file_id: str, *, deadline: float) -> str:
    if COZE_OCR_IMAGE_PARAMETER_FORMAT == "file_object":
        image_parameter: Any = {"file_id": file_id}
    else:
        image_parameter = file_id

    body: dict[str, Any] = {
        "workflow_id": COZE_OCR_WORKFLOW_ID,
        "parameters": {
            COZE_OCR_IMAGE_PARAMETER: image_parameter,
        },
        "is_async": False,
    }
    if COZE_OCR_WORKFLOW_BOT_ID:
        body["bot_id"] = COZE_OCR_WORKFLOW_BOT_ID

    payload = _request_json(
        f"{COZE_API_BASE}/v1/workflow/run",
        method="POST",
        headers={
            "Authorization": f"Bearer {COZE_API_TOKEN}",
            "Content-Type": "application/json; charset=utf-8",
        },
        body=json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8"),
        deadline=deadline,
    )
    data_value = _response_data_value(payload, "运行识图工作流")
    text = _extract_workflow_text(data_value, COZE_OCR_OUTPUT_FIELD).strip()
    if not text:
        raise CozeUpstreamError(
            "识图工作流没有返回可用文字，请检查结束节点和输出字段配置。"
        )
    return _clean_transcription(text)[:2000]


def _create_chat(file_id: str, *, deadline: float) -> dict[str, Any]:
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
        deadline=deadline,
    )
    return _response_data(payload, "创建识别任务")


def _wait_for_chat(
    conversation_id: str,
    chat_id: str,
    initial_status: str,
    *,
    deadline: float,
) -> None:
    status = initial_status
    attempt = 0
    while status != "completed":
        if status in _FAILED_CHAT_STATUSES:
            raise CozeUpstreamError("图片识别任务未完成，请重新上传图片后再试。")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CozeUpstreamError("图片识别超时，请稍后重试。")
        delay = min(_poll_delay(attempt), remaining)
        if delay:
            time.sleep(delay)

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
            deadline=deadline,
        )
        response_data = _response_data(payload, "查询识别状态")
        status = str(response_data.get("status") or "").strip().lower()
        attempt += 1


def _list_messages(
    conversation_id: str,
    chat_id: str,
    *,
    deadline: float,
) -> list[dict[str, Any]]:
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
        deadline=deadline,
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


def _extract_workflow_text(value: Any, output_field: str = "") -> str:
    if output_field:
        selected = _workflow_field_value(value, output_field)
        if selected is None:
            return ""
        return _workflow_text_from_value(selected)
    return _workflow_text_from_value(value)


def _workflow_field_value(value: Any, field: str) -> Any:
    current = _parse_json_container(value)
    for part in (item.strip() for item in field.split(".")):
        if not part:
            continue
        current = _parse_json_container(current)
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _workflow_text_from_value(value: Any) -> str:
    value = _parse_json_container(value)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_workflow_text_from_value(item).strip() for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        preferred_keys = (
            "ocr_text",
            "text",
            "content",
            "output",
            "result",
            "answer",
            "data",
            "message",
        )
        for key in preferred_keys:
            if key not in value:
                continue
            text = _workflow_text_from_value(value[key]).strip()
            if text:
                return text
        for key, item in value.items():
            if key in {"debug_url", "usage", "error_code", "error_message"}:
                continue
            text = _workflow_text_from_value(item).strip()
            if text:
                return text
    return ""


def _parse_json_container(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped.startswith(("{", "[")):
        return value
    try:
        return json.loads(stripped)
    except (TypeError, ValueError, json.JSONDecodeError):
        return value


def _clean_transcription(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 2:
            cleaned = "\n".join(lines[1:-1]).strip()
    cleaned = normalize_math_text(cleaned)
    lines = cleaned.splitlines()
    while lines and (
        not lines[-1].strip()
        or lines[-1].strip() in _NORMALIZED_ASSISTANT_TRAILING_NOTES
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


def _response_data_value(payload: dict[str, Any], action: str) -> Any:
    code = payload.get("code")
    if code not in (None, 0, "0"):
        message = str(payload.get("msg") or payload.get("message") or "").strip()
        detail = f"：{message[:200]}" if message else ""
        raise CozeUpstreamError(f"{action}失败{detail}")

    if "data" not in payload or payload.get("data") is None:
        raise CozeUpstreamError(f"{action}时没有返回有效数据。")
    return payload["data"]


def _request_json(
    url: str,
    *,
    method: str,
    headers: dict[str, str],
    body: bytes | None = None,
    deadline: float | None = None,
) -> dict[str, Any]:
    request = Request(url, data=body, headers=headers, method=method)
    timeout = COZE_TIMEOUT_SECONDS
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CozeUpstreamError("图片识别超时，请稍后重试。")
        timeout = max(0.1, min(COZE_TIMEOUT_SECONDS, remaining))
    try:
        with urlopen(request, timeout=timeout) as response:
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


def _poll_delay(attempt: int) -> float:
    if COZE_POLL_INTERVAL_SECONDS <= 0:
        return 0.0
    if attempt < len(COZE_POLL_DELAYS):
        return min(COZE_POLL_INTERVAL_SECONDS, COZE_POLL_DELAYS[attempt])
    return COZE_POLL_INTERVAL_SECONDS


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
