from __future__ import annotations

import io
import re
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.verify_deployment import (
    DEMO_REQUIRED_MARKERS,
    DEFAULT_NON_IMAGE_URL,
    DEFAULT_OCR_IMAGE_URL,
    VerificationError,
    assert_demo_page_markers,
    assert_model_health,
    request_json,
    verify_ocr_url_api,
)


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def rate_limit_error(retry_after: str = "1") -> HTTPError:
    headers = Message()
    headers["Retry-After"] = retry_after
    return HTTPError(
        "https://example.test/solve-query",
        429,
        "Too many requests",
        headers,
        io.BytesIO(b'{"detail":"Too many requests"}'),
    )


class VerifyDeploymentTests(unittest.TestCase):
    def test_default_ocr_fixture_is_versioned_in_repository(self) -> None:
        fixture = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "ocr-deployment-regression.png"
        )

        self.assertTrue(fixture.is_file())
        self.assertTrue(fixture.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(
            DEFAULT_OCR_IMAGE_URL,
            (
                "https://raw.githubusercontent.com/cfy123456-yr/gaoshu-agent/"
                "main/tests/fixtures/ocr-deployment-regression.png"
            ),
        )
        self.assertEqual(
            DEFAULT_NON_IMAGE_URL,
            (
                "https://raw.githubusercontent.com/cfy123456-yr/gaoshu-agent/"
                "main/README.md"
            ),
        )

    @staticmethod
    def model_health() -> dict[str, object]:
        return {
            "ocr": {
                "configured": True,
                "provider": "vision",
                "vision_configured": True,
                "vision_provider": "dashscope",
                "vision_model": "qwen3-vl-plus",
            },
            "general_chat": {
                "configured": True,
                "provider": "dashscope",
                "model": "qwen-plus",
                "key_source": "vision_fallback",
                "timeout_seconds": 30.0,
            },
        }

    def test_accepts_configured_model_health(self) -> None:
        assert_model_health(self.model_health())

    def test_reports_missing_general_chat_configuration(self) -> None:
        health = self.model_health()
        health["general_chat"] = {
            "configured": False,
            "provider": "",
            "model": "",
            "key_source": "missing",
            "timeout_seconds": 30.0,
        }

        with self.assertRaisesRegex(VerificationError, "普通问答模型未配置"):
            assert_model_health(health)

    def test_reports_unknown_model_provider(self) -> None:
        health = self.model_health()
        health["ocr"]["vision_provider"] = "unknown"

        with self.assertRaisesRegex(VerificationError, "视觉模型提供商无效"):
            assert_model_health(health)

    def test_reports_unknown_model_key_source(self) -> None:
        health = self.model_health()
        health["general_chat"]["key_source"] = "unknown"

        with self.assertRaisesRegex(VerificationError, "普通问答密钥来源无效"):
            assert_model_health(health)

    def test_accepts_current_demo_page_markers(self) -> None:
        page = "\n".join(
            (
                *DEMO_REQUIRED_MARKERS,
                'fetch("/demo/api/chat", { method: "POST" })',
            )
        )

        assert_demo_page_markers(page)

    def test_reports_missing_required_marker(self) -> None:
        missing_marker = DEMO_REQUIRED_MARKERS[-1]
        page = "\n".join(
            (
                *DEMO_REQUIRED_MARKERS[:-1],
                'fetch("/demo/api/chat", { method: "POST" })',
            )
        )

        with self.assertRaisesRegex(
            VerificationError,
            re.escape(f"演示页缺少必需标记：{missing_marker}"),
        ):
            assert_demo_page_markers(page)

    def test_reports_missing_slow_notice_marker(self) -> None:
        missing_marker = "SLOW_REQUEST_NOTICE_MS = 8000"
        page = "\n".join(
            (
                *(
                    marker
                    for marker in DEMO_REQUIRED_MARKERS
                    if marker != missing_marker
                ),
                'fetch("/demo/api/chat", { method: "POST" })',
            )
        )

        with self.assertRaisesRegex(
            VerificationError,
            re.escape(f"演示页缺少必需标记：{missing_marker}"),
        ):
            assert_demo_page_markers(page)

    def test_reports_old_demo_page_without_chat_call(self) -> None:
        page = "\n".join(DEMO_REQUIRED_MARKERS)

        with self.assertRaisesRegex(VerificationError, "缺少聊天接口调用"):
            assert_demo_page_markers(page)

    def test_accepts_remote_image_ocr_contract(self) -> None:
        responses = (
            {"detail": "缺少 image_url 参数。"},
            {"detail": "图片链接不能指向本机地址。"},
            {"detail": "图片链接不能指向本机、内网或保留地址。"},
            {"detail": "图片链接返回的内容不是图片。"},
            {
                "provider": "vision",
                "requires_confirmation": True,
                "text": "∫ x^2 dx",
            },
        )

        with patch(
            "scripts.verify_deployment.request_json",
            side_effect=responses,
        ) as request_json:
            verify_ocr_url_api(
                "https://example.test",
                "https://images.example/question.png",
                timeout=20.0,
            )

        self.assertEqual(5, request_json.call_count)
        non_image_call = request_json.call_args_list[3]
        self.assertEqual(
            {"image_url": DEFAULT_NON_IMAGE_URL},
            non_image_call.kwargs["json_body"],
        )
        recognized_call = request_json.call_args_list[-1]
        self.assertEqual(70.0, recognized_call.kwargs["timeout"])

    def test_uses_explicit_non_image_url(self) -> None:
        responses = (
            {"detail": "缺少 image_url 参数。"},
            {"detail": "图片链接不能指向本机地址。"},
            {"detail": "图片链接不能指向本机、内网或保留地址。"},
            {"detail": "图片链接返回的内容不是图片。"},
            {
                "provider": "vision",
                "requires_confirmation": True,
                "text": "∫ x^2 dx",
            },
        )

        with patch(
            "scripts.verify_deployment.request_json",
            side_effect=responses,
        ) as request_json:
            verify_ocr_url_api(
                "https://example.test",
                "https://images.example/question.png",
                timeout=20.0,
                non_image_url="https://example.test/README.txt",
            )

        non_image_call = request_json.call_args_list[3]
        self.assertEqual(
            {"image_url": "https://example.test/README.txt"},
            non_image_call.kwargs["json_body"],
        )

    def test_rejects_remote_image_ocr_without_dx(self) -> None:
        responses = (
            {"detail": "缺少 image_url 参数。"},
            {"detail": "图片链接不能指向本机地址。"},
            {"detail": "图片链接不能指向本机、内网或保留地址。"},
            {"detail": "图片链接返回的内容不是图片。"},
            {
                "provider": "vision",
                "requires_confirmation": True,
                "text": "∫ xexdx",
            },
        )

        with (
            patch(
                "scripts.verify_deployment.request_json",
                side_effect=responses,
            ),
            self.assertRaisesRegex(VerificationError, "平方、积分变量和 dx"),
        ):
            verify_ocr_url_api(
                "https://example.test",
                "https://images.example/question.png",
                timeout=20.0,
            )

    def test_request_json_retries_transient_rate_limit(self) -> None:
        responses = (
            rate_limit_error("1"),
            rate_limit_error("2"),
            FakeResponse(200, b'{"status":"ok"}'),
        )

        with (
            patch(
                "scripts.verify_deployment.urlopen",
                side_effect=responses,
            ) as urlopen,
            patch("scripts.verify_deployment.time.sleep") as sleep,
        ):
            payload = request_json(
                "https://example.test",
                "/solve-query",
                method="POST",
                json_body={"chapter": "limits"},
            )

        self.assertEqual({"status": "ok"}, payload)
        self.assertEqual(3, urlopen.call_count)
        self.assertEqual(2, sleep.call_count)
        self.assertEqual(1.0, sleep.call_args_list[0].args[0])
        self.assertEqual(2.0, sleep.call_args_list[1].args[0])

    def test_request_json_stops_after_limited_rate_limit_retries(self) -> None:
        responses = tuple(rate_limit_error("1") for _ in range(4))

        with (
            patch(
                "scripts.verify_deployment.urlopen",
                side_effect=responses,
            ) as urlopen,
            patch("scripts.verify_deployment.time.sleep"),
            self.assertRaisesRegex(VerificationError, "实际为 429"),
        ):
            request_json(
                "https://example.test",
                "/solve-query",
                method="POST",
            )

        self.assertEqual(4, urlopen.call_count)

    def test_request_json_does_not_retry_expected_rate_limit_response(self) -> None:
        with patch(
            "scripts.verify_deployment.urlopen",
            side_effect=[rate_limit_error("61")],
        ) as urlopen:
            payload = request_json(
                "https://example.test",
                "/solve-query",
                method="POST",
                expected_status=429,
            )

        self.assertEqual({"detail": "Too many requests"}, payload)
        self.assertEqual(1, urlopen.call_count)


if __name__ == "__main__":
    unittest.main()
