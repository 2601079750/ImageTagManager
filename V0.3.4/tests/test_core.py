import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from imagetag.core import Catalogue, file_hash, filter_images, path_key


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="imagetag-test-")
        self.root = Path(self.temp.name)
        self.source = self.root / "原图"
        self.source.mkdir()
        self.catalogue = Catalogue(self.root / "data", self.root / "library")
        self.group = self.catalogue.groups()[0]["id"]

    def tearDown(self):
        self.temp.cleanup()

    def test_settings_batch_survives_reopen_without_affecting_other_preferences(self):
        self.catalogue.set_setting("library_dir", str(self.catalogue.library_dir))
        self.catalogue.set_settings({"theme": "深色", "custom_accent": "#127c98"})
        reopened = Catalogue(self.root / "data", self.root / "library")
        self.assertEqual(reopened.setting("theme"), "深色")
        self.assertEqual(reopened.setting("custom_accent"), "#127c98")
        self.assertEqual(reopened.setting("library_dir"), str(self.catalogue.library_dir))

    def picture(self, name="作品.png", color="coral", size=(320, 240)):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, color).save(path)
        return path

    def tag_first(self, name="画师A"):
        image_id = self.catalogue.rows()[0]["id"]
        tag_id = self.catalogue.create_tag(name, self.group)
        self.catalogue.apply_tag([image_id], tag_id)
        return image_id, tag_id

    def test_deleted_default_categories_stay_deleted_after_restart(self):
        for group in self.catalogue.groups():
            self.catalogue.delete_group(group["id"])
        reopened = Catalogue(self.root / "data", self.root / "library")
        self.assertEqual(reopened.groups(), [])
        custom = reopened.create_group("服装")
        self.assertEqual([g["name"] for g in reopened.groups()], ["服装"])
        self.assertEqual(reopened.create_group("服装"), custom)

    def test_upgrade_preserves_renamed_categories(self):
        self.catalogue.rename_group(self.group, "自定义类别")
        with self.catalogue.connection() as db:
            db.execute("DELETE FROM settings WHERE key='groups_initialized'")
        reopened = Catalogue(self.root / "data", self.root / "library")
        self.assertEqual(len(reopened.groups()), 4)
        self.assertEqual(reopened.groups()[0]["name"], "自定义类别")

    def test_move_tag_keeps_id_and_picture_associations(self):
        image = self.picture()
        self.catalogue.import_paths([image], "reference")
        image_id, tag_id = self.tag_first()
        group = self.catalogue.create_group("服装")
        self.catalogue.move_tags([tag_id], group)
        self.assertEqual(self.catalogue.tags()[0]["group_id"], group)
        self.assertEqual(self.catalogue.rows()[0]["tags"], {tag_id})
        self.assertEqual(self.catalogue.rows()[0]["id"], image_id)
        self.assertTrue(image.exists())

    def test_move_tag_conflict_rolls_back_whole_batch(self):
        first = self.catalogue.create_tag("A", self.group)
        second = self.catalogue.create_tag("B", self.group)
        destination = self.catalogue.create_group("服装")
        self.catalogue.create_tag("B", destination)
        with self.assertRaises(ValueError):
            self.catalogue.move_tags([first, second], destination)
        self.assertTrue(all(t["group_id"] == self.group for t in self.catalogue.tags() if t["id"] in (first, second)))
        with self.assertRaises(ValueError):
            self.catalogue.move_tags([first], 99999)

    def test_delete_tag_removes_links_and_preserves_image_file(self):
        image = self.picture()
        digest = file_hash(image)
        self.catalogue.import_paths([image], "reference")
        _, tag_id = self.tag_first()
        self.catalogue.delete_tags([tag_id])
        self.assertEqual(self.catalogue.tags(), [])
        self.assertEqual(self.catalogue.rows()[0]["tags"], set())
        self.assertEqual(file_hash(image), digest)

    def test_delete_nonempty_category_requires_and_transfers_to_target(self):
        self.catalogue.import_paths([self.picture()], "reference")
        _, tag = self.tag_first()
        target = self.catalogue.create_group("收藏")
        with self.assertRaises(ValueError):
            self.catalogue.delete_group(self.group)
        with self.assertRaises(ValueError):
            self.catalogue.delete_group(self.group, self.group)
        self.catalogue.delete_group(self.group, target)
        self.assertNotIn(self.group, [g["id"] for g in self.catalogue.groups()])
        self.assertEqual(self.catalogue.tags()[0]["group_id"], target)
        self.assertEqual(self.catalogue.rows()[0]["tags"], {tag})

    def test_category_delete_conflict_preserves_category_and_tags(self):
        first = self.catalogue.create_tag("A", self.group)
        self.catalogue.create_tag("B", self.group)
        target = self.catalogue.create_group("收藏")
        self.catalogue.create_tag("B", target)
        with self.assertRaises(ValueError):
            self.catalogue.delete_group(self.group, target)
        self.assertIn(self.group, [g["id"] for g in self.catalogue.groups()])
        self.assertEqual(next(t for t in self.catalogue.tags() if t["id"] == first)["group_id"], self.group)

    def test_empty_categories_survive_backup_restore_restart(self):
        for group in self.catalogue.groups():
            self.catalogue.delete_group(group["id"])
        backup = self.root / "empty.json"
        self.catalogue.backup(backup)
        self.catalogue.create_group("临时类别")
        self.catalogue.restore(backup)
        reopened = Catalogue(self.root / "data", self.root / "library")
        self.assertEqual(reopened.groups(), [])

    def test_theme_setting_is_persistent(self):
        self.catalogue.set_setting("theme", "黑色")
        reopened = Catalogue(self.root / "data", self.root / "library")
        self.assertEqual(reopened.setting("theme"), "黑色")

    def test_reference_recursive_preserves_original(self):
        image = self.picture("子目录/作品.png")
        digest = file_hash(image)
        report = self.catalogue.import_paths([self.source], "reference")
        self.assertEqual(report.added, 1)
        self.assertEqual(file_hash(image), digest)
        self.assertEqual(self.catalogue.rows()[0]["path"], path_key(image))
        self.assertTrue(self.catalogue.thumb_path(digest).exists())

    def test_copy_does_not_overwrite_or_remove_originals(self):
        image = self.picture()
        self.catalogue.import_paths([image], "copy")
        self.catalogue.import_paths([image], "copy")
        rows = self.catalogue.rows()
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["path"], rows[1]["path"])
        self.assertTrue(image.exists())
        self.assertEqual(file_hash(Path(rows[0]["path"])), file_hash(image))

    def test_move_preserves_tags_and_deletes_only_selected_images(self):
        image = self.picture()
        other = self.source / "keep.txt"
        other.write_text("keep", encoding="utf-8")
        self.catalogue.import_paths([self.source], "reference")
        image_id, tag_id = self.tag_first()
        report = self.catalogue.import_paths([self.source], "move")
        self.assertFalse(report.errors)
        self.assertFalse(image.exists())
        self.assertTrue(other.exists())
        rows = self.catalogue.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], image_id)
        self.assertEqual(rows[0]["tags"], {tag_id})
        self.assertTrue(Path(rows[0]["path"]).is_file())

    def test_move_failed_copy_preserves_source(self):
        image = self.picture()
        with patch("imagetag.core.shutil.copy2", side_effect=OSError("模拟磁盘写入失败")):
            report = self.catalogue.import_paths([image], "move")
        self.assertTrue(image.exists())
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(self.catalogue.rows(), [])

    def test_move_failed_database_write_preserves_source(self):
        image = self.picture()
        with patch.object(self.catalogue, "_store", side_effect=OSError("模拟数据库写入失败")):
            report = self.catalogue.import_paths([image], "move")
        self.assertTrue(image.exists())
        self.assertTrue(report.errors)

    def test_move_changed_source_is_not_deleted(self):
        image = self.picture()
        original_copy = shutil.copy2

        def changing_copy(source, destination):
            original_copy(source, destination)
            Image.new("RGB", (100, 100), "blue").save(source)

        with patch("imagetag.core.shutil.copy2", side_effect=changing_copy):
            report = self.catalogue.import_paths([image], "move")
        self.assertTrue(image.exists())
        self.assertTrue(report.errors)

    def test_overlapping_folder_import_is_deduplicated(self):
        self.picture("nested/image.png")
        report = self.catalogue.import_paths([self.source, self.source / "nested"], "copy")
        self.assertEqual(report.added, 1)

    def test_prevent_importing_library_into_itself(self):
        with self.assertRaises(ValueError):
            self.catalogue.import_paths([self.root], "move")

    def test_scan_detects_new_files_updates_and_missing(self):
        first = self.picture()
        self.catalogue.import_paths([self.source], "reference")
        image_id, tag_id = self.tag_first()
        Image.new("RGB", (480, 320), "navy").save(first)
        self.picture("新图.jpg")
        report = self.catalogue.scan()
        self.assertEqual(report.added, 1)
        self.assertEqual(report.updated, 1)
        row = next(r for r in self.catalogue.rows() if r["id"] == image_id)
        self.assertEqual(row["width"], 480)
        self.assertEqual(row["tags"], {tag_id})
        first.unlink()
        self.assertEqual(self.catalogue.scan().missing, 1)

    def test_unchanged_scan_does_not_redecode(self):
        self.picture()
        self.catalogue.import_paths([self.source], "reference")
        with patch.object(self.catalogue, "inspect", side_effect=AssertionError("不应解码")):
            report = self.catalogue.scan()
        self.assertFalse(report.errors)
        self.assertEqual(report.updated, 0)

    def test_rename_auto_recovery_keeps_tags(self):
        image = self.picture()
        self.catalogue.import_paths([self.source], "reference")
        image_id, tag_id = self.tag_first()
        renamed = image.with_name("已改名.png")
        image.rename(renamed)
        report = self.catalogue.scan()
        self.assertEqual(report.recovered, 1)
        row = self.catalogue.rows()[0]
        self.assertEqual(row["id"], image_id)
        self.assertEqual(row["tags"], {tag_id})
        self.assertEqual(row["path"], path_key(renamed))

    def test_explicit_recovery_outside_sources(self):
        image = self.picture()
        self.catalogue.import_paths([image], "reference")
        image_id, tag_id = self.tag_first()
        new = self.root / "新位置"
        new.mkdir()
        image.rename(new / "改名.png")
        report = self.catalogue.recover([new])
        self.assertEqual(report.recovered, 1)
        self.assertEqual(self.catalogue.rows()[0]["tags"], {tag_id})
        self.assertEqual(self.catalogue.rows()[0]["id"], image_id)

    def test_ambiguous_candidates_never_picked_automatically(self):
        image = self.picture()
        self.catalogue.import_paths([image], "reference")
        image_id, tag_id = self.tag_first()
        candidate_dir = self.root / "候选"
        candidate_dir.mkdir()
        shutil.copy2(image, candidate_dir / "a.png")
        shutil.copy2(image, candidate_dir / "b.png")
        image.unlink()
        report = self.catalogue.recover([candidate_dir])
        self.assertEqual(report.recovered, 0)
        self.assertEqual(len(report.candidates), 1)
        self.assertEqual(len(report.candidates[0][1]), 2)
        self.assertEqual(self.catalogue.rows()[0]["missing"], 1)
        self.catalogue.relink(image_id, candidate_dir / "b.png")
        self.assertEqual(self.catalogue.rows()[0]["tags"], {tag_id})

    def test_scan_with_ambiguous_new_paths_keeps_missing_record(self):
        image = self.picture()
        self.catalogue.import_paths([self.source], "reference")
        self.tag_first()
        shutil.copy2(image, image.with_name("a.png"))
        shutil.copy2(image, image.with_name("b.png"))
        image.unlink()
        report = self.catalogue.scan()
        self.assertEqual(len(report.candidates), 1)
        self.assertEqual(len(self.catalogue.rows()), 1)
        self.assertTrue(self.catalogue.rows()[0]["missing"])

    def test_manual_relink_requires_same_content_unless_allowed(self):
        image = self.picture()
        self.catalogue.import_paths([image], "reference")
        image_id, tag_id = self.tag_first()
        other = self.picture("other.png", color="green")
        with self.assertRaises(ValueError):
            self.catalogue.relink(image_id, other)
        self.catalogue.relink(image_id, other, allow_changed=True)
        self.assertEqual(self.catalogue.rows()[0]["tags"], {tag_id})

    def test_relocate_entire_source_folder(self):
        image = self.picture("nested/image.png")
        self.catalogue.import_paths([self.source], "reference")
        _, tag_id = self.tag_first()
        source = next(s for s in self.catalogue.sources() if s["kind"] == "reference")
        moved = self.root / "搬家后"
        self.source.rename(moved)
        report = self.catalogue.relocate_source(source["id"], moved)
        self.assertEqual(report.recovered, 1)
        self.assertEqual(report.missing, 0)
        self.assertEqual(self.catalogue.rows()[0]["tags"], {tag_id})
        self.assertNotIn(source["path"], {s["path"] for s in self.catalogue.sources()})

    def test_grouped_tags_batch_local_replace_and_global_rename(self):
        self.picture("a.png")
        self.picture("b.png", color="blue")
        self.catalogue.import_paths([self.source], "reference")
        ids = [row["id"] for row in self.catalogue.rows()]
        first = self.catalogue.create_tag("角色A", self.group)
        second = self.catalogue.create_tag("角色B", self.group)
        self.catalogue.apply_tag(ids, first)
        self.catalogue.replace_tag([ids[0]], first, second)
        rows = {row["id"]: row for row in self.catalogue.rows()}
        self.assertEqual(rows[ids[0]]["tags"], {second})
        self.assertEqual(rows[ids[1]]["tags"], {first})
        self.catalogue.rename_tag(first, "角色A完整名称")
        self.assertEqual(next(t for t in self.catalogue.tags() if t["id"] == first)["name"], "角色A完整名称")
        self.catalogue.apply_tag(ids, second, remove=True)
        self.assertFalse(self.catalogue.rows()[0]["tags"])

    def test_duplicate_tag_reuses_existing_with_unicode_casefold(self):
        first = self.catalogue.create_tag("  Artist A  ", self.group)
        second = self.catalogue.create_tag("artist a", self.group)
        self.assertEqual(first, second)
        other = self.catalogue.create_tag("Other", self.group)
        with self.assertRaises(ValueError):
            self.catalogue.rename_tag(other, "ARTIST A")

    def test_backup_restore_after_move_preserves_tags(self):
        image = self.picture()
        self.catalogue.import_paths([self.source], "reference")
        image_id, tag_id = self.tag_first()
        backup = self.root / "backup.json"
        self.catalogue.backup(backup)
        moved = self.root / "moved"
        moved.mkdir()
        image.rename(moved / image.name)
        self.catalogue.apply_tag([image_id], tag_id, remove=True)
        safety = self.catalogue.restore(backup)
        self.assertTrue(safety.is_file())
        self.assertEqual(self.catalogue.rows()[0]["tags"], {tag_id})
        self.assertEqual(self.catalogue.rows()[0]["missing"], 1)
        self.assertEqual(self.catalogue.recover([moved]).recovered, 1)

    def test_corrupt_backup_cannot_destroy_active_catalogue(self):
        self.picture()
        self.catalogue.import_paths([self.source], "reference")
        image_id, tag_id = self.tag_first()
        backup = self.root / "backup.json"
        self.catalogue.backup(backup)
        data = json.loads(backup.read_text(encoding="utf-8"))
        data["image_tags"][0]["tag_id"] = 999999
        backup.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(Exception):
            self.catalogue.restore(backup)
        self.assertEqual(self.catalogue.rows()[0]["id"], image_id)
        self.assertEqual(self.catalogue.rows()[0]["tags"], {tag_id})

    def test_multiple_format_metadata_and_animation(self):
        for name in ("a.jpg", "b.png", "c.webp", "d.bmp", "e.tiff"):
            self.picture(name)
        gif = self.source / "animation.gif"
        Image.new("RGB", (64, 64), "red").save(gif, save_all=True, append_images=[Image.new("RGB", (64, 64), "blue")], duration=120, loop=0)
        self.catalogue.import_paths([self.source], "reference")
        self.assertEqual(len(self.catalogue.rows()), 6)
        self.assertTrue(next(r for r in self.catalogue.rows() if r["filename"] == gif.name)["animated"])

    def test_invalid_image_does_not_interrupt_import(self):
        self.picture("valid.png")
        (self.source / "broken.jpg").write_bytes(b"not an image")
        report = self.catalogue.import_paths([self.source], "reference")
        self.assertEqual(report.added, 1)
        self.assertEqual(len(report.errors), 1)

    def test_filter_intersection_union_search_scope_and_sort(self):
        self.picture("角色A.png", size=(100, 200))
        self.picture("other.png", color="blue", size=(300, 400))
        self.catalogue.import_paths([self.source], "reference")
        rows = self.catalogue.rows()
        a, b = rows[0]["id"], rows[1]["id"]
        tag1 = self.catalogue.create_tag("海边", self.group)
        tag2 = self.catalogue.create_tag("晴天", self.group)
        self.catalogue.apply_tag([a, b], tag1)
        self.catalogue.apply_tag([a], tag2)
        rows, tags = self.catalogue.rows(), self.catalogue.tags()
        self.assertEqual(len(filter_images(rows, tags, selected_tags=[tag1, tag2])), 1)
        self.assertEqual(len(filter_images(rows, tags, selected_tags=[tag1, tag2], intersection=False)), 2)
        self.assertEqual(len(filter_images(rows, tags, query="晴天", search_mode="标签")), 1)
        self.assertEqual(len(filter_images(rows, tags, query="角色A", search_mode="文件名")), 1)
        self.assertEqual(len(filter_images(rows, tags, scope="未打标签")), 0)
        self.assertEqual(filter_images(rows, tags, sort="图片分辨率", descending=False)[0]["width"], 100)
        self.assertEqual(filter_images(rows, tags, sort="图片分辨率", descending=True)[0]["width"], 300)


if __name__ == "__main__":
    unittest.main()
