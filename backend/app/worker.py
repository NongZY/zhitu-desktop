from __future__ import annotations

import logging
import re
from hashlib import sha256

import pymupdf as fitz
from celery import Celery
from sqlalchemy import delete, func, select

from app.config import settings
from app.database import SessionLocal
from app.models import Chapter, DocumentChapter, DocumentChunk, DocumentImport, DocumentRendition, DocumentSource, ImportTask, Textbook
from app.services.pdf_math_layout import extract_math_layout
from app.services.pdf_outline import apply_outline, extract_outline
from app.services.pdf_symbols import EXTRACTION_VERSION, PdfSymbolNormalizer
from app.services.storage import materialize

logger = logging.getLogger(__name__)

celery_app = Celery(
    "adaptive_learning",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=False,
    task_track_started=True,
    timezone="Asia/Shanghai",
)


def _split_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    # PDF font mappings can yield NUL, which PostgreSQL text cannot store.
    # Keep a visible unknown-glyph marker instead of silently joining formula digits.
    text = text.replace("\x00", "\ufffd")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            boundary = max(text.rfind("。", start, end), text.rfind("\n", start, end))
            if boundary > start + size // 2:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return [chunk for chunk in chunks if chunk]


@celery_app.task(name="app.process_textbook_pdf")
def process_textbook_pdf(import_task_id: str) -> dict[str, object]:
    with SessionLocal() as db:
        task = db.get(ImportTask, import_task_id)
        if task is None:
            return {"status": "missing", "task_id": import_task_id}
        if task.status not in {'queued', 'processing'}:
            return {'status': task.status, 'task_id': import_task_id}
        textbook = db.get(Textbook, task.textbook_id)
        binding = db.get(DocumentImport, task.id)
        imported_source = db.get(DocumentSource, binding.source_id) if binding else None
        file_path = imported_source.managed_file if imported_source else textbook.file_path if textbook else None
        if textbook is None or not file_path:
            task.status = "failed"
            task.message = "教材文件不存在"
            db.commit()
            return {"status": "failed", "message": task.message}
        local_path = None
        remove_after = False
        document = None
        try:
            task.status = "processing"
            task.progress = 5
            task.message = "正在读取 PDF 文件"
            if not textbook.file_path:
                textbook.parse_status = "processing"
            db.commit()
            local_path, remove_after = materialize(file_path)
            digest = sha256()
            with local_path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            source_sha256 = digest.hexdigest()
            if imported_source and (local_path.stat().st_size != imported_source.byte_size
                                    or source_sha256 != imported_source.source_revision):
                raise ValueError('保存的原文件发生变化，请重新导入')
            document = fitz.open(local_path)
            normalizer = PdfSymbolNormalizer(document, source_sha256)
            extracted: list[DocumentChunk] = []
            recovered_fractions = 0
            recovered_superscripts = 0
            review_pages = 0
            page_texts: list[str] = []
            for page_index, page in enumerate(document):
                previous_unknown = normalizer.unknown_symbols
                previous_replacements = normalizer.replacements
                page_text, layout = extract_math_layout(page, normalizer)
                page_texts.append(page_text)
                unknown = normalizer.unknown_symbols - previous_unknown
                review_required = bool(unknown or layout["layout_warnings"])
                review_pages += int(review_required)
                recovered_fractions += layout["fractions_recovered"]
                recovered_superscripts += layout["superscripts_recovered"]
                metadata = {
                    "source": "pdf", "page": page_index + 1,
                    "source_sha256": source_sha256,
                    "extraction_version": EXTRACTION_VERSION,
                    "symbols_recovered": normalizer.replacements - previous_replacements,
                    "unknown_symbols": unknown,
                    "math_review_required": review_required,
                    **layout,
                }
                for content in _split_text(page_text):
                    extracted.append(
                        DocumentChunk(
                            textbook_id=textbook.id,
                            content=content,
                            page_number=page_index + 1,
                            chunk_index=len(extracted),
                            metadata_json=dict(metadata),
                        )
                    )
                task.progress = min(90, 10 + int((page_index + 1) / max(1, len(document)) * 80))
                task.message = f"正在提取文本：第 {page_index + 1}/{len(document)} 页"
                if page_index % 10 == 0 or page_index + 1 == len(document):
                    db.commit()
            task.progress = 92
            task.message = "正在识别章节目录并关联教材内容"
            db.commit()
            outline = extract_outline(document, page_texts)
            document.close()
            document = None
            if not extracted:
                raise ValueError("未提取到可用文字，扫描版 PDF 需要 OCR 识别")
            latest = db.scalar(select(ImportTask.id).where(ImportTask.textbook_id == textbook.id)
                               .order_by(ImportTask.created_at.desc(), ImportTask.id.desc()))
            if latest != task.id:
                task.status, task.message = 'failed', '已有更新的导入任务，本次结果未替换资料'
                db.commit()
                return {'status': 'failed', 'message': task.message}

            # Replace PDF-derived content atomically after extraction succeeds.
            # Progress commits above never expose a partially replaced knowledge base.
            from app.services.documents import enroll_legacy_pdf
            previous_rendition = enroll_legacy_pdf(db, textbook)
            db.execute(delete(DocumentChunk).where(
                DocumentChunk.textbook_id == textbook.id,
                DocumentChunk.metadata_json["source"].as_string().in_(['pdf', 'structured']),
            ))
            highest_index = db.scalar(select(func.max(DocumentChunk.chunk_index)).where(
                DocumentChunk.textbook_id == textbook.id,
            ))
            first_index = highest_index + 1 if highest_index is not None else 0
            for index, chunk in enumerate(extracted, start=first_index):
                chunk.chunk_index = index
            chapter_ids = None
            if previous_rendition:
                previous_source = db.get(DocumentSource, previous_rendition.source_id)
                same_layout_text = (previous_rendition.content.get('outline') == [vars(entry) for entry in outline]
                                    and [b['text'] for b in previous_rendition.content['blocks']] == page_texts)
                chapter_ids = ({c['id'] for c in previous_rendition.content['chapters']}
                               if previous_source.format == 'pdf' and (previous_source.source_revision == source_sha256 or same_layout_text)
                               else set())
                if previous_source.format == 'pdf' and (previous_source.source_revision == source_sha256 or same_layout_text):
                    chapter_ids.update(db.scalars(select(DocumentChapter.chapter_id).where(DocumentChapter.source_id == previous_source.id)))
            added_chapters = apply_outline(db, textbook.id, outline, extracted, chapter_ids=chapter_ids)
            if imported_source:
                revision = sha256(f'{imported_source.id}:{EXTRACTION_VERSION}'.encode()).hexdigest()
                imported_source.active_rendition = revision
                base_locator = dict(source_id=imported_source.id, source_revision=source_sha256,
                                    rendition_revision=revision, kind='page')
                for chunk in extracted:
                    chunk.metadata_json = {**chunk.metadata_json, 'locator': {
                        **base_locator, 'unit_id': str(chunk.page_number)}}
                if db.get(DocumentRendition, revision) is None:
                    blocks = []
                    chapters = []
                    by_page = {chunk.page_number: chunk.chapter_id for chunk in extracted}
                    for number, text in enumerate(page_texts, 1):
                        chapter_id = by_page.get(number)
                        blocks.append(dict(id=f'p{number}', kind='paragraph', page=number,
                                           text=text, chapter_id=chapter_id))
                    directory = select(Chapter).where(Chapter.textbook_id == textbook.id).order_by(Chapter.order_index, Chapter.id)
                    if chapter_ids is not None:
                        directory = directory.where(Chapter.id.in_(chapter_ids))
                    levels = {}
                    for chapter in db.scalars(directory):
                        if not chapter.page_start or not 1 <= chapter.page_start <= len(page_texts):
                            continue
                        level = levels.get(chapter.parent_id, 0) + 1
                        levels[chapter.id] = level
                        chapters.append(dict(id=chapter.id, title=chapter.title, level=level,
                            locator={**base_locator, 'unit_id': str(chapter.page_start)}))
                    db.add(DocumentRendition(revision=revision, source_id=imported_source.id,
                        textbook_id=textbook.id, parser_version=EXTRACTION_VERSION,
                        content=dict(blocks=blocks, chapters=chapters, warnings=[], page_count=len(page_texts),
                                     outline=[vars(entry) for entry in outline])))
            db.add_all(extracted)
            task.status = "completed"
            task.progress = 100
            task.message = (
                f"课本整理完成，可按章节阅读和提问；新增 {added_chapters} 个章节"
            )
            if not added_chapters:
                task.message += "；已有目录已保留，没有目录时可自行添加"
            if normalizer.replacements or recovered_fractions or recovered_superscripts:
                task.message += (
                    f"；已恢复 {normalizer.replacements} 处字母或符号、"
                    f"{recovered_fractions} 处分数、{recovered_superscripts} 处上标"
                )
            if review_pages:
                task.message += (
                    f"；{review_pages} 页仍有内容需要核对，"
                    "遇到 � 或不完整公式时请点击“查看原页”"
                )
            textbook.parse_status = "ready"
            textbook.file_path = file_path
            db.commit()
            return {"status": "completed", "chunks": len(extracted)}
        except Exception as exc:  # worker boundary: persist a safe error for polling
            # A flush failure leaves the session unusable until rollback. Reload
            # records afterwards so failure status persists instead of freezing progress.
            db.rollback()
            task = db.get(ImportTask, import_task_id)
            if task is None:
                return {"status": "missing", "task_id": import_task_id}
            textbook = db.get(Textbook, task.textbook_id)
            task.status = "failed"
            image_only = isinstance(exc, ValueError) and str(exc).startswith("未提取到可用文字")
            task.message = (
                "可阅读原页，但未识别到可搜索文字；扫描版 PDF 需要 OCR 识别"
                if image_only
                else f"PDF 解析失败：{type(exc).__name__}，请重试或检查后台日志"
            )
            if textbook is not None and not textbook.file_path:
                textbook.parse_status = "failed"
                # An initial, valid image-only PDF remains readable even without OCR.
                # Never let a failed replacement discard a previously published book.
                if image_only:
                    textbook.file_path = file_path
            elif image_only:
                task.message = '新文件没有可搜索文字，需要 OCR 识别；原教材仍保留，未替换'
            db.commit()
            # SQL exception strings can contain private document text and parameters.
            logger.error("PDF import %s failed (%s)", import_task_id, type(exc).__name__)
            return {"status": "failed", "message": task.message}
        finally:
            if document is not None:
                document.close()
            if remove_after and local_path is not None:
                local_path.unlink(missing_ok=True)
