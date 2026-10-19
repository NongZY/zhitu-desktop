"""在 PyCharm 中右键运行此文件：不使用 Docker、Redis 或独立数据库服务。"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def prepare_environment(root: Path, data: Path, port: int) -> None:
    data = data.resolve()
    data.mkdir(parents=True, exist_ok=True)
    key_path = data / "jwt-secret.key"
    try:
        with key_path.open("x", encoding="utf-8") as key_file:
            key_file.write(secrets.token_urlsafe(48))
    except FileExistsError:
        pass
    key = key_path.read_text(encoding="utf-8").strip()
    if len(key) < 32:
        raise RuntimeError("本地登录密钥文件不完整，请先备份并检查 data/local/jwt-secret.key")
    os.environ.update({
        "LOCAL_MODE": "true",
        "DATABASE_URL": f"sqlite:///{(data / 'learning.db').as_posix()}",
        "UPLOAD_DIR": str(data / "uploads"),
        "JWT_SECRET_KEY": key,
        "MINIO_ENDPOINT": "", "MINIO_ACCESS_KEY": "", "MINIO_SECRET_KEY": "",
        "REDIS_URL": "memory://",
        "CELERY_BROKER_URL": "memory://",
        "CELERY_RESULT_BACKEND": "cache+memory://",
        "CELERY_TASK_ALWAYS_EAGER": "true",
        "CORS_ORIGINS": f"http://127.0.0.1:{port},http://localhost:{port}",
    })


def ensure_frontend(force: bool = False) -> Path:
    frontend = ROOT / "frontend"
    output = frontend / "dist"
    index = output / "index.html"
    sources = list((frontend / "src").rglob("*")) + [
        frontend / "package-lock.json", frontend / "vite.config.ts", frontend / "index.html",
    ]
    stale = not index.is_file() or any(
        path.is_file() and path.stat().st_mtime > index.stat().st_mtime for path in sources
    )
    if force or stale:
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if not npm:
            raise RuntimeError("需要构建网页，但未找到 Node.js。请安装 Node.js 后重新打开 PyCharm。")
        if not (frontend / "node_modules").is_dir():
            raise RuntimeError("尚未安装网页依赖。请先按 docs/LOCAL_RUN.md 完成首次配置。")
        print("正在更新网页，首次启动需要稍等……", flush=True)
        env = dict(os.environ, VITE_API_BASE_URL="/api/v1")
        subprocess.run([npm, "run", "build"], cwd=frontend, env=env, check=True)
    return output


def open_when_ready(url: str) -> None:
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"{url}/api/v1/health", timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            time.sleep(0.3)


def main() -> int:
    # Right-click Run also works when PyCharm still has another project's SDK selected.
    python = ROOT / "backend" / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if python.is_file() and Path(sys.executable).resolve() != python.resolve():
        return subprocess.call([str(python), str(Path(__file__).resolve()), *sys.argv[1:]])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise RuntimeError("网页端口须在 1024 至 65535 之间")
    if args.check:
        import fastapi  # noqa: F401
        import pymupdf  # noqa: F401
        import sqlalchemy  # noqa: F401
        import uvicorn  # noqa: F401
        print(f"Python 环境正常：{sys.executable}\n启动文件：{ROOT / 'run_local.py'}")
        return 0
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", args.port))
        except OSError as exc:
            raise RuntimeError(f"端口 {args.port} 已被占用。若项目已启动，请直接打开网页；否则选择其他端口。") from exc
    frontend = ensure_frontend(args.build)
    prepare_environment(ROOT, ROOT / "data" / "local", args.port)
    # Read optional AI settings from backend/.env, never depend on PyCharm's working directory.
    os.chdir(ROOT / "backend")
    sys.path.insert(0, str(ROOT / "backend"))
    import uvicorn

    from app.local_web import mount_local_web
    from app.main import app

    mount_local_web(app, frontend)
    url = f"http://127.0.0.1:{args.port}"
    print(f"\n学习系统：{url}\n数据目录：{ROOT / 'data' / 'local'}\n停止时请点击 PyCharm 的停止按钮。\n", flush=True)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ImportError, subprocess.CalledProcessError) as exc:
        print(f"\n启动未完成：{exc}\n请参阅 docs/LOCAL_RUN.md。", file=sys.stderr)
        raise SystemExit(1) from None
