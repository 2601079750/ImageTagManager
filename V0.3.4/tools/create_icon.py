"""Render the original Shitu mascot artwork; requires only Pillow."""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw


def main():
    target = Path(__file__).resolve().parents[1] / "assets"
    target.mkdir(exist_ok=True)
    scale = 4
    canvas = Image.new("RGBA", (512 * scale, 512 * scale))
    draw = ImageDraw.Draw(canvas)
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 512 512">',
           '<defs><linearGradient id="bg" x2="0" y2="1"><stop stop-color="#8070dd"/><stop offset="1" stop-color="#403479"/></linearGradient></defs>']

    def path(data, fill, stroke=None, width=4):
        tokens = re.findall(r"[MLCQZ]|-?\d+(?:\.\d+)?", data)
        points = []
        cursor = (0, 0)
        index = 0
        while index < len(tokens):
            command = tokens[index]
            index += 1
            count = {"M": 2, "L": 2, "C": 6, "Q": 4, "Z": 0}[command]
            values = [float(v) for v in tokens[index:index + count]]
            index += count
            if command in ("M", "L"):
                cursor = tuple(values)
                points.append(cursor)
            elif command in ("C", "Q"):
                origin = cursor
                for step in range(1, 33):
                    t = step / 32
                    u = 1 - t
                    if command == "C":
                        point = tuple(u**3 * origin[d] + 3 * u*u*t * values[d]
                                      + 3 * u*t*t * values[d+2] + t**3 * values[d+4] for d in (0, 1))
                    else:
                        point = tuple(u*u * origin[d] + 2*u*t * values[d] + t*t * values[d+2] for d in (0, 1))
                    points.append(point)
                cursor = point
            elif command == "Z":
                points.append(points[0])
        scaled = [(round(x * scale), round(y * scale)) for x, y in points]
        if fill:
            draw.polygon(scaled, fill=fill)
        if stroke:
            draw.line(scaled, fill=stroke, width=round(width * scale), joint="curve")
        svg.append(f'<path d="{data}" fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>')

    def ellipse(box, fill):
        draw.ellipse(tuple(round(v * scale) for v in box), fill=fill)
        x0, y0, x1, y1 = box
        svg.append(f'<ellipse cx="{(x0+x1)/2}" cy="{(y0+y1)/2}" rx="{(x1-x0)/2}" ry="{(y1-y0)/2}" fill="{fill}"/>')

    def rounded(box, radius, fill):
        draw.rounded_rectangle(tuple(v*scale for v in box), radius*scale, fill=fill)
        x0, y0, x1, y1 = box
        svg.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" rx="{radius}" fill="{fill}"/>')

    # A transparent outer margin and a gently shaded, rounded application tile.
    rounded((20, 20, 492, 492), 110, "#6555b2")
    mask = canvas.getchannel("A")
    gradient = Image.new("RGBA", canvas.size)
    gd = ImageDraw.Draw(gradient)
    for y in range(512 * scale):
        t = min(1, max(0, y / (512 * scale)))
        color = tuple(round(a*(1-t)+b*t) for a, b in zip((128, 112, 221), (64, 52, 121)))
        gd.line((0, y, 512*scale, y), fill=(*color, 255))
    canvas.paste(gradient, (0, 0), mask)
    svg[-1] = svg[-1].replace('fill="#6555b2"', 'fill="url(#bg)"')
    draw = ImageDraw.Draw(canvas)

    # Offset photo sheet behind the mascot's portrait card.
    path("M 99 118 L 343 79 Q 365 75 369 98 L 411 362 Q 415 384 392 388 L 148 427 Q 125 431 121 408 L 79 144 Q 75 122 99 118 Z", "#b4aceb")
    rounded((103, 112, 407, 428), 38, "#35285f")
    rounded((96, 100, 400, 416), 38, "#fcf7ff")
    rounded((112, 116, 384, 374), 26, "#dedbff")

    # Original cat-eared anime mascot, drawn with broad, readable shapes.
    ink = "#453260"
    path("M 143 239 C 122 202 126 143 139 124 Q 166 128 197 160 C 225 143 271 142 302 162 Q 329 130 355 129 C 371 162 372 208 355 240 L 367 326 Q 365 353 335 363 L 157 363 Q 126 348 131 325 Z", "#b4a2f2", ink, 6)
    path("M 146 143 Q 169 152 181 169 L 149 190 Z", "#f5bdcf")
    path("M 344 149 Q 326 157 315 172 L 349 195 Z", "#f5bdcf")
    path("M 167 215 Q 245 181 326 219 L 329 277 C 329 321 295 346 248 346 C 202 346 168 321 166 279 Z", "#ffeadf", ink, 5)
    # Face-framing hair and asymmetric bangs.
    path("M 145 237 C 146 180 181 156 238 158 C 302 150 352 183 353 238 L 334 295 L 321 246 L 300 218 L 306 246 Q 271 229 253 198 Q 254 229 225 249 L 228 222 Q 200 248 173 254 L 166 298 Z", "#beacf6", ink, 5)
    path("M 173 205 Q 191 177 219 178", None, "#e9dfff", 8)
    path("M 270 175 Q 304 177 324 199", None, "#e9dfff", 7)
    # Large anime eyes, simplified to survive icon downsampling.
    path("M 180 263 Q 194 249 213 260 L 212 281 Q 198 294 184 281 Z", "#ffffff")
    path("M 279 260 Q 299 249 313 264 L 309 283 Q 293 295 281 280 Z", "#ffffff")
    ellipse((190, 257, 212, 286), "#655197")
    ellipse((282, 257, 304, 286), "#655197")
    ellipse((194, 263, 209, 282), "#79d5c7")
    ellipse((285, 263, 300, 282), "#79d5c7")
    ellipse((197, 259, 207, 270), "#ffffff")
    ellipse((288, 259, 298, 270), "#ffffff")
    path("M 179 261 Q 194 249 214 259", None, ink, 6)
    path("M 279 259 Q 298 249 314 262", None, ink, 6)
    ellipse((177, 290, 204, 302), "#f3b5c3")
    ellipse((290, 290, 317, 302), "#f3b5c3")
    path("M 237 308 Q 247 319 258 308", None, "#985d7c", 4)
    path("M 151 255 Q 139 308 150 334 L 175 343 L 164 318 Z", "#9d87df")
    path("M 343 255 Q 356 308 345 333 L 323 344 L 333 314 Z", "#9d87df")
    # Clothing reads as a small ribbon under the face, within the portrait.
    path("M 183 370 Q 195 341 220 337 L 248 355 L 277 337 Q 303 341 316 370 Z", "#665193")
    path("M 212 348 L 239 357 L 230 375 L 211 369 Z", "#9cdddb")
    path("M 283 348 L 256 357 L 265 375 L 285 369 Z", "#9cdddb")
    ellipse((237, 351, 257, 371), "#dcfcf5")
    rounded((125, 389, 205, 397), 4, "#c2b6dc")

    # A large tag ties the mascot to the app's purpose, rather than generic art.
    path("M 353 315 Q 359 308 369 312 L 430 340 Q 440 345 436 357 L 405 429 Q 400 440 388 435 L 327 408 Q 318 404 319 394 L 324 347 Z", "#302454")
    path("M 354 302 Q 362 295 371 300 L 436 331 Q 446 336 441 347 L 408 419 Q 403 430 392 425 L 327 394 Q 318 390 320 379 L 326 333 Z", "#a5eee0", ink, 5)
    ellipse((344, 321, 362, 339), "#514078")
    path("M 353 358 L 368 376 L 400 359", None, "#386f73", 9)
    path("M 417 164 Q 420 183 437 187 Q 420 190 417 209 Q 413 190 397 187 Q 413 183 417 164 Z", "#e5fff7")
    ellipse((87, 304, 97, 314), "#c3b6f5")

    svg.append("</svg>")
    (target / "app-icon.svg").write_text("\n".join(svg) + "\n", encoding="utf-8")
    icon = canvas.resize((1024, 1024), Image.Resampling.LANCZOS)
    icon.save(target / "app-icon.png", optimize=True)
    icon.save(target / "app-icon.ico", sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    print(f"Saved original vector artwork, PNG and multi-size ICO in {target}")


if __name__ == "__main__":
    main()
