"""Per-data-directory OS lock, with non-secret activation metadata only."""
from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from uuid import uuid4


def show_native_error(message: str) -> None:
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, message, "知途", 0x10)


@dataclass(frozen=True)
class ExistingInstance:
    metadata: dict

    def activate(self) -> bool:
        if os.name != "nt":
            return False
        hwnd, pid = self.metadata.get("hwnd", 0), self.metadata.get("pid", 0)
        if type(hwnd) is not int or type(pid) is not int or hwnd <= 0:
            return False
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        actual = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(actual))
        if not user32.IsWindow(hwnd) or actual.value != pid:
            return False
        user32.ShowWindow(hwnd, 9)
        return bool(user32.SetForegroundWindow(hwnd))


class InstanceLease:
    def __init__(self, directory: Path, stream):
        self.directory, self._stream = directory, stream
        self.launch_id = str(uuid4())

    @classmethod
    def try_acquire(cls, data_dir: Path):
        if not data_dir.is_absolute():
            raise ValueError("数据目录必须是绝对路径")
        data_dir.mkdir(parents=True, exist_ok=True)
        stream = (data_dir / "instance.lock").open("a+b")
        if stream.seek(0, 2) == 0:
            stream.write(b"\0"); stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            stream.close()
            try:
                metadata = json.loads((data_dir / "instance.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                metadata = {}
            return ExistingInstance(metadata)
        return cls(data_dir, stream)

    def publish_window(self, hwnd: int) -> None:
        metadata = dict(schemaVersion=1, pid=os.getpid(), hwnd=hwnd, launchId=self.launch_id)
        temporary = self.directory / f".instance-{self.launch_id}.tmp"
        temporary.write_text(json.dumps(metadata), encoding="utf-8")
        os.replace(temporary, self.directory / "instance.json")

    def close(self):
        if self._stream.closed:
            return
        self._stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
        self._stream.close()
