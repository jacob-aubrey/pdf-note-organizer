"""Responsive, modal shutdown while background workers finish safely."""
import logging
import threading
import tkinter as tk
from tkinter import ttk

from . import APP_NAME
from .branding import apply_app_icon
from .theme import BACKGROUND
from .screens import work_area
from .widgets import dismiss_tooltips, fit_dialog


class ShutdownTasks:
    def __init__(self, steps):
        self.stage = ("starting", "Stopping background work…")
        self.finished = threading.Event()
        self.thread = threading.Thread(target=self.run, args=(steps,), name="Safe app shutdown", daemon=False)
        self.thread.start()

    def run(self, steps):
        try:
            for key, label, finish in steps:
                self.stage = (key, label)
                try:
                    finish()
                except Exception:
                    # Attempt the remaining cleanup even if one worker fails.
                    logging.exception("Shutdown failed while %s", label)
        finally:
            self.finished.set()


class ShutdownDialog:
    def __init__(self, root):
        dismiss_tooltips()
        self.window = window = tk.Toplevel(root)
        window.withdraw()
        window.title(f"Closing {APP_NAME}")
        window.configure(background=BACKGROUND)
        window.transient(root)
        window.resizable(False, False)
        apply_app_icon(window)
        window.protocol("WM_DELETE_WINDOW", self.present)
        window.bind("<KeyPress>", lambda _: "break")
        self.detail = tk.StringVar(master=window, value="Stopping background work…")
        frame = ttk.Frame(window, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Closing {APP_NAME} safely…", style="Section.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Finishing active tasks before the app closes.", style="Muted.TLabel").pack(anchor="w", pady=(8, 16))
        self.progress = ttk.Progressbar(frame, mode="indeterminate", length=440)
        self.progress.pack(fill="x")
        ttk.Label(frame, textvariable=self.detail, wraplength=440, justify="left").pack(fill="x", pady=(16, 0))
        self.disabled_windows = []
        # A Tk grab alone does not block the non-Tk WebView2 child. Disable
        # every existing native app window as well as taking the modal grab.
        if root.tk.call("tk", "windowingsystem") == "win32":
            def disable(parent):
                if parent == window:
                    return
                if isinstance(parent, (tk.Tk, tk.Toplevel)):
                    self.disabled_windows.append((parent, parent.attributes("-disabled")))
                    parent.attributes("-disabled", True)
                for child in parent.winfo_children():
                    disable(child)
            disable(root)
        fit_dialog(window, root)
        window.deiconify()
        self.center()
        window.grab_set()
        self.present()
        self.progress.start(20)

    def present(self):
        self.window.lift()
        self.window.focus_set()

    def update(self, text):
        if text != self.detail.get():
            self.detail.set(text)
            # Recenter when a longer task name changes the dialog height.
            self.center()

    def center(self):
        window, parent = self.window, self.window.master
        fit_dialog(window, parent)
        window.update_idletasks()
        if window.winfo_ismapped():
            # Geometry positions the native frame; root coordinates describe
            # its client area. Account for the title bar and window borders.
            dx = parent.winfo_rootx() + (parent.winfo_width() - window.winfo_width()) // 2 - window.winfo_rootx()
            dy = parent.winfo_rooty() + (parent.winfo_height() - window.winfo_height()) // 2 - window.winfo_rooty()
            border = window.winfo_rootx() - window.winfo_x()
            title = window.winfo_rooty() - window.winfo_y()
            left, top, right, bottom = work_area(parent)
            x = max(left + 8, min(window.winfo_x() + dx, right - window.winfo_width() - 2 * border - 8))
            y = max(top + 8, min(window.winfo_y() + dy, bottom - window.winfo_height() - title - border - 8))
            window.geometry(f"+{x}+{y}")

    def destroy(self):
        self.progress.stop()
        self.window.grab_release()
        for window, previous in self.disabled_windows:
            if window.winfo_exists():
                window.attributes("-disabled", previous)
        self.window.destroy()
