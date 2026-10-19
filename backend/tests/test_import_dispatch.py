import threading

from app.config import settings
from app.database import SessionLocal
from app.models import ImportTask, Textbook
from tests.test_pdf_import import _sample_pdf


def test_local_upload_returns_queued_before_parser_finishes(client, create_learner, tmp_path, monkeypatch):
    from app.services import import_dispatch

    entered, release = threading.Event(), threading.Event()
    original = import_dispatch.process_textbook_pdf.run

    def slow_parser(task_id):
        entered.set()
        assert release.wait(10)
        return original(task_id)

    monkeypatch.setattr(settings, "local_mode", True)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(import_dispatch.process_textbook_pdf, "run", slow_parser)
    headers = create_learner("local-import@example.com")
    book_id = client.post("/api/v1/textbooks", headers=headers, json={"title": "本地教材", "subject": "测试"}).json()["id"]
    try:
        response = client.post(f"/api/v1/textbooks/{book_id}/upload", headers=headers,
                               files={"file": ("sample.pdf", _sample_pdf(), "application/pdf")})
        assert response.status_code == 202
        assert response.json()["status"] == "queued"
        assert entered.wait(3)
        assert client.get("/api/v1/health").status_code == 200
    finally:
        release.set()
        import_dispatch.shutdown_local_imports()
    task = client.get(f"/api/v1/import-tasks/{response.json()['id']}", headers=headers).json()
    assert task["status"] == "completed"
    assert task["progress"] == 100


def test_restart_marks_interrupted_imports_failed(client, create_learner):
    from app.services.import_dispatch import recover_interrupted_imports

    headers = create_learner("interrupted@example.com")
    book_id = client.post("/api/v1/textbooks", headers=headers, json={"title": "教材", "subject": "测试"}).json()["id"]
    with SessionLocal() as db:
        db.get(Textbook, book_id).parse_status = "processing"
        db.add(ImportTask(id="interrupted", textbook_id=book_id, status="processing", progress=10))
        db.commit()
    recover_interrupted_imports()
    task = client.get("/api/v1/import-tasks/interrupted", headers=headers).json()
    assert task["status"] == "failed"
    assert "中断" in task["message"]
    with SessionLocal() as db:
        assert db.get(Textbook, book_id).parse_status == "failed"
