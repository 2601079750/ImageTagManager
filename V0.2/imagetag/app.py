from __future__ import annotations

import argparse
import ctypes
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageOps, ImageTk

from . import __version__
from .appearance import ClickCombobox, PALETTES, system_theme
from .core import Catalogue, EXTENSIONS, Report, default_data_folder, filter_images, pictures_folder

globals().update(PALETTES["白色"])
FILE_TYPES = [("图片", " ".join("*" + extension for extension in sorted(EXTENSIONS))), ("所有文件", "*.*")]


def size_label(count: int) -> str:
    if count >= 1024 * 1024:
        return f"{count / (1024 * 1024):.1f} MB"
    return f"{count / 1024:.0f} KB"


def button(parent, text, command, primary=False, **kwargs):
    options = dict(font=("Microsoft YaHei UI", 10), bg=ACCENT if primary else PANEL,
                   fg=PRIMARY_INK if primary else INK, activebackground=HOVER,
                   activeforeground=INK, relief="flat", bd=0,
                   padx=12, pady=8, cursor="hand2")
    options.update(kwargs)
    return tk.Button(parent, text=text, command=command, **options)


def label(parent, text="", color=None, size=10, bold=False, **kwargs):
    return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color or INK,
                    font=("Microsoft YaHei UI", size, "bold" if bold else "normal"), **kwargs)


class Popup(tk.Toplevel):
    def __init__(self, parent, title, geometry="520x420"):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=PANEL)
        width, height = map(int, geometry.split("x"))
        parent.update_idletasks()
        x = max(0, parent.winfo_rootx() + (parent.winfo_width() - width) // 2)
        y = max(0, parent.winfo_rooty() + (parent.winfo_height() - height) // 2)
        self.geometry(f"{geometry}+{x}+{y}")
        self.transient(parent)
        if os.name == "nt":
            self.after_idle(lambda: self.iconbitmap(str(parent._icon_path)) if self.winfo_exists() else None)
        self.bind("<Escape>", lambda _: self.destroy())
        self.after(100, lambda: parent.style_titlebar(self) if self.winfo_exists() else None)


class Gallery(tk.Canvas):
    """Draw just the visible rows; keep a bounded thumbnail cache."""

    CELL_W = 206
    CELL_H = 238

    def __init__(self, parent, app):
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0, takefocus=True)
        self.app = app
        self.rows = []
        self.selected: set[int] = set()
        self.anchor: int | None = None
        self.columns = 1
        self.photos = OrderedDict()
        self.pending = set()
        self.positions = {}
        self.redraw_id = None
        self.hover_id = None
        self.hover_item = None
        self.hover_token = 0
        self.hover_photo = None
        self.hover_layers = {}
        self.tween_due = None
        self.selection_badge = None
        self.badge_color = None
        self.card_photos = OrderedDict()
        self.anim_due = None
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="thumbnail")
        self.anim_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="animation")
        self.anim_image = None
        self.anim_path = None
        self.anim_frame = 0
        self.bind("<Configure>", self.request_redraw)
        self.bind("<MouseWheel>", self.wheel)
        self.bind("<Button-1>", self.click)
        self.bind("<Double-Button-1>", self.open)
        self.bind("<Motion>", self.motion)
        self.bind("<Leave>", lambda _: self.stop_hover())
        self.bind("<Control-a>", self.select_all)
        self.bind("<Return>", lambda _: self.app.preview_selected())
        self.bind("<space>", lambda _: self.app.preview_selected())
        self.bind("<Escape>", self.clear_selection)

    def set_rows(self, rows, reset_scroll=False):
        self.stop_hover()
        self.rows = rows
        self.selected &= {row["id"] for row in rows}
        if reset_scroll:
            self.yview_moveto(0)
        self.request_redraw()

    def scroll(self, *args):
        self.stop_hover()
        self.yview(*args)
        self.request_redraw()

    def wheel(self, event):
        self.scroll("scroll", -int(event.delta / 120) * 2, "units")
        return "break"

    def request_redraw(self, _=None):
        if not self.redraw_id:
            self.redraw_id = self.after_idle(self.redraw)

    def redraw(self):
        self.redraw_id = None
        self.stop_hover(hard=True)
        self.delete("all")
        self.positions.clear()
        width = max(self.winfo_width(), 220)
        self.columns = max(1, (width - 24) // self.CELL_W)
        cell_width = (width - 24) / self.columns
        total_rows = (len(self.rows) + self.columns - 1) // self.columns
        self.configure(scrollregion=(0, 0, width, max(self.winfo_height(), total_rows * self.CELL_H + 24)), yscrollincrement=24)
        top = max(0, int(self.canvasy(0) // self.CELL_H) - 1)
        bottom = min(total_rows, int(self.canvasy(self.winfo_height()) // self.CELL_H) + 2)
        if not self.rows:
            self.create_text(width / 2, max(150, self.winfo_height() / 2 - 35), text="这里还没有图片", fill=INK, font=("Microsoft YaHei UI", 19, "bold"))
            self.create_text(width / 2, max(185, self.winfo_height() / 2), text="导入图片或文件夹，开始整理你的收藏\n也可以清除筛选条件，查看其他图片", fill=MUTED, font=("Microsoft YaHei UI", 10), justify="center")
        for index in range(top * self.columns, min(len(self.rows), bottom * self.columns)):
            row = self.rows[index]
            x = 12 + (index % self.columns) * cell_width
            y = 12 + (index // self.columns) * self.CELL_H
            right = x + cell_width - 12
            self.positions[row["id"]] = (x, y, right, y + self.CELL_H - 12)
            chosen = row["id"] in self.selected
            card_size = (round(right - x), self.CELL_H - 12)
            card_key = (card_size, chosen, PANEL, LINE, ACCENT)
            if card_key not in self.card_photos:
                card = Image.new("RGBA", (card_size[0] * 3, card_size[1] * 3))
                ImageDraw.Draw(card).rounded_rectangle((2, 2, card.width - 3, card.height - 3), radius=27,
                    fill=PANEL, outline=ACCENT if chosen else LINE, width=6 if chosen else 3)
                self.card_photos[card_key] = ImageTk.PhotoImage(card.resize(card_size, Image.Resampling.LANCZOS), master=self)
            self.card_photos.move_to_end(card_key)
            self.create_image(x, y, image=self.card_photos[card_key], anchor="nw")
            while len(self.card_photos) > 12:
                self.card_photos.popitem(last=False)
            self.create_rectangle(x + 7, y + 7, right - 7, y + 171, fill=SURFACE, outline="")
            key = row["sha256"]
            photo = self.photos.get(key)
            if photo:
                self.photos.move_to_end(key)
                self.create_image((x + right) / 2, y + 89, image=photo)
            elif key not in self.pending:
                self.pending.add(key)
                self.pool.submit(self.load_thumb, key)
            if row["missing"]:
                self.create_rectangle(x + 10, y + 10, x + 88, y + 32, fill=WARNING, outline="")
                self.create_text(x + 49, y + 21, text="原图缺失", fill=WARNING_INK, font=("Microsoft YaHei UI", 9))
            elif row["animated"]:
                self.create_rectangle(x + 10, y + 10, x + 55, y + 32, fill=ACCENT, outline="")
                self.create_text(x + 33, y + 21, text="动图", fill=PRIMARY_INK, font=("Microsoft YaHei UI", 9))
            if chosen:
                if self.badge_color != ACCENT:
                    badge = Image.new("RGBA", (96, 96))
                    draw = ImageDraw.Draw(badge)
                    draw.ellipse((4, 4, 91, 91), fill=ACCENT, outline=PANEL, width=6)
                    draw.line([(27, 48), (42, 63), (69, 34)], fill=PRIMARY_INK, width=8, joint="curve")
                    for px, py in ((27, 48), (42, 63), (69, 34)):
                        draw.ellipse((px-4, py-4, px+4, py+4), fill=PRIMARY_INK)
                    self.selection_badge = ImageTk.PhotoImage(badge.resize((24, 24), Image.Resampling.LANCZOS), master=self)
                    self.badge_color = ACCENT
                self.create_image(right - 20, y + 20, image=self.selection_badge, tags="badge")
            filename = row["filename"]
            chars = max(13, int((right - x - 20) / 8))
            if len(filename) > chars:
                filename = filename[:chars - 2] + "…"
            self.create_text(x + 10, y + 186, text=filename, anchor="w", fill=INK, font=("Microsoft YaHei UI", 10))
            self.create_text(x + 10, y + 209, text=f"{row['width']} × {row['height']}  ·  {size_label(row['bytes'])}", anchor="w", fill=MUTED, font=("Segoe UI", 9))
            if row["tags"]:
                self.create_text(right - 10, y + 209, text=f"{len(row['tags'])} 标签", anchor="e", fill=ACCENT, font=("Microsoft YaHei UI", 8))

    def load_thumb(self, digest):
        try:
            with Image.open(self.app.catalogue.thumb_path(digest)) as image:
                photo = image.copy()
                photo.thumbnail((173, 156), Image.Resampling.LANCZOS)
            self.app.events.put(("thumb", digest, photo))
        except OSError:
            self.app.events.put(("thumb", digest, None))

    def receive_thumb(self, digest, image):
        self.pending.discard(digest)
        if image:
            self.photos[digest] = ImageTk.PhotoImage(image, master=self)
            while len(self.photos) > 180:
                self.photos.popitem(last=False)
            self.request_redraw()

    def at(self, event):
        x, y = self.canvasx(event.x), self.canvasy(event.y)
        for image_id, (left, top, right, bottom) in self.positions.items():
            if left <= x <= right and top <= y <= bottom:
                return image_id
        return None

    def click(self, event):
        self.focus_set()
        image_id = self.at(event)
        if image_id is None:
            self.selected.clear()
        elif event.state & 0x1 and self.anchor is not None:
            ids = [row["id"] for row in self.rows]
            if self.anchor in ids:
                start, end = sorted((ids.index(self.anchor), ids.index(image_id)))
                self.selected.update(ids[start:end + 1])
        elif event.state & 0x4:
            self.selected.symmetric_difference_update({image_id})
            self.anchor = image_id
        else:
            self.selected = {image_id}
            self.anchor = image_id
        self.request_redraw()
        self.app.selection_changed()

    def clear_selection(self, _=None):
        self.selected.clear()
        self.request_redraw()
        self.app.selection_changed()

    def select_all(self, _=None):
        self.selected = {row["id"] for row in self.rows}
        self.request_redraw()
        self.app.selection_changed()
        return "break"

    def open(self, event):
        image_id = self.at(event)
        if image_id:
            self.app.preview(image_id)

    def motion(self, event):
        image_id = self.at(event)
        if image_id != self.hover_id:
            self.stop_hover()
            self.hover_id = image_id
            if image_id:
                self.anim_due = self.after(220, self.start_hover)

    def stop_hover(self, hard=False):
        had_hover = self.hover_id is not None
        if self.anim_due:
            self.after_cancel(self.anim_due)
            self.anim_due = None
        if hard:
            if self.tween_due:
                self.after_cancel(self.tween_due)
                self.tween_due = None
            for layer in self.hover_layers.values():
                self.delete(layer["item"])
            self.hover_layers.clear()
        elif self.hover_id in self.hover_layers:
            self.retarget_hover(self.hover_id, 0.0)
        self.hover_item = None
        self.hover_id = None
        self.hover_token += 1
        self.hover_photo = None
        if had_hover:
            self.anim_pool.submit(self.close_animation)

    def close_animation(self):
        if self.anim_image:
            self.anim_image.close()
        self.anim_image = None
        self.anim_path = None

    def start_hover(self):
        self.anim_due = None
        row = next((r for r in self.rows if r["id"] == self.hover_id), None)
        if not row or row["id"] not in self.positions:
            return
        token = self.hover_token
        self.anim_pool.submit(self.decode_hover, row, token, True)

    def decode_hover(self, row, token, first):
        try:
            if row["animated"] and not row["missing"]:
                if first or self.anim_path != row["path"]:
                    if self.anim_image:
                        self.anim_image.close()
                    self.anim_image = Image.open(row["path"])
                    self.anim_path = row["path"]
                    self.anim_frame = 0
                else:
                    self.anim_frame += 1
                    try:
                        self.anim_image.seek(self.anim_frame)
                    except EOFError:
                        self.anim_frame = 0
                        self.anim_image.seek(0)
                image = self.anim_image.convert("RGBA")
                duration = max(30, min(int(self.anim_image.info.get("duration", 100)), 10000))
            else:
                with Image.open(self.app.catalogue.thumb_path(row["sha256"])) as source:
                    image = source.convert("RGBA")
                duration = 0
            image.thumbnail((187, 169), Image.Resampling.LANCZOS)
            self.app.events.put(("hover", token, row["id"], image, duration))
        except (OSError, ValueError, Image.DecompressionBombError):
            pass

    def receive_hover(self, token, image_id, image, duration):
        if token != self.hover_token or image_id != self.hover_id or image_id not in self.positions:
            return
        layer = self.hover_layers.get(image_id)
        if layer is None:
            x, y, right, _ = self.positions[image_id]
            layer = dict(item=self.create_image((x + right) / 2, y + 89), scale=0.0,
                         start=0.0, target=1.0, began=time.monotonic(), photo=None)
            self.hover_layers[image_id] = layer
        layer["source"] = image
        self.retarget_hover(image_id, 1.0)
        self.paint_hover(layer)
        self.tag_raise("badge")
        if duration:
            row = next((r for r in self.rows if r["id"] == image_id), None)
            self.anim_due = self.after(duration, lambda: self.next_hover(row, token))

    def retarget_hover(self, image_id, target):
        layer = self.hover_layers[image_id]
        if layer["target"] != target:
            layer.update(start=layer["scale"], target=target, began=time.monotonic())
        if self.tween_due is None:
            self.tween_due = self.after(16, self.tick_hover)

    def paint_hover(self, layer):
        source = layer["source"]
        factor = 173 / 187 + (1 - 173 / 187) * layer["scale"]
        size = tuple(max(1, round(n * factor)) for n in source.size)
        layer["photo"] = ImageTk.PhotoImage(source.resize(size, Image.Resampling.LANCZOS), master=self)
        self.itemconfigure(layer["item"], image=layer["photo"])

    def tick_hover(self):
        self.tween_due = None
        pending = False
        for image_id, layer in list(self.hover_layers.items()):
            progress = min(1.0, (time.monotonic() - layer["began"]) / 0.18)
            eased = 1 - (1 - progress) ** 3
            layer["scale"] = layer["start"] + (layer["target"] - layer["start"]) * eased
            if progress == 1 and layer["target"] == 0:
                self.delete(layer["item"])
                del self.hover_layers[image_id]
            else:
                self.paint_hover(layer)
                pending |= progress < 1
        if pending:
            self.tween_due = self.after(16, self.tick_hover)

    def next_hover(self, row, token):
        self.anim_due = None
        if token == self.hover_token and row:
            self.anim_pool.submit(self.decode_hover, row, token, False)

    def shutdown(self):
        self.stop_hover(hard=True)
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.anim_pool.shutdown(wait=False, cancel_futures=False)


class Preview(Popup):
    def __init__(self, app, image_id):
        super().__init__(app, "图片预览", "1050x780")
        self.app = app
        self.ids = [row["id"] for row in app.filtered]
        self.image_id = image_id
        self.image = None
        self.scale = 1.0
        self.fit = True
        self.photo = None
        self.timer = None
        self.playing = False
        self.frame_index = 0
        toolbar = tk.Frame(self, bg=PANEL)
        toolbar.pack(fill="x", padx=12, pady=8)
        for text, command in [("‹ 上一张", lambda: self.navigate(-1)), ("下一张 ›", lambda: self.navigate(1)),
                              ("适应窗口", self.fit_window), ("1:1", self.actual),
                              ("−", lambda: self.zoom(0.8)), ("＋", lambda: self.zoom(1.25)),
                              ("播放 / 暂停", self.toggle_play)]:
            button(toolbar, text, command).pack(side="left", padx=2)
        self.info = label(toolbar, color=MUTED, size=9)
        self.info.pack(side="right")
        area = tk.Frame(self, bg=INK)
        area.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(area, bg="#202635", highlightthickness=0)
        horizontal = ttk.Scrollbar(area, orient="horizontal", command=self.canvas.xview)
        vertical = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.canvas.bind("<Configure>", lambda _: self.render())
        self.canvas.bind("<MouseWheel>", lambda event: self.zoom(1.2 if event.delta > 0 else 1 / 1.2))
        self.canvas.bind("<ButtonPress-1>", lambda event: self.canvas.scan_mark(event.x, event.y))
        self.canvas.bind("<B1-Motion>", lambda event: self.canvas.scan_dragto(event.x, event.y, gain=1))
        self.bind("<Left>", lambda _: self.navigate(-1))
        self.bind("<Right>", lambda _: self.navigate(1))
        self.bind("<space>", lambda _: self.toggle_play())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.load(image_id)

    def load(self, image_id):
        self.stop()
        self.image_id = image_id
        self.frame_index = 0
        if self.image:
            self.image.close()
            self.image = None
        row = next((r for r in self.app.all_rows if r["id"] == image_id), None)
        if not row:
            return
        self.title(row["filename"] + " — 图片预览")
        try:
            self.image = Image.open(row["path"])
            self.fit = True
            self.render()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            self.canvas.delete("all")
            self.canvas.create_text(400, 240, text="原图暂不可用，请先重新关联\n" + str(exc)[:100], fill="white", font=("Microsoft YaHei UI", 13))

    def render(self):
        if not self.image:
            return
        width, height = max(self.canvas.winfo_width(), 100), max(self.canvas.winfo_height(), 100)
        try:
            frame = ImageOps.exif_transpose(self.image).convert("RGBA")
            if self.fit:
                self.scale = min((width - 20) / frame.width, (height - 20) / frame.height, 1.0)
            # Bound the rendered surface, including at large manual zoom values.
            scale = min(self.scale, 8192 / max(frame.size), (24000000 / (frame.width * frame.height)) ** 0.5)
            target = (max(1, int(frame.width * scale)), max(1, int(frame.height * scale)))
            frame = frame.resize(target, Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(frame, master=self)
            self.canvas.delete("all")
            total_w, total_h = max(width, target[0]), max(height, target[1])
            self.canvas.create_image(total_w / 2, total_h / 2, image=self.photo)
            self.canvas.configure(scrollregion=(0, 0, total_w, total_h))
            self.info.configure(text=f"{self.image.width} × {self.image.height}  ·  {scale:.0%}")
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            logging.exception("Preview failed")
            self.stop()
            self.info.configure(text="预览失败：" + str(exc)[:50])

    def zoom(self, factor):
        self.fit = False
        self.scale = max(0.02, min(8.0, self.scale * factor))
        self.render()

    def fit_window(self):
        self.fit = True
        self.render()

    def actual(self):
        self.fit = False
        self.scale = 1.0
        self.render()

    def navigate(self, direction):
        if self.image_id in self.ids and self.ids:
            self.load(self.ids[(self.ids.index(self.image_id) + direction) % len(self.ids)])

    def stop(self):
        self.playing = False
        if self.timer:
            self.after_cancel(self.timer)
            self.timer = None

    def toggle_play(self):
        if self.playing:
            self.stop()
        elif self.image and getattr(self.image, "is_animated", False) and self.image.format != "TIFF":
            self.playing = True
            self.advance()

    def advance(self):
        self.timer = None
        if not self.playing or not self.image:
            return
        try:
            self.frame_index += 1
            try:
                self.image.seek(self.frame_index)
            except EOFError:
                self.frame_index = 0
                self.image.seek(0)
            self.render()
            self.timer = self.after(max(30, min(int(self.image.info.get("duration", 100)), 10000)), self.advance)
        except (OSError, ValueError):
            self.stop()

    def destroy(self):
        self.stop()
        if self.image:
            self.image.close()
            self.image = None
        super().destroy()


class TagManager(Popup):
    def __init__(self, app):
        super().__init__(app, "标签管理", "860x640")
        self.app = app
        self.minsize(740, 540)
        label(self, "整理你的标签", size=20, bold=True).pack(anchor="w", padx=24, pady=(22, 4))
        label(self, "修改会同步到所有图片，原图文件保持不变。", color=MUTED).pack(anchor="w", padx=24, pady=(0, 15))
        notebook = ttk.Notebook(self)
        self.notebook = notebook
        notebook.pack(fill="both", expand=True, padx=22, pady=(0, 20))
        tags_page = tk.Frame(notebook, bg=PANEL)
        categories_page = tk.Frame(notebook, bg=PANEL)
        notebook.add(tags_page, text="标签管理")
        notebook.add(categories_page, text="标签类别")
        tags_footer = tk.Frame(tags_page, bg=PANEL)
        tags_footer.pack(side="bottom", fill="x")
        categories_footer = tk.Frame(categories_page, bg=PANEL)
        categories_footer.pack(side="bottom", fill="x")
        self.query = tk.StringVar()
        label(tags_page, "搜索标签 / 分类", color=MUTED, size=9).pack(anchor="w", pady=(14, 5))
        ttk.Entry(tags_page, textvariable=self.query).pack(fill="x", pady=(0, 10))
        self.tag_tree = self.table(tags_page, ("category", "count"), ("类别", "图片数"))
        self.query.trace_add("write", lambda *_: self.refresh_tags())
        moves = tk.Frame(tags_footer, bg=PANEL)
        moves.pack(fill="x", pady=12)
        label(moves, "目标类别").pack(side="left", padx=(0, 10))
        self.destination = tk.StringVar()
        self.move_combo = ClickCombobox(moves, textvariable=self.destination, state="readonly", width=20)
        self.move_combo.pack(side="left", fill="x", expand=True)
        button(moves, "移动所选标签", self.move_selected).pack(side="left", padx=(10, 0))
        controls = tk.Frame(tags_footer, bg=PANEL)
        controls.pack(fill="x", pady=(0, 12))
        button(controls, "新增标签", self.add_tag, True).pack(side="left")
        button(controls, "重命名", self.rename_tag).pack(side="left", padx=8)
        button(controls, "删除标签…", self.delete_selected_tags).pack(side="right")
        label(categories_page, "类别可自由创建、重命名或删除，初始类别也可删除。", color=MUTED, size=9).pack(anchor="w", pady=(14, 10))
        self.category_tree = self.table(categories_page, ("count",), ("标签数",), multiple=False)
        category_moves = tk.Frame(categories_footer, bg=PANEL)
        category_moves.pack(fill="x", pady=(12, 6))
        label(category_moves, "删除时将标签转移到", size=9).pack(side="left", padx=(0, 10))
        self.category_target = tk.StringVar()
        self.category_combo = ClickCombobox(category_moves, textvariable=self.category_target, state="readonly", width=20)
        self.category_combo.pack(side="left", fill="x", expand=True)
        label(categories_footer, "空类别可直接删除；非空类别需选择其他类别。目标有同名标签时会取消操作。", color=MUTED, size=9).pack(anchor="w", pady=(0, 10))
        controls = tk.Frame(categories_footer, bg=PANEL)
        controls.pack(fill="x", pady=(0, 12))
        button(controls, "新增类别", self.add_category, True).pack(side="left")
        button(controls, "重命名", self.rename_category).pack(side="left", padx=8)
        button(controls, "删除类别…", self.delete_category).pack(side="right")
        self.refresh()

    @staticmethod
    def table(parent, columns, titles, multiple=True):
        area = tk.Frame(parent, bg=PANEL)
        area.pack(fill="both", expand=True)
        tree = ttk.Treeview(area, columns=columns, show="tree headings", height=5,
                           selectmode="extended" if multiple else "browse")
        tree.heading("#0", text="标签" if multiple else "类别")
        tree.column("#0", width=280, minwidth=170)
        for column, title in zip(columns, titles):
            tree.heading(column, text=title)
            tree.column(column, width=120, minwidth=70, anchor="center")
        scroll = ttk.Scrollbar(area, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return tree

    def refresh_tags(self):
        selected = set(self.tag_tree.selection())
        self.tag_tree.delete(*self.tag_tree.get_children())
        query = self.query.get().strip().casefold()
        for tag in self.app.catalogue.tags():
            if query in (tag["group_name"] + tag["name"]).casefold():
                self.tag_tree.insert("", "end", iid=str(tag["id"]), text=tag["name"], values=(tag["group_name"], tag["count"]))
        self.tag_tree.selection_set(tuple(selected & set(self.tag_tree.get_children())))

    def refresh(self):
        self.groups = self.app.catalogue.groups()
        tags = self.app.catalogue.tags()
        self.refresh_tags()
        selected = self.category_tree.selection()
        self.category_tree.delete(*self.category_tree.get_children())
        for group in self.groups:
            self.category_tree.insert("", "end", iid=str(group["id"]), text=group["name"],
                                      values=(sum(t["group_id"] == group["id"] for t in tags),))
        self.category_tree.selection_set(tuple(set(selected) & set(self.category_tree.get_children())))
        names = [g["name"] for g in self.groups]
        for combo, variable in ((self.move_combo, self.destination), (self.category_combo, self.category_target)):
            combo["values"] = names
            if variable.get() not in names:
                variable.set("")

    def perform(self, operation):
        if not self.app.editable():
            return
        try:
            operation()
            self.app.reload()
            self.refresh()
        except (ValueError, OSError) as exc:
            messagebox.showerror("未完成", str(exc), parent=self)

    def target_id(self, variable):
        group = next((g for g in self.groups if g["name"] == variable.get()), None)
        if group is None:
            raise ValueError("请先选择目标类别。")
        return group["id"]

    def require_tags(self, one=False):
        tags = self.tag_tree.selection()
        if not tags or (one and len(tags) != 1):
            messagebox.showinfo("选择标签", "请选择一个标签。" if one else "请选择一个或多个标签（Ctrl / Shift 多选）。", parent=self)
            return []
        return [int(tag) for tag in tags]

    def move_selected(self):
        tags = self.require_tags()
        if tags:
            self.perform(lambda: self.app.catalogue.move_tags(tags, self.target_id(self.destination)))

    def delete_selected_tags(self):
        tags = self.require_tags()
        if tags and messagebox.askyesno("删除标签", f"删除 {len(tags)} 个标签及其全部图片关联？\n原图片文件会保留。", parent=self):
            self.perform(lambda: self.app.catalogue.delete_tags(tags))

    def rename_tag(self):
        tags = self.require_tags(one=True)
        if tags:
            current = self.tag_tree.item(str(tags[0]), "text")
            name = simpledialog.askstring("重命名标签", "新名称：", initialvalue=current, parent=self)
            if name is not None:
                self.perform(lambda: self.app.catalogue.rename_tag(tags[0], name))

    def add_tag(self):
        try:
            group_id = self.target_id(self.destination)
        except ValueError:
            messagebox.showinfo("选择类别", "请先在“目标类别”下拉栏选择标签所属类别。没有类别时可在“标签类别”页创建。", parent=self)
            return
        name = simpledialog.askstring("新增标签", "标签名称：", parent=self)
        if name is not None:
            self.perform(lambda: self.app.catalogue.create_tag(name, group_id))

    def add_category(self):
        name = simpledialog.askstring("新增类别", "类别名称：", parent=self)
        if name is not None:
            self.perform(lambda: self.app.catalogue.create_group(name))

    def rename_category(self):
        selected = self.category_tree.selection()
        if selected:
            name = simpledialog.askstring("重命名类别", "新名称：", initialvalue=self.category_tree.item(selected[0], "text"), parent=self)
            if name is not None:
                self.perform(lambda: self.app.catalogue.rename_group(int(selected[0]), name))

    def delete_category(self):
        selected = self.category_tree.selection()
        if not selected:
            return
        group_id = int(selected[0])
        has_tags = any(t["group_id"] == group_id for t in self.app.catalogue.tags())
        target_id = None
        if has_tags:
            try:
                target_id = self.target_id(self.category_target)
                if target_id == group_id:
                    raise ValueError("请选择其他类别接收标签。")
            except ValueError as exc:
                messagebox.showinfo("选择转移类别", str(exc), parent=self)
                return
        name = self.category_tree.item(selected[0], "text")
        action = f"标签将转移到“{self.category_target.get()}”，图片关联保持不变。" if has_tags else "此类别为空。"
        if messagebox.askyesno("删除类别", f"删除类别“{name}”？\n{action}", parent=self):
            self.perform(lambda: self.app.catalogue.delete_group(group_id, target_id))


class SettingsDialog(Popup):
    def __init__(self, app):
        super().__init__(app, "设置", "700x500")
        self.app = app
        self.minsize(640, 460)
        label(self, "设置", size=20, bold=True).pack(anchor="w", padx=24, pady=(22, 4))
        label(self, "管理外观、同步与数据备份", color=MUTED).pack(anchor="w", padx=24, pady=(0, 16))
        footer = tk.Frame(self, bg=PANEL)
        footer.pack(side="bottom", fill="x", padx=24, pady=(0, 16))
        label(footer, "设置立即生效，自动保存", color=MUTED, size=9).pack(side="left")
        button(footer, "完成", self.destroy).pack(side="right")
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=24, pady=(0, 14))
        self.pages = {}
        for name in ("外观", "同步", "备份与恢复"):
            page = tk.Frame(self.notebook, bg=PANEL, padx=18, pady=20)
            self.pages[name] = page
            self.notebook.add(page, text=name)

        appearance = self.pages["外观"]
        label(appearance, "界面主题", size=13, bold=True).pack(anchor="w", pady=(0, 8))
        label(appearance, "选择白色、黑色，或自动跟随 Windows 应用主题。", color=MUTED).pack(anchor="w", pady=(0, 16))
        self.theme_combo = ClickCombobox(appearance, textvariable=app.theme_mode,
                                        values=("白色", "黑色", "跟随系统"), state="readonly", width=18)
        self.theme_combo.pack(anchor="w")
        self.theme_combo.bind("<<ComboboxSelected>>", lambda _: app.apply_theme())

        sync = self.pages["同步"]
        label(sync, "自动同步", size=13, bold=True).pack(anchor="w", pady=(0, 8))
        label(sync, "定期检查图片库和引用文件夹中的新增、移动和修改。", color=MUTED).pack(anchor="w", pady=(0, 16))
        self.auto_sync_check = tk.Checkbutton(sync, text="启用自动同步（每 15 秒）", variable=app.auto_sync,
                                             command=app.save_auto_sync, bg=PANEL, fg=INK,
                                             selectcolor=PANEL, activebackground=PANEL,
                                             activeforeground=INK, font=("Microsoft YaHei UI", 10),
                                             cursor="hand2", anchor="w")
        self.auto_sync_check.pack(anchor="w")
        label(sync, "关闭后仍可手动“重新扫描”；正常启动时也会检查一次。", color=MUTED, size=9,
              wraplength=550, justify="left").pack(anchor="w", pady=(14, 0))

        backup = self.pages["备份与恢复"]
        label(backup, "标签数据备份", size=13, bold=True).pack(anchor="w", pady=(0, 8))
        label(backup, "备份包含标签、类别、图片路径和内容指纹，不包含原图。\n图片移动后，可恢复备份，再重新定位文件夹或查找原图。\n恢复会替换当前标签库；替换前会自动保存一份当前数据。",
              color=MUTED, justify="left", wraplength=550).pack(anchor="w")
        controls = tk.Frame(backup, bg=PANEL)
        controls.pack(fill="x", pady=22)
        self.export_button = button(controls, "导出备份…", self.export_backup, True)
        self.export_button.pack(side="left")
        self.restore_button = button(controls, "从备份恢复…", self.restore_backup)
        self.restore_button.pack(side="left", padx=12)
        label(backup, f"本地数据：{app.catalogue.data_dir}", color=MUTED, size=9,
              wraplength=550, justify="left").pack(anchor="w")

    def export_backup(self):
        if not self.app.editable():
            return
        path = filedialog.asksaveasfilename(parent=self, title="保存标签备份", defaultextension=".json",
                                          initialfile=f"拾图备份-{time.strftime('%Y%m%d')}.json",
                                          filetypes=[("标签备份", "*.json")])
        if path:
            self.destroy()
            self.app.run_job("备份标签数据", lambda _: self.app.catalogue.backup(Path(path)))

    def restore_backup(self):
        if not self.app.editable():
            return
        path = filedialog.askopenfilename(parent=self, title="选择标签备份", filetypes=[("标签备份", "*.json")])
        if path and messagebox.askyesno("恢复标签备份", "恢复会替换当前标签库，原图文件不会被改动。\n将先自动备份当前数据。确定继续吗？", parent=self):
            self.destroy()
            self.app.run_job("恢复标签数据", lambda _: self.app.catalogue.restore(Path(path)),
                             callback=lambda safety: messagebox.showinfo("恢复完成", f"恢复完成。请重新扫描或定位已移动的图片。\n\n恢复前的数据已保存到：\n{safety}", parent=self.app))


class App(tk.Tk):
    def __init__(self, catalogue: Catalogue, auto_scan=True):
        if os.name == "nt":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Shitu.ImageTagManager")
            except (AttributeError, OSError):
                pass
        super().__init__()
        self.catalogue = catalogue
        preference = catalogue.setting("theme", "跟随系统")
        self.theme_mode = tk.StringVar(value=preference if preference in ("白色", "黑色", "跟随系统") else "跟随系统")
        self.resolved_theme = system_theme() if self.theme_mode.get() == "跟随系统" else self.theme_mode.get()
        self.palette = PALETTES[self.resolved_theme].copy()
        globals().update(self.palette)
        self.title(f"拾图 · ImageTagManager {__version__}")
        self.geometry("1460x900")
        self.minsize(1120, 740)
        self.configure(bg=BG)
        self.events = queue.Queue()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="catalogue")
        self.busy = False
        self.closing = False
        self.all_rows = []
        self.all_tags = []
        self.filtered = []
        self.tag_filters = set()
        self.scope = "全部图片"
        self.current_source = None
        self.search_timer = None
        self.progress_time = 0.0
        self.auto_sync = tk.BooleanVar(value=catalogue.setting("auto_sync", "1") == "1")
        self.search = tk.StringVar()
        self.search_mode = tk.StringVar(value="全部")
        self.sort_mode = tk.StringVar(value="导入时间")
        self.descending = tk.BooleanVar(value=True)
        self.match_mode = tk.StringVar(value="全部")
        self.status = tk.StringVar(value="准备就绪")
        self.build_ui()
        self.reload()
        self.set_app_icon()
        self.after_idle(lambda: self.style_titlebar(self))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(60, self.poll_events)
        self.after(15000, self.periodic_scan)
        self.after(2000, self.check_system_theme)
        if auto_scan:
            self.after(150, lambda: self.run_job("启动检查", self.catalogue.scan, quiet=True))

    def set_app_icon(self):
        resources = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets"
        with Image.open(resources / "app-icon.png") as artwork:
            self._icon_images = [ImageTk.PhotoImage(artwork.resize((size, size), Image.Resampling.LANCZOS), master=self)
                                 for size in (32, 256)]
        self.iconphoto(True, *self._icon_images)
        if os.name == "nt":
            # Default also covers subsequently created previews and dialogs.
            self._icon_path = resources / "app-icon.ico"
            self.update_idletasks()
            self.iconbitmap(default=str(self._icon_path))
            self.iconbitmap(str(self._icon_path))

    def configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TCombobox", padding=7, fieldbackground=PANEL, foreground=INK,
                        background=SURFACE, arrowcolor=MUTED, bordercolor=LINE,
                        lightcolor=LINE, darkcolor=LINE, insertcolor=INK)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", INK)],
                  selectbackground=[("readonly", PANEL)], selectforeground=[("readonly", INK)])
        style.configure("TEntry", padding=7, fieldbackground=SURFACE, foreground=INK,
                        insertcolor=INK, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=INK,
                        borderwidth=0, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE,
                        rowheight=29, font=("Microsoft YaHei UI", 10))
        style.map("Treeview", background=[("selected", ROW_SELECT)], foreground=[("selected", ROW_SELECT_INK)])
        style.configure("Treeview.Heading", background=SURFACE, foreground=MUTED, relief="flat")
        style.configure("TScrollbar", background=LINE, troughcolor=BG, borderwidth=0, arrowsize=12)
        style.configure("TSeparator", background=LINE)
        style.configure("TNotebook", background=PANEL, borderwidth=0,
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
        style.configure("TNotebook.Tab", background=SURFACE, foreground=MUTED, padding=(20, 10),
                        bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
        style.map("TNotebook.Tab", background=[("selected", SELECT)], foreground=[("selected", INK)],
                  padding=[("selected", (20, 10)), ("!selected", (20, 10))])
        self.option_add("*Listbox.background", PANEL)
        self.option_add("*Listbox.foreground", INK)

    def apply_theme(self, persist=True):
        mode = self.theme_mode.get()
        resolved = system_theme() if mode == "跟随系统" else mode
        if persist:
            self.catalogue.set_setting("theme", mode)
        old = self.palette
        self.resolved_theme = resolved
        self.palette = PALETTES[resolved].copy()
        globals().update(self.palette)
        mapping = {old[key]: value for key, value in self.palette.items()}

        def recolor(widget):
            for option in ("background", "foreground", "activebackground", "activeforeground",
                           "selectbackground", "selectforeground", "selectcolor", "highlightbackground",
                           "highlightcolor", "insertbackground", "disabledforeground"):
                try:
                    current = str(widget.cget(option))
                    if current in mapping:
                        widget.configure(**{option: mapping[current]})
                except tk.TclError:
                    pass
            for child in widget.winfo_children():
                recolor(child)
        recolor(self)
        self.configure_styles()
        self.gallery.badge_color = None
        attached_selection = {self.attached_tags[i]["id"] for i in self.attached_list.curselection()}
        available_selection = {self.visible_tags[i]["id"] for i in self.tag_list.curselection()}
        self.apply_filters()
        for widget, tags, selected in ((self.attached_list, self.attached_tags, attached_selection),
                                       (self.tag_list, self.visible_tags, available_selection)):
            for index, tag in enumerate(tags):
                if tag["id"] in selected:
                    widget.selection_set(index)
        # Windows title bars also follow the selected theme.
        if os.name == "nt":
            self.update_idletasks()
            for window in [self] + [w for w in self.winfo_children() if isinstance(w, tk.Toplevel)]:
                self.style_titlebar(window)

    def style_titlebar(self, window):
        if os.name == "nt":
            try:
                hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
                dark = ctypes.c_int(self.resolved_theme == "黑色")
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
            except (AttributeError, OSError):
                pass

    def check_system_theme(self):
        if self.closing:
            return
        if self.theme_mode.get() == "跟随系统" and system_theme() != self.resolved_theme:
            self.apply_theme(persist=False)
        self.after(2000, self.check_system_theme)

    def build_ui(self):
        self.configure_styles()

        header = tk.Frame(self, bg=PANEL, height=80)
        header.pack(fill="x")
        brand = tk.Frame(header, bg=PANEL)
        brand.pack(side="left", padx=24, pady=14)
        label(brand, "拾图", size=22, bold=True).pack(anchor="w")
        label(brand, f"LOCAL COLLECTION  /  {__version__}", color=MUTED, size=9).pack(anchor="w")
        button(header, "＋ 导入图片 / 文件夹", self.import_dialog, True).pack(side="right", padx=(8, 24))
        button(header, "设置", self.settings_dialog).pack(side="right", padx=5)
        button(header, "重新扫描", lambda: self.run_job("重新扫描", self.catalogue.scan)).pack(side="right", padx=5)
        button(header, "来源与路径恢复", self.sources_dialog).pack(side="right", padx=5)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        sidebar = tk.Frame(body, bg=PANEL, width=216)
        sidebar.pack(side="left", fill="y", padx=(0, 1))
        sidebar.pack_propagate(False)
        label(sidebar, "我的收藏", color=MUTED, size=9, bold=True).pack(anchor="w", padx=20, pady=(22, 9))
        self.nav_buttons = {}
        for scope in ("全部图片", "未打标签", "原图缺失"):
            nav = button(sidebar, scope, lambda value=scope: self.set_scope(value), anchor="w")
            nav.pack(fill="x", padx=10, pady=2)
            self.nav_buttons[scope] = nav
        ttk.Separator(sidebar).pack(fill="x", padx=18, pady=17)
        tag_header = tk.Frame(sidebar, bg=PANEL)
        tag_header.pack(fill="x", padx=18)
        label(tag_header, "按标签筛选", bold=True).pack(side="left")
        button(tag_header, "管理", self.tags_dialog, padx=4, pady=3).pack(side="right")
        match = self.match_combo = ClickCombobox(sidebar, textvariable=self.match_mode,
                                                values=("全部", "任一"), state="readonly")
        match.pack(fill="x", padx=16, pady=(10, 5))
        match.bind("<<ComboboxSelected>>", lambda _: self.apply_filters(True))
        label(sidebar, "点击标签可多选；每组均可留空", color=MUTED, size=8).pack(anchor="w", padx=17, pady=3)
        tag_area = tk.Frame(sidebar, bg=PANEL)
        tag_area.pack(fill="both", expand=True, padx=9, pady=6)
        self.tag_tree = ttk.Treeview(tag_area, show="tree", selectmode="none")
        tag_scroll = ttk.Scrollbar(tag_area, command=self.tag_tree.yview)
        self.tag_tree.configure(yscrollcommand=tag_scroll.set)
        self.tag_tree.pack(side="left", fill="both", expand=True)
        tag_scroll.pack(side="right", fill="y")
        self.tag_tree.bind("<ButtonRelease-1>", self.toggle_filter_tag)
        button(sidebar, "清除筛选", self.clear_filters).pack(fill="x", padx=16, pady=(4, 8))

        inspector_outer = tk.Frame(body, bg=PANEL, width=310)
        inspector_outer.pack(side="right", fill="y", padx=(1, 0))
        inspector_outer.pack_propagate(False)
        inspector_canvas = tk.Canvas(inspector_outer, bg=PANEL, highlightthickness=0, bd=0)
        inspector_scroll = ttk.Scrollbar(inspector_outer, command=inspector_canvas.yview)
        inspector_canvas.configure(yscrollcommand=inspector_scroll.set, yscrollincrement=20)
        inspector_scroll.pack(side="right", fill="y")
        inspector_canvas.pack(side="left", fill="both", expand=True)
        inspector = tk.Frame(inspector_canvas, bg=PANEL)
        inspector_window = inspector_canvas.create_window((0, 0), window=inspector, anchor="nw")

        def size_inspector(_=None):
            inspector_canvas.itemconfigure(inspector_window, width=inspector_canvas.winfo_width(),
                                            height=max(inspector.winfo_reqheight(), inspector_canvas.winfo_height()))
            inspector_canvas.configure(scrollregion=inspector_canvas.bbox("all"))

        def scroll_inspector(event):
            widget = event.widget
            if isinstance(widget, (tk.Listbox, ttk.Combobox, ttk.Entry)):
                return
            while widget is not None:
                if widget == inspector_outer:
                    inspector_canvas.yview_scroll(-int(event.delta / 120) * 2, "units")
                    return "break"
                widget = getattr(widget, "master", None)

        inspector.bind("<Configure>", size_inspector)
        inspector_canvas.bind("<Configure>", size_inspector)
        self.bind_all("<MouseWheel>", scroll_inspector, add="+")
        self.selection_title = label(inspector, "图片详情", size=14, bold=True)
        self.selection_title.pack(anchor="w", padx=20, pady=(18, 8))
        self.detail_text = tk.StringVar(value="点击缩略图查看详情\nCtrl / Shift 可多选图片")
        label(inspector, textvariable=self.detail_text, color=MUTED, size=9, justify="left", wraplength=240).pack(anchor="w", padx=20, pady=(0, 10))
        actions = tk.Frame(inspector, bg=PANEL)
        actions.pack(fill="x", padx=15)
        button(actions, "大图预览", self.preview_selected).pack(side="left")
        button(actions, "所在位置", self.reveal_selected).pack(side="right")
        ttk.Separator(inspector).pack(fill="x", padx=18, pady=(12, 8))
        label(inspector, "创建标签", size=12, bold=True).pack(anchor="w", padx=20, pady=(8, 8))
        self.new_group = tk.StringVar()
        self.group_combo = ClickCombobox(inspector, textvariable=self.new_group, state="readonly")
        self.group_combo.pack(fill="x", padx=18, pady=(0, 6))
        self.new_tag = tk.StringVar()
        self.tag_entry = ttk.Entry(inspector, textvariable=self.new_tag)
        self.tag_entry.pack(fill="x", padx=18, pady=(0, 6))
        self.tag_entry.bind("<Return>", lambda _: self.create_and_apply())
        button(inspector, "＋ 创建并添加到所选图片", self.create_and_apply, True).pack(fill="x", padx=18, pady=(0, 12))
        label(inspector, "图片已有标签", size=11, bold=True).pack(anchor="w", padx=20, pady=(0, 3))
        self.attached_hint = label(inspector, "选择图片后显示", color=MUTED, size=8)
        self.attached_hint.pack(anchor="w", padx=20, pady=(0, 6))
        attached_box = tk.Frame(inspector, bg=SURFACE, highlightbackground=LINE, highlightthickness=1)
        attached_box.pack(fill="x", padx=18)
        self.attached_list = tk.Listbox(attached_box, selectmode="extended", exportselection=False, relief="flat",
                                       bg=SURFACE, fg=INK, selectbackground=ROW_SELECT, selectforeground=ROW_SELECT_INK,
                                       font=("Microsoft YaHei UI", 9), activestyle="none", highlightthickness=0, bd=0, height=3)
        attached_scroll = ttk.Scrollbar(attached_box, command=self.attached_list.yview)
        self.attached_list.configure(yscrollcommand=attached_scroll.set)
        self.attached_list.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        attached_scroll.pack(side="right", fill="y")
        attached_actions = tk.Frame(inspector, bg=PANEL)
        attached_actions.pack(fill="x", padx=18, pady=(4, 10))
        button(attached_actions, "移除选中标签", self.remove_attached_tags, padx=5, pady=4).pack(side="left")
        button(attached_actions, "更换标签…", self.replace_tag_dialog, padx=5, pady=4).pack(side="right")
        ttk.Separator(inspector).pack(fill="x", padx=18, pady=(0, 12))
        existing_header = tk.Frame(inspector, bg=PANEL)
        existing_header.pack(fill="x", padx=20)
        label(existing_header, "选择已有标签", size=11, bold=True).pack(side="left")
        button(existing_header, "管理…", self.tags_dialog, padx=3, pady=3).pack(side="right")
        self.tag_search = tk.StringVar()
        entry = ttk.Entry(inspector, textvariable=self.tag_search)
        entry.pack(fill="x", padx=18, pady=7)
        self.tag_search.trace_add("write", lambda *_: self.refresh_tag_list())
        existing_box = tk.Frame(inspector, bg=PANEL)
        existing_box.pack(fill="x", padx=18)
        self.tag_list = tk.Listbox(existing_box, selectmode="extended", exportselection=False, relief="flat",
                                   bg=SURFACE, fg=INK, selectbackground=ROW_SELECT, selectforeground=ROW_SELECT_INK,
                                   font=("Microsoft YaHei UI", 9), activestyle="none", highlightthickness=0, bd=0, height=4)
        existing_scroll = ttk.Scrollbar(existing_box, command=self.tag_list.yview)
        self.tag_list.configure(yscrollcommand=existing_scroll.set)
        self.tag_list.pack(side="left", fill="both", expand=True)
        existing_scroll.pack(side="right", fill="y")
        button(inspector, "添加所选标签", lambda: self.modify_tags(False), True).pack(fill="x", padx=18, pady=(8, 18))
        button(inspector, "重新关联原图…", self.relink_selected, pady=4).pack(fill="x", padx=18, pady=(0, 12))

        center = tk.Frame(body, bg=BG)
        center.pack(fill="both", expand=True)
        searchbar = tk.Frame(center, bg=BG)
        searchbar.pack(fill="x", padx=20, pady=(20, 12))
        searchbox = ttk.Entry(searchbar, textvariable=self.search, font=("Microsoft YaHei UI", 11))
        searchbox.pack(side="left", fill="x", expand=True, ipady=4)
        self.search.trace_add("write", self.defer_search)
        mode = ClickCombobox(searchbar, textvariable=self.search_mode, values=("全部", "文件名", "标签"), state="readonly", width=8)
        mode.pack(side="left", padx=(8, 0))
        mode.bind("<<ComboboxSelected>>", lambda _: self.apply_filters(True))
        toolbar = tk.Frame(center, bg=BG)
        toolbar.pack(fill="x", padx=20, pady=(0, 10))
        self.result_label = label(toolbar, "全部图片", size=12, bold=True)
        self.result_label.pack(side="left")
        order = ClickCombobox(toolbar, textvariable=self.sort_mode,
                             values=("导入时间", "文件名", "修改时间", "图片分辨率", "文件大小"), width=11, state="readonly")
        order.pack(side="right")
        order.bind("<<ComboboxSelected>>", lambda _: self.apply_filters(True))
        self.order_button = button(toolbar, "↓ 降序", self.toggle_order, pady=3, padx=8)
        self.order_button.pack(side="right", padx=4)
        grid_area = tk.Frame(center, bg=BG)
        grid_area.pack(fill="both", expand=True, padx=8)
        self.gallery = Gallery(grid_area, self)
        gallery_scroll = ttk.Scrollbar(grid_area, command=self.gallery.scroll)
        self.gallery.configure(yscrollcommand=gallery_scroll.set)
        self.gallery.pack(side="left", fill="both", expand=True)
        gallery_scroll.pack(side="right", fill="y")
        statusbar = tk.Frame(self, bg=PANEL)
        statusbar.pack(fill="x", side="bottom")
        label(statusbar, textvariable=self.status, color=MUTED, size=9).pack(side="left", padx=16, pady=7)
        label(statusbar, "双击预览  ·  Ctrl 多选  ·  Shift 连选  ·  Ctrl+A 全选", color=MUTED, size=8).pack(side="right", padx=16)

    def reload(self):
        self.all_rows = self.catalogue.rows()
        self.all_tags = self.catalogue.tags()
        self.groups = self.catalogue.groups()
        self.tag_filters &= {t["id"] for t in self.all_tags}
        values = [group["name"] for group in self.groups]
        self.group_combo["values"] = values
        if self.new_group.get() not in values:
            self.new_group.set(values[0] if values else "")
        self.refresh_filter_tree()
        self.apply_filters()
        self.selection_changed()

    def refresh_filter_tree(self):
        opened = {key for key in self.tag_tree.get_children() if self.tag_tree.item(key, "open")}
        self.tag_tree.delete(*self.tag_tree.get_children())
        for group in self.groups:
            key = "g" + str(group["id"])
            self.tag_tree.insert("", "end", iid=key, text=group["name"], open=key in opened or not opened)
            for tag in self.all_tags:
                if tag["group_id"] == group["id"]:
                    mark = "☑" if tag["id"] in self.tag_filters else "☐"
                    self.tag_tree.insert(key, "end", iid="t" + str(tag["id"]), text=f"{mark} {tag['name']}  {tag['count']}")

    def toggle_filter_tag(self, event):
        item = self.tag_tree.identify_row(event.y)
        if item.startswith("t"):
            self.tag_filters.symmetric_difference_update({int(item[1:])})
            self.refresh_filter_tree()
            self.apply_filters(True)

    def set_scope(self, scope, source=None):
        self.scope = scope
        self.current_source = source
        self.apply_filters(True)

    def clear_filters(self):
        self.tag_filters.clear()
        self.search.set("")
        self.current_source = None
        self.scope = "全部图片"
        self.refresh_filter_tree()
        self.apply_filters(True)

    def defer_search(self, *_):
        if self.search_timer:
            self.after_cancel(self.search_timer)
        self.search_timer = self.after(150, lambda: self.apply_filters(True))

    def apply_filters(self, reset_scroll=False):
        self.search_timer = None
        self.filtered = filter_images(self.all_rows, self.all_tags, query=self.search.get(), search_mode=self.search_mode.get(),
                                      selected_tags=self.tag_filters, intersection=self.match_mode.get() == "全部",
                                      scope=self.scope, source=self.current_source, sort=self.sort_mode.get(), descending=self.descending.get())
        self.result_label.configure(text=f"{self.scope}  ·  {len(self.filtered)} 张" + (f"  ·  已选 {len(self.tag_filters)} 标签" if self.tag_filters else ""))
        counts = {"全部图片": len(self.all_rows), "未打标签": sum(not r["tags"] for r in self.all_rows),
                  "原图缺失": sum(r["missing"] for r in self.all_rows)}
        for scope, nav in self.nav_buttons.items():
            nav.configure(text=f"{scope}    {counts[scope]}", bg=SELECT if self.scope == scope else PANEL,
                          fg=ACCENT if self.scope == scope else INK)
        self.gallery.set_rows(self.filtered, reset_scroll)
        self.selection_changed()

    def toggle_order(self):
        self.descending.set(not self.descending.get())
        self.order_button.configure(text="↓ 降序" if self.descending.get() else "↑ 升序")
        self.apply_filters(True)

    def selected_rows(self):
        return [row for row in self.all_rows if row["id"] in self.gallery.selected]

    def selection_changed(self):
        rows = self.selected_rows()
        if not rows:
            self.selection_title.configure(text="图片详情")
            self.detail_text.set("点击缩略图查看详情\nCtrl / Shift 可多选图片")
        elif len(rows) == 1:
            row = rows[0]
            modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(row["mtime_ns"] / 1e9))
            self.selection_title.configure(text="已选 1 张图片")
            self.detail_text.set(f"{row['filename']}\n{row['width']} × {row['height']} · {size_label(row['bytes'])} · {row['format']}\n修改时间 {modified}" + ("\n原图缺失 · 可重新关联" if row['missing'] else ""))
        else:
            self.selection_title.configure(text=f"已选 {len(rows)} 张图片")
            self.detail_text.set(f"合计 {size_label(sum(r['bytes'] for r in rows))}\n添加 / 移除标签将应用于所有选中图片")
        self.refresh_tag_list()
        self.refresh_attached_tags()

    def refresh_attached_tags(self):
        rows = self.selected_rows()
        attached = set().union(*(row["tags"] for row in rows)) if rows else set()
        self.attached_tags = [tag for tag in self.all_tags if tag["id"] in attached]
        self.attached_list.delete(0, "end")
        for tag in self.attached_tags:
            count = sum(tag["id"] in row["tags"] for row in rows)
            suffix = "" if len(rows) == 1 else f"  {count}/{len(rows)}"
            self.attached_list.insert("end", f"{tag['group_name']} / {tag['name']}{suffix}")
        self.attached_hint.configure(text="选择图片后显示" if not rows else
                                     "还没有标签，在上方创建或从下方添加" if not attached else
                                     f"共 {len(attached)} 个标签" + (" · 数字表示拥有该标签的图片数" if len(rows) > 1 else ""))

    def remove_attached_tags(self):
        if not self.editable() or not self.ensure_selected():
            return
        for index in self.attached_list.curselection():
            self.catalogue.apply_tag(self.gallery.selected, self.attached_tags[index]["id"], remove=True)
        self.reload()

    def refresh_tag_list(self):
        rows = self.selected_rows()
        search = self.tag_search.get().strip().casefold()
        self.visible_tags = [tag for tag in self.all_tags if search in (tag["group_name"] + tag["name"]).casefold()]
        self.tag_list.delete(0, "end")
        for tag in self.visible_tags:
            count = sum(tag["id"] in row["tags"] for row in rows)
            mark = "✓" if rows and count == len(rows) else "◐" if count else "＋"
            self.tag_list.insert("end", f"{mark}  {tag['group_name']} / {tag['name']}")

    def ensure_selected(self, one=False):
        count = len(self.gallery.selected)
        if not count or (one and count != 1):
            messagebox.showinfo("选择图片", "请先选中一张图片。" if one else "请先选中一张或多张图片。", parent=self)
            return False
        return True

    def editable(self):
        if self.busy:
            messagebox.showinfo("正在处理", "请等待当前扫描或导入完成。", parent=self)
            return False
        return True

    def modify_tags(self, remove):
        if not self.editable() or not self.ensure_selected():
            return
        selected = list(self.tag_list.curselection())
        for index in selected:
            self.catalogue.apply_tag(self.gallery.selected, self.visible_tags[index]["id"], remove)
        self.reload()

    def create_and_apply(self):
        if not self.editable() or not self.ensure_selected():
            return
        group = next((g for g in self.groups if g["name"] == self.new_group.get()), None)
        if not group:
            messagebox.showinfo("选择类别", "请先选择类别；没有类别时可在标签管理页创建。", parent=self)
            return
        try:
            tag_id = self.catalogue.create_tag(self.new_tag.get(), group["id"])
            self.catalogue.apply_tag(self.gallery.selected, tag_id)
            self.new_tag.set("")
            self.reload()
        except (ValueError, OSError) as exc:
            messagebox.showerror("无法创建标签", str(exc), parent=self)

    def preview_selected(self):
        if self.ensure_selected(one=True):
            self.preview(next(iter(self.gallery.selected)))

    def preview(self, image_id):
        Preview(self, image_id)

    def reveal_selected(self):
        if not self.ensure_selected(one=True):
            return
        path = Path(self.selected_rows()[0]["path"])
        if path.is_file():
            subprocess.Popen(["explorer.exe", "/select,", str(path)])
        else:
            messagebox.showinfo("原图缺失", "原位置没有找到图片。请点击“重新关联原图”或“来源与路径恢复”。", parent=self)

    def import_dialog(self):
        if not self.editable():
            return
        dialog = Popup(self, "导入图片", "620x500")
        label(dialog, "把收藏加入拾图", size=19, bold=True).pack(anchor="w", padx=25, pady=(24, 8))
        label(dialog, "支持多个文件夹，默认扫描子文件夹。也可以选择多张图片。", color=MUTED, size=10).pack(anchor="w", padx=25)
        mode = tk.StringVar(value="copy")
        for value, title, description in [
            ("copy", "复制到图片库（默认）", "保留源文件，图片库保存独立副本。"),
            ("move", "移动到图片库", "校验副本成功后删除源文件；只移动支持的图片。"),
            ("reference", "保留原位置", "不复制、不移动；以后移动原图需恢复关联。")]:
            tk.Radiobutton(dialog, text=title, variable=mode, value=value, bg=PANEL,
                           activebackground=PANEL, fg=INK, font=("Microsoft YaHei UI", 11), anchor="w").pack(fill="x", padx=25, pady=(14, 0))
            label(dialog, description, color=MUTED, size=9).pack(anchor="w", padx=48)
        label(dialog, f"图片库：{self.catalogue.library_dir}", color=MUTED, size=9, wraplength=560, justify="left").pack(anchor="w", padx=25, pady=15)
        controls = tk.Frame(dialog, bg=PANEL)
        controls.pack(fill="x", padx=25, pady=12)

        def choose_files():
            files = filedialog.askopenfilenames(parent=dialog, title="选择要导入的图片", filetypes=FILE_TYPES)
            if files:
                begin([Path(path) for path in files])

        def choose_folders():
            folder = filedialog.askdirectory(parent=dialog, title="选择文件夹（可重复添加多个来源）")
            if folder:
                chosen.append(Path(folder))
                chosen_label.configure(text="已选：" + "；".join(str(path) for path in chosen), wraplength=560)
                start_button.configure(state="normal", text=f"导入 {len(chosen)} 个文件夹")

        def begin(paths):
            selected_mode = mode.get()
            if selected_mode == "move" and not messagebox.askyesno("确认移动图片", "将先复制并校验图片，再删除源图片文件。\n源文件夹中的非图片文件会保留。\n\n确定移动所选图片吗？", parent=dialog):
                return
            dialog.destroy()
            self.run_job("导入图片", lambda progress: self.catalogue.import_paths(paths, selected_mode, progress))

        chosen = []
        button(controls, "选择图片…", choose_files).pack(side="left")
        button(controls, "添加文件夹…", choose_folders).pack(side="left", padx=8)
        start_button = button(controls, "导入文件夹", lambda: begin(chosen), True)
        start_button.configure(state="disabled")
        start_button.pack(side="right")
        chosen_label = label(dialog, "", color=MUTED, size=9, justify="left")
        chosen_label.pack(anchor="w", padx=25)

    def run_job(self, title, function, quiet=False, callback=None):
        if self.busy or self.closing:
            if not quiet:
                messagebox.showinfo("正在处理", "请等待当前任务完成。", parent=self)
            return False
        self.busy = True
        self.status.set(title + "…")

        def progress(text):
            now = time.monotonic()
            if now - self.progress_time > 0.12:
                self.progress_time = now
                self.events.put(("progress", text))

        def work():
            try:
                result = function(progress)
                self.events.put(("done", title, result, quiet, callback))
            except Exception as exc:
                logging.exception("Background task failed: %s", title)
                self.events.put(("error", title, str(exc)))

        self.worker.submit(work)
        return True

    def poll_events(self):
        if self.closing:
            return
        for _ in range(120):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind, *args = event
            if kind == "progress":
                self.status.set(args[0])
            elif kind == "thumb":
                self.gallery.receive_thumb(*args)
            elif kind == "hover":
                self.gallery.receive_hover(*args)
            elif kind == "done":
                title, result, quiet, callback = args
                self.busy = False
                changed = not isinstance(result, Report) or result.added or result.updated or result.recovered
                if not quiet or changed or (isinstance(result, Report) and result.missing != sum(r["missing"] for r in self.all_rows)):
                    self.reload()
                if isinstance(result, Report):
                    self.status.set(result.summary())
                    if result.candidates and not quiet:
                        self.candidates_dialog(result)
                    if result.errors and not quiet:
                        self.report_dialog(title, result)
                else:
                    self.status.set(title + "完成")
                if callback:
                    callback(result)
            elif kind == "error":
                self.busy = False
                self.status.set(args[0] + "失败")
                messagebox.showerror(args[0], args[1], parent=self)
        self.after(60, self.poll_events)

    def periodic_scan(self):
        if self.closing:
            return
        if self.auto_sync.get() and not self.busy:
            self.run_job("自动同步", self.catalogue.scan, quiet=True)
        self.after(15000, self.periodic_scan)

    def report_dialog(self, title, report):
        dialog = Popup(self, title + "结果", "700x440")
        label(dialog, report.summary(), size=11, bold=True, wraplength=650).pack(anchor="w", padx=20, pady=18)
        text = tk.Text(dialog, wrap="word", bg=BG, fg=INK, relief="flat", font=("Microsoft YaHei UI", 10))
        text.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        text.insert("1.0", "\n\n".join(report.errors))
        text.configure(state="disabled")

    def sources_dialog(self):
        dialog = Popup(self, "来源与路径恢复", "800x580")
        label(dialog, "来源文件夹", size=17, bold=True).pack(anchor="w", padx=22, pady=(22, 7))
        label(dialog, "图片库和引用目录会在启动时、自动同步时及手动扫描时检查。", color=MUTED).pack(anchor="w", padx=22)
        listing = tk.Listbox(dialog, bg=BG, fg=INK, font=("Microsoft YaHei UI", 10), exportselection=False, relief="flat")
        listing.pack(fill="both", expand=True, padx=22, pady=15)
        sources = self.catalogue.sources()
        for source in sources:
            listing.insert("end", ("[图片库] " if source["kind"] == "library" else "[引用] ") + source["path"])
        if sources:
            listing.selection_set(0)

        def recover_folder():
            if not self.editable():
                return
            folder = filedialog.askdirectory(parent=dialog, title="选择可能包含丢失图片的文件夹")
            if folder:
                dialog.destroy()
                self.run_job("查找丢失图片", lambda progress: self.catalogue.recover([Path(folder)], progress))

        def relocate():
            if not self.editable() or not listing.curselection():
                return
            source = sources[listing.curselection()[0]]
            folder = filedialog.askdirectory(parent=dialog, title="选择该文件夹的新位置")
            if folder:
                dialog.destroy()
                self.run_job("重新定位文件夹", lambda progress: self.catalogue.relocate_source(source["id"], Path(folder), progress))

        controls = tk.Frame(dialog, bg=PANEL)
        controls.pack(fill="x", padx=22, pady=6)
        button(controls, "重新定位所选文件夹…", relocate, True).pack(side="left")
        button(controls, "在指定目录查找丢失图片…", recover_folder).pack(side="left", padx=10)
        label(dialog, "恢复规则：按文件内容匹配并保留原标签；多个候选位置会要求你选择。\n图片库位置保持固定；为移动后的图片库定位时，新位置将作为引用来源。", color=MUTED, size=9, justify="left").pack(anchor="w", padx=22, pady=12)
        button(dialog, "打开图片库", lambda: os.startfile(self.catalogue.library_dir)).pack(anchor="w", padx=22, pady=(0, 16))

    def candidates_dialog(self, report):
        dialog = Popup(self, "选择原图位置", "800x500")
        label(dialog, "发现多个可能的对应关系，请逐项确认", size=13, bold=True).pack(anchor="w", padx=20, pady=18)
        records = {row["id"]: row for row in self.all_rows}
        label_var = tk.StringVar()
        label(dialog, textvariable=label_var, color=MUTED, justify="left", wraplength=750).pack(anchor="w", padx=20)
        listing = tk.Listbox(dialog, bg=BG, fg=INK, font=("Microsoft YaHei UI", 10), exportselection=False)
        listing.pack(fill="both", expand=True, padx=20, pady=15)
        pending = list(report.candidates)

        def load():
            if not pending:
                dialog.destroy()
                return
            image_id, paths = pending[0]
            record = records.get(image_id, {})
            label_var.set(f"原记录：{record.get('path', image_id)}\n剩余 {len(pending)} 项")
            listing.delete(0, "end")
            for path in paths:
                listing.insert("end", path)

        def confirm():
            if not self.editable() or not pending or not listing.curselection():
                return
            image_id, paths = pending[0]
            target = Path(paths[listing.curselection()[0]])
            dialog.destroy()
            rest = pending[1:]

            def after(_):
                if rest:
                    self.candidates_dialog(Report(candidates=rest))

            self.run_job("恢复关联", lambda _: self.catalogue.relink(image_id, target), callback=after)

        controls = tk.Frame(dialog, bg=PANEL)
        controls.pack(fill="x", padx=20, pady=(0, 15))
        button(controls, "关联所选位置", confirm, True).pack(side="left")
        button(controls, "跳过这一项", lambda: (pending.pop(0), load())).pack(side="left", padx=12)
        load()

    def relink_selected(self):
        if not self.editable() or not self.ensure_selected(one=True):
            return
        row = self.selected_rows()[0]
        target = filedialog.askopenfilename(parent=self, title="选择要关联的原图", filetypes=FILE_TYPES)
        if not target:
            return
        allow_changed = messagebox.askyesno("文件内容确认", "是否允许关联内容经过修改的图片？\n\n选“否”：只接受与原图内容指纹完全相同的文件。\n选“是”：允许将这张记录的全部标签关联到新文件。", parent=self)
        self.run_job("重新关联原图", lambda _: self.catalogue.relink(row["id"], Path(target), allow_changed))

    def tags_dialog(self):
        existing = getattr(self, "tag_manager", None)
        if existing is not None and existing.winfo_exists():
            existing.refresh()
            existing.lift()
            return existing
        self.tag_manager = TagManager(self)
        return self.tag_manager

    def replace_tag_dialog(self):
        if not self.editable() or not self.ensure_selected():
            return
        selected_ids = set(self.gallery.selected)
        attached = set().union(*(row["tags"] for row in self.selected_rows()))
        choices = [tag for tag in self.all_tags if tag["id"] in attached]
        if not choices:
            messagebox.showinfo("没有可更换的标签", "请先为图片添加标签。", parent=self)
            return
        dialog = Popup(self, "仅为选中图片更换标签", "520x340")
        label(dialog, "其他图片的标签保持不变", size=13, bold=True).pack(anchor="w", padx=24, pady=20)
        old = tk.StringVar(value=f"{choices[0]['group_name']} / {choices[0]['name']}")
        label(dialog, "原标签", color=MUTED).pack(anchor="w", padx=24)
        ClickCombobox(dialog, textvariable=old, values=[f"{t['group_name']} / {t['name']}" for t in choices], state="readonly").pack(fill="x", padx=24, pady=7)
        label(dialog, "替换为（在原分组中创建或使用已有标签）", color=MUTED).pack(anchor="w", padx=24, pady=(10, 0))
        new = tk.StringVar()
        ttk.Entry(dialog, textvariable=new).pack(fill="x", padx=24, pady=7)

        def apply():
            if not self.editable():
                return
            tag = next(t for t in choices if f"{t['group_name']} / {t['name']}" == old.get())
            try:
                new_id = self.catalogue.create_tag(new.get(), tag["group_id"])
                self.catalogue.replace_tag(selected_ids, tag["id"], new_id)
                dialog.destroy()
                self.reload()
            except ValueError as exc:
                messagebox.showerror("无法更换", str(exc), parent=dialog)

        button(dialog, "更换所选图片的标签", apply, True).pack(anchor="e", padx=24, pady=20)

    def settings_dialog(self, page=None):
        dialog = getattr(self, "_settings_window", None)
        if dialog is None or not dialog.winfo_exists():
            dialog = self._settings_window = SettingsDialog(self)
        if page in dialog.pages:
            dialog.notebook.select(dialog.pages[page])
        dialog.deiconify()
        dialog.lift()
        return dialog

    def save_auto_sync(self):
        self.catalogue.set_setting("auto_sync", "1" if self.auto_sync.get() else "0")

    def close(self):
        if self.busy:
            messagebox.showinfo("正在处理文件", "请等待扫描、导入或备份完成后再退出。", parent=self)
            return
        self.closing = True
        self.gallery.shutdown()
        self.worker.shutdown(wait=False, cancel_futures=True)
        self.destroy()


def main():
    parser = argparse.ArgumentParser(description="拾图 · ImageTagManager")
    parser.add_argument("--data-dir", type=Path, default=default_data_folder())
    parser.add_argument("--library-dir", type=Path, default=pictures_folder() / "ImageTagManager 图片库")
    parser.add_argument("--no-startup-scan", action="store_true")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.data_dir / "app.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    # One writer UI per database; a second instance must not race a file move/restore.
    mutex = None
    if os.name == "nt":
        import hashlib
        identity = hashlib.sha256(str(args.data_dir.resolve()).casefold().encode()).hexdigest()[:24]
        ctypes.windll.kernel32.CreateMutexW.restype = ctypes.c_void_p
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\ImageTagManager-" + identity)
        if ctypes.windll.kernel32.GetLastError() == 183:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("拾图已在运行", "这个图片库已经在另一个拾图窗口中打开。", parent=root)
            root.destroy()
            return
    try:
        catalogue = Catalogue(args.data_dir, args.library_dir)
        app = App(catalogue, auto_scan=not args.no_startup_scan)

        def callback_exception(exc, value, traceback):
            logging.error("UI exception", exc_info=(exc, value, traceback))
            messagebox.showerror("操作未完成", f"{value}\n\n详情已写入 {args.data_dir / 'app.log'}", parent=app)

        app.report_callback_exception = callback_exception
        app.mainloop()
    except Exception as exc:
        logging.exception("Application startup failed")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("无法启动拾图", str(exc), parent=root)
        root.destroy()
        sys.exit(1)
    finally:
        if mutex:
            ctypes.windll.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            ctypes.windll.kernel32.CloseHandle(mutex)
