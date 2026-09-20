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
        self.assertIn("知微高数计算演示", html)
        self.assertIn("/demo/api/verify", html)
        self.assertIn("/demo/api/integrate", html)
        self.assertIn("/demo/api/limit", html)

    def test_demo_health_is_available(self):
        response = self.client.get("/demo/api/health")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("ok", payload["status"])
        self.assertTrue(payload["demo"]["available"])
        self.assertEqual("/demo", payload["demo"]["page"])

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

    def test_demo_remains_public_when_api_key_is_enabled(self):
        with patch.object(wsgi_app, "API_KEY", "test-secret"):
            page = self.client.get("/demo")
            demo_api = self.client.post(
                "/demo/api/verify",
                json={"expression": "x^2", "variable": "x"},
            )
            protected_api = self.client.post(
                "/verify",
                json={"expression": "x^2", "variable": "x"},
            )

        self.assertEqual(200, page.status_code)
        self.assertEqual(200, demo_api.status_code)
        self.assertEqual(401, protected_api.status_code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
