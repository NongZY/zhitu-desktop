import hashlib
import json
import sqlite3
import zipfile
from uuid import uuid4

import pytest

from desktop_helpers import RunningDesktop


@pytest.fixture
def space(tmp_path):
    root = tmp_path / 'space'
    service = RunningDesktop(root)
    try:
        book = service.request('POST', '/api/v1/textbooks', json={'title': '备份教材', 'subject': '数学'}).json()['id']
    finally:
        service.close()
    original = root / 'uploads' / 'one.txt'
    original.write_text('绝对值表示数轴上一个数对应的点到原点的距离。', encoding='utf-8')
    with sqlite3.connect(root / 'learning.db') as db:
        db.execute('UPDATE textbooks SET file_path=? WHERE id=?', (str(original), book))
        other = original.with_name('same-content-old-import.txt')
        other.write_bytes(original.read_bytes())
        for path in (original, other):
            db.execute('INSERT INTO document_sources(id,textbook_id,format,original_name,managed_file,byte_size,source_revision,created_at) VALUES (?,?,?,?,?,?,?,CURRENT_TIMESTAMP)',
                       (str(uuid4()), book, 'txt', path.name, str(path), path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()))
    db.close()
    (root / 'settings').mkdir(exist_ok=True)
    (root / 'settings' / 'ai.json').write_text('SYNTHETIC-SECRET')
    return root, book, original


def test_wal_round_trip_excludes_keys_rebases_original_and_preserves_previous(space):
    from app.desktop.maintenance import create_backup, stage_restore, confirm_restore, resolve_active_space, schedule_rollback
    root, book, original = space
    wal = sqlite3.connect(root / 'learning.db')
    try:
        wal.execute('PRAGMA journal_mode=WAL')
        wal.execute('UPDATE textbooks SET title=? WHERE id=?', ('WAL 中的新标题', book))
        wal.commit()
        backup = create_backup(root, root)
        archive = root / 'backups' / (backup['id'] + '.zip')
        with zipfile.ZipFile(archive) as z:
            assert 'settings/ai.json' not in z.namelist()
            assert all('SYNTHETIC-SECRET' not in z.read(n).decode('utf-8', errors='ignore') for n in z.namelist())
        staged = stage_restore(root, archive)
        assert staged['counts']['textbooks'] == 1
        assert resolve_active_space(root) == root
        confirm_restore(root, staged['id'])
        active = resolve_active_space(root)
        assert active != root and original.exists()
        with sqlite3.connect(active / 'learning.db') as restored:
            title, path = restored.execute('SELECT title,file_path FROM textbooks WHERE id=?', (book,)).fetchone()
            assert title == 'WAL 中的新标题'
            from pathlib import Path
            assert Path(path).is_relative_to(active / 'uploads')
            assert Path(path).read_bytes() == original.read_bytes()
            sources = [r[0] for r in restored.execute('SELECT managed_file FROM document_sources')]
            assert len(set(sources)) == 2 and path in sources
            assert all(Path(p).is_relative_to(active / 'uploads') and Path(p).read_bytes() == original.read_bytes() for p in sources)
            restored.execute('UPDATE textbooks SET title=? WHERE id=?', ('恢复后的修改', book))
        assert resolve_active_space(root) == active  # no obsolete hash check after legitimate writes
        schedule_rollback(root)
        assert resolve_active_space(root) == root
    finally:
        wal.close()


@pytest.mark.parametrize('attack', ['traversal', 'duplicate', 'tampered', 'oversize', 'future_schema', 'owner', 'trigger'])
def test_invalid_archive_never_changes_live_space(space, attack, monkeypatch):
    from app.desktop import maintenance as m
    root, _, original = space
    backup = m.create_backup(root, root)
    source = root / 'backups' / (backup['id'] + '.zip')
    with zipfile.ZipFile(source) as z:
        items = {n: z.read(n) for n in z.namelist()}
    manifest = json.loads(items['manifest.json'])
    if attack == 'traversal':
        items['../escape.txt'] = b'bad'
    elif attack == 'tampered':
        items['workspace.json'] += b' '
    elif attack == 'oversize':
        monkeypatch.setattr(m, 'MAX_EXPANDED', 100)
    elif attack in {'future_schema', 'owner', 'trigger'}:
        dbfile = root / 'attack.db'
        dbfile.write_bytes(items['learning.db'])
        with sqlite3.connect(dbfile) as db:
            if attack == 'future_schema':
                db.execute("INSERT INTO schema_migrations(version,applied_at) VALUES ('20990101_future', CURRENT_TIMESTAMP)")
            elif attack == 'owner':
                db.execute("UPDATE users SET email='different@example.com'")
            else:
                db.execute('CREATE TRIGGER evil AFTER UPDATE ON textbooks BEGIN DELETE FROM users; END')
        db.close()  # checkpoint the edited WAL before putting the database bytes in the archive
        items['learning.db'] = dbfile.read_bytes()
        manifest['files']['learning.db'] = {'size': len(items['learning.db']), 'sha256': hashlib.sha256(items['learning.db']).hexdigest()}
        items['manifest.json'] = json.dumps(manifest).encode()
    bad = root / 'bad.zip'
    with zipfile.ZipFile(bad, 'w') as z:
        for name, value in items.items():
            z.writestr(name, value)
        if attack == 'duplicate':
            z.writestr('WORKSPACE.JSON', items['workspace.json'])
    with pytest.raises(ValueError):
        m.stage_restore(root, bad)
    assert m.resolve_active_space(root) == root and original.exists()
    assert not (root.parent / 'escape.txt').exists()


def test_desktop_routes_confirm_cancel_restart_and_token_boundary(tmp_path):
    service = RunningDesktop(tmp_path)
    try:
        assert service.request('POST', '/api/v1/maintenance/backups', authenticated=False).status_code == 403
        service.request('POST', '/api/v1/textbooks', json={'title': '原教材', 'subject': '数学'})
        backup = service.request('POST', '/api/v1/maintenance/backups')
        assert backup.status_code == 201, backup.text
        body = service.get('/api/v1/maintenance/backups/' + backup.json()['id']).content
        service.request('POST', '/api/v1/textbooks', json={'title': '后来新增', 'subject': '数学'})
        staged = service.request('POST', '/api/v1/maintenance/restores', files={'file': ('backup.zip', body, 'application/zip')})
        assert staged.status_code == 201, staged.text
        restore_id = staged.json()['id']
        assert service.request('POST', f'/api/v1/maintenance/restores/{restore_id}/confirm').status_code == 200
        assert service.request('POST', '/api/v1/textbooks', json={'title': '不允许改动', 'subject': '数学'}).status_code == 409
        assert service.request('DELETE', '/api/v1/maintenance/pending').status_code == 204
        assert service.request('POST', f'/api/v1/maintenance/restores/{restore_id}/confirm').status_code == 200
    finally:
        service.close()
    service = RunningDesktop(tmp_path)
    try:
        books = service.get('/api/v1/textbooks').json()['items']
        assert [b['title'] for b in books] == ['原教材']
        assert service.get('/api/v1/maintenance/status').json()['can_rollback']
        assert service.request('POST', '/api/v1/maintenance/rollback').status_code == 200
    finally:
        service.close()
    service = RunningDesktop(tmp_path)
    try:
        assert len(service.get('/api/v1/textbooks').json()['items']) == 2
    finally:
        service.close()


def test_changed_staged_restore_falls_back_to_current_space(space):
    from app.desktop import maintenance as m
    root, book, _ = space
    backup = m.create_backup(root, root)
    staged = m.stage_restore(root, root / 'backups' / (backup['id'] + '.zip'))
    m.confirm_restore(root, staged['id'])
    (root / 'restores' / staged['id'] / 'workspace.json').write_text('{}')
    assert m.resolve_active_space(root) == root
    assert m.status(root)['restore_error']
    assert not m.status(root)['pending']


def test_backup_rejects_original_changed_since_import(space):
    from app.desktop import maintenance as m
    root, _, original = space
    original.write_bytes(b'x' * original.stat().st_size)
    with pytest.raises(ValueError, match='原文件.*不一致'):
        m.create_backup(root, root)
    assert not list((root / 'backups').glob('*.zip'))
    assert m.resolve_active_space(root) == root


def test_restore_rejects_original_with_recomputed_manifest_but_wrong_source_revision(space):
    from app.desktop import maintenance as m
    root, _, original = space
    backup = m.create_backup(root, root)
    with zipfile.ZipFile(root / 'backups' / (backup['id'] + '.zip')) as archive:
        items = {name: archive.read(name) for name in archive.namelist()}
    name = next(name for name in items if name.startswith('uploads/'))
    items[name] = b'x' * len(items[name])
    manifest = json.loads(items['manifest.json'])
    manifest['files'][name] = {'sha256': hashlib.sha256(items[name]).hexdigest(), 'size': len(items[name])}
    items['manifest.json'] = json.dumps(manifest).encode()
    changed = root / 'changed-original.zip'
    with zipfile.ZipFile(changed, 'w') as archive:
        for name, content in items.items():
            archive.writestr(name, content)
    with pytest.raises(ValueError, match='原文件.*不一致'):
        m.stage_restore(root, changed)
    assert m.resolve_active_space(root) == root and original.is_file()


def test_upgrade_keeps_database_snapshot_before_schema_change(space):
    from app.desktop import maintenance as m
    root, book, _ = space
    with sqlite3.connect(root / 'learning.db') as db:
        db.execute("DELETE FROM schema_migrations WHERE version='20261026_textbook_practice_v1'")
    db.close()
    snapshot = m.backup_before_upgrade(root, root)
    assert snapshot and (snapshot / 'workspace.json').exists()
    with sqlite3.connect(snapshot / 'learning.db') as db:
        assert db.execute('SELECT COUNT(*) FROM textbooks').fetchone()[0] == 1
        assert db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0] == 4
    assert m.backup_before_upgrade(root, root) == snapshot
