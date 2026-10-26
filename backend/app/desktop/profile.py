"""Process-scoped bootstrap contract; safe to import before application settings."""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlsplit


class WorkspaceContext(TypedDict):
    id: str
    ownerId: int
    label: str


class DesktopContext(TypedDict):
    schemaVersion: Literal[1]
    mode: Literal["desktop"]
    apiBaseUrl: str
    version: Literal["0.2.0-dev"]
    workspace: WorkspaceContext


@dataclass(frozen=True)
class DesktopProfile:
    data_dir: Path
    origin: str
    session_token: str = field(repr=False)
    root_dir: Path | None = None

    def __post_init__(self):
        parsed = urlsplit(self.origin)
        if (
            not self.data_dir.is_absolute()
            or parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or not parsed.port
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or self.origin != f"http://127.0.0.1:{parsed.port}"
            or not self.session_token
        ):
            raise ValueError("本地启动配置无效")


_profile: DesktopProfile | None = None


def resolve_data_dir(local_app_data: Path) -> Path:
    if not local_app_data.is_absolute():
        raise ValueError("本地数据目录必须为绝对路径")
    return local_app_data.resolve() / "ZhiTu"


def install_profile(profile: DesktopProfile) -> None:
    global _profile
    if _profile is not None or any(
        name in sys.modules for name in ("app.config", "app.database", "app.models", "app.main")
    ):
        raise RuntimeError("桌面配置必须在导入业务模块前安装，且每个进程只能安装一次")
    _profile = profile


def current_profile() -> DesktopProfile | None:
    return _profile
