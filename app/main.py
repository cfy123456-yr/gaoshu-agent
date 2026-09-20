import hashlib
import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
from typing import Any

import sympy
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sympy import Limit, diff, integrate, latex, simplify
from sympy.parsing.sympy_parser import (
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from app.chapter_solvers import SUPPORTED_TOPICS, SolveError, solve_chapter
from app.plotting import render_function_svg


load_dotenv()


def read_int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def read_float_env(name: str, default: float, minimum: float = 0.1) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


MAX_EXPRESSION_LENGTH = read_int_env("MAX_EXPRESSION_LENGTH", 300)
MAX_SYMBOL_LENGTH = read_int_env("MAX_SYMBOL_LENGTH", 32)
RATE_LIMIT_PER_MINUTE = read_int_env("RATE_LIMIT_PER_MINUTE", 60, minimum=0)
CALCULATION_TIMEOUT_SECONDS = read_float_env("CALCULATION_TIMEOUT_SECONDS", 10.0)
CALCULATION_WORKERS = read_int_env("CALCULATION_WORKERS", 4)
LOG_ENABLED = os.getenv("LOG_ENABLED", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()
LOG_FILE = os.getenv(
    "LOG_FILE",
    str(Path(__file__).resolve().parents[1] / "logs" / "math-service.jsonl"),
)
LOG_MAX_BYTES = read_int_env("LOG_MAX_BYTES", 5 * 1024 * 1024)
LOG_BACKUP_COUNT = read_int_env("LOG_BACKUP_COUNT", 3, minimum=0)
API_KEY = os.getenv("MATH_API_KEY", "").strip()
SERVICE_VERSION = "0.5.0"
SERVICE_STARTED_AT = datetime.now(timezone.utc)
SERVICE_STARTED_MONOTONIC = time.monotonic()


class JsonLineFormatter(logging.Formatter):
    LOG_FIELDS = (
        "event",
        "method",
        "endpoint",
        "status_code",
        "duration_ms",
        "client",
        "error_type",
        "calculation",
        "timeout_seconds",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
        }
        for field_name in self.LOG_FIELDS:
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = value
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


logger = logging.getLogger("gaoshu.math")


def configure_logging() -> bool:
    if not LOG_ENABLED:
        return False

    try:
        log_path = Path(LOG_FILE).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(JsonLineFormatter())
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
        logger.propagate = False
        return True
    except Exception:
        logger.handlers.clear()
        logger.addHandler(logging.StreamHandler())
        logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
        logger.propagate = False
        return False


PERSISTENT_LOGGING_ENABLED = configure_logging()

app = FastAPI(title="知微数学验证服务", version=SERVICE_VERSION)


class VerifyRequest(BaseModel):
    expression: str = Field(min_length=1, max_length=MAX_EXPRESSION_LENGTH)
    variable: str = Field(default="x", min_length=1, max_length=MAX_SYMBOL_LENGTH)
    candidate: str | None = Field(default=None, max_length=MAX_EXPRESSION_LENGTH)


class VerifyResponse(BaseModel):
    expression: str
    variable: str
    derivative: str
    derivative_latex: str
    candidate: str | None
    is_correct: bool | None


class IntegrateRequest(BaseModel):
    expression: str = Field(min_length=1, max_length=MAX_EXPRESSION_LENGTH)
    variable: str = Field(default="x", min_length=1, max_length=MAX_SYMBOL_LENGTH)
    lower: str | None = Field(default=None, max_length=MAX_EXPRESSION_LENGTH)
    upper: str | None = Field(default=None, max_length=MAX_EXPRESSION_LENGTH)
    candidate: str | None = Field(default=None, max_length=MAX_EXPRESSION_LENGTH)


class IntegrateResponse(BaseModel):
    expression: str
    variable: str
    integral: str
    integral_latex: str
    candidate: str | None
    is_correct: bool | None


class LimitRequest(BaseModel):
    expression: str = Field(min_length=1, max_length=MAX_EXPRESSION_LENGTH)
    variable: str = Field(default="x", min_length=1, max_length=MAX_SYMBOL_LENGTH)
    point: str = Field(default="0", min_length=1, max_length=MAX_EXPRESSION_LENGTH)
    direction: str | None = Field(default=None, max_length=1)
    candidate: str | None = Field(default=None, max_length=MAX_EXPRESSION_LENGTH)


class LimitResponse(BaseModel):
    expression: str
    variable: str
    point: str
    direction: str | None
    limit: str
    limit_latex: str
    candidate: str | None
    is_correct: bool | None


class SolveRequest(BaseModel):
    chapter: str = Field(min_length=1, max_length=64)
    topic: str = Field(min_length=1, max_length=64)
    inputs: dict[str, Any] = Field(default_factory=dict, max_length=32)
    candidate: str | None = Field(default=None, max_length=MAX_EXPRESSION_LENGTH)


class SolveResponse(BaseModel):
    chapter: str
    topic: str
    method: str
    result: str
    latex: str
    candidate: str | None
    is_correct: bool | None
    notes: list[str]


class PlotRequest(BaseModel):
    expression: str = Field(min_length=1, max_length=MAX_EXPRESSION_LENGTH)
    variable: str = Field(default="x", min_length=1, max_length=MAX_SYMBOL_LENGTH)
    x_min: float = Field(default=-10, ge=-1_000_000, le=1_000_000)
    x_max: float = Field(default=10, ge=-1_000_000, le=1_000_000)
    y_min: float | None = Field(default=None, ge=-1_000_000_000, le=1_000_000_000)
    y_max: float | None = Field(default=None, ge=-1_000_000_000, le=1_000_000_000)
    samples: int = Field(default=600, ge=80, le=1200)
    width: int = Field(default=720, ge=320, le=1200)
    height: int = Field(default=420, ge=240, le=800)


class PlotResponse(BaseModel):
    expression: str
    variable: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    svg: str


SAFE_FUNCTIONS = {
    name: getattr(sympy, name)
    for name in (
        "sin",
        "cos",
        "tan",
        "cot",
        "sec",
        "csc",
        "asin",
        "acos",
        "atan",
        "acot",
        "asec",
        "acsc",
        "sinh",
        "cosh",
        "tanh",
        "asinh",
        "acosh",
        "atanh",
        "exp",
        "factorial",
        "log",
        "sqrt",
        "Abs",
    )
    if hasattr(sympy, name)
}
SAFE_FUNCTIONS["abs"] = sympy.Abs
SAFE_FUNCTIONS["ln"] = sympy.log

SAFE_LOCAL_DICT = {
    **SAFE_FUNCTIONS,
    "pi": sympy.pi,
    "PI": sympy.pi,
    "e": sympy.E,
    "E": sympy.E,
    "oo": sympy.oo,
    "Symbol": sympy.Symbol,
    "Integer": sympy.Integer,
    "Float": sympy.Float,
    "Rational": sympy.Rational,
}
ALLOWED_EXPRESSION_CHARS = frozenset(
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_+-*/^().,! "
)
SYMBOL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def validate_expression_text(value: str, field_name: str = "expression") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > MAX_EXPRESSION_LENGTH:
        raise ValueError(f"{field_name} is too long")
    if "__" in value:
        raise ValueError(f"{field_name} contains an unsupported identifier")

    invalid_chars = sorted(set(value) - ALLOWED_EXPRESSION_CHARS)
    if invalid_chars:
        raise ValueError(f"{field_name} contains unsupported characters")

    for index, char in enumerate(value):
        if char != ".":
            continue
        previous_is_digit = index > 0 and value[index - 1].isdigit()
        next_is_digit = index + 1 < len(value) and value[index + 1].isdigit()
        if not (previous_is_digit and next_is_digit):
            raise ValueError(f"{field_name} contains an unsupported decimal point")

    return value.strip()


def parse_math_expression(value: str):
    normalized = validate_expression_text(value)
    normalized = re.sub(
        r"([A-Za-z][A-Za-z0-9_]*|\d+)!",
        r"factorial(\1)",
        normalized,
    ).replace("^", "**")
    transformations = standard_transformations + (implicit_multiplication_application,)
    return parse_expr(
        normalized,
        transformations=transformations,
        local_dict=SAFE_LOCAL_DICT,
        global_dict={"__builtins__": {}},
    )


def parse_symbol(value: str):
    if not isinstance(value, str):
        raise ValueError("variable must be a string")
    symbol_name = value.strip()
    if len(symbol_name) > MAX_SYMBOL_LENGTH or not SYMBOL_PATTERN.fullmatch(symbol_name):
        raise ValueError("variable is invalid")
    if symbol_name in SAFE_FUNCTIONS or symbol_name in {"pi", "e", "oo"}:
        raise ValueError("variable conflicts with a reserved name")
    return sympy.Symbol(symbol_name)


def expressions_equal(left, right) -> bool:
    if left == right:
        return True
    return simplify(left - right) == 0


def build_plot_response(request: PlotRequest) -> PlotResponse:
    variable = parse_symbol(request.variable)
    expression = parse_math_expression(request.expression)
    return PlotResponse(
        **render_function_svg(
            expression,
            variable,
            x_min=request.x_min,
            x_max=request.x_max,
            y_min=request.y_min,
            y_max=request.y_max,
            samples=request.samples,
            width=request.width,
            height=request.height,
        )
    )


calculation_executor = ThreadPoolExecutor(
    max_workers=CALCULATION_WORKERS,
    thread_name_prefix="math-calc",
)


def run_calculation(callback, calculation_name: str):
    started = time.perf_counter()
    future = calculation_executor.submit(callback)
    try:
        result = future.result(timeout=CALCULATION_TIMEOUT_SECONDS)
    except FutureTimeoutError as exc:
        future.cancel()
        logger.warning(
            "calculation_timeout",
            extra={
                "event": "calculation_timeout",
                "calculation": calculation_name,
                "timeout_seconds": CALCULATION_TIMEOUT_SECONDS,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        raise HTTPException(
            status_code=504,
            detail="Calculation timed out",
            headers={"X-Calculation-Timeout": str(CALCULATION_TIMEOUT_SECONDS)},
        ) from exc

    logger.info(
        "calculation_completed",
        extra={
            "event": "calculation_completed",
            "calculation": calculation_name,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return result


def client_fingerprint(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    client_key = forwarded_for.split(",")[0].strip()
    if not client_key:
        client_key = request.client.host if request.client else "unknown"
    return hashlib.sha256(client_key.encode("utf-8")).hexdigest()[:12]


def classify_error_type(status_code: int) -> str | None:
    if status_code == 400:
        return "invalid_math_request"
    if status_code == 401:
        return "unauthorized"
    if status_code == 422:
        return "validation_error"
    if status_code == 429:
        return "rate_limited"
    if status_code == 504:
        return "calculation_timeout"
    if status_code >= 500:
        return "internal_error"
    return None


@app.middleware("http")
async def log_request(request: Request, call_next):
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except HTTPException as exc:
        status_code = exc.status_code
        raise
    finally:
        logger.info(
            "request_completed",
            extra={
                "event": "request_completed",
                "method": request.method,
                "endpoint": request.url.path,
                "status_code": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "client": client_fingerprint(request),
                "error_type": classify_error_type(status_code),
            },
        )


class InMemoryRateLimiter:
    def __init__(self, limit_per_minute: int):
        self.limit_per_minute = limit_per_minute
        self.requests: dict[str, deque[float]] = defaultdict(deque)
        self.lock = Lock()

    def check(self, client_key: str) -> None:
        if self.limit_per_minute <= 0:
            return

        now = time.monotonic()
        cutoff = now - 60
        with self.lock:
            bucket = self.requests[client_key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit_per_minute:
                retry_after = max(1, int(60 - (now - bucket[0])) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests",
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)


rate_limiter = InMemoryRateLimiter(RATE_LIMIT_PER_MINUTE)


def enforce_api_access(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    forwarded_for = request.headers.get("x-forwarded-for", "")
    client_key = forwarded_for.split(",")[0].strip()
    if not client_key:
        client_key = request.client.host if request.client else "unknown"
    rate_limiter.check(client_key)


def parse_direction(value: str | None) -> str | None:
    if value is None or not value.strip() or value.strip() == "+-":
        return None

    direction = value.strip()
    if direction not in {"+", "-"}:
        raise ValueError("方向只能是 '+'、'-' 或空")

    return direction


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "math-tool",
        "version": SERVICE_VERSION,
        "started_at": SERVICE_STARTED_AT.isoformat(),
        "uptime_seconds": round(time.monotonic() - SERVICE_STARTED_MONOTONIC, 2),
        "calculation_timeout_seconds": CALCULATION_TIMEOUT_SECONDS,
        "calculation_workers": CALCULATION_WORKERS,
        "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
        "api_key_enabled": bool(API_KEY),
        "persistent_logging_enabled": PERSISTENT_LOGGING_ENABLED,
        "limits": {
            "max_expression_length": MAX_EXPRESSION_LENGTH,
            "max_symbol_length": MAX_SYMBOL_LENGTH,
        },
        "solve_topics": {
            chapter: sorted(topics)
            for chapter, topics in SUPPORTED_TOPICS.items()
        },
    }


@app.post("/verify", response_model=VerifyResponse)
def verify_derivative(
    request: VerifyRequest,
    _: None = Depends(enforce_api_access),
):
    def calculate():
        variable = parse_symbol(request.variable)
        expression = parse_math_expression(request.expression)
        derivative = diff(expression, variable)
        candidate_text = request.candidate.strip() if request.candidate else None
        candidate = parse_math_expression(candidate_text) if candidate_text else None
        is_correct = expressions_equal(derivative, candidate) if candidate is not None else None

        return VerifyResponse(
            expression=str(expression),
            variable=str(variable),
            derivative=str(derivative),
            derivative_latex=latex(derivative),
            candidate=str(candidate) if candidate is not None else None,
            is_correct=is_correct,
        )

    try:
        return run_calculation(calculate, "verify")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"表达式无法解析: {exc}") from exc


@app.post("/verify-query", response_model=VerifyResponse)
def verify_derivative_query(
    expression: str = Query(min_length=1),
    variable: str = Query(default="x", min_length=1),
    candidate: str | None = Query(default=None),
    _: None = Depends(enforce_api_access),
):
    return verify_derivative(
        VerifyRequest(
            expression=expression,
            variable=variable,
            candidate=candidate,
        )
    )


@app.post("/integrate", response_model=IntegrateResponse)
def calculate_integral(
    request: IntegrateRequest,
    _: None = Depends(enforce_api_access),
):
    def calculate():
        variable = parse_symbol(request.variable)
        expression = parse_math_expression(request.expression)
        lower_value = request.lower.strip() if request.lower and request.lower.strip() else None
        upper_value = request.upper.strip() if request.upper and request.upper.strip() else None
        candidate_value = (
            request.candidate.strip()
            if request.candidate and request.candidate.strip()
            else None
        )

        if lower_value is not None and upper_value is not None:
            lower = parse_math_expression(lower_value)
            upper = parse_math_expression(upper_value)
            integral = integrate(expression, (variable, lower, upper))
        else:
            integral = integrate(expression, variable)

        candidate = parse_math_expression(candidate_value) if candidate_value else None
        if candidate is None:
            is_correct = None
        elif lower_value is not None and upper_value is not None:
            is_correct = expressions_equal(integral, candidate)
        else:
            is_correct = expressions_equal(
                diff(integral, variable),
                diff(candidate, variable),
            )

        return IntegrateResponse(
            expression=str(expression),
            variable=str(variable),
            integral=str(integral),
            integral_latex=latex(integral),
            candidate=str(candidate) if candidate is not None else None,
            is_correct=is_correct,
        )

    try:
        return run_calculation(calculate, "integrate")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"表达式无法解析: {exc}") from exc


@app.post("/integrate-query", response_model=IntegrateResponse)
def calculate_integral_query(
    expression: str = Query(min_length=1),
    variable: str = Query(default="x", min_length=1),
    lower: str | None = Query(default=None),
    upper: str | None = Query(default=None),
    candidate: str | None = Query(default=None),
    _: None = Depends(enforce_api_access),
):
    return calculate_integral(
        IntegrateRequest(
            expression=expression,
            variable=variable,
            lower=lower,
            upper=upper,
            candidate=candidate,
        )
    )


@app.post("/limit", response_model=LimitResponse)
def calculate_limit(
    request: LimitRequest,
    _: None = Depends(enforce_api_access),
):
    def calculate():
        variable = parse_symbol(request.variable)
        expression = parse_math_expression(request.expression)
        point = parse_math_expression(request.point)
        direction = parse_direction(request.direction)
        candidate_text = request.candidate.strip() if request.candidate else None
        candidate = parse_math_expression(candidate_text) if candidate_text else None

        if direction is None:
            limit_expression = Limit(expression, variable, point)
        else:
            limit_expression = Limit(expression, variable, point, direction)
        limit_value = limit_expression.doit()
        if getattr(limit_value, "has", lambda *_: False)(Limit):
            raise ValueError("极限无法确定，可能需要补充条件或改写表达式")

        is_correct = expressions_equal(limit_value, candidate) if candidate is not None else None

        return LimitResponse(
            expression=str(expression),
            variable=str(variable),
            point=str(point),
            direction=direction,
            limit=str(limit_value),
            limit_latex=latex(limit_value),
            candidate=str(candidate) if candidate is not None else None,
            is_correct=is_correct,
        )

    try:
        return run_calculation(calculate, "limit")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"表达式无法解析: {exc}") from exc


@app.post("/limit-query", response_model=LimitResponse)
def calculate_limit_query(
    expression: str = Query(min_length=1),
    variable: str = Query(default="x", min_length=1),
    point: str = Query(default="0", min_length=1),
    direction: str | None = Query(default=None),
    candidate: str | None = Query(default=None),
    _: None = Depends(enforce_api_access),
):
    return calculate_limit(
        LimitRequest(
            expression=expression,
            variable=variable,
            point=point,
            direction=direction,
            candidate=candidate,
        )
    )


@app.post("/solve", response_model=SolveResponse)
def solve_math(
    request: SolveRequest,
    _: None = Depends(enforce_api_access),
):
    def calculate():
        try:
            return SolveResponse(
                **solve_chapter(
                    chapter=request.chapter,
                    topic=request.topic,
                    inputs=request.inputs,
                    candidate=request.candidate,
                )
            )
        except SolveError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return run_calculation(calculate, "solve")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"solve 请求无法完成：{exc}") from exc


@app.post("/solve-query", response_model=SolveResponse)
def solve_math_query(
    chapter: str = Query(min_length=1, max_length=64),
    topic: str = Query(min_length=1, max_length=64),
    inputs: str = Query(min_length=2, max_length=4096),
    candidate: str | None = Query(default=None, max_length=MAX_EXPRESSION_LENGTH),
    _: None = Depends(enforce_api_access),
):
    try:
        parsed_inputs = json.loads(inputs)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="inputs 必须是合法的 JSON 对象") from exc

    if not isinstance(parsed_inputs, dict):
        raise HTTPException(status_code=400, detail="inputs 必须是合法的 JSON 对象")

    return solve_math(
        SolveRequest(
            chapter=chapter,
            topic=topic,
            inputs=parsed_inputs,
            candidate=candidate or None,
        ),
        _=None,
    )


def calculate_plot(request: PlotRequest) -> PlotResponse:
    try:
        return run_calculation(
            lambda: build_plot_response(request),
            "plot",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"函数图像无法生成：{exc}") from exc


@app.post("/plot", response_model=PlotResponse)
def plot_function(
    request: PlotRequest,
    _: None = Depends(enforce_api_access),
):
    return calculate_plot(request)


@app.api_route("/plot-query", methods=["GET", "POST"], response_model=PlotResponse)
def plot_function_query(
    expression: str = Query(min_length=1, max_length=MAX_EXPRESSION_LENGTH),
    variable: str = Query(default="x", min_length=1, max_length=MAX_SYMBOL_LENGTH),
    x_min: float = Query(default=-10, ge=-1_000_000, le=1_000_000),
    x_max: float = Query(default=10, ge=-1_000_000, le=1_000_000),
    y_min: float | None = Query(default=None, ge=-1_000_000_000, le=1_000_000_000),
    y_max: float | None = Query(default=None, ge=-1_000_000_000, le=1_000_000_000),
    samples: int = Query(default=600, ge=80, le=1200),
    width: int = Query(default=720, ge=320, le=1200),
    height: int = Query(default=420, ge=240, le=800),
    _: None = Depends(enforce_api_access),
):
    return calculate_plot(
        PlotRequest(
            expression=expression,
            variable=variable,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            samples=samples,
            width=width,
            height=height,
        )
    )


@app.get("/plot.svg", response_class=Response)
def plot_function_svg(
    expression: str = Query(min_length=1, max_length=MAX_EXPRESSION_LENGTH),
    variable: str = Query(default="x", min_length=1, max_length=MAX_SYMBOL_LENGTH),
    x_min: float = Query(default=-10, ge=-1_000_000, le=1_000_000),
    x_max: float = Query(default=10, ge=-1_000_000, le=1_000_000),
    y_min: float | None = Query(default=None, ge=-1_000_000_000, le=1_000_000_000),
    y_max: float | None = Query(default=None, ge=-1_000_000_000, le=1_000_000_000),
    samples: int = Query(default=600, ge=80, le=1200),
    width: int = Query(default=720, ge=320, le=1200),
    height: int = Query(default=420, ge=240, le=800),
    _: None = Depends(enforce_api_access),
):
    result = plot_function_query(
        expression=expression,
        variable=variable,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        samples=samples,
        width=width,
        height=height,
        _=None,
    )
    return Response(
        content=result.svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )
