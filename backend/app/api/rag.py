from __future__ import annotations

import re
from collections import Counter

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Chapter, DocumentChunk, Textbook, User
from app.schemas import RagAnswer, RagAskRequest, RagCitation
from app.security import get_current_user, require_staff

router = APIRouter(prefix="/rag", tags=["RAG 教材问答"])


def _features(text: str) -> Counter[str]:
    lowered = text.lower()
    compact = re.sub(r"\s+", "", lowered)
    chinese = [char for char in compact if "\u4e00" <= char <= "\u9fff"]
    features = Counter(re.findall(r"[a-z0-9_.+-]+", lowered))
    features.update(chinese)
    features.update("".join(chinese[index : index + 2]) for index in range(len(chinese) - 1))
    return features


def _score(question: str, content: str) -> float:
    query = _features(question)
    document = _features(content)
    if not query or not document:
        return 0.0
    overlap = sum(min(count, document.get(token, 0)) for token, count in query.items())
    return round(overlap / max(1, sum(query.values())), 4)


def _llm_answer(question: str, citations: list[RagCitation]) -> str | None:
    if not settings.llm_api_url or not settings.llm_api_key or not settings.llm_model:
        return None
    context = "\n\n".join(f"[资料{i + 1}] {item.excerpt}" for i, item in enumerate(citations))
    prompt = (
        "你是教材助教。只能依据资料回答；资料不足时明确说无法从教材确认。"
        "不要编造页码或事实，并在结论后使用[资料1]形式标注依据。\n\n"
        f"问题：{question}\n\n{context}"
    )
    try:
        response = httpx.post(
            settings.llm_api_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"]).strip()
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return None


@router.post("/ask", response_model=RagAnswer)
def ask(
    payload: RagAskRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RagAnswer:
    stmt = select(DocumentChunk)
    if payload.textbook_id is not None:
        stmt = stmt.where(DocumentChunk.textbook_id == payload.textbook_id)
    if payload.chapter_id is not None:
        stmt = stmt.where(DocumentChunk.chapter_id == payload.chapter_id)
    chunks = db.scalars(stmt.order_by(DocumentChunk.id).limit(1000)).all()
    ranked = sorted(
        ((chunk, _score(payload.question, chunk.content)) for chunk in chunks),
        key=lambda item: item[1],
        reverse=True,
    )
    selected = [(chunk, score) for chunk, score in ranked[: payload.top_k] if score > 0]
    citations: list[RagCitation] = []
    for chunk, score in selected:
        textbook = db.get(Textbook, chunk.textbook_id)
        chapter = db.get(Chapter, chunk.chapter_id) if chunk.chapter_id else None
        citations.append(
            RagCitation(
                chunk_id=chunk.id,
                textbook_id=chunk.textbook_id,
                textbook_title=textbook.title if textbook else "未知教材",
                chapter_id=chunk.chapter_id,
                chapter_title=chapter.title if chapter else None,
                page_number=chunk.page_number,
                excerpt=chunk.content[:500],
                score=score,
            )
        )
    if not citations:
        return RagAnswer(
            answer="当前教材知识库中没有找到足以回答该问题的内容。请换一种问法，或确认教材已完成解析。",
            citations=[],
            grounded=False,
            model="retrieval-only",
        )
    generated = _llm_answer(payload.question, citations)
    if generated:
        return RagAnswer(
            answer=generated,
            citations=citations,
            grounded=True,
            model=settings.llm_model,
        )
    excerpts = "\n\n".join(
        f"资料 {index + 1}：{citation.excerpt}" for index, citation in enumerate(citations[:3])
    )
    return RagAnswer(
        answer=("已检索到以下教材原文。当前未配置大模型，因此保留原文供你核对：\n\n" + excerpts),
        citations=citations,
        grounded=True,
        model="retrieval-only",
    )


@router.post("/chunks", status_code=201)
def create_chunk(
    textbook_id: int,
    content: str,
    chapter_id: int | None = None,
    page_number: int | None = None,
    _: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if not content.strip():
        raise HTTPException(status_code=422, detail="片段内容不能为空")
    if db.get(Textbook, textbook_id) is None:
        raise HTTPException(status_code=404, detail="教材不存在")
    if chapter_id is not None:
        chapter = db.get(Chapter, chapter_id)
        if chapter is None or chapter.textbook_id != textbook_id:
            raise HTTPException(status_code=422, detail="章节不属于所选教材")
    next_index = len(
        db.scalars(select(DocumentChunk).where(DocumentChunk.textbook_id == textbook_id)).all()
    )
    chunk = DocumentChunk(
        textbook_id=textbook_id,
        chapter_id=chapter_id,
        content=content.strip(),
        page_number=page_number,
        chunk_index=next_index,
    )
    db.add(chunk)
    db.commit()
    db.refresh(chunk)
    return {"id": chunk.id, "content": chunk.content, "chunk_index": chunk.chunk_index}
