"""Exercise the shipped desktop profile and queue, not eager legacy web mode."""
import time

from desktop_helpers import RunningDesktop
from tests.test_document_parser import docx_bytes, pptx_bytes


def test_local_document_import_search_and_restart(tmp_path):
    service = RunningDesktop(tmp_path / 'learning-space')
    saved = []
    try:
        for name, content, term in [('教材.docx', docx_bytes(), '第一章'),
                                    ('课件.pptx', pptx_bytes(), '幻灯片'),
                                    ('笔记.txt', '本地阅读测试'.encode(), '本地'),
                                    ('课程.md', '# 目录\n离线学习内容'.encode(), '离线')]:
            response = service.request('POST', '/api/v1/textbooks', json={'title': name, 'subject': '测试'})
            assert response.status_code == 201, response.text
            book = response.json()['id']
            task = service.request('POST', f'/api/v1/textbooks/{book}/upload',
                                   files={'file': (name, content, 'application/octet-stream')})
            assert task.status_code == 202, task.text
            task_id = task.json()['id']
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                state = service.get(f'/api/v1/import-tasks/{task_id}').json()
                if state['status'] in {'failed', 'completed'}:
                    break
                time.sleep(0.05)
            assert state['status'] == 'completed', state
            document = service.get(f'/api/v1/textbooks/{book}/document').json()
            assert document['chapters'] and document['blocks']
            # Search a literal from the parsed synthetic fixture; persistence/queue is the contract here.
            term = document['blocks'][0]['text'][:4]
            results = service.get(f'/api/v1/textbooks/{book}/document/search', params={'q': term}).json()
            assert results['total'] >= 1
            locator = results['items'][0]['locator']
            position = service.request('PUT', f'/api/v1/textbooks/{book}/document/position',
                                       json={**locator, 'expected_revision': 0})
            assert position.status_code == 200, position.text
            saved.append((book, locator))
    finally:
        service.close()
    service = RunningDesktop(tmp_path / 'learning-space')
    try:
        for book, locator in saved:
            position = service.get(f'/api/v1/textbooks/{book}/document/position').json()
            assert position['rendition_revision'] == locator['rendition_revision']
            assert position['unit_id'] == locator['unit_id']
            assert position['source_changed'] is False
    finally:
        service.close()
