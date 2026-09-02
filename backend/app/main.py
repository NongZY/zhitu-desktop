from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401
from app.api.auth import router as auth_router
from app.api.exams import router as exams_router
from app.api.imports import router as imports_router
from app.api.learning import router as learning_router
from app.api.questions import router as questions_router
from app.api.rag import router as rag_router
from app.api.textbooks import router as textbooks_router
from app.config import settings
from app.database import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="教材解析、RAG 问答、题库、考试与自适应学习 API",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(textbooks_router, prefix=settings.api_prefix)
app.include_router(imports_router, prefix=settings.api_prefix)
app.include_router(questions_router, prefix=settings.api_prefix)
app.include_router(exams_router, prefix=settings.api_prefix)
app.include_router(learning_router, prefix=settings.api_prefix)
app.include_router(rag_router, prefix=settings.api_prefix)


@app.get(f"{settings.api_prefix}/health", tags=["系统"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "adaptive-learning-api"}


@app.get("/health", include_in_schema=False)
def root_health() -> dict[str, str]:
    return health()
