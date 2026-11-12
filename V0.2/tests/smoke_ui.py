"""Exercise native widgets and background queue using only temporary generated images."""
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from imagetag.app import App, Preview
from imagetag.appearance import ClickCombobox
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
        assert len(app.attached_tags) == 1
        assert "2/2" in app.attached_list.get(0)
        assert app.tag_entry.winfo_rooty() < app.attached_list.winfo_rooty() < app.tag_list.winfo_rooty()
        assert app.group_combo.winfo_width() > 150
        settings = app.settings_dialog()
        pump()
        assert app.settings_dialog() is settings, "重复点击应复用设置窗口"
        assert [settings.notebook.tab(page, "text") for page in settings.notebook.tabs()] == ["外观", "同步", "备份与恢复"]
        settings.geometry("640x460")
        for name, page in settings.pages.items():
            settings.notebook.select(page)
            pump(0.1)
            for widget in (settings.theme_combo, settings.auto_sync_check, settings.export_button, settings.restore_button):
                if widget.winfo_ismapped():
                    assert widget.winfo_rootx() + widget.winfo_width() <= settings.winfo_rootx() + settings.winfo_width(), name
                    assert widget.winfo_rooty() + widget.winfo_height() <= settings.winfo_rooty() + settings.winfo_height(), name
        settings.notebook.select(settings.pages["同步"])
        settings.auto_sync_check.invoke()
        assert not app.auto_sync.get() and catalogue.setting("auto_sync") == "0"
        settings.auto_sync_check.invoke()
        assert app.auto_sync.get() and catalogue.setting("auto_sync") == "1"
        settings.auto_sync_check.invoke()
        settings.notebook.select(settings.pages["外观"])
        combos = []
        def collect(widget):
            if isinstance(widget, ClickCombobox):
                combos.append(widget)
            for child in widget.winfo_children():
                collect(child)
        collect(app)
        for combo in combos:
            before = combo.get()
            combo.focus_force()
            for delta in (-120, 120, -240):
                combo.event_generate("<MouseWheel>", delta=delta)
            assert combo.get() == before, "滚轮不能更改下拉值"
            combo.style_dropdown()
        manager = app.tags_dialog()
        pump()
        manager.geometry("740x540")
        for page in (0, 1):
            manager.notebook.select(page)
            pump(0.1)
            def check_visible_actions(widget):
                if isinstance(widget, tk.Button) and widget.winfo_ismapped():
                    assert widget.winfo_rooty() + widget.winfo_height() <= manager.winfo_rooty() + manager.winfo_height(), widget.cget("text")
                for child in widget.winfo_children():
                    check_visible_actions(child)
            check_visible_actions(manager)
        manager.notebook.select(0)
        destination = catalogue.create_group("测试分类")
        manager.refresh()
        tag_id = app.all_tags[0]["id"]
        manager.tag_tree.selection_set(str(tag_id))
        manager.destination.set("测试分类")
        manager.move_selected()
        assert app.all_tags[0]["group_id"] == destination
        assert len(app.attached_tags) == 1
        assert app.attached_tags[0]["group_name"] == "测试分类"
        app.attached_list.selection_set(0)
        app.tag_list.selection_set(0)
        for theme in ("黑色", "白色", "跟随系统"):
            settings.theme_combo.set(theme)
            settings.theme_combo.event_generate("<<ComboboxSelected>>")
            pump(0.1)
            assert catalogue.setting("theme") == theme
            assert manager.cget("bg") == app.palette["PANEL"]
            assert settings.cget("bg") == app.palette["PANEL"]
            for widget in (app.attached_list, app.tag_list):
                assert widget.curselection() == (0,), "切换主题应保留所选标签"
                assert widget.cget("selectbackground") == app.palette["ROW_SELECT"]
                assert widget.cget("selectforeground") == app.palette["ROW_SELECT_INK"]
            app.group_combo.style_dropdown()
        with patch("imagetag.app.system_theme", return_value="黑色"):
            app.apply_theme(persist=False)
            assert app.resolved_theme == "黑色"
        with patch("imagetag.app.system_theme", return_value="白色"):
            app.check_system_theme()
            assert app.resolved_theme == "白色"
        manager.destroy()
        settings.destroy()
        backup_file = root / "ui-backup.json"
        settings = app.settings_dialog("备份与恢复")
        with patch("imagetag.app.filedialog.asksaveasfilename", return_value=str(backup_file)):
            settings.export_button.invoke()
        deadline = time.monotonic() + 5
        while app.busy and time.monotonic() < deadline:
            pump(0.1)
        assert backup_file.is_file() and not app.busy
        original_name = app.all_tags[0]["name"]
        catalogue.rename_tag(tag_id, "待恢复的修改")
        app.reload()
        settings = app.settings_dialog("备份与恢复")
        with patch("imagetag.app.filedialog.askopenfilename", return_value=str(backup_file)), \
             patch("imagetag.app.messagebox.askyesno", return_value=False):
            settings.restore_button.invoke()
        assert settings.winfo_exists() and not app.busy
        assert catalogue.tags()[0]["name"] == "待恢复的修改"
        with patch("imagetag.app.filedialog.askopenfilename", return_value=str(backup_file)), \
             patch("imagetag.app.messagebox.askyesno", return_value=True), \
             patch("imagetag.app.messagebox.showinfo") as notice:
            settings.restore_button.invoke()
            deadline = time.monotonic() + 5
            while app.busy and time.monotonic() < deadline:
                pump(0.1)
            assert notice.called and not app.busy
        assert catalogue.tags()[0]["name"] == original_name
        assert list((catalogue.data_dir / "backups").glob("before-restore-*.json"))
        assert catalogue.setting("auto_sync") == "0"
        second_tag = catalogue.create_tag("筛选测试", destination)
        first, second, third = [row["id"] for row in app.all_rows[:3]]
        catalogue.apply_tag([first, third], second_tag)
        app.reload()
        assert tuple(app.match_combo["values"]) == ("全部", "任一")
        app.tag_filters = {tag_id, second_tag}
        app.match_combo.set("全部")
        app.match_combo.event_generate("<<ComboboxSelected>>")
        assert {row["id"] for row in app.filtered} == {first}
        app.match_combo.set("任一")
        app.match_combo.event_generate("<<ComboboxSelected>>")
        assert {row["id"] for row in app.filtered} == {first, second, third}
        app.match_combo.set("全部")
        app.clear_filters()
        catalogue.delete_tags([second_tag])
        app.reload()
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
        for open_dialog in (app.import_dialog, app.sources_dialog, app.settings_dialog, app.tags_dialog, app.replace_tag_dialog):
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
        pump(0.3)
        assert not app.gallery.hover_layers, "离开后应完成缩小并释放图片"
        static = next(row for row in app.all_rows if not row["animated"])
        app.gallery.hover_id = static["id"]
        app.gallery.start_hover()
        pump(0.12)
        layer = app.gallery.hover_layers[static["id"]]
        scale = layer["scale"]
        assert 0 < scale < 1, "悬停放大应有过渡帧"
        pump(0.25)
        assert layer["scale"] == 1
        app.gallery.stop_hover()
        pump(0.06)
        assert 0 < layer["scale"] < 1, "移开应平滑缩小"
        pump(0.2)
        assert not app.gallery.hover_layers
        manager = app.tags_dialog()
        manager.tag_tree.selection_set(str(tag_id))
        with patch("imagetag.app.messagebox.askyesno", return_value=True):
            manager.delete_selected_tags()
        assert not app.all_tags and not app.attached_tags
        manager.category_tree.selection_set(str(destination))
        with patch("imagetag.app.messagebox.askyesno", return_value=True):
            manager.delete_category()
        assert destination not in [g["id"] for g in app.groups]
        manager.destroy()
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
        restarted = App(Catalogue(root / "data", root / "library"), auto_scan=False)
        assert not restarted.auto_sync.get(), "重启应保留自动同步开关"
        assert restarted.theme_mode.get() == "跟随系统"
        restarted.close()
        restarted.gallery.pool.shutdown(wait=True)
        restarted.gallery.anim_pool.shutdown(wait=True)
        restarted.worker.shutdown(wait=True)
        print("UI smoke passed: virtual gallery, wheel guards, tag management, settings, persisted sync, themes, backup/restore, all/any filtering, smooth hover, previews, worker queue")


if __name__ == "__main__":
    main()
