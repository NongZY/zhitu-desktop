from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError

from app.database import Base
from app.models import Textbook, User


NEW_TABLES = {'reading_progress', 'schema_migrations'}


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
        assert len(versions) == 1
        assert versions[0][0] == '20261015_reading_progress_v1'
        assert versions[0][1]
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
