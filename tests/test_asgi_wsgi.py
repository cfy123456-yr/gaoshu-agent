import io
import unittest
from wsgiref.util import setup_testing_defaults

from deploy.asgi_wsgi import ASGIApplication


class ASGIWSGITest(unittest.TestCase):
    def test_get_response_is_converted_to_wsgi(self):
        async def app(scope, receive, send):
            self.assertEqual("/health", scope["path"])
            self.assertEqual("token=abc", scope["query_string"].decode())
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b'{"status":"ok"}',
                }
            )

        environ = self._environ("/health", "token=abc")
        result = {}

        def start_response(status, headers, exc_info=None):
            result["status"] = status
            result["headers"] = headers
            return lambda data: None

        body = b"".join(ASGIApplication(app)(environ, start_response))

        self.assertEqual("200 OK", result["status"])
        self.assertEqual(
            [("content-type", "application/json")],
            result["headers"],
        )
        self.assertEqual(b'{"status":"ok"}', body)

    def test_request_body_is_forwarded(self):
        async def app(scope, receive, send):
            message = await receive()
            self.assertEqual(b'{"expression":"x^2"}', message["body"])
            await send(
                {
                    "type": "http.response.start",
                    "status": 201,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b"created"})

        environ = self._environ("/verify", "")
        environ["REQUEST_METHOD"] = "POST"
        environ["CONTENT_TYPE"] = "application/json"
        environ["CONTENT_LENGTH"] = "20"
        environ["wsgi.input"] = io.BytesIO(b'{"expression":"x^2"}')

        status = {}

        def start_response(response_status, headers, exc_info=None):
            status["value"] = response_status
            return lambda data: None

        body = b"".join(ASGIApplication(app)(environ, start_response))

        self.assertEqual("201 Created", status["value"])
        self.assertEqual(b"created", body)

    def test_unhandled_application_error_returns_500(self):
        async def app(scope, receive, send):
            raise RuntimeError("boom")

        environ = self._environ("/health", "")
        status = {}

        def start_response(response_status, headers, exc_info=None):
            status["value"] = response_status
            self.assertIsNotNone(exc_info)
            return lambda data: None

        body = b"".join(ASGIApplication(app)(environ, start_response))

        self.assertEqual("500 Internal Server Error", status["value"])
        self.assertEqual(b"Internal Server Error", body)

    @staticmethod
    def _environ(path, query):
        environ = {}
        setup_testing_defaults(environ)
        environ["REQUEST_METHOD"] = "GET"
        environ["PATH_INFO"] = path
        environ["SCRIPT_NAME"] = ""
        environ["QUERY_STRING"] = query
        return environ


if __name__ == "__main__":
    unittest.main(verbosity=2)
