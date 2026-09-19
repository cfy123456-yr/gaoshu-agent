from app.main import app as fastapi_app


class VercelAsgiApp:
    """Normalize Vercel's function path before handing it to FastAPI."""

    async def __call__(self, scope, receive, send):
        if scope.get("type") in {"http", "websocket"}:
            path = scope.get("path", "/")

            if path == "/api/index":
                path = "/"
            elif path.startswith("/api/index/"):
                path = path[len("/api/index") :]
            elif path == "/api":
                path = "/"
            elif path.startswith("/api/"):
                path = path[len("/api") :]

            scope["path"] = path
            scope["raw_path"] = path.encode("utf-8")

        await fastapi_app(scope, receive, send)


app = VercelAsgiApp()
