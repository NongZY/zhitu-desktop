from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def _create_user_and_login(client, email: str, role: UserRole) -> dict[str, str]:
    with SessionLocal() as db:
        db.add(
            User(
                email=email,
                name=role.value,
                role=role,
                hashed_password=hash_password("Learning123!"),
            )
        )
        db.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Learning123!"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_exam_submission_scores_answers_and_drives_adaptive_weights(client):
    teacher_headers = _create_user_and_login(client, "teacher@example.com", UserRole.teacher)
    student_headers = _create_user_and_login(client, "student@example.com", UserRole.student)

    textbook = client.post(
        "/api/v1/textbooks",
        headers=teacher_headers,
        json={"title": "七年级数学", "subject": "数学", "grade": "七年级"},
    ).json()
    chapter = client.post(
        f"/api/v1/textbooks/{textbook['id']}/chapters",
        headers=teacher_headers,
        json={"title": "有理数", "order_index": 1},
    ).json()
    weak_kp = client.post(
        f"/api/v1/chapters/{chapter['id']}/knowledge-points",
        headers=teacher_headers,
        json={"name": "有理数加法"},
    ).json()
    strong_kp = client.post(
        f"/api/v1/chapters/{chapter['id']}/knowledge-points",
        headers=teacher_headers,
        json={"name": "有理数减法"},
    ).json()

    weak_question = client.post(
        "/api/v1/questions",
        headers=teacher_headers,
        json={
            "textbook_id": textbook["id"],
            "chapter_id": chapter["id"],
            "knowledge_point_id": weak_kp["id"],
            "question_type": "single_choice",
            "stem": "1 + (-2) = ?",
            "options": ["-1", "1", "-3", "3"],
            "correct_answer": "-1",
            "difficulty": 3,
            "status": "approved",
        },
    ).json()
    strong_question = client.post(
        "/api/v1/questions",
        headers=teacher_headers,
        json={
            "textbook_id": textbook["id"],
            "chapter_id": chapter["id"],
            "knowledge_point_id": strong_kp["id"],
            "question_type": "fill_blank",
            "stem": "3 - 5 = ____",
            "correct_answer": "-2",
            "difficulty": 3,
            "status": "approved",
        },
    ).json()

    paper = client.post(
        "/api/v1/exams/generate",
        headers=student_headers,
        json={
            "textbook_id": textbook["id"],
            "question_count": 2,
            "mode": "random",
            "score_per_question": 5,
        },
    )
    assert paper.status_code == 201
    paper_id = paper.json()["id"]

    result = client.post(
        f"/api/v1/exams/{paper_id}/submit",
        headers=student_headers,
        json={
            "answers": [
                {"question_id": weak_question["id"], "answer": "1"},
                {"question_id": strong_question["id"], "answer": " -2 "},
            ]
        },
    )
    assert result.status_code == 201
    assert result.json()["score"] == 5
    assert result.json()["correct_count"] == 1
    assert result.json()["wrong_count"] == 1

    wrong_book = client.get("/api/v1/learning/wrong-questions", headers=student_headers).json()
    assert wrong_book["total"] == 1
    assert wrong_book["items"][0]["question_id"] == weak_question["id"]

    adaptive = client.post(
        "/api/v1/exams/generate",
        headers=student_headers,
        json={
            "textbook_id": textbook["id"],
            "question_count": 1,
            "mode": "adaptive",
            "random_seed": 7,
        },
    )
    assert adaptive.status_code == 201
    weights = adaptive.json()["strategy"]["knowledge_point_weights"]
    assert weights[str(weak_kp["id"])] > weights[str(strong_kp["id"])]
