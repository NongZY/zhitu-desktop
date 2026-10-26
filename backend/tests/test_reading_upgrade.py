from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError

from app.database import Base
from app.models import Textbook, User


NEW_TABLES = {'reading_progress', 'schema_migrations', 'document_sources',
              'document_imports', 'document_renditions', 'document_positions', 'document_chapters',
              'practice_jobs', 'practice_candidates', 'question_evidence'}


def test_upgrade_adds_version_once_without_changing_legacy_rows(tmp_path):
    from app.services.schema_upgrades import apply_schema_upgrades

    engine = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    legacy = [table for table in Base.metadata.sorted_tables if table.name not in NEW_TABLES]
    Base.metadata.create_all(engine, tables=legacy)
    with engine.begin() as connection:
        connection.execute(User.__table__.insert(), {'id': 8, 'email': 'old@example.com',
            'name': '旧账户', 'hashed_password': 'unchanged-hash', 'role': 'student',
            'is_active': True, 'created_at': datetime(2020, 1, 2, tzinfo=timezone.utc)})
        connection.execute(Textbook.__table__.insert(), {'id': 9, 'owner_id': 8,
            'title': '旧教材', 'subject': '数学', 'parse_status': 'ready'})
        before = {table.name: connection.execute(select(table)).all() for table in legacy}
    assert not NEW_TABLES.intersection(inspect(engine).get_table_names())
    apply_schema_upgrades(engine)
    apply_schema_upgrades(engine)
    assert NEW_TABLES.issubset(inspect(engine).get_table_names())
    with engine.connect() as connection:
        after = {table.name: connection.execute(select(table)).all() for table in legacy}
        assert after == before
        versions = connection.exec_driver_sql('SELECT version, applied_at FROM schema_migrations').all()
        assert len(versions) == 5
        assert versions[0][0] == '20261015_reading_progress_v1'
        assert versions[1][0] == '20261023_structured_documents_v1'
        assert versions[2][0] == '20261025_document_activation_v1'
        assert versions[3][0] == '20261025_document_directory_v1'
        assert versions[4][0] == '20261026_textbook_practice_v1'
        assert versions[0][1]
    engine.dispose()


def test_legacy_exam_upgrade_preserves_ids_and_does_not_fabricate_past_snapshot(tmp_path):
    from app.services.schema_upgrades import apply_schema_upgrades
    engine = create_engine(f"sqlite:///{(tmp_path / 'old-exams.db').as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE exam_paper_questions (id INTEGER PRIMARY KEY, paper_id INTEGER, question_id INTEGER, order_index INTEGER, score FLOAT)')
        connection.exec_driver_sql('INSERT INTO exam_paper_questions VALUES (41, 3, 17, 1, 5)')
    apply_schema_upgrades(engine)
    apply_schema_upgrades(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT id, paper_id, question_id, score, snapshot FROM exam_paper_questions').one() == (41, 3, 17, 5, None)
    engine.dispose()


def test_upgrade_adds_active_rendition_to_already_created_d2_source_table(tmp_path):
    from app.services.schema_upgrades import apply_schema_upgrades
    engine = create_engine(f"sqlite:///{(tmp_path / 'd2.db').as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE document_sources (id VARCHAR(36) PRIMARY KEY, textbook_id INTEGER, format VARCHAR(10), original_name VARCHAR(255), managed_file VARCHAR(1000), byte_size INTEGER, source_revision VARCHAR(64), created_at DATETIME)')
        connection.exec_driver_sql("INSERT INTO document_sources (id, textbook_id, format, original_name, managed_file, byte_size, source_revision) VALUES ('existing', 1, 'txt', 'note.txt', 'original.txt', 3, 'digest')")
    apply_schema_upgrades(engine)
    apply_schema_upgrades(engine)
    assert 'active_rendition' in {column['name'] for column in inspect(engine).get_columns('document_sources')}
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT managed_file FROM document_sources').scalar() == 'original.txt'
    engine.dispose()


@pytest.mark.parametrize('field', ['page_number', 'revision'])
def test_storage_rejects_nonpositive_progress_numbers(tmp_path, field):
    from app.models import ReadingProgress
    from app.services.schema_upgrades import apply_schema_upgrades

    engine = create_engine(f"sqlite:///{(tmp_path / 'constraint.db').as_posix()}")
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in NEW_TABLES])
    apply_schema_upgrades(engine)
    row = {'user_id': 1, 'textbook_id': 1, 'page_number': 1,
           'document_revision': 'a' * 64, 'revision': 1}
    row[field] = 0
    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(ReadingProgress.__table__.insert(), row)
    engine.dispose()
