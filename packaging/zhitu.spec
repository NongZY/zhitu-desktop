# Windows onedir package: a GUI host and a hidden, pipe-capable service.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

root = Path(SPECPATH).parent
common = dict(
    pathex=[str(root / "backend")],
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter", "pytest", "ruff"],
    noarchive=False,
)
gui = Analysis(
    [str(root / "run_desktop.py")],
    datas=[(str(root / "frontend" / "dist"), "frontend/dist")],
    hiddenimports=["webview.platforms.winforms", "webview.platforms.edgechromium"],
    **common,
)
service = Analysis(
    [str(root / "run_desktop_service.py")],
    datas=copy_metadata("email-validator"),
    hiddenimports=collect_submodules("uvicorn") + collect_submodules("celery") + ["sqlalchemy.dialects.sqlite"],
    **common,
)
gui_exe = EXE(
    PYZ(gui.pure), gui.scripts, [], exclude_binaries=True,
    name="知途", console=False, debug=False, strip=False, upx=False,
)
service_exe = EXE(
    PYZ(service.pure), service.scripts, [], exclude_binaries=True,
    name="ZhiTuService", console=True, debug=False, strip=False, upx=False,
)
COLLECT(
    gui_exe, service_exe, gui.binaries, gui.datas, service.binaries, service.datas,
    strip=False, upx=False, name="ZhiTu-0.2.0-test.2",
)
