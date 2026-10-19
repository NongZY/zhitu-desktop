"""Opt-in real-book integration test; all accounts/answers stay in the test database.

Set TEXTBOOK_TEST_PDF to the supplied mathematics PDF before running pytest.
The copyrighted textbook itself is deliberately not included in the repository.
"""
import os
from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import DocumentChunk, Question


@pytest.mark.skipif(not os.environ.get("TEXTBOOK_TEST_PDF"), reason="real PDF not supplied")
def test_real_mathematics_book_learning_flow(client, create_learner, monkeypatch, tmp_path):
    pdf_path = Path(os.environ["TEXTBOOK_TEST_PDF"])
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "llm_api_key", None)
    headers = create_learner("real-book-test@example.com")
    book = client.post("/api/v1/textbooks", headers=headers, json={
        "title": "真实教材功能测试", "subject": "数学", "grade": "七年级",
    }).json()
    book_id = book["id"]
    with pdf_path.open("rb") as source:
        response = client.post(f"/api/v1/textbooks/{book_id}/upload", headers=headers,
                               files={"file": ("mathematics.pdf", source, "application/pdf")})
    assert response.status_code == 202
    task = response.json()
    assert task["status"] == "completed"
    assert task["progress"] == 100
    structure = client.get(f"/api/v1/textbooks/{book_id}/structure", headers=headers).json()
    assert structure['textbook']['parse_status'] == 'ready'
    assert [c["title"] for c in structure["chapters"]] == [
        "第一章 有理数", "第二章 整式的加减", "第三章 一元一次方程", "第四章 几何图形初步",
    ]
    first_section = structure["chapters"][0]["children"][0]
    assert first_section["title"] == "1.1 正数和负数"
    assert first_section["page_start"] == 9  # PDF page, printed page 2
    reader = client.get(f"/api/v1/textbooks/{book_id}/reader", headers=headers)
    assert reader.status_code == 200
    assert reader.json()["page_count"] == 162
    search = client.get(f"/api/v1/textbooks/{book_id}/search", headers=headers,
                        params={"q": "正数和负数", "chapter_id": first_section["id"]})
    assert search.status_code == 200
    assert 9 in [item["page_number"] for item in search.json()["items"]]
    page_image = client.get(f"/api/v1/textbooks/{book_id}/pages/9/image", headers=headers)
    assert page_image.status_code == 200
    assert page_image.headers["content-type"] == "image/png"
    with pymupdf.open(pdf_path) as original:
        page = original[8]
        scale = min(2.0, 2000 / max(page.rect.width, page.rect.height))
        expected = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                   colorspace=pymupdf.csRGB, alpha=False)
        # The default reader must use the actual colored original, not a
        # reconstruction from extracted characters or a converted grayscale page.
        assert pymupdf.Pixmap(page_image.content).samples == expected.samples
    absolute = next(c for c in structure["chapters"][0]["children"][1]["children"]
                    if "绝对值" in c["title"])
    assert absolute["title"] == "1.2.4 绝对值"
    assert absolute["page_start"] == 18
    content = client.get(f"/api/v1/chapters/{absolute['id']}/content", headers=headers).json()
    assert content["total"] > 0
    assert all(18 <= item["page_number"] <= 22 for item in content["items"])
    parent_content = client.get(
        f"/api/v1/chapters/{structure['chapters'][0]['id']}/content",
        headers=headers, params={"page_size": 50},
    ).json()
    assert parent_content["total"] > content["total"]
    section_answer = client.post("/api/v1/rag/ask", headers=headers, json={
        "textbook_id": book_id, "chapter_id": absolute["id"], "question": "绝对值是什么？",
    }).json()
    assert section_answer["grounded"]
    assert all(c["chapter_title"] == absolute["title"] for c in section_answer["citations"])
    with pymupdf.open(pdf_path) as document:
        nonempty_pages = {i + 1 for i, page in enumerate(document) if page.get_text().strip()}
    with SessionLocal() as db:
        chunks = db.scalars(select(DocumentChunk).where(
            DocumentChunk.textbook_id == book_id,
        )).all()
        assert {c.page_number for c in chunks} == nonempty_pages
        assert all("\x00" not in c.content for c in chunks)
        page_17 = "\n".join(c.content for c in chunks if c.page_number == 17)
        assert "设a是一个正数" in page_17
        assert "(5)/(2)" in page_17
        assert "-(2)/(11)" in page_17
        assert "犪" not in page_17
        page_93 = "\n".join(c.content for c in chunks if c.page_number == 93)
        assert "x+2x+4x=140" in page_93.replace(" ", "")
        assert all(c.metadata_json["extraction_version"] == "math-layout-v1" for c in chunks)
        assert any(c.metadata_json["math_review_required"] for c in chunks)
        excerpts = {c.id: c.content for c in chunks}
    for question in ["什么是正数和负数？", "什么是绝对值？", "怎样解一元一次方程？"]:
        answer = client.post("/api/v1/rag/ask", headers=headers, json={
            "textbook_id": book_id, "question": question,
        })
        assert answer.status_code == 200
        assert answer.json()["grounded"]
        for citation in answer.json()["citations"]:
            assert citation["textbook_id"] == book_id
            assert citation["page_number"] in nonempty_pages
            assert citation["excerpt"] in excerpts[citation["chunk_id"]]

    visitor = create_learner("real-book-visitor@example.com")
    assert client.get(f"/api/v1/chapters/{absolute['id']}/content", headers=visitor).status_code == 404
    assert client.get(f"/api/v1/import-tasks/{task['id']}", headers=visitor).status_code == 404
    assert client.post("/api/v1/rag/ask", headers=visitor, json={
        "textbook_id": book_id, "question": "什么是正数？",
    }).status_code == 404

    # Chapters are extracted; exercises below are explicitly authored test questions.
    # These explicitly authored test questions verify the downstream practice pipeline.
    chapter = client.post(f"/api/v1/textbooks/{book_id}/chapters", headers=headers,
                          json={"title": "第一章 有理数"}).json()
    question_rows = []
    point_ids = []
    for name, stem, answer in [("有理数加法", "3+(-5)=?", "-2"),
                               ("绝对值", "|-6|=?", "6")]:
        point = client.post(f"/api/v1/chapters/{chapter['id']}/knowledge-points",
                            headers=headers, json={"name": name}).json()
        point_ids.append(point["id"])
        response = client.post("/api/v1/questions", headers=headers, json={
            "textbook_id": book_id, "chapter_id": chapter["id"],
            "knowledge_point_id": point["id"], "stem": stem,
            "question_type": "fill_blank", "correct_answer": answer,
            "status": "approved", "source": "manual",
        })
        assert response.status_code == 201
        question_rows.append(response.json())
    assert client.post(f"/api/v1/textbooks/{book_id}/publish", headers=headers).status_code == 200
    paper = client.post("/api/v1/exams/generate", headers=headers, json={
        "textbook_id": book_id, "question_count": 2, "score_per_question": 5,
    }).json()
    assert all("correct_answer" not in q for q in paper["questions"])
    submission = {"answers": [
        {"question_id": question_rows[0]["id"], "answer": "0"},
        {"question_id": question_rows[1]["id"], "answer": "6"},
    ]}
    result = client.post(f"/api/v1/exams/{paper['id']}/submit",
                         headers=headers, json=submission)
    assert result.status_code == 201
    assert result.json()["score"] == 5
    assert client.post(f"/api/v1/exams/{paper['id']}/submit",
                       headers=headers, json=submission).status_code == 409
    assert client.get("/api/v1/learning/wrong-questions", headers=headers).json()["total"] == 1
    assert client.get("/api/v1/learning/mastery", headers=headers).json()["total"] == 2
    adaptive = client.post("/api/v1/exams/generate", headers=headers, json={
        "textbook_id": book_id, "question_count": 1, "mode": "adaptive",
    }).json()
    weights = adaptive["strategy"]["knowledge_point_weights"]
    assert weights[str(point_ids[0])] > weights[str(point_ids[1])]

    # The learner can practise an extracted chapter without authoring its questions.
    generated = client.post('/api/v1/exams/generate', headers=headers, json={
        'textbook_id': book_id, 'chapter_ids': [absolute['id']],
        'question_count': 5, 'auto_fill': True, 'random_seed': 7,
    })
    assert generated.status_code == 201, generated.text
    paper = generated.json()
    assert paper['strategy']['generated_count'] == 5
    assert all('correct_answer' not in q for q in paper['questions'])
    with SessionLocal() as db:
        questions = db.scalars(select(Question).where(
            Question.chapter_id == absolute['id'],
        )).all()
        assert len(questions) == 5
        assert all(q.source == 'generated_template' for q in questions)
        answers = [{'question_id': q.id, 'answer': q.correct_answer} for q in questions]
    result = client.post(f"/api/v1/exams/{paper['id']}/submit", headers=headers,
                         json={'answers': answers})
    assert result.status_code == 201
    assert result.json()['correct_count'] == 4
    assert result.json()['pending_count'] == 1
    assert result.json()['graded_total_score'] == 20
