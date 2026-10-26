from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    """Legacy database values retained for upgrades; they grant no product permissions."""

    student = "student"
    teacher = "teacher"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    hashed_password: Mapped[str] = mapped_column(String(255))
    # Kept mapped so existing databases can still insert users without a destructive
    # migration. Public schemas and authorization deliberately ignore this value.
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.student)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Textbook(Base):
    __tablename__ = "textbooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    edition: Mapped[str | None] = mapped_column(String(100))
    subject: Mapped[str] = mapped_column(String(100), index=True)
    grade: Mapped[str | None] = mapped_column(String(50), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(String(500))
    file_path: Mapped[str | None] = mapped_column(String(1000))
    parse_status: Mapped[str] = mapped_column(String(30), default="not_uploaded")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="textbook", cascade="all, delete-orphan"
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    textbook_id: Mapped[int] = mapped_column(ForeignKey("textbooks.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)

    textbook: Mapped[Textbook] = relationship(back_populates="chapters")
    parent: Mapped[Chapter | None] = relationship(
        back_populates="children", remote_side="Chapter.id"
    )
    children: Mapped[list[Chapter]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    knowledge_points: Mapped[list[LocalKnowledgePoint]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan"
    )


class GlobalKnowledgePoint(Base):
    __tablename__ = "global_knowledge_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    subject: Mapped[str] = mapped_column(String(100), index=True)
    grade: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LocalKnowledgePoint(Base):
    __tablename__ = "local_knowledge_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    textbook_id: Mapped[int] = mapped_column(ForeignKey("textbooks.id"), index=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), index=True)
    global_knowledge_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("global_knowledge_points.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    chapter: Mapped[Chapter] = relationship(back_populates="knowledge_points")
    global_knowledge_point: Mapped[GlobalKnowledgePoint | None] = relationship()


class KnowledgePointMapping(Base):
    __tablename__ = "knowledge_point_mappings"
    __table_args__ = (UniqueConstraint("local_id", "global_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_id: Mapped[int] = mapped_column(ForeignKey("local_knowledge_points.id"))
    global_id: Mapped[int] = mapped_column(ForeignKey("global_knowledge_points.id"))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class KnowledgeRelation(Base):
    __tablename__ = "knowledge_relations"
    __table_args__ = (UniqueConstraint("source_id", "target_id", "relation_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("global_knowledge_points.id"))
    target_id: Mapped[int] = mapped_column(ForeignKey("global_knowledge_points.id"))
    relation_type: Mapped[str] = mapped_column(String(30), default="prerequisite")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    textbook_id: Mapped[int] = mapped_column(ForeignKey("textbooks.id"), index=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), index=True)
    knowledge_point_id: Mapped[int | None] = mapped_column(
        ForeignKey("local_knowledge_points.id"), index=True
    )
    question_type: Mapped[str] = mapped_column(String(30), index=True)
    stem: Mapped[str] = mapped_column(Text)
    options: Mapped[list | dict | None] = mapped_column(JSON)
    correct_answer: Mapped[object] = mapped_column(JSON)
    explanation: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(Integer, default=3, index=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    source_page: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    knowledge_point: Mapped[LocalKnowledgePoint | None] = relationship()


class ExamPaper(Base):
    __tablename__ = "exam_papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    textbook_id: Mapped[int | None] = mapped_column(ForeignKey("textbooks.id"))
    title: Mapped[str] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(30), default="random")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=45)
    total_score: Mapped[float] = mapped_column(Float, default=0)
    strategy: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    paper_questions: Mapped[list[ExamPaperQuestion]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="ExamPaperQuestion.order_index",
    )


class ExamPaperQuestion(Base):
    __tablename__ = "exam_paper_questions"
    __table_args__ = (UniqueConstraint("paper_id", "question_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("exam_papers.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float, default=5)
    snapshot: Mapped[dict | None] = mapped_column(JSON)

    paper: Mapped[ExamPaper] = relationship(back_populates="paper_questions")
    question: Mapped[Question] = relationship()


class ExamRecord(Base):
    __tablename__ = "exam_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("exam_papers.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    score: Mapped[float] = mapped_column(Float, default=0)
    total_score: Mapped[float] = mapped_column(Float, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="submitted")

    details: Mapped[list[AnswerDetail]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )


class AnswerDetail(Base):
    __tablename__ = "answer_details"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("exam_records.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    user_answer: Mapped[object | None] = mapped_column(JSON)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[float] = mapped_column(Float, default=0)
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer)

    record: Mapped[ExamRecord] = relationship(back_populates="details")
    question: Mapped[Question] = relationship()


class UserMastery(Base):
    __tablename__ = "user_mastery"
    __table_args__ = (UniqueConstraint("user_id", "global_knowledge_point_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    global_knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("global_knowledge_points.id"), index=True
    )
    mastery: Mapped[float] = mapped_column(Float, default=0.5)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    global_knowledge_point: Mapped[GlobalKnowledgePoint] = relationship()


class WrongQuestion(Base):
    __tablename__ = "wrong_questions"
    __table_args__ = (UniqueConstraint("user_id", "question_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    wrong_count: Mapped[int] = mapped_column(Integer, default=1)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    last_wrong_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    question: Mapped[Question] = relationship()


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    textbook_id: Mapped[int] = mapped_column(ForeignKey("textbooks.id"), index=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImportTask(Base):
    __tablename__ = "import_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    textbook_id: Mapped[int] = mapped_column(ForeignKey("textbooks.id"), index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ReadingProgress(Base):
    __tablename__ = "reading_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "textbook_id", name="uq_reading_progress_user_textbook"),
        CheckConstraint("page_number > 0", name="ck_reading_progress_page_positive"),
        CheckConstraint("revision > 0", name="ck_reading_progress_revision_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    textbook_id: Mapped[int] = mapped_column(ForeignKey("textbooks.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    # A disposable directory hint: reparsing can replace chapters while the PDF
    # physical page remains valid. Ownership is checked when saving/reading it.
    chapter_id: Mapped[int | None] = mapped_column(Integer)
    document_revision: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    version: Mapped[str] = mapped_column(String(100), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentSource(Base):
    __tablename__ = "document_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    textbook_id: Mapped[int] = mapped_column(ForeignKey("textbooks.id"), index=True)
    format: Mapped[str] = mapped_column(String(10))
    original_name: Mapped[str] = mapped_column(String(255))
    managed_file: Mapped[str] = mapped_column(String(1000))
    byte_size: Mapped[int] = mapped_column(Integer)
    source_revision: Mapped[str] = mapped_column(String(64), index=True)
    active_rendition: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentImport(Base):
    __tablename__ = "document_imports"

    task_id: Mapped[str] = mapped_column(ForeignKey("import_tasks.id"), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("document_sources.id"), index=True)
    encoding: Mapped[str] = mapped_column(String(20), default="auto")


class DocumentChapter(Base):
    """Manual reading landmarks belong to a source, not every future replacement."""
    __tablename__ = 'document_chapters'
    source_id: Mapped[str] = mapped_column(ForeignKey('document_sources.id'), primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey('chapters.id'), primary_key=True)


class PracticeJob(Base):
    __tablename__ = 'practice_jobs'
    __table_args__ = (UniqueConstraint('owner_id', 'request_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    textbook_id: Mapped[int] = mapped_column(ForeignKey('textbooks.id'), index=True)
    request_id: Mapped[str] = mapped_column(String(80))
    rendition_revision: Mapped[str | None] = mapped_column(String(64))
    parameters: Mapped[dict] = mapped_column(JSON)
    units: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default='queued')
    message: Mapped[str] = mapped_column(String(500), default='等待补充练习')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PracticeCandidate(Base):
    __tablename__ = 'practice_candidates'
    __table_args__ = (UniqueConstraint('job_id', 'fingerprint'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('practice_jobs.id'), index=True)
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey('chapters.id'))
    content: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[list] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    saved_question_id: Mapped[int | None] = mapped_column(ForeignKey('questions.id'))


class QuestionEvidence(Base):
    __tablename__ = 'question_evidence'
    __table_args__ = (UniqueConstraint('textbook_id', 'rendition_revision', 'fingerprint'),)
    question_id: Mapped[int] = mapped_column(ForeignKey('questions.id'), primary_key=True)
    textbook_id: Mapped[int] = mapped_column(ForeignKey('textbooks.id'))
    candidate_id: Mapped[str] = mapped_column(String(36), unique=True)
    rendition_revision: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[list] = mapped_column(JSON)
    provenance: Mapped[dict] = mapped_column(JSON)


class DocumentRendition(Base):
    __tablename__ = "document_renditions"

    revision: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("document_sources.id"), index=True)
    textbook_id: Mapped[int] = mapped_column(ForeignKey("textbooks.id"), index=True)
    parser_version: Mapped[str] = mapped_column(String(80))
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentPosition(Base):
    __tablename__ = "document_positions"
    __table_args__ = (UniqueConstraint("user_id", "textbook_id"), CheckConstraint("revision > 0"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    textbook_id: Mapped[int] = mapped_column(ForeignKey("textbooks.id"), index=True)
    locator: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
