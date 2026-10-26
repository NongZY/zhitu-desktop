import copy

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.access import owned_question_or_404, owned_textbook_or_404
from app.database import get_db
from app.models import PracticeJob, PracticeCandidate, Question, QuestionEvidence, User
from app.security import get_current_user
from app.services.practice_content import CandidateContent, JobCreate, evidence_units, fingerprint, supported_topics
from app.services.textbook_practice import (owned_job, job_read, create_job, process_job, cancel_job,
                                           confirm_candidates, is_current, candidate_read)

router = APIRouter(tags=['教材配套练习'])


def _connection(request, consent):
    from app.api.desktop_settings import desktop_root
    from app.services.ai_connection import connection_for
    if consent is not True:
        raise HTTPException(422, '请先确认要发送的教材范围，以及可能产生的费用')
    connection = connection_for(desktop_root(request))
    config = connection.public()
    if not config['practice_enabled'] or not config['key_configured']:
        raise HTTPException(422, '请先在设置中开启 AI 补题并填写接口')
    return connection


@router.get('/textbooks/{book_id}/practice/coverage')
def coverage(book_id: int, chapter_id: int | None = None,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    book = owned_textbook_or_404(db, book_id, user.id)
    try:
        rendition, units = evidence_units(db, book, chapter_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    chapters = []
    total = 0
    for unit in units:
        count = db.scalar(select(func.count()).select_from(Question).where(
            Question.textbook_id == book_id, Question.chapter_id == unit['chapter_id'], Question.status == 'approved')) or 0
        total += count
        topics = sorted({topic for e in unit['evidence'] for topic in supported_topics(e['text'])})
        chapters.append(dict(chapter_id=unit['chapter_id'], title=unit['title'], ready_questions=count,
            body_blocks=unit['body_blocks'], excerpts=unit['evidence'], supported_topics=topics,
            selected_blocks=len(unit['evidence']), missing_practice=count == 0))
    db.commit()
    return dict(textbook_id=book_id, title=book.title, rendition_revision=rendition.revision if rendition else None,
                ready_questions=total, chapters=chapters, estimated_requests=sum(bool(u['evidence']) for u in units),
                notice='每章使用下面列出的必要正文片段；有引用仍需核对题目与答案。')


@router.post('/textbooks/{book_id}/practice/jobs', status_code=202)
async def start_job(book_id: int, payload: JobCreate, request: Request, background: BackgroundTasks,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    book = owned_textbook_or_404(db, book_id, user.id)
    connection = _connection(request, payload.external_consent) if payload.mode == 'ai' else None
    try:
        job, created = create_job(db, book, user.id, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if created:
        background.add_task(process_job, job.id, connection)
    return job_read(db, job)


@router.get('/textbooks/{book_id}/practice/jobs')
def list_jobs(book_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_textbook_or_404(db, book_id, user.id)
    return [{'id': job.id, 'status': job.status, 'message': job.message, 'created_at': job.created_at}
            for job in db.scalars(select(PracticeJob).where(PracticeJob.textbook_id == book_id,
                PracticeJob.owner_id == user.id).order_by(PracticeJob.created_at.desc()).limit(30))]


@router.get('/practice/jobs/{job_id}')
def read_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return job_read(db, owned_job(db, job_id, user.id))


@router.post('/practice/jobs/{job_id}/cancel')
def stop_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = owned_job(db, job_id, user.id)
    cancel_job(db, job)
    return job_read(db, job)


class Retry(BaseModel):
    external_consent: bool = False


@router.post('/practice/jobs/{job_id}/retry', status_code=202)
async def retry_job(job_id: str, payload: Retry, request: Request, background: BackgroundTasks,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = owned_job(db, job_id, user.id)
    if job.status in {'queued', 'running', 'completed'}:
        return job_read(db, job)
    if not is_current(db, job):
        raise HTTPException(409, '教材或章节已更新，请重新发起')
    connection = _connection(request, payload.external_consent) if job.parameters['mode'] == 'ai' else None
    units = copy.deepcopy(job.units)
    for unit in units:
        if unit['status'] != 'completed':
            unit['status'], unit['message'] = 'queued', '等待重试'
    job.units, job.status, job.message = units, 'queued', '将重试未完成章节，已保存题目不会重复加入'
    db.commit()
    background.add_task(process_job, job.id, connection)
    return job_read(db, job)


@router.patch('/practice/candidates/{candidate_id}')
def edit_candidate(candidate_id: str, payload: CandidateContent,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(PracticeCandidate, candidate_id)
    if row is None:
        raise HTTPException(404, '候选不存在')
    job = owned_job(db, row.job_id, user.id)
    if row.saved_question_id:
        raise HTTPException(409, '这道题已保存，请从我的题库编辑')
    if not is_current(db, job):
        raise HTTPException(409, '教材已更新，请重新补题')
    # Fingerprint stored on the generation candidate remains its dedupe identity;
    # confirmation independently hashes the edited final contents.
    row.content = payload.model_dump()
    db.commit()
    return candidate_read(row)


class Confirm(BaseModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=500)


@router.post('/practice/jobs/{job_id}/confirm')
def confirm(job_id: str, payload: Confirm, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    return confirm_candidates(db, owned_job(db, job_id, user.id), payload.candidate_ids)


@router.get('/questions/{question_id}/evidence')
def evidence(question_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_question_or_404(db, question_id, user.id)
    row = db.get(QuestionEvidence, question_id)
    return {'evidence': row.evidence if row else [], 'provenance': row.provenance if row else None}
