def _build_personal_material(client, headers: dict[str, str]) -> dict[str, int]:
    textbook_response = client.post(
        "/api/v1/textbooks",
        headers=headers,
        json={"title": "个人代数教材", "subject": "数学", "grade": "七年级"},
    )
    assert textbook_response.status_code == 201
    textbook_id = textbook_response.json()["id"]

    chapter_response = client.post(
        f"/api/v1/textbooks/{textbook_id}/chapters",
        headers=headers,
        json={"title": "第一章 方程"},
    )
    assert chapter_response.status_code == 201
    chapter_id = chapter_response.json()["id"]

    point_response = client.post(
        f"/api/v1/chapters/{chapter_id}/knowledge-points",
        headers=headers,
        json={"name": "一元一次方程"},
    )
    assert point_response.status_code == 201
    point = point_response.json()

    question_response = client.post(
        "/api/v1/questions",
        headers=headers,
        json={
            "textbook_id": textbook_id,
            "chapter_id": chapter_id,
            "knowledge_point_id": point["id"],
            "question_type": "fill_blank",
            "stem": "x + 2 = 5，则 x = ____。",
            "correct_answer": "3",
            "status": "approved",
        },
    )
    assert question_response.status_code == 201

    chunk_response = client.post(
        "/api/v1/rag/chunks",
        headers=headers,
        params={
            "textbook_id": textbook_id,
            "chapter_id": chapter_id,
            "content": "一元一次方程只含一个未知数，且未知数的次数是一次。",
            "page_number": 8,
        },
    )
    assert chunk_response.status_code == 201
    return {
        "textbook_id": textbook_id,
        "chapter_id": chapter_id,
        "point_id": point["id"],
        "global_point_id": point["global_knowledge_point_id"],
        "question_id": question_response.json()["id"],
    }


def test_personal_library_and_learning_data_are_isolated(client, create_learner):
    owner = create_learner("owner@example.com", "教材所有者")
    visitor = create_learner("visitor@example.com", "另一位学习者")
    resources = _build_personal_material(client, owner)

    owner_books = client.get("/api/v1/textbooks", headers=owner)
    visitor_books = client.get("/api/v1/textbooks", headers=visitor)
    assert owner_books.json()["total"] == 1
    assert visitor_books.json()["total"] == 0

    private_gets = [
        f"/api/v1/textbooks/{resources['textbook_id']}",
        f"/api/v1/textbooks/{resources['textbook_id']}/structure",
        f"/api/v1/questions/{resources['question_id']}",
    ]
    for path in private_gets:
        assert client.get(path, headers=visitor).status_code == 404

    assert (
        client.patch(
            f"/api/v1/textbooks/{resources['textbook_id']}",
            headers=visitor,
            json={"title": "不能修改"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/textbooks/{resources['textbook_id']}/chapters",
            headers=visitor,
            json={"title": "不能添加"},
        ).status_code
        == 404
    )

    visitor_questions = client.get("/api/v1/questions", headers=visitor)
    assert visitor_questions.json()["total"] == 0
    assert (
        client.post(
            "/api/v1/rag/ask",
            headers=visitor,
            json={
                "textbook_id": resources["textbook_id"],
                "question": "什么是一元一次方程？",
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/exams/generate",
            headers=visitor,
            json={"textbook_id": resources["textbook_id"], "question_count": 1},
        ).status_code
        == 404
    )

    visitor_dashboard = client.get("/api/v1/learning/dashboard", headers=visitor).json()
    visitor_path = client.get("/api/v1/learning/path", headers=visitor).json()
    assert visitor_dashboard["textbook_count"] == 0
    assert visitor_path == {"nodes": [], "edges": []}

    owner_answer = client.post(
        "/api/v1/rag/ask",
        headers=owner,
        json={
            "textbook_id": resources["textbook_id"],
            "question": "什么是一元一次方程？",
        },
    )
    assert owner_answer.status_code == 200
    assert owner_answer.json()["grounded"] is True


def test_registration_exposes_no_role_and_all_accounts_have_equal_capabilities(
    client, create_learner
):
    first = create_learner("first@example.com")
    second = create_learner("second@example.com")

    first_profile = client.get("/api/v1/auth/me", headers=first).json()
    second_profile = client.get("/api/v1/auth/me", headers=second).json()
    assert "role" not in first_profile
    assert "role" not in second_profile

    for headers, title in ((first, "第一本个人教材"), (second, "第二本个人教材")):
        response = client.post(
            "/api/v1/textbooks",
            headers=headers,
            json={"title": title, "subject": "通识"},
        )
        assert response.status_code == 201
        own_titles = [
            item["title"]
            for item in client.get("/api/v1/textbooks", headers=headers).json()["items"]
        ]
        assert own_titles == [title]
