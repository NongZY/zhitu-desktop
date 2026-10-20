import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.desktop.profile import current_profile


class Settings(BaseSettings):
    app_name: str = "智能自适应学习系统 API"
    api_prefix: str = "/api/v1"
    debug: bool = False
    local_mode: bool = False
    database_url: str = "sqlite:///./adaptive_learning.db"
    jwt_secret_key: str = "change-this-secret-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    upload_dir: str = "./uploads"
    max_upload_mb: int = 80

    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "memory://"
    celery_result_backend: str = "cache+memory://"
    celery_task_always_eager: bool = True

    llm_api_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = ""

    minio_endpoint: str | None = None
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_bucket: str = "textbooks"
    minio_secure: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        value = self.cors_origins.strip()
        if value.startswith("["):
            try:
                parsed = json.loads(value)
                return [str(item).strip() for item in parsed if str(item).strip()]
            except (json.JSONDecodeError, TypeError):
                pass
        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir).resolve()


class DesktopSettings(Settings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                   dotenv_settings, file_secret_settings):
        return (init_settings,)


@lru_cache
def get_settings() -> Settings:
    profile = current_profile()
    if profile is not None:
        profile.data_dir.mkdir(parents=True, exist_ok=True)
        return DesktopSettings(
            app_name="知途", local_mode=True, debug=False, api_prefix="/api/v1",
            database_url=f"sqlite:///{(profile.data_dir / 'learning.db').as_posix()}",
            upload_dir=str(profile.data_dir / "uploads"), cors_origins=profile.origin,
            redis_url="", celery_broker_url="memory://", celery_result_backend="cache+memory://",
            celery_task_always_eager=True, minio_endpoint=None, llm_api_url=None, llm_api_key=None,
        )
    return Settings()


settings = get_settings()
