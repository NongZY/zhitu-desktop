from fastapi import APIRouter, Depends, HTTPException, Request

from app.security import get_current_user
from app.services.ai_connection import connection_for

router = APIRouter(prefix='/settings', tags=['设置'], dependencies=[Depends(get_current_user)])


def desktop_root(request: Request):
    profile = getattr(request.app.state, 'desktop_profile', None)
    if profile is None:
        raise HTTPException(404, '仅在桌面软件中使用')
    return getattr(profile, 'root_dir', None) or profile.data_dir


async def safe_payload(request: Request) -> dict:
    try:
        body = await request.body()
        if len(body) > 16384:
            raise ValueError()
        import json
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise ValueError()
        return payload
    except (ValueError, TypeError):
        raise HTTPException(422, '设置格式不正确，请检查输入') from None


@router.get('/ai')
def read_ai(request: Request):
    try:
        return connection_for(desktop_root(request)).public()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.put('/ai')
async def save_ai(request: Request):
    payload = await safe_payload(request)
    try:
        return connection_for(desktop_root(request)).save(payload)
    except (ValueError, OSError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else '设置未保存，请检查磁盘空间后重试'
        raise HTTPException(422, message) from None


@router.post('/ai/test')
async def test_ai(request: Request):
    payload = await safe_payload(request)
    result = await connection_for(desktop_root(request)).complete('test', [], consent=payload.get('consent') is True)
    return {key: result[key] for key in ('status', 'model', 'notice')}
