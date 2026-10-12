"""Tk interface with searchable notes, original page context and activity."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import queue
import shutil
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, font
from PIL import Image, ImageTk
from . import APP_NAME, __version__
from .exporting import paper_title
from .combined_pdf import materialize_combined, export_combined
from .service import Service
from .storage import SEARCH_FIELDS, NOTE_TYPES, digest_file
from .search import SearchSyntaxError
from .research_search import search_library
from .viewers import open_pdf_page, VIEWERS
from .theme import apply_theme, BACKGROUND, PANEL
from .remarkable_cloud import PAIR_URL
from .remarkable_sync import scoped_folders, effective_config
from .icons import Button, menu_action
from .widgets import Tooltip, PathField, ReadOnlyText, annotate_buttons, fit_dialog, bind_dialog_close, dismiss_tooltips, CellTooltip, SelectionDetails
from .dialogs import PreferencesDialog, ProcessingFields
from .pages import page_description, page_tooltip
from .view_state import LibraryView, read_view, cloud_destinations
from .pdf_worker import PDFWorker
from .image_viewport import ImageViewport
from .clipboard import copy_image
from .inbox import InboxController
from .workflow_ui import InboxView, ReconciliationWindow, background
from .research_ui import CitationWindow, SupplementsWindow
from .citations import export_citations
from .workspace_layouts import WorkspaceLayouts
from .time_display import local_time


class App(WorkspaceLayouts):
    def __init__(self, root, store, data_dir):
        self.root, self.store, self.data_dir = root, store, Path(data_dir)
        self.view = LibraryView(store.path)
        self.pdf_worker = PDFWorker()
        self.service = Service(store, pdf_worker=self.pdf_worker)
        self.viewer_preference = {"viewer": "system"}
        self.entries = []
        self.failed_papers = {}
        self.image = None
        self.closing = False
        self.search_after = None
        self.query_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="Notes search")
        self.context_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="Page context")
        self.context_window = None
        self.context_future = None
        self.pdf_open_future = None
        self.pdf_export_future = None
        self.pdf_export_busy = False
        self.query_results = queue.Queue()
        self.image_results = queue.Queue()
        self.dialog_results = queue.Queue()
        self.workflow_results = queue.Queue()
        self.workflow_futures = set()
        self.workflow_events = queue.Queue()
        self.workflow_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="Literature workflow")
        self.inbox = InboxController(store, data_dir, post=lambda event, payload: self.workflow_events.put((event, payload)))
        self.service.inbox = self.inbox
        self.reconciliation_window = None
        self.library_results = queue.Queue()
        self.library_future = None
        self.library_requested = False
        self.library_loaded = False
        self.cloud_path_results = queue.Queue()
        self.cloud_path_key = None
        self.cloud_path_future = None
        self.cloud_paths = {}
        self.cloud_root_available = False
        self.action_feedback = {}
        self.feedback_labels = {}
        self.query_generation = 0
        self.query_cancel = threading.Event()
        self.query_future = None
        self.notes_after = None
        self.refresh_needed = False
        self.next_refresh = 0
        self.preview_identity = None
        self.preview_future = None
        self.preview_cancel = threading.Event()
        self.query_signature = None
        self.paper_listing_key = None
        self.image_after = None
        self.image_size = None
        self.last_poll = time.monotonic()
        self.largest_ui_delay = 0
        self.style = apply_theme(root)
        root.title(f"{APP_NAME} {__version__}")
        root.geometry(f"{min(1250, root.winfo_screenwidth()-80)}x{min(820, root.winfo_screenheight()-100)}")
        root.minsize(940, 620)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.build()
        self.bind_shortcuts()
        self.initial_controls = []
        self.lock_initial_controls(self.root)
        self.status.set("Loading saved library…")
        self.refresh()
        root.after(10, self.poll)

    def lock_initial_controls(self, parent):
        for widget in parent.winfo_children():
            is_control = isinstance(widget, (ttk.Button, ttk.Entry, ttk.Combobox, ttk.Checkbutton))
            is_help = isinstance(widget, ttk.Button) and widget.cget("text") == "Help"
            if is_control and not is_help:
                self.initial_controls.append((widget, str(widget.cget("state"))))
                widget.configure(state="disabled")
            self.lock_initial_controls(widget)

    def cloud_config(self):
        return effective_config(self.view)

    def cloud_paired(self):
        return str(self.service.remarkable.vault.path) in self.view.files

    def build(self):
        self.status = tk.StringVar(value="Starting…")
        footer = ttk.Frame(self.root, padding=(20, 8))
        footer.pack(side="bottom", fill="x")
        status = ttk.Label(footer, textvariable=self.status, style="Muted.TLabel")
        status.pack(side="left", fill="x", expand=True)
        status.bind("<Configure>", lambda e: status.configure(wraplength=max(100, e.width-40)))
        self.details_button = Button(footer, text="View sync details", command=self.show_sync_details)
        Tooltip(self.details_button, "Open Library's latest sync summary and processing log.")
        self.work_progress = ttk.Progressbar(footer, length=95, mode="indeterminate")
        self.work_phase = tk.StringVar()
        self.work_label = ttk.Label(footer, textvariable=self.work_phase, style="Muted.TLabel")
        self.work_visible = False
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=20, pady=(8, 4))
        self.library_tab = ttk.Frame(self.tabs, padding=(12, 16))
        self.inbox_tab = ttk.Frame(self.tabs, padding=(12, 16))
        self.notes_tab = ttk.Frame(self.tabs, padding=(12, 16))
        self.remarkable_tab = ttk.Frame(self.tabs, padding=(12, 16))
        self.tabs.add(self.inbox_tab, text="Inbox")
        self.tabs.add(self.library_tab, text="Library")
        self.tabs.add(self.notes_tab, text="Notes")
        self.tabs.add(self.remarkable_tab, text="reMarkable")
        self.tabs.hide(self.remarkable_tab)
        self.inbox_view = InboxView(self, self.inbox_tab)
        self.build_library()
        self.build_reader()
        self.build_remarkable()
        self.tabs.bind("<<NotebookTabChanged>>", self.tab_changed)
        # Ordinary child widgets occupy the unused right end of the tab strip.
        # They move with the notebook and require no native title-bar overlay.
        self.utility_header = header = ttk.Frame(self.tabs)
        header.place(relx=1, x=-2, y=2, anchor="ne")
        self.help_button = Button(header, text="Help", command=self.help, style="Quiet.TButton")
        self.help_button.pack(side="right")
        self.settings_button = Button(header, text="Settings", command=self.global_settings, style="Quiet.TButton")
        self.settings_button.pack(side="right", padx=(0, 8))
        annotate_buttons(self.root)

    def refresh_integration_visibility(self):
        enabled = self.cloud_config()["integration_enabled"]
        if enabled:
            self.tabs.add(self.remarkable_tab, text="reMarkable")
            self.library_send_button.pack(side="left")
        elif self.tabs.tab(self.remarkable_tab, "state") != "hidden":
            if self.tabs.select() == str(self.remarkable_tab):
                self.tabs.select(self.library_tab)
            self.tabs.hide(self.remarkable_tab)
        if not enabled:
            self.library_send_button.pack_forget()

    def review_library(self):
        existing = self.reconciliation_window
        if existing and existing.window.winfo_exists():
            existing.window.lift()
            return existing
        self.reconciliation_window = ReconciliationWindow(self)
        return self.reconciliation_window

    def filing_recovery(self):
        window = tk.Toplevel(self.root)
        window.title("Files retained after interrupted filing")
        window.configure(background=BACKGROUND)
        bind_dialog_close(window, window.destroy)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        message = ttk.Label(frame, text="These filings need inspection. The app retained the available copies; it has not chosen which one to keep.", wraplength=750)
        message.pack(fill="x", pady=(0, 10))
        table = self.tree(frame, [("name", "Document", 270), ("reason", "What needs review", 480)], height=8, content_columns=())
        table.tooltip.value = lambda row, column: rows.get(row, {}).get("source", "") if column == "name" else table.set(row, column)
        table.tooltip.extra = lambda row, column: "Select this retained filing to inspect or copy the original and destination paths." if column == "name" else ""
        table.tooltip.full_with_help = True
        details = SelectionDetails(frame, "Original and destination locations", height=5)
        details.pack(fill="x", pady=10)
        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        rows = {}
        def open_location(field):
            selection = table.selection()
            if selection:
                self.open_path(str(Path(rows[selection[0]][field]).parent))
        original = Button(actions, text="Open inbox", command=lambda: open_location("source"), state="disabled")
        original.pack(side="left")
        destination = Button(actions, text="Open containing folder", command=lambda: open_location("path"), state="disabled")
        destination.pack(side="left", padx=8)
        Button(actions, text="Close", command=window.destroy).pack(side="right")
        Tooltip(original, "Open the original download's folder. Its file may already have been filed or moved.")
        Tooltip(destination, "Open the folder containing the retained destination copy.")
        def selected(event=None):
            selection = table.selection()
            row = rows.get(selection[0]) if selection else None
            details.set(f"{row['error']}\n\nOriginal: {row['source']}\nDestination: {row['path']}" if row else "Select a filing to see both locations.", selected=bool(row),
                        paths={"Original download": row["source"], "Retained destination": row["path"]} if row else {})
            for button in (original, destination):
                button.configure(state="normal" if row else "disabled")
        table.bind("<<TreeviewSelect>>", selected)
        def loaded(values):
            if not window.winfo_exists():
                return
            rows.update({row["job_id"]: row for row in values})
            self.update_rows(table, [(key, (Path(row["source"]).name, row["error"])) for key, row in rows.items()])
            if not rows:
                message.configure(text="No interrupted filings currently need review.")
            selected()
            fit_dialog(window, self.root)
        background(self, self.inbox.list_recovery_errors, loaded)
        annotate_buttons(window)
        return window

    def transfers(self):
        window = tk.Toplevel(self.root)
        window.title("reMarkable transfer queue")
        window.configure(background=BACKGROUND)
        bind_dialog_close(window, window.destroy)
        window.geometry("950x550")
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Pending and completed transfers", style="Section.TLabel").pack(anchor="w", pady=(0, 10))
        footer = ttk.Frame(frame)
        footer.pack(side="bottom", fill="x")
        table = self.tree(frame, [("name", "Paper / folder", 280), ("state", "Status", 150), ("reason", "Details", 420)], content_columns=())
        details = SelectionDetails(footer, "Selected transfer · complete locations", height=3)
        details.pack(fill="x", pady=(10, 0))
        actions = ttk.Frame(footer)
        actions.pack(fill="x", pady=(12, 0))
        retry = Button(actions, text="Retry transfers", command=lambda: self.service.command("remarkable_outbox"))
        retry.pack(side="left")
        Tooltip(retry, "Retry eligible transfers after connecting or fixing folder mappings. Completed transfers are retained in the list.")
        selected_actions = ttk.Frame(footer)
        selected_actions.pack(fill="x", pady=(8, 0))
        selected_retry = Button(selected_actions, text="Retry selected…", state="disabled")
        selected_retry.pack(side="left")
        cancel = Button(selected_actions, text="Cancel selected transfer", state="disabled")
        cancel.pack(side="left", padx=8)
        Tooltip(selected_retry, "Inspect and confirm the selected transfer using its current PDF and linked destination. A changed destination or PDF requires this explicit decision.")
        Tooltip(cancel, "Stop future attempts for this queued transfer. Local papers and any document already uploaded remain intact.")
        mapping = Button(selected_actions, text="Map and sync…", state="disabled")
        mapping.pack(side="left")
        Tooltip(mapping, "Choose a PC counterpart for the selected tablet folder, save its link and sync enabled transfers.")
        close = Button(actions, text="Close", command=window.destroy)
        close.pack(side="right")
        Tooltip(close, "Close the transfer list; queued work remains saved.")
        folder_reviews = {}
        current_jobs = {}
        def transfer_cell(row, column):
            if column != "name":
                return table.set(row, column)
            if row in current_jobs:
                return current_jobs[row].get("path", "") or table.set(row, column)
            review = folder_reviews.get(row, {})
            return next((folder["path"] for folder in self.view.preference("remarkable_folders", [])
                         if folder["id"] == review.get("id")), review.get("path") or table.set(row, column))
        table.tooltip.value = transfer_cell
        table.tooltip.extra = lambda row, column: "Select this transfer to inspect and copy its PC and tablet locations." if column == "name" else ""
        table.tooltip.full_with_help = True
        details_selection = None
        def selected(event=None):
            nonlocal details_selection
            selection = table.selection()
            mapping.configure(state="normal" if selection and selection[0] in folder_reviews else "disabled")
            job = current_jobs.get(selection[0]) if selection else None
            enabled = bool(job and job.get("state") not in {"sent", "cancelled", "sending"})
            for button in (selected_retry, cancel):
                button.configure(state="normal" if enabled else "disabled")
            catalog = {folder["id"]: folder["path"] for folder in self.view.preference("remarkable_folders", [])}
            lines = []
            paths = {}
            if job:
                lines = [f"PC file or folder: {job.get('path', '')}", f"Status: {job.get('state', 'Waiting')}"]
                paths["PC file or folder"] = job.get("path", "")
                if job.get("reason"):
                    lines.append(f"Details: {job['reason']}")
                if job.get("pc_root"):
                    lines.append(f"PC library when queued: {job['pc_root']}")
                    paths["PC library when queued"] = job["pc_root"]
                for key, label in (("folder_id", "Tablet destination when queued"),
                                   ("source_folder_id", "Tablet library when queued")):
                    if job.get(key):
                        lines.append(f"{label}: {catalog.get(job[key], 'Unavailable in the saved folder list')}")
                        if job[key] in catalog:
                            paths[label] = catalog[job[key]]
            elif selection and selection[0] in folder_reviews:
                review = folder_reviews[selection[0]]
                lines = [f"Tablet folder: {catalog.get(review['id'], review.get('path', review['name']))}",
                         "Status: Needs mapping", f"Details: {review['reason']}"]
                paths["Tablet folder"] = catalog.get(review["id"], review.get("path", ""))
            text = "\n".join(lines) if lines else "Select a transfer to see its complete locations and explanation."
            selected_id = selection[0] if selection else None
            # Periodic refreshes should not interrupt someone reading or copying
            # a long location. Keep the viewport when this same item changes.
            if details.text.get("1.0", "end-1c") != text:
                view = details.text.index("@0,0") if selected_id == details_selection else "1.0"
                details.set(text, selected=bool(lines), paths=paths)
                details.text.yview(view)
            details_selection = selected_id
        def retry_selected():
            selection = table.selection()
            job = current_jobs.get(selection[0]) if selection else None
            if not job or job.get("state") in {"sent", "cancelled", "sending"}:
                return
            if messagebox.askokcancel("Retry selected transfer", f"Retry this transfer using the current local file and currently linked tablet destination?\n\n{job['path']}\n\n{job.get('reason', '')}\n\nConfirming accepts changes to this PDF or its destination. Existing tablet documents are retained.", parent=window):
                self.service.command("remarkable_retry_transfer", job["id"], True, True)
        def cancel_selected():
            selection = table.selection()
            job = current_jobs.get(selection[0]) if selection else None
            if job and messagebox.askokcancel("Cancel transfer", "Stop future attempts for this transfer?\n\nYour local files and any document already uploaded will remain.", parent=window):
                self.service.command("remarkable_cancel_transfer", job["id"])
        selected_retry.configure(command=retry_selected)
        cancel.configure(command=cancel_selected)
        def map_selected():
            selection = table.selection()
            if selection and selection[0] in folder_reviews:
                self.set_cloud_mapping(folder_reviews[selection[0]]["id"])
        mapping.configure(command=map_selected)
        table.bind("<<TreeviewSelect>>", selected)
        def refresh():
            if self.closing or not window.winfo_exists():
                return
            jobs = self.view.preference("remarkable_outbox", [])
            current_jobs.clear()
            current_jobs.update({job["id"]: job for job in jobs})
            folder_reviews.clear()
            folder_reviews.update({"folder-review:" + row["id"]: row for row in self.view.preference("remarkable_folder_review", [])})
            rows = [(job.get("id", str(index)), (Path(job.get("path", job.get("name", "Folder"))).name,
                         job.get("state", "Waiting"), job.get("reason", ""))) for index, job in enumerate(jobs)]
            rows.extend((key, (row["name"], "Needs mapping", row["reason"])) for key, row in folder_reviews.items())
            self.update_rows(table, rows)
            selected()
            # Keep the callback alive until it can see that the list closed.
            # A callback owned by the destroyed window becomes invalid in Tcl.
            self.root.after(1500, refresh)
        refresh()
        annotate_buttons(window)
        fit_dialog(window, self.root)
        return window

    def saved_recovery_paths(self):
        return sorted({path for item in self.view.remarkable_items().values()
                       if isinstance(item.get("recovery_paths"), list)
                       for path in item.get("recovery_paths", []) if isinstance(path, str)})

    def global_settings(self):
        window = getattr(self, "preferences_window", None)
        if window and window.winfo_exists():
            window.lift()
            return
        self.preferences_dialog = PreferencesDialog(self)
        self.preferences_window = self.preferences_dialog.window

    def setup_inbox(self):
        self.global_settings()
        self.preferences_dialog.tabs.select(self.preferences_dialog.sorting_tab)

    def storage_maintenance(self):
        from .maintenance_ui import MaintenanceWindow
        return MaintenanceWindow(self)

    def organize_paper(self):
        from .research_tools import open_labels
        return open_labels(self)

    def saved_searches(self):
        from .research_tools import open_saved_searches
        return open_saved_searches(self)

    def refresh_label_choices(self):
        from .research_tools import labels
        background(self, lambda: labels(self.store), lambda values: self.label_picker.configure(values=["All papers", *values]) if not self.closing else None)

    def bind_shortcuts(self):
        def focus_search():
            self.tabs.select(self.notes_tab)
            self.search_entry.focus_set()
            self.search_entry.selection_range(0, "end")
        actions = {"<Control-f>": focus_search, "<F5>": self.service.request_sync,
                   "<Control-comma>": self.global_settings, "<Control-Shift-S>": self.saved_searches,
                   "<Control-Shift-T>": self.organize_paper, "<Control-Shift-A>": self.accessible_reader,
                   "<Alt-Key-1>": lambda: self.tabs.select(self.inbox_tab),
                   "<Alt-Key-2>": lambda: self.tabs.select(self.library_tab),
                   "<Alt-Key-3>": lambda: self.tabs.select(self.notes_tab)}
        for sequence, action in actions.items():
            self.root.bind(sequence, lambda event, function=action: (function(), "break")[1])

    def accessible_reader(self):
        from .accessible_reader import open_reader
        return open_reader(self)

    def build_feedback(self, parent, section):
        value = self.action_feedback[section] = tk.StringVar()
        label = ttk.Label(parent, textvariable=value, style="Muted.TLabel", wraplength=850)
        label.bind("<Configure>", lambda e: label.configure(wraplength=max(100, e.width)))
        self.feedback_labels[section] = label

    def notify(self, text, section="notes"):
        self.action_feedback[section].set(text)
        label = self.feedback_labels[section]
        if text:
            # Restore feedback at its original position only when it has text.
            siblings = label.master.winfo_children()
            following = next((w for w in siblings[siblings.index(label)+1:] if w.winfo_manager() == "pack"), None)
            options = {"before": following} if following else {}
            label.pack(fill="x", pady=(0, 8), **options)
        else:
            label.pack_forget()

    def tab_changed(self, event=None):
        dismiss_tooltips()
        # The footer describes background work. Action feedback belongs to its
        # tab, so opening a source PDF cannot leave a warning on the cloud tab.
        for section in self.action_feedback:
            if str(getattr(self, {"library": "library_tab", "notes": "notes_tab", "cloud": "remarkable_tab"}[section])) != self.tabs.select():
                self.notify("", section)
        if hasattr(self, "inbox_view") and self.tabs.select() == str(self.inbox_tab) and self.library_loaded:
            self.inbox_view.refresh()

    def show_sync_details(self):
        self.tabs.select(self.library_tab)
        if not self.activity_frame.winfo_manager():
            self.toggle_activity()
        summary = self.view.preference("sync_summary", {})
        if summary.get("details") and summary.get("at") != getattr(self, "details_summary_at", None):
            self.details_summary_at = summary["at"]
            self.activity.configure(state="normal")
            self.activity.insert("end", "\nLatest saved sync details:\n" + "\n".join(
                f"{detail['path']}\n  {detail['message']}" for detail in summary["details"]) + "\n")
            self.activity.configure(state="disabled")
        error = self.saved_cloud_error()
        if error and error != getattr(self, "details_cloud_error", None):
            self.details_cloud_error = error
            self.activity.configure(state="normal")
            self.activity.insert("end", f"\nLatest saved reMarkable failure:\n  {error}\n")
            self.activity.configure(state="disabled")
        paths = self.saved_recovery_paths()
        if paths and paths != getattr(self, "details_recovery_paths", None):
            self.details_recovery_paths = paths
            self.activity.configure(state="normal")
            self.activity.insert("end", "\nPrevious PDF copies retained for recovery:\n" + "\n".join(paths) +
                                 "\nReview these copies before removing them; the newer PDF is already saved.\n")
            self.activity.configure(state="disabled")
        self.activity.see("end")
        self.refresh_activity_paths()
        self.activity.focus_set()

    def build_remarkable(self):
        tab = self.remarkable_tab
        config = self.cloud_config()
        self.cloud_header = header = ttk.LabelFrame(tab, text="Connection & sync", padding=8)
        header.pack(fill="x", pady=(0, 16))
        toolbar = ttk.Frame(header)
        toolbar.pack(fill="x", pady=(0, 8))
        self.cloud_sync_button = Button(toolbar, text="Sync PDFs", command=self.sync_cloud_now, style="Primary.TButton")
        self.cloud_sync_button.pack(side="left")
        Tooltip(self.cloud_sync_button, lambda: "Choose an existing PC destination for the reMarkable cloud source in Sync setup first." if not self.cloud_pc_root.get() else
                "A reMarkable cloud check is running; wait for it to finish." if self.service.cloud_busy else
                "Apply the pending source and PC destination changes, then download changed PDFs and process enabled transfer and folder queues." if self.cloud_routing_values() != self.cloud_saved_routing else
                "Download changed PDFs, retry PDFs needing attention, and process enabled upload and folder queues beneath the linked roots.")
        self.cloud_browse_button = Button(toolbar, text="Refresh folders", command=lambda: self.service.command("remarkable_browse"))
        self.cloud_browse_button.pack(side="left", padx=8)
        self.cloud_transfers_button = Button(toolbar, text="Transfer queue…", command=self.transfers)
        self.cloud_transfers_button.pack(side="left", padx=(0, 8))
        Tooltip(self.cloud_transfers_button, "Review queued uploads, missing folder links, and completed transfers. Retry paused work after resolving its explanation.")
        Tooltip(self.cloud_browse_button, lambda: "Connect reMarkable before loading the folder catalog." if not self.cloud_paired() else
                "A reMarkable cloud check is running; wait for it to finish." if self.service.cloud_busy else "Refresh tablet folders without downloading PDFs. If folder mirroring is enabled, this can create PC counterparts and queue new tablet folders.")
        self.cloud_connect_button = Button(toolbar, text="Connect reMarkable…", command=self.pair_remarkable, style="Primary.TButton")
        self.cloud_connection_button = self.more_button(toolbar, [("Reconnect…", self.pair_remarkable), ("Disconnect", self.disconnect_cloud)], text="Connection ▾")
        self.cloud_connection_button.pack(side="left", padx=(8, 0))
        self.cloud_status = tk.StringVar()
        status_row = ttk.Frame(header)
        status_row.pack(fill="x", pady=(0, 6))
        self.cloud_connection_status = ttk.Label(status_row, textvariable=self.cloud_status, style="Muted.TLabel", wraplength=600)
        self.cloud_connection_status.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.cloud_connection_status.bind("<Configure>", lambda e: self.cloud_connection_status.configure(wraplength=max(100, e.width)))
        self.build_feedback(header, "cloud")
        self.cloud_error = tk.StringVar()
        self.cloud_error_row = error_row = ttk.Frame(header)
        self.cloud_error_label = ttk.Label(error_row, textvariable=self.cloud_error, foreground="#FFB4AB", wraplength=800)
        self.cloud_error_label.pack(side="left", fill="x", expand=True)
        self.cloud_error_label.bind("<Configure>", lambda e: self.cloud_error_label.configure(wraplength=max(100, e.width)))
        self.cloud_dismiss_button = Button(error_row, text="Dismiss", command=self.dismiss_cloud_error)
        self.cloud_dismissed_error = None
        self.cloud_saved_routing = None
        self.cloud_pending_enabled = None
        self.cloud_scope_ids = [""]
        self.cloud_setup_frame = setup = ttk.Frame(header)
        setup.pack(fill="x", pady=(0, 6))
        self.cloud_route_summary = tk.StringVar()
        self.cloud_summary_row = summary_row = ttk.Frame(setup)
        summary_row.pack(fill="x")
        summary = ttk.Label(summary_row, textvariable=self.cloud_route_summary)
        summary.pack(side="left", fill="x", expand=True)
        summary.bind("<Configure>", lambda e: summary.configure(wraplength=max(100, e.width)))
        Tooltip(summary, lambda: f"reMarkable cloud source: {self.cloud_scope_path() or 'Choose a source'}\nPC destination: {self.cloud_pc_root.get() or 'Choose an existing folder'}\n\nEdit setup to inspect or copy either complete location.")
        self.cloud_setup_button = Button(toolbar, text="Edit setup", command=self.toggle_cloud_setup)
        self.cloud_setup_button.pack(side="left", padx=8)
        self.cloud_setup_panel = routing = ttk.LabelFrame(setup, text="Sync setup", padding=6)
        self.cloud_setup_expanded = not bool(config["pc_root"] and config.get("source_folder_id"))
        if self.cloud_setup_expanded:
            summary_row.pack_forget()
            routing.pack(fill="x", pady=(8, 0))
        ttk.Label(routing, text="Cloud source").grid(row=0, column=0, sticky="w", padx=(0, 12))
        cloud_scope_row = ttk.Frame(routing)
        cloud_scope_row.grid(row=0, column=1, sticky="ew", pady=(0, 4))
        self.cloud_scope = ttk.Combobox(cloud_scope_row, state="readonly", width=20, values=["Find Literature automatically"])
        self.cloud_scope.current(0)
        self.cloud_scope.pack(side="left", fill="x", expand=True)
        self.cloud_scope_path_access = PathField(self.cloud_scope, "Only this source and its descendants are downloaded to this PC. Automatic selection requires exactly one Literature folder.", value=self.cloud_scope_path)
        self.cloud_scope_copy = self.cloud_scope_path_access.add_copy_button(cloud_scope_row)
        self.cloud_scope_copy.pack(side="right", padx=(6, 0))
        ttk.Label(routing, text="PC destination").grid(row=0, column=2, sticky="w", padx=12)
        self.cloud_pc_root = tk.StringVar(value=config["pc_root"])
        cloud_pc_row = ttk.Frame(routing)
        cloud_pc_row.grid(row=0, column=3, sticky="ew")
        self.cloud_pc_entry = ttk.Entry(cloud_pc_row, textvariable=self.cloud_pc_root, width=26)
        self.cloud_pc_entry.pack(side="left", fill="x", expand=True)
        self.cloud_pc_path_access = PathField(self.cloud_pc_entry, "The selected reMarkable cloud source maps directly here. Existing descendant paths must match or be mapped separately.")
        self.cloud_pc_copy = self.cloud_pc_path_access.add_copy_button(cloud_pc_row)
        self.cloud_pc_copy.pack(side="right", padx=(6, 0))
        browse = Button(routing, text="Browse…", command=self.choose_cloud_root)
        browse.grid(row=0, column=4, padx=(8, 0))
        Tooltip(browse, "Choose the existing PC folder corresponding to the selected reMarkable cloud source, normally Sorted.")
        self.cloud_apply_button = Button(routing, text="Apply folder changes", command=self.save_cloud_routing)
        self.cloud_apply_button.grid(row=1, column=1, columnspan=3, sticky="e", pady=(4, 0))
        Tooltip(self.cloud_apply_button, lambda: "The visible reMarkable cloud source and PC destination are already saved. Change either to apply edits." if self.cloud_routing_values() == self.cloud_saved_routing else "Save the reMarkable cloud source and PC destination. Automatic checks use the saved routing.")
        self.cloud_routing_pending = None
        self.cloud_apply_status = tk.StringVar()
        ttk.Label(routing, textvariable=self.cloud_apply_status, style="Muted.TLabel").grid(row=1, column=4, sticky="w", padx=8)
        routing.columnconfigure(1, weight=1)
        routing.columnconfigure(3, weight=2)
        self.cloud_enabled = tk.BooleanVar(value=config["enabled"])
        self.cloud_auto = auto = ttk.Checkbutton(toolbar, text="Automatic checks (every 5 min)", variable=self.cloud_enabled, command=self.toggle_cloud_sync)
        auto.pack(side="left", padx=(12, 0))
        Tooltip(auto, lambda: "Connect reMarkable before enabling automatic checks." if not self.cloud_paired() else
                "Choose and apply a PC destination for the reMarkable cloud source before enabling automatic checks." if not self.cloud_config()["pc_root"] else
                "Download changed tablet PDFs every five minutes while this app is open. Applies immediately to future checks. Enabled folder mirroring and queued uploads run separately; turn off cloud services in Connections to pause all cloud activity.")
        self.cloud_routing_note = tk.StringVar()
        self.cloud_routing_label = note = ttk.Label(header, textvariable=self.cloud_routing_note, style="Muted.TLabel", wraplength=900)
        note.bind("<Configure>", lambda e: note.configure(wraplength=max(100, e.width)))
        self.cloud_scope.bind("<<ComboboxSelected>>", self.cloud_routing_changed)
        self.cloud_pc_root.trace_add("write", self.cloud_routing_changed)
        self.cloud_pane = pane = ttk.Panedwindow(tab, orient="horizontal")
        pane.pack(fill="both", expand=True)
        folders = ttk.Frame(pane, width=280, height=300, padding=(0, 0, 16, 0))
        folders.pack_propagate(False)
        ttk.Label(folders, text="Folder mappings", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        buttons = ttk.Frame(folders)
        buttons.pack(fill="x", pady=(0, 8))
        self.cloud_map_button = Button(buttons, text="Map and sync…", command=self.map_cloud_folder)
        self.cloud_map_button.grid(row=0, column=0, sticky="w")
        self.cloud_unmap_button = Button(buttons, text="Unlink folder…", command=self.unmap_cloud_folder)
        self.cloud_unmap_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        def arrange_mapping_actions(event):
            fits = event.width >= self.cloud_map_button.winfo_reqwidth() + self.cloud_unmap_button.winfo_reqwidth() + 8
            self.cloud_unmap_button.grid_configure(row=0 if fits else 1, column=1 if fits else 0,
                                                  padx=(8, 0) if fits else 0, pady=0 if fits else (4, 0))
        buttons.bind("<Configure>", arrange_mapping_actions)
        Tooltip(self.cloud_map_button, lambda: "Choose an existing PC counterpart, save this folder link and sync enabled transfers." if self.cloud_folders.selection() else "Select a reMarkable cloud folder first. Refresh folders if none are listed.")
        Tooltip(self.cloud_unmap_button, self.cloud_unmap_help)
        self.cloud_folders_empty = tk.StringVar()
        self.cloud_folders_empty_label = ttk.Label(folders, textvariable=self.cloud_folders_empty, style="Muted.TLabel", wraplength=340)
        self.mapping_details = SelectionDetails(folders, "Selected mapping", height=2)
        self.cloud_folders = self.tree(folders, [("name", "Cloud folder", 180), ("local", "PC destination", 280)])
        self.cloud_folders.tooltip.extra = lambda row, column: "This tablet folder's corresponding PC location. Select the row to inspect and copy its locations."
        self.cloud_folders.tooltip.full_with_help = True
        self.cloud_folders.bind("<<TreeviewSelect>>", self.cloud_selection_changed)
        pane.add(folders, weight=1)
        review = ttk.Frame(pane, width=650, height=300)
        review.pack_propagate(False)
        self.review_heading = tk.StringVar(value="PDFs needing attention · 0")
        ttk.Label(review, textvariable=self.review_heading, style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        buttons = ttk.Frame(review)
        buttons.pack(fill="x", pady=(0, 8))
        self.cloud_open_button = Button(buttons, text="Open PDF", command=self.open_cloud_review)
        self.cloud_open_button.pack(side="left")
        Tooltip(self.cloud_open_button, lambda: "Open the selected retained reMarkable PDF on this PC." if not self.cloud_open_button.instate(["disabled"]) else "Select a reMarkable review PDF with an available download on this PC first.")
        self.cloud_review_map_button = Button(buttons, text="Map and sync…", command=self.map_review_folder)
        self.cloud_review_map_button.pack(side="left", padx=8)
        Tooltip(self.cloud_review_map_button, lambda: "Save this PDF's cloud folder link and sync enabled transfers. Conversion errors and local edits need separate attention." if self.cloud_review.selection() else "Select a reMarkable review PDF first.")
        Button(buttons, text="Open review folder", command=lambda: self.open_path(self.cloud_config()["review_dir"])).pack(side="left")
        self.cloud_review_empty = tk.StringVar()
        self.cloud_review_empty_label = ttk.Label(review, textvariable=self.cloud_review_empty, style="Muted.TLabel", wraplength=530)
        self.review_details = SelectionDetails(review, "Selected PDF · paths & explanation", height=2)
        self.cloud_review = self.tree(review, [("name", "PDF", 240), ("folder", "Cloud location", 170), ("reason", "Needs attention", 185)], content_columns=())
        self.cloud_review.tooltip.value = self.review_cell_value
        self.cloud_review.tooltip.extra = lambda row, column: "Select this tablet PDF to inspect and copy its saved locations." if column == "folder" else ""
        self.cloud_review.tooltip.full_with_help = True
        self.cloud_review.bind("<Double-1>", lambda event: self.open_cloud_review())
        self.cloud_review_detail = tk.StringVar()

        self.cloud_review.bind("<<TreeviewSelect>>", self.cloud_review_selected)
        pane.add(review, weight=4)
        self.initial_split(pane, .30)

    def choose_cloud_root(self):
        path = filedialog.askdirectory(title="PC folder corresponding to the cloud source (Sorted)", parent=self.root)
        if path:
            self.cloud_pc_root.set(path)

    def toggle_cloud_setup(self):
        self.cloud_setup_expanded = not self.cloud_setup_expanded
        if self.cloud_setup_expanded:
            self.cloud_summary_row.pack_forget()
            self.cloud_setup_panel.pack(fill="x", pady=(8, 0))
        else:
            self.cloud_setup_panel.pack_forget()
            self.cloud_summary_row.pack(fill="x")
        self.refresh_cloud_folders()
        self.cloud_setup_button.configure(text="Hide setup" if self.cloud_setup_expanded else "Edit setup")

    def dismiss_cloud_error(self):
        self.cloud_dismissed_error = self.view.preference("remarkable_error", "")
        self.cloud_error.set("")
        self.cloud_error_row.pack_forget()

    def pair_remarkable(self):
        window = tk.Toplevel(self.root)
        window.title("Connect reMarkable cloud")
        window.configure(background=BACKGROUND)
        bind_dialog_close(window, window.destroy)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Pair this app with your reMarkable account", style="Section.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Open the pairing page, sign in, and generate an eight-character code. "
                  "Enter it here. Your account password stays with reMarkable.", wraplength=470).pack(anchor="w", pady=12)
        import webbrowser
        Button(frame, text="Open reMarkable pairing page", command=lambda: webbrowser.open(PAIR_URL)).pack(anchor="w")
        code = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=code, width=24, show="•")
        entry.pack(anchor="w", pady=12)
        Tooltip(entry, "Enter the eight-character one-time code from reMarkable's pairing page, not your account password.")
        ttk.Label(frame, text="The pairing token is protected by your Windows account. "
                  "This connection downloads PDFs and annotations. Optional PDF uploads and folder creation are enabled separately in Settings → Connections. Existing cloud files are retained.",
                  wraplength=470, style="Muted.TLabel").pack(anchor="w")
        def connect():
            if len(code.get().strip()) != 8:
                messagebox.showerror("Pairing code", "Enter the eight-character code from the pairing page.", parent=window)
                return
            self.service.command("remarkable_connect", code.get().strip())
            code.set("")
            window.destroy()
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(16, 0))
        Button(actions, text="Connect", command=connect, style="Primary.TButton").pack(side="right")
        cancel = Button(actions, text="Cancel", command=window.destroy)
        cancel.pack(side="right", padx=(0, 8))
        Tooltip(cancel, "Close without pairing this PC with reMarkable.")
        annotate_buttons(window)
        fit_dialog(window, self.root)

    def disconnect_cloud(self):
        self.cloud_enabled.set(False)
        self.cloud_pending_enabled = False
        self.service.command("remarkable_disconnect")

    def toggle_cloud_sync(self):
        self.cloud_pending_enabled = self.cloud_enabled.get()
        self.service.command("remarkable_settings", {"enabled": self.cloud_pending_enabled})
        self.refresh_cloud_status()

    def cloud_routing_values(self):
        index = self.cloud_scope.current()
        return (self.cloud_scope_ids[index] if index >= 0 else "", self.cloud_pc_root.get().strip())

    def cloud_scope_path(self):
        index = self.cloud_scope.current()
        source_id = self.cloud_scope_ids[index] if 0 <= index < len(self.cloud_scope_ids) else ""
        return next((folder["path"] for folder in self.view.preference("remarkable_folders", [])
                     if folder["id"] == source_id), "")

    def cloud_routing_changed(self, *_):
        if not hasattr(self, "cloud_folders"):
            return
        self.refresh_cloud_folders()

    def sync_cloud_now(self):
        if self.save_cloud_routing():
            self.service.command("remarkable_sync")

    def cloud_selection_changed(self, event=None):
        selection = self.cloud_folders.selection()
        self.cloud_map_button.configure(state="normal" if selection else "disabled")
        config = self.cloud_config()
        mapped = selection and (selection[0] in config["mappings"] or
                                selection[0] == config.get("source_folder_id") and bool(config["pc_root"]))
        self.cloud_unmap_button.configure(state="normal" if mapped else "disabled")
        values = self.cloud_folders.item(selection[0], "values") if selection else ()
        paths = {"Tablet folder": values[0]} if values else {}
        if values and values[1] not in {"Needs mapping", "Checking path…"}:
            paths["PC destination"] = values[1]
        self.mapping_details.set(f"Cloud folder: {values[0]}\nPC destination: {values[1]}" if values else
                                 "Select a mapping to see its complete cloud and PC paths.", selected=bool(values), paths=paths)
        if values:
            self.mapping_details.pack(side="bottom", fill="x", pady=(8, 0), before=self.cloud_folders.master)
        else:
            self.mapping_details.pack_forget()

    def cloud_unmap_help(self):
        selection = self.cloud_folders.selection()
        if not selection:
            return "Select a linked reMarkable cloud folder first."
        if selection[0] == self.cloud_config().get("source_folder_id"):
            return "Unlink the reMarkable cloud source's PC destination and turn off automatic checks. Existing PDFs and notes are retained."
        if self.cloud_unmap_button.instate(["disabled"]):
            return "This reMarkable cloud folder follows the source's PC path matching; it has no separate mapping to remove."
        return "Remove this reMarkable cloud folder's explicit PC mapping and return to source path matching. Existing PDFs and notes are retained."

    def review_cell_value(self, row, column):
        item = self.view.remarkable_items().get(row, {})
        return item.get("reason", "") if column == "reason" else self.cloud_review.set(row, column)

    @staticmethod
    def review_reason(item):
        reason = item.get("reason", "")
        kind = item.get("reason_kind", "")
        if kind == "conversion" or reason.startswith("Annotation conversion"):
            return "Conversion needs review"
        if kind == "local_conflict" or reason.startswith("A local PDF conflicts"):
            return "Local PDF conflict"
        if "excluded" in reason:
            return "Destination excluded"
        if reason.startswith("No matching PC folder"):
            return "Needs mapping"
        return reason

    def cloud_review_selected(self, event=None):
        selection = self.cloud_review.selection()
        item = self.view.remarkable_items().get(selection[0], {}) if selection else {}
        empty = "" if not self.cloud_review.get_children() else "Select a PDF to see its review reason."
        self.cloud_review_detail.set(item.get("reason", empty))
        lines = [f"PDF: {item.get('name', '')}", f"Cloud location: {item.get('cloud_path', '')}"]
        if item.get("target"):
            lines.append(f"PC destination: {item['target']}")
        if item.get("review_pdf"):
            lines.append(f"Retained PDF: {item['review_pdf']}")
        lines.append(f"Needs attention: {item.get('reason', '')}")
        paths = {label: item[key] for key, label in (("cloud_path", "Tablet location"), ("target", "PC destination"), ("review_pdf", "Retained PDF")) if item.get(key)}
        self.review_details.set("\n".join(lines) if item else empty or "No PDFs currently need attention.", selected=bool(item), paths=paths)
        if item:
            self.review_details.pack(side="bottom", fill="x", pady=(8, 0), before=self.cloud_review.master)
        else:
            self.review_details.pack_forget()
        available = item.get("review_pdf") in self.view.files
        self.cloud_open_button.configure(state="normal" if available else "disabled")
        self.cloud_review_map_button.configure(state="normal" if item.get("parent") else "disabled")

    def save_cloud_routing(self):
        path = self.cloud_pc_root.get().strip()
        if path and not Path(path).is_dir():
            messagebox.showerror("PC library root", "Choose an existing PC folder.", parent=self.root)
            return False
        source_id, _ = self.cloud_routing_values()
        path = str(Path(path).resolve()) if path else ""
        self.cloud_pc_root.set(path)
        self.service.command("remarkable_settings", {"pc_root": path,
                                                     "source_folder_id": source_id, "source_folder_name": "Literature"})
        self.cloud_routing_pending = (source_id, path)
        self.refresh_cloud_folders()
        return True

    def set_cloud_mapping(self, folder_id):
        path = filedialog.askdirectory(title="PC folder corresponding to this cloud folder", parent=self.root)
        if not path:
            return
        source_id, _ = self.cloud_routing_values()
        if folder_id == source_id:
            self.cloud_pc_root.set(str(Path(path).resolve()))
        if not self.save_cloud_routing():
            return
        self.service.command("remarkable_map", folder_id, None if folder_id == source_id else str(Path(path).resolve()))
        self.service.command("remarkable_sync")

    def map_cloud_folder(self):
        selection = self.cloud_folders.selection()
        if selection:
            self.set_cloud_mapping(selection[0])

    def unmap_cloud_folder(self):
        selection = self.cloud_folders.selection()
        if not selection:
            return
        folder_id = selection[0]
        config = self.cloud_config()
        source = folder_id == config.get("source_folder_id")
        if not source and folder_id not in config["mappings"]:
            return
        if source and not config["pc_root"] and folder_id not in config["mappings"]:
            return
        detail = ("This removes the source's PC destination and turns off automatic checks until you choose a destination again."
                  if source else "This removes the folder's explicit mapping. Future downloads use source path matching.")
        if not messagebox.askyesno("Unlink cloud folder?", detail + "\n\nExisting PDFs, notes and folders are retained.", parent=self.root):
            return
        self.service.command("remarkable_unlink", folder_id)
        if source:
            self.cloud_pc_root.set("")
            self.cloud_enabled.set(False)
            self.cloud_pending_enabled = False
            self.cloud_auto.configure(state="disabled")
            self.cloud_routing_pending = (config.get("source_folder_id", ""), "")
            if not self.cloud_setup_expanded:
                self.toggle_cloud_setup()

    def map_review_folder(self):
        selection = self.cloud_review.selection()
        if selection:
            item = self.view.remarkable_items().get(selection[0], {})
            self.set_cloud_mapping(item.get("parent", ""))

    def open_cloud_review(self):
        selection = self.cloud_review.selection()
        if selection:
            item = self.view.remarkable_items().get(selection[0], {})
            path = item.get("review_pdf")
            if path and Path(path).exists():
                # Review must expose the retained copy itself, even when its
                # unresolved version correctly blocks the combined reader.
                self.launch_pdf(path, section="cloud")
            else:
                messagebox.showinfo("Review download", "The retained cloud copy has not been downloaded successfully yet.", parent=self.root)

    def saved_cloud_error(self):
        error = self.view.preference("remarkable_error", "")
        # Earlier versions saved intentional shutdown as a cloud failure.
        return "" if error in {"reMarkable sync stopped", "reMarkable PDF conversion stopped", "reMarkable download stopped"} else error

    def refresh_cloud_status(self):
        paired = self.cloud_paired()
        config = self.cloud_config()
        check = self.view.preference("remarkable_last_check", {}) or self.view.preference("remarkable_last_sync", {})
        root = config["pc_root"]
        if not paired:
            status = "Not paired — connect reMarkable to begin."
        elif not root:
            status = "Paired · Setup incomplete — choose your PC destination."
        elif root not in self.view.directories:
            status = "Paired · PC destination is unavailable. Saved PDFs and notes are retained."
        else:
            status = "Paired"
        if paired:
            status += " · Automatic checks on" if config["enabled"] else " · Automatic checks off"
            if self.service.cloud_busy:
                status += " · Checking cloud…"
            if self.cloud_pending_enabled is not None:
                if config["enabled"] == self.cloud_pending_enabled:
                    self.cloud_pending_enabled = None
                else:
                    status += " · Applying automatic-check setting…"
            if check:
                try:
                    checked = datetime.fromisoformat(check["at"]).astimezone().strftime("%b %d, %I:%M %p")
                except (KeyError, ValueError):
                    checked = "unknown"
                status += f" · Last successful check: {checked}"
            else:
                status += " · No successful cloud check yet"
        if self.cloud_pending_enabled is None:
            self.cloud_enabled.set(bool(config["enabled"]))
        self.cloud_status.set(status)
        self.cloud_auto.configure(state="normal" if paired and root else "disabled")
        error = self.saved_cloud_error()
        shown_error = error if error != self.cloud_dismissed_error else ""
        self.cloud_error.set(f"Cloud check failed: {shown_error} · Retry with Sync PDFs or check Connection." if shown_error else "")
        if shown_error:
            self.cloud_error_row.pack(fill="x", before=self.cloud_setup_frame)
            self.cloud_dismiss_button.pack(side="right", padx=(8, 0))
        else:
            self.cloud_error_row.pack_forget()
        if paired:
            self.cloud_connect_button.pack_forget()
            self.cloud_connection_button.pack(side="left", padx=(8, 0), before=self.cloud_setup_button)
            self.cloud_sync_button.pack(side="left", before=self.cloud_browse_button)
        else:
            self.cloud_connection_button.pack_forget()
            self.cloud_sync_button.pack_forget()
            self.cloud_connect_button.pack(side="left", before=self.cloud_browse_button)
        self.cloud_browse_button.configure(state="normal" if paired and not self.service.cloud_busy else "disabled")

    def refresh_cloud_folders(self):
        config = self.cloud_config()
        source_id, root = self.cloud_routing_values()
        catalog = self.view.preference("remarkable_folders", [])
        self.cloud_scope_path_access.refresh()
        self.cloud_pc_path_access.refresh()
        draft = (source_id, root) != self.cloud_saved_routing
        source = self.cloud_scope.get().split(" [")[0] if source_id else "Literature (not yet confirmed)"
        source_short = source.rsplit("/", 1)[-1]
        local_short = Path(root).name if root else "Choose PC destination"
        self.cloud_route_summary.set(f"{source_short[:48]} → {local_short[:48]}")
        applying = self.cloud_routing_pending == (source_id, root) and draft
        self.cloud_apply_status.set("Applying…" if applying else "Unsaved changes" if draft else "Saved")
        self.cloud_apply_button.configure(state="normal" if draft and not applying else "disabled")
        self.cloud_setup_button.configure(text="Hide setup" if self.cloud_setup_expanded else "Edit setup")
        path_key = (repr(catalog), source_id, root, repr(config["mappings"]))
        valid_root = root in self.view.directories if root == config["pc_root"] else self.cloud_root_available and path_key == getattr(self, "cloud_paths_key", None)
        self.cloud_sync_button.configure(text="Apply & sync PDFs" if draft else "Sync PDFs",
            state="normal" if self.cloud_paired() and valid_root and not self.service.cloud_busy else "disabled")
        self.cloud_routing_note.set("Only this source is downloaded. Missing PC paths go to review." if root else
            "Choose your existing PC library folder in Sync setup. Other saved libraries are listed in Settings → Library & diagnostics.")
        if self.cloud_setup_expanded:
            self.cloud_routing_label.pack_forget()
        else:
            self.cloud_routing_label.pack(fill="x", pady=(8, 0))
        if not catalog:
            empty = "Connect reMarkable, then refresh folders." if not self.cloud_paired() else "No folder catalog loaded. Click Refresh folders to find Literature."
        elif not source_id:
            empty = "Choose the source in Sync setup, or refresh folders to locate Literature automatically."
        elif not scoped_folders(catalog, source_id):
            empty = "The saved source is absent from this catalog. Refresh folders or choose its replacement."
        else:
            empty = ""
        self.cloud_folders_empty.set(empty)
        if empty:
            self.cloud_folders_empty_label.pack(fill="x", pady=(0, 4), before=self.cloud_folders.master)
        else:
            self.cloud_folders_empty_label.pack_forget()
        signature = (path_key, repr(self.cloud_paths))
        if self.cloud_path_key != path_key and self.cloud_path_future is None:
            self.cloud_path_key = path_key
            routing = {**config, "source_folder_id": source_id, "pc_root": root}
            future = self.cloud_path_future = self.query_executor.submit(cloud_destinations, catalog, routing, self.data_dir)
            future.add_done_callback(lambda result, key=path_key: self.cloud_path_results.put((key, result)))
        if signature == getattr(self, "cloud_folder_signature", None):
            self.cloud_selection_changed()
            return
        self.cloud_folder_signature = signature
        selected = self.cloud_folders.selection()
        rows = []
        for folder in scoped_folders(catalog, source_id):
            local = self.cloud_paths.get(folder["id"], "Checking path…") if path_key == getattr(self, "cloud_paths_key", None) else "Checking path…"
            rows.append((folder["id"], (folder["path"], local)))
        self.update_rows(self.cloud_folders, rows)
        if selected and self.cloud_folders.exists(selected[0]):
            self.cloud_folders.selection_set(selected[0])
        self.cloud_selection_changed()

    def refresh_cloud(self):
        self.refresh_cloud_status()
        config = self.cloud_config()
        choices = sorted(self.view.preference("remarkable_folders", []), key=lambda f: f["path"].casefold())
        current = self.cloud_routing_values()
        saved = (config.get("source_folder_id", ""), config["pc_root"])
        # Adopt worker discoveries only when no genuine edits are waiting.
        desired, root = saved if self.cloud_saved_routing is None or current == self.cloud_saved_routing else current
        self.cloud_scope_ids = [""] + [f["id"] for f in choices]
        labels = ["Find Literature automatically"] + [f"{f['path']} [{f['id'][:8]}]" for f in choices]
        if desired not in self.cloud_scope_ids:
            self.cloud_scope_ids.append(desired)
            labels.append("Saved source unavailable — refresh folders")
        self.cloud_scope.configure(values=labels)
        self.cloud_scope.current(self.cloud_scope_ids.index(desired))
        self.cloud_saved_routing = saved
        if self.cloud_pc_root.get() != root:
            self.cloud_pc_root.set(root)
        self.refresh_cloud_folders()
        if self.cloud_routing_pending == saved:
            self.cloud_routing_pending = None
            if self.cloud_setup_expanded and root and (desired, root) == saved:
                self.toggle_cloud_setup()
        selected = self.cloud_review.selection()
        rows = []
        for item_id, item in self.view.remarkable_items().items():
            if item["state"] == "review":
                rows.append((item_id, (item["name"], item["cloud_path"], self.review_reason(item))))
        self.update_rows(self.cloud_review, rows)
        self.review_heading.set(f"PDFs needing attention · {len(rows)}")
        if selected and self.cloud_review.exists(selected[0]):
            self.cloud_review.selection_set(selected[0])
        self.cloud_review_selected()
        if self.cloud_review.get_children():
            self.cloud_review_empty.set("")
        elif not self.view.preference("remarkable_last_sync", {}):
            self.cloud_review_empty.set("No PDFs have been checked yet. Complete setup, then sync.")
        else:
            self.cloud_review_empty.set("No PDFs need review from the last sync.")
        if self.cloud_review_empty.get():
            self.cloud_review_empty_label.pack(fill="x", pady=(0, 4), before=self.cloud_review.master)
        else:
            self.cloud_review_empty_label.pack_forget()

    def tree(self, parent, columns, height=8, content_columns=None):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings",
                            height=height, selectmode="browse")
        heading_face = ttk.Style(tree).lookup("Treeview.Heading", "font") or "TkDefaultFont"
        measure_heading = font.Font(root=tree, font=heading_face).measure
        for key, title, width in columns:
            tree.heading(key, text=title, anchor="w")
            minimum = max(60, measure_heading(title) + 28)
            tree.column(key, width=max(width, minimum), minwidth=minimum,
                        stretch=key in {"name", "text", "reason", "local"})
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        tree.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        CellTooltip(tree)
        tree.horizontal_scrollbar = horizontal
        tree.initial_widths = {key: tree.column(key, "width") for key, _, _ in columns}
        tree.content_columns = {"name", "local", "folder", "text", "reason"} if content_columns is None else set(content_columns)
        tree.user_columns = set()
        def scroll_x(first, last):
            horizontal.set(first, last)
            if float(first) > .001 or float(last) < .999:
                horizontal.grid()
            else:
                horizontal.grid_remove()
            tree.tooltip.reset()
        def column_resize(event):
            if tree.identify_region(event.x, event.y) == "separator":
                display = tree.identify_column(event.x)
                shown = tree.cget("displaycolumns")
                shown = tree.cget("columns") if shown == ("#all",) else shown
                index = int(display[1:]) - 1
                if 0 <= index < len(shown):
                    # Keep the chosen width while untouched columns can still
                    # use the available space after a window resize.
                    key = shown[index]
                    tree.user_columns.add(key)
                    tree.column(key, stretch=False)
        tree.bind("<ButtonPress-1>", column_resize, add="+")
        def fit_column(event):
            if tree.identify_region(event.x, event.y) != "separator":
                return
            shown = tree.cget("displaycolumns")
            shown = tree.cget("columns") if shown == ("#all",) else shown
            index = int(tree.identify_column(event.x)[1:]) - 1
            if 0 <= index < len(shown):
                key = shown[index]
                face = ttk.Style(tree).lookup("Treeview", "font") or "TkDefaultFont"
                measure = font.Font(root=tree, font=face).measure
                width = max([tree.column(key, "minwidth")] +
                            [measure(tree.set(row, key)) + 28 for row in tree.get_children()])
                tree.column(key, width=width, stretch=False)
                tree.user_columns.add(key)
                return "break"
        fit_tag = "FitColumns:" + str(tree)
        tree.bindtags((fit_tag,) + tree.bindtags())
        tree.bind_class(fit_tag, "<Double-Button-1>", fit_column)
        tree.bind("<Shift-MouseWheel>", lambda e: tree.xview_scroll(-int(e.delta / 120), "units"))
        tree.configure(yscrollcommand=scrollbar.set, xscrollcommand=scroll_x)
        return tree

    @staticmethod
    def initial_split(pane, fraction):
        """Set a useful initial split, then leave the user's sash position alone."""
        def position(event):
            if event.width > 50 and not getattr(pane, "split_set", False):
                pane.split_set = True
                pane.after_idle(lambda: pane.sashpos(0, round(pane.winfo_width() * fraction)) if pane.winfo_exists() else None)
            for frame in pane.winfo_children():
                for details in frame.winfo_children():
                    if isinstance(details, SelectionDetails):
                        height = 3 if event.height > 380 else 2 if event.height > 230 else 1
                        if int(details.text.cget("height")) != height:
                            details.text.configure(height=height)
        pane.bind("<Configure>", position, add="+")

    def more_button(self, parent, actions, text="Actions ▾"):
        button = Button(parent, text=text)
        menu = tk.Menu(button, tearoff=False, background=PANEL, foreground="#DCE4EE",
                       activebackground="#1B629B", activeforeground="white", borderwidth=0)
        for label, action in actions:
            menu_action(menu, label, action)
        button.action_menu = menu
        help_text = {
            "Reconnect…": "Pair this PC with reMarkable again using a new code.", "Disconnect": "Remove this PC's reMarkable pairing token; local PDFs and notes remain.",
            "Open source PDF": "Open the selected paper's PDF.",
            "Save editable copy…": "Make a separate Word notebook for your writing.", "Change history": "Read saved annotation changes for the selected note's actual PDF copy.",
            "Export annotated PDF…": "Save the selected paper with its combined PC and tablet notes as a separate PDF.",
            "Review extra PDFs…": "Review old app-generated reading copies and remove only verified copies whose notes and current notebook links are preserved.",
            "Citation details…": "Review, edit, copy, or look up the selected paper's citation information.",
            "Export citations…": "Export citations for the current paper/folder selection, or papers in the current Notes search, as RIS or BibTeX.",
            "Find supplementary files…": "Find supplementary links for the selected paper and review downloads or attached files.",
            "Tags & collections…": "Organize the selected paper with local tags and research collections.",
            "Saved searches…": "Save or apply searches in the current folder and paper scope.",
            "Accessible reading view…": "Open current results in your browser with semantic headings, keyboard search and screen reader support.",
            "Library storage & backups…": "Create or restore verified backups and compact the library without removing history.",
            "Rebuild notebook…": "Regenerate this folder's Word notebook from saved notes.",
            "Remove folder…": "Stop watching the selected folder. Original files remain on disk.",
            "Locate moved folder…": "Reconnect a moved folder while retaining saved history.",
            "Folder settings": "Change this folder's extraction and Word settings.",
            "Filing recovery…": "Inspect copies retained after interrupted filing.",
            "Review library…": "Compare duplicate papers and PC/tablet folder differences before changing relationships.",
        }
        Tooltip(button, "\n".join(f"{label}: {help_text[label]}" for label, _ in actions))
        def show():
            try:
                menu.tk_popup(button.winfo_rootx(), button.winfo_rooty()+button.winfo_height())
            finally:
                menu.grab_release()
        button.configure(command=show)
        return button



    def toggle_activity(self):
        if self.activity_frame.winfo_manager():
            self.activity_frame.pack_forget()
            self.activity_toggle.configure(text="Show sync details")
        else:
            self.refresh_activity_paths()
            self.activity_frame.pack(fill="x", pady=(10, 0))
            self.activity_toggle.configure(text="Hide sync details")

    def refresh_activity_paths(self):
        paths = {}
        for project in self.view.projects():
            paths[f"Watched folder · {len(paths) + 1}"] = project["root"]
        for detail in self.view.preference("sync_summary", {}).get("details", []):
            if detail.get("path"):
                paths[f"Sync location · {len(paths) + 1}"] = detail["path"]
        for recovery in self.saved_recovery_paths():
            paths[f"Retained recovery copy · {len(paths) + 1}"] = recovery
        previous = self.activity_path_access.value()
        self.activity_location_paths = paths
        self.activity_locations.configure(values=list(paths), state="readonly" if paths else "disabled")
        choice = next((label for label, path in paths.items() if path == previous), next(iter(paths), ""))
        self.activity_locations.set(choice)
        self.activity_path_access.refresh()
        self.activity_path_tooltip.set_paths(paths)

    def watched_folder_path(self, project_id):
        return next((project["root"] for project in self.view.projects() if str(project["id"]) == str(project_id)), "")

    def library_paper_path(self, document_id):
        document = next((row for row in self.view.documents() if row["id"] == document_id), None)
        return document["path"] if document else self.failed_papers.get(document_id, ("", ""))[0]

    def reader_folder_path(self):
        index = self.reader_folder.current()
        ids = getattr(self, "reader_project_ids", [])
        return self.watched_folder_path(ids[index - 1]) if 0 < index <= len(ids) else ""

    def reader_paper_path(self):
        index = self.reader_paper.current()
        ids = getattr(self, "reader_paper_ids", [])
        if 0 < index <= len(ids) and not self.all_projects.get():
            return self.library_paper_path(ids[index - 1])
        entry = self.selected_entry() if hasattr(self, "notes") else None
        return self.entry_paper_path(entry) if entry else ""

    @staticmethod
    def entry_paper_path(entry):
        return entry.get("combined_view_path") or entry.get("source_link_path") or entry["path"]

    @staticmethod
    def entry_pdf_target(entry):
        if entry.get("kind") == "pdf" and not entry.get("logical_paper_id"):
            return entry["path"], entry["page"]
        if entry.get("combined_view_unavailable"):
            raise ValueError(str(entry["combined_view_unavailable"]))
        return (entry.get("logical_paper_id") or entry.get("combined_view_path") or entry["path"],
                entry.get("combined_view_page", entry["page"]))

    def note_help(self):
        y = self.notes.winfo_pointery() - self.notes.winfo_rooty()
        row = self.notes.identify_row(y)
        entry = self.entries[int(row)] if row and int(row) < len(self.entries) else self.selected_entry()
        return page_tooltip(entry) if entry else "Select a note to read its text, page numbering and source PDF link."

    def note_cell_value(self, row, column):
        entry = self.entries[int(row)] if int(row) < len(self.entries) else {}
        if column != "text" or not entry:
            return self.notes.set(row, column)
        text = entry.get("comment") or entry.get("quote") or entry.get("ocr") or "Drawing with page context"
        if entry.get("kind") == "pdf":
            text = "PDF: " + text
        if self.all_projects.get():
            text = Path(entry["path"]).stem + ": " + text
        return text

    def view_notes(self, event=None):
        self.all_projects.set(False)
        self.sync_reader_filters()
        self.refresh_notes()
        self.tabs.select(self.notes_tab)

    def sync_reader_filters(self):
        p = self.selected_project()
        pid = p["id"] if p else None
        ids = [None] + self.reader_project_ids
        self.reader_folder.current(ids.index(pid) if pid in ids and not self.all_projects.get() else 0)
        self.reader_paper_ids = list(self.papers.get_children())
        self.reader_paper.configure(values=["All papers"] + [self.papers.item(i, "values")[0] for i in self.reader_paper_ids],
                                    state="disabled" if self.all_projects.get() else "readonly")
        sel = self.papers.selection()
        self.reader_paper.current(self.reader_paper_ids.index(sel[0])+1 if sel and not self.all_projects.get() else 0)
        self.notebook_button.configure(state="normal" if p and not self.all_projects.get() else "disabled")
        available = bool(p and p["root"] in self.view.directories)
        self.library_folder_button.configure(state="normal" if available else "disabled")
        self.notes_folder_button.configure(state="normal" if available and not self.all_projects.get() else "disabled")
        self.reader_folder_path_access.refresh()
        self.reader_paper_path_access.refresh()

    def reader_folder_selected(self, event=None):
        index = self.reader_folder.current()
        self.all_projects.set(index == 0)
        if index > 0:
            self.projects.selection_set(str(self.reader_project_ids[index-1]))
            self.project_selected()
        else:
            self.sync_reader_filters()
            self.refresh_notes()

    def reader_paper_selected(self, event=None):
        index = self.reader_paper.current()
        if index > 0:
            self.papers.selection_set(self.reader_paper_ids[index-1])
        else:
            self.papers.selection_remove(*self.papers.selection())
        self.refresh_notes()

    def paper_selected(self, event=None):
        self.update_paper_details()
        self.sync_reader_filters()
        self.refresh_notes()

    def update_paper_details(self):
        selection = self.papers.selection()
        key = selection[0] if selection else None
        document = next((d for d in self.view.documents() if d["id"] == key), None)
        failed = self.failed_papers.get(key)
        path = document["path"] if document else failed[0] if failed else ""
        values = self.papers.item(key, "values") if key else ()
        reason = failed[1] if failed else ""
        if path and document:
            project = self.selected_project()
            reason = next((r["error"] for r in self.view.errors(project["id"]) if r["path"] == path), "") if project else ""
        details = f"PDF: {path}\nStatus: {values[2]}" if path else "Select a paper to see its complete path and status."
        if reason:
            details += f"\nNeeds attention: {reason}"
        if document and len(document.get("variant_paths", [])) > 1:
            details += "\nLinked sources:\n" + "\n".join(document["variant_paths"])
        paths = {"Source PDF": path} if path else {}
        if document:
            for index, variant in enumerate(document.get("variant_paths", []), 1):
                if variant != path:
                    paths[f"Linked source {index}"] = variant
        self.paper_details.set(details, selected=bool(path), paths=paths)
        self.library_source_button.configure(state="normal" if path and (failed or not document["missing"]) else "disabled")
        role = document.get("paper_source", {}).get("metadata", {}).get("role") if document else None
        self.library_send_button.configure(state="normal" if document and not document["missing"] and role != "tablet_render" else "disabled")


    def selected_project(self):
        sel = self.projects.selection()
        return self.view.project(int(sel[0])) if sel else None

    def update_search_options_summary(self):
        filtered = len(self.search_fields) != len(SEARCH_FIELDS) or self.search_mode != "Words / Boolean" or self.note_type != "All notes"
        self.search_options_button.configure(text="Search in… •" if filtered else "Search in…")
        self.search_summary.set(" · ".join([f"{len(self.search_fields)} search fields", self.search_mode, self.note_type]) if filtered else "")
        if filtered:
            self.search_summary_label.pack(fill="x", before=self.reader_pane, pady=(0, 8))
        else:
            self.search_summary_label.pack_forget()

    def search_options(self):
        window = tk.Toplevel(self.root)
        window.title("Search options")
        window.configure(background=BACKGROUND)
        window.transient(self.root)
        bind_dialog_close(window, window.destroy)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Search in", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        fields = {key: tk.BooleanVar(value=key in self.search_fields) for key in SEARCH_FIELDS}
        for index, (key, label) in enumerate(SEARCH_FIELDS.items()):
            check = ttk.Checkbutton(frame, text=label, variable=fields[key])
            check.grid(row=1+index//2, column=index%2, sticky="w", padx=(0, 20), pady=5)
            Tooltip(check, f"Include {label.lower()} when matching your query.")
        ttk.Label(frame, text="Handwriting matches available OCR only. Printed text beneath ink is a separate field.",
                  wraplength=500, style="Muted.TLabel").grid(row=6, column=0, columnspan=2, sticky="w", pady=12)
        mode, kind = tk.StringVar(value=self.search_mode), tk.StringVar(value=self.note_type)
        ttk.Label(frame, text="Match").grid(row=7, column=0, sticky="w", pady=5)
        match = ttk.Combobox(frame, textvariable=mode, values=["Words / Boolean", "Exact phrase"], state="readonly")
        match.grid(row=7, column=1, sticky="ew")
        Tooltip(match, "Words / Boolean supports AND, OR, NOT and quoted phrases. Exact phrase matches the literal phrase and treats operators as text.")
        ttk.Label(frame, text="Show").grid(row=8, column=0, sticky="w", pady=5)
        types = ttk.Combobox(frame, textvariable=kind, values=NOTE_TYPES, state="readonly")
        types.grid(row=8, column=1, sticky="ew")
        Tooltip(types, "All notes includes every annotation. Highlights filters markup; Drawings filters pen notes; Typed notes includes annotations with comments.")
        option_help = tk.StringVar()
        ttk.Label(frame, textvariable=option_help, style="Muted.TLabel", wraplength=500).grid(row=11, column=0, columnspan=2, sticky="w", pady=(8, 0))
        def explain_options(*_):
            option_help.set(("Your words are matched across the selected fields." if mode.get() != "Exact phrase" else "Your complete phrase is matched as written.") + f" Showing: {kind.get()}.")
        mode.trace_add("write", explain_options)
        kind.trace_add("write", explain_options)
        explain_options()
        def reset():
            for var in fields.values():
                var.set(True)
            mode.set("Words / Boolean")
            kind.set("All notes")
        def apply():
            selected = [key for key, var in fields.items() if var.get()]
            if not selected:
                messagebox.showinfo("Choose a field", "Select at least one field to search.", parent=window)
                return
            self.search_fields, self.search_mode, self.note_type = selected, mode.get(), kind.get()
            self.update_search_options_summary()
            self.refresh_notes()
            window.destroy()
        buttons = ttk.Frame(frame)
        ttk.Label(frame, text='Words / Boolean: use uppercase AND, OR, NOT, quotes, and parentheses.\n'
                  'Example: (iodine OR gold) AND "spectral CT" NOT phantom\n'
                  'Spaces mean AND. Exact phrase treats operators as ordinary text.',
                  style="Muted.TLabel", wraplength=500).grid(row=9, column=0, columnspan=2, sticky="w", pady=(12, 0))
        buttons.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        Button(buttons, text="Reset all", command=reset).pack(side="left", padx=(0, 8))
        Button(buttons, text="Clear fields", command=lambda: [v.set(False) for v in fields.values()]).pack(side="left")
        Button(buttons, text="Apply", command=apply, style="Primary.TButton").pack(side="right")
        cancel = Button(buttons, text="Cancel", command=window.destroy)
        cancel.pack(side="right", padx=(0, 8))
        Tooltip(cancel, "Close without applying these search options.")
        annotate_buttons(window)
        window.update_idletasks()
        fit_dialog(window, self.root)
        window.resizable(False, False)

    def selected_entry(self):
        sel = self.notes.selection()
        return self.entries[int(sel[0])] if sel and int(sel[0]) < len(self.entries) else None

    def add(self):
        path = filedialog.askdirectory(title="Choose a folder of annotated PDFs")
        if path:
            self.service.command("add", path)

    def show_folder_menu(self, event):
        keyboard = getattr(event, "num", None) != 3
        row = (self.projects.focus() or next(iter(self.projects.selection()), "")) if keyboard else self.projects.identify_row(event.y)
        if not row or not keyboard and self.projects.identify_region(event.x, event.y) not in {"cell", "tree"}:
            return "break"
        project = self.view.project(int(row))
        if not project:
            return "break"
        self.projects.selection_set(row)
        self.projects.focus(row)
        self.projects.focus_set()
        self.project_selected()
        # Keep the action tied to the clicked folder even if a refresh changes selection.
        project = dict(project)
        self.folder_menu.entryconfigure(0, command=lambda: self.rebuild(project))
        self.folder_menu.entryconfigure(1, command=lambda: self.remove(project))
        self.folder_menu.entryconfigure(2, command=lambda: self.locate_folder(project))
        if keyboard:
            self.projects.see(row)
            x, y, width, height = self.projects.bbox(row) or (0, 0, 0, 0)
            x, y = self.projects.winfo_rootx() + x + 12, self.projects.winfo_rooty() + y + height
        else:
            x, y = event.x_root, event.y_root
        dismiss_tooltips()
        try:
            self.folder_menu.tk_popup(x, y)
        finally:
            self.folder_menu.grab_release()
        return "break"

    def open_selected_folder(self, notes=False):
        p = self.selected_project()
        if p and (not notes or not self.all_projects.get()):
            self.open_path(p["root"])

    def locate_folder(self, project=None):
        p = project if project is not None else self.selected_project()
        if not p:
            return
        path = filedialog.askdirectory(title="Locate this watched folder at its new location", parent=self.root)
        if path and messagebox.askokcancel("Locate moved folder", f"Use this as the new location of your watched folder?\n\nPrevious: {p['root']}\nNew: {path}\n\nSaved notes, history and folder settings will stay together. This does not move or delete your files.", parent=self.root):
            self.service.command("relocate", p["id"], path)

    def remove(self, project=None):
        p = project if project is not None else self.selected_project()
        if p and messagebox.askyesno("Remove folder?", f"Remove this watched folder and its saved annotation history from the library?\n\n{p['root']}\n\nPDFs and Word notebooks remain on disk.", parent=self.root, default="no", icon="warning"):
            self.service.command("remove", p["id"])

    def rebuild(self, project=None):
        p = project if project is not None else self.selected_project()
        if p and messagebox.askyesno(
                "Rebuild notebook?",
                f"Regenerate this notebook from saved PDF annotations using current formatting?\n\n{p['output']}\n\n"
                "This replaces the generated notebook's contents. Edits made outside the app since its last export "
                "are preserved in Notebook backups, but are not merged into the rebuilt notebook. "
                "Use an editable copy for ongoing writing.",
                parent=self.root, default="no", icon="warning"):
            self.service.command("rebuild", p["id"])

    def open_path(self, path):
        try:
            if not Path(path).exists():
                raise FileNotFoundError(f"File is not available yet:\n{path}")
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("Unable to open", str(exc))

    def open_notebook(self):
        p = self.selected_project()
        if p:
            self.open_path(p["output"])

    def reserved_output(self, target):
        return Path(target).resolve() in [Path(r["output"]).resolve() for r in self.view.projects()]

    def editable_copy(self):
        if self.all_projects.get():
            messagebox.showinfo("Choose a folder", "Select one folder in Notes to copy its notebook, or use Export view for notes from all folders.")
            return
        p = self.selected_project()
        if not p:
            return
        if not Path(p["output"]).exists():
            messagebox.showinfo("Notebook", "The notebook has not been exported yet. Open Show sync details in Library for progress.")
            return
        target = filedialog.asksaveasfilename(defaultextension=".docx", filetypes=[("Word document", "*.docx")],
                                            initialfile=f"My notes on {Path(p['root']).name}.docx")
        if target:
            if self.reserved_output(target):
                messagebox.showerror("Choose another filename", "An editable copy must be separate from a generated notebook.")
                return
            self.notify("Saving editable notebook copy…", "notes")
            def copied(future):
                try:
                    future.result()
                    self.notify("Editable notebook copy saved.", "notes")
                    self.open_path(target)
                except Exception as exc:
                    messagebox.showerror("Copy failed", str(exc), parent=self.root)
            future = self.query_executor.submit(shutil.copy2, p["output"], target)
            future.add_done_callback(lambda result: self.dialog_results.put((self.root, copied, result)))

    def export_view(self):
        target = filedialog.asksaveasfilename(defaultextension=".docx", initialfile="Selected research notes.docx",
                                            filetypes=[("Word document", "*.docx")])
        if target:
            if self.reserved_output(target):
                messagebox.showerror("Choose another filename", "Use a separate file for a filtered export.")
                return
            self.service.command("export_view", target, [e for e in self.entries if e.get("kind") != "pdf"])

    def research_paper(self):
        if self.tabs.select() == str(self.notes_tab):
            entry = self.selected_entry()
            if entry:
                return entry["document_id"], entry["path"]
        selected = self.papers.selection()
        if selected and any(row["id"] == selected[0] for row in self.view.documents()):
            return selected[0], self.library_paper_path(selected[0])
        messagebox.showinfo("Choose a paper", "Select a paper in Library or a result in Notes first.", parent=self.root)
        return None

    def citation_details(self):
        paper = self.research_paper()
        if paper:
            return CitationWindow(self, paper[0])

    def supplementary_files(self):
        paper = self.research_paper()
        if paper:
            return SupplementsWindow(self, paper[0], paper[1])

    def export_citation_selection(self):
        in_notes = self.tabs.select() == str(self.notes_tab)
        if in_notes and self.search.get().strip():
            ids = list(dict.fromkeys(entry["document_id"] for entry in self.entries))
        else:
            project = self.selected_project()
            selected = self.papers.selection()
            if in_notes and self.all_projects.get():
                ids = [row["id"] for row in self.view.documents()]
            elif selected:
                ids = [selected[0]]
            else:
                ids = [row["id"] for row in self.view.documents(project["id"] if project else None)]
        if not ids:
            messagebox.showinfo("No papers", "Choose a folder or search with matching papers first.", parent=self.root)
            return
        target = filedialog.asksaveasfilename(parent=self.root, title=f"Export citations — {len(ids)} selected paper(s)",
                                            defaultextension=".ris", initialfile="Research citations.ris",
                                            filetypes=[("RIS citations", "*.ris"), ("BibTeX citations", "*.bib")])
        if target:
            section = "notes" if in_notes else "library"
            self.notify("Exporting citations…", section)
            background(self, lambda: export_citations(self.store, ids, target),
                       lambda count: self.notify(f"Exported {count} citation(s) to {target}", section),
                       lambda error: self.notify(f"Could not export citations: {error}", section))

    def settings(self):
        project = self.selected_project()
        if not project:
            messagebox.showinfo("Folder settings", "Select a watched folder first.", parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title(f"Folder settings — {Path(project['root']).name}")
        window.configure(background=BACKGROUND)
        window.transient(self.root)
        bind_dialog_close(window, window.destroy)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        folder_path_row = ttk.Frame(window, padding=(18, 0, 18, 12))
        folder_path_row.pack(side="bottom", fill="x", before=frame)
        ttk.Label(folder_path_row, text="Folder").pack(side="left", padx=(0, 8))
        folder_path = ttk.Entry(folder_path_row)
        folder_path.insert(0, project["root"])
        folder_path.configure(state="readonly")
        folder_path.pack(side="left", fill="x", expand=True)
        path_access = PathField(folder_path, "These settings apply to this watched folder only.")
        path_access.add_copy_button(folder_path_row).pack(side="right", padx=(6, 0))
        values = json.loads(project["settings"])
        fields = ProcessingFields(frame, values)
        ttk.Label(frame, text="These changes apply only to this folder. Changed extraction options re-read its PDFs.",
                  style="Muted.TLabel", wraplength=510).grid(row=6, column=0, columnspan=2, sticky="w", pady=(12, 8))
        def save():
            settings = fields.values(window)
            if settings is None:
                return
            self.service.command("settings", project["id"], {**values, **settings})
            window.destroy()
        actions = ttk.Frame(frame)
        actions.grid(row=7, column=0, columnspan=2, sticky="ew")
        apply = Button(actions, text="Apply changes", command=save, style="Primary.TButton")
        apply.pack(side="right")
        cancel = Button(actions, text="Cancel", command=window.destroy)
        cancel.pack(side="right", padx=(0, 8))
        Tooltip(cancel, "Close without saving these folder settings.")
        Tooltip(apply, "Save this folder's settings and refresh its notes. Other folders keep their settings.")
        annotate_buttons(window)
        fit_dialog(window, self.root)
        window.resizable(False, False)

    def refresh(self):
        """Coalesce background reads; callbacks keep using the last good view."""
        self.library_requested = True
        if self.library_future is not None or self.closing:
            return
        self.library_requested = False
        self.library_future = future = self.query_executor.submit(read_view, self.store.path)
        future.add_done_callback(lambda result: self.library_results.put(result))

    def finish_view(self, future):
        self.library_future = None
        if self.closing:
            return
        try:
            view = future.result()
        except Exception as exc:
            # Writers can briefly hold the rollback-journal lock. Keep the
            # saved reader visible and retry instead of waiting inside Tk.
            logging.info("Library snapshot deferred: %s", exc)
            self.refresh_needed = True
            self.next_refresh = time.monotonic() + 2
            return
        initial = not self.library_loaded
        self.view = view
        if not self.inbox._initialized:
            self.inbox.set_config_snapshot(view.preference("inbox", {}))
        if self.cloud_path_future is None:
            self.cloud_path_key = None
        if initial:
            self.library_loaded = True
            for widget, state in self.initial_controls:
                if widget.winfo_exists():
                    widget.configure(state=state)
            self.initial_controls.clear()
            preference = view.preference("pdf_viewer", {"viewer": "system"})
            self.viewer_preference = preference if isinstance(preference, dict) and preference.get("viewer") in VIEWERS else {"viewer": "system"}
            config = self.cloud_config()
            if config["pc_root"] and config.get("source_folder_id") and self.cloud_setup_expanded:
                self.toggle_cloud_setup()
        self.render_view()
        if initial:
            if any(d["count"] for d in view.documents()):
                self.tabs.select(self.notes_tab)
            self.status.set("Saved library loaded. Checking for changes in the background…")
            self.service.start()
            if view.preference("inbox", {}):
                background(self, self.inbox.pending_filings, self.resume_filings)
            if self.inbox.config().get("enabled"):
                self.inbox.start()
                self.inbox_view.refresh()
            elif not view.documents():
                self.tabs.select(self.inbox_tab)
        if self.library_requested:
            self.refresh()

    def resume_filings(self, results):
        handled = set(self.view.preference("inbox_handoffs", []))
        for result in results:
            if result.get("is_pdf") and result.get("job_id") not in handled:
                self.service.command("filed_pdf", result)
            else:
                background(self, lambda job_id=result["job_id"]: self.inbox.acknowledge_filing(job_id), lambda _: None)

    @staticmethod
    def update_rows(tree, rows):
        """Keep unchanged items, selection and scroll position in place."""
        desired = {str(key): tuple(str(v) for v in values) for key, values in rows}
        missing = [key for key in tree.get_children() if key not in desired]
        if missing:
            tree.delete(*missing)
        changed = bool(missing)
        for index, (key, values) in enumerate(desired.items()):
            if not tree.exists(key):
                tree.insert("", index, iid=key, values=values)
                changed = True
            elif tree.item(key, "values") != values:
                tree.item(key, values=values)
                changed = True
            tree.move(key, "", index)
        if changed and hasattr(tree, "initial_widths"):
            tree.tooltip.reset()
            face = ttk.Style(tree).lookup("Treeview", "font") or "TkDefaultFont"
            measure = font.Font(root=tree, font=face).measure
            for index, column in enumerate(tree.cget("columns")):
                if column in tree.user_columns or column not in tree.content_columns:
                    continue
                cap = {"name": 480, "local": 900, "folder": 520, "text": 600, "reason": 600}.get(column, 480)
                width = max([tree.initial_widths[column]] + [min(cap, measure(values[index][:300]) + 24)
                            for values in list(desired.values())[:200]])
                tree.column(column, width=width)

    def render_view(self):
        self.refresh_integration_visibility()
        self.refresh_cloud()
        summary = self.view.preference("sync_summary", {})
        counts = [(summary.get(key, 0), label) for key, label in (
            ("unavailable_folders", "watched folders unavailable"), ("unreadable_folders", "folders unreadable"),
            ("pdf_errors", "PDF read errors"), ("export_waiting", "notebooks waiting to save"))]
        issues = [f"{count} {label}" for count, label in counts if count]
        recovery_count = len(self.saved_recovery_paths())
        if recovery_count:
            noun = "copy" if recovery_count == 1 else "copies"
            issues.append(f"{recovery_count} previous PDF {noun} retained for recovery")
        self.local_sync_summary.set("Last sync: " + "; ".join(issues) if issues else "Last sync completed without issues." if summary else "Add a watched folder or sync to check its PDFs.")
        if issues or (self.cloud_config()["integration_enabled"] and self.cloud_error.get()):
            self.details_button.pack(side="right", padx=(8, 0))
        else:
            self.details_button.pack_forget()
        selection = self.projects.selection()
        projects = self.view.projects()
        self.reader_project_ids = [p["id"] for p in projects]
        names = [Path(p["root"]).name for p in projects]
        labels = [name if names.count(name) == 1 else f"{name} — {Path(p['root']).parent.name} [{p['id']}]"
                  for name, p in zip(names, projects)]
        self.reader_folder.configure(values=["All folders"] + labels)
        rows = []
        for p in projects:
            state = "Export pending" if p["error"] else "Needs export" if p["dirty"] else "Saved " + local_time(p["exported_at"])
            errors = self.view.errors(p["id"])
            if errors:
                state = f"{len(errors)} PDF read errors"
            if p["root"] not in self.view.directories:
                state = "Folder unavailable"
            rows.append((p["id"], (Path(p["root"]).name, state)))
        self.update_rows(self.projects, rows)
        children = self.projects.get_children()
        if children:
            self.projects.selection_set(selection[0] if selection and selection[0] in children else children[0])
        self.project_selected()
        if self.activity_frame.winfo_manager():
            self.refresh_activity_paths()

    def project_selected(self, event=None):
        p = self.selected_project()
        pid = p["id"] if p else None
        listing_key = (pid, self.view.note_token(pid), repr(self.view.errors(pid)) if pid else "")
        if listing_key == self.paper_listing_key:
            self.update_paper_details()
            self.sync_reader_filters()
            self.refresh_notes()
            return
        self.paper_listing_key = listing_key
        old = self.papers.selection()
        self.failed_papers = {}
        if pid != self.active_project_id:
            self.all_projects.set(False)
            self.active_project_id = pid
        for button in self.library_actions:
            button.configure(state="normal" if p else "disabled")
        self.location.set(p["root"] if p else "Add a folder to begin collecting PDF annotations.")
        self.folder_details.set(f"PC folder: {p['root']}" if p else self.location.get(), selected=bool(p),
                                paths={"Watched PC folder": p["root"]} if p else {})
        self.paper_heading.set(f"Papers in {Path(p['root']).name}" if p else "Papers")
        rows = []
        if p:
            errors = {r["path"]: r["error"] for r in self.view.errors(p["id"])}
            shown = set()
            for d in self.view.documents(p["id"]):
                shown.add(d["path"])
                relative = str(Path(d["path"]).relative_to(Path(p["root"])))
                rows.append((d["id"], (relative, d["count"], "Read error" if d["path"] in errors else "Unavailable" if d["missing"] else "Available")))
            for index, path in enumerate(sorted(errors.keys() - shown)):
                relative = str(Path(path).relative_to(Path(p["root"])))
                iid = f"error-{index}"
                self.failed_papers[iid] = (path, errors[path])
                rows.append((iid, (relative, "—", "Read error")))
        self.update_rows(self.papers, rows)
        if old and self.papers.exists(old[0]):
            self.papers.selection_set(old[0])
        self.update_paper_details()
        self.sync_reader_filters()
        self.refresh_notes()

    def search_changed(self, *_):
        if self.search_after:
            self.root.after_cancel(self.search_after)
        self.search_after = self.root.after(250, self.refresh_notes)

    def refresh_notes(self):
        """Query off the Tk thread without loading every crop; cancel stale searches."""
        if self.search_after:
            self.root.after_cancel(self.search_after)
        self.search_after = None
        p = self.selected_project()
        paper = self.papers.selection()
        current = self.selected_entry()
        options = dict(project_id=p["id"] if p and not self.all_projects.get() else None,
                       document_id=paper[0] if paper and not self.all_projects.get() else None,
                       query=self.search.get(), fields=list(self.search_fields),
                       match_mode=self.search_mode, note_type=self.note_type, include_images=False,
                       label_filter=self.label_filter.get())
        signature = (self.search_scope.get(), repr(options), self.view.note_token(options["project_id"], options["document_id"]))
        if signature == self.query_signature:
            return
        self.query_signature = signature
        self.query_cancel.set()
        if self.query_future:
            self.query_future.cancel()
        self.query_cancel = cancelled = threading.Event()
        self.query_generation += 1
        generation = self.query_generation
        if self.notes_after:
            self.root.after_cancel(self.notes_after)
            self.notes_after = None
        self.note_count.set("Searching PDFs…" if self.search_scope.get() != "Notes" and self.search.get().strip() else "Loading notes…")
        self.export_button.configure(state="disabled")
        self.query_future = self.query_executor.submit(search_library, self.store, self.pdf_worker,
                                                       self.search_scope.get(), **options, cancelled=cancelled.is_set)
        self.query_future.add_done_callback(lambda future: self.query_results.put((generation, current, future)))

    def finish_query(self, generation, current, future):
        if self.closing or generation != self.query_generation:
            return
        try:
            entries = future.result()
        except SearchSyntaxError as exc:
            entries = []
            self.search_error.set(f"Search: {exc}")
            self.search_error_label.pack(fill="x", before=self.reader_pane, pady=(0, 8))
        except InterruptedError:
            return
        except Exception as exc:
            self.notify(f"Could not load notes: {exc}", "notes")
            self.note_count.set("Could not load notes")
            self.query_signature = None
            return
        else:
            self.search_error.set("")
            self.search_error_label.pack_forget()
        warnings = getattr(entries, "warnings", [])
        self.search_warning.set("\n".join(warnings))
        if warnings:
            self.search_warning_label.configure(text=f"{len(warnings)} PDF search issue(s). Hover for details.")
            self.search_warning_label.pack(fill="x", before=self.reader_pane, pady=(0, 8))
        else:
            self.search_warning_label.pack_forget()
        self.notes.tooltip.reset()
        current = self.selected_entry() or current
        unchanged_order = [(e["document_id"], e["key"]) for e in self.entries] == [(e["document_id"], e["key"]) for e in entries]
        if not unchanged_order:
            self.notes.delete(*self.notes.get_children())
        self.entries = entries
        selected = [None]
        def insert_rows(start=0):
            self.notes_after = None
            if self.closing or generation != self.query_generation:
                return
            # Yield between batches so mouse, typing and resize events stay live.
            end = min(start + 100, len(entries))
            for i in range(start, end):
                e = entries[i]
                text = e.get("comment") or e.get("quote") or e.get("ocr") or "Drawing with page context"
                if e.get("kind") == "pdf":
                    text = "PDF: " + text
                if self.all_projects.get():
                    text = Path(e["path"]).stem + ": " + text
                values = tuple(str(v) for v in (e["page"], e["kind"], text.replace("\n", " ")))
                if not self.notes.exists(str(i)):
                    self.notes.insert("", "end", iid=str(i), values=values)
                elif self.notes.item(str(i), "values") != values:
                    self.notes.item(str(i), values=values)
                if current and (e["document_id"], e["key"]) == (current["document_id"], current["key"]):
                    selected[0] = str(i)
            if end < len(entries):
                self.notes_after = self.root.after(1, lambda: insert_rows(end))
                return
            if entries:
                # Keep a selection the reader made while rows were loading.
                selection = self.notes.selection()
                target = selection[0] if selection else selected[0] or "0"
                self.notes.selection_set(target)
                self.notes.see(target)
            pdf_count = sum(e.get("kind") == "pdf" for e in entries)
            count = f"{len(entries)} results" if self.search_scope.get() != "Notes" else f"{len(entries)} notes"
            self.note_count.set("Check search" if self.search_error.get() else count)
            self.export_button.configure(state="normal" if len(entries) > pdf_count else "disabled")
            self.preview()
        insert_rows()

    def preview(self, event=None):
        e = self.selected_entry()
        self.reader_paper_path_access.refresh()
        identity = (self.query_generation, e["document_id"], e["key"], self.show_details.get()) if e else None
        if e and identity == self.preview_identity:
            return
        self.preview_cancel.set()
        if self.preview_future:
            self.preview_future.cancel()
        self.preview_cancel = cancelled = threading.Event()
        self.preview_identity = identity
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.image = None
        if e:
            title = paper_title(e["path"], e.get("metadata", {}))
            lines = [title, page_description(e)]
            if e.get("kind") == "pdf":
                lines.extend(["PDF text match", e.get("context", "")])
            elif e.get("quote"):
                lines.append(e["quote"])
            for key, label in [("comment", "Note"), ("ocr", "Transcription to check")]:
                if e.get(key):
                    lines.append(f"{label}: {e[key]}")
            if self.show_details.get():
                lines.append(f"{Path(e['path']).name} | {e['kind']} {e.get('color', '')}")
                if e.get("context"):
                    lines.append("Nearby text: " + e["context"])
                lines.extend(e.get("metadata", {}).get("warnings", []))
            self.preview_text.insert("1.0", "\n\n".join(lines))
            if e["kind"] == "drawing":
                # Fetch/decode only the selected drawing on the query worker.
                # A late preview is ignored if the reader has selected another.
                future = self.preview_future = self.query_executor.submit(self.load_preview_image, dict(e), cancelled.is_set)
                future.add_done_callback(lambda result: self.image_results.put((identity, result)))
        elif self.search_error.get():
            self.preview_text.insert("1.0", "Complete or correct your search to see matching notes.")
        elif self.papers.selection() and self.papers.selection()[0] in self.failed_papers:
            path, error = self.failed_papers[self.papers.selection()[0]]
            self.preview_text.insert("1.0", f"{Path(path).name}\n\nCould not read this PDF:\n{error}\n\nUse Sync PDFs to retry.")
        elif self.search_scope.get() == "PDFs" and not self.search.get().strip():
            self.preview_text.insert("1.0", "Enter a search to find printed text in your PDFs, including papers without notes.")
        else:
            self.preview_text.insert("1.0", "No notes to show.\n\nTry another paper or search, or add a PDF folder in Library.")
        self.source_button.configure(state="normal" if e else "disabled")
        self.enlarge_button.configure(state="normal" if self.image else "disabled")
        self.copy_image_button.configure(state="normal" if self.image else "disabled")
        self.full_page_button.configure(state="normal" if e and e["kind"] in {"drawing", "pdf"} else "disabled")
        self.preview_text.configure(state="disabled")
        self.layout_note_preview()
        self.image_size = None
        self.draw_image()

    def load_preview_image(self, entry, cancelled):
        if cancelled():
            return None
        image = entry.get("image") or self.store.entry_image(
            entry["document_id"], entry["key"], expected_digest=entry.get("source_digest"),
            expected_note_revision=entry.get("source_note_revision"))
        if not image or cancelled():
            return None
        with Image.open(BytesIO(base64.b64decode(image))) as img:
            return img.copy()

    def schedule_image_resize(self, event=None):
        if self.image_after:
            self.root.after_cancel(self.image_after)
        self.image_after = self.root.after(80, self.draw_image)

    def draw_image(self):
        self.image_after = None
        size = (max(20, self.canvas.winfo_width()-16), max(20, self.canvas.winfo_height()-16))
        if self.image and self.image_size == size:
            return
        self.image_size = size
        self.canvas.delete("all")
        if self.image:
            copy = self.image.copy()
            copy.thumbnail(size)
            self.tk_image = ImageTk.PhotoImage(copy, master=self.canvas)
            self.canvas.create_image(self.canvas.winfo_width()/2, 8, image=self.tk_image, anchor="n")

    def layout_note_preview(self):
        entry = self.selected_entry()
        drawing = bool(entry and entry.get("kind") == "drawing")
        present = str(self.canvas) in {str(pane) for pane in self.context_pane.panes()}
        if drawing and not present:
            self.context_pane.add(self.canvas, weight=2)
        elif not drawing and present:
            self.context_pane.forget(self.canvas)
        if drawing and self.context_pane.winfo_height() > 40:
            length = len(self.preview_text.get("1.0", "end-1c"))
            fraction = min(.48, max(.18, .16 + length / 5000))
            position = round(self.context_pane.winfo_height()*fraction)
            if abs(self.context_pane.sashpos(0)-position) > 2:
                self.context_pane.sashpos(0, position)

    def copy_note_image(self, event=None):
        if self.image is not None:
            try:
                copy_image(self.image, self.canvas.winfo_id())
            except OSError as exc:
                self.notify(f"Could not copy image: {exc}", "notes")
            else:
                self.notify("Note image copied at its original resolution.", "notes")
        return "break"

    def show_image_menu(self, event):
        self.canvas.focus_set()
        self.image_menu.entryconfigure(0, state="normal" if self.image is not None else "disabled")
        x, y = ((self.canvas.winfo_rootx() + 8, self.canvas.winfo_rooty() + 8) if getattr(event, "keysym", "") == "F10"
                else (event.x_root, event.y_root))
        try:
            self.image_menu.tk_popup(x, y)
        finally:
            self.image_menu.grab_release()
        return "break"

    def enlarge(self):
        if not self.image:
            return
        window = tk.Toplevel(self.root)
        window.title("Original annotation and page context")
        window.geometry("1000x750")
        window.configure(background=BACKGROUND)
        bind_dialog_close(window, window.destroy)
        header = ttk.Frame(window, padding=12)
        header.pack(fill="x")
        help_text = tk.StringVar(value="100% · Scroll to move vertically · Drag to pan · Ctrl + scroll to zoom")
        instructions = ttk.Label(window, textvariable=help_text, style="Muted.TLabel", padding=12)
        instructions.pack(fill="x")
        instructions.bind("<Configure>", lambda event: instructions.configure(wraplength=max(100, event.width - 24)))
        viewport = ImageViewport(window, window, help_text.set, background=PANEL)
        viewport.pack(fill="both", expand=True)
        canvas = viewport.canvas
        window.image_canvas = canvas
        self.image_fit_controls(window, header, canvas)
        canvas.set_image(self.image)
        annotate_buttons(window)
        return window

    def image_fit_controls(self, window, header, canvas, loading=False):
        window.copy_image_button = Button(header, text="Copy image", command=canvas.copy_original,
                                          state="disabled" if loading else "normal")
        window.copy_image_button.pack(side="right", padx=(0, 8))
        Tooltip(window.copy_image_button, "Copy this complete image at its original resolution. Ctrl+C works while the image has focus.")
        for text, command, attribute, axis in (
                ("Fit height", canvas.fit_height, "fit_height_button", "height"),
                ("Fit width", canvas.fit_width, "fit_width_button", "width")):
            button = Button(header, text=text, command=command, state="disabled" if loading else "normal")
            button.pack(side="right", padx=(0, 8))
            Tooltip(button, f"Fit the image to the window {axis}. Keep fitting to that {axis} when the window is resized; Ctrl + wheel returns to manual zoom.")
            setattr(window, attribute, button)

    def full_page_context(self):
        entry = self.selected_entry()
        if not entry or entry["kind"] not in {"drawing", "pdf"}:
            return
        # One context window bounds pending renders; waiting for PDF work must
        # never occupy the library/search worker.
        if self.context_window and self.context_window.winfo_exists():
            if self.context_window.context_identity == (entry["path"], entry["page"]):
                self.context_window.lift()
                return
            self.context_window.destroy()
        if self.context_future and not self.context_future.done():
            self.notify("The previous page preview is finishing. Try again shortly.", "notes")
            return
        dismiss_tooltips()
        self.context_window = window = tk.Toplevel(self.root)
        window.context_identity = (entry["path"], entry["page"])
        window.title("Full page context — " + page_description(entry))
        window.configure(background=BACKGROUND)
        bind_dialog_close(window, window.destroy)
        window.geometry(f"{min(1050, self.root.winfo_screenwidth()-80)}x{min(820, self.root.winfo_screenheight()-100)}")
        header = ttk.Frame(window, padding=12)
        header.pack(fill="x")
        page_label = ttk.Label(header, text=page_description(entry), style="Section.TLabel")
        source = Button(header, text="Open PDF", command=lambda: self.open_entry_pdf(entry))
        source.pack(side="right")
        Tooltip(source, f"{self.entry_paper_path(entry)}\n\nOpen this complete page with combined PC and tablet notes in your chosen PDF viewer.")
        info = ttk.Label(window, text="Loading full page…", style="Muted.TLabel", padding=12)
        info.pack(fill="x")
        info.bind("<Configure>", lambda event: info.configure(wraplength=max(100, event.width - 24)))
        viewport = ImageViewport(window, window, lambda text: info.configure(text="Complete page including retained margins. " + text), background=PANEL)
        context_cancel = threading.Event()
        viewport.pack(fill="both", expand=True)
        canvas = viewport.canvas
        window.context_canvas = canvas
        self.image_fit_controls(window, header, canvas, loading=True)
        page_label.pack(side="left", fill="x", expand=True)
        page_label.bind("<Configure>", lambda event: page_label.configure(wraplength=max(100, event.width)))
        def loaded(future):
            try:
                image = future.result()
            except Exception as exc:
                info.configure(text=f"Could not render this page: {exc}. Review the paper's source and page match before combining its notes.")
                return
            canvas.set_image(image, fit_width=True)
            window.fit_width_button.configure(state="normal")
            window.fit_height_button.configure(state="normal")
            window.copy_image_button.configure(state="normal")
        def close_context(event):
            if event.widget == window and self.context_window == window:
                context_cancel.set()
                self.context_window = None
                if self.context_future:
                    self.context_future.cancel()
        window.bind("<Destroy>", close_context, add="+")
        try:
            reference, page = self.entry_pdf_target(entry)
        except ValueError as exc:
            info.configure(text=str(exc))
            return
        self.context_future = future = self.context_executor.submit(self.load_full_page, reference, page, context_cancel.is_set)
        future.add_done_callback(lambda result: self.dialog_results.put((window, loaded, result)))

    def load_full_page(self, path, page, cancelled=None):
        path = self.materialize_pdf(path)
        if cancelled and cancelled():
            raise InterruptedError("Page preview closed")
        data = self.pdf_worker.full_page_cancellable(str(path), page, cancelled) if cancelled is not None and hasattr(type(self.pdf_worker), "full_page_cancellable") else self.pdf_worker.full_page(str(path), page)
        with Image.open(BytesIO(data)) as image:
            return image.copy()

    def materialize_pdf(self, reference):
        worker = getattr(self, "pdf_worker", None)
        if worker is not None and callable(getattr(worker, "materialize", None)):
            return Path(worker.materialize(self.store.path, reference))
        return materialize_combined(self.store, reference, cancelled=lambda: self.closing)

    def write_annotated_pdf(self, reference, target, expected_digest, require_absent):
        worker = getattr(self, "pdf_worker", None)
        if worker is not None and callable(getattr(worker, "export_combined", None)):
            return Path(worker.export_combined(self.store.path, reference, target,
                                               expected_digest=expected_digest, require_absent=require_absent))
        return export_combined(self.store, reference, target, expected_digest=expected_digest,
                               require_absent=require_absent, cancelled=lambda: self.closing)

    def open_source(self):
        e = self.selected_entry()
        if e:
            self.open_entry_pdf(e)

    def open_entry_pdf(self, entry):
        try:
            reference, page = self.entry_pdf_target(entry)
        except ValueError as exc:
            messagebox.showerror("PDF needs review", str(exc), parent=self.root)
            return
        self.open_pdf(reference, page)

    def open_pdf(self, path, page=1):
        section = "cloud" if self.tabs.select() == str(self.remarkable_tab) else "library" if self.tabs.select() == str(self.library_tab) else "notes"
        if self.pdf_open_future and not self.pdf_open_future.done():
            self.notify("Preparing the previous PDF. It will open when ready.", section)
            return
        self.notify("Preparing PDF with saved notes…", section)
        def loaded(future):
            try:
                resolved = future.result()
            except Exception as exc:
                self.notify(f"PDF needs attention: {exc}", section)
                messagebox.showerror("Unable to open PDF", str(exc), parent=self.root)
                return
            self.launch_pdf(resolved, page, section)
        self.pdf_open_future = future = self.context_executor.submit(
            self.materialize_pdf, path)
        future.add_done_callback(lambda result: self.dialog_results.put((self.root, loaded, result)))

    def launch_pdf(self, path, page=1, section="notes"):
        try:
            status, page_supported = open_pdf_page(path, page, self.viewer_preference)
            self.notify(status, section)
            if not page_supported:
                messagebox.showinfo("PDF page navigation", status, parent=self.root)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Unable to open PDF", str(exc), parent=self.root)

    def open_paper(self):
        selection = self.papers.selection()
        if selection:
            if selection[0] in self.failed_papers:
                self.open_pdf(self.failed_papers[selection[0]][0])
                return
            for d in self.view.documents():
                if d["id"] == selection[0]:
                    self.open_pdf(d.get("logical_paper_id") or d["path"])

    def export_paper_pdf(self):
        selection = self.papers.selection()
        document = next((row for row in self.view.documents() if selection and row["id"] == selection[0]), None)
        if document:
            self.export_annotated_pdf(document.get("logical_paper_id") or document["path"], document["path"], "library")
        else:
            self.notify("Select a paper to export its annotated PDF.", "library")

    def export_note_pdf(self):
        entry = self.selected_entry()
        if not entry:
            self.notify("Select a note to export its paper as an annotated PDF.", "notes")
            return
        try:
            reference, _ = self.entry_pdf_target(entry)
        except ValueError as exc:
            messagebox.showerror("PDF needs review", str(exc), parent=self.root)
            return
        self.export_annotated_pdf(reference, self.entry_paper_path(entry), "notes")

    def export_annotated_pdf(self, reference, source_path, section):
        if self.pdf_export_busy:
            self.notify("The previous annotated PDF export is finishing.", section)
            return
        target = filedialog.asksaveasfilename(parent=self.root, title="Export annotated PDF",
            initialfile=Path(source_path).stem + " — annotated.pdf", defaultextension=".pdf",
            filetypes=[("PDF document", "*.pdf")], confirmoverwrite=False)
        if not target:
            return
        self.pdf_export_busy = True
        self.notify("Preparing annotated PDF export…", section)
        # Inspect on the workflow worker, then bind overwrite consent to these
        # exact bytes. Publishing also rejects a file that appears meanwhile.
        def inspect_target():
            destination = Path(target)
            return digest_file(destination) if destination.exists() else None
        def failure(exc):
            self.pdf_export_busy = False
            self.notify(f"Annotated PDF export needs attention: {exc}", section)
            messagebox.showerror("Unable to export annotated PDF", str(exc), parent=self.root)
        def prepared(expected_digest):
            if expected_digest is not None and not messagebox.askokcancel("Replace exported PDF?",
                    "Replace this existing PDF with the combined annotated view?\n\n" + target, parent=self.root):
                self.notify("Annotated PDF export cancelled.", section)
                self.pdf_export_busy = False
                return
            def completed(destination):
                self.pdf_export_busy = False
                self.notify(f"Annotated PDF saved: {destination}", section)
            self.pdf_export_future = background(self,
                lambda: self.write_annotated_pdf(reference, target, expected_digest, expected_digest is None),
                completed, failure)
        self.pdf_export_future = background(self, inspect_target, prepared, failure)

    def send_paper(self):
        selection = self.papers.selection()
        document = next((row for row in self.view.documents() if selection and row["id"] == selection[0]), None)
        if document:
            self.send_pdf_path(document["path"])

    def review_extra_pdfs(self):
        from .storage_ui import open_cleanup
        return open_cleanup(self)

    def send_pdf_path(self, path, parent=None):
        config = self.cloud_config()
        if not config["integration_enabled"] or not config["send_new_pdfs"]:
            messagebox.showinfo("PDF transfers off", "Enable reMarkable cloud services and PDF sending in Settings → Connections first.", parent=parent or self.root)
            return
        if not config["pc_root"] or not Path(path).is_relative_to(Path(config["pc_root"])) or Path(path).suffix.lower() != ".pdf":
            messagebox.showinfo("Outside linked folder", "Choose an original PDF beneath the linked PC root, such as Sorted.", parent=parent or self.root)
            return
        if messagebox.askokcancel("Send selected PDF", f"Send this PDF to its linked tablet folder?\n\n{path}\n\nReview duplicates first. Existing confirmed tablet links are reused; uncertain matches need review.", parent=parent or self.root):
            self.service.command("remarkable_upload", path)
            self.transfers()

    def history(self):
        e = self.selected_entry()
        if not e:
            return
        window = tk.Toplevel(self.root)
        window.title("Paper annotation history")
        window.configure(background=BACKGROUND)
        window.geometry("800x550")
        bind_dialog_close(window, window.destroy)
        actions = ttk.Frame(window, padding=12)
        actions.pack(side="bottom", fill="x")
        Button(actions, text="Close", command=window.destroy).pack(side="right")
        path_row = ttk.Frame(window, padding=12)
        path_row.pack(fill="x")
        ttk.Label(path_row, text="Source PDF").pack(side="left", padx=(0, 8))
        path_entry = ttk.Entry(path_row)
        path_entry.insert(0, e["path"])
        path_entry.configure(state="readonly")
        path_entry.pack(side="left", fill="x", expand=True)
        path_access = PathField(path_entry, "This history belongs to the selected PDF copy.")
        path_access.add_copy_button(path_row).pack(side="right", padx=(6, 0))
        history_text = ReadOnlyText(window, "Loading saved history…", height=14)
        history_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        window.history_text = history_text
        def loaded(future):
            lines = []
            try:
                rows = future.result()
                for h in rows:
                    payload = json.loads(h["payload"])
                    summary = payload.get("comment") or payload.get("quote") or payload.get("ocr") or "Drawing with saved context image"
                    lines.append(f"{local_time(h['at'], '%Y-%m-%d %H:%M %Z')} | {h['action']} | {page_description(payload)}\n{summary}")
            except Exception as exc:
                lines.append(f"History unavailable: {exc}")
            history_text.set("\n\n".join(lines) if lines else "No saved annotation changes for this PDF copy.", paths={"Source PDF": e["path"]})
        future = self.query_executor.submit(self.store.history, e["document_id"], include_images=False)
        future.add_done_callback(lambda result: self.dialog_results.put((window, loaded, result)))
        annotate_buttons(window)
        fit_dialog(window, self.root)
        return window

    def help(self):
        existing = getattr(self, "help_window", None)
        if existing and existing.winfo_exists():
            existing.lift()
            return existing
        window = self.help_window = tk.Toplevel(self.root)
        window.title(f"{APP_NAME} help")
        window.configure(background=BACKGROUND)
        window.geometry("800x600")
        bind_dialog_close(window, window.destroy)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        actions = ttk.Frame(frame)
        actions.pack(side="bottom", fill="x", pady=(12, 0))
        Button(actions, text="Close", command=window.destroy).pack(side="right")
        library_row = ttk.Frame(frame)
        library_row.pack(fill="x", pady=(0, 12))
        ttk.Label(library_row, text="Active library").pack(side="left", padx=(0, 8))
        library_path = ttk.Entry(library_row)
        library_path.insert(0, str(self.data_dir.resolve()))
        library_path.configure(state="readonly")
        library_path.pack(side="left", fill="x", expand=True)
        path_access = PathField(library_path, "This app stores its notes, settings and activity log in this data folder.")
        path_access.add_copy_button(library_row).pack(side="right", padx=(6, 0))
        content = ("Inbox: choose incoming and library folders in Settings → Sorting. Review names and destinations before filing PDFs, Word documents or PowerPoint presentations. Only PDFs enter note consolidation.\n\n"
            "Review library: open it from Inbox or Library to compare duplicates and folder differences. Click headings to sort, or use its filters and search. Keep separate remembers a decision; Review again clears it. Linking copies retains files, independent notes and history. Undo last link reverses the latest link made by this version. Saved tablet information can be incomplete.\n\n"
            "Library: add folders, sync PDFs, and adjust Folder settings. Show sync details opens the processing log and changes to Hide sync details while it is open. View sync details in the bottom bar opens it when a check needs attention.\n\n"
            "reMarkable: enable cloud services in Settings → Connections to reveal the tab, then pair and link your PC and tablet roots. "
            "New PDF sending and new folder creation each have separate switches. Existing paper transfers are explicit. Cloud activity stays within the linked roots; mismatches need review.\n\n"
            "Notes: choose a folder and paper, search annotations, read their page context, and export. Open folder in Library or Notes opens the selected PC folder. More contains editable copies, Export annotated PDF and history. Drag a column divider to see more text, or double-click it to fit the column to its rows.\n\n"
            "Open PDF combines PC and tablet notes when the paper version and page positions are verified. Uncertain matches need review first. Export annotated PDF saves this combined view as a separate PDF. Your original sources stay intact.\n\n"
            "Highlights keep their text and PDF link. Only drawings and handwriting show context previews, also in Word notebooks. After a tablet paper is verified and refreshed, Word PDF links open its saved original. Older tablet copies keep their existing links until that refresh succeeds. Use Notable to open or export the combined annotated view.\n\n"
            "PDF page is the physical file position used by Open PDF. PDF labels are separate; journal pages appear only when verified.\n\n"
            "Settings: configure sorting, your own optional Gemini key, PDF viewing and processing defaults. Gemini starts off; Local only makes no naming requests. Key removal stays pending until Save; Undo removal or Cancel keeps the saved key. Library & diagnostics identifies saved libraries.\n\n"
            "Drawings retain surrounding text and figures. Folder settings adjusts grouping and context margins; Whole page keeps drawings together. Highlights and typed comments stay separate.\n\n"
            "Sync checks PDFs and updates extracted screenshots. Right-click a watched folder in Library to rebuild its notebook from saved notes "
            "using current formatting after confirmation. Save editable copy makes a separate notebook for your writing. "
            "External edits to generated notebooks are preserved in Notebook backups before regeneration.\n\n"
            "Updates are watched while the app is open, checked every five minutes, and caught up at startup. "
            "Closing the app stops watching.\n\n"
            "Hover over a file or folder location to see its complete path and an explanation. The small Copy full path button copies the entire location. For a selected table row with several locations, choose the location in its details panel first.\n\n"
            "Library → Actions → Library storage & backups creates verified backups, restores an independent library and compacts repeated drawing images without removing note history. Recovery archive review removes only proven duplicate raw archives after backup.\n\n"
            "Notes → Actions contains tags and research collections, saved searches and an accessible browser reading view. Collection or tag filters apply to both note and printed PDF results. Saved searches apply to the current folder and paper selection.\n\n"
            "Keyboard: Ctrl+F searches notes; F5 syncs PDFs; Ctrl+, opens Settings. Alt+1/2/3 selects Inbox/Library/Notes. Ctrl+Shift+S opens saved searches, Ctrl+Shift+T edits tags, and Ctrl+Shift+A opens the accessible reading view. Tab and Shift+Tab move between controls; Enter opens the selected note's PDF.\n\n"
            f"Version {__version__}")
        window.help_text = ReadOnlyText(frame, content, height=18)
        window.help_text.pack(fill="both", expand=True)
        annotate_buttons(window)
        fit_dialog(window, self.root)
        return window

    def poll(self):
        if self.closing:
            return
        started = time.monotonic()
        delay = max(0, started - self.last_poll - .1)
        self.last_poll = started
        if delay > .25 and delay > self.largest_ui_delay:
            self.largest_ui_delay = delay
            logging.warning("Interface heartbeat delayed %.3fs during %s", delay,
                            (self.service.activity_state or {}).get("phase", "idle"))
        lines = []
        for _ in range(100):
            try:
                text, changed = self.service.messages.get_nowait()
            except queue.Empty:
                break
            if text:
                self.status.set(text)
                lines.append(f"{datetime.now():%H:%M:%S}  {text}\n")
            self.refresh_needed |= changed
        if lines:
            self.activity.configure(state="normal")
            self.activity.insert("end", "".join(lines))
            if int(self.activity.index("end-1c").split(".")[0]) > 2500:
                self.activity.delete("1.0", "500.0")
            self.activity.see("end")
            self.activity.configure(state="disabled")
        for _ in range(15):
            try:
                success, error, future = self.workflow_results.get_nowait()
            except queue.Empty:
                break
            self.workflow_futures.discard(future)
            if self.closing:
                continue
            try:
                result = future.result()
            except Exception as exc:
                if error:
                    error(exc)
                else:
                    self.status.set(f"Literature action needs attention: {exc}")
            else:
                success(result)
        for _ in range(15):
            try:
                event, payload = self.workflow_events.get_nowait()
            except queue.Empty:
                break
            if event == "inbox_filed" and payload.get("is_pdf"):
                self.service.command("filed_pdf", payload)
            elif event == "inbox_filed":
                background(self, lambda job_id=payload["job_id"]: self.inbox.acknowledge_filing(job_id), lambda _: None)
            if event in {"inbox_changed", "inbox_filed", "inbox_prepared", "inbox_skipped", "inbox_config_changed"} and not self.closing:
                self.inbox_view.load_rows()
            if event == "inbox_error" and not self.closing:
                self.inbox_view.feedback.set(str(payload.get("error", "Inbox action needs attention.")))
            if event == "inbox_recovery_error" and not self.closing:
                self.inbox_view.feedback.set("An interrupted filing needs review. Open Filing recovery to inspect the retained copies.")
        for _ in range(10):
            try:
                window, callback, future = self.dialog_results.get_nowait()
            except queue.Empty:
                break
            if not self.closing and window.winfo_exists():
                callback(future)
        for _ in range(5):
            try:
                future = self.library_results.get_nowait()
            except queue.Empty:
                break
            self.finish_view(future)
        for _ in range(5):
            try:
                key, future = self.cloud_path_results.get_nowait()
            except queue.Empty:
                break
            self.cloud_path_future = None
            if self.closing:
                continue
            config = self.cloud_config()
            source_id, root = self.cloud_routing_values()
            desired = (repr(self.view.preference("remarkable_folders", [])), source_id, root, repr(config["mappings"]))
            if key == desired:
                try:
                    self.cloud_paths, self.cloud_root_available = future.result()
                    self.cloud_paths_key = key
                except Exception as exc:
                    self.notify(f"Could not check PC folder paths: {exc}", "cloud")
            else:
                self.cloud_path_key = None
            self.refresh_cloud_folders()
        now = time.monotonic()
        # Imports can emit hundreds of changes. Refresh at most once per two
        # seconds, keeping the current reading selection instead of rebuilding
        # the entire library after each downloaded/extracted PDF.
        if self.refresh_needed and now >= self.next_refresh:
            self.refresh_needed = False
            self.next_refresh = now + 2
            self.refresh()
        for _ in range(10):
            try:
                generation, current, future = self.query_results.get_nowait()
            except queue.Empty:
                break
            self.finish_query(generation, current, future)
        for _ in range(10):
            try:
                identity, future = self.image_results.get_nowait()
            except queue.Empty:
                break
            if identity == self.preview_identity and not self.closing:
                try:
                    self.image = future.result()
                except Exception as exc:
                    self.notify(f"Could not load drawing preview: {exc}. Open the source PDF to see it.", "notes")
                    continue
                self.image_size = None
                self.enlarge_button.configure(state="normal" if self.image else "disabled")
                self.copy_image_button.configure(state="normal" if self.image else "disabled")
                self.draw_image()
        self.show_work_progress()
        if not self.closing:
            self.root.after(100, self.poll)

    def show_work_progress(self):
        state = self.service.activity_state
        phase = state["phase"] if state else "Loading library" if not self.library_loaded else ""
        if phase:
            count = f" {state['current']}/{state['total']}" if state and state.get("total") else f" {state['current']}" if state and state.get("current") else ""
            self.work_phase.set(phase + count)
            if not self.work_visible:
                self.work_label.pack(side="right", padx=8)
                self.work_progress.pack(side="right", padx=8)
                self.work_progress.start(80)
                self.work_visible = True
        elif self.work_visible:
            self.work_progress.stop()
            self.work_progress.pack_forget()
            self.work_label.pack_forget()
            self.work_visible = False

    def close(self):
        self.closing = True
        self.status.set("Finishing the current PDF safely before closing…")
        self.service.stop()
        self.query_cancel.set()
        self.preview_cancel.set()
        self.query_executor.shutdown(wait=False, cancel_futures=True)
        self.context_executor.shutdown(wait=False, cancel_futures=True)
        self.workflow_executor.shutdown(wait=False, cancel_futures=True)
        self.inbox.stop(wait=False)
        if self.reconciliation_window:
            self.reconciliation_window.cancelled.set()
        if not self.service.thread:
            self.pdf_worker.shutdown(wait=False)
        self.wait_close()

    def wait_close(self):
        if (self.service.thread and self.service.thread.is_alive()) or any(not future.done() for future in self.workflow_futures):
            self.root.after(100, self.wait_close)
        else:
            self.root.destroy()
