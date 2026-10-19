from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import ReadingHome, ReadingProgressRead, ReadingProgressResult, ReadingProgressWrite
from app.security import get_current_user
from app.services.reading_progress import (
    ReadingProgressError, get_progress, get_reading_home, save_progress,
)


class PrivateReadingRoute(APIRoute):
    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def handler(request: Request):
            try:
                response = await original_handler(request)
            except ReadingProgressError as exc:
                response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            except HTTPException as exc:
                response = await http_exception_handler(request, exc)
            except RequestValidationError as exc:
                response = await request_validation_exception_handler(request, exc)
            response.headers["Cache-Control"] = "private, no-store"
            return response

        return handler


router = APIRouter(prefix="/learning", tags=["阅读位置"], route_class=PrivateReadingRoute)


@router.get("/home", response_model=ReadingHome)
def reading_home(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_reading_home(db, current_user.id)


@router.get("/reading-progress/{textbook_id}", response_model=ReadingProgressResult)
def reading_progress(
    textbook_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return ReadingProgressResult(progress=get_progress(db, current_user.id, textbook_id))


@router.put("/reading-progress/{textbook_id}", response_model=ReadingProgressRead)
def update_reading_progress(
    textbook_id: int, payload: ReadingProgressWrite,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return save_progress(db, current_user.id, textbook_id, payload)
