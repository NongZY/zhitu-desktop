"""An owned collection uses the existing question FK and backup format."""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Textbook, User

BANK_STATUS = "standalone_question_bank"


def question_bank(db: Session, user_id: int) -> Textbook:
    # Serialize first use of a learner's bank across concurrent requests.
    db.execute(update(User).where(User.id == user_id).values(name=User.name))
    book = db.scalar(select(Textbook).where(
        Textbook.owner_id == user_id, Textbook.parse_status == BANK_STATUS,
    ))
    if book is None:
        book = Textbook(owner_id=user_id, title="独立题库", subject="练习", parse_status=BANK_STATUS)
        db.add(book)
        db.flush()
    return book
