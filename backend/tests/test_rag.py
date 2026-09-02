from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def _login(client, email: str, role: UserRole) -> dict[str, str]:
    with SessionLocal() as db:
        db.add(
            User(
                email=email,
                name="tester",
                role=role,
                hashed_password=hash_password("Learning123!"),
            )
        )
        db.commit()
    token = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Learning123!"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_rag_answer_is_grounded_in_a_textbook_chunk(client):
    teacher = _login(client, "teacher-rag@example.com", UserRole.teacher)
    student = _login(client, "student-rag@example.com", UserRole.student)
    textbook = client.post(
        "/api/v1/textbooks",
        headers=teacher,
        json={"title": "数学", "subject": "数学"},
    ).json()
    client.post(
        "/api/v1/rag/chunks",
        headers=teacher,
        params={
            "textbook_id": textbook["id"],
            "content": "三角形的内角和等于180度。",
            "page_number": 12,
        },
    )
    response = client.post(
        "/api/v1/rag/ask",
        headers=student,
        json={"question": "三角形的内角和是多少？", "textbook_id": textbook["id"]},
    )
    assert response.status_code == 200
    assert response.json()["grounded"] is True
    assert response.json()["citations"][0]["page_number"] == 12
    assert "180" in response.json()["answer"]
