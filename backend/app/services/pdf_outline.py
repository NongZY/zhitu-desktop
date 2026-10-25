"""Conservative, local PDF outline extraction; no model-generated chapter names."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chapter, DocumentChunk

ROOT = re.compile(r"^(第[一二三四五六七八九十百零〇\d]+章)\s*(\S.{0,70})$")
SECTION = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){1,3})\s*([\u4e00-\u9fff].{0,100})$")


def normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text.replace("\x00", "�")).strip()


@dataclass
class OutlineEntry:
    title: str
    level: int
    page_start: int
    page_end: int = 0


def extract_outline(document, page_texts: list[str]) -> list[OutlineEntry]:
    """Prefer PDF bookmarks, otherwise match printed TOC entries to body headings.

    Printed page numbers are deliberately not treated as PDF page indices. Only
    body matches determine destinations. Fine numbered headings need a known parent.
    """
    bookmarks = document.get_toc()
    entries: list[OutlineEntry] = []
    for level, title, page in bookmarks:
        if not 1 <= page <= len(page_texts) or not normalized(title):
            continue
        if entries and page < entries[-1].page_start:
            continue
        # Normalize missing/skipped bookmark levels to a valid tree.
        depth = min(level, entries[-1].level + 1) if entries else 1
        entries.append(OutlineEntry(normalized(title)[:200], max(1, depth), page))
    if not entries:
        lines = [[normalized(line) for line in text.splitlines() if line.strip()]
                 for text in page_texts]
        toc_pages: set[int] = set()
        titles: dict[str, str] = {}
        for index, page_lines in enumerate(lines[:30]):
            # TOC continuation pages contain several chapter/section titles and
            # many standalone page numbers. Avoid classifying body lessons as TOC.
            numbers = sum(bool(re.fullmatch(r"\d{1,4}", line)) for line in page_lines)
            sections = sum(bool(SECTION.match(line)) for line in page_lines)
            if any(re.sub(r"\s", "", line) == "目录" for line in page_lines) or (
                toc_pages and index - 1 in toc_pages and sections >= 3 and numbers >= 5
            ):
                toc_pages.add(index)
                for j, line in enumerate(page_lines):
                    match = SECTION.match(line)
                    if match:
                        number, title = match.groups()
                        title = re.sub(r"[.·…\s]*\d+$", "", title).strip()
                        if j + 1 < len(page_lines) and page_lines[j + 1].startswith(("—", "-")):
                            title += " " + page_lines[j + 1]
                        titles[number] = title
        last_toc = max(toc_pages, default=-1)
        seen: set[str] = set()
        active_numbers: dict[int, str] = {}
        for index, page_lines in enumerate(lines):
            if index <= last_toc:
                continue
            for line_index, line in enumerate(page_lines):
                root = ROOT.match(line)
                if root and line_index < 5 and root[1] not in seen:
                    seen.add(root[1])
                    entries.append(OutlineEntry(f"{root[1]} {root[2]}", 1, index + 1))
                    active_numbers.clear()
                    continue
                match = SECTION.match(line)
                if not match or not entries:
                    continue
                number, title = match.groups()
                depth = number.count(".") + 1
                if number in seen:
                    continue
                if depth == 2:
                    # Without a printed TOC, refuse to mistake decimal exercises
                    # for sections; PDF bookmarks remain supported independently.
                    expected = titles.get(number)
                    if not expected or not re.sub(r"\s", "", expected).startswith(
                        re.sub(r"\s", "", title)
                    ):
                        continue
                    title = expected
                elif active_numbers.get(depth - 1) != number.rsplit(".", 1)[0]:
                    continue
                if len(title) > 100 or re.search(r"[=<>?？。]", title):
                    continue
                seen.add(number)
                active_numbers = {k: v for k, v in active_numbers.items() if k < depth}
                active_numbers[depth] = number
                entries.append(OutlineEntry(f"{number} {title}", depth, index + 1))
    for index, entry in enumerate(entries):
        following = next((other.page_start for other in entries[index + 1:]
                          if other.level <= entry.level), len(page_texts) + 1)
        entry.page_end = max(entry.page_start, following - 1)
    return entries


def apply_outline(db: Session, textbook_id: int, entries: list[OutlineEntry],
                  chunks: list[DocumentChunk], *, chapter_ids: set[int] | None = None) -> int:
    """Create only an empty outline. Never replace learners' edited structures.

    Runs inside caller's transaction; retries preserve chapter IDs and references.
    """
    chapters = list(db.scalars(select(Chapter).where(Chapter.textbook_id == textbook_id)))
    if chapter_ids is not None:
        chapters = [c for c in chapters if c.id in chapter_ids]
    added = 0
    if not chapters:
        parents: dict[int, Chapter] = {}
        for index, entry in enumerate(entries):
            parent = parents.get(entry.level - 1)
            chapter = Chapter(
                textbook_id=textbook_id, parent_id=parent.id if parent else None,
                title=entry.title, order_index=index,
                page_start=entry.page_start, page_end=entry.page_end,
                summary="从 PDF 目录或正文标题自动识别；页码为 PDF 文件页码，请对照原文核对。",
            )
            db.add(chapter)
            db.flush()
            parents = {k: v for k, v in parents.items() if k < entry.level}
            parents[entry.level] = chapter
            chapters.append(chapter)
            added += 1
    if chapter_ids is not None:
        chapter_ids.update(c.id for c in chapters)
    # Narrowest matching range gives each text chunk its most specific chapter.
    for chunk in chunks:
        candidates = [c for c in chapters if c.page_start and c.page_end
                      and c.page_start <= (chunk.page_number or 0) <= c.page_end]
        if candidates:
            chunk.chapter_id = min(candidates, key=lambda c: (
                c.page_end - c.page_start, -c.order_index,
            )).id
    return added


def chapter_scope_ids(db: Session, chapter: Chapter) -> list[int]:
    rows = db.execute(select(Chapter.id, Chapter.parent_id).where(
        Chapter.textbook_id == chapter.textbook_id,
    )).all()
    ids = {chapter.id}
    while True:
        descendants = {row.id for row in rows if row.parent_id in ids} - ids
        if not descendants:
            return sorted(ids)
        ids.update(descendants)
