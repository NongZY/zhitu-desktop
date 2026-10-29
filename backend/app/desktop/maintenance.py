"""Portable learning-space archives. Bootstrap helpers use only the standard library."""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import threading
import zipfile
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

MAX_ARCHIVE = 2 * 1024**3
MAX_EXPANDED = 4 * 1024**3
MAX_MEMBERS = 10000
LOCK = threading.RLock()
VERSIONS = frozenset({'20261015_reading_progress_v1', '20261023_structured_documents_v1',
    '20261025_document_activation_v1', '20261025_document_directory_v1', '20261026_textbook_practice_v1'})
PATH_COLUMNS = (('textbooks', 'file_path'), ('document_sources', 'managed_file'))


def identifier(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError):
        raise ValueError('备份编号不正确') from None


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        with temp.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path):
    if path.stat().st_size > 4 * 1024**2:
        raise ValueError('清单太大，无法读取')
    return json.loads(path.read_text(encoding='utf-8'))


def file_info(path):
    with path.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'sha256': digest, 'size': path.stat().st_size}


@contextmanager
def _db(path):
    connection = sqlite3.connect(path)
    try:
        connection.execute('PRAGMA trusted_schema=OFF')
        with connection:
            yield connection
    finally:
        connection.close()


def check_versions(path):
    if not path.exists():
        return
    with _db(path) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone():
            if not {r[0] for r in db.execute('SELECT version FROM schema_migrations')} <= VERSIONS:
                raise ValueError('这份资料来自更新的软件版本，请先更新软件')


def backup_before_upgrade(root, space):
    """Pre-upgrade DB snapshot; originals remain in place, unlike a portable user backup."""
    path = space / 'learning.db'
    if not path.exists() or not (space / 'workspace.json').is_file():
        return None
    check_versions(path)
    with _db(path) as db:
        versions = {r[0] for r in db.execute('SELECT version FROM schema_migrations')}
    if versions == VERSIONS:
        return None
    key = hashlib.sha256((str(space) + '|'.join(sorted(versions)) + '|'.join(sorted(VERSIONS))).encode()).hexdigest()[:24]
    folder = root / 'pre-upgrade' / key
    if (folder / 'snapshot.json').is_file():
        return folder
    folder.mkdir(parents=True, exist_ok=True)
    with _db(path) as source, _db(folder / 'learning.db') as dest:
        source.backup(dest)
    shutil.copyfile(space / 'workspace.json', folder / 'workspace.json')
    atomic_json(folder / 'snapshot.json', {'space': str(space), 'versions': sorted(versions),
        'notice': '升级前数据库副本；教材原文件仍在原学习空间。此目录不是可导入的完整备份。'})
    return folder


def validate_database(space):
    path = space / 'learning.db'
    check_versions(path)
    manifest = read_json(space / 'workspace.json')
    uid = identifier(manifest.get('id'))
    if manifest.get('schemaVersion') != 1 or type(manifest.get('ownerId')) is not int:
        raise ValueError('备份中的学习空间信息不完整')
    with _db(path) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger') OR upper(sql) LIKE '%CREATE VIRTUAL TABLE%'").fetchone():
            raise ValueError('备份包含不支持的数据库对象')
        if db.execute('PRAGMA quick_check').fetchone() != ('ok',) or db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('备份的学习记录不完整，请保留原资料')
        owner = db.execute('SELECT id FROM users WHERE email=? AND is_active=1', (f'workspace-{uid}@local.invalid',)).fetchone()
        if owner != (manifest['ownerId'],):
            raise ValueError('备份与学习空间不匹配')
        if db.execute('SELECT COUNT(*) FROM users').fetchone()[0] != 1:
            raise ValueError('此入口仅支持单人桌面学习空间')
        return {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                for table in ('textbooks', 'questions', 'exam_records')}


def _original(path, space):
    candidate = Path(path)
    resolved = candidate.resolve(strict=True)
    if not candidate.is_absolute() or not resolved.is_relative_to((space / 'uploads').resolve()) or not resolved.is_file():
        raise ValueError('部分教材原文件不在本地资料目录中，无法制作完整备份')
    if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in (candidate, *candidate.parents) if p != space.parent):
        raise ValueError('教材原文件不能使用链接目录')
    return resolved


def validate_source_files(db, files):
    """The archive manifest must also agree with the imported source identity."""
    for name, revision, size in db.execute('SELECT managed_file,source_revision,byte_size FROM document_sources'):
        if files.get(name) != {'sha256': revision, 'size': size}:
            raise ValueError('教材原文件与导入时的内容不一致，请保留原资料并重新导入正确文件')


def create_backup(root, space):
    with LOCK:
        root, space = root.resolve(), space.resolve()
        uid = str(uuid4())
        folder = root / 'backups'
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='backup-', dir=folder) as scratch:
            temp = Path(scratch)
            with _db(space / 'learning.db') as source, _db(temp / 'learning.db') as dest:
                source.backup(dest)
            shutil.copyfile(space / 'workspace.json', temp / 'workspace.json')
            counts = validate_database(temp)
            files = {}
            with _db(temp / 'learning.db') as db:
                for table, column in PATH_COLUMNS:
                    for (value,) in db.execute(f'SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL').fetchall():
                        path = _original(value, space)
                        suffix = path.suffix.lower()
                        if not re.fullmatch(r'\.[a-z0-9]{1,10}', suffix):
                            raise ValueError('教材文件格式不受支持')
                        # Identity includes the original path: equal-content different imports remain distinct.
                        name = 'uploads/' + hashlib.sha256(str(path).encode()).hexdigest() + suffix
                        if name not in files:
                            copied = temp / name
                            copied.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(path, copied)
                            files[name] = copied
                        db.execute(f'UPDATE {table} SET {column}=? WHERE {column}=?', (name, value))
                original_info = {name: file_info(path) for name, path in files.items()}
                validate_source_files(db, original_info)
            files.update({'learning.db': temp / 'learning.db', 'workspace.json': temp / 'workspace.json'})
            info = {name: file_info(path) for name, path in files.items()}
            if len(files) > MAX_MEMBERS - 1 or sum(v['size'] for v in info.values()) > MAX_EXPANDED:
                raise ValueError('资料超过当前备份容量上限（4 GB）')
            manifest = {'format': 'zhitu-learning-backup', 'version': 1, 'files': info, 'counts': counts}
            partial = folder / (uid + '.partial')
            try:
                with zipfile.ZipFile(partial, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
                    for name, path in files.items():
                        archive.write(path, name)
                if partial.stat().st_size > MAX_ARCHIVE:
                    raise ValueError('备份超过当前文件大小上限（2 GB）')
                os.replace(partial, folder / (uid + '.zip'))
            finally:
                partial.unlink(missing_ok=True)
        return {'id': uid, 'counts': counts, 'size': (folder / (uid + '.zip')).stat().st_size}


def _archive_name(name):
    return name in {'manifest.json', 'learning.db', 'workspace.json'} or bool(re.fullmatch(r'uploads/[a-f0-9]{64}\.[a-z0-9]{1,10}', name))


def stage_restore(root, archive_path):
    with LOCK:
        uid = str(uuid4())
        folder = root / 'restores' / uid
        folder.mkdir(parents=True)
        try:
            if archive_path.stat().st_size > MAX_ARCHIVE:
                raise ValueError('备份文件超过 2 GB')
            with zipfile.ZipFile(archive_path) as archive:
                members = archive.infolist()
                if len(members) > MAX_MEMBERS or sum(m.file_size for m in members) > MAX_EXPANDED:
                    raise ValueError('备份解压后超过容量限制')
                seen = set()
                for member in members:
                    name = member.filename
                    if (not _archive_name(name) or name.casefold() in seen or
                        stat.S_ISLNK(member.external_attr >> 16) or member.flag_bits & 1 or
                        member.file_size > (512 * 1024**2 if name == 'learning.db' else 80 * 1024**2)):
                        raise ValueError('备份包含不支持或重复的文件')
                    seen.add(name.casefold())
                if not {'manifest.json', 'learning.db', 'workspace.json'} <= seen:
                    raise ValueError('备份缺少必要文件')
                if archive.getinfo('manifest.json').file_size > 4 * 1024**2:
                    raise ValueError('备份清单太大')
                manifest = json.loads(archive.read('manifest.json'))
                if manifest.get('format') != 'zhitu-learning-backup' or manifest.get('version') != 1:
                    raise ValueError('请选择知途生成的备份文件')
                if set(manifest['files']) != seen - {'manifest.json'}:
                    raise ValueError('备份文件与清单不匹配')
                for member in members:
                    if member.filename == 'manifest.json':
                        continue
                    target = folder / member.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as src, target.open('wb') as dest:
                        shutil.copyfileobj(src, dest, length=1024 * 1024)
                    if file_info(target) != manifest['files'][member.filename]:
                        raise ValueError('备份文件已损坏，原资料没有改动')
            counts = validate_database(folder)
            with _db(folder / 'learning.db') as db:
                validate_source_files(db, manifest['files'])
                for table, column in PATH_COLUMNS:
                    for (value,) in db.execute(f'SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL').fetchall():
                        if not isinstance(value, str) or not value.startswith('uploads/') or value not in manifest['files']:
                            raise ValueError('备份中缺少教材原文件')
                        db.execute(f'UPDATE {table} SET {column}=? WHERE {column}=?', (str((folder / value).resolve()), value))
            files = {name: file_info(folder / name) for name in manifest['files']}
            atomic_json(folder / 'prepared.json', {'files': files, 'counts': counts})
            return {'id': uid, 'counts': counts, 'notice': '检查通过。确认后下次启动切换到此备份，当前资料会保留。'}
        except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, zipfile.BadZipFile, RuntimeError) as exc:
            # The generated directory is inside root/restores; never touch any supplied path.
            if folder.resolve().parent == (root / 'restores').resolve():
                shutil.rmtree(folder)
            message = str(exc) if type(exc) is ValueError else '备份无法读取，请选择知途生成的完整备份'
            raise ValueError(message) from None


def _space(root, value):
    if value == '.':
        return root
    if not isinstance(value, str) or not re.fullmatch(r'restores/[a-f0-9-]{36}', value):
        raise ValueError('学习空间位置无效，请保留资料')
    identifier(value.split('/')[1])
    path = (root / value).resolve(strict=True)
    if path.parent != (root / 'restores').resolve() or not (path / 'learning.db').is_file():
        raise ValueError('学习空间未找到，请保留资料')
    return path


def current_space(root):
    pointer = root / 'active-space.json'
    return _space(root, read_json(pointer)['active']) if pointer.exists() else root


def _verify_prepared(folder):
    prepared = read_json(folder / 'prepared.json')
    for name, expected in prepared['files'].items():
        if not _archive_name(name) or file_info(folder / name) != expected:
            raise ValueError('待恢复资料发生变化，请重新选择备份')
    validate_database(folder)


def confirm_restore(root, uid):
    with LOCK:
        folder = _space(root, 'restores/' + identifier(uid))
        if folder == current_space(root):
            raise ValueError('此学习空间已经在使用')
        _verify_prepared(folder)
        atomic_json(root / 'pending-space.json', {'target': 'restores/' + uid, 'verify': True})


def cancel_pending(root):
    with LOCK:
        (root / 'pending-space.json').unlink(missing_ok=True)


def schedule_rollback(root):
    with LOCK:
        pointer = read_json(root / 'active-space.json')
        target = pointer.get('previous')
        validate_database(_space(root, target))
        atomic_json(root / 'pending-space.json', {'target': target, 'verify': False})


def resolve_active_space(root):
    root = root.resolve()
    pending = root / 'pending-space.json'
    if pending.exists():
        try:
            data = read_json(pending)
            target = _space(root, data['target'])
            old = current_space(root)
            if target != old:  # activation succeeded before a crash removing the pending marker
                if data['verify']:
                    _verify_prepared(target)
                else:
                    validate_database(target)
                previous = old.relative_to(root).as_posix()
                atomic_json(root / 'active-space.json', {'active': data['target'], 'previous': previous})
            (root / 'restore-error.json').unlink(missing_ok=True)
        except (ValueError, KeyError, OSError, sqlite3.Error, TypeError):
            atomic_json(root / 'restore-error.json', {'message': '恢复资料检查未通过，已继续使用原学习空间。请重新选择完整备份。'})
        pending.unlink()
    active = current_space(root)
    check_versions(active / 'learning.db')
    return active


def status(root):
    pointer = root / 'active-space.json'
    return {'pending': (root / 'pending-space.json').exists(),
            'restore_error': read_json(root / 'restore-error.json')['message'] if (root / 'restore-error.json').exists() else '',
            'can_rollback': pointer.exists() and bool(read_json(pointer).get('previous'))}
