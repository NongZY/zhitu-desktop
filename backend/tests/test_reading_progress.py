from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models import Chapter, Textbook


@pytest.fixture()
def reading_book(client, create_learner, tmp_path):
    headers = create_learner('reading-owner@example.com')
    book_id = client.post('/api/v1/textbooks', headers=headers, json={
        'title': '阅读教材', 'subject': '数学',
    }).json()['id']
    path = tmp_path / 'reading.pdf'
    with pymupdf.open() as document:
        for _ in range(16):
            document.new_page()
        document.save(path)
    with SessionLocal() as db:
        book = db.get(Textbook, book_id)
        book.file_path = str(path)
        chapter = Chapter(textbook_id=book_id, title='目录提示', page_start=1, page_end=16)
        db.add(chapter)
        db.commit()
        user_id, chapter_id = book.owner_id, chapter.id
    revision = client.get(f'/api/v1/textbooks/{book_id}/reader', headers=headers).json()['document_revision']
    return {'headers': headers, 'book_id': book_id, 'user_id': user_id,
            'chapter_id': chapter_id, 'path': path, 'document_revision': revision}


def progress_url(book):
    return f"/api/v1/learning/reading-progress/{book['book_id']}"


def save(client, book, **changes):
    payload = {'page_number': 15, 'chapter_id': book['chapter_id'],
               'document_revision': book['document_revision'], 'expected_revision': 0}
    payload.update(changes)
    return client.put(progress_url(book), headers=book['headers'], json=payload)


def test_progress_survives_new_client_and_rejects_stale_revisions(client, reading_book):
    from app.main import app

    book = reading_book
    initial = client.get(progress_url(book), headers=book['headers'])
    assert initial.status_code == 200
    assert initial.json() == {'progress': None}
    first = save(client, book)
    assert first.status_code == 200, first.text
    assert first.headers['cache-control'] == 'private, no-store'
    assert first.json()['page_number'] == 15
    assert first.json()['revision'] == 1
    assert datetime.fromisoformat(first.json()['updated_at'].replace('Z', '+00:00')).utcoffset().total_seconds() == 0
    with TestClient(app) as reopened:
        assert reopened.get(progress_url(book), headers=book['headers']).json()['progress'] == first.json()
    stale = save(client, book, page_number=2)
    assert stale.status_code == 409
    assert stale.headers['cache-control'] == 'private, no-store'
    assert stale.json()['detail']['code'] == 'reading_conflict'
    assert stale.json()['detail']['current'] == first.json()
    assert client.get(progress_url(book), headers=book['headers']).json()['progress']['page_number'] == 15
    second = save(client, book, page_number=16, expected_revision=1)
    assert second.status_code == 200
    assert second.json()['revision'] == 2


@pytest.mark.parametrize('page', [0, -1, True, 1.5, '2', 17])
def test_invalid_physical_pages_cannot_create_progress(client, reading_book, page):
    response = save(client, reading_book, page_number=page)
    assert response.status_code == 422
    assert response.headers['cache-control'] == 'private, no-store'
    assert client.get(progress_url(reading_book), headers=reading_book['headers']).json() == {'progress': None}


@pytest.mark.parametrize('changes', [
    {'expected_revision': True}, {'expected_revision': -1}, {'expected_revision': 0.0},
    {'chapter_id': True}, {'chapter_id': 1.2}, {'document_revision': ''},
    {'unexpected': 'discarding this would hide a client error'},
])
def test_save_rejects_coerced_ids_revisions_and_unknown_fields(client, reading_book, changes):
    assert save(client, reading_book, **changes).status_code == 422


def test_progress_is_private_and_ownership_precedes_file_reads(client, reading_book, create_learner):
    visitor = create_learner('reading-visitor@example.com')
    reading_book['path'].unlink()
    for response in [client.get(progress_url(reading_book), headers=visitor),
                     save(client, {**reading_book, 'headers': visitor})]:
        assert response.status_code == 404
        assert response.headers['cache-control'] == 'private, no-store'
    assert client.get('/api/v1/learning/home', headers=visitor).json() == {
        'textbook_count': 0, 'continue_reading': None, 'reading_notice': None,
    }
    response = client.get(progress_url(reading_book))
    assert response.status_code in {401, 403}
    assert response.headers['cache-control'] == 'private, no-store'


def test_chapter_is_optional_hint_and_textbook_deletion_removes_progress(client, reading_book):
    book = reading_book
    other = client.post('/api/v1/textbooks', headers=book['headers'], json={
        'title': '其他教材', 'subject': '数学',
    }).json()['id']
    foreign_chapter = client.post(f'/api/v1/textbooks/{other}/chapters', headers=book['headers'],
                                 json={'title': '其他章节'}).json()['id']
    assert save(client, book, chapter_id=foreign_chapter).status_code == 422
    assert save(client, book).status_code == 200
    assert client.delete(f"/api/v1/chapters/{book['chapter_id']}", headers=book['headers']).status_code == 204
    progress = client.get(progress_url(book), headers=book['headers']).json()['progress']
    assert progress['page_number'] == 15
    assert progress['chapter_id'] is None
    with engine.connect() as connection:
        assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
    home = client.get('/api/v1/learning/home', headers=book['headers']).json()
    assert home['continue_reading']['chapter_title'] is None
    assert save(client, book, expected_revision=1, chapter_id=None).status_code == 200
    assert client.delete(f"/api/v1/textbooks/{book['book_id']}", headers=book['headers']).status_code == 204
    assert client.get(progress_url(book), headers=book['headers']).status_code == 404
    from app.models import ReadingProgress
    with SessionLocal() as db:
        assert db.scalar(select(ReadingProgress).where(ReadingProgress.textbook_id == book['book_id'])) is None


def test_replaced_file_requires_its_new_revision_even_with_same_page_count(client, reading_book):
    book = reading_book
    assert save(client, book).status_code == 200
    with pymupdf.open(book['path']) as document:
        document[0].insert_text((30, 30), 'Changed contents')
        replacement = document.tobytes()
    book['path'].write_bytes(replacement)
    conflict = save(client, book, expected_revision=1, page_number=9)
    assert conflict.status_code == 409
    assert conflict.json()['detail']['code'] == 'document_changed'
    assert client.get(progress_url(book), headers=book['headers']).json()['progress']['page_number'] == 15
    home = client.get('/api/v1/learning/home', headers=book['headers']).json()
    assert home['continue_reading'] is None
    assert '更新' in home['reading_notice']
    revision = client.get(f"/api/v1/textbooks/{book['book_id']}/reader", headers=book['headers']).json()['document_revision']
    assert save(client, book, expected_revision=1, page_number=9, document_revision=revision).json()['revision'] == 2


@pytest.mark.parametrize('fault', ['missing', 'corrupt', 'changed'])
def test_home_skips_invalid_newer_candidates_and_returns_valid_older_book(client, reading_book, tmp_path, fault):
    from app.models import ReadingProgress

    book = reading_book
    assert save(client, book).status_code == 200
    newer_id = client.post('/api/v1/textbooks', headers=book['headers'], json={
        'title': '最新教材', 'subject': '数学',
    }).json()['id']
    newer_path = tmp_path / 'newer.pdf'
    newer_path.write_bytes(book['path'].read_bytes())
    with SessionLocal() as db:
        db.get(Textbook, newer_id).file_path = str(newer_path)
        db.commit()
    newer = {**book, 'book_id': newer_id, 'chapter_id': None}
    assert save(client, newer, page_number=9).status_code == 200
    # Same timestamps must choose descending id, independently of database row order.
    with SessionLocal() as db:
        for row in db.scalars(select(ReadingProgress)):
            row.updated_at = datetime(2026, 10, 15, tzinfo=timezone.utc)
        db.commit()
    home = client.get('/api/v1/learning/home', headers=book['headers']).json()
    assert home['continue_reading']['textbook_id'] == newer_id
    if fault == 'missing':
        newer_path.unlink()
    elif fault == 'corrupt':
        newer_path.write_bytes(b'not a PDF')
    else:
        with pymupdf.open(newer_path) as document:
            document[0].insert_text((30, 30), 'New edition')
            replacement = document.tobytes()
        newer_path.write_bytes(replacement)
    response = client.get('/api/v1/learning/home', headers=book['headers'])
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    home = response.json()
    assert home['textbook_count'] == 2
    assert home['reading_notice']
    assert home['continue_reading']['textbook_id'] == book['book_id']
    assert home['continue_reading']['title'] == '阅读教材'
    assert home['continue_reading']['chapter_title'] == '目录提示'
    assert home['continue_reading']['page_count'] == 16


@pytest.mark.parametrize('existing', [False, True])
def test_competing_connections_only_accept_one_writer(client, reading_book, existing):
    from app.schemas import ReadingProgressWrite
    from app.services.reading_progress import ReadingProgressError, save_progress

    book = reading_book
    if existing:
        assert save(client, book).status_code == 200
    barrier = Barrier(2)

    def attempt(page):
        with Session(engine) as db:
            # Check out two independent connections before the competing writes.
            db.connection()
            barrier.wait(timeout=10)
            payload = ReadingProgressWrite(page_number=page, chapter_id=None,
                                           document_revision=book['document_revision'],
                                           expected_revision=int(existing))
            try:
                return save_progress(db, book['user_id'], book['book_id'], payload)
            except ReadingProgressError as exc:
                return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, [8, 9]))
    successful = [item for item in outcomes if not isinstance(item, ReadingProgressError)]
    conflicts = [item for item in outcomes if isinstance(item, ReadingProgressError)]
    assert len(successful) == len(conflicts) == 1
    assert conflicts[0].status_code == 409
    assert conflicts[0].detail['code'] == 'reading_conflict'
    current = client.get(progress_url(book), headers=book['headers']).json()['progress']
    assert current['page_number'] == successful[0].page_number
    assert current['revision'] == (2 if existing else 1)
