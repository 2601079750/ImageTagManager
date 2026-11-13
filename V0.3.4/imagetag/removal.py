"""Recoverable catalogue removal. Disk originals are never deleted."""
import functools
import os
import time
from pathlib import Path


def serialized(function):
    @functools.wraps(function)
    def locked(self, *args, **kwargs):
        with self._operation_lock:
            return function(self, *args, **kwargs)
    return locked


def key(path):
    return os.path.normcase(os.path.abspath(path))


def within(path, root):
    return Path(key(path)).is_relative_to(Path(key(root)))


class CatalogueRemoval:
    def _init_removal(self, db):
        columns = {r[1] for r in db.execute('PRAGMA table_info(images)')}
        for column, kind in (('removed_at', 'REAL'), ('removal_root', 'TEXT')):
            if column not in columns:
                db.execute(f'ALTER TABLE images ADD COLUMN {column} {kind}')
        if 'enabled' not in {r[1] for r in db.execute('PRAGMA table_info(sources)')}:
            db.execute('ALTER TABLE sources ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1')
        db.execute("CREATE TABLE IF NOT EXISTS scan_rules (path TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('file','directory')), excluded INTEGER NOT NULL CHECK(excluded IN (0,1)), PRIMARY KEY(path,kind))")
        db.execute('CREATE INDEX IF NOT EXISTS removed_images ON images(removed_at)')

    def scan_rules(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM scan_rules ORDER BY length(path) DESC')]

    @staticmethod
    def excluded_path(path, rules):
        path = key(path)
        matches = [r for r in rules if (path == r['path'] if r['kind'] == 'file' else within(path, r['path']))]
        return bool(max(matches, key=lambda r: (len(r['path']), r['kind'] == 'file'))['excluded']) if matches else False

    @staticmethod
    def _rule(db, path, kind, excluded):
        db.execute('INSERT OR REPLACE INTO scan_rules(path,kind,excluded) VALUES (?,?,?)', (key(path), kind, int(excluded)))

    @serialized
    def remove_images(self, image_ids):
        ids = set(map(int, image_ids))
        with self.connection() as db:
            rows = [r for r in db.execute('SELECT id,path FROM images WHERE removed_at IS NULL') if r['id'] in ids]
            for r in rows:
                self._rule(db, r['path'], 'file', True)
                db.execute('UPDATE images SET removed_at=?,removal_root=NULL WHERE id=?', (time.time(), r['id']))
        return len(rows)

    def folder_images(self, root, removed=False):
        return [r for r in self.rows(removed=removed) if within(r['path'], root)]

    def _clear_rules_under(self, db, root):
        for r in db.execute('SELECT path,kind FROM scan_rules').fetchall():
            if within(r['path'], root):
                db.execute('DELETE FROM scan_rules WHERE path=? AND kind=?', (r['path'], r['kind']))

    @serialized
    def remove_folder(self, root):
        root = key(root)
        with self.connection() as db:
            self._clear_rules_under(db, root)
            self._rule(db, root, 'directory', True)
            rows = [r for r in db.execute('SELECT id,path FROM images WHERE removed_at IS NULL') if within(r['path'], root)]
            for r in rows:
                db.execute('UPDATE images SET removed_at=?,removal_root=? WHERE id=?', (time.time(), root, r['id']))
            for r in db.execute('SELECT id,path FROM sources').fetchall():
                if within(r['path'], root):
                    db.execute('UPDATE sources SET enabled=0 WHERE id=?', (r['id'],))
        return len(rows)

    @serialized
    def set_source_enabled(self, source_id, enabled):
        with self.connection() as db:
            db.execute('UPDATE sources SET enabled=? WHERE id=?', (int(enabled), source_id))

    @serialized
    def restore_images(self, image_ids):
        ids = set(map(int, image_ids))
        with self.connection() as db:
            rows = [r for r in db.execute('SELECT id,path FROM images WHERE removed_at IS NOT NULL') if r['id'] in ids]
            for r in rows:
                self._rule(db, r['path'], 'file', False)
                db.execute('UPDATE images SET removed_at=NULL,removal_root=NULL,missing=? WHERE id=?', (int(not Path(r['path']).is_file()), r['id']))
        return len(rows)

    @serialized
    def restore_folder(self, root, resume_sync=False):
        root = key(root)
        with self.connection() as db:
            self._clear_rules_under(db, root)
            self._rule(db, root, 'directory', not resume_sync)
            rows = [r for r in db.execute('SELECT id,path FROM images WHERE removed_at IS NOT NULL') if within(r['path'], root)]
            for r in rows:
                if not resume_sync:
                    self._rule(db, r['path'], 'file', False)
                db.execute('UPDATE images SET removed_at=NULL,removal_root=NULL,missing=? WHERE id=?', (int(not Path(r['path']).is_file()), r['id']))
            if resume_sync:
                for r in db.execute('SELECT id,path FROM sources').fetchall():
                    if within(r['path'], root):
                        db.execute('UPDATE sources SET enabled=1 WHERE id=?', (r['id'],))
                db.execute("INSERT OR IGNORE INTO sources(path,kind,enabled) VALUES (?,'reference',1)", (root,))
        return len(rows)

    @serialized
    def purge_removed(self, image_ids):
        ids = set(map(int, image_ids))
        with self.connection() as db:
            rows = [r for r in db.execute('SELECT id,path FROM images WHERE removed_at IS NOT NULL') if r['id'] in ids]
            for r in rows:
                self._rule(db, r['path'], 'file', True)
                db.execute('DELETE FROM images WHERE id=?', (r['id'],))
        return len(rows)

    def expired_removed_ids(self, now=None):
        try:
            days = int(self.setting('removed_retention_days', '0'))
        except ValueError:
            return []
        if days not in (3, 7, 15, 30):
            return []
        with self.connection() as db:
            return [r[0] for r in db.execute('SELECT id FROM images WHERE removed_at IS NOT NULL AND removed_at<=?', ((time.time() if now is None else now) - days * 86400,))]

    @serialized
    def purge_expired(self):
        return self.purge_removed(self.expired_removed_ids())

    def import_conflicts(self, paths):
        rules = self.scan_rules()
        directories = [p for p in paths if Path(p).is_dir()]
        files = {key(p) for p in paths if not Path(p).is_dir()}
        selected = lambda p: key(p) in files or any(within(p, d) for d in directories)
        return ([r for r in self.rows(removed=True) if selected(r['path'])],
                any(selected(r['path']) for r in rules if r['excluded']) or any(self.excluded_path(p, rules) for p in paths)
                or any(selected(s['path']) for s in self.sources() if not s['enabled']))

    @serialized
    def prepare_reimport(self, paths):
        for path in paths:
            if Path(path).is_dir():
                self.restore_folder(path, resume_sync=True)
            else:
                self.restore_images([r['id'] for r in self.rows(removed=True) if r['path'] == key(path)])
                with self.connection() as db:
                    self._rule(db, path, 'file', False)
