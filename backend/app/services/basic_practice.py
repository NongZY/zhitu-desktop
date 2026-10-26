"""Small, explicit mathematics templates, not PDF extraction or LLM output."""

import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chapter, GlobalKnowledgePoint, LocalKnowledgePoint, Question, Textbook

TOPICS = (
    "绝对值",
    "相反数",
    "正数和负数",
    "加法",
    "减法",
    "乘法",
    "除法",
    "乘方",
    "一元一次方程",
    "整式",
    "余角和补角",
)
PRACTICE_TYPES = ("single_choice", "multiple_choice", "true_false", "fill_blank", "short_answer")


def make_problem(topic: str, rng: random.Random) -> tuple[str, str, str]:
    a, b = rng.randint(-50, 50), rng.choice([n for n in range(-20, 21) if n])
    if topic == "绝对值":
        return f"求 {a} 的绝对值。", str(abs(a)), f"绝对值表示到原点的距离，所以 |{a}| = {abs(a)}。"
    if topic == "相反数":
        return f"{a} 的相反数是多少？", str(-a), f"相反数之和为 0，因此答案是 {-a}。"
    if topic == "正数和负数":
        return (
            f"在 {a}、{b}、0 中，有几个正数？",
            str(int(a > 0) + int(b > 0)),
            "正数大于 0；0 既不是正数也不是负数。",
        )
    if topic in ("加法", "减法", "乘法", "除法"):
        symbol, value = {
            "加法": ("+", a + b),
            "减法": ("−", a - b),
            "乘法": ("×", a * b),
            "除法": ("÷", a),
        }[topic]
        left = a * b if topic == "除法" else a
        expression = f"({left}) {symbol} ({b})"
        return f"计算：{expression}。", str(value), f"{expression} = {value}。"
    if topic == "乘方":
        base, power = rng.randint(-12, 12), rng.randint(2, 4)
        return (
            f"计算：({base})^{power}。",
            str(base**power),
            f"将 {base} 连乘 {power} 次，结果为 {base**power}。",
        )
    if topic == "一元一次方程":
        c = b * a + 7
        return (
            f"解方程：({b})x + 7 = {c}。",
            str(a),
            f"两边减 7，得 ({b})x = {c - 7}；再除以 {b}，得 x = {a}。",
        )
    if topic == "整式":
        return (
            f"合并同类项：({a})x + ({b})x，结果中 x 的系数是多少？",
            str(a + b),
            f"同类项的系数相加：({a}) + ({b}) = {a + b}。",
        )
    angle = rng.randint(1, 89)
    return (
        f"一个角是 {angle}°，它的余角是多少度？（填数字）",
        str(90 - angle),
        f"两角互余时和为 90°，所以为 {90 - angle}°。",
    )


def typed_problem(topic: str, kind: str, rng: random.Random) -> tuple[str, object, object, str]:
    stem, answer, explanation = make_problem(topic, rng)
    number = int(answer)
    if kind == "single_choice":
        values = [
            number,
            *(number + offset for offset in rng.sample([-5, -3, -2, -1, 1, 2, 3, 5], 3)),
        ]
        rng.shuffle(values)
        options = [{"key": chr(65 + i), "text": str(value)} for i, value in enumerate(values)]
        return stem, options, chr(65 + values.index(number)), explanation
    if kind == "multiple_choice":
        statements = [
            (f"结果是 {number}。", True),
            (f"结果加 1 等于 {number + 1}。", True),
            (f"结果是 {number + 1}。", False),
            (f"结果减 1 等于 {number + 1}。", False),
        ]
        rng.shuffle(statements)
        options = [{"key": chr(65 + i), "text": text} for i, (text, _) in enumerate(statements)]
        keys = [chr(65 + i) for i, (_, correct) in enumerate(statements) if correct]
        return stem + " 根据结果，选出所有正确的说法。", options, keys, explanation
    if kind == "true_false":
        correct = rng.choice([True, False])
        proposed = number if correct else number + rng.choice([-3, -1, 1, 3])
        return stem + f" 有人给出的答案是 {proposed}，这个答案正确吗？", None, correct, explanation
    if kind == "short_answer":
        return stem + " 请写出结果，并说明解题过程。", None, f"{answer}。{explanation}", explanation
    return stem, None, answer, explanation


def fill_basic_questions(
    db: Session,
    book: Textbook,
    user_id: int,
    count: int,
    chapter_ids: list[int],
    seed: int | None = None,
    *,
    question_types: list[str] | None = None,
    knowledge_point_ids: list[int] | None = None,
) -> int:
    from app.desktop.profile import current_profile
    if current_profile() is not None:
        # Desktop learners first preview/confirm body-grounded candidates in
        # textbook_practice; never silently infer new exercises from a title.
        return 0
    if "数学" not in book.subject or count <= 0:
        return 0
    kinds = question_types or list(PRACTICE_TYPES)
    if any(kind not in PRACTICE_TYPES for kind in kinds):
        return 0
    stmt = select(Chapter).where(Chapter.textbook_id == book.id)
    if chapter_ids:
        stmt = stmt.where(Chapter.id.in_(chapter_ids))
    chapters = db.scalars(stmt.order_by(Chapter.order_index, Chapter.id)).all()
    if knowledge_point_ids:
        selected_points = db.scalars(
            select(LocalKnowledgePoint).where(
                LocalKnowledgePoint.id.in_(knowledge_point_ids),
                LocalKnowledgePoint.textbook_id == book.id,
                LocalKnowledgePoint.chapter_id.in_([c.id for c in chapters]),
            )
        ).all()
        by_id = {c.id: c for c in chapters}
        choices = [
            (by_id[p.chapter_id], topic, p)
            for p in selected_points
            for topic in TOPICS
            if topic in p.name
        ]
    else:
        choices = [(c, topic, None) for c in chapters for topic in TOPICS if topic in c.title]
    if not choices:
        return 0
    rng = random.Random(seed)
    existing = set(
        db.execute(
            select(Question.question_type, Question.stem).where(Question.textbook_id == book.id)
        ).all()
    )
    points: dict[tuple[int, str], LocalKnowledgePoint] = {}
    added = 0
    for _ in range(count * 100):
        chapter, topic, selected_point = rng.choice(choices)
        kind = kinds[added % len(kinds)]
        stem, options, answer, explanation = typed_problem(topic, kind, rng)
        if (kind, stem) in existing:
            continue
        key = (chapter.id, topic)
        if selected_point is not None:
            point = selected_point
        elif key not in points:
            point = db.scalar(
                select(LocalKnowledgePoint).where(
                    LocalKnowledgePoint.chapter_id == chapter.id,
                    LocalKnowledgePoint.name == topic,
                )
            )
            if point is None:
                global_point = db.scalar(
                    select(GlobalKnowledgePoint).where(
                        GlobalKnowledgePoint.name == topic,
                        GlobalKnowledgePoint.subject == book.subject,
                    )
                )
                if global_point is None:
                    global_point = GlobalKnowledgePoint(
                        name=topic, subject=book.subject, grade=book.grade
                    )
                    db.add(global_point)
                    db.flush()
                point = LocalKnowledgePoint(
                    textbook_id=book.id,
                    chapter_id=chapter.id,
                    name=topic,
                    global_knowledge_point_id=global_point.id,
                )
                db.add(point)
                db.flush()
            points[key] = point
        else:
            point = points[key]
        db.add(
            Question(
                textbook_id=book.id,
                chapter_id=chapter.id,
                knowledge_point_id=point.id,
                stem=stem,
                options=options,
                correct_answer=answer,
                explanation="系统编写的基础练习（不是课本原题）。" + explanation,
                question_type=kind,
                difficulty=2,
                status="approved",
                source="generated_template",
                created_by=user_id,
            )
        )
        existing.add((kind, stem))
        added += 1
        if added == count:
            break
    db.flush()
    return added
