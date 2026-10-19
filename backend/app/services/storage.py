from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

from minio import Minio
from minio.error import S3Error

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
    try:
        _client().fget_object(bucket, object_name, str(path))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path, True


def source_signature(uri: str) -> tuple:
    """Cache invalidation only; remote ETags are not content fingerprints."""
    if not uri.startswith('minio://'):
        path = Path(uri).resolve()
        stat = path.stat()
        return (str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    bucket, name = uri.removeprefix('minio://').split('/', 1)
    try:
        stat = _client().stat_object(bucket, name)
    except S3Error as exc:
        if exc.code in {'NoSuchKey', 'NoSuchObject', 'NoSuchBucket'}:
            raise FileNotFoundError(uri) from exc
        raise
    return (uri, stat.version_id, stat.etag, stat.size, stat.last_modified)
