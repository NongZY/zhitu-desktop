import os
import subprocess
import sys

from app.desktop.instance import ExistingInstance, InstanceLease
from desktop_helpers import BACKEND


def test_second_instance_does_not_acquire_same_data_dir(tmp_path):
    first = InstanceLease.try_acquire(tmp_path)
    assert isinstance(first, InstanceLease)
    try:
        first.publish_window(0)
        second = InstanceLease.try_acquire(tmp_path)
        assert isinstance(second, ExistingInstance)
        assert not second.activate()
        assert "token" not in (tmp_path / "instance.json").read_text()
    finally:
        first.close()
    restarted = InstanceLease.try_acquire(tmp_path)
    assert isinstance(restarted, InstanceLease)
    restarted.close()


def test_os_releases_lock_after_host_crash(tmp_path):
    code = """
from app.desktop.instance import InstanceLease
from pathlib import Path
import os, sys
lease = InstanceLease.try_acquire(Path(sys.argv[1]))
lease.publish_window(0)
os._exit(0)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        cwd=BACKEND,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
        timeout=10,
    )
    assert result.returncode == 0
    lease = InstanceLease.try_acquire(tmp_path)
    assert isinstance(lease, InstanceLease)
    lease.close()
