"""Desktop settings actions, update workflow and background presentation."""
from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import shutil
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, messagebox, ttk

from PIL import Image, ImageOps, ImageTk, ImageGrab

from . import __version__, updates
from .appearance import PALETTES
from .colors import image_accents, contrast
from .core import Catalogue
from .storage import inspect_database, migrate_data, update_backup, write_config, validate_locations
from .windows import Tray


class DesktopFeatures:
    color_contrast = staticmethod(contrast)

    @staticmethod
    def safe_number(value, fallback, minimum, maximum):
        try:
            result = float(value)
            return result if minimum <= result <= maximum else fallback
        except (ValueError, TypeError):
            return fallback

    def load_background(self):
        self.background_image = None
        name = self.catalogue.setting("background_file")
        if name and Path(name).name == name:
            try:
                with Image.open(self.catalogue.data_dir / "backgrounds" / name) as image:
                    self.background_image = ImageOps.exif_transpose(image).convert("RGB")
                    self.background_image.thumbnail((2560, 2560))
            except (OSError, ValueError):
                logging.warning("Custom background is unavailable: %s", name)
        self.background_key = None

    def gallery_background(self, size):
        if self.theme_mode.get() != "自定义背景" or self.background_image is None:
            return None
        key = (size, self.backdrop.wallpaper_key(self), self.winfo_width(), self.winfo_height(),
               self.gallery.winfo_rootx(), self.gallery.winfo_rooty())
        if key != self.background_key:
            picture = self.backdrop.crop(self.gallery, size)
            self.background_photo = ImageTk.PhotoImage(picture, master=self)
            self.background_key = key
        return self.background_photo

    def accent_candidates(self):
        if hasattr(self, "_accent_candidates"):
            return self._accent_candidates
        try:
            values = json.loads(self.catalogue.setting("accent_candidates", "[]"))
            if len(values) == 4 and all(isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in values):
                self._accent_candidates = values
                return values
        except (ValueError, TypeError):
            pass
        return ["#6877bd", "#7f8c71", "#af7c8e", "#b08c64"]

    def set_background(self, source):
        candidates = image_accents(source)
        folder = self.catalogue.data_dir / "backgrounds"
        folder.mkdir(exist_ok=True)
        target = folder / "custom.png"
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((2560, 2560))
            image.save(folder / "custom.tmp", format="PNG")
        os.replace(folder / "custom.tmp", target)
        self.catalogue.set_setting("background_file", target.name)
        self.catalogue.set_setting("background_name", source.name)
        self.catalogue.set_setting("accent_candidates", json.dumps(candidates))
        self._accent_candidates = candidates
        self.custom_accent.set(candidates[0])
        self.load_background()
        self.save_appearance()

    def reset_background(self):
        self.catalogue.set_setting("background_file", "")
        self.catalogue.set_setting("background_name", "尚未选择背景图片")
        self.catalogue.set_setting("accent_candidates", "[]")
        self._accent_candidates = ["#6877bd", "#7f8c71", "#af7c8e", "#b08c64"]
        self.background_opacity.set(45)
        self.custom_accent.set("#6877bd")
        self.load_background()
        self.save_appearance()

    def save_appearance(self):
        self.schedule_appearance_save()
        self.apply_theme(persist=False)

    def schedule_appearance_save(self):
        if self.opacity_timer:
            self.after_cancel(self.opacity_timer)
        self.opacity_timer = self.after(250, self.persist_opacity)

    def schedule_background_opacity(self):
        self.background_key = None
        self.backdrop.invalidate()
        self.gallery.request_redraw()
        self.schedule_appearance_save()

    def persist_opacity(self):
        if self.opacity_timer:
            self.after_cancel(self.opacity_timer)
        self.opacity_timer = None
        # A color-dialog preview must never leak into a background save or an
        # exit/update flush. Only its Apply action commits the candidate color.
        accent = getattr(self, "_accent_preview_original", None) or self.custom_accent.get()
        values = {"custom_accent": accent, "theme": self.theme_mode.get(),
                  "background_opacity": str(round(self.background_opacity.get()))}
        for name in ("layout", "scale", "x", "y"):
            values["background_" + name] = str(getattr(self, "background_" + name).get())
        previous = getattr(self, "_saved_appearance", {})
        changed = {key: value for key, value in values.items() if previous.get(key) != value}
        self.catalogue.set_settings(changed)
        self._saved_appearance = values

    def refresh_backdrop(self):
        """Refresh ordinary theme surfaces and custom wallpaper."""
        with self.backdrop.transaction():
            if os.name == "nt":
                for window in [self] + [w for w in self.winfo_children()
                                       if isinstance(w, tk.Toplevel) and not getattr(w, "_no_backdrop", False)]:
                    self.style_titlebar(window)
            if hasattr(self, "gallery"):
                self.gallery.card_photos.clear()
                self.gallery.configure(bg=self.palette["BG"])
                self.gallery.request_redraw()
            ttk.Style(self).configure("Treeview", background=self.palette["PANEL"],
                                      fieldbackground=self.palette["PANEL"])
            self.backdrop.invalidate()

    def color_dialog(self, parent, callback, preview_callback):
        from .app import Popup, button, label
        existing = getattr(self, "_color_dialog", None)
        if existing and existing.winfo_exists():
            existing.lift()
            existing.focus_set()
            return existing
        # Finish earlier committed appearance changes before starting a draft.
        self.persist_opacity()
        original = self.custom_accent.get()
        app = self

        class ColorDialog(Popup):
            applied = False
            closed = False

            def destroy(self):
                if self.closed:
                    return
                self.closed = True
                if getattr(self, "preview_trace", None):
                    self.color_value.trace_remove("write", self.preview_trace)
                app._accent_preview_original = None
                app._color_dialog = None
                super().destroy()
                if not self.applied:
                    if not app.closing and parent.winfo_exists():
                        preview_callback(original)
                    else:
                        app.custom_accent.set(original)
                        if not app.closing:
                            app.apply_theme(persist=False)

        dialog = self._color_dialog = ColorDialog(self, "自定义主题色", "450x245")
        self._accent_preview_original = original
        dialog.preview_parent = parent
        dialog.transient(parent)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        label(dialog, "选择主题色", size=15, bold=True).pack(anchor="w", padx=22, pady=(20, 12))
        value = dialog.color_value = tk.StringVar(master=dialog, value=original)
        row = tk.Frame(dialog, bg=self.palette["PANEL"])
        row.pack(fill="x", padx=22)
        ttk.Entry(row, textvariable=value, width=15).pack(side="left")
        def chooser():
            chosen = colorchooser.askcolor(value.get() if re.fullmatch(r"#[0-9a-fA-F]{6}", value.get()) else "#6877bd", parent=dialog, title="选择主题色")[1]
            if chosen:
                value.set(chosen)
        dialog.chooser_button = button(row, "颜色选择器…", chooser)
        dialog.chooser_button.pack(side="left", padx=12)
        dialog.pick_button = button(dialog, "屏幕取色（Esc 取消）", lambda: self.screen_pick(dialog, value.set))
        dialog.pick_button.pack(anchor="w", padx=22, pady=10)
        def apply():
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", value.get()):
                messagebox.showinfo("检查颜色", "请输入 #RRGGBB 格式的颜色，例如 #6877bd。", parent=dialog)
                return
            self._accent_preview_original = None
            callback(value.get().lower())
            # The candidate is already displayed, so the regular callback may
            # correctly skip repainting. Commit explicitly even in that case.
            self.persist_opacity()
            dialog.applied = True
            dialog.destroy()
        dialog.apply_button = button(dialog, "应用颜色", apply, True)
        dialog.apply_button.pack(anchor="e", padx=22, pady=8)
        dialog.preview_trace = value.trace_add("write", lambda *_: preview_callback(value.get().lower())
                                               if re.fullmatch(r"#[0-9a-fA-F]{6}", value.get()) else None)
        dialog.grab_set()
        return dialog

    def screen_pick(self, dialog, callback):
        from .app import label
        if os.name != "nt":
            messagebox.showinfo("屏幕取色", "屏幕取色目前适用于 Windows。", parent=dialog)
            return
        # A temporary frozen desktop intercepts the selection click. Clicking a
        # color must never accidentally click a button in the app underneath.
        # The image stays in memory and is released on confirmation/cancellation.
        try:
            captured = ImageGrab.grab(all_screens=True).convert("RGB")
        except OSError as exc:
            messagebox.showerror("无法屏幕取色", str(exc), parent=dialog)
            return
        user = ctypes.windll.user32
        left, top = user.GetSystemMetrics(76), user.GetSystemMetrics(77)
        overlay = tk.Toplevel(self)
        overlay._no_backdrop = True
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.geometry(f"{captured.width}x{captured.height}{left:+d}{top:+d}")
        canvas = tk.Canvas(overlay, highlightthickness=0, cursor="crosshair", bd=0)
        canvas.pack(fill="both", expand=True)
        photo = ImageTk.PhotoImage(captured, master=overlay)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.photo = photo
        hint = label(overlay, "单击取色 · Esc 取消", size=10, padx=12, pady=9)
        hint.place(x=24, y=24)
        def finish(color=None):
            overlay.grab_release()
            overlay.destroy()
            captured.close()
            dialog.lift()
            dialog.grab_set()
            if color:
                callback(color)
        def pixel(event):
            x = min(captured.width - 1, max(0, event.x_root - left))
            y = min(captured.height - 1, max(0, event.y_root - top))
            return "#%02x%02x%02x" % captured.getpixel((x, y))
        def motion(event):
            color = pixel(event)
            hint.configure(text=f"{color}   单击取色 · Esc 取消", bg=color,
                           fg="#ffffff" if contrast(color, "#ffffff") > 4.5 else "#000000")
            hint.place(x=max(0, min(captured.width - 270, event.x_root - left + 22)),
                       y=max(0, min(captured.height - 45, event.y_root - top + 24)))
        canvas.bind("<Motion>", motion)
        overlay.bind("<Button-1>", lambda event: finish(pixel(event)))
        overlay.bind("<Escape>", lambda _: finish())
        overlay.protocol("WM_DELETE_WINDOW", finish)
        overlay.focus_force()
        overlay.grab_set()

    def notify(self, text, seconds=5):
        from .app import label
        if self.closing:
            return
        if self.toast_timer:
            self.after_cancel(self.toast_timer)
        if self.toast and self.toast.winfo_exists():
            self.toast.destroy()
        self.toast = tk.Frame(self, bg=self.palette["PANEL"], highlightbackground=self.palette["LINE"], highlightthickness=1)
        label(self.toast, text, size=10, padx=16, pady=12, wraplength=400, justify="left").pack()
        self.toast.place(x=18, rely=1, y=-46, anchor="sw")
        self.toast.lift()
        self.toast_timer = self.after(seconds * 1000, self.dismiss_toast)

    def dismiss_toast(self):
        self.toast_timer = None
        if self.toast and self.toast.winfo_exists():
            self.toast.destroy()
        self.toast = None

    def start_tray(self):
        self.tray = Tray(self._icon_path, self.events)
        self.tray.start()

    def show_window(self):
        self.deiconify()
        if self.state() == "iconic":
            self.state("normal")
        self.lift()
        self.focus_force()

    def hide_to_tray(self):
        if not self.tray or not self.tray.ok:
            messagebox.showinfo("系统托盘不可用", "未能创建托盘图标，窗口将保持显示。可以选择退出程序。", parent=self)
            return False
        # Hide transient windows too, without losing their state.
        for child in self.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.destroy()
        self.withdraw()
        return True

    def save_close_behavior(self):
        self.catalogue.set_setting("hide_on_close", "1" if self.hide_on_close.get() else "0")
        self.catalogue.set_setting("close_prompt", "0")

    def close_dialog(self):
        from .app import Popup, button, label
        existing = getattr(self, "_close_dialog", None)
        if existing and existing.winfo_exists():
            existing.lift()
            return
        dialog = self._close_dialog = Popup(self, "关闭拾图", "490x250")
        label(dialog, "关闭窗口后，继续在托盘运行？", size=14, bold=True).pack(anchor="w", padx=22, pady=(22, 10))
        label(dialog, "隐藏后仍会自动同步，可从托盘菜单恢复或退出。", color=self.palette["MUTED"], size=9).pack(anchor="w", padx=22)
        remember = tk.BooleanVar(value=False)
        tk.Checkbutton(dialog, text="不再提醒，记住本次选择", variable=remember, bg=self.palette["PANEL"], fg=self.palette["INK"],
                       activebackground=self.palette["PANEL"], selectcolor=self.palette["PANEL"], font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=18, pady=18)
        row = tk.Frame(dialog, bg=self.palette["PANEL"])
        row.pack(fill="x", padx=22)
        def choose(hide):
            if not hide and self.busy:
                messagebox.showinfo("正在处理文件", "任务尚未完成，可以先隐藏到托盘。", parent=dialog)
                return
            if hide and (not self.tray or not self.tray.ok):
                messagebox.showinfo("系统托盘不可用", "托盘图标未能创建，请选择退出或取消。", parent=dialog)
                return
            if remember.get():
                self.hide_on_close.set(hide)
                self.save_close_behavior()
            dialog.destroy()
            self.hide_to_tray() if hide else self.exit_app()
        default = button(row, "隐藏到托盘", lambda: choose(True), True)
        default.pack(side="left")
        button(row, "退出程序", lambda: choose(False)).pack(side="left", padx=8)
        button(row, "取消", dialog.destroy).pack(side="right")
        default.focus_set()
        dialog.bind("<Return>", lambda _: choose(True))
        dialog.grab_set()

    def change_library_directory(self, target):
        target = target.resolve()
        validate_locations(self.catalogue.data_dir, target)
        target.mkdir(parents=True, exist_ok=True)
        probe = target / (".imagetag-write-" + str(os.getpid()))
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        # Commit the pointer first; no old image is moved or deleted.
        write_config(self.program_folder, self.catalogue.data_dir, target)
        with self.catalogue.connection() as db:
            db.execute("UPDATE sources SET kind='reference' WHERE kind='library'")
            db.execute("INSERT INTO sources(path,kind) VALUES (?, 'library') ON CONFLICT(path) DO UPDATE SET kind='library'", (os.path.normcase(str(target)),))
            db.execute("INSERT OR REPLACE INTO settings VALUES ('library_dir', ?)", (str(target),))
        self.catalogue.library_dir = target
        self.reload()
        self.notify("图片库位置已保存，旧图片仍保留关联")

    def change_data_directory(self, target, existing=False):
        if not self.editable() or self.update_busy or self.update_stage:
            self.notify("请先完成当前任务或更新，再切换数据目录")
            return
        previous = self.catalogue
        target = target.resolve()
        try:
            validate_locations(target, previous.library_dir)
        except ValueError as exc:
            messagebox.showerror("无法切换数据目录", str(exc), parent=self)
            return
        if self.opacity_timer:
            self.after_cancel(self.opacity_timer)
            self.persist_opacity()
        def move(_):
            if self.instance:
                self.instance.protect_legacy_data(target)
            if existing:
                details = inspect_database(target / "catalogue.sqlite3")
                library = Path(details["library_dir"])
                if not details["library_dir"] or not library.is_dir():
                    raise ValueError("目标数据中的图片库不可用，请连接原磁盘后重试。")
                validate_locations(target, library)
            else:
                migrate_data(previous.data_dir, target)
                library = previous.library_dir
            new = Catalogue(target, library)
            new.set_setting("library_dir", str(library))
            write_config(self.program_folder, target, library)
            return new
        def finish(new):
            self.dismiss_toast()
            self.catalogue = new
            self._saved_appearance = {}
            self.__dict__.pop("_accent_candidates", None)
            for handler in list(logging.getLogger().handlers):
                if isinstance(handler, logging.FileHandler):
                    logging.getLogger().removeHandler(handler)
                    handler.close()
            handler = logging.FileHandler(new.data_dir / "app.log", encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logging.getLogger().addHandler(handler)
            self.tag_filters.clear()
            self.gallery.selected.clear()
            self.auto_sync.set(new.setting("auto_sync", "1") == "1")
            self.sync_seconds.set(int(self.safe_number(new.setting("sync_seconds", "60"), 60, 15, 86400)))
            self.hide_on_close.set(new.setting("hide_on_close", "1") == "1")
            self.auto_update.set(new.setting("auto_update", "0") == "1")
            self.last_sync.set(new.setting("last_sync", "最近同步：尚未同步"))
            mode = new.setting("theme", "浅色")
            self.theme_mode.set({"白色": "浅色", "黑色": "深色", "跟随系统": "浅色"}.get(mode, mode) if mode in ("浅色", "深色", "自定义背景", "白色", "黑色", "跟随系统") else "浅色")
            accent = new.setting("custom_accent", "#6877bd")
            self.custom_accent.set(accent if re.fullmatch(r"#[0-9a-fA-F]{6}", accent) else "#6877bd")
            self.background_opacity.set(self.safe_number(new.setting("background_opacity", "45"), 45, 0, 100))
            from .backdrop import LAYOUTS
            layout = new.setting("background_layout", "覆盖")
            self.background_layout.set(layout if layout in LAYOUTS else "覆盖")
            for name, fallback, lower, upper in (("scale", 100, 10, 400), ("x", 0, -100, 100), ("y", 0, -100, 100)):
                getattr(self, "background_" + name).set(self.safe_number(new.setting("background_" + name, str(fallback)), fallback, lower, upper))
            self.load_background()
            self.reload()
            self.apply_theme()
            self.schedule_sync()
            settings = getattr(self, "_settings_window", None)
            if settings and settings.winfo_exists():
                settings.destroy()
            self.settings_dialog("存储与备份")
            self.notify("数据位置已切换并校验，原目录保留")
        from .app import Popup, label
        dialog = Popup(self, "正在切换数据位置", "490x170")
        label(dialog, "正在备份、迁移并校验数据…", size=14, bold=True).pack(anchor="w", padx=22, pady=(24, 12))
        label(dialog, "完成前请勿关闭程序；原目录会保留。", color=self.palette["MUTED"], size=10).pack(anchor="w", padx=22)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        dialog.unbind("<Escape>")
        dialog.grab_set()
        self.job_dialog = dialog
        self.run_job("切换数据目录", move, callback=finish)

    def after_restore(self, safety):
        # Portable startup location remains authoritative; JSON tag backups must
        # not redirect startup to an unrelated old computer's library.
        self.catalogue.set_setting("library_dir", str(self.catalogue.library_dir))
        self.reload()
        messagebox.showinfo("恢复完成", f"标签数据已恢复；图片移动后请重新定位。\n恢复前备份：\n{safety}", parent=self)

    def refresh_update_ui(self):
        dialog = getattr(self, "_settings_window", None)
        if dialog and dialog.winfo_exists():
            dialog.refresh_update()

    def check_updates(self, manual=False):
        if self.busy:
            self.notify("请等待当前任务完成后再检查更新")
            return
        if self.update_busy:
            self.notify("正在检查或下载更新")
            return
        if self.update_stage:
            self.settings_dialog("更新")
            self.notify("更新已经下载，可以重启并更新")
            return
        if not manual:
            last = self.safe_number(self.catalogue.setting("last_update_check", "0"), 0, 0, time.time() + 86400)
            if time.time() - last < 3600:
                self.notify("最近已检查过更新，可在设置中手动检查")
                return
        self.update_busy = True
        self.update_status.set("正在检查更新…")
        self.notify("正在检查更新…")
        self.refresh_update_ui()
        def work():
            try:
                release = updates.discover(__version__)
                self.events.put(("ui_call", lambda: done(release, None)))
            except Exception as exc:
                self.events.put(("ui_call", lambda error=str(exc): done(None, error)))
        def done(release, error):
            self.update_busy = False
            self.catalogue.set_setting("last_update_check", str(time.time()))
            if error:
                text = "GitHub 暂时限制了检查请求，请稍后重试或打开下载页。" if "403" in error or "429" in error else "更新检查未完成，请检查网络后重试。"
                self.update_status.set(text)
            elif release["available"]:
                self.release_info = release
                text = f"发现新版本 {release['version']}，可在设置中下载"
                self.update_status.set(text)
            else:
                self.release_info = None
                text = f"当前 v{__version__} 已是最新版本"
                self.update_status.set(text)
            self.notify(text, 8)
            self.refresh_update_ui()
            if manual:
                self.settings_dialog("更新")
        self.network_pool.submit(work)

    def download_update(self):
        if self.update_busy or not self.release_info:
            return
        self.update_busy = True
        self.update_status.set("开始下载更新…")
        self.refresh_update_ui()
        def progress(text):
            self.events.put(("ui_call", lambda value=text: self.update_status.set(value)))
        def work():
            try:
                stage = updates.prepare(self.release_info, self.catalogue.data_dir, progress)
                self.events.put(("ui_call", lambda: done(stage, None)))
            except Exception as exc:
                self.events.put(("ui_call", lambda error=str(exc): done(None, error)))
        def done(stage, error):
            self.update_busy = False
            self.update_stage = stage
            self.update_status.set("下载失败：" + error if error else "下载与校验完成。点击“重启并更新”安装，数据与图片库位置将保留。")
            self.notify("下载失败，可在设置中重试" if error else "新版已下载并校验，可重启更新")
            self.refresh_update_ui()
        self.network_pool.submit(work)

    def install_update(self):
        if not self.update_stage or self.update_busy:
            return
        if self.busy:
            self.notify("请等待扫描、导入或备份完成后再更新")
            return
        if not getattr(sys, "frozen", False):
            messagebox.showinfo("源码运行模式", "请使用打包后的 EXE 测试程序替换与重启。", parent=self)
            return
        try:
            # Persist any debounced appearance change before snapshotting the DB.
            if self.opacity_timer:
                self.after_cancel(self.opacity_timer)
                self.persist_opacity()
            write_config(self.program_folder, self.catalogue.data_dir, self.catalogue.library_dir)
            backup = update_backup(self.catalogue.data_dir)
            plan = updates.write_plan(self.update_stage, self.program_folder, self.catalogue.data_dir, self.catalogue.library_dir, backup)
            updates.launch_helper(self.update_stage, plan)
            self.exit_app(updating=True)
        except Exception as exc:
            messagebox.showerror("更新未开始", f"{exc}\n\n当前程序和用户数据保持不变。", parent=self)
