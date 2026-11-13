"""New settings pages must be painted at idle, not after the 35 ms debounce."""
import logging
import sys
import tempfile
from pathlib import Path
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from imagetag.app import App
from imagetag.core import Catalogue


def main():
    with tempfile.TemporaryDirectory(prefix="imagetag-first-paint-") as temporary:
        folder = Path(temporary)
        app = App(Catalogue(folder / "data", folder / "library"), auto_scan=False,
                  startup_folder=folder, native_services=False)
        errors = []
        app.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
        def pump(ms=180):
            app.after(ms, app.quit)
            app.mainloop()
        def visible_controls(parent):
            for widget in parent.winfo_children():
                if getattr(widget, "_wallpaper_layer", False) or not widget.winfo_ismapped():
                    continue
                if isinstance(widget, (tk.Button, tk.Label, tk.Checkbutton)):
                    yield widget
                yield from visible_controls(widget)
        try:
            bg = folder / "background.png"
            Image.new("RGB", (1280, 900), "#758aa2").save(bg)
            app.set_background(bg)
            app.custom_accent.set("#127c98")
            for mode in ("自定义背景", "浅色", "深色"):
                app.theme_mode.set(mode)
                app.apply_theme()
                settings = app.settings_dialog()
                pump(350)
                assert all(content.cget("background") == app.palette["PANEL"]
                           for content in settings.contents.values()), (mode, "Wrong panel background")
                first_frames = []
                def inspect_first_idle(widget):
                    if not widget.winfo_exists() or not widget.winfo_ismapped():
                        return
                    surface = app.backdrop.glass.get(widget)
                    first_frames.append((str(widget), bool(surface and surface.key and surface.canvas.find_all())))
                def mapped(event):
                    w = event.widget
                    if isinstance(w, (tk.Button, tk.Label, tk.Checkbutton)):
                        app.after_idle(lambda w=w: inspect_first_idle(w))
                settings.bind("<Map>", mapped, add="+")
                # Each destination is visited for the first time, then revisited.
                for index in (1, 2, 3, 4, 0, 3, 1):
                    settings.notebook.select(index)
                    # Let native mapping finish; the Map probe above checks the
                    # first idle separately, before a delayed refresh can pass.
                    pump(100)
                    app.update_idletasks()
                    assert settings.notebook.index(settings.notebook.select()) == index
                    page = settings.nametowidget(settings.notebook.select())
                    controls = list(visible_controls(page))
                    assert controls, (mode, index, "Missing page content")
                    unpainted = [str(w) for w in controls if w not in app.backdrop.glass
                                 or not app.backdrop.glass[w].canvas.winfo_ismapped()]
                    assert not unpainted, (mode, index, "Page exposed before custom surfaces", unpainted)
                    if mode == "自定义背景":
                        canvas = settings.canvases[index][0]
                        assert canvas.find_withtag("window-backdrop"), (index, "Missing background")
                    assert settings.state() == "normal" and app.state() == "normal"
                    pump(160)
                # Exercise the same header events and keyboard path as real use.
                for index in (4, 2, 0, 1, 3):
                    data = app.backdrop.notebooks[settings.notebook]
                    _, left, right = next(r for r in data["regions"] if r[0] == index)
                    data["header"].event_generate("<Button-1>", x=(left+right)//2, y=10)
                    pump(100)
                    app.update_idletasks()
                    assert settings.notebook.index(settings.notebook.select()) == index
                    assert settings.state() == "normal" and app.state() == "normal"
                    pump(140)
                settings.notebook.focus_force()
                settings.notebook.event_generate("<KeyPress-Left>")
                pump(100)
                app.update_idletasks()
                assert settings.notebook.index(settings.notebook.select()) == 2
                assert first_frames, (mode, "First-map probes did not run")
                assert all(ready for _, ready in first_frames), (mode, first_frames)
                settings.destroy()
                pump()
            assert not errors, errors
        finally:
            app.exit_app()
            for pool in (app.gallery.pool, app.gallery.anim_pool, app.worker, app.network_pool):
                pool.shutdown(wait=True)
            logging.shutdown()
    print("Tab first-paint passed: all themes, first visits/revisits, no delayed blank page")


if __name__ == "__main__":
    main()
