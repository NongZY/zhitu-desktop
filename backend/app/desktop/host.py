"""Own exactly one sidecar. Its capability travels only through anonymous stdin."""

import ctypes
import json
import os
import queue
import secrets
import subprocess
import sys
import threading
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from app.desktop.profile import DesktopContext


def service_launch() -> tuple[list[str], Path]:
    if getattr(sys, "frozen", False):
        folder = Path(sys.executable).resolve().parent
        service = folder / "ZhiTuService.exe"
        if not service.is_file():
            raise RuntimeError("本地服务程序文件缺失，请重新解压完整测试包或重新安装")
        return [str(service)], folder
    return [sys.executable, "-I", "-m", "app.desktop.service"], Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ShutdownReport:
    status: Literal["graceful", "forced"]
    child_pid: int
    exited: bool


class _WindowsJob:
    """KILL_ON_JOB_CLOSE keeps descendants bound to this host's lifetime."""

    def __init__(self, process):
        self.handle = None
        if os.name != "nt":
            return

        class Basic(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class Counters(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            ]

        class Limits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", Basic),
                ("IoInfo", Counters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        limits = Limits()
        limits.BasicLimitInformation.LimitFlags = 0x2000
        if (
            not self.handle
            or not self.kernel.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            )
            or not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle))
        ):
            self.close()
            raise RuntimeError("无法保护本地服务进程，已停止启动")

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class DesktopHost:
    def __init__(self, startup_timeout: float = 15):
        self.startup_timeout = startup_timeout
        self._process = None
        self._job = None
        self._context = None
        self._token = secrets.token_urlsafe(32)
        self._frames = queue.Queue()
        self._lock = threading.RLock()
        self._last_report = ShutdownReport("graceful", 0, True)

    @property
    def context(self) -> DesktopContext:
        if self._context is None:
            raise RuntimeError("本地服务尚未就绪")
        return self._context

    def _send(self, frame):
        self._process.stdin.write(json.dumps(frame) + "\n")
        self._process.stdin.flush()

    def start(self, data_dir: Path, static_dir: Path) -> DesktopContext:
        if self._process is not None:
            raise RuntimeError("本地服务已启动")
        self.data_dir = data_dir.resolve()
        command, working_dir = service_launch()
        # -I ignores Python injection variables; desktop Settings separately excludes all external config.
        self._process = subprocess.Popen(
            command,
            cwd=working_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            self._job = _WindowsJob(self._process)

            def receive():
                try:
                    for line in self._process.stdout:
                        try:
                            self._frames.put(json.loads(line))
                        except ValueError:
                            self._frames.put({"type": "error"})
                finally:
                    self._frames.put({"type": "eof"})

            def drain_errors():
                # Drain without recording potentially sensitive library diagnostics.
                for _ in self._process.stderr:
                    pass

            threading.Thread(target=receive, daemon=True, name="desktop-protocol").start()
            threading.Thread(target=drain_errors, daemon=True, name="desktop-diagnostics").start()
            self._send(
                dict(
                    type="start",
                    schemaVersion=1,
                    dataDir=str(data_dir.resolve()),
                    staticDir=str(static_dir.resolve()),
                    token=self._token,
                )
            )
            frame = self._frames.get(timeout=self.startup_timeout)
            if frame.get("type") != "ready":
                raise RuntimeError("本地服务无法启动，请检查数据目录和软件界面文件")
            self._context = frame["context"]
            return self.context
        except Exception as exc:
            self.stop(0.2)
            raise RuntimeError("本地服务未能就绪，请保留数据并重新启动软件") from exc

    def status(self) -> dict:
        with self._lock:
            request_id = str(uuid4())
            try:
                self._send(dict(type="status", request_id=request_id))
                frame = self._frames.get(timeout=2)
                if frame.get("type") != "status" or frame.get("request_id") != request_id:
                    raise RuntimeError()
                return frame
            except Exception as exc:
                raise RuntimeError("本地服务连接已中断") from exc

    def authorize_request(self, request) -> None:
        from app.desktop.window import inject_desktop_header

        inject_desktop_header(
            request, self.context["apiBaseUrl"].removesuffix("/api/v1"), self._token
        )

    def stop(self, timeout_seconds: float = 5) -> ShutdownReport:
        with self._lock:
            process = self._process
            if process is None:
                return self._last_report
            if process.poll() is not None and self._last_report.child_pid == process.pid:
                return self._last_report
            status = "graceful"
            try:
                if process.poll() is None:
                    try:
                        self._send(dict(type="shutdown", request_id=str(uuid4())))
                    except (OSError, ValueError):
                        pass
                    try:
                        process.wait(timeout=timeout_seconds)
                    except subprocess.TimeoutExpired:
                        status = "forced"
                        # Popen retains the OS handle; never look up or kill a stale PID.
                        process.kill()
                        process.wait(timeout=2)
            finally:
                if self._job is not None:
                    self._job.close()
                self._last_report = ShutdownReport(status, process.pid, process.poll() is not None)
                for stream in (process.stdin, process.stdout, process.stderr):
                    try:
                        stream.close()
                    except OSError:
                        pass
            return self._last_report
