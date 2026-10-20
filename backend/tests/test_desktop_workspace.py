import json
from uuid import uuid4

import pytest
from app.database import Base
from app.models import User
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


@pytest.fixture
def space(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'learning.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db, tmp_path / "workspace.json"
    engine.dispose()


def test_workspace_is_stable_across_sessions(space):
    from app.desktop.workspace import ensure_workspace

    db, manifest = space
    a = ensure_workspace(db, manifest)
    db.close()
    b = ensure_workspace(db, manifest)
    assert a == b
    assert a.label == "本地学习空间"
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_workspace_uses_manifest_owner_not_first_user(space):
    from app.desktop.workspace import ensure_workspace

    db, manifest = space
    uid = str(uuid4())
    db.add_all(
        [
            User(id=1, email="other@example.com", name="other", hashed_password="x"),
            User(id=17, email=f"workspace-{uid}@local.invalid", name="local", hashed_password="!"),
        ]
    )
    db.commit()
    manifest.write_text(json.dumps(dict(schemaVersion=1, id=uid, ownerId=17)), encoding="utf-8")
    assert ensure_workspace(db, manifest).owner_id == 17


@pytest.mark.parametrize(
    "contents",
    [
        None,
        "broken",
        '{"schemaVersion":99}',
        json.dumps(dict(schemaVersion=1, id=str(uuid4()), ownerId=1)),
    ],
)
def test_old_or_corrupt_space_is_not_adopted(space, contents):
    from app.desktop.workspace import ensure_workspace

    db, manifest = space
    db.add(User(email="old@example.com", name="old", hashed_password="x"))
    db.commit()
    if contents is not None:
        manifest.write_text(contents, encoding="utf-8")
    with pytest.raises(RuntimeError):
        ensure_workspace(db, manifest)
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert db.get(User, 1).email == "old@example.com"


def test_pending_manifest_resumes_without_duplicate_owner(space):
    from app.desktop.workspace import ensure_workspace

    db, manifest = space
    uid = str(uuid4())
    manifest.write_text(json.dumps(dict(schemaVersion=1, id=uid, ownerId=None)), encoding="utf-8")
    db.add(User(id=17, email=f"workspace-{uid}@local.invalid", name="local", hashed_password="!"))
    db.commit()
    assert ensure_workspace(db, manifest).owner_id == 17
    assert db.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.parametrize("error", [PermissionError("read only"), OSError(28, "disk full")])
def test_failed_manifest_write_preserves_database(space, monkeypatch, error):
    from app.desktop import workspace

    db, manifest = space

    def fail(*args):
        raise error

    monkeypatch.setattr(workspace.os, "replace", fail)
    with pytest.raises((RuntimeError, OSError)):
        workspace.ensure_workspace(db, manifest)
    assert db.scalar(select(func.count()).select_from(User)) == 0
    assert not manifest.exists()


def test_separate_spaces_have_independent_identity(tmp_path):
    from app.desktop.workspace import ensure_workspace

    identities = []
    for name in ("a", "b"):
        folder = tmp_path / name
        folder.mkdir()
        engine = create_engine(f"sqlite:///{(folder / 'learning.db').as_posix()}")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            identities.append(ensure_workspace(db, folder / "workspace.json"))
        engine.dispose()
    assert identities[0].workspace_id != identities[1].workspace_id
