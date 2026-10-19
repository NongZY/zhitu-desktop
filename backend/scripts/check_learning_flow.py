"""Check a deployed book without retaining questions, answers or mastery changes.

Run inside the backend container: python /tmp/check_learning_flow.py BOOK_ID.
The database must be PostgreSQL. All ASGI writes run inside an outer transaction
that is always rolled back. Sequence numbers may advance, but rows do not remain.
No credentials, textbook text or personal account details are printed.
"""

import asyncio
import sys

import httpx
from check_data_integrity import fingerprints
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models import Chapter, Question, Textbook, User
from app.security import create_access_token


async def main(book_id: int):
    assert engine.dialect.name == "postgresql", "This rollback check requires PostgreSQL"
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    def use_session():
        yield session

    try:
        before = fingerprints(connection)
        book = session.get(Textbook, book_id)
        assert book is not None
        user = session.get(User, book.owner_id)
        headers = {"Authorization": "Bearer " + create_access_token(user)}
        # Verify the actual frontend proxy and deployed read endpoints first.
        async with httpx.AsyncClient(base_url="http://frontend/api/v1", headers=headers) as site:
            result = await site.get(f"/textbooks/{book_id}/structure")
            assert result.status_code == 200
            assert result.json()["chapters"]
            print("LIVE_PROXY_AND_CHAPTERS=PASS")
        chapter = session.scalar(
            select(Chapter).where(
                Chapter.textbook_id == book_id,
                Chapter.title.contains("绝对值"),
            )
        )
        assert chapter is not None
        app.dependency_overrides[get_db] = use_session
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://check", headers=headers
        ) as client:
            result = await client.post(
                "/api/v1/exams/generate",
                json={
                    "textbook_id": book_id,
                    "chapter_ids": [chapter.id],
                    "auto_fill": True,
                    "question_count": 5,
                    "random_seed": 7,
                },
            )
            assert result.status_code == 201, result.status_code
            paper = result.json()
            assert len(paper["questions"]) == 5
            assert {q["question_type"] for q in paper["questions"]} == {
                "single_choice",
                "multiple_choice",
                "true_false",
                "fill_blank",
                "short_answer",
            }
            assert all("correct_answer" not in q for q in paper["questions"])
            answers = [
                {"question_id": q["id"], "answer": session.get(Question, q["id"]).correct_answer}
                for q in paper["questions"]
            ]
            result = await client.post(
                f"/api/v1/exams/{paper['id']}/submit", json={"answers": answers}
            )
            assert result.status_code == 201
            scored = result.json()
            assert scored["correct_count"] == 4
            assert scored["wrong_count"] == 0
            assert scored["pending_count"] == 1
            assert scored["score"] == scored["graded_total_score"] == 20
            detail = await client.get(f"/api/v1/learning/exams/{scored['id']}")
            assert detail.status_code == 200
            assert len(detail.json()["details"]) == 5
            assert detail.json()["pending_count"] == 1
            history = await client.get("/api/v1/learning/exams?page_size=1")
            assert history.status_code == 200 and len(history.json()["items"]) == 1
            point_id = next(
                item["global_knowledge_point_id"]
                for item in detail.json()["details"]
                if item["global_knowledge_point_id"]
            )
            point = await client.get(f"/api/v1/learning/knowledge-points/{point_id}")
            assert point.status_code == 200 and point.json()["mappings"]
            mapping = next(
                item for item in point.json()["mappings"] if item["textbook_id"] == book_id
            )
            targeted = await client.post(
                "/api/v1/exams/generate",
                json={
                    "textbook_id": book_id,
                    "knowledge_point_ids": [mapping["local_knowledge_point_id"]],
                    "auto_fill": True,
                    "question_types": ["true_false"],
                    "question_count": 3,
                },
            )
            assert targeted.status_code == 201, targeted.text
            assert all(
                q["knowledge_point_id"] == mapping["local_knowledge_point_id"]
                and q["question_type"] == "true_false"
                for q in targeted.json()["questions"]
            )
            duplicate = await client.post(
                f"/api/v1/exams/{paper['id']}/submit", json={"answers": answers}
            )
            assert duplicate.status_code == 409
            print("DEPLOYED_ASGI_MIXED_TYPES_GRADING_DETAILS_AND_TARGETED_PRACTICE=PASS")
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        transaction.rollback()
        connection.close()
    with engine.connect() as verify:
        assert fingerprints(verify) == before
        print("NO_PERSISTED_TEST_ROWS=PASS")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))
