"""Real Windows tray/theme smoke checks against generated data only."""
import os
import ctypes
from ctypes import wintypes
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from imagetag.app import App
from imagetag.core import Catalogue


def main():
    if os.name != "nt":
        return
    with tempfile.TemporaryDirectory(prefix="imagetag-native-") as temporary:
        root = Path(temporary)
        catalogue = Catalogue(root / "data", root / "library")
        catalogue.set_setting("acrylic", "1")  # Existing preferences must be harmless.
        app = App(catalogue, auto_scan=False, startup_folder=root)
        errors = []
        app.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
        def pump(seconds=.3):
            app.after(round(seconds*1000), app.quit)
            app.mainloop()
        def descendants(widget):
            for child in widget.winfo_children():
                if getattr(child, "_wallpaper_layer", False):
                    continue
                yield child
                yield from descendants(child)
        pump(.8)
        assert app.tray and app.tray.ok, "Native tray was not created"
        assert app.hide_to_tray()
        assert app.state() == "withdrawn"
        app.events.put(("tray", "show"))
        pump()
        assert app.state() == "normal"
        assert not hasattr(app, "acrylic") and not hasattr(app, "acrylic_active")
        background = root / "test-background.png"
        Image.new("RGB", (320, 240), "#9fb8c6").save(background)
        app.set_background(background)
        for mode in ("浅色", "深色", "自定义背景"):
            app.theme_mode.set(mode)
            app.apply_theme()
            settings = app.settings_dialog()
            pump(.5)
            assert app.wm_attributes("-transparentcolor") == ""
            assert settings.wm_attributes("-transparentcolor") == ""
            assert not hasattr(settings, "acrylic_check")
            assert not any("Acrylic" in str(w.cget("text")) for w in descendants(settings)
                           if isinstance(w, (tk.Label, tk.Checkbutton)))
            controls = list(descendants(app))
            primary = [w.cget("text") for w in controls if isinstance(w, tk.Button) and getattr(w, "_primary_action", False)]
            assert sorted(primary) == sorted(("＋ 导入图片 / 文件夹", "＋ 创建并添加到所选图片", "添加所选标签")), primary
            user = ctypes.windll.user32
            user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user.GetAncestor.restype = wintypes.HWND
            user.IsWindowVisible.argtypes = [wintypes.HWND]
            user.IsIconic.argtypes = [wintypes.HWND]
            with app.backdrop.transaction():
                for window in (app, settings):
                    handle = user.GetAncestor(window.winfo_id(), 2)
                    assert user.IsWindowVisible(handle), "Repaint must not hide a window"
                    assert not user.IsIconic(handle), "Repaint must not minimize a window"
            for widget in controls:
                if not widget.winfo_viewable():
                    continue
                if isinstance(widget, tk.Label):
                    assert user.GetWindowLongW(widget.winfo_id(), -16) & 0x02000000
                    role = getattr(widget, "_foreground_role", None)
                    if role:
                        assert widget.cget("fg") == app.palette[role]
                    surface = app.backdrop.glass[widget]
                    assert all(surface.canvas.type(item) != "image" for item in surface.canvas.find_all()[1:]), "Text must use native glyphs"
                if isinstance(widget, tk.Button) and getattr(widget, "_primary_action", False):
                    canvas = app.backdrop.glass[widget].canvas
                    item = next(i for i in canvas.find_all() if canvas.type(i) == "text")
                    box = canvas.bbox(item)
                    assert abs((box[0]+box[2])/2 - widget.winfo_width()/2) <= 2
                    assert abs((box[1]+box[3])/2 - widget.winfo_height()/2) <= 2
            for swatch in (*settings.swatches, settings.custom_swatch):
                assert not swatch._opaque_surface
                assert ImageTk.getimage(swatch.photo).getpixel((0, 0))[:3] == app.backdrop.crop(swatch, (48, 48)).getpixel((0, 0))
            for color in ("#ff0066", "#3040dd"):
                settings.choose_accent(color)
                pump(.1)
                assert app.custom_accent.get() == color
            data = app.backdrop.notebooks[settings.notebook]
            index, left, right = data["regions"][1]
            data["header"].event_generate("<Button-1>", x=(left+right)//2, y=10)
            pump(.1)
            assert settings.notebook.index(settings.notebook.select()) == index
            settings.notebook.focus_force()
            settings.notebook.event_generate("<KeyPress-Right>")
            pump(.1)
            assert settings.notebook.index(settings.notebook.select()) == index+1
            settings.destroy()
        assert catalogue.setting("acrylic") == "1", "Retired preferences need no destructive migration"
        app.close()
        pump()
        assert app._close_dialog.winfo_exists()
        assert not app.closing
        app._close_dialog.destroy()
        app.hide_on_close.set(True)
        app.save_close_behavior()
        app.close()
        pump()
        assert app.state() == "withdrawn"
        app.show_window()
        pump()
        tray = app.tray
        app.exit_app()
        tray.thread.join(timeout=3)
        assert not tray.ok
        assert not errors, errors
        app.gallery.pool.shutdown(wait=True)
        app.gallery.anim_pool.shutdown(wait=True)
        app.worker.shutdown(wait=True)
        app.network_pool.shutdown(wait=True)
        print("Native smoke passed: tray create/hide/restore/cleanup, close prompt/default, three themes, native text and legacy preference compatibility")


if __name__ == "__main__":
    main()
