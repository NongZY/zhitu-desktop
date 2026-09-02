from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from minio import Minio

from app.config import settings


def storage_enabled() -> bool:
    return bool(settings.minio_endpoint and settings.minio_access_key and settings.minio_secret_key)


def _client() -> Minio:
    if not storage_enabled():
        raise RuntimeError("MinIO 未配置")
    return Minio(
        settings.minio_endpoint or "",
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def put_pdf(local_path: Path, object_name: str) -> str:
    client = _client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
    client.fput_object(
        settings.minio_bucket,
        object_name,
        str(local_path),
        content_type="application/pdf",
    )
    return f"minio://{settings.minio_bucket}/{object_name}"


def materialize(uri: str) -> tuple[Path, bool]:
    """Return a local readable path and whether the caller must remove it."""
    if not uri.startswith("minio://"):
        return Path(uri), False
    bucket_and_name = uri.removeprefix("minio://")
    bucket, object_name = bucket_and_name.split("/", 1)
    with NamedTemporaryFile(suffix=".pdf", delete=False) as temporary:
        path = Path(temporary.name)
    _client().fget_object(bucket, object_name, str(path))
    return path, True
