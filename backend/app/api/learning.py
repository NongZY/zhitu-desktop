from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import (
    ExamPaper,
    ExamRecord,
    GlobalKnowledgePoint,
    KnowledgeRelation,
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
    rows = db.scalars(
        select(UserMastery)
        .where(UserMastery.user_id == current_user.id)
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
    stmt = select(WrongQuestion).where(WrongQuestion.user_id == current_user.id)
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
        select(WrongQuestion).where(
            WrongQuestion.id == item_id, WrongQuestion.user_id == current_user.id
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
    records = db.scalars(select(ExamRecord).where(ExamRecord.user_id == current_user.id)).all()
    mastery_rows = db.scalars(
        select(UserMastery)
        .where(UserMastery.user_id == current_user.id)
        .options(selectinload(UserMastery.global_knowledge_point))
        .order_by(UserMastery.mastery.asc())
    ).all()
    average_rate = (
        sum(row.score / row.total_score for row in records if row.total_score > 0)
        / len([row for row in records if row.total_score > 0])
        if any(row.total_score > 0 for row in records)
        else 0.0
    )
    mastery_average = (
        sum(row.mastery for row in mastery_rows) / len(mastery_rows) if mastery_rows else 0.0
    )
    wrong_count = (
        db.scalar(
            select(func.count())
            .select_from(WrongQuestion)
            .where(
                WrongQuestion.user_id == current_user.id,
                WrongQuestion.resolved.is_(False),
            )
        )
        or 0
    )
    textbook_count = db.scalar(select(func.count()).select_from(Textbook)) or 0
    recent_rows = db.execute(
        select(ExamRecord, ExamPaper)
        .join(ExamPaper, ExamPaper.id == ExamRecord.paper_id)
        .where(ExamRecord.user_id == current_user.id)
        .order_by(ExamRecord.submitted_at.desc())
        .limit(5)
    ).all()
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
            daily[day]["questions"] += record.correct_count + record.wrong_count
    weak_items = [_mastery_item(row) for row in mastery_rows[:5]]
    return DashboardRead(
        textbook_count=textbook_count,
        exam_count=len(records),
        completed_exam_count=len(records),
        average_score_rate=round(average_rate, 4),
        average_score=round(average_rate * 100, 2),
        study_minutes=round(sum((row.duration_seconds or 0) for row in records) / 60),
        mastery_average=round(mastery_average, 4),
        weak_points=weak_items,
        wrong_question_count=wrong_count,
        recent_exams=[
            {
                "id": record.id,
                "title": paper.title,
                "score": record.score,
                "total_score": record.total_score,
                "submitted_at": record.submitted_at,
            }
            for record, paper in recent_rows
        ],
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    rows = db.execute(
        select(ExamRecord, ExamPaper)
        .join(ExamPaper, ExamPaper.id == ExamRecord.paper_id)
        .where(ExamRecord.user_id == current_user.id)
        .order_by(ExamRecord.submitted_at.desc())
        .limit(50)
    ).all()
    return {
        "items": [
            {
                "id": record.id,
                "paper_id": paper.id,
                "title": paper.title,
                "score": record.score,
                "total_score": record.total_score,
                "correct_count": record.correct_count,
                "wrong_count": record.wrong_count,
                "duration_seconds": record.duration_seconds,
                "submitted_at": record.submitted_at,
            }
            for record, paper in rows
        ],
        "total": len(rows),
    }


@router.get("/path", response_model=LearningPathRead)
def learning_path(
    subject: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningPathRead:
    point_stmt = select(GlobalKnowledgePoint)
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
