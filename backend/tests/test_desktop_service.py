import socket
import subprocess
from desktop_helpers import RunningDesktop


def test_ready_status_shutdown_and_eof(tmp_path):
    s = RunningDesktop(tmp_path)
    port = int(s.origin.rsplit(":", 1)[1])
    assert s.ready["context"]["version"] == "0.2.0-dev"
    assert s.control("status")["active_imports"] == 0
    s.process.stdin.close()
    s.process.wait(timeout=7)
    assert s.process.returncode == 0
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) != 0
    s.close()


def test_restart_keeps_owner_but_rotates_secret(tmp_path):
    first = RunningDesktop(tmp_path)
    owner = first.ready["context"]["workspace"]
    old_token = first.token
    first.close()
    second = RunningDesktop(tmp_path)
    try:
        assert second.ready["context"]["workspace"] == owner
        assert second.token != old_token
        assert second.get("/health", headers={"X-ZhiTu-Desktop-Token": old_token}).status_code == 403
    finally:
        second.close()


def test_missing_static_fails_without_secret_disclosure(tmp_path):
    import pytest
    with pytest.raises(AssertionError, match="not ready"):
        RunningDesktop(tmp_path, tmp_path / "missing")
