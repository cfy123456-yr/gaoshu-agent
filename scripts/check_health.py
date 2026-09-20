#!/usr/bin/env python3
"""Check a deployed math API health endpoint with a few retries."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_URL = "https://cfyyy.pythonanywhere.com"
DEFAULT_VERSION = "0.5.0"


def read_health(url: str, timeout: float) -> dict:
    request = Request(url.rstrip("/") + "/health", method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc

    if status != 200:
        raise RuntimeError(f"expected HTTP 200, got {status}")
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("health endpoint did not return JSON") from exc


def check(url: str, expected_version: str, timeout: float) -> dict:
    health = read_health(url, timeout)
    if health.get("status") != "ok":
        raise RuntimeError(f"status is not ok: {health}")
    if expected_version and health.get("version") != expected_version:
        raise RuntimeError(
            f"expected version {expected_version}, got {health.get('version')}"
        )
    return health


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check public deployment health")
    parser.add_argument(
        "--url",
        default=os.getenv("HEALTH_CHECK_URL", DEFAULT_URL),
        help=f"service base URL, default: {DEFAULT_URL}",
    )
    parser.add_argument(
        "--expected-version",
        default=os.getenv("EXPECTED_VERSION", DEFAULT_VERSION),
        help=f"expected service version, default: {DEFAULT_VERSION}",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--delay", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    attempts = max(1, args.attempts)
    for attempt in range(1, attempts + 1):
        try:
            health = check(args.url, args.expected_version, args.timeout)
        except RuntimeError as exc:
            print(f"attempt {attempt}/{attempts}: {exc}", file=sys.stderr)
            if attempt < attempts:
                time.sleep(max(0.0, args.delay))
                continue
            print("public health check failed", file=sys.stderr)
            return 1

        print(
            "public health check passed: "
            f"version={health.get('version')}, "
            f"uptime_seconds={health.get('uptime_seconds')}"
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
