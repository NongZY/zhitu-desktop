"""Frozen launch must not require a development interpreter or restart the GUI."""

import importlib.util
import sys
from pathlib import Path

import pytest


def test_frozen_service_uses_sibling_program(tmp_path, monkeypatch):
    from app.desktop.host import service_launch

    gui = tmp_path / "知途.exe"
    service = tmp_path / "ZhiTuService.exe"
    service.touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(gui))
    command, cwd = service_launch()
    assert command == [str(service)]
    assert cwd == tmp_path


def test_missing_frozen_service_does_not_fall_back_to_python(tmp_path, monkeypatch):
    from app.desktop.host import service_launch

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "知途.exe"))
    with pytest.raises(RuntimeError, match="程序文件"):
        service_launch()


def test_frozen_launcher_does_not_require_venv(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("test_desktop_entry", root / "run_desktop.py")
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    messages = []
    monkeypatch.setattr(entry, "ROOT", tmp_path)
    monkeypatch.setattr(entry, "_error", messages.append)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert entry.main() == 1
    # Reaching the data-location check proves it passed bootstrap without .venv.
    assert messages == ["未找到 Windows 本地数据目录，已停止启动以保护资料。"]
