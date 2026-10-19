from sqlalchemy import select

from app.database import SessionLocal
from app.models import ExamPaper, LocalKnowledgePoint, Question


def test_readable_book_needs_no_manual_knowledge_points(client, create_learner):
    headers = create_learner('reader@example.com')
    book = client.post('/api/v1/textbooks', headers=headers,
                       json={'title': '数学', 'subject': '数学'}).json()
    client.post('/api/v1/rag/chunks', headers=headers,
                params={'textbook_id': book['id'], 'content': '绝对值是到原点的距离'})
    result = client.post(f"/api/v1/textbooks/{book['id']}/publish", headers=headers)
    assert result.status_code == 200


def test_empty_math_book_can_start_basic_practice(client, create_learner):
    headers = create_learner('practice@example.com')
    book = client.post('/api/v1/textbooks', headers=headers,
                       json={'title': '数学七上', 'subject': '数学'}).json()
    chapter = client.post(f"/api/v1/textbooks/{book['id']}/chapters", headers=headers,
                          json={'title': '1.2.4 绝对值'}).json()
    payload = {'textbook_id': book['id'], 'chapter_ids': [chapter['id']],
               'question_count': 5, 'auto_fill': True}
    result = client.post('/api/v1/exams/generate', headers=headers, json=payload)
    assert result.status_code == 201, result.text
    paper = result.json()
    assert len(paper['questions']) == 5
    assert all('correct_answer' not in q for q in paper['questions'])
    with SessionLocal() as db:
        questions = db.scalars(select(Question).where(Question.textbook_id == book['id'])).all()
        assert len(questions) == 5
        assert all(q.source == 'generated_template' and q.chapter_id == chapter['id'] for q in questions)
        answers = [{'question_id': q.id, 'answer': q.correct_answer} for q in questions]
    score = client.post(f"/api/v1/exams/{paper['id']}/submit", headers=headers,
                        json={'answers': answers})
    assert score.status_code == 201 and score.json()['correct_count'] == 4
    assert score.json()['pending_count'] == 1
    assert score.json()['score'] == score.json()['graded_total_score'] == 20
    again = client.post('/api/v1/exams/generate', headers=headers, json=payload)
    assert again.status_code == 201
    with SessionLocal() as db:
        assert len(db.scalars(select(Question).where(Question.textbook_id == book['id'])).all()) == 5
    other = create_learner('visitor@example.com')
    assert client.post('/api/v1/exams/generate', headers=other, json=payload).status_code == 404


def test_unsupported_book_explains_no_questions_without_inventing(client, create_learner):
    headers = create_learner('language@example.com')
    book = client.post('/api/v1/textbooks', headers=headers,
                       json={'title': '语文', 'subject': '语文'}).json()
    result = client.post('/api/v1/exams/generate', headers=headers,
                         json={'textbook_id': book['id'], 'auto_fill': True, 'question_count': 5})
    assert result.status_code == 422
    assert '暂不支持' in result.json()['detail']


def test_failed_fill_reports_only_saved_questions_and_leaves_no_partial_data(client, create_learner):
    headers = create_learner('limited@example.com')
    book = client.post('/api/v1/textbooks', headers=headers,
                       json={'title': '数学', 'subject': '数学'}).json()
    client.post(f"/api/v1/textbooks/{book['id']}/chapters", headers=headers,
                json={'title': '余角和补角'})
    result = client.post('/api/v1/exams/generate', headers=headers, json={
        'textbook_id': book['id'], 'auto_fill': True, 'question_count': 100, 'random_seed': 7,
        'question_types': ['fill_blank'],
    })
    assert result.status_code == 422
    assert '当前已有 0 道' in result.json()['detail']
    with SessionLocal() as db:
        assert db.scalar(select(Question)) is None
        assert db.scalar(select(ExamPaper)) is None
        assert db.scalar(select(LocalKnowledgePoint)) is None


def test_parent_chapter_practice_includes_children(client, create_learner):
    headers = create_learner('parent@example.com')
    book = client.post('/api/v1/textbooks', headers=headers,
                       json={'title': '数学', 'subject': '数学'}).json()
    parent = client.post(f"/api/v1/textbooks/{book['id']}/chapters", headers=headers,
                         json={'title': '第一章 有理数'}).json()
    child = client.post(f"/api/v1/textbooks/{book['id']}/chapters", headers=headers,
                        json={'title': '绝对值', 'parent_id': parent['id']}).json()
    result = client.post('/api/v1/exams/generate', headers=headers, json={
        'textbook_id': book['id'], 'chapter_ids': [parent['id']],
        'auto_fill': True, 'question_count': 5,
    })
    assert result.status_code == 201
    with SessionLocal() as db:
        assert all(q.chapter_id == child['id'] for q in db.scalars(select(Question)))
