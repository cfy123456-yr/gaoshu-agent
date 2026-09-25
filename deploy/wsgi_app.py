"""Synchronous WSGI entry point used by PythonAnywhere."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from typing import Any

from fastapi import HTTPException
from flask import Flask, Response, jsonify, render_template, request
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException as WerkzeugHTTPException

from app.main import (
    API_KEY,
    IntegrateRequest,
    LimitRequest,
    PlotRequest,
    SolveRequest,
    VerifyRequest,
    calculate_plot,
    calculate_integral,
    calculate_limit,
    health_check,
    rate_limiter,
    solve_math,
    verify_derivative,
)
from deploy.demo_chat import (
    DemoChatRequest,
    _is_confirmation,
    _is_rejection,
    _normalize_text,
    _pending_ocr_question,
    _solve_confirmed_question,
    build_chat_response,
)
from deploy.demo_interval_solver import solve_interval_extrema
from deploy.demo_coze_ocr import (
    CozeConfigurationError,
    CozeUpstreamError,
    coze_ocr_configured,
    coze_ocr_mode,
    transcribe_question_image,
)
from deploy.demo_knowledge import (
    DEFAULT_RESULT_LIMIT,
    MAX_QUERY_CHARS,
    MAX_RESULT_LIMIT,
    search_knowledge,
)
from deploy.demo_question_blocks import (
    extract_question_blocks,
    extract_question_blocks_from_payload,
    image_layout_hint,
)
from deploy.demo_session import (
    AWAITING_OCR_CONFIRMATION,
    NO_PENDING_QUESTION_MESSAGE,
    OCR_FAILURE_MESSAGE,
    demo_sessions,
    is_valid_ocr_question,
)
from deploy.demo_vision import (
    MAX_IMAGE_BYTES,
    SUPPORTED_IMAGE_TYPES,
    VisionConfigurationError,
    VisionUpstreamError,
    audit_question_count as audit_vision_question_count,
    image_matches_type,
    transcribe_question_image as transcribe_vision_question_image,
    vision_ocr_configured,
)
from deploy.demo_windows_ocr import (
    WindowsOcrError,
    WindowsOcrUnavailable,
    windows_ocr_available,
    transcribe_question_image as transcribe_windows_question_image,
)


application = Flask(__name__)
application.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_BYTES + 1024 * 1024

_CHAT_CACHE_TTL_SECONDS = 300
_CHAT_CACHE_MAX_PER_SESSION = 40
_CHAT_CACHE_MAX_SESSIONS = 100
_chat_response_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_OCR_CACHE_TTL_SECONDS = 600
_OCR_CACHE_MAX_ENTRIES = 128
_ocr_response_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def is_public_demo_request() -> bool:
    return request.path == "/demo" or request.path.startswith("/demo/")


def is_public_health_request() -> bool:
    return request.path == "/health"


def is_public_plot_request() -> bool:
    return request.path == "/plot.svg"


def should_rate_limit_request() -> bool:
    if request.method == "OPTIONS":
        return False
    if request.path.startswith("/static/"):
        return False
    return request.path not in {"/health", "/demo/api/health"}


@application.before_request
def enforce_api_access():
    if (
        API_KEY
        and not is_public_demo_request()
        and not is_public_health_request()
        and not is_public_plot_request()
        and request.headers.get("X-API-Key") != API_KEY
    ):
        raise HTTPException(status_code=401, detail="Invalid API key")

    if should_rate_limit_request():
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        client_key = forwarded_for.split(",")[0].strip()
        if not client_key:
            client_key = request.remote_addr or "unknown"
        rate_limiter.check(client_key)


@application.errorhandler(HTTPException)
@application.errorhandler(WerkzeugHTTPException)
def handle_http_exception(exc):
    detail = getattr(exc, "detail", None) or getattr(exc, "description", "")
    response = jsonify({"detail": detail})
    response.status_code = (
        getattr(exc, "status_code", None) or getattr(exc, "code", 500) or 500
    )
    for name, value in (getattr(exc, "headers", None) or {}).items():
        response.headers[name] = value
    return response


@application.errorhandler(ValidationError)
def handle_validation_error(exc: ValidationError):
    return jsonify({"detail": "Validation error"}), 422


@application.errorhandler(Exception)
def handle_unexpected_error(exc: Exception):
    application.logger.exception("Unhandled request error", exc_info=exc)
    return jsonify({"detail": "Internal server error"}), 500


@application.get("/")
def service_index():
    return jsonify(
        {
            "service": "math-tool",
            "status": "ok",
            "health": "/health",
            "demo": "/demo",
            "endpoints": [
                "/demo",
                "/demo/api/verify",
                "/demo/api/integrate",
                "/demo/api/limit",
                "/demo/api/solve",
                "/demo/api/knowledge",
                "/demo/api/chat",
                "/demo/api/ocr",
                "/demo/api/session/reset",
                "/verify",
                "/verify-query",
                "/integrate",
                "/integrate-query",
                "/limit",
                "/limit-query",
                "/solve",
                "/plot",
                "/plot-query",
                "/plot.svg",
            ],
        }
    )


@application.get("/demo")
def demo_page():
    return render_template("demo.html")


@application.get("/demo/api/health")
def demo_health():
    payload = health_check()
    payload["demo"] = {
        "available": True,
        "page": "/demo",
        "service": "math-tool",
    }
    vision_configured = vision_ocr_configured()
    coze_configured = coze_ocr_configured()
    payload["ocr"] = {
        "provider": "vision" if vision_configured else "coze",
        "configured": vision_configured or coze_configured,
        "vision_configured": vision_configured,
        "coze_configured": coze_configured,
        "coze_mode": coze_ocr_mode(),
        "fallback": "windows" if windows_ocr_available() else "",
    }
    return jsonify(payload)


@application.post("/demo/api/knowledge")
def demo_knowledge():
    payload = request.get_json(silent=False)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid request payload")

    query = payload.get("query", "")
    if not isinstance(query, str):
        raise HTTPException(status_code=400, detail="query must be a string")
    query = query.strip()
    if len(query) > MAX_QUERY_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"query must not exceed {MAX_QUERY_CHARS} characters",
        )

    raw_limit = payload.get("limit", DEFAULT_RESULT_LIMIT)
    if isinstance(raw_limit, bool):
        raise HTTPException(status_code=400, detail="limit must be an integer")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="limit must be an integer",
        ) from exc
    limit = max(1, min(limit, MAX_RESULT_LIMIT))

    results = search_knowledge(query, limit=limit)
    return jsonify(
        {
            "query": query,
            "count": len(results),
            "engine": "local-markdown-v1",
            "results": [result.to_dict() for result in results],
        }
    )


@application.post("/demo/api/verify")
def demo_verify():
    payload = request.get_json(silent=False)
    model = VerifyRequest.model_validate(payload)
    return _json_response(verify_derivative(model, _=None))


@application.post("/demo/api/integrate")
def demo_integrate():
    payload = request.get_json(silent=False)
    model = IntegrateRequest.model_validate(payload)
    return _json_response(calculate_integral(model, _=None))


@application.post("/demo/api/limit")
def demo_limit():
    payload = request.get_json(silent=False)
    model = LimitRequest.model_validate(payload)
    return _json_response(calculate_limit(model, _=None))


@application.post("/demo/api/solve")
def demo_solve():
    payload = request.get_json(silent=False)
    model = SolveRequest.model_validate(payload)
    return _json_response(solve_math(model, _=None))


@application.post("/demo/api/plot")
def demo_plot():
    payload = request.get_json(silent=False)
    model = PlotRequest.model_validate(payload)
    return _json_response(calculate_plot(model))


@application.get("/demo/api/plot.svg")
def demo_plot_svg():
    model = _plot_request_from_query()
    result = calculate_plot(model)
    return _svg_response(result.svg)


@application.post("/demo/api/chat")
def demo_chat():
    payload = request.get_json(silent=False)
    model = DemoChatRequest.model_validate(payload)
    session_id = _demo_session_id()
    raw_message = str(model.message).strip()
    normalized = _normalize_text(raw_message)
    session = demo_sessions.get(session_id)
    carried_question = str(
        model.pending_question or payload.get("pending_question") or ""
    ).strip()
    history_question = _pending_ocr_question(model.history)
    session_question = session.pending_question
    confirmation_question = next(
        (
            question
            for question in (
                (
                    session_question
                    if session.state == AWAITING_OCR_CONFIRMATION
                    else ""
                ),
                carried_question,
                history_question,
            )
            if is_valid_ocr_question(question)
        ),
        "",
    )
    application.logger.warning(
        "Demo chat request: session=%s source=%s message=%r "
        "carried=%d history=%d session_state=%s session_question=%d",
        session_id,
        model.source,
        raw_message[:80],
        len(carried_question),
        len(history_question),
        session.state,
        len(session_question),
    )

    if model.source == "ocr" and raw_message != "确认":
        pending_question = model.message
        if not is_valid_ocr_question(pending_question):
            pending_question = session.pending_question
        if not is_valid_ocr_question(pending_question):
            demo_sessions.mark_ocr_failure(session_id)
            return jsonify(_ocr_failure_response())
        demo_sessions.remember_ocr_question(session_id, pending_question)
        return jsonify(_ocr_confirmation_response(pending_question))

    is_confirmation = raw_message == "确认" or _is_confirmation(normalized)
    if not is_confirmation and confirmation_question:
        compact = re.sub(r"[\s,，。！!？?；;]", "", normalized)
        is_confirmation = any(
            marker in compact
            for marker in ("确认", "正确", "无误", "继续", "开始")
        )
    is_rejection = _is_rejection(normalized)
    cache_key = (session_id, normalized)
    use_cache = (
        not is_confirmation
        and not is_rejection
        and session.state != AWAITING_OCR_CONFIRMATION
    )
    if use_cache:
        cached = _cached_chat_response(cache_key)
        if cached is not None:
            return jsonify(cached)

    if is_confirmation:
        # Fall back to the server-side OCR session unless the browser is
        # explicitly confirming one of the selected questions.
        pending_question = confirmation_question
        if (
            model.source == "ocr"
            and raw_message == "确认"
            and is_valid_ocr_question(carried_question)
        ):
            # Multi-question selection sends one explicit question per request.
            # Prefer that choice over a session left by the last uploaded image.
            pending_question = carried_question
        if not pending_question:
            return jsonify(_no_pending_question_response())
        demo_sessions.remember_ocr_question(session_id, pending_question)
        pending_question = demo_sessions.begin_solving(session_id)
        if not pending_question:
            return jsonify(_no_pending_question_response())
        try:
            try:
                response = (
                    solve_interval_extrema(pending_question)
                    or _solve_confirmed_question(pending_question, model.history)
                )
            except Exception:
                application.logger.exception(
                    "Confirmed OCR question failed: %s",
                    pending_question,
                )
                response = _confirmed_question_error_response()
            if (
                response.get("intent") == "unknown"
                and response.get("reply") == NO_PENDING_QUESTION_MESSAGE
            ):
                response["status"] = "needs_input"
                response["intent"] = "ocr_text_incomplete"
                response["reply"] = (
                    "已经读取到待解题目，但识别出的公式或文字不完整，"
                    "暂时无法可靠计算。请核对上方题干中的关键公式、符号和选项，"
                    "直接修改后再次发送。"
                )
            response["history_used"] = pending_question
            response["session_state"] = "solving"
            return _json_response(response)
        finally:
            try:
                demo_sessions.finish_solving(session_id)
            except Exception:
                application.logger.exception(
                    "Failed to clear solving session: %s",
                    session_id,
                )
                demo_sessions.reset(session_id)

    if is_rejection:
        demo_sessions.mark_ocr_failure(session_id)
        return jsonify(_ocr_reupload_response())

    if session.state == AWAITING_OCR_CONFIRMATION:
        demo_sessions.mark_ocr_failure(session_id)

    response = build_chat_response(model.message, model.history)
    if response.get("intent") == "ocr_confirm":
        recognized_question = str(response.get("formula_text", "")).strip()
        if is_valid_ocr_question(recognized_question):
            demo_sessions.remember_ocr_question(
                session_id,
                recognized_question,
            )
            response["session_state"] = AWAITING_OCR_CONFIRMATION
        return jsonify(response)
    if use_cache:
        _store_chat_response(cache_key, session_id, response)
    return jsonify(response)


@application.post("/demo/api/ocr")
def demo_ocr():
    started_at = time.perf_counter()
    session_id = _demo_session_id()
    uploaded = request.files.get("image")
    if uploaded is None:
        raise HTTPException(status_code=400, detail="请选择要识别的题目图片。")

    mime_type = (uploaded.mimetype or "").lower().split(";", 1)[0].strip()
    if mime_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="仅支持 JPG、PNG、WebP 或 GIF 图片。",
        )

    image_data = uploaded.read(MAX_IMAGE_BYTES + 1)
    if len(image_data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="图片不能超过 6 MB，请压缩后重试。",
        )
    if not image_matches_type(image_data, mime_type):
        raise HTTPException(status_code=400, detail="图片内容无法识别，请重新选择。")

    cache_key = hashlib.sha256(
        mime_type.encode("ascii", errors="ignore") + b"\0" + image_data
    ).hexdigest()
    cached = _cached_ocr_response(cache_key)
    if cached is not None:
        text = str(cached.get("text", "")).strip()
        payload = _cached_ocr_payload(cached, text)
        if not _ocr_payload_has_usable_text(payload):
            demo_sessions.mark_ocr_failure(session_id)
            return jsonify(_ocr_failure_response()), 422
        _remember_or_clear_ocr_question(session_id, payload)
        return jsonify(
            {
                **payload,
                "state": _ocr_response_state(payload),
                "requires_confirmation": not payload["selection_required"],
                "cache_hit": True,
                "elapsed_ms": _elapsed_milliseconds(started_at),
            }
        )

    try:
        text, provider, warning = _transcribe_demo_ocr(image_data, mime_type)
    except HTTPException as exc:
        demo_sessions.mark_ocr_failure(session_id)
        if exc.status_code >= 500:
            return jsonify({"detail": exc.detail}), exc.status_code
        return jsonify(_ocr_failure_response()), 422
    if "疑似" in text and not warning:
        warning = "识别结果包含疑似符号，请核对后再发送。"
    text = str(text or "").strip()
    payload = _build_ocr_payload(text, provider, warning, image_data, mime_type)
    if not _ocr_payload_has_usable_text(payload):
        demo_sessions.mark_ocr_failure(session_id)
        return jsonify(_ocr_failure_response()), 422

    _remember_or_clear_ocr_question(session_id, payload)
    _store_ocr_response(cache_key, payload)
    return jsonify(
        {
            **payload,
            "state": _ocr_response_state(payload),
            "requires_confirmation": not payload["selection_required"],
            "cache_hit": False,
            "elapsed_ms": _elapsed_milliseconds(started_at),
        }
    )


@application.post("/demo/api/session/reset")
def demo_session_reset():
    session_id = _demo_session_id()
    demo_sessions.reset(session_id)
    for cache_key in list(_chat_response_cache):
        if cache_key[0] == session_id:
            _chat_response_cache.pop(cache_key, None)
    return jsonify({"status": "ok", "state": "waiting_image"})


def _ocr_confirmation_response(question: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "intent": "ocr_confirm",
        "reply": (
            f"题目已识别，请核对：{question}。"
            "确认无误回复“确认”，我将开始计算。"
        ),
        "formula_latex": "",
        "formula_text": question,
        "calculation": None,
        "suggestions": [],
        "session_state": AWAITING_OCR_CONFIRMATION,
    }


def _ocr_failure_response() -> dict[str, Any]:
    return {
        "status": "error",
        "intent": "ocr_error",
        "reply": OCR_FAILURE_MESSAGE,
        "detail": OCR_FAILURE_MESSAGE,
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": [],
        "session_state": "waiting_image",
    }


def _no_pending_question_response() -> dict[str, Any]:
    return {
        "status": "needs_input",
        "intent": "needs_input",
        "reply": NO_PENDING_QUESTION_MESSAGE,
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": [],
        "session_state": "waiting_image",
    }


def _ocr_reupload_response() -> dict[str, Any]:
    return {
        "status": "ok",
        "intent": "ocr_reupload",
        "reply": "题目识别不正确，请重新上传清晰、完整的题目图片。",
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": [],
        "session_state": "waiting_image",
    }


def _confirmed_question_error_response() -> dict[str, Any]:
    return {
        "status": "error",
        "intent": "calculation",
        "reply": (
            "这次题目计算失败，可能是识别出的公式不完整。"
            "请重新上传清晰、完整的题目图片，或者直接输入题目。"
        ),
        "formula_latex": "",
        "formula_text": "",
        "calculation": None,
        "suggestions": [],
        "session_state": "waiting_image",
    }


def _build_ocr_payload(
    text: str,
    provider: str,
    warning: str,
    image_data: bytes,
    mime_type: str,
) -> dict[str, Any]:
    blocks = extract_question_blocks(text)
    layout = image_layout_hint(image_data, mime_type)
    audited_count: int | None = None
    if (
        provider == "vision"
        and len(blocks) < 2
        and layout["suspected_multi"]
    ):
        try:
            audited_count = audit_vision_question_count(image_data, mime_type)
        except (VisionConfigurationError, VisionUpstreamError) as exc:
            application.logger.warning(
                "Vision question-count audit failed: %s",
                exc,
                exc_info=True,
            )

    multiple_questions = len(blocks) >= 2 or bool(
        audited_count is not None and audited_count > 1
    )
    review_required = False
    if len(blocks) >= 2:
        warning = _merge_ocr_warning(
            warning,
            "识别到多道独立题目，请选择需要计算的题目，可多选或全选。",
        )
    elif audited_count is not None and audited_count > 1:
        review_required = True
        warning = _merge_ocr_warning(
            warning,
            "图片疑似包含多道题，但本次只完整识别出一题。"
            "请裁剪当前小题后重新识别，或确认当前识别结果。",
        )
    elif layout["suspected_multi"]:
        review_required = True
        warning = _merge_ocr_warning(
            warning,
            "图片为长图，可能包含多道题。"
            "请确认当前识别结果，或裁剪需要计算的小题后重新识别。",
        )

    selection_required = multiple_questions or review_required
    return {
        "text": text,
        "provider": provider,
        "warning": warning,
        "question_blocks": blocks,
        "multiple_questions": multiple_questions,
        "selection_required": selection_required,
        "review_required": review_required,
        "layout_suspected_multi": bool(layout["suspected_multi"]),
        "audited_question_count": audited_count,
    }


def _cached_ocr_payload(cached: dict[str, Any], text: str) -> dict[str, Any]:
    blocks = extract_question_blocks_from_payload(cached.get("question_blocks"))
    if not blocks:
        blocks = extract_question_blocks(text)
    multiple_questions = bool(
        cached.get("multiple_questions") or len(blocks) >= 2
    )
    selection_required = bool(
        cached.get("selection_required") or multiple_questions
    )
    review_required = bool(cached.get("review_required"))
    return {
        "text": text,
        "provider": str(cached.get("provider") or ""),
        "warning": str(cached.get("warning") or ""),
        "question_blocks": blocks,
        "multiple_questions": multiple_questions,
        "selection_required": selection_required,
        "review_required": review_required,
        "layout_suspected_multi": bool(cached.get("layout_suspected_multi")),
        "audited_question_count": cached.get("audited_question_count"),
    }


def _ocr_payload_has_usable_text(payload: dict[str, Any]) -> bool:
    blocks = payload.get("question_blocks")
    if isinstance(blocks, list) and blocks:
        return any(
            isinstance(block, dict)
            and is_valid_ocr_question(str(block.get("text") or ""))
            for block in blocks
        )
    return is_valid_ocr_question(str(payload.get("text") or ""))


def _remember_or_clear_ocr_question(
    session_id: str,
    payload: dict[str, Any],
) -> None:
    if payload.get("selection_required") or payload.get("review_required"):
        demo_sessions.mark_ocr_failure(session_id)
        return
    demo_sessions.remember_ocr_question(session_id, str(payload["text"]))


def _ocr_response_state(payload: dict[str, Any]) -> str:
    if payload.get("review_required"):
        return "awaiting_ocr_review"
    if payload.get("selection_required"):
        return "awaiting_question_selection"
    return AWAITING_OCR_CONFIRMATION


def _merge_ocr_warning(current: str, addition: str) -> str:
    parts = [str(current or "").strip(), str(addition or "").strip()]
    return " ".join(part for part in parts if part)


def _transcribe_demo_ocr(data: bytes, mime_type: str) -> tuple[str, str, str]:
    errors: list[str] = []
    configuration_error = ""
    upstream_configured = vision_ocr_configured() or coze_ocr_configured()

    if vision_ocr_configured():
        try:
            return (
                transcribe_vision_question_image(data, mime_type),
                "vision",
                "",
            )
        except (VisionConfigurationError, VisionUpstreamError) as exc:
            errors.append(str(exc))
            application.logger.warning("Vision OCR failed: %s", exc, exc_info=True)

    if coze_ocr_configured():
        try:
            return transcribe_question_image(data, mime_type), "coze", ""
        except CozeConfigurationError as exc:
            configuration_error = str(exc)
            if vision_ocr_configured():
                errors.append(configuration_error)
        except CozeUpstreamError as exc:
            errors.append(str(exc))

    # Never hide an upstream outage behind low-quality local OCR. The local
    # fallback can produce plausible-looking garbage that then gets confirmed
    # and solved as the wrong question.
    if upstream_configured:
        detail = "；".join(dict.fromkeys(error for error in errors if error))
        if not detail:
            detail = "图片识别服务暂时不可用。"
        raise HTTPException(status_code=502, detail=detail)

    try:
        return (
            transcribe_windows_question_image(data, mime_type),
            "windows",
            "已使用本机离线 OCR，公式可能不完整，请核对后再发送。",
        )
    except WindowsOcrUnavailable as exc:
        if not errors:
            errors.append(configuration_error)
    except WindowsOcrError as exc:
        errors.append(f"本机离线识别也未成功：{exc}")

    detail = "；".join(dict.fromkeys(error for error in errors if error))
    if not detail:
        detail = "图片识别服务未配置或暂时不可用。"
    raise HTTPException(
        status_code=502 if upstream_configured else 503,
        detail=detail,
    )


def _cached_ocr_response(cache_key: str) -> dict[str, Any] | None:
    cached = _ocr_response_cache.get(cache_key)
    if cached is None:
        return None
    created_at, payload = cached
    if time.time() - created_at > _OCR_CACHE_TTL_SECONDS:
        _ocr_response_cache.pop(cache_key, None)
        return None
    return copy.deepcopy(payload)


def _store_ocr_response(cache_key: str, payload: dict[str, Any]) -> None:
    if len(_ocr_response_cache) >= _OCR_CACHE_MAX_ENTRIES:
        oldest_key = min(
            _ocr_response_cache,
            key=lambda key: _ocr_response_cache[key][0],
        )
        _ocr_response_cache.pop(oldest_key, None)
    _ocr_response_cache[cache_key] = (time.time(), copy.deepcopy(payload))


def _elapsed_milliseconds(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


def _demo_session_id() -> str:
    value = (request.headers.get("X-Demo-Session") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{8,80}", value):
        return value
    return "anonymous"


def _cached_chat_response(
    cache_key: tuple[str, str],
) -> dict[str, Any] | None:
    cached = _chat_response_cache.get(cache_key)
    if cached is None:
        return None
    created_at, response = cached
    if time.time() - created_at > _CHAT_CACHE_TTL_SECONDS:
        _chat_response_cache.pop(cache_key, None)
        return None
    payload = copy.deepcopy(response)
    payload["cached"] = True
    return payload


def _store_chat_response(
    cache_key: tuple[str, str],
    session_id: str,
    response: dict[str, Any],
) -> None:
    if (
        response.get("intent")
        in {"general", "help", "history", "unknown", "ocr_confirm", "ocr_error"}
        or response.get("history_used")
    ):
        return

    _prune_chat_cache()
    _chat_response_cache[cache_key] = (
        time.time(),
        copy.deepcopy(response),
    )
    session_keys = [
        key for key in _chat_response_cache if key[0] == session_id
    ]
    for stale_key in session_keys[:-_CHAT_CACHE_MAX_PER_SESSION]:
        _chat_response_cache.pop(stale_key, None)


def _prune_chat_cache() -> None:
    now = time.time()
    for key, (created_at, _) in list(_chat_response_cache.items()):
        if now - created_at > _CHAT_CACHE_TTL_SECONDS:
            _chat_response_cache.pop(key, None)

    if len(_chat_response_cache) <= _CHAT_CACHE_MAX_SESSIONS:
        return
    oldest_key = min(
        _chat_response_cache,
        key=lambda item: _chat_response_cache[item][0],
    )
    _chat_response_cache.pop(oldest_key, None)


@application.get("/health")
def service_health():
    return jsonify(health_check())


@application.post("/verify")
def verify_with_json():
    payload = request.get_json(silent=False)
    model = VerifyRequest.model_validate(payload)
    return _json_response(verify_derivative(model, _=None))


@application.post("/verify-query")
def verify_with_query():
    model = VerifyRequest(
        expression=request.args.get("expression"),
        variable=request.args.get("variable", "x"),
        candidate=request.args.get("candidate") or None,
    )
    return _json_response(verify_derivative(model, _=None))


@application.post("/integrate")
def integrate_with_json():
    payload = request.get_json(silent=False)
    model = IntegrateRequest.model_validate(payload)
    return _json_response(calculate_integral(model, _=None))


@application.post("/integrate-query")
def integrate_with_query():
    model = IntegrateRequest(
        expression=request.args.get("expression"),
        variable=request.args.get("variable", "x"),
        lower=request.args.get("lower") or None,
        upper=request.args.get("upper") or None,
        candidate=request.args.get("candidate") or None,
    )
    return _json_response(calculate_integral(model, _=None))


@application.post("/limit")
def limit_with_json():
    payload = request.get_json(silent=False)
    model = LimitRequest.model_validate(payload)
    return _json_response(calculate_limit(model, _=None))


@application.post("/limit-query")
def limit_with_query():
    model = LimitRequest(
        expression=request.args.get("expression"),
        variable=request.args.get("variable", "x"),
        point=request.args.get("point", "0") or "0",
        direction=request.args.get("direction") or None,
        candidate=request.args.get("candidate") or None,
    )
    return _json_response(calculate_limit(model, _=None))


@application.post("/solve")
def solve_with_json():
    payload = request.get_json(silent=False)
    model = SolveRequest.model_validate(payload)
    return _json_response(solve_math(model, _=None))


@application.post("/solve-query")
def solve_with_query():
    raw_inputs = request.args.get("inputs", "")
    try:
        inputs = json.loads(raw_inputs)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="inputs 必须是合法的 JSON 对象") from exc

    if not isinstance(inputs, dict):
        raise HTTPException(status_code=400, detail="inputs 必须是合法的 JSON 对象")

    model = SolveRequest(
        chapter=request.args.get("chapter"),
        topic=request.args.get("topic"),
        inputs=inputs,
        candidate=request.args.get("candidate") or None,
    )
    return _json_response(solve_math(model, _=None))


@application.post("/plot")
def plot_with_json():
    payload = request.get_json(silent=False)
    model = PlotRequest.model_validate(payload)
    return _json_response(calculate_plot(model))


@application.route("/plot-query", methods=["GET", "POST"])
def plot_with_query():
    return _json_response(calculate_plot(_plot_request_from_query()))


@application.route("/plot.svg", methods=["GET", "POST"])
def plot_svg():
    result = calculate_plot(_plot_request_from_query())
    return _svg_response(result.svg)


def _plot_request_from_query() -> PlotRequest:
    return PlotRequest(
        expression=request.args.get("expression"),
        variable=request.args.get("variable", "x"),
        x_min=request.args.get("x_min", -10),
        x_max=request.args.get("x_max", 10),
        y_min=request.args.get("y_min") or None,
        y_max=request.args.get("y_max") or None,
        samples=request.args.get("samples", 600),
        width=request.args.get("width", 720),
        height=request.args.get("height", 420),
    )


def _svg_response(svg: str):
    return Response(
        svg,
        mimetype="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )


def _json_response(value: Any):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    try:
        return jsonify(value)
    except (TypeError, ValueError):
        application.logger.exception("Response JSON serialization failed")
        return Response(
            json.dumps(value, ensure_ascii=False, default=str),
            mimetype="application/json",
        )
