def test_learner_can_build_and_confirm_textbook_structure(client, create_learner):
    headers = create_learner("author@example.com")
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


def test_every_learner_can_create_a_personal_textbook(client, create_learner):
    headers = create_learner("new-reader@example.com")
    response = client.post(
        "/api/v1/textbooks",
        headers=headers,
        json={"title": "我的教材", "subject": "数学"},
    )
    assert response.status_code == 201
    listed = client.get("/api/v1/textbooks", headers=headers)
    assert [item["title"] for item in listed.json()["items"]] == ["我的教材"]
