import json
import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


APP_DIR = Path(__file__).resolve().parents[1]
API_KEY = "test-secret-key"


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class SecurityApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        env = os.environ.copy()
        env.update(
            {
                "MATH_API_KEY": API_KEY,
                "RATE_LIMIT_PER_MINUTE": "2",
                "CALCULATION_TIMEOUT_SECONDS": "5",
                "LOG_ENABLED": "false",
            }
        )
        cls.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "flask",
                "--app",
                "deploy.wsgi_app:application",
                "run",
                "--host=127.0.0.1",
                "--port",
                str(cls.port),
                "--no-reload",
            ],
            cwd=APP_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        deadline = time.time() + 15
        while time.time() < deadline:
            if cls.process.poll() is not None:
                output = cls.process.stdout.read() if cls.process.stdout else ""
                raise RuntimeError(f"临时测试服务启动失败：{output}")
            try:
                with urlopen(f"{cls.base_url}/health", timeout=1) as response:
                    if response.status == 200:
                        return
            except (HTTPError, URLError, TimeoutError, OSError):
                time.sleep(0.2)

        raise RuntimeError("临时测试服务未能在 15 秒内启动")

    @classmethod
    def tearDownClass(cls):
        if cls.process.poll() is None:
            cls.process.terminate()
            try:
                cls.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.process.kill()
                cls.process.wait(timeout=5)

    def request(self, path, params, headers=None, expected_status=200):
        url = f"{self.base_url}{path}?{urlencode(params)}"
        request = Request(url, method="POST", headers=headers or {})
        try:
            with urlopen(request, timeout=10) as response:
                status = response.status
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            status = exc.code
            payload = json.loads(exc.read().decode("utf-8"))
        except URLError as exc:
            self.fail(f"无法连接临时测试服务：{exc}")

        self.assertEqual(expected_status, status, payload)
        return payload

    def test_api_key_is_required_when_configured(self):
        params = {"expression": "x^2", "variable": "x", "candidate": "2x"}
        headers = {"X-Forwarded-For": "198.51.100.10"}

        self.request("/verify-query", params, headers, expected_status=401)
        self.request(
            "/verify-query",
            params,
            {**headers, "X-API-Key": "wrong-key"},
            expected_status=401,
        )
        payload = self.request(
            "/verify-query",
            params,
            {**headers, "X-API-Key": API_KEY},
        )
        self.assertIs(True, payload["is_correct"])

    def test_rate_limit_returns_429(self):
        params = {"expression": "x^2", "variable": "x"}
        headers = {
            "X-Forwarded-For": "198.51.100.20",
            "X-API-Key": API_KEY,
        }

        self.request("/verify-query", params, headers)
        self.request("/verify-query", params, headers)
        self.request("/verify-query", params, headers, expected_status=429)


if __name__ == "__main__":
    unittest.main(verbosity=2)
