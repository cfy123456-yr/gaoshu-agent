#!/usr/bin/env python3
"""Verify multi-chapter /solve-query results on a deployment."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_deployment import VerificationError, expect, request_json


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
EXPECTED_VERSION = "0.4.1"

SOLVE_CASES = (
    {
        "name": "higher_derivative",
        "chapter": "derivatives",
        "topic": "higher_derivative",
        "inputs": {"expression": "x^3", "variable": "x", "order": 2},
        "candidate": "6*x",
        "expected_result": "6*x",
        "expected_is_correct": True,
    },
    {
        "name": "series_sum",
        "chapter": "series",
        "topic": "sum",
        "inputs": {
            "expression": "1/n^2",
            "variable": "n",
            "lower": 1,
            "upper": "oo",
        },
        "expected_result": "pi**2/6",
    },
    {
        "name": "series_convergence",
        "chapter": "series",
        "topic": "convergence",
        "inputs": {"expression": "1/n^2", "variable": "n"},
        "expected_result": "\u6536\u655b",
    },
    {
        "name": "double_integral",
        "chapter": "multiple_integrals",
        "topic": "double",
        "inputs": {
            "expression": "x*y",
            "variables": ["x", "y"],
            "lower_x": "0",
            "upper_x": "1",
            "lower_y": "0",
            "upper_y": "1",
        },
        "expected_result": "1/4",
    },
    {
        "name": "differential_equation",
        "chapter": "differential_equations",
        "topic": "dsolve",
        "inputs": {
            "equation": "y' - y",
            "variable": "x",
            "function": "y",
        },
        "expected_contains": "C1*exp(x)",
    },
    {
        "name": "gradient",
        "chapter": "multivariable_calculus",
        "topic": "gradient",
        "inputs": {"expression": "x^2*y", "variables": ["x", "y"]},
        "expected_contains": ("2*x*y", "x**2"),
    },
    {
        "name": "directional_derivative",
        "chapter": "multivariable_calculus",
        "topic": "directional_derivative",
        "inputs": {
            "expression": "x^2+y^2",
            "variables": ["x", "y"],
            "point": ["1", "1"],
            "direction": ["1", "0"],
        },
        "expected_result": "2",
    },
    {
        "name": "line_scalar_integral",
        "chapter": "line_surface_integrals",
        "topic": "line_scalar",
        "inputs": {
            "expression": "x+y",
            "parameter": "t",
            "components": {"x": "t", "y": "t"},
            "lower": "0",
            "upper": "1",
        },
        "expected_result": "sqrt(2)",
    },
    {
        "name": "flux_integral",
        "chapter": "line_surface_integrals",
        "topic": "flux",
        "inputs": {
            "vector_field": ["0", "0", "1"],
            "parameters": ["u", "v"],
            "components": {"x": "u", "y": "v", "z": "0"},
            "u_lower": "0",
            "u_upper": "1",
            "v_lower": "0",
            "v_upper": "1",
        },
        "expected_result": "1",
    },
)


def verify_solve_regression(
    base_url: str,
    api_key: str | None,
    *,
    skip_version_check: bool,
    timeout: float,
) -> None:
    print(f"[1/2] Health: {base_url}/health")
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

    api_key_enabled = bool(health.get("api_key_enabled"))
    if api_key_enabled and not api_key:
        raise VerificationError(
            "Deployment requires MATH_API_KEY; pass --api-key or set it in env"
        )

    print(f"[2/2] /solve-query regression: {len(SOLVE_CASES)} cases")
    for case in SOLVE_CASES:
        params = {
            "chapter": case["chapter"],
            "topic": case["topic"],
            "inputs": json.dumps(case["inputs"], separators=(",", ":")),
        }
        if case.get("candidate"):
            params["candidate"] = case["candidate"]

        payload = request_json(
            base_url,
            "/solve-query",
            params=params,
            method="POST",
            api_key=api_key,
            timeout=timeout,
        )
        result = payload.get("result", "")

        if "expected_result" in case:
            expect(
                result == case["expected_result"],
                f"{case['name']} result mismatch: {payload}",
            )

        for expected_part in case.get("expected_contains", ()):
            expect(
                expected_part in result,
                f"{case['name']} missing {expected_part!r}: {payload}",
            )

        if "expected_is_correct" in case:
            expect(
                payload.get("is_correct") is case["expected_is_correct"],
                f"{case['name']} candidate check mismatch: {payload}",
            )

        print(f"      {case['name']}: OK")

    print("\nSolve regression passed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify multi-chapter /solve-query deployment results"
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
    try:
        verify_solve_regression(
            args.base_url,
            args.api_key,
            skip_version_check=args.skip_version_check,
            timeout=args.timeout,
        )
    except VerificationError as exc:
        print(f"\nSolve regression failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
