from sqlalchemy import select

from app.database import SessionLocal
from app.models import Question

TYPES = {"single_choice", "multiple_choice", "true_false", "fill_blank", "short_answer"}


def _scope(client, create_learner):
    headers = create_learner("variety@example.com")
    book = client.post(
        "/api/v1/textbooks", headers=headers, json={"title": "七年级数学", "subject": "数学"}
    ).json()
    chapter = client.post(
        f"/api/v1/textbooks/{book['id']}/chapters", headers=headers, json={"title": "有理数的加法"}
    ).json()
    point = client.post(
        f"/api/v1/chapters/{chapter['id']}/knowledge-points",
        headers=headers,
        json={"name": "有理数加法"},
    ).json()
    return headers, book, chapter, point


def _generate(client, headers, book, **kwargs):
    return client.post(
        "/api/v1/exams/generate",
        headers=headers,
        json={
            "textbook_id": book["id"],
            "question_count": 5,
            "auto_fill": True,
            "random_seed": 17,
            **kwargs,
        },
    )


def test_default_practice_contains_all_types_even_with_enough_fill_blanks(client, create_learner):
    headers, book, chapter, point = _scope(client, create_learner)
    for number in range(5):
        response = client.post(
            "/api/v1/questions",
            headers=headers,
            json={
                "textbook_id": book["id"],
                "chapter_id": chapter["id"],
                "knowledge_point_id": point["id"],
                "stem": f"{number} + 1 = ?",
                "correct_answer": str(number + 1),
                "question_type": "fill_blank",
                "difficulty": 2,
                "status": "approved",
            },
        )
        assert response.status_code == 201
    response = _generate(client, headers, book)
    assert response.status_code == 201, response.text
    assert {q["question_type"] for q in response.json()["questions"]} == TYPES
    assert all("correct_answer" not in q for q in response.json()["questions"])


def test_selected_point_and_types_are_respected_and_subjective_does_not_penalize(
    client, create_learner
):
    headers, book, chapter, point = _scope(client, create_learner)
    response = _generate(
        client,
        headers,
        book,
        chapter_ids=[chapter["id"]],
        knowledge_point_ids=[point["id"]],
        question_types=sorted(TYPES),
    )
    assert response.status_code == 201, response.text
    paper = response.json()
    assert {q["question_type"] for q in paper["questions"]} == TYPES
    assert {q["knowledge_point_id"] for q in paper["questions"]} == {point["id"]}
    with SessionLocal() as db:
        questions = db.scalars(
            select(Question).where(Question.id.in_([q["id"] for q in paper["questions"]]))
        ).all()
        answers = [
            {
                "question_id": q.id,
                "answer": q.correct_answer
                if q.question_type != "short_answer"
                else "我自己的解题过程",
            }
            for q in questions
        ]
    result = client.post(
        f"/api/v1/exams/{paper['id']}/submit", headers=headers, json={"answers": answers}
    ).json()
    assert result["correct_count"] == 4
    assert result["wrong_count"] == 0
    assert result["pending_count"] == 1
    assert result["graded_total_score"] == 20
    assert result["score"] == 20 and result["total_score"] == 25
    assert result["status"] == "pending_self_check"
    assert all(item["max_score"] == 5 for item in result["details"])
    assert client.get("/api/v1/learning/wrong-questions", headers=headers).json()["total"] == 0
    mastery = client.get("/api/v1/learning/mastery", headers=headers).json()["items"]
    assert len(mastery) == 1 and mastery[0]["attempts"] == 4


def test_explicit_single_type_and_difficulty_are_not_broadened(client, create_learner):
    headers, book, chapter, point = _scope(client, create_learner)
    response = _generate(client, headers, book, question_types=["true_false"])
    assert response.status_code == 201, response.text
    assert {q["question_type"] for q in response.json()["questions"]} == {"true_false"}
    response = _generate(client, headers, book, question_types=["single_choice"], difficulty_min=4)
    assert response.status_code == 422
    with SessionLocal() as db:
        assert not db.scalars(select(Question).where(Question.difficulty >= 4)).all()


def test_unsupported_point_cannot_generate_other_topics(client, create_learner):
    headers, book, chapter, point = _scope(client, create_learner)
    unsupported = client.post(
        f"/api/v1/chapters/{chapter['id']}/knowledge-points",
        headers=headers,
        json={"name": "待整理的概念"},
    ).json()
    response = _generate(client, headers, book, knowledge_point_ids=[unsupported["id"]])
    assert response.status_code == 422
    with SessionLocal() as db:
        assert not db.scalars(select(Question)).all()


def test_short_answers_only_are_self_check_not_zero_grade(client, create_learner):
    headers, book, _, point = _scope(client, create_learner)
    generated = _generate(
        client, headers, book, question_types=["short_answer"], knowledge_point_ids=[point["id"]]
    )
    assert generated.status_code == 201, generated.text
    paper = generated.json()
    result = client.post(
        f"/api/v1/exams/{paper['id']}/submit", headers=headers, json={"answers": []}
    ).json()
    assert result["pending_count"] == 5
    assert result["wrong_count"] == result["correct_count"] == 0
    assert result["graded_total_score"] == 0
    assert result["status"] == "pending_self_check"
    assert client.get("/api/v1/learning/mastery", headers=headers).json()["total"] == 0
    assert client.get("/api/v1/learning/wrong-questions", headers=headers).json()["total"] == 0
    detail = client.get(f"/api/v1/learning/exams/{result['id']}", headers=headers).json()
    assert detail["pending_count"] == 5 and detail["graded_total_score"] == 0


def test_point_outside_selected_chapter_does_not_expand_scope(client, create_learner):
    headers, book, _, point = _scope(client, create_learner)
    other_chapter = client.post(
        f"/api/v1/textbooks/{book['id']}/chapters", headers=headers, json={"title": "绝对值"}
    ).json()
    response = _generate(
        client, headers, book, chapter_ids=[other_chapter["id"]], knowledge_point_ids=[point["id"]]
    )
    assert response.status_code == 422
    with SessionLocal() as db:
        assert not db.scalars(select(Question)).all()
