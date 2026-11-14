from desktop_helpers import RunningDesktop


def test_independent_import_practice_and_restart(tmp_path):
    space = tmp_path / "learner"
    service = RunningDesktop(space)
    path = "/api/v1"
    rows = [
        {"question_type": "true_false", "stem": "0 是正数吗？", "correct_answer": False},
        {"question_type": "multiple_choice", "stem": "哪些是偶数？", "options": [
            {"key": "A", "text": "2"}, {"key": "B", "text": "4"}, {"key": "C", "text": "5"}],
         "correct_answer": ["A", "B"]},
    ]
    try:
        def upload(questions, **kw):
            return service.request("POST", path + "/questions/import", json={"questions": questions, **kw})
        assert upload([rows[0], {**rows[1], "correct_answer": ["Z"]}]).status_code == 422
        assert service.get(path + "/questions").json()["total"] == 0
        result = upload(rows)
        assert result.status_code == 201, result.text
        bank = result.json()["textbook_id"]
        assert result.json()["imported"] == 2
        assert upload(rows).json()["skipped"] == 2
        assert service.get(path + "/textbooks").json()["total"] == 0
        assert service.get(path + "/learning/dashboard").json()["textbook_count"] == 0
        assert service.get(path + "/textbooks?include_question_bank=true").json()["items"][0]["id"] == bank
        paper = service.request("POST", path + "/exams/generate", json={"textbook_id": bank, "question_count": 2})
        assert paper.status_code == 201, paper.text
        questions = paper.json()["questions"]
        answers = [{"question_id": q["id"], "answer": False if q["question_type"] == "true_false" else ["A", "B"]} for q in questions]
        result = service.request("POST", path + f"/exams/{paper.json()['id']}/submit", json={"answers": answers, "duration_seconds": 8})
        assert result.status_code == 201, result.text
        assert result.json()["correct_count"] == 2
        manual = service.request("POST", path + "/questions", json={**rows[0], "stem": "1 是奇数吗？", "correct_answer": True, "status": "approved"})
        assert manual.status_code == 201 and manual.json()["textbook_id"] == bank, manual.text
        assert upload(rows, textbook_id=987654).status_code in (404, 422)
    finally:
        service.close()
    reopened = RunningDesktop(space)
    try:
        assert reopened.get(path + "/questions").json()["total"] == 3
    finally:
        reopened.close()
