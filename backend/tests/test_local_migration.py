from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select

from app.database import Base
from app.models import User


def test_migration_preserves_password_unicode_and_dates_and_never_overwrites(tmp_path):
    from scripts.migrate_local_data import canonical, write_database

    rows = {table.name: [] for table in Base.metadata.sorted_tables}
    rows["users"] = [{"id": 17, "email": "migration@example.com", "name": "学习者\n001",
                      "hashed_password": "$argon2id$unchanged", "role": "student",
                      "is_active": True, "created_at": datetime(2026, 10, 10, tzinfo=timezone.utc)}]
    target = tmp_path / "new.db"
    report = write_database(rows, target)
    assert report["users"]["count"] == 1
    with create_engine(f"sqlite:///{target.as_posix()}").connect() as connection:
        actual = dict(connection.execute(select(User.__table__)).mappings().one())
    assert canonical(actual) == canonical(rows["users"][0])
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        write_database(rows, target)
    assert target.read_bytes() == before


def test_bad_references_do_not_publish_database(tmp_path):
    from scripts.migrate_local_data import write_database

    rows = {table.name: [] for table in Base.metadata.sorted_tables}
    rows["knowledge_relations"] = [{"id": 1, "source_id": 2, "target_id": 3,
                                    "relation_type": "prerequisite"}]
    target = tmp_path / "bad.db"
    with pytest.raises(ValueError, match="关联"):
        write_database(rows, target)
    assert not target.exists()


def test_copy_types_do_not_corrupt_strings_or_json():
    pytest.importorskip("pgdumplib")
    from pgdumplib.converters import DataConverter

    from app.models import Question
    from scripts.migrate_local_data import convert_value

    value, literal_null, sql_null = DataConverter.convert(r"line\nnext\t001\\" + "\t" + r"\\N" + "\t" + r"\N")
    assert value == "line\nnext\t001\\"
    assert literal_null == r"\N"
    assert sql_null is None
    assert convert_value(Question.__table__.c.stem, "001") == "001"
    assert convert_value(Question.__table__.c.correct_answer, '"001"') == "001"
    assert convert_value(Question.__table__.c.options, '["×", "\\\\frac{1}{2}"]') == ["×", r"\frac{1}{2}"]


def test_legacy_backup_missing_only_new_tables_is_restored(tmp_path):
    from scripts.migrate_local_data import write_database

    rows = {table.name: [] for table in Base.metadata.sorted_tables
            if table.name not in {'reading_progress', 'schema_migrations'}}
    report = write_database(rows, tmp_path / 'legacy.db')
    assert report['reading_progress']['count'] == 0
    assert report['schema_migrations']['count'] == 0


@pytest.mark.parametrize('change', ['missing_users', 'unknown_table', 'missing_column', 'unknown_column'])
def test_migration_still_rejects_unrecognized_tables_and_row_columns(tmp_path, change):
    from scripts.migrate_local_data import write_database

    rows = {table.name: [] for table in Base.metadata.sorted_tables}
    rows['users'] = [{'id': 17, 'email': 'migration@example.com', 'name': '旧账户',
                      'hashed_password': 'unchanged', 'role': 'student', 'is_active': True,
                      'created_at': datetime(2020, 1, 1, tzinfo=timezone.utc)}]
    if change == 'missing_users':
        del rows['users']
    elif change == 'unknown_table':
        rows['unexpected_data'] = []
    elif change == 'missing_column':
        del rows['users'][0]['role']
    else:
        rows['users'][0]['unexpected_field'] = 'must not silently discard'
    target = tmp_path / 'rejected.db'
    with pytest.raises(ValueError):
        write_database(rows, target)
    assert not target.exists()


@pytest.mark.parametrize('change', ['legacy', 'missing_users', 'unknown_table', 'missing_column', 'unknown_column'])
def test_dump_table_and_column_validation_uses_exact_legacy_whitelist(tmp_path, monkeypatch, change):
    from types import SimpleNamespace
    import sys

    from scripts.migrate_local_data import load_dump

    entries = []
    for table in Base.metadata.sorted_tables:
        if table.name in {'reading_progress', 'schema_migrations'}:
            continue
        if table.name == 'users' and change == 'missing_users':
            continue
        names = list(table.columns.keys())
        if table.name == 'users' and change == 'missing_column':
            names.remove('role')
        if table.name == 'users' and change == 'unknown_column':
            names.append('unexpected_field')
        entries.append(SimpleNamespace(desc='TABLE DATA', tag=table.name, namespace='public',
                       copy_stmt=f"COPY public.{table.name} ({', '.join(names)}) FROM stdin;"))
    if change == 'unknown_table':
        entries.append(SimpleNamespace(desc='TABLE DATA', tag='unknown_table', namespace='public'))
    # Substitute only the dump parser; schema validation and restoration remain real.
    dump = SimpleNamespace(entries=entries, table_data=lambda schema, name: [])
    monkeypatch.setitem(sys.modules, 'pgdumplib', SimpleNamespace(load=lambda path: dump))
    if change == 'legacy':
        rows = load_dump(tmp_path / 'synthetic.dump')
        assert rows['reading_progress'] == rows['schema_migrations'] == []
    else:
        with pytest.raises(ValueError):
            load_dump(tmp_path / 'synthetic.dump')
