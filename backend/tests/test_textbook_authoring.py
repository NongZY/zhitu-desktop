from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def _teacher_headers(client) -> dict[str, str]:
    with SessionLocal() as db:
        db.add(
            User(
                email="teacher@example.com",
                name="测试教师",
                role=UserRole.teacher,
                hashed_password=hash_password("Learning123!"),
            )
        )
        db.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "teacher@example.com", "password": "Learning123!"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_teacher_can_build_and_publish_textbook_structure(client):
    headers = _teacher_headers(client)
    textbook = client.post(
        "/api/v1/textbooks",
        headers=headers,
        json={"title": "七年级数学", "subject": "数学", "grade": "七年级"},
    )
    assert textbook.status_code == 201
    textbook_id = textbook.json()["id"]

    empty_publish = client.post(f"/api/v1/textbooks/{textbook_id}/publish", headers=headers)
    assert empty_publish.status_code == 422

    chapter = client.post(
        f"/api/v1/textbooks/{textbook_id}/chapters",
        headers=headers,
        json={"title": "第一章 有理数", "page_start": 1, "page_end": 20},
    )
    assert chapter.status_code == 201
    chapter_id = chapter.json()["id"]

    no_point_publish = client.post(f"/api/v1/textbooks/{textbook_id}/publish", headers=headers)
    assert no_point_publish.status_code == 422

    point = client.post(
        f"/api/v1/chapters/{chapter_id}/knowledge-points",
        headers=headers,
        json={"name": "相反数", "description": "理解互为相反数的两个数"},
    )
    assert point.status_code == 201
    assert point.json()["global_knowledge_point_id"] is not None

    published = client.post(f"/api/v1/textbooks/{textbook_id}/publish", headers=headers)
    assert published.status_code == 200
    assert published.json()["parse_status"] == "ready"

    structure = client.get(f"/api/v1/textbooks/{textbook_id}/structure", headers=headers)
    assert structure.status_code == 200
    assert structure.json()["chapters"][0]["knowledge_points"][0]["name"] == "相反数"

    listed = client.get("/api/v1/textbooks", headers=headers)
    assert listed.status_code == 200
    summary = listed.json()["items"][0]
    assert summary["chapter_count"] == 1
    assert summary["knowledge_point_count"] == 1
    assert summary["question_count"] == 0


def test_student_cannot_create_textbook(client):
    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": "student@example.com",
            "password": "Learning123!",
            "name": "学生",
            "role": "student",
        },
    )
    assert register.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "Learning123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = client.post(
        "/api/v1/textbooks",
        headers=headers,
        json={"title": "无权限教材", "subject": "数学"},
    )
    assert response.status_code == 403
