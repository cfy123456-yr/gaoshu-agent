"""Synchronous WSGI entry point used by PythonAnywhere."""

from __future__ import annotations

import copy
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
from deploy.demo_chat import DemoChatRequest, _normalize_text, build_chat_response
from deploy.demo_coze_ocr import (
    CozeConfigurationError,
    CozeUpstreamError,
    coze_ocr_configured,
    transcribe_question_image,
)
from deploy.demo_vision import (
    MAX_IMAGE_BYTES,
    SUPPORTED_IMAGE_TYPES,
    image_matches_type,
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
                "/demo/api/chat",
                "/demo/api/ocr",
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
    payload["ocr"] = {
        "provider": "coze",
        "configured": coze_ocr_configured(),
        "fallback": "windows" if windows_ocr_available() else "",
    }
    return jsonify(payload)


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
    normalized = _normalize_text(model.message)
    cache_key = (session_id, normalized)
    cached = _cached_chat_response(cache_key)
    if cached is not None:
        return jsonify(cached)

    response = build_chat_response(model.message, model.history)
    _store_chat_response(cache_key, session_id, response)
    return jsonify(response)


@application.post("/demo/api/ocr")
def demo_ocr():
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

    provider = "coze"
    warning = ""
    try:
        text = transcribe_question_image(image_data, mime_type)
    except (CozeConfigurationError, CozeUpstreamError) as coze_error:
        try:
            text = transcribe_windows_question_image(image_data, mime_type)
        except WindowsOcrUnavailable as fallback_error:
            status_code = (
                503
                if isinstance(coze_error, CozeConfigurationError)
                else 502
            )
            raise HTTPException(
                status_code=status_code,
                detail=str(coze_error),
            ) from fallback_error
        except WindowsOcrError as fallback_error:
            status_code = (
                503
                if isinstance(coze_error, CozeConfigurationError)
                else 502
            )
            raise HTTPException(
                status_code=status_code,
                detail=f"{coze_error}；本机离线识别也未成功：{fallback_error}",
            ) from fallback_error

        provider = "windows"
        warning = "已使用本机离线 OCR，公式可能不完整，请核对后再发送。"

    return jsonify(
        {
            "text": text,
            "provider": provider,
            "warning": warning,
        }
    )


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
        response.get("intent") in {"general", "help", "history", "unknown"}
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
    return jsonify(value)
