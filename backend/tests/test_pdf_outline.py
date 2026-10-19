import pymupdf
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Chapter
from app.services.pdf_outline import extract_outline


def bookmarked_pdf():
    with pymupdf.open() as doc:
        for text in ["Chapter A introduction", "Addition lesson", "Chapter B introduction"]:
            doc.new_page().insert_text((72, 72), text)
        doc.set_toc([[1, "Chapter A", 1], [2, "Addition", 2], [1, "Chapter B", 3]])
        return doc.tobytes()


def test_bookmarks_import_preserves_manual_edits_and_retry_ids(
    client, create_learner, monkeypatch, tmp_path,
):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    headers = create_learner("outline@example.com")
    book_id = client.post("/api/v1/textbooks", headers=headers,
                          json={"title": "Outline", "subject": "Math"}).json()["id"]

    def upload():
        result = client.post(f"/api/v1/textbooks/{book_id}/upload", headers=headers,
                             files={"file": ("outline.pdf", bookmarked_pdf(), "application/pdf")})
        assert result.json()["status"] == "completed"

    upload()
    structure = client.get(f"/api/v1/textbooks/{book_id}/structure", headers=headers).json()
    first = structure["chapters"][0]
    assert first["page_start"] == 1 and first["page_end"] == 2
    assert first["children"][0]["title"] == "Addition"
    chapter_id = first["id"]
    client.patch(f"/api/v1/chapters/{chapter_id}", headers=headers,
                 json={"title": "My edited chapter"})
    point = client.post(f"/api/v1/chapters/{chapter_id}/knowledge-points", headers=headers,
                        json={"name": "My note"}).json()
    upload()
    structure = client.get(f"/api/v1/textbooks/{book_id}/structure", headers=headers).json()
    assert len(structure["chapters"]) == 2
    assert structure["chapters"][0]["id"] == chapter_id
    assert structure["chapters"][0]["title"] == "My edited chapter"
    assert structure["chapters"][0]["knowledge_points"][0]["id"] == point["id"]
    with SessionLocal() as db:
        assert len(db.scalars(select(Chapter).where(Chapter.textbook_id == book_id)).all()) == 3
    result = client.get(f"/api/v1/chapters/{chapter_id}/content", headers=headers,
                        params={"page_size": 1, "page": 2}).json()
    assert result["total"] == 2
    assert result["items"][0]["page_number"] == 2
    assert client.get(f"/api/v1/chapters/{chapter_id}/content", headers=headers,
                      params={"page": 0}).status_code == 422
    answer = client.post("/api/v1/rag/ask", headers=headers, json={
        "chapter_id": chapter_id, "question": "Addition lesson",
    }).json()
    assert answer["citations"][0]["chapter_title"] == "Addition"


def test_no_outline_does_not_invent_chapters():
    with pymupdf.open() as doc:
        doc.new_page()
        assert extract_outline(doc, ["普通文字\n1.5万元\n8.3个球队进行单循环比赛"]) == []


def test_backfill_existing_book_is_private_and_idempotent(
    client, create_learner, monkeypatch, tmp_path,
):
    from app.models import ImportTask, Textbook

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    headers = create_learner("legacy@example.com")
    visitor = create_learner("other@example.com")
    book_id = client.post("/api/v1/textbooks", headers=headers,
                          json={"title": "Legacy", "subject": "Math"}).json()["id"]
    assert client.post(f"/api/v1/textbooks/{book_id}/outline", headers=headers).status_code == 422
    # Simulate a previously parsed book with no chapters using the real worker
    # with only its outline extractor disabled for this first import.
    import app.worker as worker
    extractor = worker.extract_outline
    monkeypatch.setattr(worker, "extract_outline", lambda *args: [])
    client.post(f"/api/v1/textbooks/{book_id}/upload", headers=headers,
                files={"file": ("legacy.pdf", bookmarked_pdf(), "application/pdf")})
    monkeypatch.setattr(worker, "extract_outline", extractor)
    assert client.post(f"/api/v1/textbooks/{book_id}/outline", headers=visitor).status_code == 404
    result = client.post(f"/api/v1/textbooks/{book_id}/outline", headers=headers)
    assert result.json()["added"] == 3
    assert client.post(f"/api/v1/textbooks/{book_id}/outline", headers=headers).json()["added"] == 0
    structure = client.get(f"/api/v1/textbooks/{book_id}/structure", headers=headers).json()
    parent_id = structure["chapters"][0]["id"]
    assert client.get(f"/api/v1/chapters/{parent_id}/content", headers=headers).json()["total"] == 2
    with SessionLocal() as db:
        assert db.scalar(select(ImportTask).where(ImportTask.textbook_id == book_id)).progress == 100
        db.get(Textbook, book_id).parse_status = "processing"
        db.commit()
    assert client.post(f"/api/v1/textbooks/{book_id}/outline", headers=headers).status_code == 409


def test_toc_page_numbers_not_used_as_pdf_pages():
    with pymupdf.open() as doc:
        texts = ["目录\n第一章 数\n1.1 加法\n1", "封面", "第一章 数", "1.1加法"]
        for _ in texts:
            doc.new_page()
        outline = extract_outline(doc, texts)
        assert [(c.title, c.page_start, c.page_end) for c in outline] == [
            ("第一章 数", 3, 4), ("1.1 加法", 4, 4),
        ]
