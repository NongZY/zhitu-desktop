from __future__ import annotations

import re

import pymupdf as fitz
from celery import Celery
from sqlalchemy import delete

from app.config import settings
from app.database import SessionLocal
from app.models import DocumentChunk, ImportTask, Textbook
from app.services.storage import materialize

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
            textbook.parse_status = "processing"
            db.commit()
            local_path, remove_after = materialize(textbook.file_path)
            document = fitz.open(local_path)
            db.execute(delete(DocumentChunk).where(DocumentChunk.textbook_id == textbook.id))
            db.flush()
            chunk_index = 0
            for page_index, page in enumerate(document):
                page_text = page.get_text("text")
                for content in _split_text(page_text):
                    db.add(
                        DocumentChunk(
                            textbook_id=textbook.id,
                            content=content,
                            page_number=page_index + 1,
                            chunk_index=chunk_index,
                            metadata_json={"source": "pdf", "page": page_index + 1},
                        )
                    )
                    chunk_index += 1
                task.progress = min(90, 10 + int((page_index + 1) / max(1, len(document)) * 80))
                if page_index % 10 == 0:
                    db.commit()
            document.close()
            document = None
            task.status = "completed"
            task.progress = 100
            task.message = f"解析完成，共生成 {chunk_index} 个文本片段；章节与知识点请在审核台确认"
            textbook.parse_status = "review"
            db.commit()
            return {"status": "completed", "chunks": chunk_index}
        except Exception as exc:  # worker boundary: persist a safe error for polling
            task.status = "failed"
            task.message = f"PDF 解析失败：{type(exc).__name__}"
            textbook.parse_status = "failed"
            db.commit()
            return {"status": "failed", "message": task.message}
        finally:
            if document is not None:
                document.close()
            if remove_after and local_path is not None:
                local_path.unlink(missing_ok=True)
