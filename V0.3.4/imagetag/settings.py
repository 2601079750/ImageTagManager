"""Scrollable settings pages for v0.3."""
from __future__ import annotations

import json
import os
import platform
import tkinter as tk
import time
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageTk

from . import __version__
from .app import Popup, button, label
from .appearance import ClickCombobox, animate_selection
from .updates import PROJECT_URL
from .backdrop import LAYOUTS

INTERVALS = {"15 秒": 15, "30 秒": 30, "1 分钟": 60, "5 分钟": 300, "10 分钟": 600}


class SettingsDialog(Popup):
    def __init__(self, app):
        super().__init__(app, "设置", "850x820")
        self.app = app
        self._glass_settings = True
        self.minsize(740, 560)
        self.palette = app.palette
        self.canvases = []
        label(self, "设置", size=20, bold=True).pack(anchor="w", padx=24, pady=(20, 3))
        label(self, "让拾图适合你的收藏习惯", color=self.palette["MUTED"]).pack(anchor="w", padx=24, pady=(0, 12))
        footer = tk.Frame(self, bg=self.palette["PANEL"])
        footer.pack(side="bottom", fill="x", padx=24, pady=(0, 14))
        label(footer, "设置立即生效 · 数据位置切换会先校验", color=self.palette["MUTED"], size=9).pack(side="left")
        button(footer, "完成", self.destroy).pack(side="right")
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=24, pady=(0, 14))
        self.pages, self.contents = {}, {}
        for name in ("外观", "同步与后台", "存储与备份", "更新", "关于"):
            page = tk.Frame(self.notebook, bg=self.palette["PANEL"])
            canvas = tk.Canvas(page, bg=self.palette["PANEL"], highlightthickness=0)
            scroll = ttk.Scrollbar(page, command=canvas.yview)
            canvas.configure(yscrollcommand=scroll.set, yscrollincrement=25)
            scroll.pack(side="right", fill="y")
            canvas.pack(fill="both", expand=True)
            content = tk.Frame(canvas, bg=self.palette["PANEL"], padx=20, pady=18)
            item = canvas.create_window(0, 0, window=content, anchor="nw")
            content.bind("<Configure>", lambda _, c=canvas: c.configure(scrollregion=c.bbox("all")))
            canvas.bind("<Configure>", lambda e, c=canvas, i=item: c.itemconfigure(i, width=e.width))
            self.pages[name], self.contents[name] = page, content
            self.canvases.append((canvas, content))
            self.notebook.add(page, text=name)
        # A toplevel binding sees child events without overriding the app's wheel guard.
        self.bind("<MouseWheel>", self.wheel, add="+")
        self.appearance_page()
        self.sync_page()
        self.storage_page()
        self.update_page()
        self.about_page()

    def wheel(self, event):
        if isinstance(event.widget, (ttk.Combobox, tk.Text, tk.Listbox)):
            return
        active = self.notebook.select()
        for canvas, _ in self.canvases:
            if str(canvas.master) == active and canvas.winfo_height() < canvas.bbox("all")[3]:
                canvas.yview_scroll(-int(event.delta / 120) * 2, "units")
                self.app.backdrop.schedule(window=self)

    def heading(self, parent, text):
        label(parent, text, size=13, bold=True).pack(anchor="w", pady=(0, 8))

    def note(self, parent, text):
        result = label(parent, text, color=self.app.palette["MUTED"], size=9, wraplength=650, justify="left")
        result.pack(anchor="w", pady=(0, 12))
        return result

    def row(self, parent, pady=5):
        result = tk.Frame(parent, bg=self.app.palette["PANEL"])
        result.pack(fill="x", pady=pady)
        return result

    def check(self, parent, text, variable, command):
        p = self.app.palette
        result = tk.Checkbutton(parent, text=text, variable=variable, command=command, bg=p["PANEL"], fg=p["INK"],
                                activebackground=p["PANEL"], activeforeground=p["INK"], selectcolor=p["PANEL"],
                                font=("Microsoft YaHei UI", 10), cursor="hand2", anchor="w")
        result._foreground_role = "INK"
        result.pack(anchor="w", pady=(0, 8))
        return result

    def appearance_page(self):
        app = self.app
        page = self.contents["外观"]
        self.heading(page, "主题")
        self.theme_combo = ClickCombobox(page, textvariable=app.theme_mode, values=("浅色", "深色", "自定义背景"), state="readonly", width=18)
        self.theme_combo.pack(anchor="w", pady=(0, 10))
        self.theme_combo.bind("<<ComboboxSelected>>", lambda _: self.change_theme())
        ttk.Separator(page).pack(fill="x", pady=(3, 14))
        self.heading(page, "自定义背景")
        self.background_text = self.note(page, "")
        row = self.row(page)
        self.choose_background_button = button(row, "选择背景图片…", self.choose_background)
        self.choose_background_button.pack(side="left")
        self.reset_background_button = button(row, "恢复默认", self.reset_background)
        self.reset_background_button.pack(side="left", padx=8)
        row = self.row(page, 10)
        label(row, "背景不透明度").pack(side="left")
        self.opacity_label = label(row, "")
        self.opacity_label.pack(side="right")
        self.opacity_scale = ttk.Scale(row, from_=0, to=100, variable=app.background_opacity, command=self.opacity_changed)
        self.opacity_scale.pack(side="left", fill="x", expand=True, padx=16)
        row = self.row(page)
        label(row, "填充方式").pack(side="left", padx=(0, 18))
        self.layout_combo = ClickCombobox(row, textvariable=app.background_layout, values=LAYOUTS, state="readonly", width=12)
        self.layout_combo.pack(side="left")
        self.layout_combo.bind("<<ComboboxSelected>>", lambda _: self.layout_changed())
        self.free_frame = self.row(page)
        self.free_scales = []
        for text, variable, lower, upper in (("缩放", app.background_scale, 10, 400),
                                             ("水平位置", app.background_x, -100, 100),
                                             ("垂直位置", app.background_y, -100, 100)):
            row = self.row(self.free_frame, 2)
            label(row, text).pack(side="left", padx=(0, 16))
            readout = label(row, "", size=9)
            readout.pack(side="right")
            def preview(_, v=variable, out=readout):
                out.configure(text=f"{v.get():.0f}%")
                app.schedule_background_opacity()
            scale = ttk.Scale(row, from_=lower, to=upper, variable=variable, command=preview)
            scale.pack(side="left", fill="x", expand=True)
            preview(None)
            self.free_scales.append(scale)
        self.color_heading = self.row(page, (14, 5))
        self.heading(self.color_heading, "主题色")
        self.swatch_row = self.row(page)
        self.swatches = []
        self.refresh_appearance_controls()

    def change_theme(self):
        self.app.apply_theme()
        self.refresh_appearance_controls()

    def refresh_appearance_controls(self):
        custom = self.app.theme_mode.get() == "自定义背景"
        for widget in (self.choose_background_button, self.reset_background_button, self.opacity_scale, *self.free_scales):
            widget.configure(state="normal" if custom else "disabled")
        self.layout_combo.configure(state="readonly" if custom else "disabled")
        if custom and self.app.background_layout.get() == "自由":
            self.free_frame.pack(fill="x", pady=5, before=self.color_heading)
        else:
            self.free_frame.pack_forget()
        self.background_text.configure(text=self.app.catalogue.setting("background_name", "尚未选择背景图片"))
        self.opacity_label.configure(text=f"{self.app.background_opacity.get():.0f}%")
        colors = self.app.accent_candidates()
        if not self.swatches:
            self.swatches = [self.color_swatch(self.choose_accent) for _ in colors]
            self.custom_swatch = self.color_swatch(lambda _: self.custom_color())
        for canvas, color in zip(self.swatches, colors):
            self.paint_swatch(canvas, color, self.app.custom_accent.get().lower() == color.lower())
        self.paint_swatch(self.custom_swatch, None,
            self.app.custom_accent.get().lower() not in [c.lower() for c in colors])

    def color_swatch(self, command):
        p = self.app.palette
        canvas = tk.Canvas(self.swatch_row, width=48, height=48, bg=p["PANEL"],
                           highlightthickness=0, cursor="hand2", takefocus=True)
        canvas.pack(side="left", padx=(0, 14))
        canvas.icon_item = canvas.create_image(0, 0, anchor="nw")
        canvas.bind("<Button-1>", lambda _: command(canvas.color))
        canvas.bind("<space>", lambda _: command(canvas.color))
        canvas.bind("<Return>", lambda _: command(canvas.color))
        return canvas

    def paint_swatch(self, canvas, color, selected):
        p = self.app.palette
        canvas.color = color
        canvas.selected = selected
        canvas._opaque_surface = False
        canvas._paint_surface = lambda: self.paint_swatch(canvas, canvas.color, canvas.selected)
        key = (self.app.backdrop.revision, canvas.winfo_rootx(), canvas.winfo_rooty(),
               color, selected, getattr(canvas, "selection_progress", 1))
        if getattr(canvas, "_swatch_key", None) == key:
            return
        canvas._swatch_key = key
        canvas.configure(bg=p["PANEL"])
        image = Image.new("RGBA", (192, 192))
        draw = ImageDraw.Draw(image)
        if selected:
            progress = getattr(canvas, "selection_progress", 1)
            inset = round(12*(1-progress))
            draw.ellipse((5+inset, 5+inset, 187-inset, 187-inset), outline=p["ACCENT_INK"], width=7)
        draw.ellipse((22, 22, 170, 170), fill=color or p["SURFACE"], outline=color or p["LINE"], width=5)
        if color is None:
            draw.line((96, 64, 96, 128), fill=p["INK"], width=9)
            draw.line((64, 96, 128, 96), fill=p["INK"], width=9)
        elif selected:
            ink = "#ffffff" if self.app.color_contrast(color, "#ffffff") > 4.5 else "#17202e"
            draw.line(((65, 96), (86, 117), (129, 74)), fill=ink, width=9, joint="curve")
        icon = image.resize((48, 48), Image.Resampling.LANCZOS)
        icon = self.app.backdrop.composite(self.app.backdrop.crop(canvas, (48, 48)), icon)
        canvas.photo = ImageTk.PhotoImage(icon, master=canvas)
        canvas.itemconfigure(canvas.icon_item, image=canvas.photo)

    def layout_changed(self):
        self.app.schedule_background_opacity()
        self.refresh_appearance_controls()

    def choose_background(self):
        path = filedialog.askopenfilename(parent=self, title="选择背景图片", filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp *.avif")])
        if path:
            try:
                self.app.set_background(Path(path))
                self.refresh_appearance_controls()
            except Exception as exc:
                messagebox.showerror("无法设置背景", str(exc), parent=self)

    def reset_background(self):
        self.app.reset_background()
        self.refresh_appearance_controls()

    def opacity_changed(self, _):
        self.opacity_label.configure(text=f"{self.app.background_opacity.get():.0f}%")
        self.app.schedule_background_opacity()

    def choose_accent(self, color, *, persist=True):
        if self.app.custom_accent.get().lower() == color.lower():
            return
        self.app.custom_accent.set(color)
        if persist:
            self.app.save_appearance()
        else:
            self.app.apply_theme(persist=False)
        for canvas in (*self.swatches, self.custom_swatch):
            selected = (canvas.color.lower() == color.lower() if canvas.color else
                        color.lower() not in [w.color.lower() for w in self.swatches])
            self.paint_swatch(canvas, canvas.color, selected)
            if selected:
                def draw(progress, swatch=canvas):
                    swatch.selection_progress = progress
                    self.paint_swatch(swatch, swatch.color, swatch.selected)
                animate_selection(canvas, draw)

    def custom_color(self):
        return self.app.color_dialog(self, self.choose_accent,
                                     lambda color: self.choose_accent(color, persist=False))

    def sync_page(self):
        app = self.app
        page = self.contents["同步与后台"]
        self.heading(page, "自动同步")
        self.note(page, "检查图片库与引用目录中的变化；隐藏到托盘后继续同步。扫描未完成时不会重复启动。")
        self.auto_sync_check = self.check(page, "启用自动同步", app.auto_sync, app.save_auto_sync)
        row = self.row(page)
        label(row, "检查间隔").pack(side="left", padx=(0, 14))
        seconds = app.sync_seconds.get()
        custom = app.catalogue.setting("sync_interval_mode", "preset") == "custom" or seconds not in INTERVALS.values()
        self.interval = tk.StringVar(value="" if custom else next((name for name, value in INTERVALS.items() if value == seconds), ""))
        self.interval_combo = ClickCombobox(row, textvariable=self.interval, values=tuple(INTERVALS), width=14, state="readonly")
        self.interval_combo.pack(side="left")
        self.interval_combo.bind("<<ComboboxSelected>>", lambda _: self.interval_changed())
        self.custom_interval_row = self.row(page)
        label(self.custom_interval_row, "自定义间隔：").pack(side="left", padx=(0, 8))
        self.custom_time = tk.StringVar(value=str(seconds // 60 if seconds % 60 == 0 else seconds) if custom else "")
        self.custom_unit = tk.StringVar(value="分钟" if seconds % 60 == 0 else "秒")
        ttk.Entry(self.custom_interval_row, textvariable=self.custom_time, width=9).pack(side="left")
        ClickCombobox(self.custom_interval_row, textvariable=self.custom_unit, values=("秒", "分钟"), state="readonly", width=7).pack(side="left", padx=8)
        label(self.custom_interval_row, "最短 15 秒，最长 24 小时", color=app.palette["MUTED"], size=9).pack(side="left", padx=12)
        self.interval_hint = label(page, "", color=app.palette["MUTED"], size=9)
        self.interval_hint.pack(anchor="w", pady=(3, 0))
        self._interval_guard = False
        self._interval_timer = None
        self.custom_time.trace_add("write", self.custom_interval_edited)
        self.custom_unit.trace_add("write", self.custom_interval_edited)
        self.last_sync_label = label(page, textvariable=app.last_sync, color=app.palette["MUTED"], size=9)
        self.last_sync_label.pack(anchor="w", pady=(10, 24))
        self.heading(page, "关闭窗口")
        self.check(page, "单击关闭时隐藏到托盘", app.hide_on_close, app.save_close_behavior)
        self.note(page, "托盘菜单可恢复窗口或退出。系统托盘不可用时不会隐藏窗口。")
        button(page, "恢复关闭时询问", lambda: (app.catalogue.set_setting("close_prompt", "1"), app.notify("下次关闭时会再次询问"))).pack(anchor="w")

    def interval_changed(self, save=True):
        if save and self.interval.get() in INTERVALS:
            if self._interval_timer:
                self.after_cancel(self._interval_timer)
                self._interval_timer = None
            self._interval_guard = True
            self.custom_time.set("")
            self._interval_guard = False
            self.interval_hint.configure(text="")
            self.app.catalogue.set_setting("sync_interval_mode", "preset")
            self.app.sync_seconds.set(INTERVALS[self.interval.get()])
            self.app.save_auto_sync()

    def custom_interval_edited(self, *_):
        if self._interval_guard:
            return
        self.interval.set("")
        if self._interval_timer:
            self.after_cancel(self._interval_timer)
        self._interval_timer = self.after(350, self.save_custom_interval)

    def save_custom_interval(self):
        self._interval_timer = None
        try:
            seconds = int(self.custom_time.get()) * (60 if self.custom_unit.get() == "分钟" else 1)
            if not 15 <= seconds <= 86400:
                raise ValueError()
        except ValueError:
            self.interval_hint.configure(text="请输入 15 秒至 24 小时之间的整数；当前仍沿用上一次有效间隔。")
            return
        self.app.sync_seconds.set(seconds)
        self.app.catalogue.set_setting("sync_interval_mode", "custom")
        self.app.save_auto_sync()
        self.interval_hint.configure(text=f"已应用：{seconds} 秒")

    def destroy(self):
        color_dialog = getattr(self.app, "_color_dialog", None)
        if color_dialog and color_dialog.preview_parent is self:
            color_dialog.destroy()
        if getattr(self, "_interval_timer", None):
            self.after_cancel(self._interval_timer)
            self.save_custom_interval()
        self.app.persist_opacity()
        super().destroy()

    def storage_page(self):
        app = self.app
        page = self.contents["存储与备份"]
        self.heading(page, "应用数据")
        self.data_path = self.note(page, str(app.catalogue.data_dir))
        self.note(page, "标签、设置、缩略图、日志、备份与背景图保存在这里。迁移完成并校验后切换，旧目录保留。")
        row = self.row(page)
        button(row, "迁移当前数据…", lambda: self.change_data(False)).pack(side="left")
        button(row, "使用已有数据…", lambda: self.change_data(True)).pack(side="left", padx=8)
        ttk.Separator(page).pack(fill="x", pady=16)
        self.heading(page, "图片库")
        self.library_path = self.note(page, str(app.catalogue.library_dir))
        self.note(page, "后续复制或移动导入的原图存放于此。更改位置不会搬动旧图片，旧位置仍作为来源保留。")
        button(page, "更改图片库位置…", self.change_library).pack(anchor="w")
        ttk.Separator(page).pack(fill="x", pady=16)
        self.heading(page, "标签数据备份")
        self.note(page, "备份包含标签、类别、图片路径和指纹，不包含原图。图片移动后可重新定位；恢复前会自动备份当前数据。")
        row = self.row(page)
        self.export_button = button(row, "导出备份…", self.export_backup, True)
        self.export_button.pack(side="left")
        self.restore_button = button(row, "从备份恢复…", self.restore_backup)
        self.restore_button.pack(side="left", padx=8)

    def change_data(self, existing):
        if not self.app.editable():
            return
        path = filedialog.askdirectory(parent=self, title="选择已有数据目录" if existing else "选择空文件夹接收当前数据")
        if path:
            self.app.change_data_directory(Path(path), existing)

    def change_library(self):
        if not self.app.editable():
            return
        path = filedialog.askdirectory(parent=self, title="选择图片库位置")
        if path:
            try:
                self.app.change_library_directory(Path(path))
                self.library_path.configure(text=str(self.app.catalogue.library_dir))
            except Exception as exc:
                messagebox.showerror("无法更改图片库", str(exc), parent=self)

    def export_backup(self):
        if not self.app.editable():
            return
        path = filedialog.asksaveasfilename(parent=self, title="保存标签备份", defaultextension=".json",
                                          initialfile=f"拾图备份-{time.strftime('%Y%m%d')}.json", filetypes=[("标签备份", "*.json")])
        if path:
            self.destroy()
            self.app.run_job("备份标签数据", lambda _: self.app.catalogue.backup(Path(path)))

    def restore_backup(self):
        if not self.app.editable():
            return
        path = filedialog.askopenfilename(parent=self, title="选择标签备份", filetypes=[("标签备份", "*.json")])
        if path and messagebox.askyesno("恢复标签备份", "恢复会替换当前标签库，原图不变。恢复前会先备份当前数据。确定继续吗？", parent=self):
            self.destroy()
            self.app.run_job("恢复标签数据", lambda _: self.app.catalogue.restore(Path(path)), callback=self.app.after_restore)

    def update_page(self):
        app = self.app
        page = self.contents["更新"]
        self.heading(page, f"当前版本 v{__version__}")
        self.check(page, "每次启动自动检查更新", app.auto_update, lambda: app.catalogue.set_setting("auto_update", "1" if app.auto_update.get() else "0"))
        self.note(page, "默认关闭。检查与下载连接 GitHub；无网络时仍可正常管理本地收藏。")
        row = self.row(page)
        self.check_update_button = button(row, "检查更新", lambda: app.check_updates(manual=True), True)
        self.check_update_button.pack(side="left")
        self.download_button = button(row, "下载新版", app.download_update)
        self.download_button.pack(side="left", padx=8)
        self.install_button = button(row, "重启并更新", app.install_update)
        self.install_button.pack(side="left")
        button(row, "打开下载页 ↗", lambda: webbrowser.open(PROJECT_URL + "/releases/latest")).pack(side="left", padx=8)
        label(page, textvariable=app.update_status, wraplength=650, justify="left", color=app.palette["MUTED"]).pack(anchor="w", pady=(10, 8))
        self.notes = tk.Text(page, height=10, wrap="word", bg=app.palette["SURFACE"], fg=app.palette["INK"],
                             font=("Microsoft YaHei UI", 9), relief="flat", padx=12, pady=10)
        self.notes.pack(fill="both", expand=True, pady=(5, 10))
        button(page, "查看当前版本更新日志", self.current_notes).pack(anchor="w")
        self.refresh_update()

    def current_notes(self):
        self.notes.configure(state="normal")
        resources = self.app.resource_dir()
        try:
            text = (resources / "RELEASE_NOTES.md").read_text(encoding="utf-8")
        except OSError:
            text = f"拾图 v{__version__}\n当前版本更新日志暂不可用。"
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", text)
        self.notes.configure(state="disabled")

    def refresh_update(self):
        app = self.app
        self.check_update_button.configure(state="disabled" if app.update_busy else "normal")
        self.download_button.configure(state="normal" if app.release_info and not app.update_busy and not app.update_stage else "disabled")
        self.install_button.configure(state="normal" if app.update_stage and not app.update_busy else "disabled")
        if app.release_info:
            self.notes.configure(state="normal")
            self.notes.delete("1.0", "end")
            self.notes.insert("1.0", app.release_info["version"] + "\n\n" + app.release_info["notes"])
            self.notes.configure(state="disabled")
        else:
            self.current_notes()

    def about_page(self):
        page = self.contents["关于"]
        self.heading(page, "拾图 · ImageTagManager")
        self.note(page, f"版本 v{__version__}\n离线整理收藏，让每张图片都有迹可寻。")
        row = self.row(page)
        button(row, "GitHub 项目主页 ↗", lambda: webbrowser.open(PROJECT_URL)).pack(side="left")
        button(row, "提交 GitHub Issue ↗", lambda: webbrowser.open(PROJECT_URL + "/issues/new")).pack(side="left", padx=8)
        ttk.Separator(page).pack(fill="x", pady=18)
        self.heading(page, "反馈与建议")
        self.note(page, "邮箱：yh.gao0520@qq.com")
        row = self.row(page)
        button(row, "撰写邮件 ↗", lambda: webbrowser.open("mailto:yh.gao0520@qq.com?subject=ImageTagManager%20v" + __version__)).pack(side="left")
        button(row, "复制邮箱", lambda: self.copy("yh.gao0520@qq.com")).pack(side="left", padx=8)
        button(row, "复制版本与系统信息", lambda: self.copy(f"ImageTagManager v{__version__}\n{platform.platform()}\nPython {platform.python_version()}\n架构 {platform.machine()}")).pack(side="left")
        self.note(page, "图库功能离线运行；检查更新、打开项目主页或撰写邮件由你主动控制。")

    def copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.notify("已复制")
