"""Image-derived accent candidates and a separate custom-background palette."""
from __future__ import annotations

import colorsys
import math
from PIL import Image, ImageOps

from .appearance import PALETTES


def rgb(value):
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def hex_color(value):
    return "#" + "".join(f"{max(0, min(255, round(channel))):02x}" for channel in value)


def mix(a, b, amount):
    return hex_color(tuple(x * (1 - amount) + y * amount for x, y in zip(rgb(a), rgb(b))))


def luminance(value):
    channels = [x / 255 for x in rgb(value)]
    linear = [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in channels]
    return sum(x * weight for x, weight in zip(linear, (.2126, .7152, .0722)))


def contrast(a, b):
    x, y = sorted((luminance(a), luminance(b)))
    return (y + .05) / (x + .05)


def lab(color):
    channels = [x / 255 for x in color]
    r, g, b = [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in channels]
    xyz = ((.4124564 * r + .3575761 * g + .1804375 * b) / .95047,
           .2126729 * r + .7151522 * g + .072175 * b,
           (.0193339 * r + .119192 * g + .9503041 * b) / 1.08883)
    x, y, z = [v ** (1 / 3) if v > .008856 else 7.787 * v + 16 / 116 for v in xyz]
    return (116 * y - 16, 500 * (x - y), 200 * (y - z))


def image_accents(path):
    """Monet-style suggestions: weighted image hues, separated perceptually.

    This is image palette extraction, not an implementation of Material HCT.
    Four seed suggestions are used by the independent custom-background theme.
    """
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((160, 160))
        quantized = image.quantize(colors=24, method=Image.Quantize.MEDIANCUT)
        palette = quantized.getpalette()
        candidates = []
        for count, index in quantized.getcolors():
            color = palette[index * 3:index * 3 + 3]
            h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in color))
            candidate = hex_color(x * 255 for x in colorsys.hsv_to_rgb(h, max(.25, min(.7, s)), max(.42, min(.74, v))))
            candidates.append((count * (.2 + s), candidate))
    chosen = []
    for _, candidate in sorted(candidates, reverse=True):
        point = lab(rgb(candidate))
        if all(math.dist(point, lab(rgb(other))) > 22 for other in chosen):
            chosen.append(candidate)
        if len(chosen) == 4:
            break
    hue = colorsys.rgb_to_hsv(*(x / 255 for x in rgb(chosen[0])))[0] if chosen else .65
    for rotation in (.08, -.08, .16, -.16, .25, .5):
        candidate = hex_color(x * 255 for x in colorsys.hsv_to_rgb((hue + rotation) % 1, .45, .65))
        if candidate not in chosen:
            chosen.append(candidate)
        if len(chosen) == 4:
            break
    return chosen[:4]


def custom_palette(accent, theme="白色"):
    result = PALETTES[theme].copy()
    if theme == "黑色":
        result.update(ACCENT=accent, SELECT=mix(result["PANEL"], accent, .24),
                      ROW_SELECT=mix(result["PANEL"], accent, .46),
                      ROW_SELECT_INK="#ffffff", HOVER=mix(result["PANEL"], accent, .32),
                      PRIMARY_INK="#ffffff" if contrast(accent, "#ffffff") >= contrast(accent, "#000000") else "#000000")
        readable = accent
        for _ in range(50):
            if contrast(readable, result["PANEL"]) >= 4.5:
                break
            readable = mix(readable, "#ffffff", .08)
        result["ACCENT_INK"] = readable
        result["ROW_SELECT_INK"] = max(("#ffffff", "#000000"), key=lambda c: contrast(c, result["ROW_SELECT"]))
        return result
    ink = "#202b40"
    result.update(BG=mix("#f3f5fa", accent, .07), PANEL=mix("#ffffff", accent, .035),
                  SURFACE=mix("#f5f6fa", accent, .07), LINE=mix("#e2e7f1", accent, .18),
                  ACCENT=accent, SELECT=mix("#ffffff", accent, .16),
                  ROW_SELECT=mix("#ffffff", accent, .35), ROW_SELECT_INK=ink,
                  HOVER=mix("#ffffff", accent, .24),
                  PRIMARY_INK="#ffffff" if contrast(accent, "#ffffff") >= contrast(accent, "#000000") else "#000000")
    readable = accent
    for _ in range(30):
        if contrast(readable, result["PANEL"]) >= 4.5:
            break
        readable = mix(readable, "#000000", .08)
    result["ACCENT_INK"] = readable
    return result
