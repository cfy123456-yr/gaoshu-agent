"""Windows built-in OCR fallback for the local math demo."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

WINDOWS_OCR_FALLBACK = os.getenv(
    "WINDOWS_OCR_FALLBACK",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}
WINDOWS_OCR_TIMEOUT_SECONDS = max(
    5.0,
    min(90.0, float(os.getenv("WINDOWS_OCR_TIMEOUT_SECONDS", "30") or 30)),
)

_HELPER_PATH = Path(__file__).resolve().with_name("windows_ocr.ps1")
_IMAGE_SUFFIXES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


class WindowsOcrUnavailable(RuntimeError):
    """Raised when the local Windows OCR fallback is not available."""


class WindowsOcrError(RuntimeError):
    """Raised when Windows OCR cannot return a usable transcription."""


def windows_ocr_available() -> bool:
    """Return whether the current machine can use Windows OCR."""
    return (
        WINDOWS_OCR_FALLBACK
        and sys.platform == "win32"
        and _HELPER_PATH.is_file()
        and shutil.which("powershell.exe") is not None
    )


def transcribe_question_image(data: bytes, mime_type: str) -> str:
    """Transcribe a math question image with the Windows OCR engine."""
    if not windows_ocr_available():
        raise WindowsOcrUnavailable("本机离线 OCR 未启用。")

    suffix = _IMAGE_SUFFIXES.get(mime_type, ".png")
    file_descriptor, image_path = tempfile.mkstemp(
        prefix="gaoshu-windows-ocr-",
        suffix=suffix,
    )
    os.close(file_descriptor)

    try:
        Path(image_path).write_bytes(data)
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(_HELPER_PATH),
                "-ImagePath",
                image_path,
            ],
            check=False,
            capture_output=True,
            timeout=WINDOWS_OCR_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise WindowsOcrError("本机离线识别超时，请压缩图片后重试。") from exc
    except OSError as exc:
        raise WindowsOcrError("无法启动本机离线识别服务。") from exc
    finally:
        try:
            Path(image_path).unlink(missing_ok=True)
        except OSError:
            pass

    stdout = completed.stdout.decode("utf-8", errors="replace").strip()
    stderr = completed.stderr.decode("utf-8", errors="replace").strip()
    if stdout == "__NO_OCR_ENGINE__":
        raise WindowsOcrUnavailable("系统未安装可用的 OCR 语言组件。")
    if completed.returncode != 0:
        detail = re.sub(r"\s+", " ", stderr).strip()[:200]
        suffix = f"：{detail}" if detail else ""
        raise WindowsOcrError(f"本机离线识别失败{suffix}")

    text = _normalize_ocr_text(stdout)
    if not text:
        raise WindowsOcrError("本机离线识别没有提取到可用文字。")
    return text[:2000]


def _normalize_ocr_text(value: str) -> str:
    text = (
        value.replace("\x00", "")
        .replace("\ufeff", "")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        line = re.sub(
            r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])",
            "",
            line,
        )
        line = re.sub(r"\s+([，。！？；：、）】》」』])", r"\1", line)
        line = re.sub(r"([（【《「『])\s+", r"\1", line)
        if line:
            lines.append(line)
    return "\n".join(lines).strip()
