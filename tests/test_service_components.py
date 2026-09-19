import json
import logging
import time
import unittest
from logging.handlers import RotatingFileHandler

from fastapi import HTTPException

import app.main as main


class ServiceComponentTest(unittest.TestCase):
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
