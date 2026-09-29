#!/usr/bin/env python3
"""Run reproducible randomized regression checks against a deployment."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from fractions import Fraction
from pathlib import Path
from typing import Any

import sympy

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_deployment import VerificationError, expect, request_json


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_SEED = 20260928
EXPECTED_VERSION = "0.6.7"
X = sympy.Symbol("x", real=True)
N = sympy.Symbol("n", integer=True, positive=True)
Y = sympy.Symbol("y", real=True)


def parse_expression(value: Any) -> sympy.Expr:
    return sympy.sympify(
        str(value).strip().replace("^", "**"),
        locals={"x": X, "y": Y, "n": N},
    )


def assert_equivalent(actual: Any, expected: sympy.Expr) -> None:
    parsed = parse_expression(actual)
    difference = sympy.simplify(parsed - expected)
    expect(
        difference == 0,
        f"result mismatch: expected {expected}, got {actual}",
    )


def random_polynomial(rng: random.Random) -> sympy.Expr:
    degree = rng.randint(1, 4)
    coefficients = [rng.randint(-5, 5) for _ in range(degree)]
    leading = rng.choice((-1, 1)) * rng.randint(1, 5)
    coefficients.append(leading)
    return sum(
        coefficient * X**power
        for power, coefficient in enumerate(coefficients)
        if coefficient
    )


def solve_request(
    base_url: str,
    api_key: str | None,
    timeout: float,
    *,
    chapter: str,
    topic: str,
    inputs: dict[str, Any],
    candidate: str | None = None,
) -> dict[str, Any]:
    params = {
        "chapter": chapter,
        "topic": topic,
        "inputs": json.dumps(inputs, separators=(",", ":")),
    }
    if candidate is not None:
        params["candidate"] = candidate
    return request_json(
        base_url,
        "/solve-query",
        params=params,
        method="POST",
        api_key=api_key,
        timeout=timeout,
    )


def chat_request(
    base_url: str,
    timeout: float,
    message: str,
) -> dict[str, Any]:
    return request_json(
        base_url,
        "/demo/api/chat",
        method="POST",
        json_body={"message": message, "source": "text"},
        timeout=timeout,
    )


def verify_polynomial_case(
    base_url: str,
    api_key: str | None,
    timeout: float,
    rng: random.Random,
    case_index: int,
) -> None:
    expression = random_polynomial(rng)
    expression_text = str(expression)
    label = f"polynomial-{case_index}"

    derivative = sympy.diff(expression, X)
    derivative_payload = solve_request(
        base_url,
        api_key,
        timeout,
        chapter="derivatives",
        topic="derivative",
        inputs={"expression": expression_text, "variable": "x"},
        candidate=str(derivative),
    )
    expect(
        derivative_payload.get("is_correct") is True,
        f"{label} derivative candidate was not accepted: {derivative_payload}",
    )
    assert_equivalent(derivative_payload.get("result"), derivative)

    wrong_payload = solve_request(
        base_url,
        api_key,
        timeout,
        chapter="derivatives",
        topic="derivative",
        inputs={"expression": expression_text, "variable": "x"},
        candidate=f"({derivative}) + 1",
    )
    expect(
        wrong_payload.get("is_correct") is False,
        f"{label} wrong derivative was accepted: {wrong_payload}",
    )

    antiderivative = sympy.integrate(expression, X)
    integral_payload = solve_request(
        base_url,
        api_key,
        timeout,
        chapter="integrals",
        topic="indefinite",
        inputs={"expression": expression_text, "variable": "x"},
        candidate=str(antiderivative),
    )
    expect(
        integral_payload.get("is_correct") is True,
        f"{label} antiderivative candidate was not accepted: {integral_payload}",
    )
    actual_integral = parse_expression(integral_payload.get("result"))
    expect(
        sympy.simplify(sympy.diff(actual_integral, X) - expression) == 0,
        f"{label} antiderivative does not differentiate back: {integral_payload}",
    )

    lower = rng.randint(-3, 2)
    upper = lower + rng.randint(1, 4)
    definite_value = sympy.integrate(expression, (X, lower, upper))
    definite_payload = solve_request(
        base_url,
        api_key,
        timeout,
        chapter="integrals",
        topic="definite",
        inputs={
            "expression": expression_text,
            "variable": "x",
            "lower": str(lower),
            "upper": str(upper),
        },
        candidate=str(definite_value),
    )
    expect(
        definite_payload.get("is_correct") is True,
        f"{label} definite integral candidate was not accepted: {definite_payload}",
    )
    assert_equivalent(definite_payload.get("result"), definite_value)

    point = rng.randint(-3, 3)
    limit_value = sympy.limit(expression, X, point)
    limit_payload = solve_request(
        base_url,
        api_key,
        timeout,
        chapter="limits",
        topic="limit",
        inputs={
            "expression": expression_text,
            "variable": "x",
            "point": str(point),
        },
        candidate=str(limit_value),
    )
    expect(
        limit_payload.get("is_correct") is True,
        f"{label} limit candidate was not accepted: {limit_payload}",
    )
    assert_equivalent(limit_payload.get("result"), limit_value)


def verify_interval_extrema_case(
    base_url: str,
    timeout: float,
    rng: random.Random,
    case_index: int,
) -> None:
    a = rng.choice((-5, -4, -3, -2, -1, 1, 2, 3, 4, 5))
    b = rng.randint(-8, 8)
    c = rng.randint(-8, 8)
    lower = rng.randint(-6, 1)
    upper = lower + rng.randint(1, 6)
    expression = a * X**2 + b * X + c
    vertex = sympy.Rational(-b, 2 * a)
    candidates = [
        expression.subs(X, lower),
        expression.subs(X, upper),
    ]
    if lower <= vertex <= upper:
        candidates.append(expression.subs(X, vertex))

    for kind, label, expected in (
        ("max", "\u6700\u5927\u503c", sympy.simplify(max(candidates))),
        ("min", "\u6700\u5c0f\u503c", sympy.simplify(min(candidates))),
    ):
        question = (
            f"\u51fd\u6570 f(x)={expression} "
            f"\u5728\u533a\u95f4 [{lower},{upper}] "
            f"\u4e0a\u7684{label}"
        )
        payload = chat_request(base_url, timeout, question)
        expect(
            payload.get("intent") == "solve",
            f"interval-{case_index}/{kind} intent mismatch: {payload}",
        )
        calculation = payload.get("calculation") or {}
        expect(
            calculation.get("kind") == label,
            f"interval-{case_index}/{kind} kind mismatch: {payload}",
        )
        assert_equivalent(calculation.get("result"), expected)


def verify_arithmetic_case(
    base_url: str,
    timeout: float,
    rng: random.Random,
    case_index: int,
) -> None:
    left = Fraction(rng.randint(-12, 12), rng.randint(1, 12))
    right = Fraction(rng.randint(-12, 12), rng.randint(1, 12))
    operator = rng.choice(("+", "-", "*", "/"))
    if operator == "+":
        expected = left + right
    elif operator == "-":
        expected = left - right
    elif operator == "*":
        expected = left * right
    else:
        expected = left / right

    message = (
        f"({left.numerator}/{left.denominator}){operator}"
        f"({right.numerator}/{right.denominator})"
    )
    payload = chat_request(base_url, timeout, message)
    expect(
        payload.get("intent") == "arithmetic",
        f"arithmetic-{case_index} intent mismatch: {payload}",
    )
    assert_equivalent(
        (payload.get("calculation") or {}).get("result"),
        sympy.Rational(expected.numerator, expected.denominator),
    )


def verify_chapter_cases(
    base_url: str,
    api_key: str | None,
    timeout: float,
    rng: random.Random,
) -> None:
    expression = random_polynomial(rng)
    order = rng.randint(2, 4)
    expected_derivative = sympy.diff(expression, X, order)
    payload = solve_request(
        base_url,
        api_key,
        timeout,
        chapter="derivatives",
        topic="higher_derivative",
        inputs={
            "expression": str(expression),
            "variable": "x",
            "order": order,
        },
        candidate=str(expected_derivative),
    )
    expect(
        payload.get("is_correct") is True,
        f"higher-derivative chapter case failed: {payload}",
    )
    assert_equivalent(payload.get("result"), expected_derivative)

    a = rng.randint(-4, 4) or 1
    b = rng.randint(-4, 4)
    c = rng.randint(-4, 4)
    lower_x = rng.randint(-3, 1)
    upper_x = lower_x + rng.randint(1, 4)
    lower_y = rng.randint(-3, 1)
    upper_y = lower_y + rng.randint(1, 4)
    double_expression = a * X + b * Y + c
    expected_double = sympy.integrate(
        sympy.integrate(
            double_expression,
            (X, lower_x, upper_x),
        ),
        (Y, lower_y, upper_y),
    )
    payload = solve_request(
        base_url,
        api_key,
        timeout,
        chapter="multiple_integrals",
        topic="double",
        inputs={
            "expression": str(double_expression),
            "variables": ["x", "y"],
            "lower_x": str(lower_x),
            "upper_x": str(upper_x),
            "lower_y": str(lower_y),
            "upper_y": str(upper_y),
        },
        candidate=str(expected_double),
    )
    expect(
        payload.get("is_correct") is True,
        f"double-integral chapter case failed: {payload}",
    )
    assert_equivalent(payload.get("result"), expected_double)

    exponent = rng.choice((2, 4))
    expected_sum = sympy.summation(N ** (-exponent), (N, 1, sympy.oo))
    payload = solve_request(
        base_url,
        api_key,
        timeout,
        chapter="series",
        topic="sum",
        inputs={
            "expression": f"1/n^{exponent}",
            "variable": "n",
            "lower": 1,
            "upper": "oo",
        },
        candidate=str(expected_sum),
    )
    expect(
        payload.get("is_correct") is True,
        f"series-sum chapter case failed: {payload}",
    )
    assert_equivalent(payload.get("result"), expected_sum)


def verify_random_regression(
    base_url: str,
    api_key: str | None,
    *,
    seed: int,
    cases: int,
    delay: float,
    skip_version_check: bool,
    timeout: float,
) -> None:
    print(f"[1/5] Health: {base_url}/health")
    health = request_json(base_url, "/health", timeout=timeout)
    expect(health.get("status") == "ok", f"Health check failed: {health}")
    if not skip_version_check:
        expect(
            health.get("version") == EXPECTED_VERSION,
            (
                "Version mismatch: "
                f"expected {EXPECTED_VERSION}, got {health.get('version')}"
            ),
        )

    if health.get("api_key_enabled") and not api_key:
        raise VerificationError(
            "Deployment requires MATH_API_KEY; pass --api-key or set it in env"
        )

    rng = random.Random(seed)
    throttle = max(0.0, delay)

    print(f"[2/5] Random polynomial calculus: {cases} cases")
    for case_index in range(1, cases + 1):
        verify_polynomial_case(
            base_url,
            api_key,
            timeout,
            rng,
            case_index,
        )
        print(f"      polynomial-{case_index}: OK")
        time.sleep(throttle)

    print("[3/5] Random quadratic interval extrema: 4 cases")
    for case_index in range(1, 5):
        verify_interval_extrema_case(base_url, timeout, rng, case_index)
        print(f"      interval-{case_index}: OK")
        time.sleep(throttle)

    print("[4/5] Random rational arithmetic: 4 cases")
    for case_index in range(1, 5):
        verify_arithmetic_case(base_url, timeout, rng, case_index)
        print(f"      arithmetic-{case_index}: OK")
        time.sleep(throttle)

    print("[5/5] Randomized chapter topics: higher derivative, double integral, series")
    verify_chapter_cases(base_url, api_key, timeout, rng)
    print("      chapter topics: OK")

    print("\nRandom regression passed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run randomized public regression checks"
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("TEST_BASE_URL", DEFAULT_BASE_URL),
        help=f"Deployment base URL (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("MATH_API_KEY") or None,
        help="Deployment API key, when enabled",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--cases",
        type=int,
        default=4,
        help="Random polynomial calculus cases (default: 4)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.1,
        help="Delay between requests in seconds (default: 1.1)",
    )
    parser.add_argument(
        "--skip-version-check",
        action="store_true",
        help="Skip the expected service version check",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds (default: 30)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.cases < 1:
        print("--cases must be at least 1")
        return 2
    try:
        verify_random_regression(
            args.base_url,
            args.api_key,
            seed=args.seed,
            cases=args.cases,
            delay=args.delay,
            skip_version_check=args.skip_version_check,
            timeout=args.timeout,
        )
    except VerificationError as exc:
        print(f"\nRandom regression failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
