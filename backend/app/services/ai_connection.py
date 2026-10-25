"""Opt-in, bounded Chat Completions adapter; provider error bodies never escape."""
import asyncio
import json
import threading
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.desktop.secrets import protect, unprotect

NOTICES = {
    'ok': 'AI 已根据提供的资料作答，请核对来源。',
    'disabled': 'AI 未开启，仍可使用本地资料。',
    'consent_required': '请先确认本次发送内容和可能产生的接口费用。',
    'not_configured': '请在设置中填写接口、模型和密钥。',
    'invalid_key': '密钥无效或没有权限，请在设置中检查。',
    'rate_limited': '接口请求过多，请稍后手动重试。',
    'quota_exhausted': '接口额度不足，请检查服务商账户。',
    'timeout': '接口响应超时，未自动重试；本地学习仍可使用。',
    'offline': '暂时无法连接接口，请检查网络和地址。',
    'invalid_response': '接口返回内容无法使用，请检查兼容协议和模型。',
    'unavailable': '接口暂时不可用，未自动重试。',
    'cancelled': '请求已停止或设置已改变；已经发出的内容无法撤回。',
}


def _endpoint(value: str) -> str:
    value = value.strip().rstrip('/')
    try:
        url = urlsplit(value)
        port = url.port
        loopback = url.hostname in {'127.0.0.1', 'localhost', '::1'}
        if (not url.hostname or url.username or url.password or url.query or url.fragment
                or '\\' in value or any(ord(c) < 33 for c in value)
                or (url.scheme != 'https' and not (url.scheme == 'http' and loopback))
                or (port is not None and not 1 <= port <= 65535)):
            raise ValueError()
    except ValueError:
        raise ValueError('远程接口需要 HTTPS；本机接口可填写 http://127.0.0.1:端口/v1') from None
    if url.path.endswith('/chat/completions'):
        value = value[:-len('/chat/completions')]
    return value


class AIConnection:
    def __init__(self, root: Path, transport=None):
        self.path = root / 'settings' / 'ai.json'
        self.transport = transport
        self.lock = threading.RLock()
        self.inflight: set[asyncio.Task] = set()

    def _read(self) -> dict:
        if not self.path.exists():
            return dict(base_url='', model='', qa_enabled=False, practice_enabled=False,
                        protected_key='', revision='initial')
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, OSError):
            raise ValueError('AI 设置无法读取，请重新保存设置') from None

    def public(self) -> dict:
        with self.lock:
            config = self._read()
            return {**{key: config[key] for key in ('base_url', 'model', 'qa_enabled', 'practice_enabled')},
                    'key_configured': bool(config.get('protected_key')),
                    'key_masked': '••••••••' if config.get('protected_key') else '',
                    'protocol': 'OpenAI-compatible Chat Completions'}

    def save(self, payload: dict) -> dict:
        with self.lock:
            previous = self._read()
            enabled = {key: payload.get(key, previous[key]) for key in ('qa_enabled', 'practice_enabled')}
            if any(type(value) is not bool for value in enabled.values()):
                raise ValueError('请选择是否开启 AI')
            if any(enabled.values()) and payload.get('privacy_ack') is not True:
                raise ValueError('开启前请确认会发送所选资料片段，以及可能产生的费用')
            base_url, model = payload.get('base_url', previous['base_url']), payload.get('model', previous['model'])
            key = payload.get('api_key', '')
            if (not all(isinstance(value, str) for value in (base_url, model, key))
                    or len(base_url) > 1000 or len(model) > 200 or len(key) > 4096
                    or any(ord(c) < 32 for c in key + model)):
                raise ValueError('接口设置格式不正确')
            base_url = _endpoint(base_url) if base_url else ''
            secret = previous.get('protected_key', '')
            if payload.get('clear_key') is True:
                secret = ''
            elif key.strip():
                secret = protect(key.strip())
            config = dict(base_url=base_url, model=model.strip(), **enabled,
                          protected_key=secret, revision=str(uuid4()))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
            temporary.replace(self.path)
            for task in list(self.inflight):
                try:
                    task.get_loop().call_soon_threadsafe(task.cancel)
                except RuntimeError:
                    pass
            return self.public()

    async def complete(self, purpose: str, messages: list[dict], *, consent: bool = False) -> dict:
        def result(status, text='', model=''):
            return dict(status=status, text=text, model=model, notice=NOTICES[status])
        if purpose not in {'qa', 'practice', 'test'}:
            return result('disabled')
        with self.lock:
            try:
                config = self._read()
            except ValueError:
                return result('not_configured')
            if purpose != 'test' and not config.get(f'{purpose}_enabled'):
                return result('disabled')
            if not consent:
                return result('consent_required')
            if not all(config.get(key) for key in ('base_url', 'model', 'protected_key')):
                return result('not_configured')
            try:
                url = _endpoint(config['base_url'])
                key = unprotect(config['protected_key'])
            except ValueError:
                return result('not_configured')
            task = asyncio.current_task()
            self.inflight.add(task)
        if purpose == 'test':
            messages = [{'role': 'user', 'content': 'Reply with OK.'}]
        try:
            async with asyncio.timeout(30):
                async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False,
                                             transport=self.transport) as client:
                    async with client.stream('POST', url + '/chat/completions',
                            headers={'Authorization': f'Bearer {key}'},
                            json={'model': config['model'], 'messages': messages, 'stream': False,
                                  'max_tokens': 16 if purpose == 'test' else 3000}) as response:
                        data = bytearray()
                        async for piece in response.aiter_bytes():
                            data.extend(piece)
                            if len(data) > 1024 * 1024:
                                return result('invalid_response')
                        if response.status_code in {401, 403}:
                            return result('invalid_key')
                        if response.status_code == 429:
                            try:
                                code = json.loads(data).get('error', {}).get('code')
                            except (ValueError, AttributeError):
                                code = None
                            return result('quota_exhausted' if code in {'insufficient_quota', 'quota_exceeded'} else 'rate_limited')
                        if response.status_code >= 500:
                            return result('unavailable')
                        if response.status_code != 200:
                            return result('invalid_response')
                        answer = json.loads(data)['choices'][0]['message']['content']
                        if not isinstance(answer, str) or not answer.strip() or len(answer) > 60000:
                            return result('invalid_response')
            with self.lock:
                if self._read()['revision'] != config['revision']:
                    return result('cancelled')
            return result('ok', answer.strip(), config['model'])
        except asyncio.CancelledError:
            return result('cancelled')
        except (httpx.TimeoutException, TimeoutError):
            return result('timeout')
        except httpx.HTTPError:
            return result('offline')
        except (ValueError, KeyError, IndexError, TypeError):
            return result('invalid_response')
        finally:
            with self.lock:
                self.inflight.discard(task)


@lru_cache(maxsize=8)
def connection_for(root: Path) -> AIConnection:
    return AIConnection(root)
