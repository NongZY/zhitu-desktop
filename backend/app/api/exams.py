from __future__ import annotations

import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.access import (
    owned_chapter_or_404,
    owned_knowledge_point_or_404,
    owned_textbook_or_404,
)
from app.database import get_db
from app.models import (
    AnswerDetail,
    ExamPaper,
    ExamPaperQuestion,
    ExamRecord,
    Question,
    Textbook,
    User,
    WrongQuestion,
)
from app.schemas import (
    AnswerResult,
    ExamGenerateRequest,
    ExamPaperRead,
    ExamQuestionRead,
    ExamResultRead,
    ExamSubmitRequest,
)
from app.security import get_current_user
from app.services.adaptive import (
    grade_objective,
    local_point_weights,
    update_mastery,
    weighted_sample_without_replacement,
)
from app.services.basic_practice import PRACTICE_TYPES, fill_basic_questions
from app.services.pdf_outline import chapter_scope_ids

router = APIRouter(prefix="/exams", tags=["模拟考试"])


def _paper_or_404(db: Session, paper_id: int, user_id: int) -> ExamPaper:
    paper = db.scalar(
        select(ExamPaper)
        .where(ExamPaper.id == paper_id, ExamPaper.user_id == user_id)
        .options(selectinload(ExamPaper.paper_questions).selectinload(ExamPaperQuestion.question))
    )
    if paper is None:
        raise HTTPException(status_code=404, detail="试卷不存在")
    return paper


def _paper_read(paper: ExamPaper) -> ExamPaperRead:
    questions = [
        ExamQuestionRead(
            **{
                **item.question.__dict__,
                "order_index": item.order_index,
                "score": item.score,
            }
        )
        for item in sorted(paper.paper_questions, key=lambda row: row.order_index)
    ]
    return ExamPaperRead(
        id=paper.id,
        user_id=paper.user_id,
        textbook_id=paper.textbook_id,
        title=paper.title,
        mode=paper.mode,
        duration_minutes=paper.duration_minutes,
        total_score=paper.total_score,
        strategy=paper.strategy or {},
        created_at=paper.created_at,
        questions=questions,
    )


@router.post("/generate", response_model=ExamPaperRead, status_code=status.HTTP_201_CREATED)
def generate_exam(
    payload: ExamGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExamPaperRead:
    if payload.difficulty_min > payload.difficulty_max:
        raise HTTPException(status_code=422, detail="最低难度不能高于最高难度")
    if payload.textbook_id is not None:
        owned_textbook_or_404(db, payload.textbook_id, current_user.id)
    scope_ids: set[int] = set()
    for chapter_id in payload.chapter_ids:
        chapter = owned_chapter_or_404(db, chapter_id, current_user.id)
        if payload.textbook_id is not None and chapter.textbook_id != payload.textbook_id:
            raise HTTPException(status_code=422, detail="章节不属于所选教材")
        scope_ids.update(chapter_scope_ids(db, chapter))
    for point_id in payload.knowledge_point_ids:
        point = owned_knowledge_point_or_404(db, point_id, current_user.id)
        if payload.textbook_id is not None and point.textbook_id != payload.textbook_id:
            raise HTTPException(status_code=422, detail="知识点不属于所选教材")
        if scope_ids and point.chapter_id not in scope_ids:
            raise HTTPException(status_code=422, detail="知识点不在所选章节内，请重新选择")
    stmt = (
        select(Question)
        .join(Textbook, Textbook.id == Question.textbook_id)
        .where(
            Textbook.owner_id == current_user.id,
            Question.status == "approved",
            Question.difficulty >= payload.difficulty_min,
            Question.difficulty <= payload.difficulty_max,
        )
    )
    if payload.textbook_id is not None:
        stmt = stmt.where(Question.textbook_id == payload.textbook_id)
    if payload.chapter_ids:
        stmt = stmt.where(Question.chapter_id.in_(scope_ids))
    if payload.knowledge_point_ids:
        stmt = stmt.where(Question.knowledge_point_id.in_(payload.knowledge_point_ids))
    if payload.question_types:
        stmt = stmt.where(Question.question_type.in_(payload.question_types))
    candidates = db.scalars(stmt.options(selectinload(Question.knowledge_point))).all()
    saved_count = len(candidates)
    generated_count = 0
    requested_types = list(dict.fromkeys(payload.question_types or PRACTICE_TYPES))
    rng = random.Random(payload.random_seed)
    rng.shuffle(requested_types)
    quotas = {
        kind: payload.question_count // len(requested_types)
        + int(index < payload.question_count % len(requested_types))
        for index, kind in enumerate(requested_types)
    }
    if (
        payload.auto_fill
        and payload.textbook_id
        and payload.difficulty_min <= 2 <= payload.difficulty_max
    ):
        book = owned_textbook_or_404(db, payload.textbook_id, current_user.id)
        for index, kind in enumerate(requested_types):
            shortage = quotas[kind] - sum(q.question_type == kind for q in candidates)
            if shortage > 0:
                generated_count += fill_basic_questions(
                    db,
                    book,
                    current_user.id,
                    shortage,
                    sorted(scope_ids),
                    None if payload.random_seed is None else payload.random_seed + index,
                    question_types=[kind],
                    knowledge_point_ids=payload.knowledge_point_ids,
                )
        candidates = db.scalars(stmt.options(selectinload(Question.knowledge_point))).all()
    # An explicit request for several types must not silently become only one type.
    missing_types = [
        kind for kind in requested_types if not any(q.question_type == kind for q in candidates)
    ]
    missing_required = bool(
        payload.question_types and missing_types and payload.question_count >= len(requested_types)
    )
    if len(candidates) < payload.question_count or missing_required:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail=(
                f"当前已有 {saved_count} 道符合要求的题，数量或题型还不够这次练习。"
                + (
                    "本次未能补足题目，暂不支持的内容可以先读课本或添加自己的题。"
                    if payload.auto_fill
                    else "请先添加题目，或开启基础题补充。"
                )
                + "也可以减少题数或换个章节再试。"
            ),
        )

    point_weights = local_point_weights(db, current_user.id, candidates)

    def sample(pool: list[Question], count: int) -> list[Question]:
        if payload.mode == "adaptive":
            return weighted_sample_without_replacement(
                pool, count, point_weights, rng.randrange(2**32)
            )
        return rng.sample(pool, count)

    # Balance available types first, then fill remaining places within the same scope.
    selected: list[Question] = []
    for kind in requested_types:
        pool = [q for q in candidates if q.question_type == kind]
        selected.extend(sample(pool, min(quotas[kind], len(pool))))
    if len(selected) < payload.question_count:
        selected_ids = {q.id for q in selected}
        selected.extend(
            sample(
                [q for q in candidates if q.id not in selected_ids],
                payload.question_count - len(selected),
            )
        )
    rng.shuffle(selected)

    strategy = {
        "generated_count": generated_count,
        "mode": payload.mode,
        "candidate_count": len(candidates),
        "filters": {
            "chapter_ids": payload.chapter_ids,
            "knowledge_point_ids": payload.knowledge_point_ids,
            "question_types": payload.question_types,
            "difficulty": [payload.difficulty_min, payload.difficulty_max],
        },
        "knowledge_point_weights": {str(key): value for key, value in point_weights.items()},
    }
    paper = ExamPaper(
        user_id=current_user.id,
        textbook_id=payload.textbook_id,
        title=payload.title or ("自适应巩固练习" if payload.mode == "adaptive" else "随机模拟练习"),
        mode=payload.mode,
        duration_minutes=payload.duration_minutes,
        total_score=payload.score_per_question * len(selected),
        strategy=strategy,
    )
    db.add(paper)
    db.flush()
    for index, question in enumerate(selected, start=1):
        db.add(
            ExamPaperQuestion(
                paper_id=paper.id,
                question_id=question.id,
                order_index=index,
                score=payload.score_per_question,
            )
        )
    db.commit()
    paper = _paper_or_404(db, paper.id, current_user.id)
    return _paper_read(paper)


@router.get("/{paper_id}", response_model=ExamPaperRead)
def get_exam(
    paper_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExamPaperRead:
    return _paper_read(_paper_or_404(db, paper_id, current_user.id))


@router.post(
    "/{paper_id}/submit", response_model=ExamResultRead, status_code=status.HTTP_201_CREATED
)
def submit_exam(
    paper_id: int,
    payload: ExamSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExamResultRead:
    paper = _paper_or_404(db, paper_id, current_user.id)
    existing = db.scalar(
        select(ExamRecord).where(
            ExamRecord.paper_id == paper.id, ExamRecord.user_id == current_user.id
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="该试卷已经提交")

    paper_rows = {row.question_id: row for row in paper.paper_questions}
    submitted = {item.question_id: item for item in payload.answers}
    unknown = set(submitted) - set(paper_rows)
    if unknown:
        raise HTTPException(status_code=422, detail=f"答案包含不属于试卷的题目：{sorted(unknown)}")

    record = ExamRecord(
        paper_id=paper.id,
        user_id=current_user.id,
        total_score=paper.total_score,
        duration_seconds=payload.duration_seconds,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.flush()
    score = 0.0
    correct_count = 0
    wrong_count = 0
    pending_count = 0
    graded_total_score = 0.0
    results: list[AnswerResult] = []
    for row in sorted(paper.paper_questions, key=lambda item: item.order_index):
        answer_item = submitted.get(row.question_id)
        user_answer = answer_item.answer if answer_item is not None else None
        is_correct = grade_objective(row.question, user_answer)
        item_score = row.score if is_correct is True else 0.0
        if is_correct is None:
            pending_count += 1
        else:
            graded_total_score += row.score
        if is_correct is True:
            correct_count += 1
            score += item_score
            wrong = db.scalar(
                select(WrongQuestion).where(
                    WrongQuestion.user_id == current_user.id,
                    WrongQuestion.question_id == row.question_id,
                )
            )
            if wrong is not None:
                wrong.resolved = True
        elif is_correct is False:
            wrong_count += 1
            wrong = db.scalar(
                select(WrongQuestion).where(
                    WrongQuestion.user_id == current_user.id,
                    WrongQuestion.question_id == row.question_id,
                )
            )
            if wrong is None:
                db.add(
                    WrongQuestion(
                        user_id=current_user.id,
                        question_id=row.question_id,
                        wrong_count=1,
                    )
                )
            else:
                wrong.wrong_count += 1
                wrong.resolved = False
                wrong.last_wrong_at = datetime.now(timezone.utc)
        detail = AnswerDetail(
            record_id=record.id,
            question_id=row.question_id,
            user_answer=user_answer,
            is_correct=is_correct,
            score=item_score,
            time_spent_seconds=(
                answer_item.time_spent_seconds if answer_item is not None else None
            ),
        )
        db.add(detail)
        update_mastery(db, current_user.id, row.question, is_correct)
        results.append(
            AnswerResult(
                question_id=row.question_id,
                user_answer=user_answer,
                correct_answer=row.question.correct_answer,
                is_correct=is_correct,
                score=item_score,
                max_score=row.score,
                explanation=row.question.explanation,
            )
        )
    record.score = score
    record.correct_count = correct_count
    record.wrong_count = wrong_count
    record.status = "pending_self_check" if pending_count else "submitted"
    db.commit()
    db.refresh(record)
    return ExamResultRead(
        id=record.id,
        paper_id=record.paper_id,
        score=record.score,
        total_score=record.total_score,
        correct_count=record.correct_count,
        wrong_count=record.wrong_count,
        pending_count=pending_count,
        graded_total_score=graded_total_score,
        status=record.status,
        duration_seconds=record.duration_seconds,
        submitted_at=record.submitted_at,
        details=results,
    )
