"""Background geometry and theme readability, independent of native rendering."""
import unittest
from PIL import Image

from imagetag.backdrop import compose_background
from imagetag.colors import custom_palette, contrast
from imagetag.colors import hex_color
from imagetag.glass import readable_panel, readable_text_surface


class BackdropTests(unittest.TestCase):
    def setUp(self):
        self.wide = Image.new("RGB", (200, 100), "red")

    def test_cover_crops_without_empty_edges(self):
        image = compose_background(self.wide, (100, 100), "覆盖", "#000000", 100)
        self.assertEqual(image.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(image.getpixel((99, 99)), (255, 0, 0))

    def test_fill_preserves_aspect_and_centers(self):
        image = compose_background(self.wide, (100, 100), "填充", "#000000", 100)
        self.assertEqual(image.getpixel((50, 24)), (0, 0, 0))
        self.assertEqual(image.getpixel((50, 25)), (255, 0, 0))
        self.assertEqual(image.getpixel((50, 75)), (0, 0, 0))

    def test_center_preserves_original_pixel_size(self):
        source = Image.new("RGB", (20, 10), "red")
        image = compose_background(source, (100, 100), "居中", "#000000", 100)
        self.assertEqual(image.getpixel((39, 50)), (0, 0, 0))
        self.assertEqual(image.getpixel((40, 50)), (255, 0, 0))
        self.assertEqual(image.getpixel((60, 50)), (0, 0, 0))

    def test_stretch_fills_both_axes(self):
        image = compose_background(self.wide, (100, 100), "拉伸", "#000000", 100)
        self.assertEqual(image.getpixel((50, 0)), (255, 0, 0))

    def test_free_scale_and_offsets_are_effective(self):
        image = compose_background(self.wide, (100, 100), "自由", "#000000", 100, 50, 20, 10)
        self.assertEqual(image.getpixel((44, 60)), (0, 0, 0))
        self.assertEqual(image.getpixel((45, 60)), (255, 0, 0))
        self.assertEqual(image.getpixel((50, 46)), (0, 0, 0))

    def test_zero_opacity_retains_base(self):
        image = compose_background(self.wide, (100, 100), opacity=0, base="#112233")
        self.assertEqual(image.getpixel((20, 20)), (17, 34, 51))

    def test_custom_color_is_readable_in_both_themes(self):
        for theme in ("白色", "黑色"):
            for seed in ("#000000", "#ffffff", "#ff0000", "#00ff00", "#0000ff", "#777777"):
                palette = custom_palette(seed, theme)
                self.assertEqual(palette["ACCENT"], seed)
                self.assertGreaterEqual(contrast(palette["ACCENT_INK"], palette["PANEL"]), 4.5)
                self.assertGreaterEqual(contrast(seed, palette["PRIMARY_INK"]), 4.5)

    def test_translucent_panel_text_contrast_over_dark_bright_and_patterned_images(self):
        image = Image.new("RGB", (8, 8))
        colors = ("#000000", "#ffffff", "#ff0000", "#00ff00", "#0000ff", "#808080", "#00ffff", "#ff00ff")
        for x, color in enumerate(colors):
            for y in range(8):
                image.putpixel((x, y), tuple(bytes.fromhex(color[1:])))
        for ink in ("#202b40", "#40516a"):
            result = readable_panel(image, ink)
            pixels = [result.getpixel((x, y)) for x in range(8) for y in range(8)]
            self.assertGreater(len(set(pixels)), 1, "Backdrop details should remain visible")
            for pixel in pixels:
                self.assertGreaterEqual(contrast(ink, hex_color(pixel)), 4.5)
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 0), "Must not modify the wallpaper")

    def test_readable_labels_keep_unmodified_background_when_contrast_is_sufficient(self):
        source = Image.new("RGB", (12, 12), "#ddeeff")
        self.assertEqual(readable_panel(source, "#40516a", opacity=0).tobytes(), source.tobytes())

    def test_labels_use_light_text_on_dark_background_without_a_grey_box(self):
        source = Image.new("RGB", (8, 8), "#090e18")
        result, ink = readable_text_surface(source, "#40516a")
        self.assertEqual(ink, "#ffffff")
        self.assertEqual(result.tobytes(), source.tobytes())
        self.assertGreaterEqual(contrast(ink, "#090e18"), 4.5)

    def test_adaptive_text_stays_readable_over_mixed_and_flat_backgrounds(self):
        for colors in (("#000000", "#ffffff"), ("#ff0000", "#0038aa"), ("#f8faff", "#ffffff")):
            source = Image.new("RGB", (2, 1))
            for x, color in enumerate(colors):
                source.putpixel((x, 0), tuple(bytes.fromhex(color[1:])))
            for preferred in ("#202b40", "#40516a", "#ffffff"):
                result, ink = readable_text_surface(source, preferred)
                for x in range(2):
                    self.assertGreaterEqual(contrast(ink, hex_color(result.getpixel((x, 0)))), 4.5)


if __name__ == "__main__":
    unittest.main()
