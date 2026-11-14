from contextlib import suppress
from hashlib import sha256

import pymupdf
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.access import (
    owned_chapter_or_404,
    owned_global_knowledge_point_ids,
    owned_knowledge_point_or_404,
    owned_textbook_or_404,
)
from app.database import get_db
from app.models import (
    Chapter,
    DocumentChunk,
    DocumentChapter,
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
from app.security import get_current_user
from app.services.pdf_outline import apply_outline, chapter_scope_ids, extract_outline
from app.services.pdf_reader import page_count, reader_metadata, searchable
from app.services.storage import materialize
from app.services.standalone_questions import BANK_STATUS

router = APIRouter(tags=["教材与知识点"])


@router.get("/textbooks", response_model=TextbookList)
def list_textbooks(
    include_question_bank: bool = False,
    q: str | None = None,
    subject: str | None = None,
    grade: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TextbookList:
    stmt = select(Textbook).where(Textbook.owner_id == current_user.id)
    if not include_question_bank:
        stmt = stmt.where(Textbook.parse_status != BANK_STATUS)
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
        .where(Question.textbook_id == Textbook.id,
               or_(Textbook.parse_status != BANK_STATUS, Question.status == "approved"))
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
    latest_message = (
        select(ImportTask.message)
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
            latest_message.label("processing_message"),
        )
        .order_by((Textbook.parse_status == BANK_STATUS).desc(), Textbook.updated_at.desc())
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
                "processing_message": message,
            }
        )
        for textbook, chapters, points, questions, progress, message in rows
    ]
    return TextbookList(items=items, total=total, page=page, page_size=page_size)


@router.post("/textbooks", response_model=TextbookRead, status_code=201)
def create_textbook(
    payload: TextbookCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Textbook:
    textbook = Textbook(**payload.model_dump(), owner_id=current_user.id)
    db.add(textbook)
    db.commit()
    db.refresh(textbook)
    return textbook


@router.get("/textbooks/{textbook_id}", response_model=TextbookRead)
def get_textbook(
    textbook_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Textbook:
    return owned_textbook_or_404(db, textbook_id, current_user.id)


@router.get("/textbooks/{textbook_id}/reader")
def textbook_reader(
    textbook_id: int,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    textbook = owned_textbook_or_404(db, textbook_id, current_user.id)
    response.headers['Cache-Control'] = 'private, no-store'
    info = reader_metadata(textbook.file_path)
    return {'page_count': info.page_count, 'document_revision': info.document_revision}


@router.get("/textbooks/{textbook_id}/search")
def search_textbook_pages(
    textbook_id: int,
    response: Response,
    q: str = Query(min_length=1, max_length=100),
    chapter_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    textbook = owned_textbook_or_404(db, textbook_id, current_user.id)
    query = searchable(q)
    if not query:
        raise HTTPException(422, '请输入要查找的文字')
    stmt = select(DocumentChunk).where(
        DocumentChunk.textbook_id == textbook.id,
        DocumentChunk.metadata_json['source'].as_string() == 'pdf',
        DocumentChunk.page_number >= 1,
    )
    if chapter_id is not None:
        chapter = owned_chapter_or_404(db, chapter_id, current_user.id)
        if chapter.textbook_id != textbook.id:
            raise HTTPException(422, '章节不属于这本课本')
        stmt = stmt.where(DocumentChunk.chapter_id.in_(chapter_scope_ids(db, chapter)))
    count = page_count(textbook.file_path)
    matches = {}
    stmt = stmt.where(DocumentChunk.page_number <= count).order_by(
        DocumentChunk.page_number, DocumentChunk.chunk_index,
    )
    for chunk in db.scalars(stmt.execution_options(yield_per=100)):
        if chunk.page_number in matches:
            continue
        content = searchable(chunk.content)
        position = content.find(query)
        if position < 0:
            continue
        chapter = db.get(Chapter, chunk.chapter_id) if chunk.chapter_id else None
        start, end = max(0, position - 35), min(len(content), position + len(query) + 85)
        matches[chunk.page_number] = {
            'page_number': chunk.page_number, 'chapter_id': chunk.chapter_id,
            'chapter_title': chapter.title if chapter else None,
            'excerpt': ('…' if start else '') + content[start:end] + ('…' if end < len(content) else ''),
        }
    response.headers['Cache-Control'] = 'private, no-store'
    offset = (page - 1) * page_size
    return {'items': list(matches.values())[offset:offset + page_size],
            'total': len(matches), 'page': page, 'page_size': page_size}


@router.get("/textbooks/{textbook_id}/pages/{page_number}/image")
def textbook_page_image(
    textbook_id: int,
    page_number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    textbook = owned_textbook_or_404(db, textbook_id, current_user.id)
    return render_page_image(textbook.file_path, page_number)


def render_page_image(file_path: str | None, page_number: int, expected_sha256: str | None = None) -> Response:
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    if not file_path:
        raise HTTPException(status_code=404, detail="教材原文件不存在", headers=headers)
    if page_number < 1:
        raise HTTPException(status_code=404, detail="原页不存在", headers=headers)
    local_path, remove_after = None, False
    try:
        local_path, remove_after = materialize(file_path)
        if not local_path.is_file():
            raise HTTPException(status_code=404, detail="教材原文件不存在", headers=headers)
        # Close the file handle before parsing so even a malformed PDF can be
        # removed on Windows when it was materialized from object storage.
        content = local_path.read_bytes()
        if expected_sha256 and sha256(content).hexdigest() != expected_sha256:
            raise HTTPException(409, '原文件发生变化，无法准确显示此引用', headers=headers)
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if page_number > document.page_count:
                raise HTTPException(status_code=404, detail="原页不存在", headers=headers)
            page = document[page_number - 1]
            scale = min(2.0, 2000 / max(page.rect.width, page.rect.height))
            image = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False,
            )
            return Response(
                content=image.tobytes("png"), media_type="image/png",
                headers=headers,
            )
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="教材原文件不存在", headers=headers,
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail="原页暂时无法读取，请检查 PDF 后重试", headers=headers,
        ) from exc
    finally:
        if remove_after and local_path is not None:
            with suppress(OSError):
                local_path.unlink(missing_ok=True)


@router.patch("/textbooks/{textbook_id}", response_model=TextbookRead)
def update_textbook(
    textbook_id: int,
    payload: TextbookUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Textbook:
    textbook = owned_textbook_or_404(db, textbook_id, current_user.id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(textbook, key, value)
    db.commit()
    db.refresh(textbook)
    return textbook


@router.delete("/textbooks/{textbook_id}", status_code=204)
def delete_textbook(
    textbook_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    from sqlalchemy import delete
    from app.models import DocumentImport, DocumentPosition, DocumentRendition, DocumentSource, ReadingProgress
    from app.models import PracticeJob, PracticeCandidate, QuestionEvidence, Question, ExamPaperQuestion, AnswerDetail

    textbook = owned_textbook_or_404(db, textbook_id, current_user.id)
    question_ids = select(Question.id).where(Question.textbook_id == textbook.id)
    if (db.scalar(select(ExamPaperQuestion.id).where(ExamPaperQuestion.question_id.in_(question_ids)).limit(1))
            or db.scalar(select(AnswerDetail.id).where(AnswerDetail.question_id.in_(question_ids)).limit(1))):
        raise HTTPException(409, '这本教材已有练习记录，需要保留用于查看历史；可替换资料继续学习')
    jobs = select(PracticeJob.id).where(PracticeJob.textbook_id == textbook.id)
    db.execute(delete(PracticeCandidate).where(PracticeCandidate.job_id.in_(jobs)))
    db.execute(delete(PracticeJob).where(PracticeJob.textbook_id == textbook.id))
    db.execute(delete(QuestionEvidence).where(QuestionEvidence.textbook_id == textbook.id))
    db.execute(delete(Question).where(Question.textbook_id == textbook.id))
    # SQLite does not enable FK cascades by default; use the same transaction.
    db.execute(delete(ReadingProgress).where(ReadingProgress.textbook_id == textbook.id))
    db.execute(delete(DocumentPosition).where(DocumentPosition.textbook_id == textbook.id))
    db.execute(delete(DocumentRendition).where(DocumentRendition.textbook_id == textbook.id))
    source_ids = select(DocumentSource.id).where(DocumentSource.textbook_id == textbook.id)
    db.execute(delete(DocumentChapter).where(DocumentChapter.source_id.in_(source_ids)))
    db.execute(delete(DocumentImport).where(DocumentImport.source_id.in_(source_ids)))
    db.execute(delete(DocumentSource).where(DocumentSource.textbook_id == textbook.id))
    db.execute(delete(ImportTask).where(ImportTask.textbook_id == textbook.id))
    db.execute(delete(DocumentChunk).where(DocumentChunk.textbook_id == textbook.id))
    db.delete(textbook)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/textbooks/{textbook_id}/chapters", response_model=ChapterRead, status_code=201)
def create_chapter(
    textbook_id: int,
    payload: ChapterCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Chapter:
    book = owned_textbook_or_404(db, textbook_id, current_user.id)
    if payload.parent_id is not None:
        parent = owned_chapter_or_404(db, payload.parent_id, current_user.id)
        if parent.textbook_id != textbook_id:
            raise HTTPException(status_code=422, detail="父章节不属于当前教材")
    chapter = Chapter(textbook_id=textbook_id, **payload.model_dump())
    db.add(chapter)
    db.flush()
    from app.services.documents import current_document
    current = current_document(db, book)
    if current:
        db.add(DocumentChapter(source_id=current.source_id, chapter_id=chapter.id))
    db.commit()
    db.refresh(chapter)
    return chapter


@router.patch("/chapters/{chapter_id}", response_model=ChapterRead)
def update_chapter(
    chapter_id: int,
    payload: ChapterUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Chapter:
    chapter = owned_chapter_or_404(db, chapter_id, current_user.id)
    changes = payload.model_dump(exclude_unset=True)
    if "parent_id" in changes and changes["parent_id"] is not None:
        if changes["parent_id"] == chapter.id:
            raise HTTPException(status_code=422, detail="章节不能以自身为父章节")
        parent = owned_chapter_or_404(db, changes["parent_id"], current_user.id)
        if parent.textbook_id != chapter.textbook_id:
            raise HTTPException(status_code=422, detail="父章节不属于当前教材")
    for key, value in changes.items():
        setattr(chapter, key, value)
    db.commit()
    db.refresh(chapter)
    return chapter


@router.get("/chapters/{chapter_id}/content")
def chapter_content(
    chapter_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    chapter = owned_chapter_or_404(db, chapter_id, current_user.id)
    stmt = select(DocumentChunk).where(
        DocumentChunk.textbook_id == chapter.textbook_id,
        DocumentChunk.chapter_id.in_(chapter_scope_ids(db, chapter)),
    )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    chunks = db.scalars(stmt.order_by(DocumentChunk.page_number, DocumentChunk.chunk_index)
                        .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"id": c.id, "page_number": c.page_number, "content": c.content,
                       **({"quality_note": "本页有公式或符号需要对照原页，请勿仅凭提取文字计算。"}
                          if (c.metadata_json or {}).get("math_review_required") is True else {})}
                      for c in chunks], "total": total, "page": page, "page_size": page_size}


@router.post("/textbooks/{textbook_id}/outline")
def recognize_existing_outline(
    textbook_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    textbook = db.scalar(select(Textbook).where(
        Textbook.id == textbook_id, Textbook.owner_id == current_user.id,
    ).with_for_update())
    if textbook is None:
        raise HTTPException(status_code=404, detail="教材不存在")
    if textbook.parse_status in {"processing", "queued"}:
        raise HTTPException(status_code=409, detail="请等待当前解析任务完成")
    if not textbook.file_path:
        raise HTTPException(status_code=422, detail="请先上传 PDF")
    if db.scalar(select(Chapter.id).where(Chapter.textbook_id == textbook_id).limit(1)):
        return {"added": 0, "message": "已有章节目录，已保留你的整理内容"}
    local_path, remove_after = None, False
    try:
        local_path, remove_after = materialize(textbook.file_path)
        with pymupdf.open(local_path) as document:
            entries = extract_outline(document, [page.get_text("text") for page in document])
        if not entries:
            return {"added": 0, "message": "未识别到可靠目录，请手动添加；扫描目录需要 OCR"}
        chunks = list(db.scalars(select(DocumentChunk).where(
            DocumentChunk.textbook_id == textbook_id,
            DocumentChunk.metadata_json["source"].as_string() == "pdf",
        )))
        added = apply_outline(db, textbook_id, entries, chunks)
        db.commit()
        return {"added": added, "message": f"已添加 {added} 个章节节点并关联正文"}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail="目录识别失败，请检查 PDF 后重试") from exc
    finally:
        if remove_after and local_path is not None:
            local_path.unlink(missing_ok=True)


@router.delete("/chapters/{chapter_id}", status_code=204)
def delete_chapter(
    chapter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    chapter = owned_chapter_or_404(db, chapter_id, current_user.id)
    chapter_ids = chapter_scope_ids(db, chapter)
    from sqlalchemy import delete, update
    from app.models import PracticeJob, PracticeCandidate
    for job in db.scalars(select(PracticeJob).where(PracticeJob.textbook_id == chapter.textbook_id)):
        if any(unit['chapter_id'] in chapter_ids for unit in job.units):
            job.status, job.message = 'obsolete', '原章节已删除，旧候选仍可查看，请按当前教材重新补题。'
    db.execute(delete(DocumentChapter).where(DocumentChapter.chapter_id.in_(chapter_ids)))
    points = list(db.scalars(select(LocalKnowledgePoint.id).where(LocalKnowledgePoint.chapter_id.in_(chapter_ids))))
    db.execute(delete(KnowledgePointMapping).where(KnowledgePointMapping.local_id.in_(points)))
    db.execute(update(Question).where(Question.knowledge_point_id.in_(points)).values(knowledge_point_id=None))
    for model in (Question, DocumentChunk, PracticeCandidate):
        db.execute(update(model).where(model.chapter_id.in_(chapter_ids)).values(chapter_id=None))
    db.delete(chapter)
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LocalKnowledgePoint:
    chapter = owned_chapter_or_404(db, chapter_id, current_user.id)
    textbook = owned_textbook_or_404(db, chapter.textbook_id, current_user.id)
    global_id = payload.global_knowledge_point_id
    if global_id is not None:
        if global_id not in owned_global_knowledge_point_ids(db, current_user.id):
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LocalKnowledgePoint:
    point = owned_knowledge_point_or_404(db, point_id, current_user.id)
    changes = payload.model_dump(exclude_unset=True)
    global_id = changes.get("global_knowledge_point_id")
    if (
        global_id is not None
        and global_id != point.global_knowledge_point_id
        and global_id not in owned_global_knowledge_point_ids(db, current_user.id)
    ):
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    point = owned_knowledge_point_or_404(db, point_id, current_user.id)
    from sqlalchemy import delete, update
    db.execute(delete(KnowledgePointMapping).where(KnowledgePointMapping.local_id == point.id))
    db.execute(update(Question).where(Question.knowledge_point_id == point.id).values(knowledge_point_id=None))
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TextbookStructure:
    textbook = db.scalar(
        select(Textbook)
        .where(Textbook.id == textbook_id, Textbook.owner_id == current_user.id)
        .options(selectinload(Textbook.chapters).selectinload(Chapter.knowledge_points))
    )
    if textbook is None:
        raise HTTPException(status_code=404, detail="教材不存在")
    from app.services.documents import current_document
    current = current_document(db, textbook)
    reader_chapters = None
    if current:
        active_ids = {chapter['id'] for chapter in current.content['chapters']}
        active_ids.update(db.scalars(select(DocumentChapter.chapter_id).where(DocumentChapter.source_id == current.source_id)))
        reader_chapters = _tree([chapter for chapter in textbook.chapters if chapter.id in active_ids])
    return TextbookStructure(textbook=textbook, chapters=_tree(textbook.chapters), reader_chapters=reader_chapters)


@router.post("/textbooks/{textbook_id}/publish", response_model=TextbookRead)
def publish_textbook(
    textbook_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Textbook:
    textbook = db.scalar(
        select(Textbook)
        .where(Textbook.id == textbook_id, Textbook.owner_id == current_user.id)
        .options(selectinload(Textbook.chapters).selectinload(Chapter.knowledge_points))
    )
    if textbook is None:
        raise HTTPException(status_code=404, detail="教材不存在")
    has_content = db.scalar(select(DocumentChunk.id).where(
        DocumentChunk.textbook_id == textbook.id,
    ).limit(1)) is not None
    if not has_content and not any(chapter.knowledge_points for chapter in textbook.chapters):
        raise HTTPException(status_code=422, detail="这本课本还没有内容，请先上传 PDF 或添加学习内容")
    if textbook.parse_status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="课本还在准备中，请稍等一会儿")
    textbook.parse_status = "ready"
    db.commit()
    db.refresh(textbook)
    return textbook


@router.post("/knowledge-points/relations", status_code=201)
def create_relation(
    source_id: int,
    target_id: int,
    relation_type: str = "prerequisite",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    if source_id == target_id:
        raise HTTPException(status_code=422, detail="知识点关系不能指向自身")
    owned_ids = owned_global_knowledge_point_ids(db, current_user.id)
    if source_id not in owned_ids or target_id not in owned_ids:
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
