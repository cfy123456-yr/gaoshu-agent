from __future__ import annotations

import unittest

from scripts.verify_deployment import (
    DEMO_REQUIRED_MARKERS,
    VerificationError,
    assert_demo_page_markers,
)


class VerifyDeploymentTests(unittest.TestCase):
    def test_accepts_current_demo_page_markers(self) -> None:
        page = "\n".join(
            (
                *DEMO_REQUIRED_MARKERS,
                'fetch("/demo/api/chat", { method: "POST" })',
            )
        )

        assert_demo_page_markers(page)

    def test_reports_missing_mobile_marker(self) -> None:
        missing_marker = DEMO_REQUIRED_MARKERS[-1]
        page = "\n".join(
            (
                *DEMO_REQUIRED_MARKERS[:-1],
                'fetch("/demo/api/chat", { method: "POST" })',
            )
        )

        with self.assertRaisesRegex(
            VerificationError,
            f"演示页缺少移动端加固标记：{missing_marker}",
        ):
            assert_demo_page_markers(page)

    def test_reports_old_demo_page_without_chat_call(self) -> None:
        page = "\n".join(DEMO_REQUIRED_MARKERS)

        with self.assertRaisesRegex(VerificationError, "缺少聊天接口调用"):
            assert_demo_page_markers(page)


if __name__ == "__main__":
    unittest.main()
