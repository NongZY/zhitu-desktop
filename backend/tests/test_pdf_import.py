import pymupdf

from app.config import settings


def _sample_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Adaptive learning uses evidence to select review questions.")
    content = document.tobytes()
    document.close()
    return content


def test_pdf_upload_runs_eager_parser_and_populates_rag_chunks(
    client, create_learner, tmp_path
):
    settings.upload_dir = str(tmp_path)
    headers = create_learner("pdf-owner@example.com")
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
    assert "课本整理完成" in task_status.json()["message"]

    structure = client.get(f"/api/v1/textbooks/{textbook_id}/structure", headers=headers)
    assert structure.json()["textbook"]["parse_status"] == "ready"

    answer = client.post(
        "/api/v1/rag/ask",
        headers=headers,
        json={"question": "What does adaptive learning select?", "textbook_id": textbook_id},
    )
    assert answer.status_code == 200
    assert answer.json()["grounded"] is True
    assert answer.json()["citations"][0]["page_number"] == 1


def test_upload_rejects_fake_pdf(client, create_learner, tmp_path):
    settings.upload_dir = str(tmp_path)
    headers = create_learner("pdf-security@example.com")
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
