"""Real sidecar/API acceptance using synthetic, licensed fixtures only."""

import json
import time

import pymupdf
import pytest
from desktop_helpers import RunningDesktop


def sample_textbook() -> bytes:
    with pymupdf.open() as doc:
        for number in range(1, 25):
            page = doc.new_page(width=420, height=595)
            page.draw_rect(page.rect, color=None, fill=(0.94, 0.98, 1))
            page.insert_text(
                (35, 60), f"Chapter {(number - 1) // 12 + 1} - page {number}", fontsize=16
            )
            page.insert_text((35, 100), "Addition: 2 + 2 = 4. Powers: (-1)^4 = 1.", fontsize=12)
            page.draw_circle((200, 200), 40, color=(0.2, 0.3, 0.8), fill=(0.8, 0.9, 1))
        doc.set_toc([[1, "Addition", 1], [1, "Powers", 13]])
        return doc.tobytes()


def test_import_read_practice_restart_and_preserve_wrong_book(tmp_path):
    folder = tmp_path / "space"
    service = RunningDesktop(folder)
    try:
        owner = service.ready["context"]["workspace"]
        response = service.request(
            "POST", "/api/v1/textbooks", json={"title": "Synthetic textbook", "subject": "测试"}
        )
        assert response.status_code == 201, response.text
        book_id = response.json()["id"]
        response = service.request(
            "POST",
            f"/api/v1/textbooks/{book_id}/upload",
            files={"file": ("synthetic.pdf", sample_textbook(), "application/pdf")},
        )
        assert response.status_code == 202, response.text
        task_id = response.json()["id"]
        deadline = time.monotonic() + 15
        while True:
            task = service.get(f"/api/v1/import-tasks/{task_id}").json()
            if task["status"] in {"completed", "failed"} or time.monotonic() > deadline:
                break
            time.sleep(0.05)
        assert task["status"] == "completed", task
        assert task["progress"] == 100
        structure = service.get(f"/api/v1/textbooks/{book_id}/structure").json()
        assert len(structure["chapters"]) >= 2
        reader = service.get(f"/api/v1/textbooks/{book_id}/reader").json()
        assert reader["page_count"] == 24
        image_path = f"/api/v1/textbooks/{book_id}/pages/15/image"
        assert service.get(image_path, authenticated=False).status_code == 403
        assert service.get(image_path).content.startswith(b"\x89PNG\r\n\x1a\n")
        saved = service.request(
            "PUT",
            f"/api/v1/learning/reading-progress/{book_id}",
            json=dict(
                page_number=15,
                chapter_id=None,
                document_revision=reader["document_revision"],
                expected_revision=0,
            ),
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["page_number"] == 15
        question = service.request(
            "POST",
            "/api/v1/questions",
            json=dict(
                textbook_id=book_id,
                question_type="single_choice",
                stem="2 + 2 = ?",
                options={"A": "4", "B": "5"},
                correct_answer="A",
                status="approved",
                explanation="Addition gives 4.",
                difficulty=1,
            ),
        )
        assert question.status_code == 201, question.text
        paper = service.request(
            "POST",
            "/api/v1/exams/generate",
            json=dict(
                textbook_id=book_id,
                question_count=1,
                question_types=["single_choice"],
                auto_fill=False,
            ),
        )
        assert paper.status_code == 201, paper.text
        paper_id = paper.json()["id"]
        result = service.request(
            "POST",
            f"/api/v1/exams/{paper_id}/submit",
            json=dict(
                duration_seconds=10, answers=[dict(question_id=question.json()["id"], answer="B")]
            ),
        )
        assert result.status_code == 201, result.text
        assert result.json()["wrong_count"] == 1
        record_id = result.json()["id"]
        old_token = service.token
    finally:
        service.close()

    restarted = RunningDesktop(folder)
    try:
        assert restarted.ready["context"]["workspace"] == owner
        assert restarted.token != old_token
        assert (
            restarted.get("/health", headers={"X-ZhiTu-Desktop-Token": old_token}).status_code
            == 403
        )
        progress = restarted.get(f"/api/v1/learning/reading-progress/{book_id}").json()["progress"]
        assert progress["page_number"] == 15
        assert progress["document_revision"] == reader["document_revision"]
        assert (
            restarted.get("/api/v1/learning/home").json()["continue_reading"]["page_number"] == 15
        )
        assert restarted.get("/api/v1/learning/wrong-questions").json()["total"] == 1
        detail = restarted.get(f"/api/v1/learning/exams/{record_id}").json()
        assert detail["details"][0]["user_answer"] == "B"
    finally:
        restarted.close()


@pytest.mark.parametrize("problem", [PermissionError("read only"), OSError(28, "disk full")])
def test_failed_workspace_publish_does_not_replace_existing_data(tmp_path, monkeypatch, problem):
    from app.database import Base
    from app.desktop import workspace
    from app.models import User
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    engine = create_engine(f"sqlite:///{(tmp_path / 'learning.db').as_posix()}")
    Base.metadata.create_all(engine)
    manifest = tmp_path / "workspace.json"
    with Session(engine) as db:
        identity = workspace.ensure_workspace(db, manifest)
        initial = json.loads(manifest.read_text())
        # Simulate the recoverable window after DB commit, before final manifest publish.
        initial["ownerId"] = None
        manifest.write_text(json.dumps(initial))
        original = manifest.read_bytes()

        def fail(*args):
            raise problem

        monkeypatch.setattr(workspace.os, "replace", fail)
        with pytest.raises(OSError):
            workspace.ensure_workspace(db, manifest)
        assert manifest.read_bytes() == original
        assert list(db.scalars(select(User.id))) == [identity.owner_id]
    engine.dispose()
