import pytest
from desktop_helpers import RunningDesktop


@pytest.fixture
def desktop_service(tmp_path):
    service = RunningDesktop(tmp_path)
    try:
        yield service
    finally:
        service.close()


def test_desktop_token_applies_to_all_paths(desktop_service):
    s = desktop_service
    for path in ("/", "/health", "/api/v1/health", "/api/v1/textbooks",
                 "/api/v1/textbooks/1/pages/1/image"):
        assert s.get(path, authenticated=False).status_code == 403
        assert s.get(path, headers={"X-ZhiTu-Desktop-Token": "old-launch"}).status_code == 403
    assert s.get("/api/v1/textbooks?user_id=999").json()["total"] == 0
    assert s.get("/").status_code == 200
    assert "default-src 'self'" in s.get("/").headers["content-security-policy"]


def test_desktop_rejects_host_origin_and_has_no_login_or_docs(desktop_service):
    s = desktop_service
    assert s.get("/health", headers={"Host": "localhost:1234"}).status_code == 403
    assert s.get("/health", headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert s.get("/health", headers={"Origin": s.origin}).status_code == 200
    for path in ("/api/v1/auth/me", "/api/v1/auth/login", "/docs", "/redoc", "/openapi.json",
                 "/..%2fworkspace.json", "/api/v1/not-a-route"):
        assert s.get(path).status_code == 404, path
    assert s.token not in str(s.ready)
    assert s.token not in "".join(s.errors)


def test_desktop_cannot_see_other_workspace(tmp_path):
    a, b = RunningDesktop(tmp_path / "a"), RunningDesktop(tmp_path / "b")
    try:
        book = a.request("POST", "/api/v1/textbooks", json={"title": "private", "subject": "math"})
        assert book.status_code == 201, book.text
        assert b.get("/api/v1/textbooks").json()["total"] == 0
        assert b.get(f"/api/v1/textbooks/{book.json()['id']}").status_code == 404
        assert a.ready["context"]["workspace"]["id"] != b.ready["context"]["workspace"]["id"]
    finally:
        a.close()
        b.close()


def test_legacy_web_still_requires_jwt(client):
    assert client.get("/api/v1/textbooks").status_code == 401
