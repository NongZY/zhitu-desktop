"""Capability boundary for every loopback HTTP request, including static assets."""

import hmac
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.desktop.profile import DesktopProfile, current_profile

TOKEN_HEADER = "X-ZhiTu-Desktop-Token"
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' blob: data:; font-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


class DesktopBoundary:
    def __init__(self, app, profile: DesktopProfile):
        self.app, self.profile = app, profile

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            await self.app(scope, receive, send)
            return

        def values(name):
            return [v.decode("latin1") for k, v in scope["headers"] if k.lower() == name]

        tokens, hosts, origins = (
            values(b"x-zhitu-desktop-token"),
            values(b"host"),
            values(b"origin"),
        )
        valid = (
            len(tokens) == 1
            and hmac.compare_digest(tokens[0], self.profile.session_token)
            and hosts == [urlsplit(self.profile.origin).netloc]
            and (not origins or origins == [self.profile.origin])
        )
        if not valid:
            await JSONResponse({"detail": "本地连接无效，请重新启动软件"}, status_code=403)(
                scope, receive, send
            )
            return

        root = self.profile.root_dir or self.profile.data_dir
        if (scope['method'] not in {'GET', 'HEAD', 'OPTIONS'} and
            not scope['path'].startswith('/api/v1/maintenance/') and
            (root / 'pending-space.json').exists()):
            await JSONResponse({'detail': '已安排恢复资料，请重启软件；也可以在设置中取消恢复后继续学习'}, status_code=409)(scope, receive, send)
            return

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend(
                    [
                        (b"content-security-policy", CSP.encode()),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"cache-control", b"no-store"),
                    ]
                )
            await send(message)

        await self.app(scope, receive, secure_send)


def configure_desktop_security(application: FastAPI, profile: DesktopProfile) -> None:
    if current_profile() is not profile:
        raise RuntimeError("桌面配置未在此进程正确安装")
    from app.database import get_db
    from app.models import User
    from app.security import get_current_user

    def get_desktop_user(request: Request, db: Session = Depends(get_db)) -> User:
        identity = request.app.state.workspace
        user = db.get(User, identity.owner_id)
        if user is None or not user.is_active:
            raise HTTPException(503, "本地学习空间不可用，请保留数据并重启软件")
        return user

    application.dependency_overrides[get_current_user] = get_desktop_user
    application.add_middleware(DesktopBoundary, profile=profile)


def create_desktop_app(profile: DesktopProfile) -> FastAPI:
    if current_profile() is not profile:
        raise RuntimeError("桌面配置未在此进程正确安装")
    from app.main import create_app

    return create_app(desktop_profile=profile)


def mount_desktop_static(application: FastAPI, directory: Path) -> None:
    root = directory.resolve(strict=True)
    if not (root / "index.html").is_file():
        raise RuntimeError("缺少软件界面，请先构建应用版前端")

    @application.get("/{asset_path:path}", include_in_schema=False)
    def asset(asset_path: str):
        if asset_path.startswith("api/") or asset_path in {"docs", "redoc", "openapi.json"}:
            raise HTTPException(404)
        target = (root / asset_path).resolve()
        if not target.is_relative_to(root) or ".." in Path(asset_path).parts:
            raise HTTPException(404)
        if target.is_file():
            return FileResponse(target)
        if not Path(asset_path).suffix:
            return FileResponse(root / "index.html")
        raise HTTPException(404)
