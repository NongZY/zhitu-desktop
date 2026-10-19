"""Serve the built learner UI alongside the API in single-process local mode."""

from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class LocalSite(StaticFiles):
    async def get_response(self, path, scope):
        path = path.replace("\\", "/")
        if path.split("/", 1)[0] in {"api", "docs", "redoc", "openapi.json"}:
            raise HTTPException(404)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("assets/") or Path(path).suffix:
                raise
            response = await super().get_response("index.html", scope)
        if path == "." or path == "index.html" or not Path(path).suffix:
            response.headers["Cache-Control"] = "no-cache"
        return response


def mount_local_web(app: FastAPI, directory: Path) -> None:
    if not (directory / "index.html").is_file():
        raise RuntimeError("前端页面尚未构建，请通过 run_local.py 启动项目")
    app.mount("/", LocalSite(directory=str(directory), html=True), name="local-web")
