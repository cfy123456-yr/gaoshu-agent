#!/usr/bin/env python3
"""Verify /limit-query results on a deployment."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_deployment import VerificationError, expect, request_json


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
EXPECTED_VERSION = "0.4.2"

LIMIT_CASES = (
    {
        "name": "standard_limit",
        "params": {
            "expression": "sin(x)/x",
            "variable": "x",
            "point": "0",
            "candidate": "1",
        },
        "expected_limit": "1",
        "expected_is_correct": True,
    },
    {
        "name": "incorrect_candidate",
        "params": {
            "expression": "sin(x)/x",
            "variable": "x",
            "point": "0",
            "candidate": "0",
        },
        "expected_limit": "1",
        "expected_is_correct": False,
    },
    {
        "name": "right_infinite_limit",
        "params": {
            "expression": "1/x",
            "variable": "x",
            "point": "0",
            "direction": "+",
            "candidate": "oo",
        },
        "expected_limit": "oo",
        "expected_is_correct": True,
    },
    {
        "name": "left_negative_infinite_limit",
        "params": {
            "expression": "1/x",
            "variable": "x",
            "point": "0",
            "direction": "-",
            "candidate": "-oo",
        },
        "expected_limit": "-oo",
        "expected_is_correct": True,
    },
    {
        "name": "finite_limit_by_cancellation",
        "params": {
            "expression": "(1-cos(x))/x^2",
            "variable": "x",
            "point": "0",
            "candidate": "1/2",
        },
        "expected_limit": "1/2",
        "expected_is_correct": True,
    },
    {
        "name": "limit_at_infinity",
        "params": {
            "expression": "(1+1/x)^x",
            "variable": "x",
            "point": "oo",
            "candidate": "E",
        },
        "expected_limit": "E",
        "expected_is_correct": True,
    },
)


def verify_limit_regression(
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

    print(f"[2/2] /limit-query regression: {len(LIMIT_CASES)} cases")
    for case in LIMIT_CASES:
        payload = request_json(
            base_url,
            "/limit-query",
            params=case["params"],
            method="POST",
            api_key=api_key,
            timeout=timeout,
        )

        expect(
            payload.get("limit") == case["expected_limit"],
            f"{case['name']} limit mismatch: {payload}",
        )
        expect(
            payload.get("is_correct") is case["expected_is_correct"],
            f"{case['name']} candidate check mismatch: {payload}",
        )
        print(f"      {case['name']}: OK")

    print("\nLimit regression passed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify /limit-query deployment results"
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
        verify_limit_regression(
            args.base_url,
            args.api_key,
            skip_version_check=args.skip_version_check,
            timeout=args.timeout,
        )
    except VerificationError as exc:
        print(f"\nLimit regression failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
