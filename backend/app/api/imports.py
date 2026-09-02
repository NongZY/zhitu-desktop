from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import ImportTask, Textbook, User, UserRole
from app.schemas import ImportTaskRead
from app.security import get_current_user, require_staff
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
    file: UploadFile = File(...),
    _: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> ImportTask:
    textbook = db.get(Textbook, textbook_id)
    if textbook is None:
        raise HTTPException(status_code=404, detail="教材不存在")
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
    textbook = db.get(Textbook, task.textbook_id)
    if current_user.role == UserRole.student or (
        current_user.role == UserRole.teacher
        and textbook is not None
        and textbook.owner_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="无权查看该导入任务")
    return task
