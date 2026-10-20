"""知途应用版开发启动入口。不会启动浏览器、Docker、npm 或下载依赖。"""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def _error(message):
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "知途", 0x10)
    else:
        print(message, file=sys.stderr)


def main() -> int:
    if os.name != "nt":
        _error("目前开发版仅支持 Windows 10/11 x64。")
        return 1
    python = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        _error("缺少应用版独立开发环境。请按 docs/DESKTOP_D1.md 准备；此版本还不是安装包。")
        return 1
    if Path(sys.executable).resolve() != python.resolve():
        return subprocess.call([str(python), str(Path(__file__).resolve())], cwd=ROOT)
    sys.path.insert(0, str(ROOT / "backend"))
    from app.desktop.profile import resolve_data_dir
    from app.desktop.instance import InstanceLease, ExistingInstance
    from app.desktop.host import DesktopHost
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        _error("未找到 Windows 本地数据目录，已停止启动以保护资料。")
        return 1
    host, lease = DesktopHost(), None
    try:
        lease = InstanceLease.try_acquire(resolve_data_dir(Path(local)))
        if isinstance(lease, ExistingInstance):
            if not lease.activate():
                _error("知途已经在运行或正在启动，请稍等并查看任务栏。")
            return 0
        host.start(resolve_data_dir(Path(local)), ROOT / "frontend" / "dist")
        import webview
        from app.desktop.window import create_desktop_window
        create_desktop_window(host, lease)
        webview.start(gui="edgechromium", private_mode=True, debug=False)
        return 0
    except Exception:
        _error("知途启动失败。请确认已构建应用版界面、安装桌面依赖及 WebView2。学习数据不会删除。")
        return 1
    finally:
        host.stop()
        if isinstance(lease, InstanceLease):
            lease.close()


if __name__ == "__main__":
    raise SystemExit(main())
