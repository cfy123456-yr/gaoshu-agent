import json
import logging
import time
import unittest
from logging.handlers import RotatingFileHandler
from unittest.mock import patch

from fastapi import HTTPException

import app.main as main


class ServiceComponentTest(unittest.TestCase):
    def test_client_key_ignores_forwarded_for_without_trusted_proxy(self):
        client_key = main.client_key_from_request(
            {"x-forwarded-for": "198.51.100.99"},
            "203.0.113.7",
            trusted_proxy_hops=0,
        )

        self.assertEqual("203.0.113.7", client_key)

    def test_client_key_uses_rightmost_address_for_trusted_proxy(self):
        client_key = main.client_key_from_request(
            {"x-forwarded-for": "198.51.100.99, 203.0.113.7"},
            "10.0.0.8",
            trusted_proxy_hops=1,
        )

        self.assertEqual("203.0.113.7", client_key)

    def test_rate_limiter_caps_tracked_clients(self):
        limiter = main.InMemoryRateLimiter(
            limit_per_minute=10,
            max_clients=2,
            prune_interval_seconds=1.0,
        )

        with patch.object(
            main.time,
            "monotonic",
            side_effect=[100.0, 101.1, 102.2, 103.3],
        ):
            limiter.check("client-a")
            limiter.check("client-b")
            limiter.check("client-c")
            limiter.check("client-d")

        self.assertLessEqual(len(limiter.requests), 2)

    def test_calculation_timeout_returns_504(self):
        previous_timeout = main.CALCULATION_TIMEOUT_SECONDS
        main.CALCULATION_TIMEOUT_SECONDS = 0.01
        try:
            with self.assertRaises(HTTPException) as context:
                main.run_calculation(
                    lambda: time.sleep(0.1),
                    "unit-timeout",
                )
        finally:
            main.CALCULATION_TIMEOUT_SECONDS = previous_timeout

        self.assertEqual(504, context.exception.status_code)
        self.assertEqual(
            "0.01",
            context.exception.headers["X-Calculation-Timeout"],
        )

    def test_two_sided_limit_checks_both_directions(self):
        payload = main.calculate_limit(
            main.LimitRequest(
                expression="1/x",
                variable="x",
                point="0",
            ),
            _=None,
        )

        self.assertIs(False, payload.exists)
        self.assertEqual("不存在", payload.limit)
        self.assertEqual("-oo", payload.left_limit)
        self.assertEqual("oo", payload.right_limit)

    def test_oscillating_two_sided_limit_does_not_exist(self):
        payload = main.calculate_limit(
            main.LimitRequest(
                expression="sin(1/x)",
                variable="x",
                point="0",
            ),
            _=None,
        )

        self.assertIs(False, payload.exists)
        self.assertEqual("不存在", payload.limit)
        self.assertIn("振荡", payload.explanation)

    def test_one_sided_infinite_limit_remains_valid(self):
        payload = main.calculate_limit(
            main.LimitRequest(
                expression="1/x",
                variable="x",
                point="0",
                direction="+",
            ),
            _=None,
        )

        self.assertIs(True, payload.exists)
        self.assertEqual("oo", payload.limit)
        self.assertEqual("oo", payload.right_limit)
        self.assertIsNone(payload.left_limit)

    def test_json_logger_does_not_store_math_expression(self):
        record = logging.LogRecord(
            name="gaoshu.math",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="request_completed",
            args=(),
            exc_info=None,
        )
        record.event = "request_completed"
        record.endpoint = "/verify-query"
        record.status_code = 200
        record.expression = "x^2"

        payload = json.loads(main.JsonLineFormatter().format(record))

        self.assertEqual("/verify-query", payload["endpoint"])
        self.assertNotIn("expression", payload)
        self.assertNotIn("x^2", json.dumps(payload))

    def test_persistent_logging_uses_rotation(self):
        rotating_handlers = [
            handler
            for handler in main.logger.handlers
            if isinstance(handler, RotatingFileHandler)
        ]
        if not rotating_handlers:
            self.skipTest("当前测试进程未启用持久化日志")

        handler = rotating_handlers[0]
        self.assertEqual(5 * 1024 * 1024, handler.maxBytes)
        self.assertEqual(3, handler.backupCount)


if __name__ == "__main__":
    unittest.main(verbosity=2)
