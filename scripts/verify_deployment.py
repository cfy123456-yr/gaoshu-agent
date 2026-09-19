#!/usr/bin/env python3
"""Verify a local, tunnel, or cloud deployment of the math API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
EXPECTED_VERSION = "0.3.0"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


class VerificationError(RuntimeError):
    """Raised when a deployment check does not match expectations."""


def request_json(
    base_url: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    method: str = "GET",
    api_key: str | None = None,
    expected_status: int = 200,
    timeout: float = 20.0,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"

    headers: dict[str, str] = {}
    if "loca.lt" in base_url:
        headers["bypass-tunnel-reminder"] = "true"
    if api_key:
        headers["X-API-Key"] = api_key

    data = b"" if method == "POST" else None
    request = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            raw_body = response.read()
    except HTTPError as exc:
        status = exc.code
        raw_body = exc.read()
    except (URLError, TimeoutError, OSError) as exc:
        raise VerificationError(f"无法连接 {url}: {exc}") from exc

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(
            f"{path} 返回了非 JSON 响应，HTTP 状态码为 {status}"
        ) from exc

    if status != expected_status:
        raise VerificationError(
            f"{path} 预期 HTTP {expected_status}，实际为 {status}：{payload}"
        )
    return payload


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def verify_deployment(
    base_url: str,
    api_key: str | None,
    *,
    skip_version_check: bool,
    timeout: float,
) -> None:
    print(f"[1/7] 健康检查: {base_url}/health")
    health = request_json(base_url, "/health", timeout=timeout)
    expect(health.get("status") == "ok", f"健康检查失败：{health}")
    if not skip_version_check:
        expect(
            health.get("version") == EXPECTED_VERSION,
            f"服务版本不匹配：预期 {EXPECTED_VERSION}，实际 {health.get('version')}",
        )
    print(
        "      版本 {version}，API Key {api_key_state}，日志 {logging_state}".format(
            version=health.get("version"),
            api_key_state="已启用" if health.get("api_key_enabled") else "未启用",
            logging_state=(
                "已启用" if health.get("persistent_logging_enabled") else "未启用"
            ),
        )
    )

    api_key_enabled = bool(health.get("api_key_enabled"))
    if api_key_enabled and not api_key:
        raise VerificationError(
            "云端已启用 MATH_API_KEY，请通过 --api-key 或环境变量 MATH_API_KEY 提供密钥"
        )

    print("[2/7] 求导与候选答案判定")
    derivative = request_json(
        base_url,
        "/verify-query",
        params={"expression": "x^2", "variable": "x", "candidate": "2x"},
        method="POST",
        api_key=api_key,
        timeout=timeout,
    )
    expect(derivative.get("derivative") == "2*x", f"求导结果错误：{derivative}")
    expect(derivative.get("is_correct") is True, f"求导判题错误：{derivative}")

    print("[3/7] 不定积分与候选答案判定")
    indefinite = request_json(
        base_url,
        "/integrate-query",
        params={
            "expression": "x^2",
            "variable": "x",
            "candidate": "x^3/3",
        },
        method="POST",
        api_key=api_key,
        timeout=timeout,
    )
    expect(indefinite.get("integral") == "x**3/3", f"不定积分结果错误：{indefinite}")
    expect(indefinite.get("is_correct") is True, f"不定积分判题错误：{indefinite}")

    print("[4/7] 定积分与候选答案判定")
    definite = request_json(
        base_url,
        "/integrate-query",
        params={
            "expression": "x^2",
            "variable": "x",
            "lower": "0",
            "upper": "1",
            "candidate": "1/3",
        },
        method="POST",
        api_key=api_key,
        timeout=timeout,
    )
    expect(definite.get("integral") == "1/3", f"定积分结果错误：{definite}")
    expect(definite.get("is_correct") is True, f"定积分判题错误：{definite}")

    print("[5/7] 极限与候选答案判定")
    limit = request_json(
        base_url,
        "/limit-query",
        params={
            "expression": "sin(x)/x",
            "variable": "x",
            "point": "0",
            "candidate": "1",
        },
        method="POST",
        api_key=api_key,
        timeout=timeout,
    )
    expect(limit.get("limit") == "1", f"极限结果错误：{limit}")
    expect(limit.get("is_correct") is True, f"极限判题错误：{limit}")

    print("[6/7] 非法表达式拦截")
    invalid = request_json(
        base_url,
        "/verify-query",
        params={"expression": "__import__('os')", "variable": "x"},
        method="POST",
        api_key=api_key,
        expected_status=400,
        timeout=timeout,
    )
    expect("unsupported identifier" in invalid.get("detail", ""), f"安全拦截异常：{invalid}")

    print("[7/7] API Key 鉴权")
    if api_key_enabled:
        unauthorized = request_json(
            base_url,
            "/verify-query",
            params={"expression": "x^2", "variable": "x"},
            method="POST",
            expected_status=401,
            timeout=timeout,
        )
        expect(
            unauthorized.get("detail") == "Invalid API key",
            f"无密钥请求未被正确拦截：{unauthorized}",
        )
        print("      无密钥请求已返回 401")
    else:
        print("      当前未启用密钥，跳过；固定公网部署后必须启用")

    print("\n部署验收通过。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证数学 API 部署是否完整可用")
    parser.add_argument(
        "--base-url",
        default=os.getenv("TEST_BASE_URL", DEFAULT_BASE_URL),
        help=f"部署根地址，默认 {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("MATH_API_KEY") or None,
        help="云端 MATH_API_KEY；也可通过同名环境变量传入",
    )
    parser.add_argument(
        "--skip-version-check",
        action="store_true",
        help="跳过版本号检查",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="单次请求超时秒数，默认 20",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        verify_deployment(
            args.base_url,
            args.api_key,
            skip_version_check=args.skip_version_check,
            timeout=args.timeout,
        )
    except VerificationError as exc:
        print(f"\n部署验收失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
