"""Fresh-process probes: never install desktop settings in the legacy test process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import queue
import threading
import secrets
import httpx

BACKEND = Path(__file__).resolve().parents[1]


class RunningDesktop:
    def __init__(self, folder: Path, static: Path | None = None):
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        if static is None:
            static = folder / "static"
            static.mkdir(exist_ok=True)
            (static / "index.html").write_text("<html>desktop fixture</html>", encoding="utf-8")
        self.token = secrets.token_urlsafe(32)
        env = {**os.environ, "PYTHONPATH": str(BACKEND), "PYTHONIOENCODING": "utf-8"}
        self.process = subprocess.Popen([sys.executable, "-m", "app.desktop.service"],
                                        cwd=BACKEND, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, encoding="utf-8", bufsize=1)
        self.frames = queue.Queue()
        self.errors = []
        def receive():
            for line in self.process.stdout:
                try:
                    self.frames.put(json.loads(line))
                except ValueError:
                    self.frames.put({"type": "bad_stdout", "line": line})
            self.frames.put({"type": "eof"})
        def diagnostics():
            self.errors.extend(self.process.stderr)
        threading.Thread(target=receive, daemon=True).start()
        threading.Thread(target=diagnostics, daemon=True).start()
        self.send(dict(schemaVersion=1, type="start", dataDir=str(folder.resolve()),
                       staticDir=str(static.resolve()), token=self.token))
        self.ready = self.frames.get(timeout=18)
        if self.ready.get("type") != "ready":
            self.close()
            raise AssertionError(f"desktop not ready: {self.ready}, {self.errors}")
        self.origin = self.ready["origin"]

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def control(self, kind):
        self.send(dict(type=kind, request_id="test-request"))
        frame = self.frames.get(timeout=10)
        assert frame.get("request_id") == "test-request", frame
        return frame

    def get(self, path, authenticated=True, **kwargs):
        return self.request("GET", path, authenticated=authenticated, **kwargs)

    def request(self, method, path, authenticated=True, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if authenticated:
            headers.setdefault("X-ZhiTu-Desktop-Token", self.token)
        return httpx.request(method, self.origin + path, headers=headers, timeout=10,
                             trust_env=False, **kwargs)

    def close(self):
        if self.process.poll() is None:
            try:
                self.send(dict(type="shutdown", request_id="test-close"))
                self.process.wait(timeout=7)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            try:
                stream.close()
            except OSError:
                pass


def run_probe(code: str, directory: Path, **env_values: str) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(BACKEND), "PYTHONIOENCODING": "utf-8", **env_values}
    result = subprocess.run([sys.executable, "-c", code], cwd=directory, env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=25)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def probe_profile(local_app_data: Path, *, database_url: str, minio_endpoint: str,
                  llm_api_key: str) -> dict[str, object]:
    local_app_data.mkdir(parents=True, exist_ok=True)
    (local_app_data / ".env").write_bytes(b"\xff\xfe\x81invalid dotenv")
    return run_probe('''
import builtins, io, json, os
from pathlib import Path
from sqlalchemy.engine import make_url
from app.desktop.profile import DesktopProfile, install_profile, resolve_data_dir
reads = []
def monitor(original):
    def opened(file, *args, **kwargs):
        if str(file).endswith('.env'): reads.append(str(file))
        return original(file, *args, **kwargs)
    return opened
builtins.open = monitor(builtins.open)
io.open = monitor(io.open)
profile = DesktopProfile(resolve_data_dir(Path.cwd()), 'http://127.0.0.1:41234', 'sentinel')
install_profile(profile)
from app.config import settings
print(json.dumps(dict(database_file=str(Path(make_url(settings.database_url).database)),
 storage_enabled=bool(settings.minio_endpoint), llm_enabled=bool(settings.llm_api_key or settings.llm_api_url),
 dotenv_read=bool(reads))))
''', local_app_data, DATABASE_URL=database_url, MINIO_ENDPOINT=minio_endpoint,
                     LLM_API_KEY=llm_api_key, REDIS_URL="redis://invalid", DEBUG="true")
