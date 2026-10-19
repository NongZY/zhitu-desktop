"""One score interpretation for history, dashboards and learning evidence."""

from app.models import AnswerDetail, ExamPaper, ExamRecord


def record_summary(record: ExamRecord, paper: ExamPaper) -> dict:
    scores = {item.question_id: item.score for item in paper.paper_questions}
    pending = sum(detail.is_correct is None for detail in record.details)
    # Keep legacy records readable even if they predate per-question evidence.
    graded_total = (
        sum(
            scores.get(detail.question_id, 0)
            for detail in record.details
            if detail.is_correct is not None
        )
        if record.details
        else record.total_score
    )
    return {
        "id": record.id,
        "paper_id": paper.id,
        "title": paper.title,
        "textbook_id": paper.textbook_id,
        "score": record.score,
        "total_score": record.total_score,
        "correct_count": record.correct_count,
        "wrong_count": record.wrong_count,
        "pending_count": pending,
        "graded_total_score": graded_total,
        "duration_seconds": record.duration_seconds,
        "submitted_at": record.submitted_at,
        "status": "pending_self_check" if pending else record.status,
    }


def answer_evidence(detail: AnswerDetail, max_score: float) -> dict:
    question = detail.question
    point = question.knowledge_point
    return {
        "question_id": question.id,
        "stem": question.stem,
        "question_type": question.question_type,
        "options": question.options,
        "user_answer": detail.user_answer,
        "correct_answer": question.correct_answer,
        "is_correct": detail.is_correct,
        "score": detail.score,
        "max_score": max_score,
        "explanation": question.explanation,
        "time_spent_seconds": detail.time_spent_seconds,
        "knowledge_point_id": question.knowledge_point_id,
        "global_knowledge_point_id": point.global_knowledge_point_id if point else None,
        "knowledge_point_name": point.name if point else None,
        "chapter_id": question.chapter_id,
        "textbook_id": question.textbook_id,
    }
