from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401
from app.api.auth import router as auth_router
from app.api.exams import router as exams_router
from app.api.documents import router as documents_router
from app.api.imports import router as imports_router
from app.api.learning import router as learning_router
from app.api.questions import router as questions_router
from app.api.rag import router as rag_router
from app.api.reading import router as reading_router
from app.api.textbooks import router as textbooks_router
from app.config import settings
from app.database import Base, engine, SessionLocal
from app.desktop.profile import DesktopProfile
from app.services.schema_upgrades import READING_TABLE_NAMES, apply_schema_upgrades


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine, tables=[
        table for table in Base.metadata.sorted_tables if table.name not in READING_TABLE_NAMES
    ])
    apply_schema_upgrades(engine)
    if getattr(application.state, "desktop_profile", None) is not None:
        from app.desktop.workspace import ensure_workspace
        with SessionLocal() as db:
            application.state.workspace = ensure_workspace(
                db, application.state.desktop_profile.data_dir / "workspace.json"
            )
    if settings.local_mode:
        from app.services.import_dispatch import recover_interrupted_imports

        recover_interrupted_imports()
    try:
        yield
    finally:
        if settings.local_mode:
            from app.services.import_dispatch import shutdown_local_imports

            shutdown_local_imports(wait=getattr(application.state, "desktop_profile", None) is None)


def health() -> dict[str, str]:
    return {"status": "ok", "service": "adaptive-learning-api"}


def create_app(*, desktop_profile: DesktopProfile | None = None) -> FastAPI:
    application = FastAPI(
        title=settings.app_name, version="0.2.0-dev" if desktop_profile else "0.1.0",
        lifespan=lifespan, docs_url=None if desktop_profile else "/docs",
        redoc_url=None if desktop_profile else "/redoc",
        openapi_url=None if desktop_profile else "/openapi.json",
    )
    application.state.desktop_profile = desktop_profile
    if desktop_profile:
        from app.desktop.security import configure_desktop_security
        configure_desktop_security(application, desktop_profile)
    else:
        application.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
        application.include_router(auth_router, prefix=settings.api_prefix)
    for router in (textbooks_router, imports_router, questions_router, exams_router,
                   learning_router, reading_router, rag_router, documents_router):
        application.include_router(router, prefix=settings.api_prefix)
    application.get(f"{settings.api_prefix}/health", tags=["系统"])(health)
    application.get("/health", include_in_schema=False)(health)
    return application


app = create_app()
