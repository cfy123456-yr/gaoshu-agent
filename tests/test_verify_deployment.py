from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.verify_deployment import (
    DEMO_REQUIRED_MARKERS,
    DEFAULT_OCR_IMAGE_URL,
    VerificationError,
    assert_demo_page_markers,
    assert_model_health,
    verify_ocr_url_api,
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
        recognized_call = request_json.call_args_list[-1]
        self.assertEqual(70.0, recognized_call.kwargs["timeout"])

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


if __name__ == "__main__":
    unittest.main()
