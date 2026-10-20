import json
from types import SimpleNamespace
import threading
import time
import pytest

from app.desktop.window import inject_desktop_header, handle_navigation, DesktopBridge, CloseCoordinator
from app.desktop.window import install_native_guards

ORIGIN = "http://127.0.0.1:41234"


def fake_request(url):
    return SimpleNamespace(url=url, method="GET", headers={})


@pytest.mark.parametrize("url", ["http://127.0.0.1.evil.invalid:41234/", "http://127.0.0.1:41235/",
                                 "https://127.0.0.1:41234/", "http://user@127.0.0.1:41234/",
                                 "file:///private", "https://example.com/"])
def test_header_is_never_sent_to_another_origin(url):
    request = fake_request(url)
    request.headers["x-zhitu-desktop-token"] = "previous-hop"
    inject_desktop_header(request, ORIGIN, "sentinel")
    assert not any(key.lower() == "x-zhitu-desktop-token" for key in request.headers)


def test_header_and_navigation_only_allow_exact_origin():
    request = fake_request(ORIGIN + "/assets/a.js")
    inject_desktop_header(request, ORIGIN, "sentinel")
    assert request.headers["X-ZhiTu-Desktop-Token"] == "sentinel"
    assert handle_navigation(ORIGIN + "/dashboard", False, origin=ORIGIN) == "allow"
    assert handle_navigation("https://example.com", True, origin=ORIGIN) == "external"
    assert handle_navigation("https://example.com", False, origin=ORIGIN) == "deny"
    assert handle_navigation("javascript:alert(1)", True, origin=ORIGIN) == "deny"


def test_native_guards_precede_first_privileged_load():
    class Event:
        def __init__(self): self.handlers = []
        def __iadd__(self, handler): self.handlers.append(handler); return self
    core = SimpleNamespace(WebResourceRequested=Event(), NewWindowRequested=Event(), Settings=SimpleNamespace())
    native = SimpleNamespace(CoreWebView2=core, NavigationStarting=Event(), CoreWebView2InitializationCompleted=Event())
    def load(url):
        assert native.NavigationStarting.handlers and core.WebResourceRequested.handlers
        assert url == ORIGIN + '/'
    window = SimpleNamespace(native=SimpleNamespace(webview=native, Handle=SimpleNamespace(ToInt64=lambda: 42)), load_url=load)
    install_native_guards(window, fake_host(), SimpleNamespace(publish_window=lambda hwnd: None))
    external = SimpleNamespace(Uri='https://evil.invalid/', IsUserInitiated=False, Cancel=False)
    native.NavigationStarting.handlers[0](None, external)
    assert external.Cancel is True


class FakeWindow:
    def __init__(self):
        self.url, self.scripts = ORIGIN, []
        self.requested, self.destroyed = threading.Event(), threading.Event()
    def get_current_url(self):
        return self.url
    def run_js(self, script):
        self.scripts.append(script)
        self.requested.set()
    def destroy(self):
        self.destroyed.set()


def fake_host(active=0):
    return SimpleNamespace(context={"apiBaseUrl": ORIGIN + "/api/v1", "workspace": {"ownerId": 17}},
                           status=lambda: {"active_imports": active},
                           stop=lambda: SimpleNamespace(exited=True))


def test_bridge_refuses_untrusted_page():
    window = FakeWindow()
    host = fake_host()
    bridge = DesktopBridge(host)
    bridge._attach(window, None)
    assert bridge.get_context()["workspace"]["ownerId"] == 17
    window.url = "https://example.com/"
    with pytest.raises(RuntimeError):
        bridge.get_context()


@pytest.mark.parametrize("decision,exits", [("stay", False), ("ready", True), ("discard", True)])
def test_close_handshake_waits_and_is_idempotent(decision, exits):
    window = FakeWindow()
    closer = CloseCoordinator(fake_host(), window, lambda *args: False, frontend_timeout=.2)
    assert closer.request_close() is False
    assert window.requested.wait(1)
    assert closer.request_close() is False
    assert not window.destroyed.is_set()
    closer.respond_close("wrong-request", "ready")
    assert not window.destroyed.is_set()
    closer.respond_close(closer.pending_request, decision)
    assert window.destroyed.wait(.4) is exits


def test_close_timeout_or_active_import_never_silently_exits():
    for active, reply in ((0, False), (1, True)):
        window = FakeWindow()
        prompts = []
        closer = CloseCoordinator(fake_host(active), window, lambda *args: prompts.append(args) or False,
                                  frontend_timeout=.05)
        closer.request_close()
        assert window.requested.wait(1)
        if reply:
            closer.respond_close(closer.pending_request, "ready")
        assert not window.destroyed.wait(.15)
        assert prompts
