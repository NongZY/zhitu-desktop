from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.access import owned_textbook_or_404
from app.config import settings
from app.database import get_db
from app.models import ImportTask, User
from app.schemas import ImportTaskRead
from app.security import get_current_user
from app.services.import_dispatch import enqueue_local_import
from app.services.storage import put_pdf, storage_enabled
from app.worker import process_textbook_pdf

router = APIRouter(tags=["教材导入"])


@router.post(
    "/textbooks/{textbook_id}/upload",
    response_model=ImportTaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_textbook(
    textbook_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportTask:
    textbook = owned_textbook_or_404(db, textbook_id, current_user.id)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".pdf" or file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="仅支持 PDF 文件")
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    stored_path = settings.upload_path / f"{textbook_id}-{uuid4().hex}.pdf"
    size = 0
    with stored_path.open("wb") as destination:
        while content := await file.read(1024 * 1024):
            size += len(content)
            if size > settings.max_upload_mb * 1024 * 1024:
                destination.close()
                stored_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413, detail=f"文件不能超过 {settings.max_upload_mb} MB"
                )
            destination.write(content)
    with stored_path.open("rb") as uploaded:
        signature = uploaded.read(5)
    if signature != b"%PDF-":
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=415, detail="文件内容不是有效的 PDF")
    if storage_enabled():
        try:
            textbook.file_path = put_pdf(stored_path, f"textbooks/{textbook_id}/{stored_path.name}")
            stored_path.unlink(missing_ok=True)
        except Exception as exc:
            stored_path.unlink(missing_ok=True)
            raise HTTPException(status_code=503, detail="对象存储暂不可用，请稍后重试") from exc
    else:
        textbook.file_path = str(stored_path)
    textbook.parse_status = "queued"
    task = ImportTask(id=str(uuid4()), textbook_id=textbook.id, status="queued", progress=0)
    db.add(task)
    db.commit()
    if settings.local_mode:
        task.celery_task_id = f"local:{task.id}"
        background_tasks.add_task(enqueue_local_import, task.id)
    else:
        result = process_textbook_pdf.delay(task.id)
        task.celery_task_id = result.id
    db.commit()
    db.refresh(task)
    return task


@router.get("/import-tasks/{task_id}", response_model=ImportTaskRead)
def import_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportTask:
    task = db.get(ImportTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    try:
        owned_textbook_or_404(db, task.textbook_id, current_user.id)
    except HTTPException as exc:
        raise HTTPException(status_code=404, detail="导入任务不存在") from exc
    return task
