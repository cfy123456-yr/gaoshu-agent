"""Synchronous WSGI entry point used by PythonAnywhere."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from flask import Flask, jsonify, request
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


application = Flask(__name__)


@application.before_request
def enforce_api_access():
    if API_KEY and request.headers.get("X-API-Key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

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
    response.status_code = exc.status_code
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
            "endpoints": [
                "/verify",
                "/verify-query",
                "/integrate",
                "/integrate-query",
                "/limit",
                "/limit-query",
            ],
        }
    )


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
