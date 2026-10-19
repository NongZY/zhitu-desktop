def test_rag_answer_is_grounded_in_the_learners_textbook(client, create_learner):
    headers = create_learner("rag-owner@example.com")
    textbook = client.post(
        "/api/v1/textbooks",
        headers=headers,
        json={"title": "数学", "subject": "数学"},
    ).json()
    client.post(
        "/api/v1/rag/chunks",
        headers=headers,
        params={
            "textbook_id": textbook["id"],
            "content": "三角形的内角和等于180度。",
            "page_number": 12,
        },
    )
    response = client.post(
        "/api/v1/rag/ask",
        headers=headers,
        json={"question": "三角形的内角和是多少？", "textbook_id": textbook["id"]},
    )
    assert response.status_code == 200
    assert response.json()["grounded"] is True
    assert response.json()["citations"][0]["page_number"] == 12
    assert "180" in response.json()["answer"]


def test_rag_warns_about_incomplete_formulas_instead_of_asking_model_to_guess(
    client, create_learner, monkeypatch,
):
    from app.api import rag
    from app.database import SessionLocal
    from app.models import DocumentChunk

    headers = create_learner("math-review@example.com")
    book_id = client.post("/api/v1/textbooks", headers=headers, json={
        "title": "含公式的课本", "subject": "数学",
    }).json()["id"]
    with SessionLocal() as db:
        db.add(DocumentChunk(
            textbook_id=book_id, content="分数计算中有尚未识别的符号 �。",
            page_number=17, chunk_index=0,
            metadata_json={"source": "pdf", "math_review_required": True},
        ))
        db.commit()

    def must_not_guess(*args):
        raise AssertionError("Unreliable math must not be sent to the model as reliable evidence")

    monkeypatch.setattr(rag, "_llm_answer", must_not_guess)
    response = client.post("/api/v1/rag/ask", headers=headers, json={
        "textbook_id": book_id, "question": "怎样计算分数？",
    })
    assert response.status_code == 200
    assert "查看原页" in response.json()["answer"]
    assert response.json()["model"] == "retrieval-only"
    assert response.json()["citations"][0]["page_number"] == 17
