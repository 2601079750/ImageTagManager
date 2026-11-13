"""Background-composited views that keep native Tk controls as their model.

Only the visible surface changes: selection, focus, keyboard traversal, tree
expansion, scrolling, commands and accessibility remain on the native widget.
"""
from __future__ import annotations

import tkinter as tk
import ctypes
import os
from ctypes import wintypes
from tkinter import ttk
from tkinter import font as tkfont
from PIL import Image, ImageDraw, ImageTk

from .colors import contrast, hex_color, luminance


def readable_panel(picture, foreground, opacity=.55, minimum=4.5):
    """Composite a light veil, increasing it only if the text needs contrast.

    Channel extrema give a conservative bound even for highly patterned art.
    The text itself is never rasterized into the wallpaper or made translucent.
    """
    veil = Image.new("RGB", picture.size, "#ffffff")
    while True:
        result = Image.blend(picture.convert("RGB"), veil, opacity)
        darkest = hex_color(channel[0] for channel in result.getextrema())
        if contrast(foreground, darkest) >= minimum or opacity >= 1:
            return result
        opacity = min(1, opacity + .05)


def readable_text_surface(picture, preferred, opacity=0):
    """Use light text on a dark picture before adding a local light backing."""
    result = Image.blend(picture.convert("RGB"), Image.new("RGB", picture.size, "white"), opacity)
    extrema = result.getextrema()
    darkest = hex_color(channel[0] for channel in extrema)
    brightest = hex_color(channel[1] for channel in extrema)
    # For dark text the darkest background is the conservative bound; for white
    # text the brightest background is the conservative bound.
    for ink in (preferred, "#ffffff", "#202b40"):
        outside = luminance(ink) < luminance(darkest) or luminance(ink) > luminance(brightest)
        if outside and min(contrast(ink, darkest), contrast(ink, brightest)) >= 4.5:
            return result, ink
    return readable_panel(picture, "#202b40", opacity), "#202b40"


class GlassSurface:
    def __init__(self, widget, backdrop):
        self.widget, self.backdrop = widget, backdrop
        self.revision = 0
        self.key = None
        self.hover = False
        self.canvas = tk.Canvas(widget, bd=0, highlightthickness=0, takefocus=False,
                                cursor=widget.cget("cursor") if widget.cget("cursor") else "arrow")
        self.canvas._wallpaper_layer = True
        if os.name == "nt":
            # Native Tk labels/buttons otherwise paint over their child canvas
            # after geometry changes. Let Windows clip that occupied region.
            user = ctypes.windll.user32
            user.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
            user.GetWindowLongW.restype = wintypes.LONG
            user.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
            user.SetWindowLongW.restype = wintypes.LONG
            handle = widget.winfo_id()
            user.SetWindowLongW(handle, -16, user.GetWindowLongW(handle, -16) | 0x02000000)
        self.original = str(widget) + "_native_surface"
        self.notifier = str(widget) + "_surface_changed"
        widget.tk.call("rename", str(widget), self.original)
        widget.tk.createcommand(self.notifier, self.dispatch)
        # Keep native command errors entirely in Tcl. Raising TclError from a
        # Python createcommand callback also sets _tkinter's deferred exception
        # flag: even a caught unsupported-option query then aborts mainloop.
        widget.tk.call("proc", str(widget), "args",
                       f"set result [uplevel 1 [linsert $args 0 {self.original}]]\n"
                       f"if {{[llength [info commands {self.notifier}]]}} {{\n"
                       f"    {self.notifier} {{*}}$args\n}}\nreturn $result")
        widget.bind("<Destroy>", self.destroy, add="+")
        widget.bind("<FocusIn>", self.changed, add="+")
        widget.bind("<FocusOut>", self.changed, add="+")
        widget.bind("<Expose>", self.exposed, add="+")
        for sequence in ("<ButtonPress-1>", "<ButtonRelease-1>", "<B1-Motion>",
                         "<ButtonPress-2>", "<B2-Motion>", "<MouseWheel>"):
            self.canvas.bind(sequence, lambda e, s=sequence: self.forward(e, s))
        for sequence, value in (("<Enter>", True), ("<Leave>", False)):
            self.canvas.bind(sequence, lambda e, v=value: self.enter(e, v))

    def dispatch(self, *args):
        op = args[0] if args else ""
        mutation = op in ("insert", "delete", "activate", "see", "invoke")
        mutation |= op in ("configure", "itemconfigure") and len(args) > 2
        mutation |= op in ("yview", "xview", "focus") and len(args) > 1
        mutation |= op == "item" and len(args) > 3
        mutation |= op == "selection" and len(args) > 1 and args[1] not in ("includes",)
        if mutation:
            self.changed()

    def changed(self, _=None):
        self.revision += 1
        self.backdrop.schedule(window=self.widget.winfo_toplevel())

    def exposed(self, _=None):
        # Tk's native button/label paint can cover its child canvas after a
        # details-panel resize or state change. Repaint the existing display
        # image even when its contents and geometry have not changed.
        if self.canvas.winfo_ismapped():
            self.canvas.itemconfigure("all", state="normal")

    def destroy(self, event):
        if event.widget is self.widget:
            self.widget.tk.call("rename", str(self.widget), "")
            self.widget.tk.deletecommand(self.notifier)

    def forward(self, event, sequence):
        if isinstance(self.widget, (tk.Button, tk.Checkbutton)) and str(self.widget.cget("state")) == "disabled":
            return "break"
        if sequence == "<ButtonPress-1>":
            self.widget.focus_set()
        options = dict(x=event.x, y=event.y, state=event.state, time=event.time)
        if sequence == "<MouseWheel>":
            options["delta"] = event.delta
        self.widget.event_generate(sequence, **options)
        self.changed()
        return "break"

    def enter(self, event, value):
        self.hover = value
        self.widget.event_generate("<Enter>" if value else "<Leave>", x=event.x, y=event.y)
        self.changed()

    def text(self, x, y, *, text, fill, font, anchor="center", width=0, justify="center"):
        return self.backdrop.text(self.canvas, x, y, text=text, fill=fill,
                                  font=font, anchor=anchor, width=width, justify=justify)

    def render(self, custom):
        w, canvas, p = self.widget, self.canvas, self.backdrop.app.palette
        if not custom:
            canvas.place_forget()
            self.key = None
            return
        # Combobox popup lists exist only in Tcl, so focus_get() cannot resolve
        # their path through Python's nametowidget(). Compare Tcl paths instead.
        focused = str(w.tk.call("focus", "-displayof", str(w))) == str(w)
        palette_key = (p["PANEL"],) if isinstance(w, tk.Label) else tuple(p.values())
        window = w.winfo_toplevel()
        key = (self.revision, self.backdrop.wallpaper_key(window), palette_key,
               w.winfo_width(), w.winfo_height(),
               w.winfo_rootx()-window.winfo_rootx(), w.winfo_rooty()-window.winfo_rooty(), focused, self.hover,
               str(w.cget("text")) if isinstance(w, tk.Label) else "",
               str(w.getvar(w.cget("textvariable"))) if isinstance(w, tk.Label) and w.cget("textvariable") else "")
        if key == self.key:
            return
        self.key = key
        canvas.place(x=0, y=0, relwidth=1, relheight=1, bordermode="outside")
        canvas.tk.call("raise", str(canvas))
        picture = self.backdrop.crop(w)
        if picture is None:
            return
        canvas.delete("all")
        canvas.configure(background=p["PANEL"])
        width, height = picture.size
        ink = p["INK"]
        if isinstance(w, (tk.Label, tk.Button, tk.Checkbutton)):
            foreground = str(w.cget("fg"))
            primary = getattr(w, "_primary_action", False)
            selected = getattr(w, "_selected_navigation", False)
            disabled = str(w.cget("state")) == "disabled"
            if disabled:
                foreground = p["MUTED"]
            # Only the three main actions and persistent selections have a fill.
            fill = p["ACCENT"] if primary else p["SELECT"] if selected else p["HOVER"] if self.hover and not disabled and not isinstance(w, tk.Label) else None
            if fill:
                layer = Image.new("RGBA", (width*3, height*3))
                ImageDraw.Draw(layer).rounded_rectangle((0, 0, width*3-1, height*3-1), radius=21, fill=fill)
                layer = layer.resize(picture.size, Image.Resampling.LANCZOS)
                picture = self.backdrop.composite(picture, layer)
            if primary:
                foreground = p["PRIMARY_INK"]
            elif selected:
                foreground = p["ACCENT_INK"] if contrast(p["ACCENT_INK"], p["SELECT"]) >= 4.5 else ink
            self.photo = ImageTk.PhotoImage(picture, master=canvas)
            canvas.create_image(0, 0, image=self.photo, anchor="nw")
            line = p["MUTED"] if disabled else p["ACCENT_INK"] if focused or self.hover else p["MUTED"]
            if isinstance(w, tk.Checkbutton):
                selected = str(w.getvar(w.cget("variable"))) == str(w.cget("onvalue"))
                y = height // 2
                canvas.create_rectangle(3, y-7, 17, y+7, outline=line,
                                        fill=p["ACCENT"] if selected else "")
                if selected:
                    canvas.create_line(6, y, 10, y+4, 15, y-4, fill=p["PRIMARY_INK"], width=2)
                self.text(25, y, text=w.cget("text"), fill=foreground,
                                   font=w.cget("font"), anchor="w")
            else:
                text = w.cget("text")
                if isinstance(w, tk.Label) and w.cget("textvariable"):
                    text = w.getvar(w.cget("textvariable"))
                anchor = str(w.cget("anchor"))
                west = anchor in ("w", "nw", "sw")
                east = anchor in ("e", "ne", "se")
                x = 4 if west else width-4 if east else width/2
                options = {}
                if isinstance(w, tk.Label):
                    options = dict(width=int(w.cget("wraplength")) or 0, justify=w.cget("justify"))
                self.text(x, height/2, text=text, fill=foreground, font=w.cget("font"),
                                   anchor="w" if west else "e" if east else "center", **options)
                if focused and not isinstance(w, tk.Label):
                    canvas.create_line(8, height-2, width-8, height-2, fill=p["ACCENT_INK"])
            return
        self.photo = ImageTk.PhotoImage(picture, master=canvas)
        canvas.create_image(0, 0, image=self.photo, anchor="nw")
        if isinstance(w, ttk.Treeview) and 'tree' not in tuple(map(str, w.tk.splitlist(w.cget('show')))):
            self.table_rows(width, height, ink)
        elif isinstance(w, tk.Listbox):
            selected = set(w.curselection())
            if w.size():
                for i in range(max(0, w.nearest(0)), min(w.size(), w.nearest(height)+1)):
                    box = w.bbox(i)
                    if not box:
                        continue
                    x, y, _, row_height = box
                    if i in selected:
                        canvas.create_rectangle(1, y, width-1, y+row_height, fill=p["ROW_SELECT"], outline="")
                    self.text(7, y+row_height/2, anchor="w", text=w.get(i),
                                       font=w.cget("font"), fill=p["ROW_SELECT_INK"] if i in selected else ink)
        else:
            def rows(parent="", depth=0):
                for item in w.get_children(parent):
                    yield item, depth
                    if w.item(item, "open"):
                        yield from rows(item, depth+1)
            font = ttk.Style(w).lookup("Treeview", "font")
            for item, depth in rows():
                box = w.bbox(item)
                if not box:
                    continue
                _, y, _, row_height = box
                if y+row_height < 0 or y > height:
                    continue
                text = w.item(item, "text")
                checked = text.startswith("☑")
                if checked:
                    canvas.create_rectangle(1, y, width-1, y+row_height, fill=p["ROW_SELECT"], outline="")
                x = 8+depth*20
                if w.get_children(item):
                    points = (x, y+11, x+8, y+11, x+4, y+16) if w.item(item, "open") else (x+2, y+8, x+2, y+18, x+7, y+13)
                    canvas.create_polygon(points, fill=ink)
                self.text(x+14, y+row_height/2, anchor="w", text=text, font=font,
                                   fill=p["ROW_SELECT_INK"] if checked else ink)
        canvas.create_rectangle(0, 0, width-1, height-1,
                                outline=p["ACCENT_INK"] if focused else p["LINE"], width=1)

    def table_rows(self, width, height, ink):
        """Column tables retain native hit testing, scrolling and clear Tk text."""
        w, canvas, p = self.widget, self.canvas, self.backdrop.app.palette
        columns = tuple(w.cget('columns'))
        font = ttk.Style(w).lookup('Treeview', 'font')
        metrics = getattr(self, '_table_metrics', None)
        if metrics is None or self._table_font != font:
            metrics = self._table_metrics = tkfont.Font(root=w, font=font)
            self._table_font = font

        def fit(text, available):
            text = str(text)
            if metrics.measure(text) <= available:
                return text
            low, high = 0, len(text)
            while low < high:
                mid = (low + high + 1) // 2
                if metrics.measure(text[:mid] + '…') <= available:
                    low = mid
                else:
                    high = mid - 1
            return text[:low] + '…' if available >= metrics.measure('…') else ''

        header_height = 29
        for item in w.get_children():
            box = w.bbox(item)
            if box:
                header_height = min(header_height, max(1, box[1]))
                break
        widths = [int(w.column(c, 'width')) for c in columns]
        x = -round(w.xview()[0] * sum(widths))
        for column, size in zip(columns, widths):
            caption = fit(w.heading(column, 'text'), size - 12)
            self.text(x + size / 2, header_height / 2, text=caption, fill=p['MUTED'], font=font)
            x += size
        canvas.create_line(0, header_height, width, header_height, fill=p['LINE'])
        selected = set(w.selection())
        for item in w.get_children():
            box = w.bbox(item)
            if not box or box[1] < header_height or box[1] >= height:
                continue
            _, y, _, row_height = box
            if item in selected:
                canvas.create_rectangle(1, y, width - 1, y + row_height, fill=p['ROW_SELECT'], outline='')
            values = w.item(item, 'values')
            for index, column in enumerate(columns):
                cell = w.bbox(item, column)
                if not cell:
                    continue
                x, _, size, _ = cell
                text = fit(values[index] if index < len(values) else '', size - 12)
                self.text(x + 6, y + row_height / 2, text=text, anchor='w', font=font,
                          fill=p['ROW_SELECT_INK'] if item in selected else ink)
