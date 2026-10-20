from pathlib import Path
import socket
import subprocess
import sys
import pytest
import httpx

from app.desktop.host import DesktopHost


def test_host_owns_real_service_and_releases_port(tmp_path):
    static = tmp_path / "ui"
    static.mkdir()
    (static / "index.html").write_text("desktop", encoding="utf-8")
    host = DesktopHost()
    context = host.start(tmp_path / "data", static)
    origin = context["apiBaseUrl"].removesuffix("/api/v1")
    assert host.status()["active_imports"] == 0
    request = type("Request", (), {"url": origin + "/health", "headers": {}, "method": "GET"})()
    host.authorize_request(request)
    assert httpx.get(request.url, headers=request.headers, trust_env=False).status_code == 200
    assert "token" not in str(context).lower()
    report = host.stop()
    assert report.exited and report.status == "graceful"
    assert host.stop().exited
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", int(origin.rsplit(":", 1)[1]))) != 0


def test_start_error_and_timeout_clean_up_only_owned_process(tmp_path, monkeypatch):
    from app.desktop import host as module
    real_popen = subprocess.Popen
    unrelated = real_popen([sys.executable, "-c", "import time; time.sleep(30)"])
    def stuck(*args, **kwargs):
        return real_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
    monkeypatch.setattr(module.subprocess, "Popen", stuck)
    host = DesktopHost(startup_timeout=.05)
    try:
        with pytest.raises(RuntimeError):
            host.start(tmp_path, tmp_path)
        assert host.stop(.05).exited
        assert host.stop(.05).status == "forced"
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=3)


def test_failed_static_start_exits_instead_of_orphaning(tmp_path):
    host = DesktopHost()
    with pytest.raises(RuntimeError):
        host.start(tmp_path / "data", tmp_path / "missing")
    assert host.stop().exited


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows Job Object proof')
def test_host_crash_closes_job_and_service(tmp_path):
    import json
    import time
    static = tmp_path / 'ui'
    static.mkdir()
    (static / 'index.html').write_text('desktop')
    code = '''
from app.desktop.host import DesktopHost
from pathlib import Path
import json, os, sys
h = DesktopHost()
c = h.start(Path(sys.argv[1]), Path(sys.argv[2]))
print(json.dumps(c), flush=True)
os._exit(0)
'''
    result = subprocess.run([sys.executable, '-I', '-c', code, str(tmp_path / 'data'), str(static)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    port = int(json.loads(result.stdout)['apiBaseUrl'].split(':')[2].split('/')[0])
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) != 0:
                return
        time.sleep(.05)
    pytest.fail('owned service survived host crash')
