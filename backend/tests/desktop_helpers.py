"""Fresh-process probes: never install desktop settings in the legacy test process."""
import json
import os
from pathlib import Path
import subprocess
import sys

BACKEND = Path(__file__).resolve().parents[1]


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
