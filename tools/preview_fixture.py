"""Open a representative gallery with generated fixtures in an isolated test directory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw

from imagetag.app import App
from imagetag.core import Catalogue


def main():
    base = Path(__file__).resolve().parents[1] / ".test-output" / "visual"
    source = base / "generated-pictures"
    source.mkdir(parents=True, exist_ok=True)
    palettes = [
        ("#f2dcc5", "#b6c7ca", "#527780", "#f4b798"),
        ("#dbddeb", "#b5b8d6", "#66658b", "#f3dcc0"),
        ("#e5eacb", "#bdd1ae", "#527c73", "#f2db9b"),
        ("#cddfe9", "#9ebfcb", "#4a738b", "#f5dfbc"),
        ("#efdbd9", "#dfb7c0", "#926f8f", "#f4cfb5"),
        ("#e5e0d3", "#afc6b7", "#667d78", "#faf1d8"),
    ]
    names = ["海边的日落", "山间来信", "夏日庭院", "雨后的街道", "樱花与远山", "静谧森林"]
    for i in range(24):
        palette = palettes[i % len(palettes)]
        w, h = ((540, 720) if i % 3 == 0 else (800, 540))
        image = Image.new("RGB", (w, h), palette[0])
        draw = ImageDraw.Draw(image)
        draw.ellipse((w * 0.6, h * 0.12, w * 0.83, h * 0.12 + w * 0.23), fill=palette[3])
        draw.polygon([(0, h * .7), (w * .32, h * .32), (w * .67, h * .77), (w * .85, h * .45), (w, h * .67), (w, h), (0, h)], fill=palette[1])
        draw.polygon([(0, h * .84), (w * .23, h * .67), (w * .51, h * .91), (w, h * .63), (w, h), (0, h)], fill=palette[2])
        image.save(source / f"{i + 1:02}_{names[i % len(names)]}.jpg", quality=90)
    frames = [Image.new("RGB", (400, 400), color) for color in ("#b5b8d6", "#afc6b7", "#f4b798")]
    frames[0].save(source / "25_色彩练习.gif", save_all=True, append_images=frames[1:], duration=500, loop=0)
    catalogue = Catalogue(base / "data", base / "library")
    catalogue.import_paths([source], "reference")
    groups = {group["name"]: group["id"] for group in catalogue.groups()}
    artist = catalogue.create_tag("画师示例", groups["画师"])
    sea = catalogue.create_tag("海边", groups["场景"])
    mountains = catalogue.create_tag("远山", groups["场景"])
    character = catalogue.create_tag("角色示例", groups["角色"])
    for index, row in enumerate(catalogue.rows()):
        catalogue.apply_tag([row["id"]], artist)
        if index % 2:
            catalogue.apply_tag([row["id"]], mountains)
        if index % 3 == 0:
            catalogue.apply_tag([row["id"]], sea)
        if index % 5 == 0:
            catalogue.apply_tag([row["id"]], character)
    app = App(catalogue, auto_scan=False)
    app.auto_sync.set(False)
    app.after(300, lambda: (app.gallery.selected.add(app.all_rows[1]["id"]), app.selection_changed(), app.gallery.request_redraw()))
    app.mainloop()


if __name__ == "__main__":
    main()
