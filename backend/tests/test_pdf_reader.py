import pymupdf
import pytest

from app.database import SessionLocal
from app.models import Chapter, DocumentChunk, Textbook


@pytest.fixture()
def reader_book(client, create_learner, tmp_path):
    headers = create_learner("reader-owner@example.com")
    book = client.post('/api/v1/textbooks', headers=headers,
                       json={'title': '数学', 'subject': '数学'}).json()
    path = tmp_path / 'reader.pdf'
    with pymupdf.open() as doc:
        for _ in range(3):
            doc.new_page()
        doc.save(path)
    with SessionLocal() as db:
        db.get(Textbook, book['id']).file_path = str(path)
        parent = Chapter(textbook_id=book['id'], title='第一章', page_start=1, page_end=2)
        db.add(parent)
        db.flush()
        child = Chapter(textbook_id=book['id'], parent_id=parent.id, title='正数和负数',
                        page_start=1, page_end=2)
        db.add(child)
        db.flush()
        for index, (page, content, source) in enumerate([
            (1, '正 数 和 负 数：５＋２', 'pdf'), (1, '正数和负数重复', 'pdf'),
            (2, '正数和负数，100%_正确', 'pdf'), (3, '手动正数和负数', 'manual'),
            (99, '无效页码正数和负数', 'pdf'),
        ]):
            db.add(DocumentChunk(textbook_id=book['id'], chapter_id=child.id,
                                 page_number=page, chunk_index=index, content=content,
                                 metadata_json={'source': source}))
        db.commit()
        return headers, book['id'], parent.id


def test_reader_page_count_and_literal_page_search(client, reader_book):
    headers, book_id, chapter_id = reader_book
    info = client.get(f'/api/v1/textbooks/{book_id}/reader', headers=headers).json()
    assert info['page_count'] == 3
    assert len(info['document_revision']) == 64
    path = f'/api/v1/textbooks/{book_id}/search'
    data = client.get(path, headers=headers, params={'q': '正数和负数', 'page_size': 1}).json()
    assert data['total'] == 2
    assert [item['page_number'] for item in data['items']] == [1]
    data = client.get(path, headers=headers, params={
        'q': '正数和负数', 'chapter_id': chapter_id, 'page_size': 1, 'page': 2,
    }).json()
    assert data['items'][0]['page_number'] == 2
    assert data['items'][0]['chapter_title'] == '正数和负数'
    assert client.get(path, headers=headers, params={'q': '%_'}).json()['total'] == 1
    assert client.get(path, headers=headers, params={'q': '5+2'}).json()['total'] == 1
    assert client.get(path, headers=headers, params={'q': '   '}).status_code == 422


def test_reader_cannot_access_another_account(client, reader_book, create_learner):
    _, book_id, _ = reader_book
    other = create_learner('reader-other@example.com')
    for suffix in ['reader', 'search?q=正数']:
        url = f'/api/v1/textbooks/{book_id}/{suffix}'
        assert client.get(url, headers=other).status_code == 404
        assert client.get(url).status_code in {401, 403}


def test_manual_textbook_has_no_pdf_pages(client, create_learner):
    headers = create_learner('reader-manual@example.com')
    book_id = client.post('/api/v1/textbooks', headers=headers,
                          json={'title': '笔记', 'subject': '数学'}).json()['id']
    assert client.get(f'/api/v1/textbooks/{book_id}/reader', headers=headers).json() == {'page_count': 0, 'document_revision': None}
    assert client.get(f'/api/v1/textbooks/{book_id}/search', headers=headers,
                      params={'q': '笔记'}).json()['total'] == 0
