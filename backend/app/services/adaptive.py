from __future__ import annotations

import math
import random
from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LocalKnowledgePoint, Question, UserMastery


def normalize_answer(value: object) -> object:
    if isinstance(value, str):
        return " ".join(value.strip().lower().split())
    if isinstance(value, list):
        return sorted(normalize_answer(item) for item in value)
    if isinstance(value, dict):
        return {str(key): normalize_answer(item) for key, item in sorted(value.items())}
    return value


def grade_objective(question: Question, answer: object) -> bool | None:
    if question.question_type == "short_answer":
        return None
    if question.question_type == "fill_blank":
        # Blank positions are ordered. A single blank may be stored as a string
        # or a one-item list; the learner enters multiple blanks one per line.
        def blanks(value):
            if isinstance(value, str):
                value = value.strip().splitlines()
            if not isinstance(value, list) or not value:
                return None
            if not all(isinstance(item, str) and item.strip() for item in value):
                return None
            return [normalize_answer(item) for item in value]
        submitted, expected = blanks(answer), blanks(question.correct_answer)
        return submitted is not None and expected is not None and submitted == expected
    if normalize_answer(answer) == normalize_answer(question.correct_answer):
        return True
    if question.question_type not in {"single_choice", "multiple_choice"}:
        return False
    option_map: dict[str, object] = {}
    if isinstance(question.options, list):
        for index, option in enumerate(question.options):
            default_key = chr(65 + index)
            if isinstance(option, dict):
                key = str(option.get("key", default_key)).upper()
                option_map[key] = option.get("text", option.get("value", key))
            else:
                option_map[default_key] = option
    elif isinstance(question.options, dict):
        option_map = {str(key).upper(): value for key, value in question.options.items()}

    def resolve(value: object) -> object:
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if isinstance(value, str):
            return option_map.get(value.strip().upper(), value)
        return value

    return normalize_answer(resolve(answer)) == normalize_answer(resolve(question.correct_answer))


def local_point_weights(
    db: Session, user_id: int, questions: Iterable[Question]
) -> dict[int, float]:
    point_ids = {q.knowledge_point_id for q in questions if q.knowledge_point_id is not None}
    if not point_ids:
        return {}
    points = db.scalars(
        select(LocalKnowledgePoint).where(LocalKnowledgePoint.id.in_(point_ids))
    ).all()
    global_by_local = {point.id: point.global_knowledge_point_id for point in points}
    global_ids = {value for value in global_by_local.values() if value is not None}
    mastery_by_global: dict[int, float] = {}
    if global_ids:
        rows = db.scalars(
            select(UserMastery).where(
                UserMastery.user_id == user_id,
                UserMastery.global_knowledge_point_id.in_(global_ids),
            )
        ).all()
        now = datetime.now(timezone.utc)
        for row in rows:
            updated = row.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            elapsed_days = max(0.0, (now - updated).total_seconds() / 86400)
            mastery_by_global[row.global_knowledge_point_id] = decayed_mastery(
                row.mastery, elapsed_days
            )
    return {
        local_id: round(max(0.2, 1.25 - mastery_by_global.get(global_id, 0.5)), 4)
        for local_id, global_id in global_by_local.items()
    }


def weighted_sample_without_replacement(
    questions: list[Question],
    count: int,
    point_weights: dict[int, float],
    seed: int | None,
) -> list[Question]:
    rng = random.Random(seed)
    pool = list(questions)
    chosen: list[Question] = []
    while pool and len(chosen) < count:
        weights = [
            point_weights.get(question.knowledge_point_id or -1, 1.0)
            * (0.9 + question.difficulty * 0.04)
            for question in pool
        ]
        selected = rng.choices(pool, weights=weights, k=1)[0]
        chosen.append(selected)
        pool.remove(selected)
    return chosen


def update_mastery(
    db: Session, user_id: int, question: Question, is_correct: bool | None
) -> UserMastery | None:
    point = question.knowledge_point
    if point is None or point.global_knowledge_point_id is None or is_correct is None:
        return None
    mastery = db.scalar(
        select(UserMastery).where(
            UserMastery.user_id == user_id,
            UserMastery.global_knowledge_point_id == point.global_knowledge_point_id,
        )
    )
    if mastery is None:
        mastery = UserMastery(
            user_id=user_id,
            global_knowledge_point_id=point.global_knowledge_point_id,
            mastery=0.5,
            attempts=0,
            correct_count=0,
        )
        db.add(mastery)
        # SessionLocal disables autoflush. Persist the new row now so a second
        # question for the same knowledge point reuses it within this submission.
        db.flush()
    difficulty_factor = 0.85 + 0.05 * question.difficulty
    target = 1.0 if is_correct else 0.0
    learning_rate = 0.24 * difficulty_factor
    mastery.mastery = round(
        min(1.0, max(0.0, mastery.mastery + learning_rate * (target - mastery.mastery))),
        4,
    )
    mastery.attempts += 1
    if is_correct:
        mastery.correct_count += 1
    return mastery


def decayed_mastery(value: float, days_since_practice: float, half_life_days: float = 90) -> float:
    """A conservative display helper; persisted mastery is not destructively decayed."""
    if days_since_practice <= 0:
        return value
    return value * math.pow(0.5, days_since_practice / half_life_days)
