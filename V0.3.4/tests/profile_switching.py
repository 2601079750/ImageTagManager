"""Measure real Tk switching work on isolated generated data (not wall-clock waits)."""
import argparse
import json
import logging
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from imagetag.app import App
from imagetag.core import Catalogue
import imagetag.backdrop as backgrounds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    results = []
    with tempfile.TemporaryDirectory(prefix="imagetag-profile-") as temp:
        root = Path(temp)
        cat = Catalogue(root / "data", root / "library")
        for i in range(30):
            Image.new("RGB", (100, 80), (i*7, 80, 130)).save(cat.library_dir / f"{i}.png")
        cat.import_paths([cat.library_dir], "reference")
        app = App(cat, auto_scan=False, startup_folder=root, native_services=False)
        app.auto_sync.set(False)
        errors = []
        app.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
        metrics = {}

        def wrap(obj, name, label):
            original = getattr(obj, name)
            def measured(*a, **kw):
                start = time.perf_counter()
                try:
                    return original(*a, **kw)
                finally:
                    item = metrics.setdefault(label, [0, 0.0])
                    item[0] += 1
                    item[1] += (time.perf_counter()-start)*1000
            setattr(obj, name, measured)
            return original

        compose = wrap(backgrounds, "compose_background", "background")
        wrap(app, "apply_filters", "filters")
        wrap(app.gallery, "redraw", "gallery")
        wrap(app.backdrop, "render", "render")
        wrap(cat, "set_setting", "save_one")
        if hasattr(cat, "set_settings"):
            wrap(cat, "set_settings", "save_batch")

        def pump(ms=180):
            app.after(ms, app.quit)
            app.mainloop()

        try:
            bg = root / "background.png"
            Image.new("RGB", (1920, 1080), "#7189a0").save(bg)
            app.set_background(bg)
            settings = app.settings_dialog()
            pump(600)
            selected_id = app.all_rows[0]["id"]
            app.gallery.selected = {selected_id}
            app.selection_changed()
            pump()
            row_ids = [r["id"] for r in app.filtered]
            for mode in ("浅色", "深色", "自定义背景"):
                app.theme_mode.set(mode)
                settings.change_theme()
                pump(350)
                for action in ("accent", "tab"):
                    samples = []
                    for i in range(6):
                        metrics.clear()
                        if action == "accent":
                            settings.notebook.select(0)
                            pump()
                            metrics.clear()
                        start = time.perf_counter()
                        if action == "accent":
                            settings.choose_accent(("#af7c8e", "#6877bd")[i % 2])
                        else:
                            data = app.backdrop.notebooks[settings.notebook]
                            target = (1, 2, 3, 4, 0, 1)[i]
                            _, left, right = next(r for r in data["regions"] if r[0] == target)
                            data["header"].event_generate("<Button-1>", x=(left+right)//2, y=10)
                        direct_ms = (time.perf_counter()-start)*1000
                        pump(380)
                        samples.append({"direct_ms": round(direct_ms, 3), "work": {k: [v[0], round(v[1], 3)] for k, v in metrics.items()}})
                        if args.check:
                            assert metrics.get("filters", [0])[0] == 0, (mode, action, metrics)
                            assert metrics.get("background", [0])[0] == 0, (mode, action, metrics)
                            if action == "tab":
                                assert metrics.get("gallery", [0])[0] == 0, (mode, metrics)
                        assert settings.state() == "normal" and app.state() == "normal"
                        assert app.gallery.selected == {selected_id}
                        assert [r["id"] for r in app.filtered] == row_ids
                    results.append({"theme": mode, "action": action, "median_direct_ms": round(statistics.median(s["direct_ms"] for s in samples), 3), "samples": samples})
                if args.check:
                    metrics.clear()
                    data = app.backdrop.notebooks[settings.notebook]
                    target = settings.notebook.index(settings.notebook.select())
                    _, left, right = next(r for r in data["regions"] if r[0] == target)
                    data["header"].event_generate("<Button-1>", x=(left+right)//2, y=10)
                    pump()
                    assert not metrics, ("Current tab should do no work", metrics)
            # Burst input coalesces the save and leaves the final color in place.
            metrics.clear()
            for color in ("#ff0066", "#ffffff", "#2030ff", "#127c98"):
                settings.choose_accent(color)
            pump(400)
            if args.check:
                assert metrics.get("save_batch", [0])[0] == 1, metrics
            # A rapid final choice must survive closing the settings immediately.
            settings.choose_accent("#128c98")
            settings.destroy()
            assert cat.setting("custom_accent") == "#128c98"
            assert not errors, errors
        finally:
            backgrounds.compose_background = compose
            app.exit_app()
            for pool in (app.gallery.pool, app.gallery.anim_pool, app.worker, app.network_pool):
                pool.shutdown(wait=True)
            logging.shutdown()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in results:
        print(row["theme"], row["action"], row["median_direct_ms"], "ms")


if __name__ == "__main__":
    main()
