"""Additive upgrades: run in one maintenance/startup process before other workers."""

from sqlalchemy import Engine, select

from app.models import (DocumentImport, DocumentPosition, DocumentRendition, DocumentSource,
                        ReadingProgress, SchemaMigration)


READING_PROGRESS_VERSION = "20261015_reading_progress_v1"
DOCUMENT_VERSION = "20261023_structured_documents_v1"
DOCUMENT_TABLES = (DocumentSource, DocumentImport, DocumentRendition, DocumentPosition)
READING_TABLE_NAMES = frozenset({"reading_progress", "schema_migrations", *(
    model.__tablename__ for model in DOCUMENT_TABLES
)})


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
        if applied is None:
            ReadingProgress.__table__.create(connection, checkfirst=True)
            connection.execute(SchemaMigration.__table__.insert().values(version=READING_PROGRESS_VERSION))
        if connection.scalar(select(SchemaMigration.version).where(
            SchemaMigration.version == DOCUMENT_VERSION,
        )) is None:
            for model in DOCUMENT_TABLES:
                model.__table__.create(connection, checkfirst=True)
            connection.execute(SchemaMigration.__table__.insert().values(version=DOCUMENT_VERSION))
