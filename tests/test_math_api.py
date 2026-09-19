import json
import os
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


class MathApiSmokeTest(unittest.TestCase):
    def request(self, path, params=None, expected_status=200):
        query = urlencode(params or {})
        url = f"{BASE_URL}{path}"
        if query:
            url = f"{url}?{query}"
        request = Request(url, method="POST" if path != "/health" else "GET")

        try:
            with urlopen(request, timeout=10) as response:
                status = response.status
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            status = exc.code
            payload = json.loads(exc.read().decode("utf-8"))
        except URLError as exc:
            self.fail(
                f"无法连接数学服务 {BASE_URL}。请先运行 scripts\\start-demo.cmd。原因：{exc}"
            )

        self.assertEqual(
            expected_status,
            status,
            f"{path} 返回 {status}，响应为 {payload}",
        )
        return payload

    def test_health_reports_current_version(self):
        payload = self.request("/health")
        self.assertEqual("ok", payload["status"])
        self.assertEqual("0.3.0", payload["version"])
        self.assertIn("api_key_enabled", payload)

    def test_derivative_result_and_candidate_check(self):
        correct = self.request(
            "/verify-query",
            {"expression": "x^2", "variable": "x", "candidate": "2x"},
        )
        self.assertEqual("2*x", correct["derivative"])
        self.assertIs(True, correct["is_correct"])

        incorrect = self.request(
            "/verify-query",
            {"expression": "x^3", "variable": "x", "candidate": "2x^2"},
        )
        self.assertEqual("3*x**2", incorrect["derivative"])
        self.assertIs(False, incorrect["is_correct"])

    def test_indefinite_and_definite_integrals(self):
        indefinite = self.request(
            "/integrate-query",
            {"expression": "x^2", "variable": "x", "candidate": "x^3/3"},
        )
        self.assertEqual("x**3/3", indefinite["integral"])
        self.assertIs(True, indefinite["is_correct"])

        definite = self.request(
            "/integrate-query",
            {
                "expression": "x^2",
                "variable": "x",
                "lower": "0",
                "upper": "1",
                "candidate": "1/3",
            },
        )
        self.assertEqual("1/3", definite["integral"])
        self.assertIs(True, definite["is_correct"])

    def test_limit_result_and_candidate_check(self):
        payload = self.request(
            "/limit-query",
            {
                "expression": "sin(x)/x",
                "variable": "x",
                "point": "0",
                "candidate": "1",
            },
        )
        self.assertEqual("1", payload["limit"])
        self.assertIs(True, payload["is_correct"])

    def test_left_and_right_limits(self):
        right = self.request(
            "/limit-query",
            {
                "expression": "1/x",
                "variable": "x",
                "point": "0",
                "direction": "+",
                "candidate": "oo",
            },
        )
        self.assertEqual("oo", right["limit"])
        self.assertIs(True, right["is_correct"])

        left = self.request(
            "/limit-query",
            {
                "expression": "1/x",
                "variable": "x",
                "point": "0",
                "direction": "-",
                "candidate": "-oo",
            },
        )
        self.assertEqual("-oo", left["limit"])
        self.assertIs(True, left["is_correct"])

    def test_invalid_expression_is_rejected(self):
        payload = self.request(
            "/verify-query",
            {"expression": "__import__('os')", "variable": "x"},
            expected_status=400,
        )
        self.assertIn("unsupported identifier", payload["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
