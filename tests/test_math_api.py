import json
import os
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


class MathApiSmokeTest(unittest.TestCase):
    def request(self, path, params=None, expected_status=200, json_payload=None):
        query = urlencode(params or {})
        url = f"{BASE_URL}{path}"
        if query:
            url = f"{url}?{query}"
        body = None
        headers = {}
        if json_payload is not None:
            body = json.dumps(json_payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(
            url,
            data=body,
            headers=headers,
            method="POST" if path != "/health" else "GET",
        )

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
        self.assertEqual("0.6.11", payload["version"])
        self.assertIn("api_key_enabled", payload)

    def test_spoken_chinese_expression_is_normalized_by_api(self):
        payload = self.request(
            "/verify-query",
            {"expression": "x的平方", "variable": "", "candidate": ""},
        )

        self.assertEqual("x**2", payload["expression"])
        self.assertEqual("2*x", payload["derivative"])
        self.assertIsNone(payload["candidate"])

    def test_coze_blank_optional_parameters_fall_back_to_defaults(self):
        integral = self.request(
            "/integrate-query",
            {
                "expression": "根号下x",
                "variable": "",
                "lower": "",
                "upper": "",
                "candidate": "",
            },
        )
        self.assertEqual("x", integral["variable"])
        self.assertIsNone(integral["candidate"])

        limit = self.request(
            "/limit-query",
            {
                "expression": "sinx除以x",
                "variable": "",
                "point": "",
                "direction": "",
                "candidate": "",
            },
        )
        self.assertEqual("1", limit["limit"])
        self.assertEqual("x", limit["variable"])
        self.assertEqual("0", limit["point"])

        plot = self.request(
            "/plot-query",
            {
                "expression": "sinx",
                "variable": "",
                "x_min": "",
                "x_max": "",
                "y_min": "",
                "y_max": "",
                "samples": "",
                "width": "",
                "height": "",
            },
        )
        self.assertEqual("x", plot["variable"])
        self.assertIn("<svg", plot["svg"])

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

    def test_exponential_limit_candidate(self):
        payload = self.request(
            "/limit-query",
            {
                "expression": "(1+1/x)^x",
                "variable": "x",
                "point": "oo",
                "candidate": "E",
            },
        )
        self.assertEqual("E", payload["limit"])
        self.assertIs(True, payload["is_correct"])

    def test_unified_solve_for_extended_chapters(self):
        payload = self.request(
            "/solve",
            json_payload={
                "chapter": "derivatives",
                "topic": "higher_derivative",
                "inputs": {
                    "expression": "x^3",
                    "variable": "x",
                    "order": 2,
                },
                "candidate": "6x",
            },
        )
        self.assertEqual("6*x", payload["result"])
        self.assertIs(True, payload["is_correct"])

        gradient = self.request(
            "/solve",
            json_payload={
                "chapter": "multivariable_calculus",
                "topic": "gradient",
                "inputs": {"expression": "x^2*y", "variables": ["x", "y"]},
            },
        )
        self.assertIn("2*x*y", gradient["result"])

        query_payload = self.request(
            "/solve-query",
            {
                "chapter": "series",
                "topic": "convergence",
                "inputs": json.dumps(
                    {"expression": "1/n^2", "variable": "n"},
                    ensure_ascii=True,
                ),
            },
        )
        self.assertEqual("收敛", query_payload["result"])

    def test_parametric_tangent_normal_solve_endpoint_contract(self):
        payload = self.request(
            "/solve",
            json_payload={
                "chapter": "derivatives",
                "topic": "parametric_tangent_normal",
                "inputs": {
                    "x_expression": "sin(t)",
                    "y_expression": "cos(2*t)",
                    "parameter": "t",
                    "parameter_value": "pi/4",
                },
            },
        )

        self.assertEqual("ok", payload["status"])
        self.assertIs(True, payload["verified"])
        self.assertIs(True, payload["verification"]["passed"])
        self.assertEqual(
            "parametric_tangent_normal",
            payload["verification"]["kind"],
        )
        self.assertIn("(sqrt(2)/2, 0)", payload["result"])

        missing_parameter = self.request(
            "/solve",
            json_payload={
                "chapter": "derivatives",
                "topic": "parametric_tangent_normal",
                "inputs": {
                    "x_expression": "sin(t)",
                    "y_expression": "cos(2*t)",
                    "parameter": "t",
                },
            },
            expected_status=400,
        )
        self.assertIn("parameter_value", missing_parameter["detail"])

    def test_function_plot_endpoint(self):
        payload = self.request(
            "/plot-query",
            {
                "expression": "sin(x)",
                "variable": "x",
                "x_min": "-3",
                "x_max": "3",
            },
        )
        self.assertEqual("sin(x)", payload["expression"])
        self.assertIn("<svg", payload["svg"])

    def test_invalid_expression_is_rejected(self):
        payload = self.request(
            "/verify-query",
            {"expression": "__import__('os')", "variable": "x"},
            expected_status=400,
        )
        self.assertIn("unsupported identifier", payload["detail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
