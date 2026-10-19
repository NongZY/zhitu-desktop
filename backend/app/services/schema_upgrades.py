"""Additive upgrades: run in one maintenance/startup process before other workers."""

from sqlalchemy import Engine, select

from app.models import ReadingProgress, SchemaMigration


READING_PROGRESS_VERSION = "20261015_reading_progress_v1"
READING_TABLE_NAMES = frozenset({"reading_progress", "schema_migrations"})


def apply_schema_upgrades(engine: Engine) -> None:
    """Create only this version's tables, preserving every legacy table and row.

    Deployments with multiple workers must run this once before starting them.
    A failed SQLite DDL transaction may leave an empty table: checkfirst permits
    retrying it, and the version is written only after the table exists.
    """
    with engine.begin() as connection:
        SchemaMigration.__table__.create(connection, checkfirst=True)
        applied = connection.scalar(select(SchemaMigration.version).where(
            SchemaMigration.version == READING_PROGRESS_VERSION,
        ))
        if applied is not None:
            return
        ReadingProgress.__table__.create(connection, checkfirst=True)
        connection.execute(SchemaMigration.__table__.insert().values(version=READING_PROGRESS_VERSION))
