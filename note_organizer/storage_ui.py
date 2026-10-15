"""Explicit review of extra PDFs created by older Notable versions."""
import tkinter as tk
from tkinter import ttk

from .icons import Button
from .screens import work_area
from .source_storage import plan_legacy_cleanup
from .theme import BACKGROUND
from .widgets import SelectionDetails, ReadOnlyText, Tooltip, bind_dialog_close, fit_dialog
from .workflow_ui import background


def _size(value):
    value = max(0, int(value or 0))
    for unit in ("bytes", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:,} bytes" if unit == "bytes" else f"{value:,.1f} {unit}"
        value /= 1024


def open_cleanup(app):
    """Open a review window; opening it never removes or moves a file."""
    dialog = LegacyCleanupDialog(app)
    dialog.window.cleanup_dialog = dialog
    return dialog.window


class LegacyCleanupDialog:
    def __init__(self, app):
        self.app, self.rows, self.busy = app, {}, ""
        self.confirmation = None
        self.window = window = tk.Toplevel(app.root)
        window.title("Review extra PDFs")
        window.configure(background=BACKGROUND)
        window.transient(app.root)
        window.protocol("WM_DELETE_WINDOW", self.close)
        bind_dialog_close(window, self.close)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)
        ttk.Label(frame, text="Review extra reading copies", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.summary = tk.StringVar(value="Checking saved sources, notes and notebook links…")
        summary = ttk.Label(frame, textvariable=self.summary, wraplength=850, style="Muted.TLabel")
        summary.grid(row=1, column=0, sticky="ew", pady=(8, 10))
        summary.bind("<Configure>", lambda event: summary.configure(wraplength=max(80, event.width)))
        controls = ttk.Frame(frame)
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.refresh_button = Button(controls, text="Review again", command=self.refresh)
        self.refresh_button.pack(side="left")
        Tooltip(self.refresh_button, "Recheck the saved sources, main PDFs, note identities and generated notebooks. This review leaves every file in place.")
        self.select_ready = tk.BooleanVar(value=False)
        self.select_button = ttk.Checkbutton(controls, text="Select all ready copies", variable=self.select_ready,
                                             command=self.select_all_ready)
        self.select_button.pack(side="left", padx=14)
        Tooltip(self.select_button, "Select only copies whose originals, tablet notes and current notebook links have been verified. Copies needing attention are kept.")
        listing = ttk.Frame(frame)
        listing.grid(row=3, column=0, sticky="nsew")
        self.tree = app.tree(listing, [("name", "Paper", 230), ("state", "Cleanup status", 145),
                                       ("size", "Extra copy size", 110), ("reason", "Explanation", 390)],
                             height=9, content_columns=())
        self.tree.configure(selectmode="extended")
        self.tree.bind("<<TreeviewSelect>>", self.selected)
        self.tree.tooltip.value = lambda row, column: self.rows[row].get("path", "") if column == "name" else self.tree.set(row, column)
        self.tree.tooltip.extra = lambda row, column: "\n".join(self.rows[row].get("reasons", []))
        self.details = SelectionDetails(frame, title="Selected copies", height=5)
        self.details.grid(row=4, column=0, sticky="ew", pady=(10, 8))
        self.details.set("Select a copy to inspect its complete paths and cleanup checks.", selected=False)
        self.acknowledged = tk.BooleanVar(value=False)
        self.acknowledgment = ttk.Checkbutton(frame, variable=self.acknowledged, command=self.update_controls,
            text="Old links in exported notebooks or backups may stop working")
        self.acknowledgment.grid(row=5, column=0, sticky="w", pady=(0, 8))
        Tooltip(self.acknowledgment, "Current generated notebooks are checked before cleanup. Notable cannot find every separately saved Word export, notebook backup or other document that links to an old reading copy. Its old link may stop working after that copy is removed.")
        self.report = ReadOnlyText(frame, height=3, value=
            "Only unchanged copies created by older Notable versions can be removed here. "
            "Your main PDFs, saved PC and tablet notes, raw tablet files and note history stay preserved.")
        self.report.grid(row=6, column=0, sticky="ew", pady=(0, 10))
        actions = ttk.Frame(frame)
        actions.grid(row=7, column=0, sticky="ew")
        self.remove_button = Button(actions, text="Remove reviewed copies", command=self.review_removal,
                                    style="Primary.TButton", state="disabled")
        self.remove_button.pack(side="left")
        Tooltip(self.remove_button, lambda: "Wait for the current storage review or removal to finish." if self.busy else
                "Select only copies marked Ready for review first." if not self.ready_selection() else
                "Review the selected paths and acknowledge the old-link warning above first." if not self.acknowledged.get() else
                "Review the exact selected paths and total size, then explicitly remove verified extra reading copies. Edited or changed copies remain in place.")
        self.close_button = Button(actions, text="Close", command=self.close)
        self.close_button.pack(side="right")
        Tooltip(self.close_button, "Close this review. A removal you already confirmed must finish before the window closes.")
        fit_dialog(window, app.root)
        left, top, right, bottom = work_area(app.root)
        window.minsize(min(740, right - left - 16), min(500, bottom - top - 16))
        def resize(event):
            if event.widget is window:
                self.details.text.configure(height=5 if event.height >= 700 else 3 if event.height >= 580 else 2)
                self.report.text.configure(height=3 if event.height >= 700 else 2)
        window.bind("<Configure>", resize, add="+")
        self.refresh()

    def alive(self):
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    def ready_selection(self):
        selected = [self.rows[row] for row in self.tree.selection() if row in self.rows]
        return selected if selected and all(row.get("status") == "ready" for row in selected) else []

    def update_controls(self):
        if not self.alive():
            return
        idle = not self.busy
        self.refresh_button.configure(state="normal" if idle else "disabled")
        self.select_button.configure(state="normal" if idle and any(row.get("status") == "ready" for row in self.rows.values()) else "disabled")
        self.acknowledgment.configure(state="normal" if idle else "disabled")
        self.remove_button.configure(state="normal" if idle and self.acknowledged.get() and self.ready_selection() else "disabled")
        self.close_button.configure(state="disabled" if self.busy == "removing" else "normal")

    def refresh(self):
        if self.busy or not self.alive():
            return
        self.busy = "checking"
        self.acknowledged.set(False)
        self.select_ready.set(False)
        self.summary.set("Checking saved sources, notes and notebook links…")
        self.update_controls()
        background(self.app, lambda: plan_legacy_cleanup(self.app.store), self.loaded, self.failed)

    def loaded(self, plans):
        if not self.alive():
            return
        self.busy = ""
        self.rows = {str(index): plan for index, plan in enumerate(plans)}
        self.tree.delete(*self.tree.get_children())
        for key, plan in self.rows.items():
            reason = "Ready after your review; all required source checks passed." if plan["status"] == "ready" else " ".join(plan.get("reasons", []))
            self.tree.insert("", "end", iid=key, values=(plan.get("name", "Paper"),
                {"ready": "Ready for review", "blocked": "Keep for now", "removed": "Already removed"}.get(plan["status"], "Keep for now"),
                _size(plan.get("bytes", 0)), reason))
        ready = [plan for plan in plans if plan["status"] == "ready"]
        self.summary.set(f"{len(ready)} ready copies · {_size(sum(plan.get('bytes', 0) for plan in ready))} can be reclaimed after review. "
                         f"{sum(plan['status'] == 'blocked' for plan in plans)} copies need attention. "
                         "Select ready rows together with Ctrl or Shift, or choose Select all ready copies." if plans else
                         "No legacy reading copies are recorded in this library.")
        self.selected()

    def selected(self, event=None):
        if not self.alive():
            return
        selected = [self.rows[row] for row in self.tree.selection() if row in self.rows]
        lines, paths = [], {}
        for number, plan in enumerate(selected, 1):
            lines.extend([f"{number}. {plan.get('name', 'Paper')} · {_size(plan.get('bytes', 0))}",
                          f"Extra reading copy: {plan.get('path', '')}", f"Main paper: {plan.get('main_path', '')}"])
            lines.extend(plan.get("reasons", []) or ["All required source, saved-note and current notebook checks passed."])
            lines.append("")
            if plan.get("path"):
                paths[f"{number}. Extra reading copy"] = (plan["path"], "This is the legacy copy considered for removal.")
            if plan.get("main_path"):
                paths[f"{number}. Main paper"] = (plan["main_path"], "This main research PDF stays in your library.")
        self.details.set("\n".join(lines).rstrip() if lines else "Select a copy to inspect its complete paths and cleanup checks.",
                         selected=bool(selected), paths=paths)
        self.update_controls()

    def select_all_ready(self):
        if self.busy:
            return
        self.tree.selection_set([key for key, row in self.rows.items() if row.get("status") == "ready"] if self.select_ready.get() else [])
        self.selected()

    def review_removal(self):
        plans = self.ready_selection()
        if self.busy or not self.acknowledged.get() or not plans or self.confirmation is not None:
            return
        confirm = self.confirmation = tk.Toplevel(self.window)
        confirm.title("Confirm removal of extra reading copies")
        confirm.configure(background=BACKGROUND)
        confirm.transient(self.window)
        frame = ttk.Frame(confirm, padding=18)
        frame.pack(fill="both", expand=True)
        count, total = len(plans), sum(plan.get("bytes", 0) for plan in plans)
        ttk.Label(frame, text=f"Remove {count} reviewed extra {'copy' if count == 1 else 'copies'} · {_size(total)}",
                  style="Section.TLabel").pack(anchor="w")
        detail = SelectionDetails(frame, title="Exact files selected for removal", height=12)
        detail.pack(fill="both", expand=True, pady=12)
        detail.set("\n\n".join(f"{index}. {plan['path']}\n{_size(plan.get('bytes', 0))}" for index, plan in enumerate(plans, 1)),
                   paths={f"{index}. Extra reading copy": (plan["path"], "This is the exact file selected for removal.") for index, plan in enumerate(plans, 1)})
        warning = ttk.Label(frame, text="The main papers and saved notes stay preserved. Old links in separately exported notebooks or backups may stop working. Changed copies are kept.",
                            wraplength=760, style="Muted.TLabel")
        warning.pack(fill="x", pady=(0, 12))
        warning.bind("<Configure>", lambda event: warning.configure(wraplength=max(80, event.width)))
        actions = ttk.Frame(frame)
        actions.pack(fill="x")

        def dismiss():
            self.confirmation = None
            confirm.destroy()

        def execute():
            dismiss()
            self.execute(plans)

        cancel = Button(actions, text="Cancel", command=dismiss)
        cancel.pack(side="right")
        Tooltip(cancel, "Keep every extra copy and return to the review.")
        apply = Button(actions, text="Remove reviewed copies", command=execute, style="Primary.TButton")
        apply.pack(side="right", padx=8)
        Tooltip(apply, "Recheck these exact files and remove only unchanged app-owned reading copies whose original sources and saved notes are preserved.")
        confirm.confirm_button, confirm.details = apply, detail
        confirm.protocol("WM_DELETE_WINDOW", dismiss)
        bind_dialog_close(confirm, dismiss)
        fit_dialog(confirm, self.window)
        confirm.grab_set()
        cancel.focus_set()

    def execute(self, plans):
        if self.busy or not self.alive() or not self.acknowledged.get():
            return
        self.busy = "removing"
        self.summary.set("Rechecking the selected sources and removing eligible extra copies…")
        self.update_controls()
        background(self.app, lambda: self.app.service.storage_action("cleanup", plans), self.completed, self.failed)

    def completed(self, results):
        if not self.alive():
            return
        self.busy = ""
        removed = [row for row in results if row.get("status") == "removed"]
        lines = [f"Removed {len(removed)} extra {'copy' if len(removed) == 1 else 'copies'} · {_size(sum(row.get('bytes', 0) for row in removed))} reclaimed."]
        paths = {}
        for index, row in enumerate(results, 1):
            lines.append(f"{'Removed' if row.get('status') == 'removed' else 'Kept'}: {row.get('path', '')}")
            if row.get("reason"):
                lines.append(row["reason"])
            if row.get("path"):
                paths[f"{index}. Reviewed copy"] = (row["path"], "The exact copy reviewed by cleanup; removed copies are no longer on disk.")
        self.report.set("\n".join(lines), paths=paths)
        self.app.refresh()
        self.refresh()

    def failed(self, error):
        if self.alive():
            self.busy = ""
            self.summary.set("Cleanup review paused. Copies requiring attention remain in place.")
            self.report.set(str(error))
            self.update_controls()

    def close(self):
        if self.busy == "removing":
            self.summary.set("The removal you confirmed is finishing. Please wait for its result.")
            return
        self.window.destroy()
