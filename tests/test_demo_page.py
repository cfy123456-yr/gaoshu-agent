import unittest
from unittest.mock import patch

from deploy import wsgi_app


class DemoPageTest(unittest.TestCase):
    def setUp(self):
        self.client = wsgi_app.application.test_client()

    def test_demo_page_is_available(self):
        response = self.client.get("/demo")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("知微老师", html)
        self.assertIn("/demo/api/chat", html)
        self.assertIn('id="chatInput"', html)
        self.assertIn('id="messageList"', html)
        self.assertIn("/static/katex/katex.min.css", html)
        self.assertIn("/static/katex/katex.min.js", html)
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertIn("controller.abort(), 6000", html)

    def test_demo_health_is_available(self):
        response = self.client.get("/demo/api/health")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("ok", payload["status"])
        self.assertTrue(payload["demo"]["available"])
        self.assertEqual("/demo", payload["demo"]["page"])

    def test_health_and_static_requests_do_not_consume_rate_limit(self):
        with patch.object(wsgi_app.rate_limiter, "check") as check:
            self.client.get("/demo/api/health")
            self.client.get("/health")
            self.client.get("/static/katex/katex.min.css").close()

        check.assert_not_called()

    def test_chat_requests_still_consume_rate_limit(self):
        with patch.object(wsgi_app.rate_limiter, "check") as check:
            self.client.post(
                "/demo/api/chat",
                json={"message": "x"},
            )

        check.assert_called_once()

    def test_missing_route_returns_json_404(self):
        response = self.client.get("/not-found")

        self.assertEqual(404, response.status_code)
        self.assertIn("not found", response.get_json()["detail"].lower())

    def test_demo_calculates_derivative(self):
        response = self.client.post(
            "/demo/api/verify",
            json={"expression": "x^2", "variable": "x", "candidate": "2x"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("2*x", payload["derivative"])
        self.assertIs(True, payload["is_correct"])

    def test_demo_calculates_definite_integral(self):
        response = self.client.post(
            "/demo/api/integrate",
            json={
                "expression": "x^2",
                "variable": "x",
                "lower": "0",
                "upper": "1",
                "candidate": "1/3",
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("1/3", payload["integral"])
        self.assertIs(True, payload["is_correct"])

    def test_demo_calculates_limit(self):
        response = self.client.post(
            "/demo/api/limit",
            json={
                "expression": "sin(x)/x",
                "variable": "x",
                "point": "0",
                "candidate": "1",
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("1", payload["limit"])
        self.assertIs(True, payload["is_correct"])

    def test_demo_chat_calculates_derivative(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "求导 x^2"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("ok", payload["status"])
        self.assertEqual("verify", payload["intent"])
        self.assertEqual("2*x", payload["calculation"]["derivative"])
        self.assertIsNone(payload["calculation"]["is_correct"])
        self.assertIn(r"\frac{d}{dx}", payload["formula_latex"])

    def test_demo_chat_checks_derivative_candidate(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "判断 2x 是不是 x^2 的导数"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("verify", payload["intent"])
        self.assertIs(True, payload["calculation"]["is_correct"])
        self.assertIn("答案正确", payload["reply"])

    def test_demo_chat_calculates_indefinite_integral(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "积分 x^2"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("integrate", payload["intent"])
        self.assertEqual("x**3/3", payload["calculation"]["integral"])
        self.assertIn("+C", payload["formula_latex"])

    def test_demo_chat_calculates_definite_integral(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "积分 0 到 1 x^2"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("integrate", payload["intent"])
        self.assertEqual("1/3", payload["calculation"]["integral"])
        self.assertIn(r"\int_{0}^{1}", payload["formula_latex"])

    def test_demo_chat_calculates_limit(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "lim x→0 sin(x)/x"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("limit", payload["intent"])
        self.assertEqual("1", payload["calculation"]["limit"])
        self.assertIn(r"\lim_{x\to 0}", payload["formula_latex"])

    def test_demo_chat_calculates_one_sided_limit(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "求 x趋近于0时 1/x 的右极限"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("limit", payload["intent"])
        self.assertEqual("1/x", payload["calculation"]["expression"])
        self.assertEqual("+", payload["calculation"]["direction"])
        self.assertEqual("oo", payload["calculation"]["limit"])

    def test_demo_chat_requests_missing_information(self):
        response = self.client.post(
            "/demo/api/chat",
            json={"message": "今天天气怎么样"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("needs_input", payload["status"])
        self.assertEqual("unknown", payload["intent"])
        self.assertIsNone(payload["calculation"])

    def test_demo_remains_public_when_api_key_is_enabled(self):
        with patch.object(wsgi_app, "API_KEY", "test-secret"):
            page = self.client.get("/demo")
            demo_api = self.client.post(
                "/demo/api/verify",
                json={"expression": "x^2", "variable": "x"},
            )
            chat_api = self.client.post(
                "/demo/api/chat",
                json={"message": "求导 x^2"},
            )
            protected_api = self.client.post(
                "/verify",
                json={"expression": "x^2", "variable": "x"},
            )

        self.assertEqual(200, page.status_code)
        self.assertEqual(200, demo_api.status_code)
        self.assertEqual(200, chat_api.status_code)
        self.assertEqual(401, protected_api.status_code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
