"""End-to-end desktop flow with synthetic material and an isolated learning space."""
import time
from uuid import uuid4

from desktop_helpers import RunningDesktop


def wait_until(service, path, terminal):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        result = service.get(path).json()
        if result['status'] in terminal:
            return result
        time.sleep(.05)
    raise AssertionError(result)


def test_desktop_ai_local_fill_exam_and_backup_restore(tmp_path):
    root = tmp_path / 'core-space'
    service = RunningDesktop(root)
    try:
        settings = service.request('PUT', '/api/v1/settings/ai', json={'base_url': 'http://127.0.0.1:1/v1',
            'model': 'synthetic', 'api_key': 'synthetic-test-key', 'qa_enabled': False, 'practice_enabled': False}).json()
        assert settings['key_configured'] and 'synthetic-test-key' not in str(settings)
        book = service.request('POST', '/api/v1/textbooks', json={'title': '合成数学教材', 'subject': '数学'}).json()['id']
        body = '# 数轴\n绝对值表示数轴上一个数对应的点到原点的距离。\n相反数是只有符号不同的两个数，它们的和为0。'
        upload = service.request('POST', f'/api/v1/textbooks/{book}/upload', files={'file': ('core.md', body.encode(), 'application/octet-stream')})
        assert upload.status_code == 202, upload.text
        assert wait_until(service, '/api/v1/import-tasks/' + upload.json()['id'], {'completed', 'failed'})['status'] == 'completed'
        job = service.request('POST', f'/api/v1/textbooks/{book}/practice/jobs', json={
            'request_id': str(uuid4()), 'mode': 'rules', 'count': 5,
            'question_types': ['single_choice', 'multiple_choice', 'true_false', 'fill_blank', 'short_answer']})
        assert job.status_code == 202, job.text
        job = wait_until(service, '/api/v1/practice/jobs/' + job.json()['id'], {'completed', 'partial', 'failed'})
        assert job['status'] == 'completed' and len(job['candidates']) == 5, job
        ids = [row['id'] for row in job['candidates']]
        assert service.request('POST', f"/api/v1/practice/jobs/{job['id']}/confirm", json={'candidate_ids': ids}).status_code == 200
        job = service.get('/api/v1/practice/jobs/' + job['id']).json()
        answers = [{'question_id': row['saved_question_id'], 'answer': row['question']['correct_answer']} for row in job['candidates']]
        paper = service.request('POST', '/api/v1/exams/generate', json={
            'textbook_id': book, 'question_count': 5, 'question_types': ['single_choice', 'multiple_choice', 'true_false', 'fill_blank', 'short_answer'], 'auto_fill': False})
        assert paper.status_code == 201, paper.text
        result = service.request('POST', f"/api/v1/exams/{paper.json()['id']}/submit", json={'duration_seconds': 60, 'answers': answers})
        assert result.status_code == 201, result.text
        assert result.json()['correct_count'] == 4 and result.json()['pending_count'] == 1
        record_id = result.json()['id']
        local = service.request('POST', '/api/v1/rag/ask', json={'textbook_id': book, 'question': '绝对值是什么？'}).json()
        assert local['mode'] == 'local' and local['citations']
        backup = service.request('POST', '/api/v1/maintenance/backups')
        assert backup.status_code == 201, backup.text
        archive = service.get('/api/v1/maintenance/backups/' + backup.json()['id']).content
        restore = service.request('POST', '/api/v1/maintenance/restores', files={'file': ('backup.zip', archive, 'application/zip')})
        assert restore.status_code == 201, restore.text
        assert restore.json()['counts'] == {'textbooks': 1, 'questions': 5, 'exam_records': 1}
        assert service.request('POST', f"/api/v1/maintenance/restores/{restore.json()['id']}/confirm").status_code == 200
    finally:
        service.close()
    service = RunningDesktop(root)
    try:
        doc = service.get(f'/api/v1/textbooks/{book}/document').json()
        assert doc['format'] == 'md' and doc['is_current']
        assert '距离' in str(doc)
        evidence = service.get(f"/api/v1/questions/{answers[0]['question_id']}/evidence").json()['evidence'][0]
        assert evidence['locator']['rendition_revision'] == doc['rendition_revision']
        record = service.get(f'/api/v1/learning/exams/{record_id}').json()
        assert len(record['details']) == 5 and all(row['snapshot_verified'] for row in record['details'])
        assert service.get('/api/v1/settings/ai').json()['key_configured']  # settings stay local to this PC, outside restored data
    finally:
        service.close()
