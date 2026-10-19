from app.database import SessionLocal
from app.models import ExamRecord, LocalKnowledgePoint, UserMastery, WrongQuestion


def learning_fixture(client, headers):
    book = client.post(
        "/api/v1/textbooks",
        headers=headers,
        json={
            "title": "七年级数学",
            "subject": "数学",
            "grade": "七年级",
        },
    ).json()
    chapter = client.post(
        f"/api/v1/textbooks/{book['id']}/chapters",
        headers=headers,
        json={"title": "有理数", "page_start": 9},
    ).json()
    point = client.post(
        f"/api/v1/chapters/{chapter['id']}/knowledge-points",
        headers=headers,
        json={"name": "有理数加法", "description": "数轴上的加法"},
    ).json()
    questions = []
    for kind, stem, answer in [
        ("true_false", "1+1=2", True),
        ("short_answer", "说明相反数的含义", "相反数互为相反"),
    ]:
        response = client.post(
            "/api/v1/questions",
            headers=headers,
            json={
                "textbook_id": book["id"],
                "chapter_id": chapter["id"],
                "knowledge_point_id": point["id"],
                "question_type": kind,
                "stem": stem,
                "correct_answer": answer,
                "explanation": "参考解析",
                "status": "approved",
            },
        )
        assert response.status_code == 201, response.text
        questions.append(response.json())
    paper = client.post(
        "/api/v1/exams/generate",
        headers=headers,
        json={
            "textbook_id": book["id"],
            "question_count": 2,
            "score_per_question": 5,
        },
    ).json()
    result = client.post(
        f"/api/v1/exams/{paper['id']}/submit",
        headers=headers,
        json={
            "answers": [
                {"question_id": q["id"], "answer": q["correct_answer"], "time_spent_seconds": 10}
                for q in questions
            ],
            "duration_seconds": 120,
        },
    )
    assert result.status_code == 201, result.text
    return book, chapter, point, questions, paper, result.json()


def test_record_detail_contains_answers_scores_and_is_private(client, create_learner):
    headers = create_learner("detail-owner@example.com")
    book, chapter, point, questions, paper, record = learning_fixture(client, headers)
    response = client.get(f"/api/v1/learning/exams/{record['id']}", headers=headers)
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["title"] == paper["title"]
    assert detail["textbook_title"] == book["title"]
    assert detail["pending_count"] == 1
    assert detail["graded_total_score"] == 5
    assert len(detail["details"]) == 2
    assert {item["max_score"] for item in detail["details"]} == {5}
    assert detail["details"][0]["chapter_id"] == chapter["id"]
    assert detail["details"][0]["knowledge_point_id"] == point["id"]
    assert {item["explanation"] for item in detail["details"]} == {"参考解析"}
    other = create_learner("detail-other@example.com")
    assert client.get(f"/api/v1/learning/exams/{record['id']}", headers=other).status_code == 404
    assert client.get("/api/v1/learning/exams/99999", headers=headers).status_code == 404


def test_knowledge_detail_has_chapter_mapping_and_evidence(client, create_learner):
    headers = create_learner("point-owner@example.com")
    book, chapter, point, _, _, record = learning_fixture(client, headers)
    global_id = point["global_knowledge_point_id"]
    response = client.get(f"/api/v1/learning/knowledge-points/{global_id}", headers=headers)
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["name"] == point["name"]
    assert detail["attempts"] == 1  # Self-check questions must not lower mastery.
    assert detail["mappings"][0]["local_knowledge_point_id"] == point["id"]
    assert detail["mappings"][0]["textbook_id"] == book["id"]
    assert detail["mappings"][0]["page_start"] == chapter["page_start"]
    assert len(detail["recent_answers"]) == 2
    assert detail["recent_answers"][0]["record_id"] == record["id"]
    other = create_learner("point-other@example.com")
    assert (
        client.get(f"/api/v1/learning/knowledge-points/{global_id}", headers=other).status_code
        == 404
    )


def test_dashboard_uses_objective_denominator_and_real_weak_points(client, create_learner):
    headers = create_learner("summary-owner@example.com")
    learning_fixture(client, headers)
    with SessionLocal() as db:
        mastery = db.query(UserMastery).one()
        mastery.mastery = 0.9
        db.commit()
    summary = client.get("/api/v1/learning/dashboard", headers=headers).json()
    assert summary["average_score"] == 100
    assert summary["weak_point_count"] == 0
    assert summary["weak_points"] == []
    assert summary["recommendations"] == []
    assert summary["recent_exams"][0]["pending_count"] == 1
    assert sum(day["questions"] for day in summary["weekly_activity"]) == 2


def test_history_paginates_with_true_total(client, create_learner):
    headers = create_learner("history-owner@example.com")
    _, _, _, _, paper, record = learning_fixture(client, headers)
    with SessionLocal() as db:
        original = db.get(ExamRecord, record["id"])
        for _ in range(2):
            db.add(
                ExamRecord(
                    user_id=original.user_id,
                    paper_id=paper["id"],
                    submitted_at=original.submitted_at,
                    total_score=10,
                )
            )
        db.commit()
    first = client.get("/api/v1/learning/exams?page=1&page_size=2", headers=headers).json()
    second = client.get("/api/v1/learning/exams?page=2&page_size=2", headers=headers).json()
    assert first["total"] == second["total"] == 3
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert {row["id"] for row in first["items"]}.isdisjoint(row["id"] for row in second["items"])
    assert client.get("/api/v1/learning/exams?page=0", headers=headers).status_code == 422


def test_shared_global_point_does_not_expose_other_users_books_or_answers(client, create_learner):
    owner = create_learner("shared-owner@example.com")
    book, _, point, questions, _, _ = learning_fixture(client, owner)
    other = create_learner("shared-other@example.com")
    other_book, _, other_point, _, _, _ = learning_fixture(client, other)
    global_id = point["global_knowledge_point_id"]
    with SessionLocal() as db:
        local = db.get(LocalKnowledgePoint, other_point["id"])
        local.global_knowledge_point_id = global_id
        mastery = (
            db.query(UserMastery).filter(UserMastery.global_knowledge_point_id == global_id).first()
        )
        db.add(WrongQuestion(user_id=mastery.user_id, question_id=questions[0]["id"]))
        db.commit()
    detail = client.get(f"/api/v1/learning/knowledge-points/{global_id}", headers=owner).json()
    assert {row["textbook_id"] for row in detail["mappings"]} == {book["id"]}
    assert {row["textbook_id"] for row in detail["recent_answers"]} == {book["id"]}
    assert all(row["textbook_id"] != other_book["id"] for row in detail["recent_answers"])
    wrong = client.get("/api/v1/learning/wrong-questions", headers=owner).json()["items"][0]
    assert wrong["knowledge_point_id"] == point["id"]
    assert wrong["textbook_id"] == book["id"]


def test_unpractised_point_is_not_misrepresented_as_failed(client, create_learner):
    headers = create_learner("unpractised@example.com")
    book = client.post(
        "/api/v1/textbooks", headers=headers, json={"title": "数学", "subject": "数学"}
    ).json()
    chapter = client.post(
        f"/api/v1/textbooks/{book['id']}/chapters", headers=headers, json={"title": "有理数"}
    ).json()
    point = client.post(
        f"/api/v1/chapters/{chapter['id']}/knowledge-points",
        headers=headers,
        json={"name": "有理数加法"},
    ).json()
    response = client.get(
        f"/api/v1/learning/knowledge-points/{point['global_knowledge_point_id']}", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["mastery"] is None
    assert response.json()["attempts"] == 0
    assert response.json()["recent_answers"] == []
