from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class TextbookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    edition: str | None = Field(default=None, max_length=100)
    subject: str = Field(min_length=1, max_length=100)
    grade: str | None = Field(default=None, max_length=50)
    description: str | None = None
    cover_url: str | None = None


class TextbookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    edition: str | None = Field(default=None, max_length=100)
    subject: str | None = Field(default=None, min_length=1, max_length=100)
    grade: str | None = Field(default=None, max_length=50)
    description: str | None = None
    cover_url: str | None = None


class TextbookRead(TextbookCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parse_status: str
    owner_id: int
    processing_progress: int = 0
    processing_message: str | None = None
    chapter_count: int = 0
    knowledge_point_count: int = 0
    question_count: int = 0
    created_at: datetime
    updated_at: datetime


class TextbookList(BaseModel):
    items: list[TextbookRead]
    total: int
    page: int
    page_size: int


class ChapterCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    parent_id: int | None = None
    order_index: int = 0
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    summary: str | None = None


class ChapterUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    parent_id: int | None = None
    order_index: int | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    summary: str | None = None


class ChapterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    textbook_id: int
    parent_id: int | None
    title: str
    order_index: int
    page_start: int | None
    page_end: int | None
    summary: str | None


class KnowledgePointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    order_index: int = 0
    global_knowledge_point_id: int | None = None


class KnowledgePointUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    order_index: int | None = None
    global_knowledge_point_id: int | None = None


class KnowledgePointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    textbook_id: int
    chapter_id: int
    global_knowledge_point_id: int | None
    name: str
    description: str | None
    order_index: int


class ChapterTree(ChapterRead):
    knowledge_points: list[KnowledgePointRead] = Field(default_factory=list)
    children: list["ChapterTree"] = Field(default_factory=list)


class TextbookStructure(BaseModel):
    reader_chapters: list[ChapterTree] | None = None
    textbook: TextbookRead
    chapters: list[ChapterTree]


QuestionType = Literal[
    "single_choice", "multiple_choice", "fill_blank", "true_false", "short_answer"
]
QuestionStatus = Literal["draft", "pending", "approved", "rejected"]


class QuestionCreate(BaseModel):
    textbook_id: int
    chapter_id: int | None = None
    knowledge_point_id: int | None = None
    question_type: QuestionType
    stem: str = Field(min_length=1)
    options: list[Any] | dict[str, Any] | None = None
    correct_answer: Any
    explanation: str | None = None
    difficulty: int = Field(default=3, ge=1, le=5)
    status: QuestionStatus = "draft"
    source: str = Field(default="manual", max_length=50)
    source_page: int | None = Field(default=None, ge=1)


class QuestionUpdate(BaseModel):
    textbook_id: int | None = None
    chapter_id: int | None = None
    knowledge_point_id: int | None = None
    question_type: QuestionType | None = None
    stem: str | None = Field(default=None, min_length=1)
    options: list[Any] | dict[str, Any] | None = None
    correct_answer: Any | None = None
    explanation: str | None = None
    difficulty: int | None = Field(default=None, ge=1, le=5)
    status: QuestionStatus | None = None
    source: str | None = Field(default=None, max_length=50)
    source_page: int | None = Field(default=None, ge=1)


class QuestionRead(QuestionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime


class QuestionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    textbook_id: int
    chapter_id: int | None
    knowledge_point_id: int | None
    question_type: str
    stem: str
    options: list[Any] | dict[str, Any] | None
    difficulty: int
    source: str


class QuestionList(BaseModel):
    items: list[QuestionRead]
    total: int
    page: int
    page_size: int


class QuestionBatchImport(BaseModel):
    questions: list[QuestionCreate] = Field(min_length=1, max_length=500)


class BatchImportResult(BaseModel):
    imported: int
    failed: int
    errors: list[dict[str, Any]]
    items: list[QuestionRead]


class ExamGenerateRequest(BaseModel):
    auto_fill: bool = False
    title: str | None = Field(default=None, max_length=200)
    textbook_id: int | None = None
    chapter_ids: list[int] = Field(default_factory=list)
    knowledge_point_ids: list[int] = Field(default_factory=list)
    question_types: list[QuestionType] = Field(default_factory=list)
    difficulty_min: int = Field(default=1, ge=1, le=5)
    difficulty_max: int = Field(default=5, ge=1, le=5)
    question_count: int = Field(default=10, ge=1, le=200)
    duration_minutes: int = Field(default=45, ge=1, le=600)
    score_per_question: float = Field(default=5, gt=0, le=100)
    mode: Literal["random", "adaptive"] = "random"
    random_seed: int | None = None


class ExamQuestionRead(QuestionPublic):
    order_index: int
    score: float


class ExamPaperRead(BaseModel):
    id: int
    user_id: int
    textbook_id: int | None
    title: str
    mode: str
    duration_minutes: int
    total_score: float
    strategy: dict[str, Any]
    created_at: datetime
    questions: list[ExamQuestionRead]


class AnswerSubmit(BaseModel):
    question_id: int
    answer: Any = None
    time_spent_seconds: int | None = Field(default=None, ge=0)


class ExamSubmitRequest(BaseModel):
    answers: list[AnswerSubmit]
    duration_seconds: int | None = Field(default=None, ge=0)


class AnswerResult(BaseModel):
    question_id: int
    user_answer: Any
    correct_answer: Any | None
    is_correct: bool | None
    score: float
    max_score: float
    explanation: str | None


class ExamResultRead(BaseModel):
    id: int
    paper_id: int
    score: float
    total_score: float
    correct_count: int
    wrong_count: int
    pending_count: int = 0
    graded_total_score: float = 0
    status: str = 'submitted'
    duration_seconds: int | None = None
    submitted_at: datetime
    details: list[AnswerResult]


class MasteryItem(BaseModel):
    id: int
    global_knowledge_point_id: int
    knowledge_point_name: str
    mastery: float
    attempts: int
    correct_count: int
    updated_at: datetime


class MasteryList(BaseModel):
    items: list[MasteryItem]
    total: int


class WrongQuestionItem(BaseModel):
    id: int
    question_id: int
    textbook_id: int | None = None
    chapter_id: int | None = None
    knowledge_point_id: int | None = None
    stem: str
    question_type: str
    difficulty: int
    wrong_count: int
    resolved: bool
    last_wrong_at: datetime


class WrongQuestionList(BaseModel):
    items: list[WrongQuestionItem]
    total: int


class DashboardRead(BaseModel):
    weak_point_count: int = 0
    textbook_count: int
    exam_count: int
    completed_exam_count: int
    average_score_rate: float
    average_score: float
    study_minutes: int
    mastery_average: float
    weak_points: list[MasteryItem]
    wrong_question_count: int
    recent_exams: list[dict[str, Any]] = Field(default_factory=list)
    weekly_activity: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)


class LearningPathNode(BaseModel):
    id: int
    name: str
    subject: str
    grade: str | None
    mastery: float
    status: Literal["not_started", "learning", "mastered"]


class LearningPathEdge(BaseModel):
    source: int
    target: int
    relation_type: str


class LearningPathRead(BaseModel):
    nodes: list[LearningPathNode]
    edges: list[LearningPathEdge]


class RagAskRequest(BaseModel):
    use_ai: bool = False
    question: str = Field(min_length=1, max_length=2000)
    textbook_id: int | None = None
    chapter_id: int | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class RagCitation(BaseModel):
    locator: dict | None = None
    chunk_id: int
    textbook_id: int
    textbook_title: str
    chapter_id: int | None
    chapter_title: str | None
    page_number: int | None
    excerpt: str
    score: float


class RagAnswer(BaseModel):
    mode: str = 'local'
    ai_status: str = 'disabled'
    notice: str = ''
    answer: str
    citations: list[RagCitation]
    grounded: bool
    model: str


class ImportTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    textbook_id: int
    celery_task_id: str | None
    status: str
    progress: int
    message: str | None
    created_at: datetime
    updated_at: datetime


class ReadingProgressWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(strict=True, gt=0)
    chapter_id: int | None = Field(default=None, strict=True, gt=0)
    document_revision: str = Field(strict=True, pattern=r"^[0-9a-f]{64}$")
    expected_revision: int = Field(strict=True, ge=0)


class ReadingProgressRead(BaseModel):
    textbook_id: int = Field(strict=True, gt=0)
    page_number: int = Field(strict=True, gt=0)
    chapter_id: int | None = Field(strict=True, gt=0)
    document_revision: str
    revision: int = Field(strict=True, gt=0)
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        # SQLite stores a naive datetime even for DateTime(timezone=True).
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ReadingProgressResult(BaseModel):
    progress: ReadingProgressRead | None


class ContinueReading(ReadingProgressRead):
    title: str
    chapter_title: str | None
    page_count: int


class ReadingHome(BaseModel):
    textbook_count: int
    continue_reading: ContinueReading | None
    reading_notice: str | None
