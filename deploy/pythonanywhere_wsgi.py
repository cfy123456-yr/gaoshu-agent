import os
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_PATH = Path.home() / "gaoshu-agent"
PROJECT_DIR = str(PROJECT_PATH)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

load_dotenv(PROJECT_PATH / ".env", override=True)

os.environ.setdefault("LOG_ENABLED", "false")
os.environ.setdefault("CALCULATION_TIMEOUT_SECONDS", "20")
os.environ.setdefault("CALCULATION_WORKERS", "2")

from deploy.wsgi_app import application

