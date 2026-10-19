from __future__ import annotations

import logging
import re
from hashlib import sha256

import pymupdf as fitz
from celery import Celery
from sqlalchemy import delete, func, select

from app.config import settings
from app.database import SessionLocal
from app.models import DocumentChunk, ImportTask, Textbook
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
        textbook = db.get(Textbook, task.textbook_id)
        if textbook is None or not textbook.file_path:
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
            textbook.parse_status = "processing"
            db.commit()
            local_path, remove_after = materialize(textbook.file_path)
            digest = sha256()
            with local_path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            source_sha256 = digest.hexdigest()
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

            # Replace PDF-derived content atomically after extraction succeeds.
            # Progress commits above never expose a partially replaced knowledge base.
            db.execute(delete(DocumentChunk).where(
                DocumentChunk.textbook_id == textbook.id,
                DocumentChunk.metadata_json["source"].as_string() == "pdf",
            ))
            highest_index = db.scalar(select(func.max(DocumentChunk.chunk_index)).where(
                DocumentChunk.textbook_id == textbook.id,
            ))
            first_index = highest_index + 1 if highest_index is not None else 0
            for index, chunk in enumerate(extracted, start=first_index):
                chunk.chunk_index = index
            added_chapters = apply_outline(db, textbook.id, outline, extracted)
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
            task.message = (
                "未提取到可用文字，扫描版 PDF 需要 OCR 识别"
                if isinstance(exc, ValueError) and str(exc).startswith("未提取到可用文字")
                else f"PDF 解析失败：{type(exc).__name__}，请重试或检查后台日志"
            )
            if textbook is not None:
                textbook.parse_status = "failed"
            db.commit()
            # SQL exception strings can contain private document text and parameters.
            logger.error("PDF import %s failed (%s)", import_task_id, type(exc).__name__)
            return {"status": "failed", "message": task.message}
        finally:
            if document is not None:
                document.close()
            if remove_after and local_path is not None:
                local_path.unlink(missing_ok=True)
