import hashlib
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from fastapi import HTTPException

from app.services import pdf_reader, storage


def make_pdf(path, text='first', encrypted=False):
    with pymupdf.open() as doc:
        doc.new_page().insert_text((30, 30), text)
        options = {'encryption': pymupdf.PDF_ENCRYPT_AES_256, 'owner_pw': 'owner', 'user_pw': 'secret'} if encrypted else {}
        doc.save(path, **options)


def test_content_revision_and_cache(tmp_path, monkeypatch):
    path = tmp_path / 'first.pdf'
    make_pdf(path)
    data = path.read_bytes()
    original_open = pymupdf.open
    opened = []
    def tracked_open(*args, **kwargs):
        opened.append(True)
        return original_open(*args, **kwargs)
    monkeypatch.setattr(pymupdf, 'open', tracked_open)
    first = pdf_reader.reader_metadata(str(path))
    assert first.page_count == 1
    assert first.document_revision == hashlib.sha256(data).hexdigest()
    assert pdf_reader.reader_metadata(str(path)) == first
    assert len(opened) == 1
    copy = tmp_path / 'same.pdf'
    copy.write_bytes(data)
    assert pdf_reader.reader_metadata(str(copy)).document_revision == first.document_revision
    path.unlink()
    make_pdf(path, 'different')
    changed = pdf_reader.reader_metadata(str(path))
    assert changed.page_count == 1
    assert changed.document_revision != first.document_revision
    assert path.exists()


def test_missing_encrypted_and_remote_pdf(tmp_path, monkeypatch):
    for name, code in [('missing.pdf', 404), ('bad.pdf', 422), ('encrypted.pdf', 422)]:
        path = tmp_path / name
        if name == 'bad.pdf':
            path.write_bytes(b'not a PDF')
        if name == 'encrypted.pdf':
            make_pdf(path, encrypted=True)
        with pytest.raises(HTTPException) as error:
            pdf_reader.reader_metadata(str(path))
        assert error.value.status_code == code
    source = tmp_path / 'remote-source.pdf'
    make_pdf(source)
    downloads = []
    state = {'etag': 'a'}
    def fetch(bucket, name, destination):
        downloads.append(Path(destination))
        Path(destination).write_bytes(source.read_bytes())
    fake = SimpleNamespace(stat_object=lambda *a: SimpleNamespace(etag=state['etag'], version_id=None, size=source.stat().st_size, last_modified=None), fget_object=fetch)
    monkeypatch.setattr(storage, '_client', lambda: fake)
    first = pdf_reader.reader_metadata('minio://bucket/book.pdf')
    assert first.document_revision == hashlib.sha256(source.read_bytes()).hexdigest()
    pdf_reader.reader_metadata('minio://bucket/book.pdf')
    assert len(downloads) == 1
    state['etag'] = 'b'
    pdf_reader.reader_metadata('minio://bucket/book.pdf')
    assert len(downloads) == 2
    assert all(not p.exists() for p in downloads)
    def failing_fetch(bucket, name, destination):
        downloads.append(Path(destination))
        raise OSError('download failed')
    fake.fget_object = failing_fetch
    state['etag'] = 'c'
    with pytest.raises(HTTPException):
        pdf_reader.reader_metadata('minio://bucket/book.pdf')
    assert not downloads[-1].exists()


def test_source_changed_while_reading_is_not_cached(tmp_path, monkeypatch):
    path = tmp_path / 'changing.pdf'
    make_pdf(path)
    signatures = iter([('before',), ('after',)])
    monkeypatch.setattr(pdf_reader, 'source_signature', lambda _: next(signatures))
    with pytest.raises(HTTPException) as error:
        pdf_reader.reader_metadata(str(path))
    assert error.value.status_code == 409
