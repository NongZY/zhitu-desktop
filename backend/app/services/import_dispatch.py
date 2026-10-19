"""A bounded in-process PDF worker for one local Uvicorn process (no Redis)."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.database import SessionLocal
from app.models import ImportTask, Textbook
from app.worker import process_textbook_pdf

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None


def _fail(task_id: str, message: str) -> None:
    with SessionLocal() as db:
        task = db.get(ImportTask, task_id)
        if task is not None and task.status in {"queued", "processing"}:
            task.status = "failed"
            task.message = message
            textbook = db.get(Textbook, task.textbook_id)
            if textbook is not None:
                textbook.parse_status = "failed"
            db.commit()


def _run(task_id: str) -> None:
    try:
        process_textbook_pdf.run(task_id)
    except Exception as exc:
        logger.error("Local PDF task failed (%s)", type(exc).__name__)
        _fail(task_id, "课本整理未完成，请重新上传；原有学习记录仍保留。")


def enqueue_local_import(task_id: str) -> None:
    global _executor
    try:
        with _lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-pdf")
            _executor.submit(_run, task_id)
    except RuntimeError:
        _fail(task_id, "系统正在关闭，请启动后重新上传课本。")


def recover_interrupted_imports() -> None:
    with SessionLocal() as db:
        ids = list(db.scalars(select(ImportTask.id).where(
            ImportTask.status.in_(["queued", "processing"])
        )))
    for task_id in ids:
        _fail(task_id, "上次课本整理因程序关闭而中断，请重新上传；原有学习记录仍保留。")


def shutdown_local_imports(wait: bool = True) -> None:
    global _executor
    with _lock:
        executor, _executor = _executor, None
    if executor is not None:
        executor.shutdown(wait=wait)
