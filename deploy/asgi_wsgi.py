"""Small, dependency-free ASGI-to-WSGI adapter for PythonAnywhere."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from typing import Any


class ASGIApplication:
    """Adapt a buffered ASGI HTTP application to the WSGI protocol."""

    def __init__(self, app: Callable[..., Any]):
        self.app = app

    def __call__(
        self,
        environ: dict[str, Any],
        start_response: Callable[..., Any],
    ) -> list[bytes]:
        request_body = self._read_request_body(environ)
        response_started = False
        response_status = "500 Internal Server Error"
        response_headers: list[tuple[str, str]] = []
        response_body: list[bytes] = []
        request_body_sent = False

        async def receive() -> dict[str, Any]:
            nonlocal request_body_sent
            if not request_body_sent:
                request_body_sent = True
                return {
                    "type": "http.request",
                    "body": request_body,
                    "more_body": False,
                }
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            nonlocal response_started, response_status, response_headers
            message_type = message["type"]

            if message_type == "http.response.start":
                response_started = True
                response_status = self._status_line(message["status"])
                response_headers = [
                    (
                        name.decode("latin-1"),
                        value.decode("latin-1"),
                    )
                    for name, value in message.get("headers", [])
                ]
                return

            if message_type == "http.response.body":
                response_body.append(message.get("body", b""))
                return

            if message_type == "http.response.trailers":
                return

            raise RuntimeError(f"Unsupported ASGI message type: {message_type}")

        try:
            asyncio.run(self.app(self._build_scope(environ), receive, send))
        except BaseException:
            if response_started:
                raise
            start_response(
                "500 Internal Server Error",
                [("Content-Type", "text/plain; charset=utf-8")],
                sys.exc_info(),
            )
            return [b"Internal Server Error"]

        if not response_started:
            raise RuntimeError("ASGI application did not start an HTTP response")

        start_response(response_status, response_headers)
        return response_body

    @staticmethod
    def _read_request_body(environ: dict[str, Any]) -> bytes:
        try:
            content_length = int(environ.get("CONTENT_LENGTH") or 0)
        except (TypeError, ValueError):
            content_length = 0

        if content_length <= 0:
            return b""

        stream = environ.get("wsgi.input")
        if stream is None:
            return b""
        return stream.read(content_length)

    @classmethod
    def _build_scope(cls, environ: dict[str, Any]) -> dict[str, Any]:
        raw_path = environ.get("PATH_INFO", "").encode("latin-1", errors="replace")
        raw_root_path = environ.get("SCRIPT_NAME", "").encode(
            "latin-1",
            errors="replace",
        )
        headers = cls._build_headers(environ)

        return {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": environ.get("SERVER_PROTOCOL", "HTTP/1.1")
            .split("/", 1)[-1],
            "method": environ.get("REQUEST_METHOD", "GET").upper(),
            "scheme": environ.get("wsgi.url_scheme", "http"),
            "path": raw_path.decode("utf-8", errors="replace"),
            "raw_path": raw_path,
            "query_string": environ.get("QUERY_STRING", "").encode(
                "latin-1",
                errors="replace",
            ),
            "root_path": raw_root_path.decode("utf-8", errors="replace"),
            "headers": headers,
            "client": cls._build_client(environ),
            "server": cls._build_server(environ),
            "state": {},
            "extensions": {},
        }

    @staticmethod
    def _build_headers(environ: dict[str, Any]) -> list[tuple[bytes, bytes]]:
        headers: list[tuple[bytes, bytes]] = []
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                name = key[5:].replace("_", "-").lower()
                headers.append(
                    (
                        name.encode("latin-1"),
                        str(value).encode("latin-1", errors="replace"),
                    )
                )

        if environ.get("CONTENT_TYPE"):
            headers.append(
                (
                    b"content-type",
                    str(environ["CONTENT_TYPE"]).encode(
                        "latin-1",
                        errors="replace",
                    ),
                )
            )
        if environ.get("CONTENT_LENGTH"):
            headers.append(
                (
                    b"content-length",
                    str(environ["CONTENT_LENGTH"]).encode(
                        "latin-1",
                        errors="replace",
                    ),
                )
            )

        return headers

    @staticmethod
    def _build_client(environ: dict[str, Any]) -> tuple[str, int] | None:
        address = environ.get("REMOTE_ADDR")
        if not address:
            return None
        try:
            port = int(environ.get("REMOTE_PORT") or 0)
        except (TypeError, ValueError):
            port = 0
        return address, port

    @staticmethod
    def _build_server(environ: dict[str, Any]) -> tuple[str, int] | None:
        name = environ.get("SERVER_NAME")
        if not name:
            return None
        try:
            port = int(environ.get("SERVER_PORT") or 0)
        except (TypeError, ValueError):
            port = 0
        return name, port

    @staticmethod
    def _status_line(status_code: int) -> str:
        from http import HTTPStatus

        try:
            reason = HTTPStatus(status_code).phrase
        except ValueError:
            reason = "Unknown"
        return f"{status_code} {reason}"
