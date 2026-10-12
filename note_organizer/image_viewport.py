"""Shared mouse navigation for retained closeups and full-page previews."""
import tkinter as tk
from tkinter import ttk
from pathlib import Path
import sys

from PIL import Image, ImageTk
from .clipboard import copy_image


class ImageCanvas(tk.Canvas):
    def __init__(self, parent, window, status, **options):
        options.setdefault("borderwidth", 0)
        super().__init__(parent, highlightthickness=0, xscrollincrement=1, yscrollincrement=1, **options)
        self.original_image = None
        self.image_item = None
        self.zoom = 1.0
        self.fit_mode = None
        self.panning = False
        self.pan_cursor = self.grabbing_cursor()
        self.status = status
        self.copy_menu = tk.Menu(self, tearoff=False)
        self.copy_menu.add_command(label="Copy image", command=self.copy_original)
        self.bind("<<Copy>>", self.copy_original)
        self.bind("<Button-3>", self.show_copy_menu)
        self.bind("<Shift-F10>", self.show_copy_menu)
        self.bind("<Configure>", self.resize)
        self.bind("<ButtonPress-1>", self.start_pan)
        self.bind("<B1-Motion>", self.pan)
        self.bind("<ButtonRelease-1>", self.end_pan)
        self.bind("<Double-Button-1>", self.double_click)
        self.bind("<FocusOut>", self.end_pan)
        self.bind("<Unmap>", self.end_pan)
        window.bind("<MouseWheel>", self.wheel)
        window.bind("<Button-4>", self.wheel)
        window.bind("<Button-5>", self.wheel)

    def copy_original(self, event=None):
        if self.original_image is not None:
            try:
                copy_image(self.original_image, self.winfo_id())
            except OSError as exc:
                self.status(f"Could not copy image: {exc}")
            else:
                self.status("Image copied at its original resolution.")
        return "break"

    def show_copy_menu(self, event):
        self.focus_set()
        self.copy_menu.entryconfigure(0, state="normal" if self.original_image is not None else "disabled")
        x, y = ((self.winfo_rootx() + 8, self.winfo_rooty() + 8) if getattr(event, "keysym", "") == "F10"
                else (event.x_root, event.y_root))
        try:
            self.copy_menu.tk_popup(x, y)
        finally:
            self.copy_menu.grab_release()
        return "break"

    @property
    def auto_fit_width(self):
        return self.fit_mode == "width"

    def grabbing_cursor(self):
        cursor = Path(__file__).with_name("assets") / "cursors" / "closed-hand.cur"
        candidates = [("@" + cursor.as_posix(),)] if sys.platform == "win32" and cursor.is_file() else []
        candidates.extend(("closedhand", "hand2"))
        for candidate in candidates:
            try:
                self.configure(cursor=candidate)
            except tk.TclError:
                continue
            selected = str(self.cget("cursor"))
            self.configure(cursor="")
            return selected
        return "fleur"

    def maximum_zoom(self):
        image = self.original_image
        return min(8, 8192 / max(image.size), (32_000_000 / (image.width * image.height)) ** .5)

    def set_image(self, image, fit_width=False):
        self.original_image = image
        self.display_size = None
        self.fit_mode = None
        self.zoom = min(1, self.maximum_zoom())
        if fit_width:
            self.fit_width()
        else:
            self.render()

    def render(self):
        image = self.original_image
        if image is None:
            return
        width, height = max(1, round(image.width * self.zoom)), max(1, round(image.height * self.zoom))
        if getattr(self, "display_size", None) != (width, height):
            fitted = image if image.size == (width, height) else image.resize((width, height), Image.Resampling.LANCZOS)
            self.image = ImageTk.PhotoImage(fitted)
            if self.image_item is None:
                self.image_item = self.create_image(0, 0, image=self.image, anchor="nw")
            else:
                self.itemconfigure(self.image_item, image=self.image)
            self.display_size = (width, height)
            self.configure(scrollregion=(0, 0, width, height))
        self.status(f"{self.zoom:.0%} · Scroll vertically · Drag to pan · Double-click to fit width · Ctrl + wheel to zoom")

    def fit_width(self):
        if self.original_image is None:
            return
        self.fit_mode = "width"
        position = self.yview()[0]
        self.zoom = min(self.maximum_zoom(), max(1, self.winfo_width()) / self.original_image.width)
        self.render()
        self.xview_moveto(0)
        self.yview_moveto(position)

    def fit_height(self):
        if self.original_image is None:
            return
        self.fit_mode = "height"
        position = self.xview()[0]
        self.zoom = min(self.maximum_zoom(), max(1, self.winfo_height()) / self.original_image.height)
        self.render()
        self.yview_moveto(0)
        self.xview_moveto(position)

    def resize(self, event):
        if self.fit_mode == "width":
            self.fit_width()
        elif self.fit_mode == "height":
            self.fit_height()

    def start_pan(self, event):
        if self.original_image is None:
            return
        self.focus_set()
        self.panning = True
        self.scan_mark(event.x, event.y)
        self.configure(cursor=self.pan_cursor)

    def pan(self, event):
        if self.panning:
            self.scan_dragto(event.x, event.y, gain=1)

    def end_pan(self, event=None):
        self.panning = False
        self.configure(cursor="")

    def double_click(self, event):
        self.end_pan()
        self.fit_width()
        return "break"

    def wheel(self, event):
        direction = 1 if getattr(event, "num", None) == 4 else -1 if getattr(event, "num", None) == 5 else getattr(event, "delta", 0)
        if not direction or self.original_image is None:
            return "break"
        if event.state & 0x0004:
            image = self.original_image
            maximum = self.maximum_zoom()
            zoom = min(maximum, max(1 / max(image.size), self.zoom * (1.2 if direction > 0 else 1 / 1.2)))
            if abs(zoom - self.zoom) < .0001:
                return "break"
            ratio = zoom / self.zoom
            x = max(0, min(self.winfo_width(), event.x_root - self.winfo_rootx()))
            y = max(0, min(self.winfo_height(), event.y_root - self.winfo_rooty()))
            left, top = self.canvasx(x) * ratio - x, self.canvasy(y) * ratio - y
            self.fit_mode = None
            self.zoom = zoom
            self.render()
            self.xview_moveto(max(0, left) / self.display_size[0])
            self.yview_moveto(max(0, top) / self.display_size[1])
        else:
            units = (-72 if direction > 0 else 72) if abs(direction) < 120 else -int(direction / 120) * 72
            if event.state & 0x0001:
                self.xview_scroll(units, "units")
            else:
                self.yview_scroll(units, "units")
        return "break"


class ImageViewport(ttk.Frame):
    """The same scrollable image area in both inspection windows."""

    def __init__(self, parent, window, status, **options):
        super().__init__(parent)
        self.canvas = ImageCanvas(self, window, status, **options)
        self.vertical = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.horizontal = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vertical.grid(row=0, column=1, sticky="ns")
        self.horizontal.grid(row=1, column=0, sticky="ew")
        self.horizontal.grid_remove()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas.configure(yscrollcommand=self.vertical.set, xscrollcommand=self.horizontal_position)

    def horizontal_position(self, first, last):
        self.horizontal.set(first, last)
        # Height fitting changes the width too. Keep this bar in place so its
        # own height cannot make near-square images repeatedly show/hide it.
        if self.canvas.fit_mode == "height" or float(last) - float(first) < .9999:
            self.horizontal.grid()
        else:
            self.horizontal.grid_remove()
