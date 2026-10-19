"""Read-only original-page metadata and literal search normalization."""
from contextlib import suppress
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from threading import RLock

import pymupdf
from fastapi import HTTPException

from app.services.storage import materialize, source_signature


@dataclass(frozen=True)
class ReaderMetadata:
    page_count: int
    document_revision: str | None


_cache: OrderedDict[tuple, ReaderMetadata] = OrderedDict()
_cache_lock = RLock()


def page_count(file_path: str | None) -> int:
    return reader_metadata(file_path).page_count


def reader_metadata(file_path: str | None) -> ReaderMetadata:
    if not file_path:
        return ReaderMetadata(0, None)
    path, temporary = None, False
    try:
        signature = source_signature(file_path)
        with _cache_lock:
            if signature in _cache:
                _cache.move_to_end(signature)
                return _cache[signature]
        path, temporary = materialize(file_path)
        content = path.read_bytes()
        with pymupdf.open(stream=content, filetype='pdf') as document:
            if document.needs_pass:
                raise ValueError('encrypted document')
            result = ReaderMetadata(document.page_count, sha256(content).hexdigest())
        if source_signature(file_path) != signature:
            raise HTTPException(409, '教材正在更新，请稍后重试')
        with _cache_lock:
            _cache[signature] = result
            _cache.move_to_end(signature)
            while len(_cache) > 128:
                _cache.popitem(last=False)
        return result
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(404, '课本原文件不存在，请重新上传') from exc
    except Exception as exc:
        raise HTTPException(422, '原课本暂时无法读取，请检查 PDF 后重试') from exc
    finally:
        if temporary and path is not None:
            with suppress(OSError):
                path.unlink(missing_ok=True)


def searchable(text: str) -> str:
    # Width normalization only: NFKC would misleadingly equate x² with x2.
    return ''.join(chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c
                   for c in text if not c.isspace()).casefold()
