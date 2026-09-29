import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LauncherTest(unittest.TestCase):
    def read_text(self, relative_path):
        return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    def test_windows_launchers_use_powershell_7(self):
        for name in ("start-demo.cmd", "stop-demo.cmd"):
            with self.subTest(name=name):
                script = self.read_text(Path("scripts") / name)
                self.assertIn("pwsh -NoProfile", script)
                self.assertNotIn("powershell -NoProfile", script)

    def test_start_demo_uses_current_project_work_directory(self):
        script = self.read_text("scripts/start-demo.ps1")

        self.assertIn("$workDir = Join-Path $appDir 'work'", script)
        self.assertNotIn("$projectDir = Split-Path -Parent $appDir", script)

    def test_start_demo_does_not_start_legacy_tunnel(self):
        script = self.read_text("scripts/start-demo.ps1")

        self.assertNotIn("localtunnel", script.lower())
        self.assertIn("Test-UvicornAvailable", script)
        self.assertIn("from deploy.wsgi_app import application", script)
        self.assertIn("https://cfyyy.pythonanywhere.com", script)

    def test_stop_demo_only_manages_the_local_service(self):
        script = self.read_text("scripts/stop-demo.ps1")

        self.assertNotIn("tunnel", script.lower())
        self.assertIn("127\\.0\\.0\\.1:8000", script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
