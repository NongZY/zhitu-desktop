from app.database import SessionLocal
from app.models import User, UserMastery, UserRole
from app.security import hash_password


def _login(client, email: str, role: UserRole) -> dict[str, str]:
    with SessionLocal() as db:
        db.add(
            User(email=email, name=email, role=role, hashed_password=hash_password("Learning123!"))
        )
        db.commit()
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Learning123!"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_two_questions_for_same_point_update_one_mastery_row(client):
    teacher = _login(client, "mastery-teacher@example.com", UserRole.teacher)
    student = _login(client, "mastery-student@example.com", UserRole.student)
    book = client.post(
        "/api/v1/textbooks", headers=teacher, json={"title": "测试教材", "subject": "数学"}
    ).json()
    chapter = client.post(
        f"/api/v1/textbooks/{book['id']}/chapters", headers=teacher, json={"title": "第一章"}
    ).json()
    point = client.post(
        f"/api/v1/chapters/{chapter['id']}/knowledge-points",
        headers=teacher,
        json={"name": "同一知识点"},
    ).json()
    question_ids = []
    for index in range(2):
        question = client.post(
            "/api/v1/questions",
            headers=teacher,
            json={
                "textbook_id": book["id"],
                "chapter_id": chapter["id"],
                "knowledge_point_id": point["id"],
                "question_type": "fill_blank",
                "stem": f"题目 {index + 1}",
                "correct_answer": "1",
                "status": "approved",
            },
        ).json()
        question_ids.append(question["id"])
    paper = client.post(
        "/api/v1/exams/generate",
        headers=student,
        json={"textbook_id": book["id"], "question_count": 2, "random_seed": 1},
    ).json()
    response = client.post(
        f"/api/v1/exams/{paper['id']}/submit",
        headers=student,
        json={
            "answers": [{"question_id": question_id, "answer": "1"} for question_id in question_ids]
        },
    )
    assert response.status_code == 201
    with SessionLocal() as db:
        rows = db.query(UserMastery).all()
        assert len(rows) == 1
        assert rows[0].attempts == 2
