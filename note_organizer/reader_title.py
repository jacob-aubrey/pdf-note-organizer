"""A persistent document heading that leaves room for the reading surface."""
import tkinter as tk
from tkinter import font

from .theme import PANEL, TEXT
from .widgets import Tooltip


def fit_title(title, measure, width):
    """Wrap at word boundaries, with at most two lines and a final ellipsis."""
    remaining = " ".join(title.split())
    width = max(1, width)
    lines = []
    for line in range(2):
        if measure(remaining) <= width:
            lines.append(remaining)
            break
        suffix = "…" if line else ""
        low, high = 0, len(remaining)
        while low < high:
            middle = (low + high + 1) // 2
            if measure(remaining[:middle].rstrip() + suffix) <= width:
                low = middle
            else:
                high = middle - 1
        end = low
        boundary = remaining.rfind(" ", 0, end + 1)
        if boundary > 0:
            end = boundary
        if line:
            lines.append(remaining[:end].rstrip() + suffix)
        else:
            # A single very wide glyph must still make forward progress.
            end = max(1, end)
            lines.append(remaining[:end].rstrip())
            remaining = remaining[end:].lstrip()
    return "\n".join(lines)


class DocumentTitle(tk.Label):
    """Keep the full title for hover while bounding the displayed heading."""

    def __init__(self, parent):
        self.title = ""
        self.title_font = font.Font(root=parent, family="Segoe UI", size=12, weight="bold")
        super().__init__(parent, text="", font=self.title_font, background=PANEL,
                         foreground=TEXT, anchor="w", justify="left", width=1,
                         borderwidth=0, highlightthickness=0, padx=12, pady=6,
                         takefocus=False)
        Tooltip(self, lambda: self.title)
        self.bind("<Configure>", self.render)

    def set_title(self, title):
        if title == self.title:
            return
        self.title = title
        self.tooltip.hide()
        if title:
            siblings = [child for child in self.master.pack_slaves() if child is not self]
            self.pack(fill="x", **({"before": siblings[0]} if siblings else {}))
            self.render()
        else:
            self.configure(text="")
            self.pack_forget()

    def render(self, event=None):
        width = (event.width if event else self.winfo_width()) - 2 * int(self.cget("padx"))
        if width <= 0:
            return
        text = fit_title(self.title, self.title_font.measure, width)
        if self.cget("text") != text:
            self.configure(text=text)
