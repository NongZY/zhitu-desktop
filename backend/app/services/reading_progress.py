from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import owned_textbook_or_404
from app.models import Chapter, ReadingProgress, Textbook, utcnow
from app.schemas import ContinueReading, ReadingHome, ReadingProgressRead, ReadingProgressWrite
from app.services.pdf_reader import reader_metadata


class ReadingProgressError(Exception):
    def __init__(self, status_code: int, detail: dict | str):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


def _chapter(db: Session, progress: ReadingProgress) -> Chapter | None:
    if progress.chapter_id is None:
        return None
    return db.scalar(select(Chapter).where(
        Chapter.id == progress.chapter_id, Chapter.textbook_id == progress.textbook_id,
    ))


def _read(db: Session, progress: ReadingProgress) -> ReadingProgressRead:
    chapter = _chapter(db, progress)
    return ReadingProgressRead(
        textbook_id=progress.textbook_id, page_number=progress.page_number,
        chapter_id=chapter.id if chapter else None, document_revision=progress.document_revision,
        revision=progress.revision, updated_at=progress.updated_at,
    )


def _find(db: Session, user_id: int, textbook_id: int) -> ReadingProgress | None:
    return db.scalar(select(ReadingProgress).where(
        ReadingProgress.user_id == user_id, ReadingProgress.textbook_id == textbook_id,
    ).execution_options(populate_existing=True))


def get_progress(db: Session, user_id: int, textbook_id: int) -> ReadingProgressRead | None:
    owned_textbook_or_404(db, textbook_id, user_id)
    progress = _find(db, user_id, textbook_id)
    # Keep the saved file revision so the reader can explain a replaced PDF.
    return _read(db, progress) if progress else None


def _conflict(db: Session, user_id: int, textbook_id: int) -> ReadingProgressError:
    current = _find(db, user_id, textbook_id)
    return ReadingProgressError(409, {
        "code": "reading_conflict", "message": "其他页面已更新阅读位置，请重新载入",
        "current": _read(db, current).model_dump(mode="json") if current else None,
    })


def save_progress(
    db: Session, user_id: int, textbook_id: int, payload: ReadingProgressWrite,
) -> ReadingProgressRead:
    textbook = owned_textbook_or_404(db, textbook_id, user_id)
    metadata = reader_metadata(textbook.file_path)
    if metadata.document_revision != payload.document_revision:
        raise ReadingProgressError(409, {
            "code": "document_changed", "message": "教材已更新，请重新选择阅读位置",
        })
    if payload.page_number > metadata.page_count:
        raise ReadingProgressError(422, "这个 PDF 页码不可用")
    if payload.chapter_id is not None and db.scalar(select(Chapter.id).where(
        Chapter.id == payload.chapter_id, Chapter.textbook_id == textbook_id,
    )) is None:
        raise ReadingProgressError(422, "章节不属于这本教材")
    values = {
        "page_number": payload.page_number, "chapter_id": payload.chapter_id,
        "document_revision": payload.document_revision,
        "revision": payload.expected_revision + 1, "updated_at": utcnow(),
    }
    if payload.expected_revision == 0:
        progress = ReadingProgress(user_id=user_id, textbook_id=textbook_id, **values)
        db.add(progress)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            if _find(db, user_id, textbook_id) is None:
                raise
            raise _conflict(db, user_id, textbook_id) from None
    else:
        progress = db.scalar(update(ReadingProgress).where(
            ReadingProgress.user_id == user_id, ReadingProgress.textbook_id == textbook_id,
            ReadingProgress.revision == payload.expected_revision,
        ).values(**values).returning(ReadingProgress).execution_options(synchronize_session=False))
        if progress is None:
            db.rollback()
            raise _conflict(db, user_id, textbook_id)
    # Capture this write's result before releasing the transaction to other writers.
    result = _read(db, progress)
    db.commit()
    return result


def get_reading_home(db: Session, user_id: int) -> ReadingHome:
    count = db.scalar(select(func.count()).select_from(Textbook).where(Textbook.owner_id == user_id)) or 0
    notice = None
    batch_size, offset = 100, 0
    while True:
        candidates = db.execute(select(ReadingProgress, Textbook).join(
            Textbook, Textbook.id == ReadingProgress.textbook_id,
        ).where(
            ReadingProgress.user_id == user_id, Textbook.owner_id == user_id,
        ).order_by(ReadingProgress.updated_at.desc(), ReadingProgress.id.desc())
            .offset(offset).limit(batch_size)).all()
        for progress, textbook in candidates:
            try:
                metadata = reader_metadata(textbook.file_path)
            except (HTTPException, OSError):
                notice = notice or "部分教材原文件暂时无法读取，请检查原文件后再继续阅读"
                continue
            if metadata.document_revision != progress.document_revision:
                notice = notice or "教材已更新，请重新选择阅读位置"
                continue
            if not 1 <= progress.page_number <= metadata.page_count:
                notice = notice or "已保存的 PDF 页码不可用，请打开教材重新选择阅读位置"
                continue
            chapter = _chapter(db, progress)
            return ReadingHome(textbook_count=count, reading_notice=notice, continue_reading=ContinueReading(
                **_read(db, progress).model_dump(), title=textbook.title,
                chapter_title=chapter.title if chapter else None, page_count=metadata.page_count,
            ))
        if len(candidates) < batch_size:
            return ReadingHome(textbook_count=count, continue_reading=None, reading_notice=notice)
        offset += batch_size
