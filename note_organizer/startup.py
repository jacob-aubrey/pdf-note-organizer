"""A stable branded surface while the saved workspace and Tk layout prepare."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import queue
import tkinter as tk

from PIL import Image, ImageTk

from . import APP_NAME, __version__
from .branding import apply_app_icon
from .screens import round_window_corners, work_area
from .theme import BACKGROUND, SURFACE, TEXT, MUTED
from .widgets import Tooltip


class StartupSplash:
    def __init__(self, root, prepare, build, failed, target_area=None):
        self.root, self.prepare, self.build, self.failed = root, prepare, build, failed
        self.target_area = target_area
        self.app = None
        self.closed = self.revealed = False
        self.cancel_requested = False
        self.pending = None
        self.configure_binding = None
        self.layout_revision = 0
        self.messages = queue.SimpleQueue()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="Opening library")
        self.future = None
        self.opacity = root.attributes("-alpha")
        root.withdraw()
        root.attributes("-alpha", 0)
        self.window = window = tk.Toplevel(root)
        window.withdraw()
        window.title(APP_NAME)
        window.overrideredirect(True)
        window.configure(background=BACKGROUND)
        window.resizable(False, False)
        apply_app_icon(window)
        window.protocol("WM_DELETE_WINDOW", self.cancel)
        window.bind("<Escape>", lambda _: self.cancel())
        panel = tk.Frame(window, background=BACKGROUND, padx=30, pady=24)
        panel.pack(fill="both", expand=True)
        with Image.open(Path(__file__).with_name("assets") / "branding" / "notable.png") as source:
            self.logo = ImageTk.PhotoImage(source.resize((80, 80), Image.Resampling.LANCZOS), master=window)
        tk.Label(panel, image=self.logo, background=BACKGROUND).pack(pady=(4, 12))
        tk.Label(panel, text=APP_NAME, font=("Segoe UI", 22, "bold"), background=BACKGROUND,
                 foreground=TEXT).pack()
        tk.Label(panel, text=__version__, font=("Segoe UI", 9), background=BACKGROUND,
                 foreground=MUTED).pack(pady=(2, 20))
        tk.Frame(panel, background=SURFACE, height=1).pack(fill="x", pady=(0, 14))
        self.message = tk.StringVar(window, value="Opening library…")
        self.status = tk.Label(panel, textvariable=self.message, background=BACKGROUND,
                               foreground=MUTED, font=("Segoe UI", 10), anchor="center", width=32)
        self.status.pack(fill="x")
        self.cancel_button = tk.Button(window, text="×", command=self.cancel, font=("Segoe UI", 13),
            background=BACKGROUND, foreground=MUTED, activebackground=SURFACE,
            activeforeground=TEXT, relief="flat", borderwidth=0, highlightthickness=0,
            padx=7, pady=0, takefocus=True)
        self.cancel_button.place(relx=1, x=-7, y=6, anchor="ne")
        Tooltip(self.cancel_button, lambda: "Waiting for library setup to finish safely before closing." if self.cancel_requested else
                "Cancel startup and close Notable. Escape does the same.")
        window.update_idletasks()
        left, top, right, bottom = self.target_area or work_area(root, root.winfo_pointerxy())
        width, height = window.winfo_reqwidth(), window.winfo_reqheight()
        x = left + (right-left-width)//2
        y = top + (bottom-top-height)//2
        self.border_window = border = tk.Toplevel(root)
        border.withdraw()
        border.overrideredirect(True)
        border.configure(background="white")
        border.geometry(f"{width + 2}x{height + 2}+{x - 1}+{y - 1}")
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.attributes("-alpha", 0)
        border.attributes("-alpha", 0)
        border.deiconify()
        window.deiconify()
        border.update_idletasks()
        window.update_idletasks()
        round_window_corners(border)
        round_window_corners(window)
        border.attributes("-alpha", 1)
        window.attributes("-alpha", 1)
        window.lift()
        window.focus_set()
        window.update_idletasks()
        self.schedule(self.begin, idle=True)

    def schedule(self, callback, *, idle=False):
        if not self.closed:
            self.pending = self.root.after_idle(callback) if idle else self.root.after(25, callback)

    def begin(self):
        self.pending = None
        if self.closed:
            return
        self.future = self.executor.submit(self.prepare, self.messages.put)
        self.schedule(self.poll_library)

    def poll_library(self):
        self.pending = None
        if self.closed:
            return
        while not self.messages.empty():
            self.message.set(self.messages.get_nowait())
        if not self.future.done():
            self.schedule(self.poll_library)
            return
        try:
            self.library = self.future.result()
        except Exception as exc:
            self.fail(exc)
            return
        self.message.set("Preparing workspace…")
        self.window.update_idletasks()
        self.schedule(self.build_workspace, idle=True)

    def build_workspace(self):
        self.pending = None
        if self.closed:
            return
        try:
            self.app = self.build(self.library)
            self.message.set("Loading saved library…")
            self.configure_binding = self.root.bind("<Configure>", self.layout_changed, add="+")
            # Mapping at zero opacity lets real pane sizes, wrapping toolbars,
            # and Map/Configure handlers settle behind the splash.
            self.root.deiconify()
            self.window.lift()
            self.window.focus_set()
            self.schedule(self.poll_workspace)
        except Exception as exc:
            self.fail(exc)

    def layout_changed(self, event):
        if event.widget.winfo_toplevel() == self.root:
            self.layout_revision += 1

    def poll_workspace(self):
        self.pending = None
        if self.closed:
            return
        if self.app.closing:
            self.destroy()
            return
        if not self.app.library_loaded:
            self.message.set("Waiting for library access…" if self.app.refresh_needed and
                             self.app.library_future is None else "Loading saved library…")
        elif getattr(self.app, "reader_search_busy", False) or self.app.notes_after is not None:
            self.message.set("Loading papers and notes…")
        else:
            self.message.set("Preparing workspace…")
            self.settle_layout()
            return
        self.schedule(self.poll_workspace)

    def settle_layout(self):
        self.pending = None
        if self.closed:
            return
        self.root.update_idletasks()
        revision = self.layout_revision

        def settled():
            self.pending = None
            if self.closed:
                return
            if self.layout_revision != revision:
                self.schedule(self.settle_layout, idle=True)
            elif not self.app.library_loaded or getattr(self.app, "reader_search_busy", False) or self.app.notes_after:
                self.schedule(self.poll_workspace)
            else:
                self.reveal()

        self.schedule(settled, idle=True)

    def reveal(self):
        if self.closed:
            return
        self.revealed = True
        self.root.attributes("-alpha", self.opacity)
        self.root.focus_set()
        self.destroy()

    def fail(self, exc):
        self.destroy()
        self.root.withdraw()
        self.failed(exc)

    def cancel(self):
        if self.closed or self.cancel_requested:
            return
        self.cancel_requested = True
        if self.app is None and self.future is not None and not self.future.done():
            # SQLite initialization/import must finish its current transaction.
            # Keep the explanation visible while that worker exits safely.
            self.message.set("Closing: finishing library setup…")
            self.cancel_button.configure(state="disabled")
            if self.pending is not None:
                self.root.after_cancel(self.pending)
            self.schedule(self.finish_cancel)
            return
        self.destroy()
        if self.app is not None:
            self.app.close()
        else:
            self.root.quit()

    def finish_cancel(self):
        self.pending = None
        if self.closed:
            return
        if not self.future.done():
            self.schedule(self.finish_cancel)
            return
        self.destroy()
        self.root.quit()

    def destroy(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.pending is not None:
                self.root.after_cancel(self.pending)
            if self.configure_binding is not None:
                self.root.unbind("<Configure>", self.configure_binding)
            self.cancel_button.tooltip.hide()
            self.window.destroy()
            if hasattr(self, "border_window"):
                self.border_window.destroy()
        except tk.TclError:
            # A normal app shutdown can destroy the root before this watcher
            # sees app.closing. Joining the preparation worker is still needed.
            pass
        self.pending = self.configure_binding = None
        self.executor.shutdown(wait=False, cancel_futures=True)

    def wait_closed(self):
        self.destroy()
        self.executor.shutdown(wait=True, cancel_futures=True)
