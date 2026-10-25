"""Immutable managed sources and transactional structured publication."""
from __future__ import annotations

import json
import logging
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import (Chapter, DocumentChunk, DocumentImport, DocumentRendition,
                        DocumentSource, ImportTask, Textbook)
from app.services.document_parser import parse_document

logger = logging.getLogger(__name__)


def current_document(db: Session, book: Textbook) -> DocumentRendition | None:
    return db.scalar(select(DocumentRendition).join(DocumentSource).where(
        DocumentRendition.textbook_id == book.id, DocumentSource.managed_file == book.file_path,
    ).order_by(DocumentRendition.created_at.desc()))


def document_data(db: Session, rendition: DocumentRendition) -> dict:
    source = db.get(DocumentSource, rendition.source_id)
    book = db.get(Textbook, source.textbook_id)
    current = current_document(db, book)
    return {**rendition.content, 'source_id': source.id, 'source_revision': source.source_revision,
            'rendition_revision': rendition.revision, 'format': source.format,
            'original_name': source.original_name, 'textbook_id': source.textbook_id,
            'is_current': current is not None and current.revision == rendition.revision}


def locator_for(data: dict, block: dict) -> dict:
    return {key: data[key] for key in ('source_id', 'source_revision', 'rendition_revision')} | {
        'kind': 'page' if data['format'] == 'pdf' else 'slide' if data['format'] == 'pptx' else 'block',
        'unit_id': str(block['page']) if data['format'] == 'pdf' else str(block['slide']) if data['format'] == 'pptx' else block['id'],
    }


def new_import(db: Session, book: Textbook, data: bytes, filename: str, encoding: str) -> ImportTask:
    if encoding not in {'auto', 'utf-8', 'utf-16', 'gb18030'}:
        raise HTTPException(422, '请选择支持的文字编码')
    active = db.scalar(select(ImportTask).where(ImportTask.textbook_id == book.id,
                                              ImportTask.status.in_(['queued', 'processing'])))
    if active:
        raise HTTPException(409, '这份资料正在整理，请完成后再上传')
    digest = sha256(data).hexdigest()
    existing = db.scalar(select(ImportTask).join(DocumentImport).join(DocumentSource).where(
        DocumentSource.textbook_id == book.id, DocumentSource.source_revision == digest,
        DocumentSource.format == Path(filename).suffix.lower().lstrip('.'),
        DocumentImport.encoding == encoding, ImportTask.status == 'completed',
        DocumentSource.managed_file == book.file_path,
    ))
    if existing:
        return existing
    source_id = str(uuid4())
    suffix = Path(filename).suffix.lower()
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    stored = settings.upload_path / f'{source_id}{suffix}'
    try:
        with stored.open('xb') as output:
            output.write(data)
        source = DocumentSource(id=source_id, textbook_id=book.id, format=suffix[1:],
                                original_name=Path(filename.replace('\\', '/')).name[:255],
                                managed_file=str(stored), byte_size=len(data), source_revision=digest)
        db.add(source)
        task = ImportTask(id=str(uuid4()), textbook_id=book.id, status='queued', progress=0,
                          message='已保存原文件，等待整理')
        db.add(task)
        db.flush()
        db.add(DocumentImport(task_id=task.id, source_id=source.id, encoding=encoding))
        if not book.file_path:
            book.parse_status = 'queued'
        db.commit()
        return task
    except Exception:
        db.rollback()
        stored.unlink(missing_ok=True)
        raise


def process_document_import(task_id: str) -> None:
    with SessionLocal() as db:
        binding = db.get(DocumentImport, task_id)
        task = db.get(ImportTask, task_id)
        if not binding or not task or task.status not in {'queued', 'processing'}:
            return
        source = db.get(DocumentSource, binding.source_id)
        book = db.get(Textbook, source.textbook_id)
        if book is None:
            return
        try:
            task.status, task.progress, task.message = 'processing', 10, '正在整理正文、目录和图片'
            db.commit()
            with Path(source.managed_file).open('rb') as handle:
                data = handle.read(settings.max_upload_mb * 1024 * 1024 + 1)
            if len(data) != source.byte_size or sha256(data).hexdigest() != source.source_revision:
                raise ValueError('保存的原文件发生变化，请重新导入')
            parsed = parse_document(data, source.original_name, binding.encoding)
            revision = sha256((source.id + json.dumps(parsed, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()
            task.progress, task.message = 90, '正在保存章节与阅读位置'
            db.commit()
            latest = db.scalar(select(ImportTask.id).where(ImportTask.textbook_id == book.id)
                               .order_by(ImportTask.created_at.desc(), ImportTask.id.desc()))
            if latest != task_id:
                task.status, task.message = 'failed', '已有更新的导入任务，本次结果未替换资料'
                db.commit()
                return
            prior = db.get(DocumentRendition, revision)
            if prior:
                book.file_path = source.managed_file
                task.status, task.progress, task.message = 'completed', 100, '资料已经整理完成'
                book.parse_status = 'ready'
                db.commit()
                return
            chapters = []
            stack = []
            chapter = None
            chunks = []
            data_for_locator = {'source_id': source.id, 'source_revision': source.source_revision,
                                'rendition_revision': revision, 'format': source.format}
            for index, block in enumerate(parsed['blocks']):
                if block['kind'] == 'heading' or chapter is None:
                    level = block.get('level', 1)
                    while stack and stack[-1][0] >= level:
                        stack.pop()
                    parent = stack[-1][1] if stack else None
                    title = block['text'][:200] if block['kind'] == 'heading' else '全文'
                    chapter = db.scalar(select(Chapter).where(Chapter.textbook_id == book.id,
                                                              Chapter.title == title,
                                                              Chapter.parent_id == parent))
                    if chapter is None:
                        chapter = Chapter(textbook_id=book.id, title=title, parent_id=parent,
                                          order_index=len(chapters))
                        db.add(chapter); db.flush()
                    stack.append((level, chapter.id))
                    chapters.append({'id': chapter.id, 'title': title, 'level': level,
                                     'locator': locator_for(data_for_locator, block)})
                block['chapter_id'] = chapter.id
                if block['text'] and block['kind'] not in {'unsupported', 'image'}:
                    chunks.append(DocumentChunk(textbook_id=book.id, chapter_id=chapter.id,
                        content=block['text'], chunk_index=index,
                        metadata_json={'source': 'structured', 'locator': locator_for(data_for_locator, block)}))
            # Commit the new edition as one unit; manual content and questions survive.
            db.execute(delete(DocumentChunk).where(DocumentChunk.textbook_id == book.id,
                DocumentChunk.metadata_json['source'].as_string().in_(['structured', 'pdf'])))
            db.add_all(chunks)
            parsed['chapters'] = chapters
            db.add(DocumentRendition(revision=revision, source_id=source.id, textbook_id=book.id,
                                     parser_version=parsed['parser_version'], content=parsed))
            book.file_path, book.parse_status = source.managed_file, 'ready'
            task.status, task.progress = 'completed', 100
            task.message = f"整理完成，{len(parsed['blocks'])} 个内容块、{len(chapters)} 个章节"
            if parsed['warnings']:
                task.message += '；部分图片或复杂对象请对照原文件'
            db.commit()
        except Exception as exc:
            db.rollback()
            task = db.get(ImportTask, task_id)
            if task is None:
                return
            book = db.get(Textbook, task.textbook_id)
            task.status = 'failed'
            task.message = str(exc) if isinstance(exc, ValueError) else '资料未整理完成，原文件已保留，可以重试'
            if book and not book.file_path:
                book.parse_status = 'failed'
            db.commit()
            logger.warning('Structured import failed (%s)', type(exc).__name__)
