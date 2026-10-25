from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import owned_textbook_or_404
from app.config import settings
from app.database import get_db
from app.models import (DocumentImport, DocumentPosition, DocumentRendition, DocumentSource, ImportTask, ReadingProgress,
                        Textbook, User, utcnow)
from app.schemas import ImportTaskRead
from app.security import get_current_user
from app.services.documents import (current_document, document_data, locator_for,
                                    process_document_import, enroll_legacy_pdf)
from app.services.import_dispatch import enqueue_local_import
from app.services.pdf_reader import searchable

router = APIRouter(tags=['本地资料阅读'])


@router.get('/textbooks/{textbook_id}/document/state')
def document_state(textbook_id: int, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    book = owned_textbook_or_404(db, textbook_id, current_user.id)
    current = current_document(db, book)
    latest = db.scalar(select(ImportTask).where(ImportTask.textbook_id == book.id)
                       .order_by(ImportTask.created_at.desc(), ImportTask.id.desc()))
    binding = db.get(DocumentImport, latest.id) if latest else None
    source = db.get(DocumentSource, current.source_id if current else binding.source_id) if current or binding else None
    return {'format': source.format if source else 'pdf' if book.file_path else None,
            'available': bool(book.file_path),
            'status': latest.status if latest else book.parse_status,
            'message': latest.message if latest else '', 'progress': latest.progress if latest else 0}


class PositionWrite(BaseModel):
    source_id: str = Field(max_length=36)
    source_revision: str = Field(min_length=64, max_length=64)
    rendition_revision: str = Field(min_length=64, max_length=64)
    kind: Literal['block', 'slide']
    unit_id: str = Field(min_length=1, max_length=80)
    expected_revision: int = Field(ge=0)


class RetryRequest(BaseModel):
    encoding: Literal['auto', 'utf-8', 'utf-16', 'gb18030'] = 'auto'


def _read_position(db: Session, book: Textbook, position: DocumentPosition | None):
    if position is None:
        return None
    current = current_document(db, book)
    return {**position.locator, 'revision': position.revision, 'updated_at': position.updated_at,
            'source_changed': current is None or current.revision != position.locator['rendition_revision']}


@router.get('/textbooks/{textbook_id}/document')
def read_document(textbook_id: int, response: Response,
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    book = owned_textbook_or_404(db, textbook_id, current_user.id)
    response.headers['Cache-Control'] = 'private, no-store'
    rendition = enroll_legacy_pdf(db, book)
    db.commit()
    return document_data(db, rendition) if rendition else None


@router.get('/textbooks/{textbook_id}/document/versions/{revision}')
def read_version(textbook_id: int, revision: str, response: Response,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_textbook_or_404(db, textbook_id, current_user.id)
    rendition = db.get(DocumentRendition, revision)
    if rendition is None or rendition.textbook_id != textbook_id:
        raise HTTPException(404, '这份资料版本无法找到')
    response.headers['Cache-Control'] = 'private, no-store'
    return document_data(db, rendition)


@router.get('/textbooks/{textbook_id}/document/search')
def search_document(textbook_id: int, q: str = Query(min_length=1, max_length=100),
                    chapter_id: int | None = None, page: int = Query(1, ge=1),
                    revision: str | None = Query(None, min_length=64, max_length=64),
                    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    book = owned_textbook_or_404(db, textbook_id, current_user.id)
    current = db.get(DocumentRendition, revision) if revision else current_document(db, book)
    if current is None or current.textbook_id != book.id:
        raise HTTPException(404, '资料还没有准备好')
    data = document_data(db, current)
    query = searchable(q)
    if not query:
        raise HTTPException(422, '请输入要查找的文字')
    matches = []
    for block in data['blocks']:
        if chapter_id is not None and block.get('chapter_id') != chapter_id:
            continue
        normalized = searchable(block['text'])
        where = normalized.find(query)
        if where >= 0:
            matches.append({'excerpt': normalized[max(0, where - 35):where + len(query) + 100],
                            'locator': locator_for(data, block), 'chapter_id': block.get('chapter_id')})
    return {'items': matches[(page - 1) * 30:page * 30], 'total': len(matches), 'page': page, 'page_size': 30}


@router.get('/textbooks/{textbook_id}/document/versions/{revision}/pages/{page_number}/image')
def version_page(textbook_id: int, revision: str, page_number: int,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.api.textbooks import render_page_image
    owned_textbook_or_404(db, textbook_id, current_user.id)
    rendition = db.get(DocumentRendition, revision)
    if rendition is None or rendition.textbook_id != textbook_id:
        raise HTTPException(404, '这份资料版本无法找到')
    source = db.get(DocumentSource, rendition.source_id)
    if source.format != 'pdf':
        raise HTTPException(404, '这份资料没有 PDF 原页')
    return render_page_image(source.managed_file, page_number, source.source_revision)


@router.get('/textbooks/{textbook_id}/document/position')
def get_position(textbook_id: int, current_user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    book = owned_textbook_or_404(db, textbook_id, current_user.id)
    saved = db.scalar(select(DocumentPosition).where(DocumentPosition.textbook_id == textbook_id,
                                                    DocumentPosition.user_id == current_user.id))
    if saved is None:
        legacy = db.scalar(select(ReadingProgress).where(ReadingProgress.textbook_id == textbook_id,
                                                        ReadingProgress.user_id == current_user.id))
        if legacy:
            retained = db.scalar(select(DocumentRendition).join(DocumentSource).where(
                DocumentSource.textbook_id == textbook_id, DocumentSource.format == 'pdf',
                DocumentSource.source_revision == legacy.document_revision))
            if retained:
                data = document_data(db, retained)
                return {**locator_for(data, {'page': legacy.page_number}), 'revision': 0,
                        'updated_at': legacy.updated_at, 'source_changed': not data['is_current']}
    return _read_position(db, book, saved)


@router.put('/textbooks/{textbook_id}/document/position')
def save_position(textbook_id: int, payload: PositionWrite,
                  current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    book = owned_textbook_or_404(db, textbook_id, current_user.id)
    current = current_document(db, book)
    if current is None or current.revision != payload.rendition_revision:
        raise HTTPException(409, '资料已更新，请重新选择阅读位置')
    data = document_data(db, current)
    locator = payload.model_dump(exclude={'expected_revision'})
    if not any(locator_for(data, block) == locator for block in data['blocks']):
        raise HTTPException(422, '阅读位置不属于这份资料')
    values = {'locator': locator, 'revision': payload.expected_revision + 1, 'updated_at': utcnow()}
    if payload.expected_revision == 0:
        position = DocumentPosition(user_id=current_user.id, textbook_id=textbook_id, **values)
        db.add(position)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, '阅读位置已更新，请重新载入') from None
    else:
        position = db.scalar(update(DocumentPosition).where(
            DocumentPosition.user_id == current_user.id, DocumentPosition.textbook_id == textbook_id,
            DocumentPosition.revision == payload.expected_revision,
        ).values(**values).returning(DocumentPosition).execution_options(synchronize_session=False))
        if position is None:
            db.rollback()
            raise HTTPException(409, '阅读位置已更新，请重新载入')
    result = _read_position(db, book, position)
    db.commit()
    return result


@router.get('/documents/recent')
def recent_document(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(DocumentPosition, Textbook).join(Textbook).where(
        DocumentPosition.user_id == current_user.id, Textbook.owner_id == current_user.id,
    ).order_by(DocumentPosition.updated_at.desc()).limit(20)).all()
    for position, book in rows:
        read = _read_position(db, book, position)
        if not read['source_changed']:
            return {**read, 'textbook_id': book.id, 'title': book.title}
    return None


@router.post('/textbooks/{textbook_id}/document/retry', response_model=ImportTaskRead, status_code=202)
def retry_document(textbook_id: int, payload: RetryRequest, background_tasks: BackgroundTasks,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_textbook_or_404(db, textbook_id, current_user.id)
    latest = db.scalar(select(ImportTask).where(ImportTask.textbook_id == textbook_id)
                       .order_by(ImportTask.created_at.desc(), ImportTask.id.desc()))
    if latest is None:
        raise HTTPException(422, '请先选择要导入的资料')
    if latest.status in {'queued', 'processing'}:
        return latest
    binding = db.get(DocumentImport, latest.id)
    if binding is None:
        raise HTTPException(422, '这份旧资料请重新上传后整理')
    task = ImportTask(id=str(uuid4()), textbook_id=textbook_id, status='queued',
                      message='使用保存的原文件重新整理')
    db.add(task); db.flush()
    db.add(DocumentImport(task_id=task.id, source_id=binding.source_id, encoding=payload.encoding))
    db.commit()
    source = db.get(DocumentSource, binding.source_id)
    if settings.local_mode:
        background_tasks.add_task(enqueue_local_import, task.id)
    elif source.format == 'pdf':
        from app.worker import process_textbook_pdf
        background_tasks.add_task(process_textbook_pdf.delay, task.id)
    else:
        background_tasks.add_task(process_document_import, task.id)
    return task
