"""Local startup must be independent of Docker and of PyCharm's working directory."""

import importlib.util
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


def load_launcher():
    spec = importlib.util.spec_from_file_location("learning_local_launcher", ROOT / "run_local.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_configuration_is_absolute_and_preserves_secret(tmp_path, monkeypatch):
    launcher = load_launcher()
    monkeypatch.setattr(launcher.os, "environ", dict(os.environ))
    monkeypatch.setenv("DATABASE_URL", "postgresql://docker-unavailable/example")
    monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "local-data"
    launcher.prepare_environment(ROOT, data, 8081)
    from os import environ

    assert environ["DATABASE_URL"] == f"sqlite:///{(data / 'learning.db').as_posix()}"
    assert environ["MINIO_ENDPOINT"] == ""
    assert environ["LOCAL_MODE"] == "true"
    assert Path(environ["UPLOAD_DIR"]).is_absolute()
    key = environ["JWT_SECRET_KEY"]
    assert len(key) >= 32
    launcher.prepare_environment(ROOT, data, 8081)
    assert environ["JWT_SECRET_KEY"] == key
    assert not (data / "learning.db").exists()


def test_static_site_supports_refresh_but_does_not_mask_api_errors(tmp_path):
    from app.local_web import mount_local_web

    (tmp_path / "index.html").write_text("<html>Local learning</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    mount_local_web(app, tmp_path)
    with TestClient(app) as client:
        assert client.get("/dashboard").text == "<html>Local learning</html>"
        assert client.get("/results/12").status_code == 200
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/api/v1/health").json() == {"status": "ok"}
        assert client.get("/api/v1/missing").status_code == 404
        assert client.get("/assets/missing.js").status_code == 404
        assert client.post("/dashboard").status_code == 405
        assert client.get("/dashboard").headers["cache-control"] == "no-cache"


def test_missing_frontend_is_clear_error(tmp_path):
    from app.local_web import mount_local_web

    with pytest.raises(RuntimeError, match="前端"):
        mount_local_web(FastAPI(), tmp_path)
