"""Freeze what a learner actually saw, never invent snapshots for old records."""
from copy import deepcopy
from types import SimpleNamespace


FIELDS = ('id', 'textbook_id', 'chapter_id', 'knowledge_point_id', 'question_type', 'stem',
          'options', 'correct_answer', 'explanation', 'difficulty', 'source', 'source_page')


def snapshot_question(question) -> dict:
    values = {field: deepcopy(getattr(question, field)) for field in FIELDS}
    point = question.knowledge_point
    values['knowledge_point'] = {'global_knowledge_point_id': point.global_knowledge_point_id,
                                'name': point.name} if point else None
    return values


def frozen_question(row):
    if not row.snapshot:
        return row.question
    values = deepcopy(row.snapshot)
    if values.get('knowledge_point'):
        values['knowledge_point'] = SimpleNamespace(**values['knowledge_point'])
    return SimpleNamespace(**values)
