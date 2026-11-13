"""Continuous window backgrounds without changing text/artwork opacity."""
from __future__ import annotations

import tkinter as tk
from contextlib import contextmanager
from tkinter import ttk
from PIL import Image, ImageOps, ImageTk
from .glass import GlassSurface, readable_panel
from .colors import contrast
from .appearance import animate_selection
from .windows import clip_child_paint

LAYOUTS = ("覆盖", "填充", "居中", "拉伸", "自由")


class BackdropLabel(tk.Label):
    """Keep text geometry live even when a background image is attached."""
    def __init__(self, master, **kwargs):
        variable = kwargs.get("textvariable")
        super().__init__(master, **kwargs)
        if isinstance(variable, tk.Variable):
            token = variable.trace_add("write", self._changed)
            self.bind("<Destroy>", lambda _: variable.trace_remove("write", token), add="+")

    def _changed(self, *_):
        if hasattr(self._root(), "backdrop"):
            self._root().backdrop.schedule(window=self.winfo_toplevel())

    def configure(self, cnf=None, **kwargs):
        result = super().configure(cnf, **kwargs)
        if "text" in kwargs or "font" in kwargs or "wraplength" in kwargs:
            self._changed()
        return result

    config = configure


def compose_background(source, size, mode="覆盖", base="#f3f5fa", opacity=45,
                       scale=100, x=0, y=0):
    """Cover crops; fill fits; center keeps pixels; free scales a fitted image.

    Free offsets use a percentage of the viewport, independent of resolution.
    """
    width, height = size = tuple(max(1, int(v)) for v in size)
    result = Image.new("RGB", size, base)
    if mode == "覆盖":
        picture = ImageOps.fit(source, size, Image.Resampling.LANCZOS)
    elif mode == "拉伸":
        picture = source.resize(size, Image.Resampling.LANCZOS)
    elif mode == "居中":
        picture = source
    else:
        ratio = min(width / source.width, height / source.height)
        if mode == "自由":
            ratio *= max(10, min(400, scale)) / 100
        picture = source.resize((max(1, round(source.width * ratio)),
                                 max(1, round(source.height * ratio))), Image.Resampling.LANCZOS)
    left, top = (width - picture.width) // 2, (height - picture.height) // 2
    if mode == "自由":
        left += round(width * x / 100)
        top += round(height * y / 100)
    result.paste(picture, (left, top))
    return Image.blend(Image.new("RGB", size, base), result, max(0, min(100, opacity)) / 100)


class WindowBackdrop:
    """Paint aligned image slices into existing Tk panels and label surfaces.

    Controls keep their own readable surfaces. Every toplevel has a continuous
    wallpaper; child positions are measured in that window's client coordinates.
    The normal layout and native widget semantics remain intact.
    """
    def __init__(self, app):
        self.app = app
        self.timer = None
        self.revision = 0
        self.images = {}
        self.surfaces = {}
        self.glass = {}
        self.notebooks = {}
        self._transaction_depth = 0
        self._dirty_windows = set()
        self._all_pending = True
        self._rendering = False
        self._event_geometry = {}
        app.bind_all("<Configure>", self.schedule, add="+")
        app.bind_all("<Map>", self.schedule, add="+")
        app.bind_all("<MouseWheel>", self.schedule, add="+")

    @contextmanager
    def transaction(self):
        """Flush one completed Tk layout without hiding native toplevels.

        WM_SETREDRAW on a wrapper HWND clears WS_VISIBLE and makes DWM drop
        the window temporarily. Keep its visibility and taskbar presence live.
        """
        outer = self._transaction_depth == 0
        self._transaction_depth += 1
        try:
            yield
        finally:
            try:
                if outer and not self.app.closing:
                    self.app.update_idletasks()
                    self.render()
            finally:
                self._transaction_depth -= 1

    def composite(self, background, overlay):
        """Blend antialiased controls onto their actual theme background."""
        result = background.convert("RGBA")
        result.alpha_composite(overlay)
        return result.convert("RGB")

    def text(self, canvas, x, y, *, text, fill, font, anchor="center", width=0, justify="center"):
        return canvas.create_text(x, y, text=text, fill=fill, font=font,
                                  anchor=anchor, width=width, justify=justify)

    def schedule(self, event=None, *, window=None, immediate=False):
        if event is not None and getattr(event.widget, "_wallpaper_layer", False):
            return
        if event is not None:
            widget = event.widget
            if not isinstance(widget, tk.Misc):  # Tcl-owned combobox popdown.
                return
            if str(event.type) == "22":  # Ignore Configure notifications with unchanged geometry.
                geometry = (event.x, event.y, event.width, event.height)
                if self._event_geometry.get(widget) == geometry:
                    return
                self._event_geometry[widget] = geometry
            window = widget.winfo_toplevel()
            # Newly mapped settings pages must be composited in the same idle
            # cycle as native layout, before the ordinary debounce can expose
            # their plain Frame/Label backgrounds for a visible frame.
            if getattr(window, "_glass_settings", False) and str(event.type) in ("19", "22"):
                immediate = True
        if window is None:
            self._all_pending = True
        else:
            self._dirty_windows.add(window)
        if not getattr(self.app, "closing", False):
            if immediate and event is not None and str(event.type) == "19" and not self._rendering:
                # Map is the last chance to prepare a newly visible native
                # control before Windows paints its fallback background.
                self.render()
            elif immediate:
                if self.timer is not None:
                    self.app.after_cancel(self.timer)
                self.timer = self.app.after_idle(self.render)
            elif self.timer is None:
                self.timer = self.app.after(35, self.render)

    def invalidate(self):
        self.revision += 1
        self.schedule()
        if hasattr(self.app, "gallery"):
            self.app.gallery.request_redraw()

    def wallpaper_key(self, window):
        if self._rendering and window in getattr(self, "_render_keys", {}):
            return self._render_keys[window]
        app = self.app
        return (str(window), window.winfo_width(), window.winfo_height(),
                id(app.background_image), app.theme_mode.get(), app.palette["BG"], app.palette["MUTED"],
                app.background_layout.get(), app.background_opacity.get(), app.background_scale.get(),
                app.background_x.get(), app.background_y.get())

    def wallpaper(self, window):
        app = self.app
        if app.theme_mode.get() != "自定义背景" or app.background_image is None:
            return None
        size = (max(1, window.winfo_width()), max(1, window.winfo_height()))
        key = self.wallpaper_key(window)
        if key not in self.images:
            # Retain at most the current image per toplevel during resize.
            self.images = {k: v for k, v in self.images.items() if k[0] != str(window)}
            picture = compose_background(app.background_image, size, app.background_layout.get(),
                app.palette["BG"], app.background_opacity.get(), app.background_scale.get(),
                app.background_x.get(), app.background_y.get())
            # One continuous readability veil, shared by every panel and label.
            self.images[key] = readable_panel(picture, app.palette["MUTED"], opacity=.12)
        return self.images[key]

    def crop(self, widget, size=None):
        window = widget.winfo_toplevel()
        width, height = size or (widget.winfo_width(), widget.winfo_height())
        picture = self.wallpaper(window)
        if picture is None:
            color = self.app.palette["PANEL"]
            try:
                color = widget.master.cget("background")
            except (AttributeError, tk.TclError):
                pass
            return Image.new("RGB", (max(1, width), max(1, height)), color)
        x, y = widget.winfo_rootx() - window.winfo_rootx(), widget.winfo_rooty() - window.winfo_rooty()
        # Padding beyond the visible viewport uses the theme's base, not black.
        result = Image.new("RGB", (max(1, width), max(1, height)), self.app.palette["BG"])
        result.paste(picture, (-x, -y))
        return result

    def render(self):
        if self._rendering:
            return
        if self.timer is not None:
            self.app.after_cancel(self.timer)
        self.timer = None
        app = self.app
        if getattr(app, "closing", False):
            return
        custom = app.theme_mode.get() == "自定义背景" and app.background_image is not None
        windows = [app] + [w for w in app.winfo_children() if isinstance(w, tk.Toplevel)
                           and not getattr(w, "_no_backdrop", False)]
        if not self._all_pending:
            windows = [w for w in windows if w in self._dirty_windows]
        self._dirty_windows.clear()
        self._all_pending = False
        if not windows:
            return
        self._render_keys = {w: self.wallpaper_key(w) for w in windows}
        self._rendering = True
        alive = set()
        def paint(widget):
            if getattr(widget, "_wallpaper_layer", False):
                return
            alive.add(widget)
            if not widget.winfo_ismapped():
                return
            glass = getattr(widget, "_glass_surface", False)
            text_control = isinstance(widget, (tk.Button, tk.Checkbutton, tk.Label)) and not getattr(widget, "_no_backdrop", False)
            if glass or text_control:
                if widget not in self.glass:
                    self.glass[widget] = GlassSurface(widget, self)
                self.glass[widget].render(True)
            if isinstance(widget, ttk.Notebook):
                self.paint_notebook(widget)
            if isinstance(widget, (tk.Frame, tk.Toplevel, tk.Tk)):
                layer = getattr(widget, "_backdrop_canvas", None)
                if custom:
                    if layer is None or not layer.winfo_exists():
                        clip_child_paint(widget)
                        layer = tk.Canvas(widget, highlightthickness=0, bd=0, takefocus=False)
                        layer._wallpaper_layer = True
                        widget._backdrop_canvas = layer
                    # Include Frame padx/pady; the default "inside" placement
                    # leaves an opaque band around padded settings containers.
                    layer.place(x=0, y=0, relwidth=1, relheight=1, bordermode="outside")
                    widget.tk.call("lower", str(layer))
                    self.paint_canvas(layer, widget)
                elif layer is not None and layer.winfo_exists():
                    layer.place_forget()
            elif isinstance(widget, tk.Canvas) and widget is not app.gallery:
                if custom:
                    self.paint_canvas(widget, widget)
                elif widget in self.surfaces:
                    widget.delete("window-backdrop")
                    self.surfaces.pop(widget, None)
            repaint = getattr(widget, "_paint_surface", None)
            if repaint:
                repaint()
            for child in widget.winfo_children():
                if not isinstance(child, tk.Toplevel):
                    paint(child)
        try:
            for window in windows:
                paint(window)
        finally:
            self._rendering = False
        self.images = {k: v for k, v in self.images.items() if app.tk.call("winfo", "exists", k[0])}
        self.surfaces = {w: data for w, data in self.surfaces.items() if w.winfo_exists()}
        self.glass = {w: data for w, data in self.glass.items() if w.winfo_exists()}
        self.notebooks = {w: data for w, data in self.notebooks.items() if w.winfo_exists()}
        self._event_geometry = {w: v for w, v in self._event_geometry.items() if w.winfo_exists()}

    def paint_canvas(self, canvas, coordinate_widget):
        window = coordinate_widget.winfo_toplevel()
        key = (self.wallpaper_key(window), self.app.palette["PANEL"],
               coordinate_widget.winfo_rootx() - window.winfo_rootx(),
               coordinate_widget.winfo_rooty() - window.winfo_rooty(),
               coordinate_widget.winfo_width(), coordinate_widget.winfo_height(), canvas.canvasx(0), canvas.canvasy(0))
        if self.surfaces.get(canvas, (None,))[0] == key:
            return
        picture = self.crop(coordinate_widget)
        if picture is None:
            return
        photo = ImageTk.PhotoImage(picture, master=canvas)
        canvas.delete("window-backdrop")
        canvas.create_image(canvas.canvasx(0), canvas.canvasy(0), image=photo, anchor="nw", tags="window-backdrop")
        canvas.tag_lower("window-backdrop")
        self.surfaces[canvas] = key, photo

    def paint_notebook(self, widget):
        data = self.notebooks.get(widget)
        page = widget.nametowidget(widget.select()) if widget.select() else None
        client_y = page.winfo_y() if page is not None else 0
        key = (self.revision, widget.winfo_width(), widget.winfo_height(), widget.winfo_rootx(), widget.winfo_rooty(), client_y, widget.select())
        if data is not None and data["key"] == key:
            return
        window = widget.winfo_toplevel()
        background_key = (self.wallpaper_key(window), self.app.palette["PANEL"],
                          widget.winfo_width(), widget.winfo_height(),
                          widget.winfo_rootx()-window.winfo_rootx(), widget.winfo_rooty()-window.winfo_rooty())
        picture = (data["picture"] if data and data.get("background_key") == background_key
                   else self.crop(widget))
        # A single thin client border replaces the notebook's wide solid fill.
        style = ttk.Style(widget)
        if data is None:
            name = "Glass" + str(id(widget))
            photo = ImageTk.PhotoImage(picture, master=widget)
            style.element_create(name, "image", photo, sticky="nsew")
            style.layout(name+".TNotebook", [(name, {"sticky": "nsew"})])
            style.configure(name+".TNotebook", tabmargins=0, padding=1)
            header = tk.Canvas(widget, bd=0, highlightthickness=0, takefocus=False)
            header._wallpaper_layer = True
            def select_tab(event):
                for index, left, right in data["regions"]:
                    if left <= event.x < right:
                        if widget.index(widget.select()) != index:
                            widget.select(index)
                            widget.focus_set()
                            self.schedule(window=widget.winfo_toplevel(), immediate=True)
                        break
            header.bind("<Button-1>", select_tab)
            def tab_changed(_):
                with self.transaction():
                    self.schedule(window=widget.winfo_toplevel(), immediate=True)
            widget.bind("<<NotebookTabChanged>>", tab_changed, add="+")
            data = {"original": widget.cget("style"), "name": name, "photo": photo, "header": header, "regions": []}
            self.notebooks[widget] = data
        elif data.get("background_key") != background_key:
            # Reconfigure the existing named image when resize changes dimensions.
            photo = data["photo"]
            photo.tk.call(str(photo), "configure", "-width", picture.width, "-height", picture.height)
            photo.paste(picture)
        data["picture"] = picture
        data["background_key"] = background_key
        widget.configure(style=data["name"]+".TNotebook")
        header = data["header"]
        height = max(1, client_y)
        header.place(x=0, y=0, relwidth=1, height=height)
        header.tk.call("raise", str(header))
        header.delete("all")
        header.configure(bg=self.app.palette["PANEL"])
        data["header_photo"] = ImageTk.PhotoImage(picture.crop((0, 0, picture.width, height)), master=header)
        header.create_image(0, 0, image=data["header_photo"], anchor="nw")
        geometry_key = (widget.winfo_width(), height, tuple(widget.tab(t, "text") for t in widget.tabs()))
        if data.get("geometry_key") != geometry_key:
            regions = []
            for x in range(widget.winfo_width()):
                try:
                    index = widget.index(f"@{x},{max(1, height//2)}")
                except tk.TclError:
                    continue
                if regions and regions[-1][0] == index:
                    regions[-1][2] = x+1
                else:
                    regions.append([index, x, x+1])
            data["regions"] = regions
            data["geometry_key"] = geometry_key
        regions = data["regions"]
        p = self.app.palette
        selected = widget.index(widget.select()) if widget.select() else -1
        highlight = None
        highlight_base = None
        for index, left, right in regions:
            if index == selected:
                box = (left+2, 3, max(left+3, right-2), max(4, height-3))
                highlight_base = picture.crop(box)
                highlight = header.create_image(box[0], box[1], anchor="nw")
            self.text(header, (left+right)/2, height/2, text=widget.tab(index, "text"),
                      font=("Microsoft YaHei UI", 10),
                      fill=p["ACCENT_INK"] if index == selected and contrast(p["ACCENT_INK"], p["SELECT"]) >= 4.5 else p["INK"])
        if highlight is not None:
            target = Image.new("RGB", highlight_base.size, p["SELECT"])
            def draw(progress):
                data["highlight_photo"] = ImageTk.PhotoImage(Image.blend(highlight_base, target, progress), master=header)
                header.itemconfigure(highlight, image=data["highlight_photo"])
            animate_selection(header, draw)
        data["regions"] = regions
        data["key"] = key
