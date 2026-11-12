"""Exercise native widgets and background queue using only temporary generated images."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from imagetag.app import App, Preview
from imagetag.core import Catalogue


def main():
    with tempfile.TemporaryDirectory(prefix="imagetag-ui-") as temporary:
        root = Path(temporary)
        source = root / "fixtures"
        source.mkdir()
        for i in range(18):
            Image.new("RGB", (320 + i * 5, 240 + i * 3), (60 + i * 7, 100, 170)).save(source / f"作品-{i:02}.png")
        Image.new("RGB", (100, 100), "red").save(source / "动图.gif", save_all=True,
            append_images=[Image.new("RGB", (100, 100), "green")], duration=100, loop=0)
        catalogue = Catalogue(root / "data", root / "library")
        catalogue.import_paths([source], "reference")
        app = App(catalogue, auto_scan=False)

        def pump(seconds=0.2):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                app.update()
                time.sleep(0.01)

        errors = []
        app.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
        pump(0.8)
        assert len(app.filtered) == 19
        template = app.all_rows[0]
        virtual_rows = [dict(template, id=10000 + i) for i in range(1500)]
        app.gallery.set_rows(virtual_rows)
        pump()
        assert len(app.gallery.find_all()) < 500, "不可为 1500 张图片同时创建控件"
        app.gallery.scroll("moveto", 0.9)
        pump()
        assert len(app.gallery.find_all()) < 500
        assert len(app.gallery.photos) <= 180
        app.apply_filters(True)
        pump()
        app.gallery.selected = {app.all_rows[0]["id"], app.all_rows[1]["id"]}
        app.selection_changed()
        app.new_tag.set("测试画师")
        app.create_and_apply()
        assert sum(bool(row["tags"]) for row in app.all_rows) == 2
        app.tag_filters.add(app.all_tags[0]["id"])
        app.apply_filters()
        assert len(app.filtered) == 2
        app.clear_filters()
        pump()
        preview = Preview(app, app.all_rows[0]["id"])
        pump()
        preview.zoom(1.2)
        preview.actual()
        preview.navigate(1)
        pump()
        preview.destroy()
        for open_dialog in (app.import_dialog, app.sources_dialog, app.backup_dialog, app.tags_dialog, app.replace_tag_dialog):
            before = set(app.winfo_children())
            open_dialog()
            pump()
            for child in set(app.winfo_children()) - before:
                if child.winfo_toplevel() == child:
                    child.destroy()
        animated = next(row for row in app.all_rows if row["animated"])
        app.gallery.hover_id = animated["id"]
        app.gallery.start_hover()
        pump(0.5)
        app.gallery.stop_hover()
        app.run_job("测试扫描", catalogue.scan, quiet=True)
        pump(1.0)
        assert not app.busy
        assert not errors, errors
        app.auto_sync.set(False)
        app.close()
        app.gallery.pool.shutdown(wait=True)
        app.gallery.anim_pool.shutdown(wait=True)
        app.worker.shutdown(wait=True)
        if app.gallery.anim_image:
            app.gallery.anim_image.close()
        print("UI smoke passed: gallery, bulk tags, filters, preview, animation, dialogs, worker queue")


if __name__ == "__main__":
    main()
