import pymupdf

from app.config import settings
from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def _teacher_headers(client) -> dict[str, str]:
    with SessionLocal() as db:
        db.add(
            User(
                email="pdf-teacher@example.com",
                name="PDF 测试教师",
                role=UserRole.teacher,
                hashed_password=hash_password("Learning123!"),
            )
        )
        db.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "pdf-teacher@example.com", "password": "Learning123!"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _sample_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Adaptive learning uses evidence to select review questions.")
    content = document.tobytes()
    document.close()
    return content


def test_pdf_upload_runs_eager_parser_and_populates_rag_chunks(client, tmp_path):
    settings.upload_dir = str(tmp_path)
    headers = _teacher_headers(client)
    textbook = client.post(
        "/api/v1/textbooks",
        headers=headers,
        json={"title": "PDF 测试教材", "subject": "英语"},
    )
    textbook_id = textbook.json()["id"]

    upload = client.post(
        f"/api/v1/textbooks/{textbook_id}/upload",
        headers=headers,
        files={"file": ("sample.pdf", _sample_pdf(), "application/pdf")},
    )
    assert upload.status_code == 202
    task = upload.json()
    assert task["status"] == "completed"
    assert task["progress"] == 100

    task_status = client.get(f"/api/v1/import-tasks/{task['id']}", headers=headers)
    assert task_status.status_code == 200
    assert "文本片段" in task_status.json()["message"]

    structure = client.get(f"/api/v1/textbooks/{textbook_id}/structure", headers=headers)
    assert structure.json()["textbook"]["parse_status"] == "review"

    answer = client.post(
        "/api/v1/rag/ask",
        headers=headers,
        json={"question": "What does adaptive learning select?", "textbook_id": textbook_id},
    )
    assert answer.status_code == 200
    assert answer.json()["grounded"] is True
    assert answer.json()["citations"][0]["page_number"] == 1


def test_upload_rejects_fake_pdf(client, tmp_path):
    settings.upload_dir = str(tmp_path)
    headers = _teacher_headers(client)
    textbook = client.post(
        "/api/v1/textbooks",
        headers=headers,
        json={"title": "伪 PDF", "subject": "安全测试"},
    )

    response = client.post(
        f"/api/v1/textbooks/{textbook.json()['id']}/upload",
        headers=headers,
        files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 415
