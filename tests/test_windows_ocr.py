import os
import subprocess
import tempfile
import unittest
from contextlib import suppress
from pathlib import Path
from unittest.mock import patch

from deploy import demo_windows_ocr


class WindowsOcrPowerShellTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.image_path = Path(self.temp_dir.name) / "question.png"
        self.file_descriptor = os.open(os.devnull, os.O_RDONLY)
        self.addCleanup(self.close_file_descriptor)

    def close_file_descriptor(self):
        with suppress(OSError):
            os.close(self.file_descriptor)

    def test_prefers_powershell_7_then_falls_back_to_windows_powershell(self):
        pwsh_failure = subprocess.CompletedProcess(
            args=["pwsh"],
            returncode=1,
            stdout=b"",
            stderr="找不到 WinRT OCR 类型".encode("utf-8"),
        )
        legacy_success = subprocess.CompletedProcess(
            args=["powershell.exe"],
            returncode=0,
            stdout=b"2 + 2",
            stderr=b"",
        )

        with (
            patch.object(demo_windows_ocr, "WINDOWS_OCR_FALLBACK", True),
            patch.object(demo_windows_ocr.sys, "platform", "win32"),
            patch.object(
                demo_windows_ocr,
                "_powershell_candidates",
                return_value=("pwsh", "powershell.exe"),
            ),
            patch.object(
                demo_windows_ocr.tempfile,
                "mkstemp",
                return_value=(self.file_descriptor, str(self.image_path)),
            ),
            patch.object(
                demo_windows_ocr.subprocess,
                "run",
                side_effect=(pwsh_failure, legacy_success),
            ) as run,
        ):
            result = demo_windows_ocr.transcribe_question_image(
                b"image-bytes",
                "image/png",
            )

        self.assertEqual("2 + 2", result)
        self.assertEqual(2, run.call_count)
        self.assertEqual("pwsh", run.call_args_list[0].args[0][0])
        self.assertEqual(
            "powershell.exe",
            run.call_args_list[1].args[0][0],
        )

    def test_keeps_powershell_7_result_without_starting_legacy_shell(self):
        success = subprocess.CompletedProcess(
            args=["pwsh"],
            returncode=0,
            stdout=b"x^2",
            stderr=b"",
        )

        with (
            patch.object(demo_windows_ocr, "WINDOWS_OCR_FALLBACK", True),
            patch.object(demo_windows_ocr.sys, "platform", "win32"),
            patch.object(
                demo_windows_ocr,
                "_powershell_candidates",
                return_value=("pwsh", "powershell.exe"),
            ),
            patch.object(
                demo_windows_ocr.tempfile,
                "mkstemp",
                return_value=(self.file_descriptor, str(self.image_path)),
            ),
            patch.object(
                demo_windows_ocr.subprocess,
                "run",
                return_value=success,
            ) as run,
        ):
            result = demo_windows_ocr.transcribe_question_image(
                b"image-bytes",
                "image/png",
            )

        self.assertEqual("x^2", result)
        run.assert_called_once()
        self.assertEqual("pwsh", run.call_args.args[0][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
