from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.access import (
    owned_chapter_or_404,
    owned_knowledge_point_or_404,
    owned_question_or_404,
    owned_textbook_or_404,
)
from app.database import get_db
from app.models import Question, Textbook, User, ExamPaperQuestion, QuestionEvidence, PracticeCandidate
from app.schemas import (
    BatchImportResult,
    QuestionBatchImport,
    QuestionCreate,
    QuestionList,
    QuestionRead,
    QuestionUpdate,
)
from app.security import get_current_user

router = APIRouter(prefix="/questions", tags=["题库"])


def _validate_links(
    db: Session, payload: QuestionCreate | QuestionUpdate, user_id: int
) -> None:
    values = payload.model_dump(exclude_unset=True)
    textbook_id = values.get("textbook_id")
    chapter_id = values.get("chapter_id")
    point_id = values.get("knowledge_point_id")
    try:
        if textbook_id is not None:
            owned_textbook_or_404(db, textbook_id, user_id)
        chapter = (
            owned_chapter_or_404(db, chapter_id, user_id) if chapter_id is not None else None
        )
        point = (
            owned_knowledge_point_or_404(db, point_id, user_id)
            if point_id is not None
            else None
        )
    except HTTPException as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    if textbook_id is not None and chapter is not None and chapter.textbook_id != textbook_id:
        raise HTTPException(status_code=422, detail="章节不属于所选教材")
    if textbook_id is not None and point is not None and point.textbook_id != textbook_id:
        raise HTTPException(status_code=422, detail="知识点不属于所选教材")
    if chapter_id is not None and point is not None and point.chapter_id != chapter_id:
        raise HTTPException(status_code=422, detail="知识点不属于所选章节")


@router.get("", response_model=QuestionList)
def list_questions(
    textbook_id: int | None = None,
    chapter_id: int | None = None,
    knowledge_point_id: int | None = None,
    question_type: str | None = None,
    difficulty: int | None = Query(default=None, ge=1, le=5),
    status_filter: str | None = Query(default=None, alias="status"),
    keyword: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuestionList:
    stmt = (
        select(Question)
        .join(Textbook, Textbook.id == Question.textbook_id)
        .where(Textbook.owner_id == current_user.id)
    )
    if status_filter:
        stmt = stmt.where(Question.status == status_filter)
    if textbook_id is not None:
        stmt = stmt.where(Question.textbook_id == textbook_id)
    if chapter_id is not None:
        stmt = stmt.where(Question.chapter_id == chapter_id)
    if knowledge_point_id is not None:
        stmt = stmt.where(Question.knowledge_point_id == knowledge_point_id)
    if question_type:
        stmt = stmt.where(Question.question_type == question_type)
    if difficulty is not None:
        stmt = stmt.where(Question.difficulty == difficulty)
    if keyword:
        stmt = stmt.where(
            or_(Question.stem.contains(keyword), Question.explanation.contains(keyword))
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.order_by(Question.updated_at.desc(), Question.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return QuestionList(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=QuestionRead, status_code=status.HTTP_201_CREATED)
def create_question(
    payload: QuestionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Question:
    _validate_links(db, payload, current_user.id)
    question = Question(**payload.model_dump(), created_by=current_user.id)
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.post("/batch", response_model=BatchImportResult, status_code=201)
def batch_import_questions(
    payload: QuestionBatchImport,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BatchImportResult:
    created: list[Question] = []
    errors: list[dict[str, object]] = []
    for index, item in enumerate(payload.questions):
        try:
            _validate_links(db, item, current_user.id)
            question = Question(**item.model_dump(), created_by=current_user.id)
            db.add(question)
            db.flush()
            created.append(question)
        except HTTPException as exc:
            errors.append({"index": index, "message": exc.detail})
    db.commit()
    for question in created:
        db.refresh(question)
    return BatchImportResult(
        imported=len(created), failed=len(errors), errors=errors, items=created
    )


@router.get("/{question_id}", response_model=QuestionRead)
def get_question(
    question_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Question:
    return owned_question_or_404(db, question_id, current_user.id)


@router.put("/{question_id}", response_model=QuestionRead)
def update_question(
    question_id: int,
    payload: QuestionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Question:
    question = owned_question_or_404(db, question_id, current_user.id)
    changes = payload.model_dump(exclude_unset=True)
    merged = QuestionUpdate(
        textbook_id=changes.get("textbook_id", question.textbook_id),
        chapter_id=changes.get("chapter_id", question.chapter_id),
        knowledge_point_id=changes.get("knowledge_point_id", question.knowledge_point_id),
    )
    _validate_links(db, merged, current_user.id)
    for key, value in changes.items():
        setattr(question, key, value)
    db.commit()
    db.refresh(question)
    return question


@router.delete("/{question_id}", status_code=204)
def delete_question(
    question_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    from sqlalchemy import delete, update
    question = owned_question_or_404(db, question_id, current_user.id)
    if db.scalar(select(ExamPaperQuestion.id).where(ExamPaperQuestion.question_id == question_id).limit(1)):
        raise HTTPException(409, '这道题已经用于练习，请设为暂不使用，以保留历史记录')
    db.execute(delete(QuestionEvidence).where(QuestionEvidence.question_id == question_id))
    db.execute(update(PracticeCandidate).where(PracticeCandidate.saved_question_id == question_id).values(saved_question_id=None))
    db.delete(question)
    db.commit()
    return Response(status_code=204)
