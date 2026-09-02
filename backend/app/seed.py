from __future__ import annotations

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import (
    Chapter,
    DocumentChunk,
    GlobalKnowledgePoint,
    KnowledgePointMapping,
    KnowledgeRelation,
    LocalKnowledgePoint,
    Question,
    Textbook,
    User,
    UserRole,
)
from app.security import hash_password

DEMO_USERS = [
    ("admin@example.com", "系统管理员", UserRole.admin, "Admin123!"),
    ("teacher@example.com", "示例教师", UserRole.teacher, "Teacher123!"),
    ("student@example.com", "示例学生", UserRole.student, "Student123!"),
]


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        users: dict[UserRole, User] = {}
        for email, name, role, password in DEMO_USERS:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    email=email,
                    name=name,
                    role=role,
                    hashed_password=hash_password(password),
                )
                db.add(user)
                db.flush()
            users[role] = user

        textbook = db.scalar(select(Textbook).where(Textbook.title == "七年级数学示例教材"))
        if textbook is None:
            textbook = Textbook(
                title="七年级数学示例教材",
                edition="演示版",
                subject="数学",
                grade="七年级",
                description="用于体验章节、题库、自适应考试与教材问答的内置示例。",
                parse_status="ready",
                owner_id=users[UserRole.teacher].id,
            )
            db.add(textbook)
            db.flush()
            chapter = Chapter(
                textbook_id=textbook.id,
                title="第一章 有理数",
                order_index=1,
                page_start=1,
                page_end=18,
                summary="认识正数、负数以及有理数的四则运算。",
            )
            db.add(chapter)
            db.flush()
            globals_: list[GlobalKnowledgePoint] = []
            locals_: list[LocalKnowledgePoint] = []
            for order, (name, description) in enumerate(
                [
                    ("有理数加法", "同号相加、异号相加以及加法运算律。"),
                    ("有理数减法", "减去一个数等于加上这个数的相反数。"),
                    ("绝对值", "数轴上的点到原点的距离。"),
                ],
                start=1,
            ):
                global_point = GlobalKnowledgePoint(
                    name=name, subject="数学", grade="七年级", description=description
                )
                db.add(global_point)
                db.flush()
                local_point = LocalKnowledgePoint(
                    textbook_id=textbook.id,
                    chapter_id=chapter.id,
                    global_knowledge_point_id=global_point.id,
                    name=name,
                    description=description,
                    order_index=order,
                )
                db.add(local_point)
                db.flush()
                db.add(
                    KnowledgePointMapping(
                        local_id=local_point.id,
                        global_id=global_point.id,
                        confidence=1,
                        confirmed=True,
                    )
                )
                globals_.append(global_point)
                locals_.append(local_point)
            db.add(
                KnowledgeRelation(
                    source_id=globals_[0].id,
                    target_id=globals_[1].id,
                    relation_type="prerequisite",
                )
            )
            question_data = [
                (
                    locals_[0],
                    "single_choice",
                    "计算：3 + (-5) = ?",
                    ["-8", "-2", "2", "8"],
                    "-2",
                    2,
                ),
                (locals_[0], "true_false", "两个负数相加，结果一定是负数。", None, True, 1),
                (locals_[1], "fill_blank", "计算：4 - 7 = ____。", None, "-3", 2),
                (
                    locals_[1],
                    "single_choice",
                    "把 6 - (-2) 改写成加法是？",
                    ["6 + 2", "6 + (-2)", "-6 + 2", "-6 - 2"],
                    "6 + 2",
                    2,
                ),
                (locals_[2], "single_choice", "|-6| 的值是？", ["-6", "0", "6", "±6"], "6", 1),
                (locals_[2], "fill_blank", "若 |x|=3，则 x=____。", None, "3或-3", 3),
            ]
            for point, question_type, stem, options, answer, difficulty in question_data:
                db.add(
                    Question(
                        textbook_id=textbook.id,
                        chapter_id=chapter.id,
                        knowledge_point_id=point.id,
                        question_type=question_type,
                        stem=stem,
                        options=options,
                        correct_answer=answer,
                        explanation=f"本题考查{point.name}。",
                        difficulty=difficulty,
                        status="approved",
                        source="seed",
                        created_by=users[UserRole.teacher].id,
                    )
                )
            chunks = [
                "有理数加法法则：同号两数相加，取相同的符号，并把绝对值相加；绝对值不相等的异号两数相加，取绝对值较大的加数的符号，并用较大的绝对值减去较小的绝对值。",
                "有理数减法法则：减去一个数，等于加上这个数的相反数。用式子表示为 a-b=a+(-b)。",
                "数轴上表示数 a 的点与原点的距离叫做数 a 的绝对值，记作 |a|。正数的绝对值是它本身，负数的绝对值是它的相反数，0 的绝对值是 0。",
            ]
            for index, content in enumerate(chunks):
                db.add(
                    DocumentChunk(
                        textbook_id=textbook.id,
                        chapter_id=chapter.id,
                        content=content,
                        page_number=5 + index * 4,
                        chunk_index=index,
                        metadata_json={"source": "seed"},
                    )
                )
        db.commit()
    print("示例数据已就绪。可使用 README 中的三个账号登录。")


if __name__ == "__main__":
    seed()
