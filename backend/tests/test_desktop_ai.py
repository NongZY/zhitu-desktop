import json

from desktop_helpers import RunningDesktop


def test_settings_are_private_persisted_and_qa_stays_local_by_default(tmp_path):
    service = RunningDesktop(tmp_path)
    try:
        assert service.get('/api/v1/settings/ai', authenticated=False).status_code == 403
        settings = service.get('/api/v1/settings/ai')
        assert settings.status_code == 200, settings.text
        assert settings.json()['qa_enabled'] is False
        secret = 'local-synthetic-secret'
        saved = service.request('PUT', '/api/v1/settings/ai', json={
            'base_url': 'http://127.0.0.1:1/v1', 'model': 'test', 'api_key': secret,
            'qa_enabled': True, 'practice_enabled': False, 'privacy_ack': True})
        assert saved.status_code == 200, saved.text
        assert secret not in saved.text
        bad = service.request('PUT', '/api/v1/settings/ai', json={'api_key': [secret]})
        assert bad.status_code == 422 and secret not in bad.text
        book = service.request('POST', '/api/v1/textbooks', json={'title': '合成教材', 'subject': '测试'}).json()['id']
        assert service.request('POST', '/api/v1/rag/chunks', params={
            'textbook_id': book, 'content': '绝对值表示数轴上一个数对应的点到原点的距离。'}).status_code == 201
        local = service.request('POST', '/api/v1/rag/ask', json={'textbook_id': book, 'question': '绝对值是什么？'}).json()
        assert local['mode'] == 'local' and local['ai_status'] == 'disabled'
        fallback = service.request('POST', '/api/v1/rag/ask', json={
            'textbook_id': book, 'question': '绝对值是什么？', 'use_ai': True}).json()
        assert fallback['mode'] == 'local' and fallback['ai_status'] == 'offline'
        assert fallback['citations'] and '距离' in fallback['answer']
        assert secret not in json.dumps(fallback)
        no_consent = service.request('POST', '/api/v1/settings/ai/test', json={}).json()
        assert no_consent['status'] == 'consent_required'
    finally:
        service.close()
    service = RunningDesktop(tmp_path)
    try:
        settings = service.get('/api/v1/settings/ai').json()
        assert settings['key_configured'] and settings['qa_enabled']
        assert settings['model'] == 'test'
    finally:
        service.close()
