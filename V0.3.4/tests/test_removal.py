import json
import sqlite3
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from imagetag.core import Catalogue, file_hash, path_key
from imagetag.storage import inspect_database, migrate_data


class RemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'originals'
        self.source.mkdir()
        self.c = Catalogue(self.root / 'data', self.root / 'library')
        self.tag = self.c.create_tag('保留标签', self.c.groups()[0]['id'])

    def image(self, name, color='coral'):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (70, 50), color).save(path)
        return path

    def populate(self):
        for name in ('nested/a.png', 'nested/deeper/b.png', 'nested-other/c.png'):
            self.image(name)
        self.c.import_paths([self.source], 'reference')
        self.c.apply_tag([r['id'] for r in self.c.rows()], self.tag)
        return self.c.rows()

    def test_batch_remove_restore_retains_ids_tags_originals(self):
        rows = self.populate()
        hashes = {r['path']: file_hash(Path(r['path'])) for r in rows}
        ids = [r['id'] for r in rows[:2]]
        self.assertEqual(self.c.remove_images(ids + ids + [999]), 2)
        self.assertEqual(len(self.c.rows()), 1)
        self.assertEqual({r['id'] for r in self.c.rows(True)}, set(ids))
        self.assertEqual(self.c.tags()[0]['count'], 1)
        self.c.scan()
        self.assertEqual(len(self.c.rows()), 1)
        self.assertEqual(self.c.restore_images(ids), 2)
        self.c.scan()
        self.assertEqual({r['id'] for r in self.c.rows()}, {r['id'] for r in rows})
        self.assertTrue(all(r['tags'] == {self.tag} for r in self.c.rows()))
        self.assertTrue(all(file_hash(Path(p)) == h for p, h in hashes.items()))

    def test_nested_exclusion_overlapping_sources_and_path_boundary(self):
        self.populate()
        nested = self.source / 'nested'
        self.c.add_source(nested)
        self.c.add_source(nested / 'deeper')
        self.assertEqual(self.c.remove_folder(nested), 2)
        self.image('nested/new.png')
        self.c.scan()
        self.assertEqual([r['filename'] for r in self.c.rows()], ['c.png'])
        self.assertTrue(all(not s['enabled'] for s in self.c.sources() if Path(s['path']).is_relative_to(nested)))
        self.assertTrue(next(s for s in self.c.sources() if s['path'] == path_key(self.source))['enabled'])

    def test_restore_one_in_removed_folder_keeps_siblings_excluded(self):
        self.populate()
        self.c.remove_folder(self.source / 'nested')
        row = self.c.rows(True)[0]
        self.c.restore_images([row['id']])
        self.image('nested/new.png')
        self.c.scan()
        self.assertEqual(len(self.c.rows()), 2)
        self.assertEqual(len(self.c.rows(True)), 1)

    def test_folder_restore_without_sync_excludes_future_files(self):
        self.populate()
        nested = self.source / 'nested'
        self.c.remove_folder(nested)
        self.c.restore_folder(nested, resume_sync=False)
        self.image('nested/new.png')
        self.c.scan()
        self.assertEqual(len(self.c.rows()), 3)
        self.c.restore_folder(nested, resume_sync=True)
        self.c.scan()
        self.assertEqual(len(self.c.rows()), 4)

    def test_child_restore_overrides_parent_exclusion(self):
        self.populate()
        self.c.remove_folder(self.source)
        self.c.restore_folder(self.source / 'nested' / 'deeper', resume_sync=True)
        self.c.scan()
        self.assertEqual([r['filename'] for r in self.c.rows()], ['b.png'])
        self.assertEqual(len(self.c.rows(True)), 2)

    def test_pause_source_keeps_records_and_skips_scan(self):
        self.populate()
        source = next(s for s in self.c.sources() if s['kind'] == 'reference')
        self.c.set_source_enabled(source['id'], False)
        self.image('new.png')
        self.image('nested/a.png', 'blue')
        with patch.object(self.c, 'inspect', side_effect=AssertionError('paused source decoded')):
            self.c.scan()
        self.assertEqual(len(self.c.rows()), 3)
        self.c.set_source_enabled(source['id'], True)
        self.assertEqual(self.c.scan().added, 1)

    def test_delete_records_only_removes_tombstones_and_links_not_files(self):
        rows = self.populate()
        self.c.remove_images([rows[0]['id']])
        self.assertEqual(self.c.purge_removed([rows[0]['id'], rows[1]['id']]), 1)
        self.c.scan()
        self.assertEqual(len(self.c.rows()), 2)
        self.assertEqual(self.c.rows(True), [])
        self.assertTrue(Path(rows[0]['path']).exists())
        self.assertEqual(len(self.c.tags()), 1)
        with self.c.connection() as db:
            self.assertFalse(db.execute('SELECT 1 FROM image_tags WHERE image_id=?', (rows[0]['id'],)).fetchone())

    def test_delete_folder_records_preserves_exclusions_after_reopen(self):
        self.populate()
        self.c.remove_folder(self.source)
        self.c.purge_removed([r['id'] for r in self.c.rows(True)])
        other = Catalogue(self.c.data_dir, self.c.library_dir)
        self.image('new.png')
        other.scan()
        self.assertEqual(other.rows(), [])
        self.assertEqual(other.rows(True), [])
        self.assertEqual(len(list(self.source.rglob('*.png'))), 4)

    def test_expiration_uses_removal_time_all_periods_and_never_active(self):
        rows = self.populate()
        self.c.remove_images([rows[0]['id'], rows[1]['id']])
        now = time.time()
        for days in (3, 7, 15, 30):
            with self.subTest(days=days):
                self.c.set_setting('removed_retention_days', str(days))
                with self.c.connection() as db:
                    db.execute('UPDATE images SET removed_at=? WHERE id=?', (now - days*86400, rows[0]['id']))
                    db.execute('UPDATE images SET removed_at=? WHERE id=?', (now - days*86400 + 1, rows[1]['id']))
                self.assertEqual(self.c.expired_removed_ids(now), [rows[0]['id']])
        self.c.set_setting('removed_retention_days', '0')
        self.assertEqual(self.c.expired_removed_ids(now), [])
        self.c.set_setting('removed_retention_days', '30')
        self.assertEqual(self.c.purge_expired(), 1)
        self.c.scan()
        self.assertEqual(len(self.c.rows()), 1)

    def test_restore_resets_retention_and_missing_is_recoverable(self):
        row = self.populate()[0]
        self.c.remove_images([row['id']])
        Path(row['path']).unlink()
        self.c.restore_images([row['id']])
        restored = next(r for r in self.c.rows() if r['id'] == row['id'])
        self.assertEqual(restored['missing'], 1)
        self.assertIsNone(restored['removed_at'])
        self.assertEqual(restored['tags'], {self.tag})

    def test_manual_relink_removed_record_does_not_restore_automatically(self):
        row = self.populate()[0]
        self.c.remove_images([row['id']])
        new = self.root / 'relocated.png'
        Path(row['path']).rename(new)
        self.c.relink(row['id'], new)
        self.c.scan()
        self.assertEqual(len(self.c.rows()), 2)
        self.assertEqual(self.c.rows(True)[0]['path'], path_key(new))
        self.c.restore_images([row['id']])
        self.assertEqual(next(r for r in self.c.rows() if r['id'] == row['id'])['tags'], {self.tag})

    def test_auto_recovery_ignores_removed_records_and_excluded_targets(self):
        rows = self.populate()
        self.c.remove_folder(self.source / 'nested')
        self.c.recover([self.source])
        self.c.scan()
        self.assertEqual(len(self.c.rows(True)), 2)
        active = self.c.rows()[0]
        target = self.source / 'nested' / 'same-as-missing.png'
        Path(active['path']).rename(target)
        self.assertEqual(self.c.recover([self.source]).recovered, 0)

    def test_explicit_reimport_requires_opt_in_and_preserves_existing_tags(self):
        row = self.populate()[0]
        path = Path(row['path'])
        self.c.remove_images([row['id']])
        records, excluded = self.c.import_conflicts([path])
        self.assertTrue(excluded)
        self.assertEqual(len(records), 1)
        self.c.import_paths([path], 'reference')
        self.assertEqual(len(self.c.rows()), 2)
        self.c.import_paths([path], 'reference', restore_removed=True)
        self.assertEqual(next(r for r in self.c.rows() if r['id'] == row['id'])['tags'], {self.tag})

    def test_explicit_reimport_purged_file_has_no_old_tag_links(self):
        row = self.populate()[0]
        path = Path(row['path'])
        self.c.remove_images([row['id']])
        self.c.purge_removed([row['id']])
        self.c.import_paths([path], 'reference', restore_removed=True)
        self.assertEqual(next(r for r in self.c.rows() if r['path'] == row['path'])['tags'], set())

    def test_library_root_can_be_cleared_and_restored_without_changing_config(self):
        picture = self.c.library_dir / 'library.png'
        Image.new('RGB', (40,40), 'green').save(picture)
        self.c.scan()
        self.c.remove_folder(self.c.library_dir)
        Catalogue(self.c.data_dir, self.c.library_dir).scan()
        self.assertEqual(self.c.rows(), [])
        self.assertTrue(picture.is_file())
        self.c.restore_folder(self.c.library_dir, True)
        self.c.scan()
        self.assertEqual(len(self.c.rows()), 1)

    def test_backup_restore_and_migration_keep_rules_records_policy(self):
        self.populate()
        self.c.remove_folder(self.source / 'nested')
        self.c.set_setting('removed_retention_days', '15')
        backup = self.root / 'backup.json'
        self.c.backup(backup)
        self.c.restore_folder(self.source / 'nested', True)
        self.c.restore(backup)
        self.assertEqual(len(self.c.rows(True)), 2)
        self.assertEqual(self.c.rows(True)[0]['tags'], {self.tag})
        self.assertEqual(self.c.setting('removed_retention_days'), '15')
        self.c.scan()
        self.assertEqual(len(self.c.rows()), 1)
        destination = self.root / 'moved-data'
        self.assertEqual(migrate_data(self.c.data_dir, destination), inspect_database(self.c.db_path))
        reopened = Catalogue(destination, self.c.library_dir)
        self.assertEqual(reopened.scan_rules(), self.c.scan_rules())
        self.assertEqual(len(reopened.rows(True)), 2)

    def test_legacy_backup_restores_without_new_columns(self):
        self.populate()
        target = self.root / 'old.json'
        self.c.backup(target)
        payload = json.loads(target.read_text(encoding='utf-8'))
        payload['version'] = 1
        payload.pop('scan_rules')
        for r in payload['images']:
            r.pop('removed_at'); r.pop('removal_root')
        for r in payload['sources']:
            r.pop('enabled')
        target.write_text(json.dumps(payload), encoding='utf-8')
        self.c.remove_folder(self.source)
        self.c.restore(target)
        self.assertEqual(len(self.c.rows()), 3)
        self.assertEqual(self.c.rows(True), [])
        self.assertEqual(self.c.scan_rules(), [])

    def test_real_v1_schema_upgrade_preserves_rows_and_creates_safety_backup(self):
        rows = self.populate()
        with self.c.connection() as db:
            db.execute('DROP INDEX removed_images')
            db.execute('DROP TABLE scan_rules')
            db.execute('ALTER TABLE images DROP COLUMN removed_at')
            db.execute('ALTER TABLE images DROP COLUMN removal_root')
            db.execute('ALTER TABLE sources DROP COLUMN enabled')
            db.execute('PRAGMA user_version=1')
        before = inspect_database(self.c.db_path)
        upgraded = Catalogue(self.c.data_dir, self.c.library_dir)
        self.assertEqual(upgraded.rows(), rows)
        self.assertTrue(all(s['enabled'] for s in upgraded.sources()))
        snapshots = list((self.c.data_dir / 'backups').glob('before-v0.3.4-*.sqlite3'))
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(inspect_database(snapshots[0]), before)
        self.assertEqual(inspect_database(upgraded.db_path, legacy=True), before)

    def test_scan_and_remove_are_serialized(self):
        rows = self.populate()
        self.image('nested/a.png', 'blue')
        entered, proceed = threading.Event(), threading.Event()
        inspect = self.c.inspect
        def blocked(path):
            entered.set()
            if not proceed.wait(5):
                raise AssertionError('timeout')
            return inspect(path)
        with ThreadPoolExecutor(max_workers=2) as pool, patch.object(self.c, 'inspect', side_effect=blocked):
            scan = pool.submit(self.c.scan)
            self.assertTrue(entered.wait(5))
            removal = pool.submit(self.c.remove_images, [r['id'] for r in rows])
            self.assertFalse(removal.done())
            proceed.set()
            scan.result(timeout=5)
            self.assertEqual(removal.result(timeout=5), 3)
        self.c.scan()
        self.assertEqual(self.c.rows(), [])

    def test_invalid_backup_rules_do_not_change_active_data(self):
        self.populate()
        target = self.root / 'bad.json'
        self.c.backup(target)
        payload = json.loads(target.read_text(encoding='utf-8'))
        payload['scan_rules'] = [{'path': str(self.source), 'kind': 'invalid', 'excluded': 1}]
        target.write_text(json.dumps(payload), encoding='utf-8')
        before = self.c.rows()
        with self.assertRaises((ValueError, sqlite3.IntegrityError)):
            self.c.restore(target)
        self.assertEqual(self.c.rows(), before)


if __name__ == '__main__':
    unittest.main()
