"""Fetch a public image URL for OCR without exposing private network targets."""

from __future__ import annotations

import ipaddress
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)

from deploy.demo_vision import MAX_IMAGE_BYTES, image_matches_type


MAX_IMAGE_URL_CHARS = 2048
MAX_REDIRECTS = 3
REMOTE_IMAGE_TIMEOUT_SECONDS = 12.0
_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_PORTS = {80, 443}


class RemoteImageError(RuntimeError):
    """Raised when a remote image cannot be fetched safely."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def validate_remote_image_url(url: str) -> str:
    """Validate an image URL and reject private or non-image network targets."""

    value = str(url or "").strip()
    if not value:
        raise RemoteImageError("缺少 image_url 参数。")
    if len(value) > MAX_IMAGE_URL_CHARS:
        raise RemoteImageError("图片链接过长，请使用不超过 2048 个字符的链接。")

    parsed = urlsplit(value)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise RemoteImageError("图片链接仅支持 HTTP 或 HTTPS。")
    if parsed.username or parsed.password:
        raise RemoteImageError("图片链接不能包含用户名或密码。")

    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise RemoteImageError("图片链接缺少有效域名。")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(
        ".localhost"
    ):
        raise RemoteImageError("图片链接不能指向本机地址。")

    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise RemoteImageError("图片链接端口无效。") from exc
    if port not in _ALLOWED_PORTS:
        raise RemoteImageError("图片链接仅允许使用 80 或 443 端口。")

    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise RemoteImageError("图片链接域名无效。") from exc

    try:
        addresses = [ipaddress.ip_address(ascii_hostname)]
    except ValueError:
        try:
            records = socket.getaddrinfo(
                ascii_hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise RemoteImageError("图片链接域名无法解析。") from exc
        addresses = []
        for record in records:
            try:
                addresses.append(ipaddress.ip_address(record[4][0]))
            except (IndexError, TypeError, ValueError):
                continue
        if not addresses:
            raise RemoteImageError("图片链接域名没有可用地址。")

    if any(not address.is_global for address in addresses):
        raise RemoteImageError("图片链接不能指向本机、内网或保留地址。")
    return parsed.geturl()


class _ValidatingRedirectHandler(HTTPRedirectHandler):
    def __init__(self) -> None:
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirect_count += 1
        if self.redirect_count > MAX_REDIRECTS:
            raise RemoteImageError("图片链接重定向次数过多。")
        target = urljoin(req.full_url, newurl)
        validate_remote_image_url(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


def fetch_remote_image(
    url: str,
    *,
    timeout_seconds: float | None = None,
) -> tuple[bytes, str]:
    """Download a bounded public image and return its verified bytes and MIME type."""

    validated_url = validate_remote_image_url(url)
    request_timeout = REMOTE_IMAGE_TIMEOUT_SECONDS
    if timeout_seconds is not None:
        request_timeout = max(
            0.1,
            min(REMOTE_IMAGE_TIMEOUT_SECONDS, float(timeout_seconds)),
        )
    redirect_handler = _ValidatingRedirectHandler()
    opener = build_opener(redirect_handler)
    request = Request(
        validated_url,
        headers={
            "Accept": "image/png,image/jpeg,image/webp,image/gif",
            "User-Agent": "zhiwei-math-ocr/1.0",
        },
        method="GET",
    )

    try:
        with opener.open(
            request,
            timeout=request_timeout,
        ) as response:
            content_type = (response.headers.get("Content-Type") or "").lower()
            content_type = content_type.split(";", 1)[0].strip()
            if not content_type.startswith("image/"):
                raise RemoteImageError("图片链接返回的内容不是图片。")

            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > MAX_IMAGE_BYTES:
                        raise RemoteImageError(
                            "图片不能超过 6 MB，请压缩后重试。",
                            status_code=413,
                        )
                except ValueError:
                    pass

            image_data = response.read(MAX_IMAGE_BYTES + 1)
    except RemoteImageError:
        raise
    except HTTPError as exc:
        if exc.code in {401, 403, 404}:
            raise RemoteImageError(
                "图片链接无法访问或已过期，请重新上传图片。",
                status_code=400,
            ) from exc
        raise RemoteImageError(
            f"图片下载失败（HTTP {exc.code}），请稍后重试。",
            status_code=502,
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RemoteImageError(
            "暂时无法下载图片，请稍后重试。",
            status_code=502,
        ) from exc

    if len(image_data) > MAX_IMAGE_BYTES:
        raise RemoteImageError(
            "图片不能超过 6 MB，请压缩后重试。",
            status_code=413,
        )
    if not image_matches_type(image_data, content_type):
        raise RemoteImageError("图片内容与文件类型不一致，请重新上传。")
    return image_data, content_type
