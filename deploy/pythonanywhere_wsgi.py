import os
import sys


PROJECT_DIR = "/home/YOUR_USERNAME/gaoshu-agent"
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("LOG_ENABLED", "false")
os.environ.setdefault("CALCULATION_TIMEOUT_SECONDS", "20")
os.environ.setdefault("CALCULATION_WORKERS", "2")

from a2wsgi import ASGIMiddleware
from app.main import app as asgi_app


application = ASGIMiddleware(asgi_app)
