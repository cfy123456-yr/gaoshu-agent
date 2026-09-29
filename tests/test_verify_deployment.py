from __future__ import annotations

import unittest

from scripts.verify_deployment import (
    DEMO_REQUIRED_MARKERS,
    VerificationError,
    assert_demo_page_markers,
    assert_model_health,
)


class VerifyDeploymentTests(unittest.TestCase):
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
            f"演示页缺少必需标记：{missing_marker}",
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
            f"演示页缺少必需标记：{missing_marker}",
        ):
            assert_demo_page_markers(page)

    def test_reports_old_demo_page_without_chat_call(self) -> None:
        page = "\n".join(DEMO_REQUIRED_MARKERS)

        with self.assertRaisesRegex(VerificationError, "缺少聊天接口调用"):
            assert_demo_page_markers(page)


if __name__ == "__main__":
    unittest.main()
