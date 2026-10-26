import tempfile
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.desktop_settings import desktop_root
from app.database import get_db
from app.desktop import maintenance as m
from app.models import PracticeJob, ImportTask
from app.security import get_current_user
from app.services.import_dispatch import active_import_count

router = APIRouter(prefix='/maintenance', tags=['本地资料'], dependencies=[Depends(get_current_user)])


def idle(db):
    busy = active_import_count() or db.scalar(select(func.count()).select_from(PracticeJob).where(PracticeJob.status.in_(['queued', 'running'])))
    if busy:
        raise HTTPException(409, '资料正在导入或补题，请等任务结束后再备份或恢复')


def safely(action, *args):
    try:
        return action(*args)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except (OSError, sqlite3.Error):
        raise HTTPException(422, '操作没有完成，请检查文件是否完整和磁盘剩余空间') from None


@router.get('/status')
def status(request: Request):
    return safely(m.status, desktop_root(request))


@router.post('/backups', status_code=201)
def backup(request: Request, db: Session = Depends(get_db)):
    idle(db)
    return safely(m.create_backup, desktop_root(request), request.app.state.desktop_profile.data_dir)


@router.get('/backups/{backup_id}')
def download(backup_id: str, request: Request):
    uid = safely(m.identifier, backup_id)
    path = desktop_root(request) / 'backups' / (uid + '.zip')
    if not path.is_file():
        raise HTTPException(404, '备份文件未找到，请重新创建')
    return FileResponse(path, filename=f'知途备份-{uid[:8]}.zip', media_type='application/zip')


@router.post('/restores', status_code=201)
def prepare(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    idle(db)
    root = desktop_root(request)
    with tempfile.TemporaryDirectory(prefix='restore-upload-', dir=root) as scratch:
        path = Path(scratch) / 'upload.zip'
        size = 0
        with path.open('wb') as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > m.MAX_ARCHIVE:
                    raise HTTPException(413, '备份文件不能超过 2 GB')
                out.write(chunk)
        return safely(m.stage_restore, root, path)


@router.post('/restores/{restore_id}/confirm')
def confirm(restore_id: str, request: Request, db: Session = Depends(get_db)):
    idle(db)
    safely(m.confirm_restore, desktop_root(request), restore_id)
    return {'pending': True, 'notice': '已安排恢复，请关闭并重新打开软件。当前资料会保留。'}


@router.delete('/pending', status_code=204)
def cancel(request: Request):
    safely(m.cancel_pending, desktop_root(request))
    return Response(status_code=204)


@router.post('/rollback')
def rollback(request: Request, db: Session = Depends(get_db)):
    idle(db)
    root = desktop_root(request)
    if not m.status(root)['can_rollback']:
        raise HTTPException(409, '没有可返回的上一个学习空间')
    safely(m.schedule_rollback, root)
    return {'pending': True, 'notice': '下次启动将返回恢复前的学习空间。两个空间的资料都会保留。'}
