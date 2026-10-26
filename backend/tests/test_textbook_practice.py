from uuid import uuid4

import pytest

from app.config import settings
from tests.test_documents import new_book, upload


TYPES = ['single_choice', 'multiple_choice', 'true_false', 'fill_blank', 'short_answer']
BODY = '# 数轴\n绝对值表示数轴上一个数对应的点到原点的距离。\n相反数是只有符号不同的两个数，它们的和为0。'


@pytest.fixture
def material(client, create_learner, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path))
    headers = create_learner('practice-content@example.com')
    book = new_book(client, headers)
    assert upload(client, headers, book, 'body.md', BODY.encode()).status_code == 202
    return headers, book


def start(client, headers, book, **changes):
    payload = dict(request_id=str(uuid4()), mode='rules', count=5, question_types=TYPES)
    payload.update(changes)
    response = client.post(f'/api/v1/textbooks/{book}/practice/jobs', headers=headers, json=payload)
    assert response.status_code == 202, response.text
    job_id = response.json()['id']
    result = client.get(f'/api/v1/practice/jobs/{job_id}', headers=headers)
    assert result.status_code == 200, result.text
    return payload, result.json()


def test_body_drives_five_types_and_candidates_need_idempotent_confirmation(client, material):
    headers, book = material
    coverage = client.get(f'/api/v1/textbooks/{book}/practice/coverage', headers=headers)
    assert coverage.status_code == 200, coverage.text
    assert coverage.json()['ready_questions'] == 0
    payload, job = start(client, headers, book)
    assert job['status'] == 'completed'
    candidates = job['candidates']
    assert {row['question']['question_type'] for row in candidates} == set(TYPES)
    assert all(row['evidence'][0]['locator']['kind'] == 'block' for row in candidates)
    assert client.get('/api/v1/questions', headers=headers).json()['total'] == 0
    repeated = client.post(f'/api/v1/textbooks/{book}/practice/jobs', headers=headers, json=payload)
    assert repeated.json()['id'] == job['id']
    ids = [row['id'] for row in candidates]
    for _ in range(2):
        saved = client.post(f"/api/v1/practice/jobs/{job['id']}/confirm", headers=headers, json={'candidate_ids': ids})
        assert saved.status_code == 200, saved.text
    questions = client.get('/api/v1/questions', headers=headers).json()['items']
    assert len(questions) == 5 and all(q['status'] == 'approved' for q in questions)
    assert all(q['source'] == 'textbook_rules' for q in questions)
    source = client.get(f"/api/v1/questions/{questions[0]['id']}/evidence", headers=headers)
    assert source.status_code == 200 and source.json()['evidence']


def test_title_only_and_same_title_unrelated_body_never_trigger_math_templates(client, material):
    headers, book = material
    for content in ('# 绝对值', '# 绝对值\n这是一篇文学评论，介绍作者的创作经历。'):
        assert upload(client, headers, book, 'different.md', content.encode()).status_code == 202
        _, job = start(client, headers, book)
        assert not job['candidates'] and job['status'] in {'failed', 'partial'}
        assert job['message']


def test_replaced_source_and_deleted_chapter_cannot_confirm_stale_candidates(client, material):
    headers, book = material
    _, job = start(client, headers, book)
    ids = [row['id'] for row in job['candidates']]
    assert upload(client, headers, book, 'new.txt', '完全不同的教材内容'.encode()).status_code == 202
    response = client.post(f"/api/v1/practice/jobs/{job['id']}/confirm", headers=headers, json={'candidate_ids': ids})
    assert response.status_code == 409
    assert client.get('/api/v1/questions', headers=headers).json()['total'] == 0


def test_candidate_edit_validates_false_and_choice_answer_keys(client, material):
    headers, book = material
    _, job = start(client, headers, book)
    boolean = next(row for row in job['candidates'] if row['question']['question_type'] == 'true_false')
    modified = {**boolean['question'], 'correct_answer': False}
    response = client.patch(f"/api/v1/practice/candidates/{boolean['id']}", headers=headers, json=modified)
    assert response.status_code == 200 and response.json()['question']['correct_answer'] is False
    invalid = {**modified, 'correct_answer': 'false'}
    assert client.patch(f"/api/v1/practice/candidates/{boolean['id']}", headers=headers, json=invalid).status_code == 422
    choice = next(row for row in job['candidates'] if row['question']['question_type'] == 'single_choice')
    assert client.patch(f"/api/v1/practice/candidates/{choice['id']}", headers=headers,
                        json={**choice['question'], 'correct_answer': 'Z'}).status_code == 422


def test_all_chapters_include_tail_after_one_thousand_blocks(client, material):
    headers, book = material
    content = '# 第一章\n' + '\n'.join('没有数学定义的资料正文' for _ in range(1002)) + '\n# 最后一章\n' + BODY.split('\n', 1)[1]
    assert upload(client, headers, book, 'long.md', content.encode()).status_code == 202
    _, job = start(client, headers, book, count=1, question_types=['fill_blank'])
    assert len(job['units']) == 2
    assert any(unit['title'] == '最后一章' and unit['status'] == 'completed' for unit in job['units'])
    assert job['status'] == 'partial' and job['candidates']


def test_only_explicit_original_question_answers_are_extracted(client, material):
    headers, book = material
    content = '# 科学\n题目：水在标准大气压下的沸点是多少？\n答案：100℃\n解析：这是标准大气压下的数值。\n题目：没有给答案的题目？'
    assert upload(client, headers, book, 'science.md', content.encode()).status_code == 202
    _, job = start(client, headers, book, mode='extract', question_types=['short_answer'])
    assert len(job['candidates']) == 1
    assert job['candidates'][0]['question']['correct_answer'] == '100℃'
    assert job['candidates'][0]['method'] == 'textbook_original'


def test_exam_snapshot_preserves_question_and_grading_after_edit(client, material):
    headers, book = material
    chapter = client.get(f'/api/v1/textbooks/{book}/document', headers=headers).json()['chapters'][0]['id']
    point = client.post(f'/api/v1/chapters/{chapter}/knowledge-points', headers=headers,
                        json={'name': '正数和零'}).json()
    response = client.post('/api/v1/questions', headers=headers, json={
        'textbook_id': book, 'chapter_id': chapter, 'knowledge_point_id': point['id'],
        'question_type': 'true_false', 'stem': '0是正数。',
        'correct_answer': False, 'explanation': '0既不是正数也不是负数。', 'status': 'approved'})
    question = response.json()
    paper = client.post('/api/v1/exams/generate', headers=headers, json={
        'textbook_id': book, 'question_count': 1, 'question_types': ['true_false'], 'auto_fill': False}).json()
    assert client.put(f"/api/v1/questions/{question['id']}", headers=headers,
                      json={'stem': '修改后的不同问题', 'correct_answer': True, 'explanation': '后来修改的答案'}).status_code == 200
    frozen = client.get(f"/api/v1/exams/{paper['id']}", headers=headers).json()
    assert frozen['questions'][0]['stem'] == '0是正数。'
    result = client.post(f"/api/v1/exams/{paper['id']}/submit", headers=headers,
                         json={'answers': [{'question_id': question['id'], 'answer': False}]}).json()
    assert result['correct_count'] == 1 and result['details'][0]['correct_answer'] is False
    history = client.get(f"/api/v1/learning/exams/{result['id']}", headers=headers).json()
    assert history['details'][0]['stem'] == '0是正数。'
    assert history['details'][0]['correct_answer'] is False
    evidence = client.get(f"/api/v1/learning/knowledge-points/{point['global_knowledge_point_id']}", headers=headers).json()
    assert evidence['recent_answers'][0]['stem'] == '0是正数。'
    assert client.delete(f"/api/v1/questions/{question['id']}", headers=headers).status_code == 409
    assert client.delete(f'/api/v1/textbooks/{book}', headers=headers).status_code == 409


def test_deleted_chapter_and_other_owner_cannot_save_candidates(client, material, create_learner):
    headers, book = material
    _, job = start(client, headers, book)
    other = create_learner('another-practice@example.com')
    assert client.get(f"/api/v1/practice/jobs/{job['id']}", headers=other).status_code == 404
    chapter = job['candidates'][0]['chapter_id']
    assert client.delete(f'/api/v1/chapters/{chapter}', headers=headers).status_code == 204
    replacement = client.post(f'/api/v1/textbooks/{book}/chapters', headers=headers,
                              json={'title': '新建的无关章节', 'order_index': 0})
    assert replacement.status_code == 201
    assert client.post(f"/api/v1/practice/jobs/{job['id']}/confirm", headers=headers,
                       json={'candidate_ids': [job['candidates'][0]['id']]}).status_code == 409


def test_ai_partial_invalid_sources_and_error_stop_later_paid_batches(client, material, tmp_path):
    import asyncio
    import json
    import httpx
    from app.database import SessionLocal
    from app.models import Textbook
    from app.services.ai_connection import AIConnection
    from app.services.practice_content import JobCreate
    from app.services.textbook_practice import create_job, process_job, job_read

    headers, book_id = material
    good = dict(question_type='true_false', stem='绝对值表示到原点的距离。', options=None,
                correct_answer=True, explanation='根据教材定义。', difficulty=1, evidence_ids=['e1'])
    bad = {**good, 'stem': '无关资料', 'evidence_ids': ['another-book']}
    calls = []
    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({'questions': [good, bad]})}}]})
    connection = AIConnection(tmp_path / 'ai', transport=httpx.MockTransport(respond))
    connection.save(dict(base_url='https://ai.example/v1', model='test', api_key='fake-key',
                         qa_enabled=False, practice_enabled=True, privacy_ack=True))
    with SessionLocal() as db:
        book = db.get(Textbook, book_id)
        job, _ = create_job(db, book, book.owner_id, JobCreate(request_id=str(uuid4()), mode='ai',
            count=2, question_types=['true_false'], external_consent=True))
        job_id = job.id
    asyncio.run(process_job(job_id, connection))
    with SessionLocal() as db:
        from app.models import PracticeJob
        result = job_read(db, db.get(PracticeJob, job_id))
    assert result['status'] == 'partial' and len(result['candidates']) == 1
    assert 'another-book' not in json.dumps(result, default=str)
    sent = calls[0]['messages'][1]['content']
    assert '绝对值表示' in sent and 'hashed_password' not in sent
    assert 'source_revision' not in sent and 'managed_file' not in sent
    # A provider failure must stop the remaining chapter requests, not silently retry.
    assert upload(client, headers, book_id, 'two.md', (BODY + '\n# 第二章\n' + BODY.split('\n', 1)[1]).encode()).status_code == 202
    calls.clear()
    def limited(request):
        calls.append(request)
        return httpx.Response(429, json={'error': {'code': 'insufficient_quota'}})
    connection.transport = httpx.MockTransport(limited)
    with SessionLocal() as db:
        book = db.get(Textbook, book_id)
        job, _ = create_job(db, book, book.owner_id, JobCreate(request_id=str(uuid4()), mode='ai',
            count=1, question_types=['true_false']))
        job_id = job.id
    asyncio.run(process_job(job_id, connection))
    assert len(calls) == 1


def test_cancellation_stops_pending_ai_and_preserves_candidates(client, material, tmp_path):
    import asyncio
    import httpx
    from app.database import SessionLocal
    from app.models import Textbook, PracticeJob
    from app.services.ai_connection import AIConnection
    from app.services.practice_content import JobCreate
    from app.services.textbook_practice import create_job, process_job, cancel_job, job_read
    _, book_id = material

    async def scenario():
        entered = asyncio.Event()
        async def delayed(request):
            entered.set()
            await asyncio.sleep(20)
            pytest.fail('cancelled model response was allowed to finish')
        connection = AIConnection(tmp_path / 'cancel-ai', transport=httpx.MockTransport(delayed))
        connection.save(dict(base_url='https://ai.example/v1', model='test', api_key='fake',
                             practice_enabled=True, privacy_ack=True))
        with SessionLocal() as db:
            book = db.get(Textbook, book_id)
            job, _ = create_job(db, book, book.owner_id, JobCreate(request_id=str(uuid4()), mode='ai',
                                 count=1, question_types=['true_false']))
            job_id = job.id
        task = asyncio.create_task(process_job(job_id, connection))
        await entered.wait()
        with SessionLocal() as db:
            cancel_job(db, db.get(PracticeJob, job_id))
        await asyncio.wait_for(task, 1)
        with SessionLocal() as db:
            result = job_read(db, db.get(PracticeJob, job_id))
            assert result['status'] == 'cancelled' and not result['candidates']
    asyncio.run(scenario())
