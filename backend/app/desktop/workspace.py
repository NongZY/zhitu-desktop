"""Crash-recoverable local owner manifest. Never adopt an arbitrary old account."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import User


@dataclass(frozen=True)
class WorkspaceIdentity:
    workspace_id: str
    owner_id: int
    label: str = "本地学习空间"


def _atomic_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".workspace-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ensure_workspace(db: Session, manifest_path: Path) -> WorkspaceIdentity:
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            uid = manifest["id"]
            if (manifest["schemaVersion"] != 1 or str(UUID(uid)) != uid
                    or "ownerId" not in manifest):
                raise ValueError()
            owner_id = manifest["ownerId"]
            if owner_id is not None and (type(owner_id) is not int or owner_id < 1):
                raise ValueError()
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("本地空间清单损坏，请保留数据并从备份恢复") from exc
    else:
        if db.scalar(select(func.count()).select_from(User)):
            raise RuntimeError("此数据库已有学习记录，请通过后续数据迁移入口导入")
        uid, owner_id = str(uuid4()), None
        manifest = dict(schemaVersion=1, id=uid, ownerId=None)
        _atomic_manifest(manifest_path, manifest)

    marker = f"workspace-{uid}@local.invalid"
    user = db.scalar(select(User).where(User.email == marker))
    if owner_id is not None:
        if user is None or user.id != owner_id or not user.is_active:
            raise RuntimeError("本地空间与数据库不匹配，请保留原数据")
    else:
        if user is None:
            if db.scalar(select(func.count()).select_from(User)):
                raise RuntimeError("本地空间未完成且数据库已有其他账户，请保留原数据")
            # Not a hash of a usable password; desktop never mounts login endpoints.
            user = User(email=marker, name="本地学习空间", hashed_password="!desktop-only")
            db.add(user)
            db.commit()
        if not user.is_active:
            raise RuntimeError("本地空间不可用，请保留原数据")
        manifest["ownerId"] = user.id
        _atomic_manifest(manifest_path, manifest)
    return WorkspaceIdentity(uid, user.id)
