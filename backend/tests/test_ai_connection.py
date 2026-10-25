import asyncio
import json

import httpx
import pytest


SECRET = 'synthetic-test-key-never-a-real-secret'
CONFIG = dict(base_url='https://ai.example/v1', model='test-model', api_key=SECRET,
              qa_enabled=True, practice_enabled=False, privacy_ack=True)
MESSAGES = [{'role': 'user', 'content': '仅此一段测试资料'}]


def connection(tmp_path, handler):
    from app.services.ai_connection import AIConnection
    return AIConnection(tmp_path, transport=httpx.MockTransport(handler))


def test_disabled_and_separate_purpose_never_send_data(tmp_path):
    def unexpected(request):
        pytest.fail('disabled connection made a network request')
    service = connection(tmp_path, unexpected)
    assert asyncio.run(service.complete('qa', MESSAGES, consent=True))['status'] == 'disabled'
    service.save(CONFIG)
    assert asyncio.run(service.complete('practice', MESSAGES, consent=True))['status'] == 'disabled'
    assert asyncio.run(service.complete('qa', MESSAGES))['status'] == 'consent_required'


def test_dpapi_key_survives_restart_but_is_not_in_public_settings_or_plaintext(tmp_path):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={'choices': [{'message': {'content': '依据资料的回答'}}]})
    service = connection(tmp_path, respond)
    public = service.save(CONFIG)
    assert public['key_configured'] is True
    assert SECRET not in json.dumps(public)
    assert all(SECRET.encode() not in p.read_bytes() for p in tmp_path.iterdir() if p.is_file())
    restarted = connection(tmp_path, respond)
    result = asyncio.run(restarted.complete('qa', MESSAGES, consent=True))
    assert result['status'] == 'ok' and result['text'] == '依据资料的回答'
    assert str(requests[0].url) == 'https://ai.example/v1/chat/completions'
    assert requests[0].headers['Authorization'] == f'Bearer {SECRET}'
    assert json.loads(requests[0].content)['messages'] == MESSAGES
    restarted.save({**CONFIG, 'api_key': '', 'clear_key': True})
    assert restarted.public()['key_configured'] is False
    assert asyncio.run(restarted.complete('qa', MESSAGES, consent=True))['status'] == 'not_configured'


@pytest.mark.parametrize('url', ['http://ai.example/v1', 'https://user:pass@ai.example',
                                 'file:///secret', 'https://ai.example?key=secret', 'https://ai.example/#secret'])
def test_invalid_endpoint_rejected_without_persisting_key(tmp_path, url):
    service = connection(tmp_path, lambda request: pytest.fail('save must not connect'))
    with pytest.raises(ValueError):
        service.save({**CONFIG, 'base_url': url})
    assert not service.public()['key_configured']


@pytest.mark.parametrize(('status', 'body', 'expected'), [
    (401, {'error': {'message': SECRET}}, 'invalid_key'),
    (429, {'error': {'code': 'rate_limit_exceeded', 'message': SECRET}}, 'rate_limited'),
    (429, {'error': {'code': 'insufficient_quota', 'message': SECRET}}, 'quota_exhausted'),
    (503, {'error': {'message': SECRET}}, 'unavailable'),
    (200, {'choices': []}, 'invalid_response'),
    (302, {}, 'invalid_response'),
])
def test_provider_failures_are_explicit_redacted_and_never_retried(tmp_path, status, body, expected):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, json=body, headers={'Location': 'https://other.example'})
    service = connection(tmp_path, respond)
    service.save(CONFIG)
    result = asyncio.run(service.complete('qa', MESSAGES, consent=True))
    assert result['status'] == expected
    assert SECRET not in json.dumps(result)
    assert len(calls) == 1


def test_timeout_and_connection_test_consent(tmp_path):
    def timeout(request):
        raise httpx.ReadTimeout(SECRET)
    service = connection(tmp_path, timeout)
    service.save({**CONFIG, 'qa_enabled': False})
    assert asyncio.run(service.complete('test', []))['status'] == 'consent_required'
    assert asyncio.run(service.complete('test', [], consent=True))['status'] == 'timeout'


def test_disabling_cancels_pending_call_without_returning_late_answer(tmp_path):
    async def scenario():
        entered = asyncio.Event()
        async def delayed(request):
            entered.set()
            await asyncio.sleep(10)
            return httpx.Response(200, json={'choices': [{'message': {'content': 'late'}}]})
        service = connection(tmp_path, delayed)
        service.save(CONFIG)
        task = asyncio.create_task(service.complete('qa', MESSAGES, consent=True))
        await entered.wait()
        service.save({**CONFIG, 'qa_enabled': False, 'api_key': ''})
        result = await asyncio.wait_for(task, 1)
        assert result['status'] == 'cancelled' and not result['text']
    asyncio.run(scenario())
