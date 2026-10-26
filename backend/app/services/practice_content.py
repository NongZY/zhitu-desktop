"""Textbook evidence selection and typed candidate validation; no I/O to models."""
import hashlib
import json
import random
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.models import Chapter, DocumentChunk, Question
from app.schemas import QuestionType
from app.services.basic_practice import typed_problem
from app.services.documents import document_data, enroll_legacy_pdf, locator_for
from app.services.pdf_outline import chapter_scope_ids


class JobCreate(BaseModel):
    request_id: str = Field(min_length=8, max_length=80)
    chapter_id: int | None = None
    mode: Literal['rules', 'ai', 'extract'] = 'rules'
    count: int = Field(default=5, ge=1, le=20)
    question_types: list[QuestionType] = Field(min_length=1, max_length=5)
    external_consent: bool = False


class CandidateContent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question_type: QuestionType
    stem: str = Field(min_length=1, max_length=3000)
    options: list[dict[str, str]] | None = None
    correct_answer: Any
    explanation: str = Field(default='', max_length=8000)
    difficulty: int = Field(default=2, ge=1, le=5)

    @model_validator(mode='after')
    def valid_answer(self):
        if not self.stem.strip() or '\ufffd' in self.stem + self.explanation:
            raise ValueError('题目包含空白或待核对符号')
        answer = self.correct_answer
        if self.question_type in {'single_choice', 'multiple_choice'}:
            if not self.options or not 2 <= len(self.options) <= 8:
                raise ValueError('选择题需要 2 到 8 个选项')
            keys = [o.get('key') for o in self.options]
            if (len(set(keys)) != len(keys) or any(not key or len(key) > 8 for key in keys)
                    or any(not o.get('text', '').strip() or len(o['text']) > 2000 for o in self.options)):
                raise ValueError('选项内容或编号不正确')
            if self.question_type == 'single_choice':
                if not isinstance(answer, str) or answer not in keys:
                    raise ValueError('单选答案必须对应一个选项')
            elif (not isinstance(answer, list) or not answer or not all(isinstance(v, str) for v in answer)
                  or len(set(answer)) != len(answer) or not set(answer).issubset(keys)):
                raise ValueError('多选答案必须对应所选编号')
        elif self.question_type == 'true_false':
            if type(answer) is not bool:
                raise ValueError('判断题答案必须是对或错')
            self.options = None
        else:
            if not ((isinstance(answer, str) and answer.strip()) or
                    (isinstance(answer, list) and 1 <= len(answer) <= 20 and
                     all(isinstance(v, str) and v.strip() for v in answer))):
                raise ValueError('请填写标准答案或参考要点')
            if len(json.dumps(answer)) > 16000:
                raise ValueError('答案过长')
            self.options = None
        return self


def fingerprint(content: dict) -> str:
    normalized = {k: content[k] for k in ('question_type', 'stem', 'correct_answer', 'options')}
    normalized['stem'] = re.sub(r'\s+', '', normalized['stem'])
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def supported_topics(text: str) -> list[str]:
    compact = re.sub(r'\s+', '', text)
    matches = []
    if all(word in compact for word in ('绝对值', '原点', '距离')):
        matches.append('绝对值')
    if '相反数' in compact and ('只有符号不同' in compact or re.search(r'和为[零0]', compact)):
        matches.append('相反数')
    if all(word in compact for word in ('正数', '负数', '大于0', '小于0')):
        matches.append('正数和负数')
    # Signed-number templates must not silently appear in elementary positive-only material.
    if '有理数' in compact:
        matches.extend(topic for topic in ('加法', '减法', '乘法', '除法') if topic in compact and '法则' in compact)
        if '乘方' in compact and ('相乘' in compact or '乘积' in compact):
            matches.append('乘方')
    if '一元一次方程' in compact and '等式' in compact:
        matches.append('一元一次方程')
    if '同类项' in compact and '系数' in compact and ('相加' in compact or '相加减' in compact):
        matches.append('整式')
    if '余角' in compact and ('90°' in compact or '90度' in compact):
        matches.append('余角和补角')
    return matches


def evidence_units(db, book, chapter_id=None):
    rendition = enroll_legacy_pdf(db, book)
    if rendition is None:
        return None, []
    data = document_data(db, rendition)
    selected_ids = None
    if chapter_id is not None:
        chapter = db.get(Chapter, chapter_id)
        if chapter is None or chapter.textbook_id != book.id:
            raise ValueError('所选章节不属于这本教材')
        selected_ids = chapter_scope_ids(db, chapter)
    unsafe = set()
    for chunk in db.scalars(select(DocumentChunk).where(DocumentChunk.textbook_id == book.id)):
        metadata = chunk.metadata_json or {}
        if metadata.get('math_review_required'):
            locator = metadata.get('locator') or {}
            unsafe.add((locator.get('kind', 'page'), str(locator.get('unit_id', chunk.page_number))))
    titles = {c.id: c.title for c in db.scalars(select(Chapter).where(Chapter.textbook_id == book.id))}
    grouped = {}
    for block in data['blocks']:
        chapter = block.get('chapter_id')
        if selected_ids is not None and chapter not in selected_ids:
            continue
        if block['kind'] in {'heading', 'image', 'unsupported'} or not block.get('text', '').strip():
            continue
        locator = locator_for(data, block)
        if '\ufffd' in block['text'] or (locator['kind'], locator['unit_id']) in unsafe:
            continue
        unit = grouped.setdefault(chapter, dict(chapter_id=chapter, title=titles.get(chapter, '正文'),
                                               evidence=[], body_blocks=0, status='queued', message=''))
        unit['body_blocks'] += 1
        used = sum(len(e['text']) for e in unit['evidence'])
        if used < 6000 and len(unit['evidence']) < 12:
            unit['evidence'].append(dict(id=f'e{len(unit["evidence"]) + 1}',
                text=block['text'][:min(2000, 6000 - used)], locator=locator))
    # Empty titles are still a failed, explainable task rather than guessing a concept.
    if not grouped:
        grouped[chapter_id] = dict(chapter_id=chapter_id, title=titles.get(chapter_id, '所选内容'),
                                  evidence=[], body_blocks=0, status='queued', message='')
    return rendition, list(grouped.values())


def rule_candidates(unit, count, kinds, seed):
    rng = random.Random(seed)
    evidence = unit['evidence']
    pairs = [(entry, topic) for entry in evidence for topic in supported_topics(entry['text'])]
    rows = []
    for i in range(count):
        if not pairs:
            break
        entry, topic = pairs[i % len(pairs)]
        kind = kinds[i % len(kinds)]
        stem, options, answer, explanation = typed_problem(topic, kind, rng)
        rows.append((CandidateContent(question_type=kind, stem=stem, options=options,
                     correct_answer=answer, explanation=explanation).model_dump(), [entry]))
    return rows


def original_candidates(unit, count, kinds):
    if 'short_answer' not in kinds:
        return []
    text = '\n'.join(e['text'] for e in unit['evidence'])
    rows = []
    for match in re.finditer(r'题目[：:]([^\n]+)\n答案[：:]([^\n]+)(?:\n解析[：:]([^\n]+))?', text):
        rows.append((CandidateContent(question_type='short_answer', stem=match[1],
                     correct_answer=match[2], explanation=match[3] or '原文已给出参考答案，请核对来源。').model_dump(), unit['evidence']))
        if len(rows) == count:
            break
    return rows


def parse_model_candidates(text, unit, count, kinds):
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
    payload = json.loads(text)
    rows, rejected = [], 0
    evidence = {item['id']: item for item in unit['evidence']}
    if not isinstance(payload, dict) or not isinstance(payload.get('questions'), list):
        raise ValueError('接口未返回题目列表')
    for item in payload['questions'][:count]:
        try:
            item = dict(item)
            references = item.pop('evidence_ids')
            if not isinstance(references, list) or not references or not all(isinstance(k, str) and k in evidence for k in references):
                raise ValueError()
            content = CandidateContent.model_validate(item).model_dump()
            if content['question_type'] not in kinds:
                raise ValueError()
            rows.append((content, [evidence[key] for key in dict.fromkeys(references)]))
        except (ValueError, KeyError, TypeError):
            rejected += 1
    return rows, rejected
