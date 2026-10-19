from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.access import owned_global_knowledge_point_ids
from app.database import get_db
from app.models import (
    AnswerDetail,
    Chapter,
    ExamPaper,
    ExamPaperQuestion,
    ExamRecord,
    GlobalKnowledgePoint,
    KnowledgeRelation,
    LocalKnowledgePoint,
    Question,
    Textbook,
    User,
    UserMastery,
    WrongQuestion,
)
from app.schemas import (
    DashboardRead,
    LearningPathEdge,
    LearningPathNode,
    LearningPathRead,
    MasteryItem,
    MasteryList,
    WrongQuestionItem,
    WrongQuestionList,
)
from app.security import get_current_user
from app.services.learning_records import answer_evidence, record_summary

router = APIRouter(prefix="/learning", tags=["学习分析"])


def _mastery_item(row: UserMastery) -> MasteryItem:
    return MasteryItem(
        id=row.id,
        global_knowledge_point_id=row.global_knowledge_point_id,
        knowledge_point_name=row.global_knowledge_point.name,
        mastery=row.mastery,
        attempts=row.attempts,
        correct_count=row.correct_count,
        updated_at=row.updated_at,
    )


@router.get("/mastery", response_model=MasteryList)
def mastery(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MasteryList:
    point_ids = owned_global_knowledge_point_ids(db, current_user.id)
    rows = db.scalars(
        select(UserMastery)
        .where(
            UserMastery.user_id == current_user.id,
            UserMastery.global_knowledge_point_id.in_(point_ids) if point_ids else False,
        )
        .options(selectinload(UserMastery.global_knowledge_point))
        .order_by(UserMastery.mastery.asc())
    ).all()
    return MasteryList(items=[_mastery_item(row) for row in rows], total=len(rows))


@router.get("/wrong-questions", response_model=WrongQuestionList)
def wrong_questions(
    include_resolved: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WrongQuestionList:
    stmt = (
        select(WrongQuestion)
        .join(Question, Question.id == WrongQuestion.question_id)
        .join(Textbook, Textbook.id == Question.textbook_id)
        .where(
            WrongQuestion.user_id == current_user.id,
            Textbook.owner_id == current_user.id,
        )
    )
    if not include_resolved:
        stmt = stmt.where(WrongQuestion.resolved.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.options(selectinload(WrongQuestion.question))
        .order_by(WrongQuestion.last_wrong_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return WrongQuestionList(
        items=[
            WrongQuestionItem(
                id=row.id,
                question_id=row.question_id,
                stem=row.question.stem,
                question_type=row.question.question_type,
                difficulty=row.question.difficulty,
                textbook_id=row.question.textbook_id,
                chapter_id=row.question.chapter_id,
                knowledge_point_id=row.question.knowledge_point_id,
                wrong_count=row.wrong_count,
                resolved=row.resolved,
                last_wrong_at=row.last_wrong_at,
            )
            for row in rows
        ],
        total=total,
    )


@router.patch("/wrong-questions/{item_id}/resolved")
def set_wrong_question_resolved(
    item_id: int,
    resolved: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    row = db.scalar(
        select(WrongQuestion)
        .join(Question, Question.id == WrongQuestion.question_id)
        .join(Textbook, Textbook.id == Question.textbook_id)
        .where(
            WrongQuestion.id == item_id,
            WrongQuestion.user_id == current_user.id,
            Textbook.owner_id == current_user.id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="错题记录不存在")
    row.resolved = resolved
    db.commit()
    return {"id": row.id, "resolved": row.resolved}


@router.get("/dashboard", response_model=DashboardRead)
def dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardRead:
    record_rows = db.execute(
        select(ExamRecord, ExamPaper)
        .join(ExamPaper, ExamPaper.id == ExamRecord.paper_id)
        .where(ExamRecord.user_id == current_user.id, ExamPaper.user_id == current_user.id)
        .options(selectinload(ExamRecord.details), selectinload(ExamPaper.paper_questions))
        .order_by(ExamRecord.submitted_at.desc(), ExamRecord.id.desc())
    ).all()
    records = [record for record, _ in record_rows]
    summaries = [record_summary(record, paper) for record, paper in record_rows]
    point_ids = owned_global_knowledge_point_ids(db, current_user.id)
    mastery_rows = db.scalars(
        select(UserMastery)
        .where(
            UserMastery.user_id == current_user.id,
            UserMastery.global_knowledge_point_id.in_(point_ids) if point_ids else False,
        )
        .options(selectinload(UserMastery.global_knowledge_point))
        .order_by(UserMastery.mastery.asc())
    ).all()
    rates = [
        item["score"] / item["graded_total_score"]
        for item in summaries
        if item["graded_total_score"] > 0
    ]
    average_rate = sum(rates) / len(rates) if rates else 0.0
    mastery_average = (
        sum(row.mastery for row in mastery_rows) / len(mastery_rows) if mastery_rows else 0.0
    )
    wrong_count = (
        db.scalar(
            select(func.count())
            .select_from(WrongQuestion)
            .join(Question, Question.id == WrongQuestion.question_id)
            .join(Textbook, Textbook.id == Question.textbook_id)
            .where(
                WrongQuestion.user_id == current_user.id,
                WrongQuestion.resolved.is_(False),
                Textbook.owner_id == current_user.id,
            )
        )
        or 0
    )
    textbook_count = (
        db.scalar(
            select(func.count()).select_from(Textbook).where(Textbook.owner_id == current_user.id)
        )
        or 0
    )
    today = datetime.now(timezone.utc).date()
    daily = {
        today - timedelta(days=offset): {"minutes": 0, "questions": 0}
        for offset in range(6, -1, -1)
    }
    for record in records:
        if record.submitted_at is None:
            continue
        day = record.submitted_at.date()
        if day in daily:
            daily[day]["minutes"] += round((record.duration_seconds or 0) / 60)
            daily[day]["questions"] += (
                len(record.details) or record.correct_count + record.wrong_count
            )
    weak_rows = [row for row in mastery_rows if row.mastery < 0.8]
    weak_items = [_mastery_item(row) for row in weak_rows[:5]]
    return DashboardRead(
        textbook_count=textbook_count,
        exam_count=len(records),
        completed_exam_count=len(records),
        average_score_rate=round(average_rate, 4),
        average_score=round(average_rate * 100, 2),
        study_minutes=round(sum((row.duration_seconds or 0) for row in records) / 60),
        mastery_average=round(mastery_average, 4),
        weak_points=weak_items,
        weak_point_count=len(weak_rows),
        wrong_question_count=wrong_count,
        recent_exams=summaries[:5],
        weekly_activity=[{"date": day.isoformat(), **values} for day, values in daily.items()],
        recommendations=[
            {
                "id": item.global_knowledge_point_id,
                "title": f"巩固：{item.knowledge_point_name}",
                "description": f"当前掌握度 {round(item.mastery * 100)}%，建议安排针对性练习。",
                "type": "review",
                "knowledge_point_id": item.global_knowledge_point_id,
            }
            for item in weak_items[:3]
        ],
    )


@router.get("/exams")
def exam_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    stmt = (
        select(ExamRecord, ExamPaper)
        .join(ExamPaper, ExamPaper.id == ExamRecord.paper_id)
        .where(ExamRecord.user_id == current_user.id, ExamPaper.user_id == current_user.id)
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.options(selectinload(ExamRecord.details), selectinload(ExamPaper.paper_questions))
        .order_by(ExamRecord.submitted_at.desc(), ExamRecord.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [record_summary(record, paper) for record, paper in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/exams/{record_id}")
def exam_detail(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = db.execute(
        select(ExamRecord, ExamPaper)
        .join(ExamPaper, ExamPaper.id == ExamRecord.paper_id)
        .where(
            ExamRecord.id == record_id,
            ExamRecord.user_id == current_user.id,
            ExamPaper.user_id == current_user.id,
        )
        .options(
            selectinload(ExamRecord.details)
            .selectinload(AnswerDetail.question)
            .selectinload(Question.knowledge_point),
            selectinload(ExamPaper.paper_questions),
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="学习记录不存在")
    record, paper = row
    textbook = db.scalar(
        select(Textbook).where(
            Textbook.id == paper.textbook_id, Textbook.owner_id == current_user.id
        )
    )
    answers = {detail.question_id: detail for detail in record.details}
    return {
        **record_summary(record, paper),
        "textbook_title": textbook.title if textbook else None,
        "details": [
            answer_evidence(answers[item.question_id], item.score)
            for item in paper.paper_questions
            if item.question_id in answers
        ],
    }


@router.get("/knowledge-points/{point_id}")
def knowledge_point_detail(
    point_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    # Shared global concepts never grant access to someone else's books or answers.
    mappings = db.execute(
        select(LocalKnowledgePoint, Chapter, Textbook)
        .join(Chapter, Chapter.id == LocalKnowledgePoint.chapter_id)
        .join(Textbook, Textbook.id == LocalKnowledgePoint.textbook_id)
        .where(
            LocalKnowledgePoint.global_knowledge_point_id == point_id,
            Textbook.owner_id == current_user.id,
        )
        .order_by(Textbook.id, Chapter.order_index, LocalKnowledgePoint.id)
    ).all()
    if not mappings:
        raise HTTPException(status_code=404, detail="知识点不存在")
    point = db.get(GlobalKnowledgePoint, point_id)
    mastery_row = db.scalar(
        select(UserMastery).where(
            UserMastery.user_id == current_user.id,
            UserMastery.global_knowledge_point_id == point_id,
        )
    )
    evidence = db.execute(
        select(AnswerDetail, ExamRecord, ExamPaperQuestion.score)
        .join(ExamRecord, ExamRecord.id == AnswerDetail.record_id)
        .join(Question, Question.id == AnswerDetail.question_id)
        .join(
            ExamPaperQuestion,
            (ExamPaperQuestion.paper_id == ExamRecord.paper_id)
            & (ExamPaperQuestion.question_id == AnswerDetail.question_id),
        )
        .where(
            ExamRecord.user_id == current_user.id,
            Question.knowledge_point_id.in_([local.id for local, _, _ in mappings]),
        )
        .options(selectinload(AnswerDetail.question).selectinload(Question.knowledge_point))
        .order_by(ExamRecord.submitted_at.desc(), AnswerDetail.id.desc())
        .limit(20)
    ).all()
    return {
        "id": point.id,
        "name": point.name,
        "description": point.description,
        "subject": point.subject,
        "grade": point.grade,
        "mastery": mastery_row.mastery if mastery_row else None,
        "attempts": mastery_row.attempts if mastery_row else 0,
        "correct_count": mastery_row.correct_count if mastery_row else 0,
        "updated_at": mastery_row.updated_at if mastery_row else None,
        "mappings": [
            {
                "textbook_id": book.id,
                "textbook_title": book.title,
                "chapter_id": chapter.id,
                "chapter_title": chapter.title,
                "page_start": chapter.page_start,
                "local_knowledge_point_id": local.id,
            }
            for local, chapter, book in mappings
        ],
        "recent_answers": [
            {
                **answer_evidence(detail, max_score),
                "record_id": record.id,
                "submitted_at": record.submitted_at,
            }
            for detail, record, max_score in evidence
        ],
    }


@router.get("/path", response_model=LearningPathRead)
def learning_path(
    subject: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningPathRead:
    point_stmt = (
        select(GlobalKnowledgePoint)
        .join(
            LocalKnowledgePoint,
            LocalKnowledgePoint.global_knowledge_point_id == GlobalKnowledgePoint.id,
        )
        .join(Textbook, Textbook.id == LocalKnowledgePoint.textbook_id)
        .where(Textbook.owner_id == current_user.id)
        .distinct()
    )
    if subject:
        point_stmt = point_stmt.where(GlobalKnowledgePoint.subject == subject)
    points = db.scalars(
        point_stmt.order_by(GlobalKnowledgePoint.grade, GlobalKnowledgePoint.id)
    ).all()
    point_ids = {point.id for point in points}
    mastery_rows = db.scalars(
        select(UserMastery).where(
            UserMastery.user_id == current_user.id,
            UserMastery.global_knowledge_point_id.in_(point_ids) if point_ids else False,
        )
    ).all()
    mastery_by_id = {row.global_knowledge_point_id: row.mastery for row in mastery_rows}
    relations = (
        db.scalars(
            select(KnowledgeRelation).where(
                KnowledgeRelation.source_id.in_(point_ids),
                KnowledgeRelation.target_id.in_(point_ids),
            )
        ).all()
        if point_ids
        else []
    )
    nodes: list[LearningPathNode] = []
    for point in points:
        value = mastery_by_id.get(point.id, 0.0)
        state = "mastered" if value >= 0.8 else "learning" if value > 0 else "not_started"
        nodes.append(
            LearningPathNode(
                id=point.id,
                name=point.name,
                subject=point.subject,
                grade=point.grade,
                mastery=value,
                status=state,
            )
        )
    return LearningPathRead(
        nodes=nodes,
        edges=[
            LearningPathEdge(
                source=row.source_id,
                target=row.target_id,
                relation_type=row.relation_type,
            )
            for row in relations
        ],
    )
