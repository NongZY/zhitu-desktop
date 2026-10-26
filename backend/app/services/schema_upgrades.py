"""Additive upgrades: run in one maintenance/startup process before other workers."""

from sqlalchemy import Engine, inspect, select

from app.models import (DocumentChapter, DocumentImport, DocumentPosition, DocumentRendition, DocumentSource,
                        PracticeJob, PracticeCandidate, QuestionEvidence,
                        ReadingProgress, SchemaMigration)


READING_PROGRESS_VERSION = "20261015_reading_progress_v1"
DOCUMENT_VERSION = "20261023_structured_documents_v1"
ACTIVATION_VERSION = '20261025_document_activation_v1'
DIRECTORY_VERSION = '20261025_document_directory_v1'
PRACTICE_VERSION = '20261026_textbook_practice_v1'
DOCUMENT_TABLES = (DocumentSource, DocumentImport, DocumentRendition, DocumentPosition)
READING_TABLE_NAMES = frozenset({"reading_progress", "schema_migrations", 'document_chapters',
    'practice_jobs', 'practice_candidates', 'question_evidence', *(
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
        if connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == ACTIVATION_VERSION)) is None:
            if 'active_rendition' not in {c['name'] for c in inspect(connection).get_columns('document_sources')}:
                connection.exec_driver_sql('ALTER TABLE document_sources ADD COLUMN active_rendition VARCHAR(64)')
            connection.exec_driver_sql('UPDATE document_sources SET active_rendition = (SELECT revision FROM document_renditions WHERE source_id = document_sources.id ORDER BY created_at DESC, revision DESC LIMIT 1) WHERE active_rendition IS NULL')
            connection.execute(SchemaMigration.__table__.insert().values(version=ACTIVATION_VERSION))
        if connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == DIRECTORY_VERSION)) is None:
            DocumentChapter.__table__.create(connection, checkfirst=True)
            connection.execute(SchemaMigration.__table__.insert().values(version=DIRECTORY_VERSION))
        if connection.scalar(select(SchemaMigration.version).where(SchemaMigration.version == PRACTICE_VERSION)) is None:
            for model in (PracticeJob, PracticeCandidate, QuestionEvidence):
                model.__table__.create(connection, checkfirst=True)
            if 'exam_paper_questions' in inspect(connection).get_table_names():
                if 'snapshot' not in {c['name'] for c in inspect(connection).get_columns('exam_paper_questions')}:
                    connection.exec_driver_sql('ALTER TABLE exam_paper_questions ADD COLUMN snapshot JSON')
            connection.execute(SchemaMigration.__table__.insert().values(version=PRACTICE_VERSION))
