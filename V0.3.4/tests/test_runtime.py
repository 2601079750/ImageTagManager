"""Data safety and updater regression tests, isolated from real user data."""
import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch
from contextlib import closing

from PIL import Image

from imagetag.core import Catalogue
from imagetag.storage import (StartupCancelled, configured_data, inspect_database, migrate_data,
                              read_config, resolve_startup, snapshot_database, update_backup,
                              validate_locations, write_config)
from imagetag import updates
from imagetag.colors import image_accents, custom_palette, contrast
from imagetag.windows import SingleInstance


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="imagetag-v03-")
        self.root = Path(self.temp.name)
        self.program = self.root / "程序"
        self.program.mkdir()
        self.library = self.root / "作品库"
        self.catalogue = Catalogue(self.program / "data", self.library)
        picture = self.library / "保留原名.png"
        Image.new("RGB", (48, 32), "coral").save(picture)
        self.catalogue.import_paths([picture], "reference")
        self.tag = self.catalogue.create_tag("重要标签", self.catalogue.groups()[0]["id"])
        self.catalogue.apply_tag([self.catalogue.rows()[0]["id"]], self.tag)
        self.catalogue.set_setting("library_dir", str(self.library))

    def tearDown(self):
        self.temp.cleanup()

    def pointer(self):
        write_config(self.program, self.catalogue.data_dir, self.library)

    def startup(self, **kwargs):
        return resolve_startup(self.program, lambda previous: str(self.library), lambda *args: True,
                               lambda previous: None, **kwargs)

    def test_first_run_requires_library_without_creating_database(self):
        folder = self.root / "fresh"
        folder.mkdir()
        calls = []
        data, library = resolve_startup(folder, lambda old: calls.append(old) or str(self.library), lambda *a: True, lambda old: None)
        self.assertEqual(calls, [""])
        self.assertEqual(data, folder / "data")
        self.assertEqual(library, self.library)
        self.assertFalse((data / "catalogue.sqlite3").exists())

    def test_cancel_first_run_creates_no_empty_library(self):
        folder = self.root / "fresh"
        folder.mkdir()
        with self.assertRaises(StartupCancelled):
            resolve_startup(folder, lambda old: "", lambda *a: True, lambda old: None)
        self.assertEqual(list(folder.iterdir()), [])

    def test_config_persists_both_locations_and_relative_default(self):
        self.pointer()
        config = read_config(self.program)
        self.assertEqual(config["data_dir"], "data")
        data, library = self.startup()
        self.assertEqual(data, self.catalogue.data_dir)
        self.assertEqual(library, self.library)
        self.assertEqual(Catalogue(data, library).rows()[0]["tags"], {self.tag})

    def test_external_data_path_persists(self):
        destination = self.root / "另一磁盘数据"
        migrate_data(self.catalogue.data_dir, destination)
        write_config(self.program, destination, self.library)
        self.assertEqual(read_config(self.program)["data_dir"], str(destination))
        data, library = self.startup()
        self.assertEqual(data, destination)
        self.assertEqual(Catalogue(data, library).rows()[0]["tags"], {self.tag})

    def test_missing_configured_data_never_silently_creates_empty_db(self):
        missing = self.root / "未连接磁盘"
        write_config(self.program, missing, self.library)
        with self.assertRaises(StartupCancelled):
            self.startup()
        self.assertFalse(missing.exists())

    def test_missing_data_can_reconnect_to_existing_database(self):
        write_config(self.program, self.root / "不存在", self.library)
        data, library = resolve_startup(self.program, lambda old: "", lambda *a: True,
                                       lambda old: str(self.catalogue.data_dir))
        self.assertEqual(data, self.catalogue.data_dir)
        self.assertEqual(library, self.library)

    def test_corrupt_pointer_stops_startup(self):
        (self.program / "portable.json").write_text("broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.startup()

    def test_snapshot_includes_committed_wal_records(self):
        # Keep a writer connection open so committed data remains in the WAL.
        with self.catalogue.connection() as db:
            db.execute("INSERT INTO tags(group_id,name,name_key) VALUES (?,?,?)", (1, "WAL标签", "wal标签"))
            db.commit()
            backup = self.root / "snapshot.sqlite3"
            snapshot_database(self.catalogue.db_path, backup)
            with closing(sqlite3.connect(backup)) as saved:
                self.assertEqual(saved.execute("SELECT COUNT(*) FROM tags").fetchone()[0], 2)

    def test_migration_preserves_records_settings_background_and_source(self):
        before = inspect_database(self.catalogue.db_path)
        (self.catalogue.data_dir / "backgrounds").mkdir()
        (self.catalogue.data_dir / "backgrounds" / "custom.png").write_bytes(b"background fixture")
        self.catalogue.set_setting("sync_seconds", "600")
        destination = self.root / "新数据"
        migrate_data(self.catalogue.data_dir, destination)
        self.assertTrue(self.catalogue.db_path.is_file())
        reopened = Catalogue(destination, self.library)
        self.assertEqual(reopened.rows(), self.catalogue.rows())
        self.assertEqual(reopened.tags(), self.catalogue.tags())
        self.assertEqual(reopened.setting("sync_seconds"), "600")
        self.assertTrue((destination / "backgrounds" / "custom.png").is_file())
        self.assertEqual(inspect_database(reopened.db_path)["fingerprints"], before["fingerprints"])

    def test_migration_refuses_nonempty_and_nested_targets(self):
        target = self.root / "非空"
        target.mkdir()
        sentinel = target / "不能覆盖.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaises(ValueError):
            migrate_data(self.catalogue.data_dir, target)
        with self.assertRaises(ValueError):
            migrate_data(self.catalogue.data_dir, self.catalogue.data_dir / "nested")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_failed_migration_keeps_source_and_pointer(self):
        self.pointer()
        config = (self.program / "portable.json").read_bytes()
        with patch("imagetag.storage.shutil.copytree", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                migrate_data(self.catalogue.data_dir, self.root / "新位置")
        self.assertTrue(self.catalogue.db_path.is_file())
        self.assertEqual((self.program / "portable.json").read_bytes(), config)
        self.assertFalse((self.root / "新位置").exists())

    def test_legacy_migration_inherits_library_without_new_prompt(self):
        folder = self.root / "new-version"
        folder.mkdir()
        with patch("builtins.input", side_effect=AssertionError("no stdin")):
            data, library = resolve_startup(folder, lambda old: self.fail("must inherit library"),
                                           lambda *args: True, lambda old: None, legacy_dir=self.catalogue.data_dir)
        self.assertEqual(library, self.library)
        self.assertEqual(inspect_database(data / "catalogue.sqlite3")["fingerprints"], inspect_database(self.catalogue.db_path)["fingerprints"])
        self.assertTrue(self.catalogue.db_path.is_file())

    def test_declining_legacy_migration_does_not_start_empty(self):
        folder = self.root / "new-version"
        folder.mkdir()
        with self.assertRaises(StartupCancelled):
            resolve_startup(folder, lambda old: str(self.library), lambda *args: False,
                            lambda old: None, legacy_dir=self.catalogue.data_dir)
        self.assertFalse((folder / "data").exists())

    def test_invalid_or_newer_database_is_rejected(self):
        bad = self.root / "bad.sqlite3"
        bad.write_bytes(b"not a database")
        with self.assertRaises(sqlite3.DatabaseError):
            inspect_database(bad)
        with self.catalogue.connection() as db:
            db.execute("PRAGMA user_version = 100")
        with self.assertRaises(ValueError):
            inspect_database(self.catalogue.db_path)

    def test_data_and_library_must_be_separate(self):
        for target in (self.library, self.library / "data", self.library.parent):
            with self.assertRaises(ValueError):
                validate_locations(target, self.library)

    def test_version_comparison_is_numeric(self):
        self.assertGreater(updates.version_key("v0.10"), updates.version_key("v0.3"))
        self.assertEqual(updates.version_key("0.3"), updates.version_key("v0.3.0"))
        for value in ("latest", "v0.4-beta", "../0.4"):
            with self.assertRaises(ValueError):
                updates.version_key(value)

    def fake_response(self, data):
        stream = io.BytesIO(data)
        stream.headers = {"Content-Length": str(len(data))}
        return stream

    def test_release_discovery_ignores_older_and_prerelease(self):
        for payload in ({"tag_name": "v0.2"}, {"tag_name": "v0.4", "prerelease": True}):
            with patch("imagetag.updates.request", return_value=self.fake_response(json.dumps(payload).encode())):
                self.assertFalse(updates.discover("0.3")["available"])

    def test_release_discovery_requires_matching_asset_and_digest(self):
        payload = {"tag_name": "v0.4", "body": "测试更新", "assets": [{"name": "ImageTagManager-0.4-Windows-x64.zip",
                   "digest": "sha256:" + "a" * 64, "browser_download_url": "https://github.com/download.zip"}]}
        with patch("imagetag.updates.request", return_value=self.fake_response(json.dumps(payload).encode())):
            release = updates.discover("0.3")
            self.assertTrue(release["available"])
            self.assertEqual(release["sha256"], "a" * 64)

    def archive(self, executable=b"MZnew executable"):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as bundle:
            bundle.writestr("ImageTagManager-0.4/ImageTagManager.exe", executable)
            bundle.writestr("ImageTagManager-0.4/portable.json", "malicious pointer")
            bundle.writestr("ImageTagManager-0.4/data/catalogue.sqlite3", "malicious db")
            bundle.writestr("../../escape.txt", "escape")
        return stream.getvalue()

    def prepare(self, contents, checksum=None):
        release = {"url": "https://github.com/download.zip", "version": "v0.4", "sha256": checksum or hashlib.sha256(contents).hexdigest()}
        with patch("imagetag.updates.request", return_value=self.fake_response(contents)):
            return updates.prepare(release, self.catalogue.data_dir)

    def test_prepare_extracts_only_executable_never_database_or_config(self):
        self.pointer()
        config = (self.program / "portable.json").read_bytes()
        before = inspect_database(self.catalogue.db_path)
        stage = self.prepare(self.archive())
        self.assertEqual({p.name for p in stage.iterdir()}, {"ImageTagManager.exe", "release.json"})
        self.assertEqual((self.program / "portable.json").read_bytes(), config)
        self.assertEqual(inspect_database(self.catalogue.db_path), before)
        self.assertFalse((self.root / "escape.txt").exists())

    def test_corrupted_download_leaves_database_untouched(self):
        before = inspect_database(self.catalogue.db_path)
        with self.assertRaises(ValueError):
            self.prepare(self.archive(), "0" * 64)
        self.assertEqual(inspect_database(self.catalogue.db_path), before)
        self.assertFalse(any((self.catalogue.data_dir / "updates").iterdir()))

    def test_invalid_executable_is_rejected(self):
        with self.assertRaises(ValueError):
            self.prepare(self.archive(b"not an exe"))

    def plan(self):
        self.pointer()
        (self.program / "ImageTagManager.exe").write_bytes(b"MZold executable")
        stage = self.prepare(self.archive())
        backup = update_backup(self.catalogue.data_dir)
        return updates.write_plan(stage, self.program, self.catalogue.data_dir, self.library, backup)

    def test_update_keeps_all_data_paths_records_and_original_images(self):
        path = self.plan()
        before = inspect_database(self.catalogue.db_path)
        config = (self.program / "portable.json").read_bytes()
        picture = (self.library / "保留原名.png").read_bytes()
        self.assertTrue(updates.install_plan(path, wait=False, restart=False))
        self.assertEqual((self.program / "ImageTagManager.exe").read_bytes(), b"MZnew executable")
        self.assertEqual((self.program / "rollback" / "ImageTagManager.exe").read_bytes(), b"MZold executable")
        self.assertEqual((self.program / "portable.json").read_bytes(), config)
        self.assertEqual(inspect_database(self.catalogue.db_path), before)
        self.assertEqual((self.library / "保留原名.png").read_bytes(), picture)
        data, library = self.startup()
        reopened = Catalogue(data, library)
        self.assertEqual(reopened.rows()[0]["tags"], {self.tag})
        self.assertEqual(reopened.library_dir, self.library)

    def test_update_detects_changed_config_before_replacement(self):
        path = self.plan()
        write_config(self.program, self.root / "wrong-data", self.library)
        with self.assertRaises(ValueError):
            updates.install_plan(path, wait=False, restart=False)
        self.assertEqual((self.program / "ImageTagManager.exe").read_bytes(), b"MZold executable")

    def test_update_detects_changed_tag_records_even_when_counts_same(self):
        path = self.plan()
        self.catalogue.rename_tag(self.tag, "在准备后修改")
        with self.assertRaises(ValueError):
            updates.install_plan(path, wait=False, restart=False)
        self.assertEqual((self.program / "ImageTagManager.exe").read_bytes(), b"MZold executable")
        self.assertEqual(self.catalogue.tags()[0]["name"], "在准备后修改")

    def test_update_replacement_failure_leaves_original_exe(self):
        path = self.plan()
        def fail(*args):
            raise OSError("disk unavailable")
        with self.assertRaises(OSError):
            updates.install_plan(path, wait=False, restart=False, replace=fail)
        self.assertEqual((self.program / "ImageTagManager.exe").read_bytes(), b"MZold executable")
        self.assertEqual(self.catalogue.rows()[0]["tags"], {self.tag})

    def test_post_replace_failure_restores_original_exe_and_database(self):
        path = self.plan()
        real = updates.inspect_database
        counter = 0
        def inspect(database):
            nonlocal counter
            counter += 1
            if counter == 3:
                raise ValueError("post-replace check failed")
            return real(database)
        with patch("imagetag.updates.inspect_database", side_effect=inspect):
            with self.assertRaises(ValueError):
                updates.install_plan(path, wait=False, restart=False)
        self.assertEqual((self.program / "ImageTagManager.exe").read_bytes(), b"MZold executable")
        self.assertEqual(self.catalogue.rows()[0]["tags"], {self.tag})

    def test_theme_suggestions_are_four_distinct_colors_and_readable(self):
        for color in ("white", "black", "coral"):
            path = self.root / (color + ".png")
            Image.new("RGB", (40, 30), color).save(path)
            values = image_accents(path)
            self.assertEqual(len(set(values)), 4)
            for seed in values:
                palette = custom_palette(seed)
                self.assertGreaterEqual(contrast(palette["ACCENT"], palette["PRIMARY_INK"]), 4.5)
                self.assertGreaterEqual(contrast(palette["ACCENT_INK"], palette["PANEL"]), 4.5)

    def test_new_process_failure_restores_executable_and_database(self):
        path = self.plan()
        baseline = inspect_database(self.catalogue.db_path)
        class FailedProcess:
            def poll(self):
                return 1
        launches = 0
        def launch(*args, **kwargs):
            nonlocal launches
            launches += 1
            # Model a new program corrupting a record before failing its startup.
            if launches == 1:
                self.catalogue.rename_tag(self.tag, "失败启动中的修改")
            return FailedProcess()
        with patch("imagetag.updates.subprocess.Popen", side_effect=launch):
            with self.assertRaises(RuntimeError):
                updates.install_plan(path, wait=False, restart=True)
        self.assertEqual((self.program / "ImageTagManager.exe").read_bytes(), b"MZold executable")
        self.assertEqual(inspect_database(self.catalogue.db_path)["fingerprints"], baseline["fingerprints"])
        restored = inspect_database(self.program / "rollback" / "catalogue.sqlite3")
        self.assertEqual(restored["fingerprints"], baseline["fingerprints"])
        self.assertTrue((path.parent / "failed-startup.sqlite3").is_file())

    @unittest.skipUnless(os.name == "nt", "Windows mutex")
    def test_single_instance_activation_event_and_release(self):
        suffix = "-test-" + uuid.uuid4().hex
        first = SingleInstance(suffix, detect_legacy=False)
        second = None
        try:
            self.assertFalse(first.already_running)
            second = SingleInstance(suffix, detect_legacy=False)
            self.assertTrue(second.already_running)
            self.assertTrue(first.activation_requested())
            self.assertFalse(first.activation_requested())
        finally:
            if second:
                second.close()
            first.close()
        third = SingleInstance(suffix, detect_legacy=False)
        self.assertFalse(third.already_running)
        third.close()


if __name__ == "__main__":
    unittest.main()
