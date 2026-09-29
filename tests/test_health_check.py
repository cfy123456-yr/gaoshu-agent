import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import scripts.check_health as check_health


class HealthCheckTest(unittest.TestCase):
    def run_main(self, results, *args):
        calls = []

        def fake_check(url, expected_version, timeout):
            calls.append((url, expected_version, timeout))
            result = results[len(calls) - 1]
            if isinstance(result, Exception):
                raise result
            return result

        with (
            patch.object(check_health, "check", side_effect=fake_check),
            patch.object(check_health.time, "sleep") as sleep,
            patch.object(
                sys,
                "argv",
                ["check_health.py", *args],
            ),
            redirect_stdout(io.StringIO()) as stdout,
            redirect_stderr(io.StringIO()) as stderr,
        ):
            exit_code = check_health.main()

        return exit_code, calls, sleep, stdout.getvalue(), stderr.getvalue()

    def test_retries_transient_failure_until_health_recovers(self):
        exit_code, calls, sleep, stdout, stderr = self.run_main(
            [
                RuntimeError("cold start"),
                {
                    "status": "ok",
                    "version": "0.6.7",
                    "uptime_seconds": 12.5,
                },
            ],
            "--attempts",
            "3",
            "--delay",
            "1",
        )

        self.assertEqual(0, exit_code)
        self.assertEqual(2, len(calls))
        self.assertEqual(1, sleep.call_count)
        self.assertIn("public health check passed", stdout)
        self.assertIn("attempt 1/3: cold start", stderr)

    def test_returns_failure_after_all_attempts_are_exhausted(self):
        exit_code, calls, sleep, stdout, stderr = self.run_main(
            [
                RuntimeError("HTTP 502"),
                RuntimeError("HTTP 502"),
                RuntimeError("HTTP 502"),
            ],
            "--attempts",
            "3",
            "--delay",
            "1",
        )

        self.assertEqual(1, exit_code)
        self.assertEqual(3, len(calls))
        self.assertEqual(2, sleep.call_count)
        self.assertEqual("", stdout)
        self.assertIn("public health check failed", stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
