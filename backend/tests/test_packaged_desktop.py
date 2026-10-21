"""Opt-in proof against the actual EXE, with an isolated data dir and no Python PATH."""

import os
from functools import partial
from pathlib import Path

import pytest
import test_desktop_flow as flow
from desktop_helpers import RunningDesktop

BUNDLE = os.environ.get("ZHITU_TEST_BUNDLE")
pytestmark = pytest.mark.skipif(not BUNDLE, reason="packaged directory not explicitly supplied")


def test_packaged_pdf_reading_practice_restart(tmp_path, monkeypatch):
    folder = Path(BUNDLE)
    factory = partial(
        RunningDesktop,
        executable=folder / "ZhiTuService.exe",
        static=folder / "_internal" / "frontend" / "dist",
    )
    monkeypatch.setattr(flow, "RunningDesktop", factory)
    flow.test_import_read_practice_restart_and_preserve_wrong_book(tmp_path)


def test_packaged_assets_are_present_and_protected(tmp_path):
    folder = Path(BUNDLE)
    service = RunningDesktop(
        tmp_path,
        executable=folder / "ZhiTuService.exe",
        static=folder / "_internal" / "frontend" / "dist",
    )
    try:
        assert service.get("/", authenticated=False).status_code == 403
        assert '<div id="app">' in service.get("/").text
        script = next((folder / "_internal/frontend/dist/assets").glob("index-*.js"))
        asset = service.get("/assets/" + script.name)
        assert asset.status_code == 200 and len(asset.content) > 1000
        assert service.get("/api/v1/auth/login").status_code == 404
    finally:
        service.close()
