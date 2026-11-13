"""Exercise translucent surfaces against real native selection and scrolling."""
import logging
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw, ImageTk
from imagetag.app import App
from imagetag.core import Catalogue
from imagetag.colors import contrast


def main():
    with tempfile.TemporaryDirectory(prefix="imagetag-glass-") as temporary:
        root = Path(temporary)
        catalogue = Catalogue(root / "data", root / "library")
        picture = root / "pattern.png"
        art = Image.new("RGB", (640, 480), "white")
        draw = ImageDraw.Draw(art)
        for x in range(0, 640, 32):
            for y in range(0, 480, 32):
                draw.rectangle((x, y, x+31, y+31), fill="black" if (x+y)//32 % 2 else "white")
        art.save(picture)
        catalogue.import_paths([picture], "reference")
        group = catalogue.groups()[0]["id"]
        for i in range(60):
            catalogue.create_tag(f"中文标签 {i:02d} AaBb 123", group)
        catalogue.set_setting("theme", "自定义背景")
        app = App(catalogue, auto_scan=False, startup_folder=root, native_services=False)
        errors = []
        app.report_callback_exception = lambda kind, value, trace: errors.append(str(value))

        def pump(seconds=.12):
            until = time.monotonic()+seconds
            while time.monotonic() < until:
                app.update()
                time.sleep(.01)

        def click(surface, x, y, state=0):
            surface.canvas.event_generate("<Enter>", x=x, y=y)
            surface.canvas.event_generate("<ButtonPress-1>", x=x, y=y, state=state)
            surface.canvas.event_generate("<ButtonRelease-1>", x=x, y=y, state=state)
            pump()

        app.set_background(picture)
        app.background_opacity.set(100)
        app.schedule_background_opacity()
        pump(.6)
        app.gallery.selected = {app.all_rows[0]["id"]}
        app.selection_changed()
        pump()
        app.focus_force()
        native = app.tag_list
        surface = app.backdrop.glass[native]
        native.yview_moveto(0)
        pump()
        click(surface, 50, 9)
        assert native.curselection() == (0,)
        row_height = native.bbox(0)[3]
        click(surface, 50, row_height+9, 4)  # Ctrl adds a second row.
        assert native.curselection() == (0, 1), native.curselection()
        native.focus_force()
        native.event_generate("<KeyPress-Down>")
        pump()
        assert native.curselection() == (2,), native.curselection()
        native.yview_moveto(1)
        pump()
        visible = [surface.canvas.itemcget(item, "text") for item in surface.canvas.find_all()
                   if surface.canvas.type(item) == "text"]
        assert native.get("end") in visible, visible
        surface.canvas.event_generate("<MouseWheel>", delta=120)
        pump()
        assert native.yview()[1] < 1, native.yview()
        native.yview_moveto(0)
        pump()
        click(surface, 50, 9)
        app.modify_tags(False)
        pump()
        assert app.attached_tags, "Selection through the surface must apply real tags"
        tree = app.tag_tree
        tree.see("t"+str(app.all_tags[0]["id"]))
        pump()
        y = tree.bbox("t"+str(app.all_tags[0]["id"]))[1]+14
        click(app.backdrop.glass[tree], 65, y)
        assert app.all_tags[0]["id"] in app.tag_filters
        settings = app.settings_dialog()
        pump(.4)
        check = settings.auto_sync_check
        settings.notebook.select(settings.pages["同步与后台"])
        pump()
        before = app.auto_sync.get()
        click(app.backdrop.glass[check], 9, check.winfo_height()//2)
        assert app.auto_sync.get() != before
        settings.notebook.select(settings.pages["外观"])
        for color in ("#000000", "#ffffff", "#ff0066", "#00ffaa", "#3030ff"):
            settings.choose_accent(color)
            pump()
            p = app.palette
            assert contrast(p["ROW_SELECT_INK"], p["ROW_SELECT"]) >= 4.5
            assert contrast(p["MUTED"], "#ffffff") >= 4.5
        for mode in ("浅色", "深色", "自定义背景"):
            app.theme_mode.set(mode)
            settings.change_theme()
            for geometry in ("850x650", "980x820"):
                settings.geometry(geometry)
                pump()
            assert surface.canvas.winfo_ismapped(), "三种主题都保留一致的交互显示层"
            for widget, button_surface in app.backdrop.glass.items():
                if not getattr(widget, "_primary_action", False):
                    continue
                items = [item for item in button_surface.canvas.find_all()
                         if button_surface.canvas.type(item) == "text"]
                assert len(items) == 1
                box = button_surface.canvas.bbox(items[0])
                assert abs((box[0]+box[2])/2 - widget.winfo_width()/2) <= 2, (mode, widget.cget("text"), box)
                assert abs((box[1]+box[3])/2 - widget.winfo_height()/2) <= 2, (mode, widget.cget("text"), box)
        # On the darkest wallpaper, all text backgrounds still meet contrast.
        app.background_image = Image.new("RGB", (640, 480), "black")
        app.backdrop.invalidate()
        pump(.3)
        pixel = ImageTk.getimage(surface.photo).getpixel((3, 3))
        assert contrast("#202b40", "#"+bytes(pixel[:3]).hex()) >= 4.5
        assert not errors, errors
        settings.destroy()
        app.exit_app()
        app.gallery.pool.shutdown(wait=True)
        app.gallery.anim_pool.shutdown(wait=True)
        app.worker.shutdown(wait=True)
        app.network_pool.shutdown(wait=True)
        logging.shutdown()
        print("Glass smoke passed: native mouse/Ctrl/keyboard selection, scroll/wheel, tag actions, checkboxes, theme/resize and text contrast")


if __name__ == "__main__":
    main()
