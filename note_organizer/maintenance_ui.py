"""Small, explicit library maintenance workflow, separate from the main UI."""
from datetime import datetime
from pathlib import Path
import tkinter as tk
import os
import subprocess
import sys
from tkinter import filedialog, ttk
from .icons import Button
from .storage_ui import _size, open_cleanup
from .theme import BACKGROUND
from .widgets import ReadOnlyText, bind_dialog_close, fit_dialog, annotate_buttons
from .workflow_ui import background
from .maintenance import stats


class MaintenanceWindow:
    def __init__(self, app):
        self.app, self.busy = app, False
        self.window = window = tk.Toplevel(app.root)
        window.title("Library storage & backups")
        window.transient(app.root)
        window.configure(background=BACKGROUND)
        bind_dialog_close(window, self.close)
        window.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        footer = ttk.Frame(frame)
        footer.pack(side="bottom", fill="x", pady=(12, 0))
        ttk.Label(frame, text="Protect and maintain your library", style="Section.TLabel").pack(anchor="w")
        self.summary = ReadOnlyText(frame, height=6, value="Measuring library storage…")
        self.summary.pack(fill="x", pady=12)
        self.controls = []
        for label, action in (("Create verified backup…", lambda: self.run("backup")),
                              ("Compact library…", lambda: self.run("compact")),
                              ("Restore backup…", self.restore),
                              ("Review extra PDFs…", lambda: open_cleanup(app))):
            button = Button(frame, text=label, command=action)
            button.pack(anchor="w", pady=4)
            self.controls.append(button)
        from .archive_ui import ArchiveReviewWindow
        archive_button = Button(frame, text="Review recovery archives…", command=lambda: ArchiveReviewWindow(app))
        archive_button.pack(anchor="w", pady=4)
        self.controls.append(archive_button)
        ttk.Label(frame, text="Compaction creates and verifies a complete backup first, then shares repeated images and reclaims unused database pages. All note revisions remain. Backups include available original PDFs and attachments. Restore creates a separate library folder.",
                  wraplength=610, style="Muted.TLabel").pack(fill="x", pady=12)
        self.status = tk.StringVar()
        ttk.Label(frame, textvariable=self.status, wraplength=610).pack(fill="x", pady=8)
        self.close_button = Button(footer, text="Close", command=self.close)
        self.close_button.pack(side="right")
        self.restored_path = None
        self.open_restored_button = Button(footer, text="Open restored library", command=self.open_restored, state="disabled")
        self.open_restored_button.pack(side="left")
        annotate_buttons(window)
        fit_dialog(window, app.root)
        background(app, lambda: stats(app.store), self.loaded, self.failed)

    def loaded(self, result):
        if self.window.winfo_exists():
            self.summary.set(f"Database: {_size(result['database_bytes'])}\nUnused database pages: {_size(result['reclaimable_bytes'])}\n"
                             f"{result['notes']:,} notes · {result['revisions']:,} history revisions\n"
                             f"{result['inline_images']:,} legacy inline images · {result['images']:,} shared images")

    def set_busy(self, value):
        self.busy = value
        for control in self.controls + [self.close_button]:
            control.configure(state="disabled" if value else "normal")
        self.open_restored_button.configure(state="normal" if self.restored_path and not value else "disabled")

    def run(self, action):
        if self.busy:
            return
        target = filedialog.asksaveasfilename(parent=self.window, title="Choose a new verified backup filename",
            initialfile=f"Notable-backup-{datetime.now():%Y%m%d-%H%M%S}.zip", defaultextension=".zip", filetypes=[("Library backup", "*.zip")])
        if not target:
            return
        self.set_busy(True)
        self.status.set("Creating and verifying backup…" + (" Then compacting without removing history." if action == "compact" else ""))
        def completed(result):
            self.set_busy(False)
            self.status.set(f"Verified backup saved: {target}" + ("\nLibrary compacted and verified." if action == "compact" else ""))
            background(self.app, lambda: stats(self.app.store), self.loaded, self.failed)
        background(self.app, lambda: self.app.service.storage_action(action, target), completed, self.failed)

    def restore(self):
        if self.busy:
            return
        source = filedialog.askopenfilename(parent=self.window, title="Choose a library backup", filetypes=[("Library backup", "*.zip")])
        if not source:
            return
        parent = filedialog.askdirectory(parent=self.window, title="Choose where to create a restored library")
        if not parent:
            return
        destination = Path(parent) / ("Notable-restored-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
        self.set_busy(True)
        self.status.set("Verifying archive and restoring a separate library…")
        def completed(result):
            self.restored_path = Path(result)
            self.set_busy(False)
            self.status.set(f"Restored and verified: {result}\nOpen restored library launches this separate recovery, using its own original file snapshots. Inbox watching and cloud services start paused for setup review. Your current library stays open.")
            self.app.open_path(result)
        background(self.app, lambda: self.app.service.storage_action("restore", (source, destination)), completed, self.failed)

    def open_restored(self):
        if self.restored_path:
            environment = {**os.environ, "PDF_NOTES_DATA_DIR": str(self.restored_path), "PDF_NOTES_SKIP_LEGACY_IMPORT": "1"}
            command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve().parent.parent / "PDF Note Organizer.py")]
            subprocess.Popen(command, env=environment, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

    def failed(self, error):
        if self.window.winfo_exists():
            self.set_busy(False)
            self.status.set(str(error))

    def close(self):
        if not self.busy:
            self.window.destroy()
