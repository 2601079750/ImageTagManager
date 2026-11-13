"""Regression checks for proxied controls, dropdown focus and accent clicks."""
import logging
import sys
import tempfile
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageTk
from imagetag.app import App
from imagetag.core import Catalogue


def main():
    with tempfile.TemporaryDirectory(prefix="imagetag-theme-") as temporary:
        root = Path(temporary)
        app = App(Catalogue(root / "data", root / "library"), auto_scan=False,
                  startup_folder=root, native_services=False)
        errors = []
        app.report_callback_exception = lambda kind, value, trace: errors.append(str(value))

        def pump(seconds=.15):
            timer = app.after(round(seconds * 1000), app.quit)
            try:
                app.mainloop()
            finally:
                app.after_cancel(timer)

        try:
            picture = root / "background.png"
            Image.new("RGB", (320, 240), "#758aa2").save(picture)
            app.theme_mode.set("自定义背景")
            app.set_background(picture)
            settings = app.settings_dialog()
            settings.focus_force()
            pump(.6)

            # Native Tk widgets reject unsupported options. A display proxy must
            # preserve that catchable Tcl error, without leaking Python errors
            # into a later update/mainloop call.
            for widget in (app.tag_tree, app.tag_list, settings.auto_sync_check):
                try:
                    widget.cget("insertbackground")
                except tk.TclError:
                    pass
                else:
                    raise AssertionError("Unsupported option should raise TclError")
                pump()

            # Tcl creates the combobox popup without a Python widget object.
            combo = settings.theme_combo
            combo.tk.call("ttk::combobox::Post", str(combo))
            popup = str(combo.tk.call("ttk::combobox::PopdownWindow", str(combo))) + ".f.l"
            combo.tk.call("focus", "-force", popup)
            app.backdrop.invalidate()
            pump(.25)
            assert str(app.tk.call("focus")) == popup
            combo.tk.call("ttk::combobox::Unpost", str(combo))
            settings.focus_force()

            assert not hasattr(settings, "acrylic_check")
            assert not hasattr(app, "acrylic")

            # Exercise events on the swatches, not just their Python callbacks.
            for mode in ("浅色", "深色", "自定义背景", "深色", "浅色"):
                app.theme_mode.set(mode)
                settings.change_theme()
                pump()
                if mode == "自定义背景":
                    canvas = settings.canvases[0][0]
                    assert canvas.find_withtag("window-backdrop"), "Returning to custom background must restore the canvas layer"
                for index in range(4):
                    color = app.accent_candidates()[index]
                    settings.swatches[index].event_generate("<ButtonPress-1>", x=24, y=24, state=0, when="tail")
                    settings.swatches[index].event_generate("<ButtonRelease-1>", x=24, y=24, state=0, when="tail")
                    pump()
                    assert app.custom_accent.get() == color, (mode, index, color, app.custom_accent.get(), settings.swatches[index].winfo_ismapped(), errors)
                    # Preview is immediate; persistence is intentionally batched.
                    pump(.15)
                    assert app.catalogue.setting("custom_accent") == color
                if mode != "自定义背景":
                    # The icon keeps its smooth contour, without a square mat.
                    swatch = settings.swatches[0]
                    rendered = ImageTk.getimage(swatch.photo).convert("RGBA")
                    assert rendered.getextrema()[3] == (255, 255)
                    assert not getattr(swatch, "_opaque_surface", False)
                    assert rendered.getpixel((0, 0))[:3] == ImageTk.getimage(app.backdrop.glass[settings.background_text].photo).getpixel((0, 0))[:3]
            pump(.3)
            assert not errors, errors
            # White/black action text must never recolor neutral panels that
            # happen to share the same RGB value.
            for mode in ("浅色", "深色", "自定义背景"):
                app.theme_mode.set(mode)
                settings.change_theme()
                for color in ("#ffffff", "#000000", "#00ffaa"):
                    settings.choose_accent(color)
                    pump(.3)
                    assert settings.cget("bg") == app.palette["PANEL"]
                    for widget in app.backdrop.glass:
                        if getattr(widget, "_primary_action", False):
                            assert widget.cget("bg") == app.palette["ACCENT"]
                            assert widget.cget("fg") == app.palette["PRIMARY_INK"]
            # A proxied button may destroy its own dialog from inside invoke.
            app.theme_mode.set("自定义背景")
            settings.change_theme()
            pump()
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            done = next(w for w in descendants(settings) if isinstance(w, tk.Button) and w.cget("text") == "完成")
            done.invoke()
            pump()
            assert not settings.winfo_exists()
            assert not errors, errors
        finally:
            app.exit_app()
            app.gallery.pool.shutdown(wait=True)
            app.gallery.anim_pool.shutdown(wait=True)
            app.worker.shutdown(wait=True)
            app.network_pool.shutdown(wait=True)
            logging.shutdown()
        print("Theme regression passed: native Tcl errors, dropdown popup focus, native text, accent click events and circular swatch surfaces")


if __name__ == "__main__":
    main()
