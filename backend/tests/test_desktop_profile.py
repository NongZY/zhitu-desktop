from pathlib import Path
import pytest
from desktop_helpers import probe_profile, run_probe


def test_desktop_ignores_process_env_and_dotenv(tmp_path):
    report = probe_profile(tmp_path, database_url="postgresql://invalid/private",
                           minio_endpoint="invalid:9000", llm_api_key="sentinel")
    assert report == {"database_file": str(tmp_path / "ZhiTu" / "learning.db"),
                      "storage_enabled": False, "llm_enabled": False, "dotenv_read": False}


@pytest.mark.parametrize("first", ["import app.config", "import app.database", ""])
def test_profile_rejects_late_or_second_install(tmp_path, first):
    report = run_probe('''
import json
from pathlib import Path
from app.desktop.profile import DesktopProfile, install_profile
''' + first + '''
p = DesktopProfile(Path.cwd(), 'http://127.0.0.1:41234', 'hidden-token')
try:
    install_profile(p)
    install_profile(p)
except RuntimeError:
    print(json.dumps({'rejected': True, 'repr': repr(p)}))
''', tmp_path)
    assert report["rejected"] is True
    assert "hidden-token" not in report["repr"]
