from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chapter, LocalKnowledgePoint, Question, Textbook


def owned_textbook_or_404(db: Session, textbook_id: int, user_id: int) -> Textbook:
    textbook = db.scalar(
        select(Textbook).where(Textbook.id == textbook_id, Textbook.owner_id == user_id)
    )
    if textbook is None:
        raise HTTPException(status_code=404, detail="教材不存在")
    return textbook


def owned_chapter_or_404(db: Session, chapter_id: int, user_id: int) -> Chapter:
    chapter = db.scalar(
        select(Chapter)
        .join(Textbook, Textbook.id == Chapter.textbook_id)
        .where(Chapter.id == chapter_id, Textbook.owner_id == user_id)
    )
    if chapter is None:
        raise HTTPException(status_code=404, detail="章节不存在")
    return chapter


def owned_knowledge_point_or_404(
    db: Session, point_id: int, user_id: int
) -> LocalKnowledgePoint:
    point = db.scalar(
        select(LocalKnowledgePoint)
        .join(Textbook, Textbook.id == LocalKnowledgePoint.textbook_id)
        .where(LocalKnowledgePoint.id == point_id, Textbook.owner_id == user_id)
    )
    if point is None:
        raise HTTPException(status_code=404, detail="知识点不存在")
    return point


def owned_question_or_404(db: Session, question_id: int, user_id: int) -> Question:
    question = db.scalar(
        select(Question)
        .join(Textbook, Textbook.id == Question.textbook_id)
        .where(Question.id == question_id, Textbook.owner_id == user_id)
    )
    if question is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    return question


def owned_global_knowledge_point_ids(db: Session, user_id: int) -> set[int]:
    return set(
        db.scalars(
            select(LocalKnowledgePoint.global_knowledge_point_id)
            .join(Textbook, Textbook.id == LocalKnowledgePoint.textbook_id)
            .where(
                Textbook.owner_id == user_id,
                LocalKnowledgePoint.global_knowledge_point_id.is_not(None),
            )
            .distinct()
        ).all()
    )
