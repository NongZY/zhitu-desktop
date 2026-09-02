from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import (
    Chapter,
    GlobalKnowledgePoint,
    ImportTask,
    KnowledgePointMapping,
    KnowledgeRelation,
    LocalKnowledgePoint,
    Question,
    Textbook,
    User,
)
from app.schemas import (
    ChapterCreate,
    ChapterRead,
    ChapterTree,
    ChapterUpdate,
    KnowledgePointCreate,
    KnowledgePointRead,
    KnowledgePointUpdate,
    TextbookCreate,
    TextbookList,
    TextbookRead,
    TextbookStructure,
    TextbookUpdate,
)
from app.security import get_current_user, require_staff

router = APIRouter(tags=["教材与知识点"])


def _textbook_or_404(db: Session, textbook_id: int) -> Textbook:
    textbook = db.get(Textbook, textbook_id)
    if textbook is None:
        raise HTTPException(status_code=404, detail="教材不存在")
    return textbook


def _chapter_or_404(db: Session, chapter_id: int) -> Chapter:
    chapter = db.get(Chapter, chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="章节不存在")
    return chapter


@router.get("/textbooks", response_model=TextbookList)
def list_textbooks(
    q: str | None = None,
    subject: str | None = None,
    grade: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TextbookList:
    stmt = select(Textbook)
    if q:
        stmt = stmt.where(or_(Textbook.title.contains(q), Textbook.description.contains(q)))
    if subject:
        stmt = stmt.where(Textbook.subject == subject)
    if grade:
        stmt = stmt.where(Textbook.grade == grade)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    chapter_count = (
        select(func.count(Chapter.id))
        .where(Chapter.textbook_id == Textbook.id)
        .correlate(Textbook)
        .scalar_subquery()
    )
    point_count = (
        select(func.count(LocalKnowledgePoint.id))
        .where(LocalKnowledgePoint.textbook_id == Textbook.id)
        .correlate(Textbook)
        .scalar_subquery()
    )
    question_count = (
        select(func.count(Question.id))
        .where(Question.textbook_id == Textbook.id)
        .correlate(Textbook)
        .scalar_subquery()
    )
    latest_progress = (
        select(ImportTask.progress)
        .where(ImportTask.textbook_id == Textbook.id)
        .order_by(ImportTask.created_at.desc())
        .limit(1)
        .correlate(Textbook)
        .scalar_subquery()
    )
    rows = db.execute(
        stmt.add_columns(
            chapter_count.label("chapter_count"),
            point_count.label("knowledge_point_count"),
            question_count.label("question_count"),
            func.coalesce(latest_progress, 0).label("processing_progress"),
        )
        .order_by(Textbook.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        TextbookRead.model_validate(textbook).model_copy(
            update={
                "chapter_count": chapters,
                "knowledge_point_count": points,
                "question_count": questions,
                "processing_progress": progress,
            }
        )
        for textbook, chapters, points, questions, progress in rows
    ]
    return TextbookList(items=items, total=total, page=page, page_size=page_size)


@router.post("/textbooks", response_model=TextbookRead, status_code=201)
def create_textbook(
    payload: TextbookCreate,
    staff: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> Textbook:
    textbook = Textbook(**payload.model_dump(), owner_id=staff.id)
    db.add(textbook)
    db.commit()
    db.refresh(textbook)
    return textbook


@router.get("/textbooks/{textbook_id}", response_model=TextbookRead)
def get_textbook(
    textbook_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Textbook:
    return _textbook_or_404(db, textbook_id)


@router.patch("/textbooks/{textbook_id}", response_model=TextbookRead)
def update_textbook(
    textbook_id: int,
    payload: TextbookUpdate,
    _: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> Textbook:
    textbook = _textbook_or_404(db, textbook_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(textbook, key, value)
    db.commit()
    db.refresh(textbook)
    return textbook


@router.delete("/textbooks/{textbook_id}", status_code=204)
def delete_textbook(
    textbook_id: int,
    _: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> Response:
    db.delete(_textbook_or_404(db, textbook_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/textbooks/{textbook_id}/chapters", response_model=ChapterRead, status_code=201)
def create_chapter(
    textbook_id: int,
    payload: ChapterCreate,
    _: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> Chapter:
    _textbook_or_404(db, textbook_id)
    if payload.parent_id is not None:
        parent = _chapter_or_404(db, payload.parent_id)
        if parent.textbook_id != textbook_id:
            raise HTTPException(status_code=422, detail="父章节不属于当前教材")
    chapter = Chapter(textbook_id=textbook_id, **payload.model_dump())
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


@router.patch("/chapters/{chapter_id}", response_model=ChapterRead)
def update_chapter(
    chapter_id: int,
    payload: ChapterUpdate,
    _: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> Chapter:
    chapter = _chapter_or_404(db, chapter_id)
    changes = payload.model_dump(exclude_unset=True)
    if "parent_id" in changes and changes["parent_id"] is not None:
        if changes["parent_id"] == chapter.id:
            raise HTTPException(status_code=422, detail="章节不能以自身为父章节")
        parent = _chapter_or_404(db, changes["parent_id"])
        if parent.textbook_id != chapter.textbook_id:
            raise HTTPException(status_code=422, detail="父章节不属于当前教材")
    for key, value in changes.items():
        setattr(chapter, key, value)
    db.commit()
    db.refresh(chapter)
    return chapter


@router.delete("/chapters/{chapter_id}", status_code=204)
def delete_chapter(
    chapter_id: int,
    _: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> Response:
    db.delete(_chapter_or_404(db, chapter_id))
    db.commit()
    return Response(status_code=204)


@router.post(
    "/chapters/{chapter_id}/knowledge-points",
    response_model=KnowledgePointRead,
    status_code=201,
)
def create_knowledge_point(
    chapter_id: int,
    payload: KnowledgePointCreate,
    _: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> LocalKnowledgePoint:
    chapter = _chapter_or_404(db, chapter_id)
    textbook = _textbook_or_404(db, chapter.textbook_id)
    global_id = payload.global_knowledge_point_id
    if global_id is not None:
        if db.get(GlobalKnowledgePoint, global_id) is None:
            raise HTTPException(status_code=422, detail="全局知识点不存在")
    else:
        global_point = db.scalar(
            select(GlobalKnowledgePoint).where(
                GlobalKnowledgePoint.name == payload.name,
                GlobalKnowledgePoint.subject == textbook.subject,
            )
        )
        if global_point is None:
            global_point = GlobalKnowledgePoint(
                name=payload.name,
                subject=textbook.subject,
                grade=textbook.grade,
                description=payload.description,
            )
            db.add(global_point)
            db.flush()
        global_id = global_point.id
    point = LocalKnowledgePoint(
        textbook_id=chapter.textbook_id,
        chapter_id=chapter.id,
        global_knowledge_point_id=global_id,
        name=payload.name,
        description=payload.description,
        order_index=payload.order_index,
    )
    db.add(point)
    db.flush()
    db.add(
        KnowledgePointMapping(
            local_id=point.id, global_id=global_id, confidence=1.0, confirmed=True
        )
    )
    db.commit()
    db.refresh(point)
    return point


@router.patch("/knowledge-points/{point_id}", response_model=KnowledgePointRead)
def update_knowledge_point(
    point_id: int,
    payload: KnowledgePointUpdate,
    _: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> LocalKnowledgePoint:
    point = db.get(LocalKnowledgePoint, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="知识点不存在")
    changes = payload.model_dump(exclude_unset=True)
    global_id = changes.get("global_knowledge_point_id")
    if global_id is not None and db.get(GlobalKnowledgePoint, global_id) is None:
        raise HTTPException(status_code=422, detail="全局知识点不存在")
    for key, value in changes.items():
        setattr(point, key, value)
    if global_id is not None:
        mapping = db.scalar(
            select(KnowledgePointMapping).where(KnowledgePointMapping.local_id == point.id)
        )
        if mapping:
            mapping.global_id = global_id
            mapping.confirmed = True
        else:
            db.add(
                KnowledgePointMapping(
                    local_id=point.id, global_id=global_id, confidence=1, confirmed=True
                )
            )
    db.commit()
    db.refresh(point)
    return point


@router.delete("/knowledge-points/{point_id}", status_code=204)
def delete_knowledge_point(
    point_id: int,
    _: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> Response:
    point = db.get(LocalKnowledgePoint, point_id)
    if point is None:
        raise HTTPException(status_code=404, detail="知识点不存在")
    db.delete(point)
    db.commit()
    return Response(status_code=204)


def _tree(chapters: list[Chapter]) -> list[ChapterTree]:
    by_parent: dict[int | None, list[Chapter]] = {}
    for chapter in chapters:
        by_parent.setdefault(chapter.parent_id, []).append(chapter)

    def build(parent_id: int | None) -> list[ChapterTree]:
        result: list[ChapterTree] = []
        for chapter in sorted(
            by_parent.get(parent_id, []), key=lambda item: (item.order_index, item.id)
        ):
            node = ChapterTree.model_validate(chapter)
            node.knowledge_points = [
                KnowledgePointRead.model_validate(point)
                for point in sorted(
                    chapter.knowledge_points, key=lambda item: (item.order_index, item.id)
                )
            ]
            node.children = build(chapter.id)
            result.append(node)
        return result

    return build(None)


@router.get("/textbooks/{textbook_id}/structure", response_model=TextbookStructure)
def textbook_structure(
    textbook_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TextbookStructure:
    textbook = db.scalar(
        select(Textbook)
        .where(Textbook.id == textbook_id)
        .options(selectinload(Textbook.chapters).selectinload(Chapter.knowledge_points))
    )
    if textbook is None:
        raise HTTPException(status_code=404, detail="教材不存在")
    return TextbookStructure(textbook=textbook, chapters=_tree(textbook.chapters))


@router.post("/textbooks/{textbook_id}/publish", response_model=TextbookRead)
def publish_textbook(
    textbook_id: int,
    _: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> Textbook:
    textbook = db.scalar(
        select(Textbook)
        .where(Textbook.id == textbook_id)
        .options(selectinload(Textbook.chapters).selectinload(Chapter.knowledge_points))
    )
    if textbook is None:
        raise HTTPException(status_code=404, detail="教材不存在")
    if not textbook.chapters:
        raise HTTPException(status_code=422, detail="发布前至少需要一个章节")
    if not any(chapter.knowledge_points for chapter in textbook.chapters):
        raise HTTPException(status_code=422, detail="发布前至少需要一个知识点")
    textbook.parse_status = "ready"
    db.commit()
    db.refresh(textbook)
    return textbook


@router.post("/knowledge-points/relations", status_code=201)
def create_relation(
    source_id: int,
    target_id: int,
    relation_type: str = "prerequisite",
    _: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    if source_id == target_id:
        raise HTTPException(status_code=422, detail="知识点关系不能指向自身")
    if (
        db.get(GlobalKnowledgePoint, source_id) is None
        or db.get(GlobalKnowledgePoint, target_id) is None
    ):
        raise HTTPException(status_code=404, detail="全局知识点不存在")
    relation = KnowledgeRelation(
        source_id=source_id, target_id=target_id, relation_type=relation_type
    )
    db.add(relation)
    db.commit()
    db.refresh(relation)
    return {
        "id": relation.id,
        "source_id": source_id,
        "target_id": target_id,
        "relation_type": relation_type,
    }
