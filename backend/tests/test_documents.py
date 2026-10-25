from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import ImportTask, Textbook
from tests.test_document_parser import docx_bytes, pptx_bytes


def new_book(client, headers, title='教材'):
    return client.post('/api/v1/textbooks', headers=headers,
                       json={'title': title, 'subject': '学习'}).json()['id']


def upload(client, headers, book, name, data, **extra):
    return client.post(f'/api/v1/textbooks/{book}/upload', headers=headers,
                       files={'file': (name, data, 'application/octet-stream')}, data=extra)


def test_docx_pptx_upload_publish_chapters_and_keep_question_data(client, create_learner, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path))
    headers = create_learner('documents@example.com')
    for filename, data in [('课本.docx', docx_bytes()), ('课件.pptx', pptx_bytes())]:
        book = new_book(client, headers)
        response = upload(client, headers, book, filename, data)
        assert response.status_code == 202, response.text
        state = client.get(f"/api/v1/import-tasks/{response.json()['id']}", headers=headers).json()
        assert state['status'] == 'completed', state
        doc = client.get(f'/api/v1/textbooks/{book}/document', headers=headers).json()
        assert doc['format'] == filename.rsplit('.', 1)[1]
        assert doc['chapters'] and doc['blocks']
        assert len(doc['source_revision']) == 64
        assert 'managed_file' not in doc
        structure = client.get(f'/api/v1/textbooks/{book}/structure', headers=headers).json()
        assert structure['chapters']


def test_failed_import_keeps_original_content_and_retries_managed_source(client, create_learner, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path))
    headers = create_learner('retrydoc@example.com')
    book = new_book(client, headers)
    assert upload(client, headers, book, 'first.txt', '原有正文'.encode()).status_code == 202
    original = client.get(f'/api/v1/textbooks/{book}/document', headers=headers).json()
    bad = upload(client, headers, book, 'new.txt', '编码正文'.encode('gb18030'))
    assert bad.status_code == 202
    state = client.get(f"/api/v1/import-tasks/{bad.json()['id']}", headers=headers).json()
    assert state['status'] == 'failed' and '编码' in state['message']
    state_view = client.get(f'/api/v1/textbooks/{book}/document/state', headers=headers)
    assert state_view.status_code == 200
    assert state_view.json()['format'] == 'txt' and state_view.json()['status'] == 'failed'
    assert client.get(f'/api/v1/textbooks/{book}/document', headers=headers).json() == original
    retry = client.post(f'/api/v1/textbooks/{book}/document/retry', headers=headers, json={'encoding': 'gb18030'})
    assert retry.status_code == 202, retry.text
    revised = client.get(f'/api/v1/textbooks/{book}/document', headers=headers).json()
    assert revised['blocks'][0]['text'] == '编码正文'
    retained = client.get(f"/api/v1/textbooks/{book}/document/versions/{original['rendition_revision']}", headers=headers)
    assert retained.status_code == 200 and retained.json()['blocks'][0]['text'] == '原有正文'
    assert retained.json()['is_current'] is False
    old_search = client.get(f'/api/v1/textbooks/{book}/document/search', headers=headers,
                            params={'q': '原有正文', 'revision': original['rendition_revision']}).json()
    assert old_search['total'] == 1
    assert old_search['items'][0]['locator']['rendition_revision'] == original['rendition_revision']
    with SessionLocal() as db:
        assert len(db.scalars(select(Textbook)).all()) == 1


def test_position_conflict_version_change_and_private_sources(client, create_learner, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path))
    headers = create_learner('positiondoc@example.com')
    other = create_learner('otherdoc@example.com')
    book = new_book(client, headers)
    assert upload(client, headers, book, 'note.md', '# 章节\n正文'.encode()).status_code == 202
    doc = client.get(f'/api/v1/textbooks/{book}/document', headers=headers).json()
    locator = {key: doc[key] for key in ('source_id', 'source_revision', 'rendition_revision')}
    locator.update(kind='block', unit_id='b2', expected_revision=0)
    saved = client.put(f'/api/v1/textbooks/{book}/document/position', headers=headers, json=locator)
    assert saved.status_code == 200 and saved.json()['revision'] == 1
    assert client.put(f'/api/v1/textbooks/{book}/document/position', headers=headers, json=locator).status_code == 409
    assert client.get(f'/api/v1/textbooks/{book}/document', headers=other).status_code == 404
    assert client.put(f'/api/v1/textbooks/{book}/document/position', headers=other, json=locator).status_code == 404
    assert upload(client, headers, book, 'new.md', '# 新章节\n新正文'.encode()).status_code == 202
    old = client.get(f'/api/v1/textbooks/{book}/document/position', headers=headers).json()
    assert old['rendition_revision'] == doc['rendition_revision'] and old['source_changed'] is True
    locator['expected_revision'] = 1
    assert client.put(f'/api/v1/textbooks/{book}/document/position', headers=headers, json=locator).status_code == 409


def test_document_search_and_rag_reach_after_first_thousand_blocks(client, create_learner, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path))
    headers = create_learner('taildoc@example.com')
    book = new_book(client, headers)
    text = '\n'.join(['普通练习'] * 1100 + ['光合作用通过叶绿体把光能转化为化学能'])
    assert upload(client, headers, book, 'science.txt', text.encode()).status_code == 202
    results = client.get(f'/api/v1/textbooks/{book}/document/search', headers=headers, params={'q': '叶绿体'}).json()
    assert results['total'] == 1 and results['items'][0]['locator']['unit_id'] == 'b1101'
    answer = client.post('/api/v1/rag/ask', headers=headers, json={'textbook_id': book, 'question': '叶绿体光合作用'}).json()
    assert answer['citations'][0]['locator']['unit_id'] == 'b1101'
    assert '叶绿体' in answer['citations'][0]['excerpt']


def test_duplicate_upload_reuses_source_and_task_and_bad_extension_is_explained(client, create_learner, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path))
    headers = create_learner('duplicatedoc@example.com')
    book = new_book(client, headers)
    first = upload(client, headers, book, 'first.txt', b'content')
    assert first.status_code == 202
    second = upload(client, headers, book, 'copy.txt', b'content')
    assert second.status_code == 202 and second.json()['id'] == first.json()['id']
    assert upload(client, headers, book, 'old.doc', b'content').status_code == 415
    with SessionLocal() as db:
        assert len(db.scalars(select(ImportTask)).all()) == 1


def test_failed_pdf_replacement_preserves_structured_reader(client, create_learner, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path))
    headers = create_learner('pdfreplace@example.com')
    book = new_book(client, headers)
    assert upload(client, headers, book, 'first.txt', '原资料'.encode()).status_code == 202
    prior = client.get(f'/api/v1/textbooks/{book}/document', headers=headers).json()
    response = upload(client, headers, book, 'bad.pdf', b'%PDF-broken')
    assert response.status_code == 202
    assert client.get(f'/api/v1/textbooks/{book}/document', headers=headers).json() == prior


def test_switch_to_pdf_removes_old_structured_search_only_after_success(client, create_learner, tmp_path, monkeypatch):
    from tests.test_pdf_import import _sample_pdf
    from app.models import DocumentChunk
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path))
    headers = create_learner('switchpdf@example.com')
    book = new_book(client, headers)
    assert upload(client, headers, book, 'first.txt', '旧资料'.encode()).status_code == 202
    response = upload(client, headers, book, 'new.pdf', _sample_pdf())
    assert response.status_code == 202
    with SessionLocal() as db:
        sources = [chunk.metadata_json.get('source') for chunk in db.scalars(select(DocumentChunk).where(DocumentChunk.textbook_id == book))]
        assert sources and set(sources) == {'pdf'}
    state = client.get(f'/api/v1/textbooks/{book}/document/state', headers=headers).json()
    assert state['format'] == 'pdf'


def test_pdf_citation_retains_original_page_after_replacement(client, create_learner, tmp_path, monkeypatch):
    from tests.test_pdf_import import _sample_pdf
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path))
    headers = create_learner('pdfversion@example.com')
    other = create_learner('privatepdf@example.com')
    book = new_book(client, headers)
    assert upload(client, headers, book, 'original.pdf', _sample_pdf()).status_code == 202
    answer = client.post('/api/v1/rag/ask', headers=headers,
                         json={'textbook_id': book, 'question': 'Adaptive learning evidence'}).json()
    locator = answer['citations'][0]['locator']
    assert locator and locator['kind'] == 'page'
    path = f"/api/v1/textbooks/{book}/document/versions/{locator['rendition_revision']}"
    page_path = path + '/pages/1/image'
    original_image = client.get(page_path, headers=headers)
    assert original_image.status_code == 200 and original_image.content.startswith(b'\x89PNG')
    assert upload(client, headers, book, 'replacement.txt', b'new content').status_code == 202
    retained = client.get(path, headers=headers).json()
    assert retained['is_current'] is False and retained['format'] == 'pdf'
    assert client.get(page_path, headers=headers).content == original_image.content
    assert client.get(page_path, headers=other).status_code == 404
    assert client.get(path + '/pages/999/image', headers=headers).status_code == 404


def test_deleted_book_does_not_expose_old_versions_when_identifier_is_reused(client, create_learner, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path))
    headers = create_learner('removedoc@example.com')
    book = new_book(client, headers)
    assert upload(client, headers, book, 'private.txt', b'private text').status_code == 202
    old = client.get(f'/api/v1/textbooks/{book}/document', headers=headers).json()
    assert client.delete(f'/api/v1/textbooks/{book}', headers=headers).status_code == 204
    replacement = new_book(client, headers)
    assert client.get(f"/api/v1/textbooks/{replacement}/document/versions/{old['rendition_revision']}", headers=headers).status_code == 404
    assert client.get(f'/api/v1/textbooks/{replacement}/document/state', headers=headers).json()['format'] is None


def test_retry_reactivates_original_rendition_and_search_chunks(client, create_learner, tmp_path, monkeypatch):
    from app.models import DocumentChunk
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path))
    headers = create_learner('encoding-cycle@example.com')
    book = new_book(client, headers)
    upload(client, headers, book, 'text.txt', '中文'.encode())
    original = client.get(f'/api/v1/textbooks/{book}/document', headers=headers).json()
    for encoding in ['gb18030', 'auto']:
        result = client.post(f'/api/v1/textbooks/{book}/document/retry', headers=headers, json={'encoding': encoding})
        assert result.status_code == 202
    current = client.get(f'/api/v1/textbooks/{book}/document', headers=headers).json()
    assert current['rendition_revision'] == original['rendition_revision']
    assert current['blocks'][0]['text'] == '中文'
    with SessionLocal() as db:
        assert list(db.scalars(select(DocumentChunk.content).where(DocumentChunk.textbook_id == book))) == ['中文']


def test_replacing_legacy_pdf_retains_verified_original_and_position(client, create_learner, tmp_path, monkeypatch):
    from hashlib import sha256
    from app.models import DocumentChunk, DocumentSource, ReadingProgress
    from tests.test_pdf_import import _sample_pdf
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path))
    headers = create_learner('legacy-pdf@example.com')
    book = new_book(client, headers)
    old_file = tmp_path / 'legacy.pdf'
    content = _sample_pdf()
    old_file.write_bytes(content)
    with SessionLocal() as db:
        row = db.get(Textbook, book)
        row.file_path = str(old_file)
        row.parse_status = 'ready'
        db.add(DocumentChunk(textbook_id=book, content='Adaptive learning evidence', page_number=1,
                             chunk_index=0, metadata_json={'source': 'pdf', 'source_sha256': sha256(content).hexdigest()}))
        db.add(ReadingProgress(user_id=row.owner_id, textbook_id=book, page_number=1,
                              document_revision=sha256(content).hexdigest(), revision=3))
        db.commit()
    upload(client, headers, book, 'new.txt', b'new text')
    with SessionLocal() as db:
        assert db.scalar(select(DocumentSource).where(DocumentSource.source_revision == sha256(content).hexdigest()))
    old_position = client.get(f'/api/v1/textbooks/{book}/document/position', headers=headers).json()
    assert old_position['kind'] == 'page' and old_position['source_changed']
    image = client.get(f"/api/v1/textbooks/{book}/document/versions/{old_position['rendition_revision']}/pages/1/image", headers=headers)
    assert image.status_code == 200 and image.content.startswith(b'\x89PNG')


def test_replacement_pdf_uses_its_own_outline_without_deleting_old_learning_chapters(client, create_learner, tmp_path, monkeypatch):
    import pymupdf
    from app.models import Chapter
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path))
    headers = create_learner('outline-replace@example.com')
    book = new_book(client, headers)
    upload(client, headers, book, 'old.md', '# 旧章节\n旧正文'.encode())
    old = client.get(f'/api/v1/textbooks/{book}/document', headers=headers).json()['chapters'][0]['id']
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), 'New book first chapter')
        pdf.set_toc([[1, 'New chapter', 1]])
        pdf_bytes = pdf.tobytes()
    upload(client, headers, book, 'new.pdf', pdf_bytes)
    current = client.get(f'/api/v1/textbooks/{book}/document', headers=headers).json()
    assert [chapter['title'] for chapter in current['chapters']] == ['New chapter']
    structure = client.get(f'/api/v1/textbooks/{book}/structure', headers=headers).json()
    assert [chapter['title'] for chapter in structure['reader_chapters']] == ['New chapter']
    with SessionLocal() as db:
        assert db.get(Chapter, old).title == '旧章节'
    new_note = client.post(f'/api/v1/textbooks/{book}/chapters', headers=headers,
                          json={'title': '手动阅读标记', 'page_start': 1, 'page_end': 1})
    assert new_note.status_code == 201
    structure = client.get(f'/api/v1/textbooks/{book}/structure', headers=headers).json()
    assert {chapter['title'] for chapter in structure['reader_chapters']} == {'手动阅读标记', 'New chapter'}
    assert client.delete(f"/api/v1/chapters/{new_note.json()['id']}", headers=headers).status_code == 204
    again = client.post(f'/api/v1/textbooks/{book}/chapters', headers=headers,
                        json={'title': '新阅读标记', 'page_start': 1, 'page_end': 1})
    assert again.status_code == 201
