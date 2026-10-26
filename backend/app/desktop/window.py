"""EdgeChromium boundary and the two-method, non-secret desktop bridge."""

import copy
import json
import threading
import time
import webbrowser
from collections.abc import MutableMapping
from types import SimpleNamespace
from typing import Literal, Protocol
from urllib.parse import urlsplit
from uuid import uuid4


class NativeRequest(Protocol):
    url: str
    method: str
    headers: MutableMapping[str, str]


def _same_origin(uri: str, origin: str) -> bool:
    try:
        parsed, trusted = urlsplit(uri), urlsplit(origin)
        return (
            parsed.scheme == "http"
            and parsed.netloc == trusted.netloc
            and trusted.hostname == "127.0.0.1"
            and parsed.hostname == "127.0.0.1"
            and not parsed.username
            and not parsed.password
            and parsed.port == trusted.port
        )
    except ValueError:
        return False


def inject_desktop_header(request: NativeRequest, origin: str, token: str) -> None:
    # Remove credentials inherited by a redirect before deciding whether to add ours.
    for name in list(request.headers):
        if name.lower() == "x-zhitu-desktop-token":
            del request.headers[name]
    if _same_origin(request.url, origin):
        request.headers["X-ZhiTu-Desktop-Token"] = token


def handle_navigation(
    uri: str, is_user_initiated: bool, *, origin: str
) -> Literal["allow", "external", "deny"]:
    if _same_origin(uri, origin):
        return "allow"
    try:
        parsed = urlsplit(uri)
        if (
            is_user_initiated
            and parsed.scheme in {"http", "https"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
        ):
            return "external"
    except ValueError:
        pass
    return "deny"


class DesktopBridge:
    def __init__(self, host):
        self._host, self._window, self._closer = host, None, None

    def _attach(self, window, closer):
        self._window, self._closer = window, closer

    def _check_origin(self):
        origin = self._host.context["apiBaseUrl"].removesuffix("/api/v1")
        if self._window is None or not _same_origin(str(self._window.get_current_url()), origin):
            raise RuntimeError("本地连接无效")

    def get_context(self):
        self._check_origin()
        return copy.deepcopy(self._host.context)

    def respond_close(self, request_id: str, decision: str):
        self._check_origin()
        self._closer.respond_close(request_id, decision)

    def open_data_dir(self):
        self._check_origin()
        import os
        os.startfile(str(self._host.data_dir))
        return {'opened': True}

    def export_backup(self, backup_id: str):
        self._check_origin()
        from app.desktop.maintenance import identifier, MAX_ARCHIVE
        from pathlib import Path
        import os
        import httpx
        import webview
        uid = identifier(backup_id)
        chosen = self._window.create_file_dialog(webview.FileDialog.SAVE,
            save_filename=f'知途备份-{uid[:8]}.zip', file_types=('知途备份 (*.zip)',))
        if not chosen:
            return {'saved': False}
        self._check_origin()
        path = Path(chosen[0] if isinstance(chosen, (tuple, list)) else chosen)
        temporary = path.with_name(path.name + '.' + uuid4().hex + '.part')
        request = SimpleNamespace(url=self._host.context['apiBaseUrl'] + '/maintenance/backups/' + uid,
                                  method='GET', headers={})
        self._host.authorize_request(request)
        try:
            with httpx.Client(trust_env=False, follow_redirects=False, timeout=120) as client:
                with client.stream('GET', request.url, headers=request.headers) as response:
                    response.raise_for_status()
                    size = 0
                    with temporary.open('xb') as output:
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > MAX_ARCHIVE:
                                raise ValueError()
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
            self._check_origin()
            os.replace(temporary, path)
        except Exception:
            raise RuntimeError('备份没有导出，原有文件未改动，请重试') from None
        finally:
            temporary.unlink(missing_ok=True)
        return {'saved': True}


class CloseCoordinator:
    def __init__(self, host, window, ask, frontend_timeout: float = 8):
        self._host, self._window, self._ask = host, window, ask
        self._timeout = frontend_timeout
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._response = threading.Event()
        self._decision = None
        self._last_activity = 0.0
        self._accepting = False
        self._allow = False
        self.pending_request = None

    def respond_close(self, request_id, decision):
        with self._state_lock:
            if (
                self._accepting
                and request_id == self.pending_request
                and decision in {"ready", "stay", "discard", "pending"}
                and self._decision is None
            ):
                if decision == "pending":
                    self._last_activity = time.monotonic()
                else:
                    self._decision = decision
                self._response.set()

    def request_close(self):
        if self._allow:
            return True
        if self._lock.acquire(blocking=False):
            with self._state_lock:
                request_id = self.pending_request = str(uuid4())
                self._decision = None
                self._last_activity = time.monotonic()
                self._accepting = True
                self._response.clear()
            threading.Thread(
                target=self._prepare, args=(request_id,), daemon=True, name="desktop-close"
            ).start()
        return False

    def _dispatch(self, event_name, request_id):
        script = f"window.dispatchEvent(new CustomEvent({json.dumps(event_name)}, {{detail: {json.dumps(request_id)}}}));"

        def send():
            try:
                self._window.run_js(script)
            except Exception:
                pass

        # pywebview run_js can block on a frozen renderer. It must never own
        # the watchdog thread or postpone its deadline.
        threading.Thread(target=send, daemon=True, name="desktop-close-dispatch").start()

    def _prepare(self, request_id):
        try:
            self._dispatch("zhitu:close-request", request_id)
            while True:
                with self._state_lock:
                    decision = self._decision
                    remaining = self._timeout - (time.monotonic() - self._last_activity)
                    self._response.clear()
                    if decision is not None or remaining <= 0:
                        self._accepting = False
                        break
                self._response.wait(remaining)
            if decision is None:
                self._dispatch("zhitu:close-cancel", request_id)
                if not self._ask(
                    "未能确认保存", "界面没有回应，最近的位置或作答可能未保存。仍要退出吗？"
                ):
                    return
            elif decision == "stay":
                return
            try:
                active = self._host.status()["active_imports"]
            except RuntimeError:
                active = 0
                if not self._ask("本地服务已中断", "可能有记录尚未保存。要关闭并稍后重新启动吗？"):
                    return
            if active and not self._ask(
                "教材还在整理",
                "要取消整理并退出吗？选择取消可留在软件中继续等待。已保存的资料仍保留。",
            ):
                return
            if not self._host.stop().exited:
                return
            self._allow = True
            self._window.destroy()
        finally:
            with self._state_lock:
                self._accepting = False
                self.pending_request = None
            self._dispatch("zhitu:close-cancel", request_id)
            self._lock.release()


def install_native_guards(window, host, lease):
    """Called synchronously on before_show, before loading ANY privileged page."""
    native = window.native.webview
    origin = host.context["apiBaseUrl"].removesuffix("/api/v1")
    installed = False

    def navigation(sender, args):
        if str(args.Uri) == "about:blank" and not installed:
            return
        action = handle_navigation(str(args.Uri), bool(args.IsUserInitiated), origin=origin)
        if action != "allow":
            args.Cancel = True
            if action == "external":
                webbrowser.open(str(args.Uri))

    native.NavigationStarting += navigation

    def ready(sender=None, args=None):
        nonlocal installed
        if installed:
            return
        if args is not None and not args.IsSuccess:
            raise RuntimeError("WebView2 初始化失败")
        core = native.CoreWebView2
        if core is None:
            return

        def synchronous_request(sender, args):
            before = {str(h.Key): str(h.Value) for h in args.Request.Headers.GetEnumerator()}
            request = SimpleNamespace(
                url=str(args.Request.Uri), method=str(args.Request.Method), headers=dict(before)
            )
            host.authorize_request(request)
            for key in before:
                if key not in request.headers:
                    args.Request.Headers.RemoveHeader(key)
            for key, value in request.headers.items():
                if before.get(key) != value:
                    args.Request.Headers.SetHeader(key, value)

        # 6.2.1 dispatches request_sent asynchronously. This native synchronous
        # companion makes initial/asset requests deterministic without changing library internals.
        core.WebResourceRequested += synchronous_request

        def new_window(sender, args):
            args.Handled = True
            if (
                handle_navigation(str(args.Uri), bool(args.IsUserInitiated), origin=origin)
                == "external"
            ):
                webbrowser.open(str(args.Uri))

        core.NewWindowRequested += new_window
        core.Settings.AreDevToolsEnabled = False
        core.Settings.AreDefaultContextMenusEnabled = False
        installed = True
        lease.publish_window(int(window.native.Handle.ToInt64()))
        window.load_url(origin + "/")

    native.CoreWebView2InitializationCompleted += ready
    ready()


def create_desktop_window(host, lease):
    import webview

    webview.settings.update(
        ALLOW_FILE_URLS=False,
        ALLOW_DOWNLOADS=False,
        OPEN_EXTERNAL_LINKS_IN_BROWSER=False,
        REMOTE_DEBUGGING_PORT=None,
        IGNORE_SSL_ERRORS=False,
    )
    bridge = DesktopBridge(host)
    window = webview.create_window(
        "知途 · 本地学习空间",
        "about:blank",
        js_api=bridge,
        width=1280,
        height=850,
        min_size=(900, 650),
        text_select=True,
    )
    closer = CloseCoordinator(host, window, window.create_confirmation_dialog)
    bridge._attach(window, closer)
    window.events.request_sent += host.authorize_request

    def before_show():
        try:
            install_native_guards(window, host, lease)
        except Exception:
            from app.desktop.instance import show_native_error

            show_native_error("无法建立安全的本地窗口，请确认已安装 WebView2。学习数据仍保留。")
            window.destroy()

    window.events.before_show += before_show
    window.events.closing += closer.request_close
    return window
