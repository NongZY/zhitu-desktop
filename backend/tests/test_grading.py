from app.models import Question
from app.services.adaptive import grade_objective


def _question(options, answer, question_type="single_choice"):
    return Question(
        textbook_id=1,
        question_type=question_type,
        stem="demo",
        options=options,
        correct_answer=answer,
        difficulty=2,
        status="approved",
        source="test",
        created_by=1,
    )


def test_choice_accepts_key_when_answer_is_stored_as_option_text():
    question = _question(["-2", "2", "5", "-5"], "-2")
    assert grade_objective(question, "A") is True


def test_choice_accepts_text_when_answer_is_stored_as_key():
    question = _question([{"key": "A", "text": "Paris"}, {"key": "B", "text": "Rome"}], "A")
    assert grade_objective(question, "Paris") is True


def test_multiple_choice_normalizes_order():
    question = _question({"A": "甲", "B": "乙", "C": "丙"}, ["A", "C"], "multiple_choice")
    assert grade_objective(question, ["丙", "甲"]) is True
