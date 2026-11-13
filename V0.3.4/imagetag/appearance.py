"""Palette and Windows appearance helpers; no external UI dependencies."""
from __future__ import annotations

import os
import ctypes
import time
import tkinter as tk
from tkinter import ttk


def animate_selection(widget, draw, duration=120):
    """Animate only a small selection surface; never fade a whole window."""
    previous = getattr(widget, "_selection_timer", None)
    if previous:
        widget.after_cancel(previous)
    if not getattr(widget, "_selection_destroy_bound", False):
        def cancel(event):
            if event.widget is widget and getattr(widget, "_selection_timer", None):
                widget.after_cancel(widget._selection_timer)
                widget._selection_timer = None
        widget.bind("<Destroy>", cancel, add="+")
        widget._selection_destroy_bound = True
    enabled = ctypes.c_int(1)
    if os.name == "nt":
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
    start = time.perf_counter()
    def frame():
        widget._selection_timer = None
        progress = min(1, (time.perf_counter()-start)*1000/duration) if enabled.value else 1
        draw(1-(1-progress)**3)
        if progress < 1:
            widget._selection_timer = widget.after(16, frame)
    frame()

PALETTES = {
    "白色": dict(BG="#f3f5fa", PANEL="#ffffff", INK="#202b40", MUTED="#6e7b93",
                 ACCENT="#5865dc", LINE="#e2e7f1", SURFACE="#edf0f7", SELECT="#e9edff",
                 ROW_SELECT="#c3ccff", ROW_SELECT_INK="#26377c",
                 HOVER="#e1e6fa", WARNING="#fff0e5", WARNING_INK="#a65b29", PRIMARY_INK="#fefeff"),
    "黑色": dict(BG="#131722", PANEL="#1c2230", INK="#edf0f8", MUTED="#a2aec5",
                 ACCENT="#a2abff", LINE="#343e52", SURFACE="#252d3e", SELECT="#333e65",
                 ROW_SELECT="#5364a6", ROW_SELECT_INK="#f7f8ff",
                 HOVER="#3d4966", WARNING="#49372c", WARNING_INK="#ffc393", PRIMARY_INK="#141a2d"),
}
for _palette in PALETTES.values():
    _palette["ACCENT_INK"] = _palette["ACCENT"]


def system_theme() -> str:
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                return "白色" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "黑色"
        except OSError:
            pass
    return "白色"


class ClickCombobox(ttk.Combobox):
    """Ignore wheel selection changes, including when the control has focus."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind(sequence, lambda event: "break")
        self.configure(postcommand=self.style_dropdown)

    def style_dropdown(self):
        # Popups inherit the application's complete custom palette as well.
        root = self._root()
        palette = getattr(root, "palette", PALETTES["白色"])
        path = self.tk.call("ttk::combobox::PopdownWindow", str(self)) + ".f.l"
        self.tk.call(path, "configure", "-background", palette["PANEL"], "-foreground", palette["INK"],
                     "-selectbackground", palette["SELECT"], "-selectforeground", palette["INK"],
                     "-font", "{Microsoft YaHei UI} 10")
