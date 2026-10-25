import pymupdf
from sqlalchemy import select, text

from app.config import settings
from app.database import SessionLocal
from app.models import DocumentChunk


def pdf_bytes():
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Positive and negative numbers are useful in mathematics.")
        page.insert_text((72, 100), "1?+2=3")
        return document.tobytes()


def create_book(client, create_learner, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    headers = create_learner("pdf-recovery@example.com")
    book = client.post(
        "/api/v1/textbooks", headers=headers,
        json={"title": "解析回归测试", "subject": "数学"},
    ).json()
    return headers, book["id"]


def upload(client, headers, book_id):
    return client.post(
        f"/api/v1/textbooks/{book_id}/upload", headers=headers,
        files={"file": ("test.pdf", pdf_bytes(), "application/pdf")},
    )


def test_pdf_nul_text_is_cleaned_before_database_insert(
    client, create_learner, monkeypatch, tmp_path
):
    headers, book_id = create_book(client, create_learner, monkeypatch, tmp_path)
    original = pymupdf.Page.get_text

    def extract_with_nul(page, *args, **kwargs):
        result = original(page, *args, **kwargs)
        if isinstance(result, dict):
            for block in result.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        for character in span.get("chars", []):
                            if character["c"] == "?":
                                character["c"] = "\x00"
        return result

    monkeypatch.setattr(pymupdf.Page, "get_text", extract_with_nul)
    # SQLite accepts NUL by default; emulate PostgreSQL's real storage constraint.
    with SessionLocal() as db:
        db.execute(text("""CREATE TRIGGER reject_nul BEFORE INSERT ON document_chunks
            WHEN instr(NEW.content, char(0)) > 0
            BEGIN SELECT RAISE(ABORT, 'NUL text rejected'); END"""))
        db.commit()
    response = upload(client, headers, book_id)
    assert response.status_code == 202
    assert response.json()["status"] == "completed"
    assert response.json()["progress"] == 100
    with SessionLocal() as db:
        chunks = db.scalars(select(DocumentChunk)).all()
        assert chunks
        assert all("\x00" not in chunk.content for chunk in chunks)
        assert any("1�+2=3" in chunk.content for chunk in chunks)
        assert any(chunk.metadata_json["math_review_required"] for chunk in chunks)


def test_database_error_records_failure_and_preserves_previous_chunks(
    client, create_learner, monkeypatch, tmp_path
):
    headers, book_id = create_book(client, create_learner, monkeypatch, tmp_path)
    with SessionLocal() as db:
        db.add(DocumentChunk(
            textbook_id=book_id, content="previous valid extraction",
            chunk_index=0, metadata_json={"source": "pdf"},
        ))
        db.commit()
        db.execute(text("""CREATE TRIGGER reject_insert BEFORE INSERT ON document_chunks
            BEGIN SELECT RAISE(ABORT, 'simulated storage failure'); END"""))
        db.commit()
    response = upload(client, headers, book_id)
    assert response.status_code == 202
    task = response.json()
    polled = client.get(f"/api/v1/import-tasks/{task['id']}", headers=headers).json()
    assert polled["status"] == "failed"
    assert "失败" in polled["message"]
    book = client.get(f"/api/v1/textbooks/{book_id}", headers=headers).json()
    assert book["parse_status"] == "failed"
    listed = client.get("/api/v1/textbooks", headers=headers).json()["items"][0]
    assert listed["processing_message"] == polled["message"]
    with SessionLocal() as db:
        assert db.scalars(select(DocumentChunk.content)).all() == ["previous valid extraction"]


def test_reparse_does_not_duplicate_pdf_chunks_or_delete_manual_content(
    client, create_learner, monkeypatch, tmp_path
):
    headers, book_id = create_book(client, create_learner, monkeypatch, tmp_path)
    with SessionLocal() as db:
        db.add(DocumentChunk(
            textbook_id=book_id, content="个人补充笔记", chunk_index=0,
            metadata_json={"source": "manual"},
        ))
        db.commit()
    for _ in range(2):
        assert upload(client, headers, book_id).json()["status"] == "completed"
    with SessionLocal() as db:
        chunks = db.scalars(select(DocumentChunk)).all()
        assert len(chunks) == 2
        assert any(chunk.content == "个人补充笔记" for chunk in chunks)
        assert len({chunk.chunk_index for chunk in chunks}) == 2


def test_image_only_pdf_reports_ocr_requirement(client, create_learner, monkeypatch, tmp_path):
    headers, book_id = create_book(client, create_learner, monkeypatch, tmp_path)
    with pymupdf.open() as document:
        document.new_page()
        empty_pdf = document.tobytes()
    result = client.post(
        f"/api/v1/textbooks/{book_id}/upload", headers=headers,
        files={"file": ("empty.pdf", empty_pdf, "application/pdf")},
    ).json()
    assert result["status"] == "failed"
    assert "OCR" in result["message"]
    assert result["progress"] != 100
    # OCR failure is not a failure to read the original scanned pages.
    assert client.get(f'/api/v1/textbooks/{book_id}/reader', headers=headers).json()['page_count'] == 1
    assert client.get(f'/api/v1/textbooks/{book_id}/pages/1/image', headers=headers).status_code == 200
