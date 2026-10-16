"""Review exact archive paths before a backed-up duplicate cleanup."""
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, ttk
from .archive_storage import plan
from .icons import Button
from .storage_ui import _size
from .theme import BACKGROUND
from .widgets import ReadOnlyText, bind_dialog_close, fit_dialog, Tooltip, annotate_buttons
from .workflow_ui import background


class ArchiveReviewWindow:
    def __init__(self, app):
        self.app, self.rows, self.busy = app, [], False
        self.window = window = tk.Toplevel(app.root)
        window.title("Review recovery archives")
        window.transient(app.root)
        window.configure(background=BACKGROUND)
        bind_dialog_close(window, self.close)
        window.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Compare recovery archives with retained original sources", style="Section.TLabel").pack(anchor="w")
        self.report = ReadOnlyText(frame, height=14, width=90, value="Verifying raw source bytes and migrated notes…")
        self.report.pack(fill="both", expand=True, pady=12)
        self.acknowledged = tk.BooleanVar()
        self.check = ttk.Checkbutton(frame, text="I reviewed these duplicates; a verified backup will preserve the raw archives", variable=self.acknowledged, command=self.update)
        self.check.pack(anchor="w")
        Tooltip(self.check, "Acknowledge the exact verified duplicate archives listed above. Cleanup first creates a complete, verified backup.")
        self.remove = Button(frame, text="Back up & remove duplicates…", command=self.remove_ready, state="disabled")
        self.remove.pack(anchor="w", pady=12)
        Tooltip(self.remove, lambda: "Wait for the current backed-up cleanup to finish." if self.busy else
                "No verified duplicate archives are ready to remove." if not any(row["ready"] for row in self.rows) else
                "Review the verified duplicates and select the acknowledgment above first." if not self.acknowledged.get() else
                "Choose a new backup file. The app verifies the backup and rechecks source bytes before deleting only the exact verified duplicate archives listed above.")
        self.status = tk.StringVar()
        ttk.Label(frame, textvariable=self.status, wraplength=750).pack(fill="x")
        self.close_button = Button(frame, text="Close", command=self.close)
        self.close_button.pack(anchor="e")
        Tooltip(self.close_button, lambda: "Wait for the current backed-up cleanup to finish before closing." if self.busy else
                "Close the recovery-archive review. Every unreviewed archive remains in place.")
        annotate_buttons(window)
        fit_dialog(window, app.root)
        background(app, lambda: plan(app.store), self.loaded, self.failed, task='Reviewing recovery archives…')

    def loaded(self, rows):
        if not self.window.winfo_exists():
            return
        self.rows = rows
        ready = [row for row in rows if row["ready"]]
        self.report.set("\n\n".join(f"{row['path']}\n{_size(row['bytes'])} · {row['reason']}" for row in rows) or "No legacy recovery archives are present.")
        self.status.set(f"{len(ready)} verified duplicates · {_size(sum(row['bytes'] for row in ready))} reclaimable. Every unverified archive stays.")
        self.update()

    def update(self):
        self.remove.configure(state="normal" if not self.busy and self.acknowledged.get() and any(row["ready"] for row in self.rows) else "disabled")
        self.check.configure(state="disabled" if self.busy else "normal")
        self.close_button.configure(state="disabled" if self.busy else "normal")

    def remove_ready(self):
        if self.busy:
            return
        target = filedialog.asksaveasfilename(parent=self.window, title="Choose a new verified backup before duplicate cleanup",
            initialfile=f"Notable-archives-{datetime.now():%Y%m%d-%H%M%S}.zip", defaultextension=".zip", filetypes=[("Library backup", "*.zip")])
        if not target:
            return
        self.busy = True
        self.update()
        self.status.set("Backing up and verifying before removing the reviewed duplicates…")
        values = {"backup": target, "rows": [row for row in self.rows if row["ready"]]}
        def completed(result):
            self.busy = False
            self.acknowledged.set(False)
            self.report.set(f"Removed {len(result['removed'])} verified duplicates. Retained {len(result['retained'])} archives.\nVerified backup: {result['backup']}\n\n" + "\n".join(f"{path}: {reason}" for path, reason in result["retained"]))
            self.rows = []
            self.status.set("Cleanup finished. Original baseline and tablet layer assets remain available.")
            self.update()
        background(self.app, lambda: self.app.service.storage_action("archive_cleanup", values), completed, self.failed, task='Finishing recovery archive cleanup…')

    def failed(self, error):
        if self.window.winfo_exists():
            self.busy = False
            self.status.set(str(error))
            self.update()

    def close(self):
        if not self.busy:
            self.window.destroy()
