"""Synchronous WSGI entry point used by PythonAnywhere."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from flask import Flask, jsonify, render_template, request
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException as WerkzeugHTTPException

from app.main import (
    API_KEY,
    IntegrateRequest,
    LimitRequest,
    VerifyRequest,
    calculate_integral,
    calculate_limit,
    health_check,
    rate_limiter,
    verify_derivative,
)
from deploy.demo_chat import DemoChatRequest, build_chat_response


application = Flask(__name__)


def is_public_demo_request() -> bool:
    return request.path == "/demo" or request.path.startswith("/demo/")


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
                "/demo/api/chat",
                "/verify",
                "/verify-query",
                "/integrate",
                "/integrate-query",
                "/limit",
                "/limit-query",
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


@application.post("/demo/api/chat")
def demo_chat():
    payload = request.get_json(silent=False)
    model = DemoChatRequest.model_validate(payload)
    return jsonify(build_chat_response(model.message))


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
        candidate=request.args.get("candidate"),
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
        lower=request.args.get("lower"),
        upper=request.args.get("upper"),
        candidate=request.args.get("candidate"),
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
        point=request.args.get("point", "0"),
        direction=request.args.get("direction"),
        candidate=request.args.get("candidate"),
    )
    return _json_response(calculate_limit(model, _=None))


def _json_response(value: Any):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return jsonify(value)
