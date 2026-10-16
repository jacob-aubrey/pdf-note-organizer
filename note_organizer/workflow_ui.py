"""Review-first literature workflows, using background work outside Tk."""
from pathlib import Path
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .icons import Button, icon, menu_action
from .theme import BACKGROUND, BLUE, TEXT
from .widgets import Tooltip, PathField, ReadOnlyText, ScrollFrame, WrapToolbar, EntryPlaceholder, annotate_buttons, bind_dialog_close, fit_dialog, bind_item_open


def background(app, function, success, error=None, *, task="Finishing a library action…"):
    """Callbacks are drained by App.poll on the Tk thread."""
    future = app.workflow_executor.submit(function)
    future.shutdown_label = task
    app.workflow_futures.add(future)
    future.add_done_callback(lambda result: app.workflow_results.put((success, error, result)))
    return future


def explanation(details):
    parts = []
    for key, label in (("title", "Title"), ("authors", "Authors"), ("author", "Author"),
                       ("journal", "Journal"), ("year", "Year"), ("doi", "DOI"),
                       ("document_type", "Type"), ("naming_source", "Identification"),
                       ("metadata_source", "Source"), ("source", "Identification"),
                       ("creators", "Creators"), ("document_type_label", "Document"),
                       ("evidence_label", "Evidence"), ("evidence_detail", "Details"),
                       ("ai_failure_message", "Lookup issue")):
        value = details.get(key)
        if value:
            if isinstance(value, (list, tuple)):
                value = ", ".join(map(str, value))
            parts.append(f"{label}: {value}")
    warnings = []
    for field in ("warnings", "review_reasons"):
        value = details.get(field, [])
        warnings.extend([value] if isinstance(value, str) else value)
    parts.extend(f"Review: {warning}" for warning in warnings)
    return "\n".join(parts) or "Review the suggested filename and choose its destination."


class InboxView:
    def __init__(self, app, parent):
        self.app, self.parent = app, parent
        self.rows = {}
        self.busy = False
        self.review_path = None
        self.review_signature = None
        self.proposal = ""
        self.retry_available = False
        self.generation = 0
        pane = ttk.Panedwindow(parent, orient="horizontal")
        pane.pack(fill="both", expand=True)
        listing = ttk.Frame(pane, width=440)
        pane.add(listing, weight=1)
        parent = listing
        ttk.Label(parent, text="Incoming documents", style="Section.TLabel").pack(anchor="w", pady=(0, 10))
        toolbar = WrapToolbar(parent)
        toolbar.pack(fill="x", pady=(0, 12))
        more = app.more_button(toolbar, [("Filing recovery…", app.filing_recovery),
                                          ("Review library…", app.review_library)])
        self.setup_button = Button(toolbar, text="Set up Inbox…", command=app.setup_inbox, style="Primary.TButton")
        Tooltip(self.setup_button, "Choose the incoming-document and library folders in Settings → Sorting.")
        toolbar.add(self.setup_button, visible=False)
        self.inbox_toolbar = toolbar
        for label, action in (("Add documents…", self.add_documents),
                              ("Refresh inbox", self.refresh),
                              ("Open inbox", lambda: self.open_folder("watch_folder"))):
            button = Button(toolbar, text=label, command=action)
            toolbar.add(button)
            Tooltip(button, {"Add documents…": "Copy PDF, Word (.docx), or PowerPoint (.ppt/.pptx) documents into your inbox for review. The source files stay where they are. Dropping documents onto the list also copies them.",
                             "Refresh inbox": "Check for finished downloads and changes to documents in the inbox. A file must stop changing before it can be reviewed. This check does not name, file, or upload documents.",
                             "Open inbox": "Open the configured incoming-document folder.",
                             "Filing recovery…": "Inspect copies retained after interrupted filing. Open both locations before deciding how to organize the copies.",
                             "Review library…": "Find duplicate papers and compare PC and saved tablet information without changing files."}[label])
        toolbar.add(more)
        self.actions_button = more
        Tooltip(more, "Inbox actions, including setup, filing recovery and library review.")
        self.refresh_setup_action()
        self.summary = tk.StringVar(value="Choose an inbox and library in Settings → Sorting, or import your sorter settings.")
        summary = ttk.Label(parent, textvariable=self.summary, style="Muted.TLabel", wraplength=900)
        summary.pack(fill="x", pady=(0, 12))
        summary.bind("<Configure>", lambda event: summary.configure(wraplength=max(120, event.width)))
        Tooltip(summary, lambda: self.summary.get())
        self.parent_listing = parent
        self.inbox_listing = listing
        self.inbox_pane = pane
        self.build_inbox_detail_layout()

    def is_configured(self):
        config = self.app.inbox.config()
        return bool(config.get("watch_folder") and config.get("library_root"))

    def refresh_setup_action(self):
        if hasattr(self, "actions_button"):
            configured = self.is_configured()
            try:
                self.actions_button.action_menu.index("Set up Inbox…")
                has_menu_setup = True
            except tk.TclError:
                has_menu_setup = False
            if configured and not has_menu_setup:
                menu_action(self.actions_button.action_menu, "Set up Inbox…", self.app.setup_inbox)
            elif not configured and has_menu_setup:
                self.actions_button.action_menu.delete("Set up Inbox…")
            self.inbox_toolbar.set_visible(self.setup_button, not configured)

    def build_inbox_detail_layout(self):
        app = self.app
        parent = self.parent_listing
        listing = self.inbox_listing
        pane = self.inbox_pane
        locations = ttk.Frame(parent)
        locations.pack(fill="x", pady=(0, 10))
        self.location_variables = {}
        for index, (key, label) in enumerate((("watch_folder", "Inbox"), ("library_root", "Library"))):
            ttk.Label(locations, text=label).grid(row=index, column=0, sticky="w", padx=(0, 8), pady=3)
            variable = self.location_variables[key] = tk.StringVar()
            entry = ttk.Entry(locations, textvariable=variable, state="readonly", width=1)
            entry.grid(row=index, column=1, sticky="ew", pady=3)
            locations.columnconfigure(1, weight=1)
            access = PathField(entry, "Incoming documents wait here for review." if key == "watch_folder" else "Reviewed documents are filed inside this library root.")
            access.add_copy_button(locations).grid(row=index, column=2, padx=(6, 0), pady=3)
        controls = WrapToolbar(listing)
        controls.pack(fill="x", pady=(0, 8))
        self.review_button = Button(controls, text="Review selected", command=self.review, style="Primary.TButton")
        controls.add(self.review_button)
        Tooltip(self.review_button, lambda: "Wait for the current inbox operation to finish." if self.busy else
                "Select an incoming document first." if not self.tree.selection() else
                "Identify the selected finished document using your naming settings, then suggest an editable filename. Review the name and destination before filing; this action does not move or upload the document.")
        self.skip_button = Button(controls, text="Skip", command=self.skip)
        controls.add(self.skip_button)
        Tooltip(self.skip_button, lambda: "Wait for the current inbox operation to finish." if self.busy else
                "Select an incoming document first." if not self.tree.selection() else
                "Leave this document in the inbox and set it aside until its contents change. Review selected can bring it back at any time.")
        self.retry_button = Button(controls, text="Retry lookup", command=lambda: self.review(force=True))
        controls.add(self.retry_button)
        Tooltip(self.retry_button, lambda: "Wait for the current inbox operation to finish." if self.busy else
                "Review a document with a retryable identification failure first." if not self.review_path or not self.retry_available else
                "Try identification again using your current naming permissions. A filename you edited is kept; the new metadata appears below.")
        self.tree = app.tree(listing, [("name", "Document", 265), ("state", "Status", 150)], content_columns=(), empty_text="No incoming documents")
        self.tree.bind("<<TreeviewSelect>>", self.selected)
        bind_item_open(self.tree, self.open_document)
        self.tree.tooltip.value = lambda row, column: row if column == "name" else self.tree.set(row, column)
        self.tree.tooltip.extra = self.item_help
        self.editor_form = ScrollFrame(pane, width=490, height=1, padding=(16, 0, 16, 0), stretch=True)
        editor = self.editor_form.content
        pane.add(self.editor_form, weight=1)
        editor_heading = ttk.Label(editor, text="Review filename & destination", style="Section.TLabel")
        editor_heading.pack(fill="x", pady=(0, 12))
        editor_heading.bind("<Configure>", lambda event: editor_heading.configure(wraplength=max(100, event.width)))
        self.original = tk.StringVar(value="Select a document in the inbox.")
        self.original_name = tk.StringVar(value=self.original.get())
        original_row = ttk.Frame(editor)
        original_row.pack(fill="x", pady=(0, 12))
        ttk.Label(original_row, text="Original file").pack(side="left", padx=(0, 10))
        self.original_label = original_label = ttk.Label(original_row, textvariable=self.original_name, width=1)
        original_label.pack(side="left", fill="x", expand=True)
        original_access = PathField(original_label, "This is the original document in the inbox. Naming and filing keep its document type.",
            value=lambda: self.original.get() if self.original.get() != "Select a document in the inbox." else "")
        self.original_path_copy = original_access.add_copy_button(original_row)
        Tooltip(self.original_path_copy, lambda: "\n\n".join(part for part in (original_access.value(),
            "Copy the original document's full path. This does not copy the proposed filename below.") if part))
        fields = ttk.Frame(editor)
        fields.pack(fill="x", pady=(0, 12))
        fields.columnconfigure(1, weight=1)
        ttk.Label(fields, text="Filename").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 10))
        self.filename = tk.StringVar()
        self.name_entry = ttk.Entry(fields, textvariable=self.filename, width=1)
        self.name_entry.grid(row=0, column=1, columnspan=3, sticky="ew", pady=(0, 10))
        Tooltip(self.name_entry, lambda: (self.filename.get() + "\n\n" if self.filename.get() else "") +
            "Edit the filename only, without a folder path. The source .pdf, .docx, .ppt, or .pptx extension is kept and added if omitted. Existing destination files are never overwritten.")
        ttk.Label(fields, text="Destination folder").grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.destination = tk.StringVar()
        self.destination_entry = ttk.Entry(fields, textvariable=self.destination, width=1)
        self.destination_entry.grid(row=1, column=1, sticky="ew")
        destination_access = PathField(self.destination_entry, "Choose a destination inside your library root. You can type a new subfolder path; it is created only when you file the document. The destination must be outside the inbox and app cache areas.")
        self.destination_path_copy = destination_access.add_copy_button(fields)
        self.destination_path_copy.grid(row=1, column=2, padx=(8, 0))
        destination_browse = Button(fields, text="Browse…", command=self.choose_destination)
        destination_browse.grid(row=1, column=3, padx=(8, 0))
        Tooltip(destination_browse, "Choose the destination folder for the reviewed document.")
        self.file_button = Button(editor, text="File document", command=self.file_document, style="Primary.TButton")
        self.file_button.pack(anchor="w", pady=(0, 10))
        Tooltip(self.file_button, lambda: "Wait for the current inbox operation to finish." if self.busy else
                "Choose Review selected and check the proposed filename and destination first." if not self.review_path else
                "Confirm the name and destination, then move this document from the inbox into your library. Existing files are never overwritten. Only PDFs enter note analysis or an enabled tablet upload queue; Word and PowerPoint stay local.")
        self.feedback = tk.StringVar()
        feedback = ttk.Label(editor, textvariable=self.feedback, wraplength=440, style="Muted.TLabel")
        feedback.pack(fill="x", pady=(0, 8))
        feedback.bind("<Configure>", lambda event: feedback.configure(wraplength=max(80, event.width)))
        self.details_display = ReadOnlyText(editor, height=12)
        self.details_display.pack(fill="both", expand=True)
        self.details = self.details_display.text
        self.editor_form.bind_content()
        app.initial_split(pane, .48)
        self.update_controls()
        self.original.trace_add("write", lambda *_: self.update_controls())
        if hasattr(app.root, "drop_target_register"):
            from tkinterdnd2 import DND_FILES
            self.tree.drop_target_register(DND_FILES)
            self.tree.dnd_bind("<<Drop>>", self.drop)

    def config(self):
        return self.app.inbox.config()

    def item_help(self, row, column):
        if column == "name":
            return "Double-click or press Enter to open this downloaded file. Use Review selected to identify it and check its proposed filename."
        if column != "state":
            return ""
        item = self.rows.get(row, {})
        return {
            "waiting": "Waiting for the download to finish and stop changing. Use Refresh inbox after it finishes, then Review selected.",
            "ready": "The download is ready. Use Review selected to identify it and check its proposed name.",
            "preparing": "Reading document information using your current naming and online permissions.",
            "review": "The name is ready for your review. Check the filename and destination before choosing File document.",
            "skipped": "Set aside without moving the document. You can review it again at any time; a changed file returns to the incoming queue.",
            "error": item.get("error") or "Identification needs attention. Review the document again after resolving the issue.",
        }.get(item.get("status"), "")

    def update_controls(self):
        selected = bool(self.tree.selection())
        source = self.original_label.path_access.value()
        self.original_name.set(Path(source).name if source else self.original.get())
        if source:
            self.original_path_copy.pack(side="left", padx=(8, 0))
        else:
            self.original_path_copy.pack_forget()
        self.review_button.configure(state="normal" if selected and not self.busy else "disabled")
        self.skip_button.configure(state="normal" if selected and not self.busy else "disabled")
        self.file_button.configure(state="normal" if self.review_path and not self.busy else "disabled")
        self.retry_button.configure(state="normal" if self.review_path and self.retry_available and not self.busy else "disabled")

    def render(self, rows):
        self.rows = {row["path"]: row for row in rows}
        self.app.update_rows(self.tree, [(row["path"], (row.get("name", Path(row["path"]).name),
                             row.get("status", "Waiting for review").replace("_", " ").capitalize())) for row in rows])
        config = self.config()
        for key, variable in self.location_variables.items():
            variable.set(config.get(key, ""))
        if config.get("watch_folder"):
            self.summary.set(f"{len(rows)} document{'' if len(rows) == 1 else 's'} · "
                             + ("Automatic inbox checks on" if config.get("enabled") else "Automatic inbox checks off; Refresh inbox checks on demand"))
        self.selected()

    def refresh(self):
        if self.busy or self.app.closing:
            return
        self.busy = True
        self.update_controls()
        def checked():
            self.app.inbox.refresh()
            return self.app.inbox.list_items()
        background(self.app, checked, self.refreshed, self.failed, task='Checking Inbox documents…')

    def load_rows(self):
        if self.busy or self.app.closing:
            return
        self.busy = True
        background(self.app, self.app.inbox.list_items, self.refreshed, self.failed, task='Loading Inbox documents…')

    def refreshed(self, rows):
        self.busy = False
        self.render(rows)

    def failed(self, exc):
        self.busy = False
        self.feedback.set(str(exc))
        self.update_controls()

    def selected(self, event=None):
        selection = self.tree.selection()
        path = selection[0] if selection else None
        row = self.rows.get(path, {})
        invalid = self.review_path and (row.get("signature") != self.review_signature or row.get("status") not in {"review", "error"})
        if path != self.review_path or invalid or (not path and self.original_label.path_access.value()):
            self.generation += 1
            self.review_path = None
            self.review_signature = None
            self.retry_available = False
            self.filename.set("")
            self.original.set(path or "Select a document in the inbox.")
            self.set_details(self.rows.get(path, {}).get("error", "Choose Review selected to identify this document."))
            if invalid:
                self.feedback.set("This document or its naming settings changed. Review it again before filing.")
        self.update_controls()

    def set_details(self, text):
        self.details_display.set(text)

    def open_document(self, row):
        if not self.busy:
            self.app.open_file_or_folder(self.rows.get(row, {}).get("path", row))

    def review(self, force=False):
        selection = self.tree.selection()
        if not selection or self.busy:
            return
        path = selection[0]
        edited_name = self.filename.get() if force and self.review_path == path and self.filename.get() != self.proposal else ""
        self.generation += 1
        generation = self.generation
        self.busy = True
        self.feedback.set("Identifying document…")
        self.update_controls()
        def prepared(details):
            self.busy = False
            if generation != self.generation or not self.tree.selection() or self.tree.selection()[0] != path:
                self.update_controls()
                return
            self.review_path = path
            self.review_signature = details.get("signature")
            self.original.set(path)
            self.proposal = details.get("proposed_filename", Path(path).name)
            self.filename.set(edited_name or self.proposal)
            self.retry_available = bool(details.get("ai_retry_available"))
            self.destination.set(self.destination.get() or self.config().get("library_root", ""))
            self.set_details(explanation(details.get("details", details)))
            self.feedback.set("Check the name and folder, then file the document.")
            self.update_controls()
        def identify():
            from .inbox import DownloadNotReady
            try:
                return self.app.inbox.prepare(path, force=force)
            except DownloadNotReady:
                raise
            except ValueError as exc:
                row = next((item for item in self.app.inbox.list_items() if item["path"] == path), None)
                if not row or row.get("status") != "error":
                    raise
                return {"signature": row["signature"], "proposed_filename": Path(path).name,
                        "review_reasons": [f"{exc} Enter a name manually or retry identification."],
                        "ai_retry_available": True}
        background(self.app, identify, prepared, self.failed, task=f'Identifying Inbox document: {Path(path).name}')

    def choose_destination(self):
        root = self.config().get("library_root", "")
        target = filedialog.askdirectory(parent=self.app.root, title="Choose a folder in your library",
                                        initialdir=self.destination.get() or root or None, mustexist=False)
        if target:
            self.destination.set(target)

    def file_document(self):
        if not self.review_path or self.busy:
            return
        path, name, destination = self.review_path, self.filename.get().strip(), self.destination.get().strip()
        if not name or not destination:
            self.feedback.set("Enter a filename and choose a destination folder.")
            return
        if not messagebox.askokcancel("File document", f"File: {name}\n\nFolder: {destination}", parent=self.app.root):
            return
        self.busy = True
        self.update_controls()
        def filed(result):
            self.busy = False
            self.review_path = None
            self.feedback.set(f"Filed: {result['path']}")
            self.refresh()
        reviewed_signature = self.review_signature
        background(self.app, lambda: self.app.inbox.file_item(path, name, destination, expected_signature=reviewed_signature), filed, self.failed, task=f'Filing Inbox document: {name}')

    def skip(self):
        selection = self.tree.selection()
        if selection and not self.busy:
            path = selection[0]
            self.busy = True
            self.update_controls()
            background(self.app, lambda: self.app.inbox.skip(path), self.mutated, self.failed, task='Saving the Inbox skip decision…')

    def add_documents(self):
        if self.busy or self.app.closing:
            return
        paths = filedialog.askopenfilenames(parent=self.app.root, title="Add documents to inbox",
                                           filetypes=[("Supported documents", "*.pdf *.docx *.pptx *.ppt"), ("All files", "*.*")])
        if paths:
            self.add(paths)

    def drop(self, event):
        if self.busy or self.app.closing:
            return "none"
        self.add(self.app.root.tk.splitlist(event.data))
        return "copy"

    def add(self, paths):
        if self.busy or self.app.closing:
            return
        self.busy = True
        self.update_controls()
        background(self.app, lambda: self.app.inbox.add_files(paths), self.mutated, self.failed, task='Adding documents to the Inbox…')

    def mutated(self, result):
        self.busy = False
        self.refresh()

    def open_folder(self, key):
        target = self.config().get(key)
        if target:
            self.app.open_path(target)
        else:
            self.feedback.set("Choose your folders in Settings → Sorting first.")


class SortingFields:
    """Settings drafts apply explicitly and never silently import another app."""
    def __init__(self, app, parent):
        from .sorting import FILENAME_FORMAT_LABELS
        self.app, self.parent = app, parent
        self.initial = app.inbox.config()
        self.labels = FILENAME_FORMAT_LABELS
        self.watch = tk.StringVar(value=self.initial.get("watch_folder", ""))
        self.library = tk.StringVar(value=self.initial.get("library_root", ""))
        self.enabled = tk.BooleanVar(value=self.initial.get("enabled", False))
        self.folder_entries = {}
        self.folder_copy_buttons = {}
        for label, variable in (("Incoming documents", self.watch), ("Library root", self.library)):
            ttk.Label(parent, text=label).pack(anchor="w")
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=(4, 10))
            entry = self.folder_entries[label] = ttk.Entry(row, textvariable=variable, width=1)
            entry.pack(side="left", fill="x", expand=True)
            path_access = PathField(entry, "Folder where new downloads wait for naming and filing. The app checks documents directly in this folder, not its subfolders. Keep it separate from the library root." if variable is self.watch else
                    "Top folder containing your sorted documents. Choose a destination beneath this root for each document. Keep it separate from the incoming folder; neither folder may contain the other.")
            copy = self.folder_copy_buttons[label] = path_access.add_copy_button(row)
            copy.pack(side="left", padx=(8, 0))
            browse = Button(row, text="Browse…", command=lambda var=variable: self.browse(var))
            browse.pack(side="left", padx=(8, 0))
            Tooltip(browse, "Choose the incoming folder or library root. These folders must be separate.")
        ttk.Label(parent, text="Hover over a path to read its full location and help. Use the copy button beside it to copy the full path.",
                  style="Muted.TLabel", wraplength=520).pack(fill="x", pady=(0, 10))
        self.watch_check = ttk.Checkbutton(parent, text="Check the inbox automatically while this app is open", variable=self.enabled)
        self.watch_check.pack(anchor="w", pady=(0, 12))
        Tooltip(self.watch_check, "Find new and changed downloads while this app is open. Each document still needs your review before filing. With this off, use Refresh inbox. This option does not launch or watch the app while it is closed.")
        self.mode = tk.StringVar(value="Local only" if self.initial.get("naming_mode") == "Basic" else "Smart metadata lookup")
        ttk.Label(parent, text="Naming method").pack(anchor="w")
        self.mode_combo = ttk.Combobox(parent, textvariable=self.mode, values=["Smart metadata lookup", "Local only"], state="readonly", width=36)
        self.mode_combo.pack(anchor="w", pady=(4, 8))
        Tooltip(self.mode_combo, "Local only reads document text and built-in metadata on this computer and makes no online requests. Smart can check an exact DOI for citation metadata, then use Gemini as a backup when you enable it with your own key. You review every proposed name.")
        self.online = tk.BooleanVar(value=self.initial.get("online_metadata_lookup_enabled", True))
        self.online_check = ttk.Checkbutton(parent, text="Look up an exact DOI online in Smart mode", variable=self.online)
        self.online_check.pack(anchor="w")
        Tooltip(self.online_check, "In Smart mode, send a DOI identifier found in the document to Crossref or DataCite to retrieve citation metadata. This lookup sends the DOI, not the document text or file, and does not require a Gemini key.")
        self.format = tk.StringVar(value=self.labels.get(self.initial.get("filename_format", "smart"), self.labels["smart"]))
        ttk.Label(parent, text="Filename style").pack(anchor="w", pady=(10, 0))
        self.format_combo = ttk.Combobox(parent, textvariable=self.format, values=list(self.labels.values()), state="readonly", width=44)
        self.format_combo.pack(anchor="w", pady=(4, 8))
        Tooltip(self.format_combo, self.filename_style_help)
        self.template = tk.StringVar(value=self.initial.get("custom_filename_template", ""))
        ttk.Label(parent, text="Custom template (used only for Custom style)").pack(anchor="w")
        self.template_entry = ttk.Entry(parent, textvariable=self.template)
        self.template_entry.pack(fill="x", pady=(4, 8))
        Tooltip(self.template_entry, self.template_help)
        self.api_key = tk.StringVar()
        self.key_removal_pending = False
        self.gemini_before_key_removal = False
        self.gemini_enabled = tk.BooleanVar(value=self.initial.get("gemini_enabled", False))
        self.gemini_toggle = ttk.Checkbutton(parent, text="Use Gemini for document identification", variable=self.gemini_enabled)
        self.gemini_toggle.pack(anchor="w", pady=(0, 6))
        Tooltip(self.gemini_toggle, "Optional: Smart mode can send document text to Gemini using your own key. New installations start off; Local only never sends it. Word and PowerPoint also need their separate permissions below.")
        ttk.Label(parent, text="Your Gemini key (optional; blank keeps your saved key)").pack(anchor="w")
        self.key_entry = ttk.Entry(parent, textvariable=self.api_key, show="•")
        self.key_entry.pack(fill="x", pady=(4, 6))
        Tooltip(self.key_entry, "Enter your own key, then Save preferences. It is protected for your Windows account in this app's local library and excluded from shared source and ordinary settings import. Blank preserves a saved key unless you have marked it for removal.")
        self.gemini_model = tk.StringVar(value=self.initial.get("gemini_model", "gemini-3.5-flash-lite"))
        ttk.Label(parent, text="Gemini model").pack(anchor="w")
        model = ttk.Combobox(parent, textvariable=self.gemini_model,
                             values=["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-2.5-flash"], width=40)
        model.pack(anchor="w", pady=(4, 6))
        Tooltip(model, "Choose a model available to your key. Existing users can retain Gemini 2.5 Flash. Model access can change; Test connection checks availability without sending document text.")
        self.test_connection_button = Button(parent, text="Test connection", command=self.test_connection)
        self.test_connection_button.pack(anchor="w", pady=(0, 8))
        Tooltip(self.test_connection_button, "Check the selected Gemini model and your draft or saved key without sending any document text or requesting a generation.")
        key_actions = ttk.Frame(parent)
        key_actions.pack(fill="x", pady=(0, 8))
        self.key_status = tk.StringVar(value="Key saved for your Windows account" if self.initial.get("api_key_present") else "No Gemini key saved")
        ttk.Label(key_actions, textvariable=self.key_status, style="Muted.TLabel").pack(side="left")
        self.remove_key_button = Button(key_actions, text="Remove saved key", command=self.remove_key,
                                        state="normal" if self.initial.get("api_key_present") else "disabled")
        self.remove_key_button.pack(side="right")
        Tooltip(self.remove_key_button, self.key_removal_help)
        self.word_ai = tk.BooleanVar(value=self.initial.get("allow_cloud_ai_for_word_documents", False))
        self.slides_ai = tk.BooleanVar(value=self.initial.get("allow_cloud_ai_for_presentation_documents", False))
        self.word_ai_check = ttk.Checkbutton(parent, text="Allow Gemini backup for Word documents", variable=self.word_ai)
        self.word_ai_check.pack(anchor="w")
        Tooltip(self.word_ai_check, "When Smart mode and Gemini are enabled, allow extracted Word (.docx) text to be sent to Gemini if citation information is incomplete. With this off, Word text stays on this computer; an enabled DOI lookup can still send only the DOI.")
        self.slides_ai_check = ttk.Checkbutton(parent, text="Allow Gemini backup for PowerPoint presentations", variable=self.slides_ai)
        self.slides_ai_check.pack(anchor="w")
        Tooltip(self.slides_ai_check, "When Smart mode and Gemini are enabled, allow extracted PowerPoint (.pptx) text to be sent to Gemini as a naming backup. Legacy .ppt files need manual review and are not sent to Gemini. DOI lookup permission is separate; presentations stay local for filing and do not enter PDF notes.")
        importer = Button(parent, text="Import sorter settings…", command=self.import_settings)
        importer.pack(anchor="w", pady=(10, 6))
        Tooltip(importer, "Load the old sorter's folders and naming preferences into this draft. Save preferences applies them; automatic checking starts off.")
        self.help = tk.StringVar(value="Local only makes no citation or Gemini requests. Word and PowerPoint remain local files; tablet transfer accepts PDFs.")
        ttk.Label(parent, textvariable=self.help, wraplength=520, style="Muted.TLabel").pack(fill="x")
        self.mode.trace_add("write", self.update_naming_controls)
        self.gemini_enabled.trace_add("write", self.update_naming_controls)
        self.format.trace_add("write", self.update_naming_controls)
        self.update_naming_controls()

    def update_naming_controls(self, *_):
        key_state = "disabled" if self.key_removal_pending else "normal"
        self.key_entry.configure(state=key_state)
        self.gemini_toggle.configure(state=key_state)
        smart = self.mode.get() == "Smart metadata lookup"
        self.online_check.configure(state="normal" if smart else "disabled")
        cloud = smart and self.gemini_enabled.get()
        for check in (self.word_ai_check, self.slides_ai_check):
            check.configure(state="normal" if cloud else "disabled")
        self.template_entry.configure(state="normal" if self.format.get() == self.labels["custom"] else "disabled")

    def test_connection(self):
        if self.key_removal_pending:
            self.help.set("Undo key removal or enter a key before testing.")
            return
        key, model = self.api_key.get().strip(), self.gemini_model.get().strip()
        self.test_connection_button.configure(state="disabled")
        self.help.set("Checking model access. No document text is sent…")
        def check():
            from google import genai
            from .sorting.key_protection import _unprotect_for_current_windows_user
            secret = key
            if not secret:
                saved = self.app.store.preference("inbox", {})
                secret = _unprotect_for_current_windows_user(saved.get("api_key_protected", "")) if saved.get("api_key_protected") else ""
            if not secret:
                raise ValueError("Enter your Gemini key first, or save one in Settings.")
            try:
                with genai.Client(api_key=secret, http_options={"timeout": 15000}) as client:
                    client.models.get(model=model)
            except Exception:
                raise ValueError("Connection check failed. Check your key, model ID, account access and network.") from None
            return f"Connection verified: {model}. No document text was sent and no generation was requested."
        def completed(message):
            if self.parent.winfo_exists():
                self.test_connection_button.configure(state="normal")
                self.help.set(message)
        background(self.app, check, completed, lambda error: completed(str(error)), task='Finishing the naming-service connection test…')

    def filename_style_help(self):
        style = next((key for key, label in self.labels.items() if label == self.format.get()), "smart")
        examples = {
            "smart": "Choose a pattern for the detected document type. Journal papers use author, journal and year; patents use inventor, year and patent number. Confirmed supporting information receives an SI suffix.",
            "journal_compact": "Use author, an available journal abbreviation and year. The app does not invent an abbreviation; it uses Smart when the required journal information is missing or the document is another type.",
            "journal_detailed": "Use author, journal, volume, issue and year. Use Smart instead when the journal cannot be identified or the document is another type.",
            "author_year_title": "Use author, year and title, for example Smith_2026_Research_title.pdf. The original document extension is retained.",
            "title_year_type": "Use title, year and document type. This can help distinguish reports, presentations and other document types while preserving their original extension.",
            "custom": "Build a name from the tokens in the Custom template field. Do not include a folder path or extension. The app checks the template when you save preferences.",
        }
        return examples[style]

    @staticmethod
    def template_help():
        from .sorting.core_logic import FILENAME_TEMPLATE_TOKENS
        tokens = ", ".join("{" + token + "}" for token in sorted(FILENAME_TEMPLATE_TOKENS))
        return ("Used only with Custom style. Example: {author_last_et_al}_{year}_{title}. "
                "Leave out the file extension; it is added automatically. Supported tokens: " + tokens)

    def remove_key(self):
        if not self.initial.get("api_key_present") or self.key_removal_pending:
            return
        self.gemini_before_key_removal = self.gemini_enabled.get()
        self.key_removal_pending = True
        self.gemini_enabled.set(False)
        self.remove_key_button.configure(text="Undo removal", command=self.undo_key_removal)
        self.key_status.set("Key will be removed when you save.")
        self.help.set("Removal is pending. Save deletes this app's saved key and turns Gemini off; Undo removal or Cancel keeps it.")

    def undo_key_removal(self):
        self.key_removal_pending = False
        self.gemini_enabled.set(self.gemini_before_key_removal)
        self.remove_key_button.configure(text="Remove saved key", command=self.remove_key)
        self.key_status.set("Key saved for your Windows account")
        self.help.set("Removal cancelled. The saved key and your other draft edits are retained.")

    def key_removal_help(self):
        if self.key_removal_pending:
            return "Cancel the proposed removal. The stored key has not been deleted; your other draft edits are kept."
        return "Mark this app's saved key for removal when you Save preferences. Undo removal or Cancel keeps it. Saving deletes the key and turns Gemini off; separate key files and old sorter settings stay unchanged."

    def browse(self, variable):
        target = filedialog.askdirectory(parent=self.parent.winfo_toplevel(), initialdir=variable.get() or None)
        if target:
            variable.set(target)

    def values(self):
        result = {"watch_folder": self.watch.get().strip(), "library_root": self.library.get().strip(),
                  "enabled": self.enabled.get(), "naming_mode": "Basic" if self.mode.get() == "Local only" else "Automatic",
                  "filename_format": next((key for key, label in self.labels.items() if label == self.format.get()), "smart"),
                  "custom_filename_template": self.template.get(), "online_metadata_lookup_enabled": self.online.get(),
                  "gemini_enabled": False if self.key_removal_pending else self.gemini_enabled.get(),
                  "gemini_model": self.gemini_model.get().strip(),
                  "allow_cloud_ai_for_word_documents": self.word_ai.get(),
                  "allow_cloud_ai_for_presentation_documents": self.slides_ai.get()}
        if self.key_removal_pending:
            result["api_key"] = ""
        elif self.api_key.get().strip():
            result["api_key"] = self.api_key.get().strip()
        return result

    def import_settings(self):
        default = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "AI Paper Sorter" / "config.json"
        path = str(default) if default.is_file() else filedialog.askopenfilename(parent=self.parent.winfo_toplevel(),
                         title="Choose Paper Sorter settings", filetypes=[("Settings JSON", "*.json")])
        if not path:
            return
        def loaded(preview):
            # Import into draft fields; Save preferences is the only application.
            self.watch.set(preview.get("watch_folder", ""))
            self.library.set(preview.get("library_root", preview.get("sorted_folder", "")))
            self.mode.set("Local only" if preview.get("naming_mode") == "Basic" else "Smart metadata lookup")
            self.format.set(self.labels.get(preview.get("filename_format", "smart"), self.labels["smart"]))
            self.template.set(preview.get("custom_filename_template", ""))
            self.online.set(preview.get("online_metadata_lookup_enabled", True))
            self.word_ai.set(preview.get("allow_cloud_ai_for_word_documents", False))
            self.slides_ai.set(preview.get("allow_cloud_ai_for_presentation_documents", False))
            self.enabled.set(False)
            self.gemini_enabled.set(False)
            if self.key_removal_pending:
                self.gemini_before_key_removal = False
            self.help.set("Imported folders and naming into this draft. Save preferences to apply. Inbox checks and Gemini start off; your key was not imported. Close the old sorter before enabling inbox checks.")
        background(self.app, lambda: self.app.inbox.preview_sorter_settings(path),
                   lambda result: loaded(result) if self.parent.winfo_exists() else None,
                   lambda exc: self.help.set(str(exc)) if self.parent.winfo_exists() else None, task='Reading imported sorting settings…')


class IntegrationFields:
    def __init__(self, app, parent):
        self.app = app
        self.initial = app.cloud_config()
        self.master = tk.BooleanVar(value=self.initial["integration_enabled"])
        toggle = ttk.Checkbutton(parent, text="Enable reMarkable cloud services", variable=self.master)
        toggle.pack(anchor="w", pady=(0, 8))
        Tooltip(toggle, "After Save preferences, show or hide the reMarkable tab and allow or pause cloud activity. Turning off keeps saved notes, pairing and folder links. Uploads and folder creation have their own switches.")
        ttk.Label(parent, text="The reMarkable tab appears when enabled. Pair your account and choose the linked roots there. New installations start with this off.",
                  style="Muted.TLabel", wraplength=520).pack(fill="x", pady=(0, 16))
        self.variables = {}
        self.checks = []
        for key, label in (("send_new_pdfs", "Send newly filed PDFs in linked folders"),
                           ("mirror_cloud_folders", "Create PC counterparts for new tablet folders"),
                           ("mirror_pc_folders", "Create tablet counterparts for new PC folders")):
            variable = self.variables[key] = tk.BooleanVar(value=self.initial.get(key, False))
            check = ttk.Checkbutton(parent, text=label, variable=variable)
            check.pack(anchor="w", pady=5)
            self.checks.append(check)
            Tooltip(check, {"send_new_pdfs": "After saving, queue only newly filed original PDFs beneath the linked PC root. Other document types stay local. Existing papers need an explicit Send selected PDF action; uncertain duplicates need review.",
                            "mirror_cloud_folders": "After saving, new tablet folders beneath the selected cloud root can get PC counterparts. Existing mismatches need review; invalid names and collisions are flagged. Renames, moves and deletions are not propagated.",
                            "mirror_pc_folders": "After saving, new PC folders beneath the linked root can get tablet counterparts. Parent folders are created first. Existing papers are not bulk uploaded, and renames, moves and deletions are not propagated."}[key])
        ttk.Label(parent, text="Transfers apply within your linked PC library folder. Existing papers and folder mismatches are reviewed separately; these settings apply to new additions.",
                  wraplength=520, style="Muted.TLabel").pack(fill="x", pady=(16, 8))
        self.master.trace_add("write", self.changed)
        self.changed()

    def changed(self, *_):
        for check in self.checks:
            check.configure(state="normal" if self.master.get() else "disabled")

    def changes(self):
        values = {"integration_enabled": self.master.get(), **{key: variable.get() for key, variable in self.variables.items()}}
        return {key: value for key, value in values.items() if value != self.initial.get(key, False)}


class ReconciliationWindow:
    def __init__(self, app):
        self.app = app
        self.rows = {}
        self.choices = {}
        self.sort_column, self.sort_reverse = "kind", False
        self.scan_generation = 0
        self.busy = False
        self.checking = False
        self.copy_sources = {}
        self.copy_finding = None
        self.action_detail = ""
        self.cancelled = __import__("threading").Event()
        self.window = window = tk.Toplevel(app.root)
        window.title("Review duplicates & folder mismatches")
        window.configure(background=BACKGROUND)
        window.geometry("1000x700")
        window.transient(app.root)
        bind_dialog_close(window, self.close)
        self.scope = tk.StringVar(value=app.cloud_config().get("pc_root") or app.inbox.config().get("library_root", ""))
        frame = self.review_frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        heading = ttk.Label(frame, text="Compare your library before changing it", style="Section.TLabel")
        heading.pack(anchor="w")
        introduction = self.review_introduction = ttk.Label(frame, text="Find duplicates and differences using local files and the last downloaded tablet information. Different notes and files stay preserved.",
                  wraplength=900, style="Muted.TLabel")
        introduction.pack(fill="x", pady=(8, 12))
        introduction.bind("<Configure>", lambda event: introduction.configure(wraplength=max(80, event.width)))
        Tooltip(heading, lambda: introduction.cget("text"))
        scope = self.review_scope_row = ttk.Frame(frame)
        scope.pack(fill="x", pady=(0, 10))
        ttk.Label(scope, text="PC folder").pack(side="left", padx=(0, 8))
        self.scope_entry = ttk.Entry(scope, textvariable=self.scope)
        self.scope_entry.pack(side="left", fill="x", expand=True)
        scope_access = PathField(self.scope_entry, "Choose the PC folder to check. Local PDFs can be compared without connecting; saved tablet comparisons remain limited to the linked PC root.")
        self.scope_path_copy = scope_access.add_copy_button(scope)
        self.scope_path_copy.pack(side="left", padx=(8, 0))
        browse = Button(scope, text="Browse…", command=self.browse)
        browse.pack(side="left", padx=8)
        Tooltip(browse, "Choose an existing PC folder for this review; the saved sorting and cloud roots remain unchanged.")
        self.check_button = Button(scope, text="Check library", command=self.check, style="Primary.TButton")
        self.check_button.pack(side="left")
        Tooltip(self.check_button, "Compare local PDFs and previously saved tablet information in the background. This does not download, upload, delete or link anything. Cached results may be incomplete.")
        self.feedback = tk.StringVar(value="Choose Check library. Tablet comparisons use previously downloaded information; refreshing folders alone does not cache the PDFs.")
        feedback = ttk.Label(frame, textvariable=self.feedback, style="Muted.TLabel", wraplength=900)
        feedback.pack(fill="x", pady=(0, 8))
        feedback.bind("<Configure>", lambda event: feedback.configure(wraplength=max(80, event.width)))
        filters = ttk.Frame(frame)
        filters.pack(fill="x", pady=(0, 8))
        self.finding_type = tk.StringVar(value="All types")
        self.review_state = tk.StringVar(value="Needs review")
        self.search = tk.StringVar()
        self.type_filter = ttk.Combobox(filters, textvariable=self.finding_type, values=["All types"], state="readonly", width=25)
        self.type_filter.pack(side="left")
        state = ttk.Combobox(filters, textvariable=self.review_state, values=["Needs review", "All findings", "Already linked", "Kept separate"], state="readonly", width=18)
        state.pack(side="left", padx=8)
        self.search_label = ttk.Label(filters, text="Search", image=icon(filters, "search"), compound="left")
        self.search_label.pack(side="left", padx=(0, 8))
        self.search_entry = search = ttk.Entry(filters, textvariable=self.search, width=20)
        EntryPlaceholder(search, "Search papers, folders, or file paths…", self.search)
        search.pack(side="left", fill="x", expand=True)
        Tooltip(self.type_filter, "Show one kind of finding, such as identical local copies or folder differences.")
        Tooltip(state, "Separate items still needing a decision from existing links and copies you chose to keep separate.")
        Tooltip(search, "Search paper names, explanations and file locations in these findings.")
        for variable in (self.finding_type, self.review_state, self.search):
            variable.trace_add("write", lambda *_: self.render())
        # Reserve actions and the copy picker before giving the findings table
        # its remaining height, so long lists cannot push Delete/Close offscreen.
        footer = self.review_footer = ttk.Frame(frame)
        footer.pack(side="bottom", fill="x")
        self.tree = app.tree(frame, [("kind", "Finding", 180), ("name", "Paper / folder", 290), ("reason", "Explanation", 450)], content_columns=(),
                             empty_text="Choose Check library to compare papers.")
        for column in ("kind", "name", "reason"):
            self.tree.heading(column, command=lambda key=column: self.sort(key))
        self.tree.bind("<<TreeviewSelect>>", self.selected)
        bind_item_open(self.tree, self.open_finding)
        self.details_display = ReadOnlyText(footer, height=3)
        self.details_display.pack(fill="x", pady=10)
        self.details = self.details_display.text
        ttk.Label(footer, text="Copies · Ctrl/Shift-click to select files to link or delete", style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        self.local_copies = app.tree(footer, [("name", "File / folder", 270), ("local", "Location", 510),
                                            ("state", "Status", 110)], height=4, content_columns=(),
                                     empty_text="This finding has no local files", pack=False)
        self.local_copies.master.pack(fill="x", pady=(0, 8))
        self.copy_paths = {}
        self.local_copies.configure(selectmode="extended")
        self.local_copies.bind("<<TreeviewSelect>>", self.copy_selected)
        bind_item_open(self.local_copies, self.open_copy)
        self.local_copies.tooltip.value = lambda row, _column: self.copy_paths.get(row) or "Tablet ID: " + self.copy_sources.get(row, {}).get("cloud_id", "")
        self.local_copies.tooltip.extra = lambda row, _column: "Ctrl/Shift-click to select several copies. Link uses only the selected sources; Delete applies only to selected local PDFs."
        self.local_copies.tooltip.full_with_help = True
        action_row = ttk.Frame(footer)
        action_row.pack(fill="x")
        actions = self.review_actions = WrapToolbar(action_row)
        actions.pack(side="left", fill="x", expand=True)
        self.open_pdf_button = actions.add(Button(actions, text="Open PDF", command=self.open_pdf, state="disabled"))
        self.open_folder_button = Button(actions, text="Open containing folder", command=self.open_folder, state="disabled")
        self.local_path_copy = Button(actions, text="Copy full path", command=self.copy_path, state="disabled")
        self.delete_pdf_button = Button(actions, text="Delete selected PDFs…", command=self.delete_pdf, state="disabled")
        Tooltip(self.local_path_copy, lambda: "Copy the selected local file paths, one per line.\n\n" + "\n".join(self.selected_paths())
                if self.selected_paths() else "Select local files in the list above to copy their full paths.")
        Tooltip(self.open_pdf_button, lambda: "Select a finding and an available local PDF above first." if self.open_pdf_button.instate(["disabled"]) else
                "Open the selected local PDF to inspect its contents and annotations.\n\n" + self.selected_path())
        Tooltip(self.open_folder_button, lambda: "Select a finding and a local copy above first." if self.open_folder_button.instate(["disabled"]) else
                "Open the folder containing the selected copy in File Explorer.\n\n" + self.selected_path())
        Tooltip(self.delete_pdf_button, lambda: "Review the selected local PDFs and confirm moving them to Windows Recycle Bin. Saved notes, history and tablet sources stay preserved.\n\n" + "\n".join(self.selected_paths())
                if not self.delete_pdf_button.instate(["disabled"]) else "Select available local PDFs inside the checked folder. Folders and tablet sources cannot be deleted here; wait for the current check or action to finish.")
        self.link_button = actions.add(Button(actions, text="Link selected copies…", command=self.link, state="disabled", style="Primary.TButton"))
        Tooltip(self.link_button, "Select at least two copies in the lower list, using Ctrl/Shift-click. Confirm only those selected sources as the same paper. Previously linked copies remain together; files, annotation history and independent notes are retained.")
        self.map_button = Button(actions, text="Map and sync…", command=self.map_folder, state="disabled")
        Tooltip(self.map_button, "Link the selected tablet folder to an existing PC folder, then sync enabled transfers. Different folder names can remain linked.")
        self.send_button = Button(actions, text="Send selected PDF…", command=self.send, state="disabled")
        Tooltip(self.send_button, "Review an explicit transfer of this existing PDF. Enable reMarkable PDF transfers in Connections first.")
        self.keep_button = actions.add(Button(actions, text="Keep separate", command=lambda: self.save_choice(True), state="disabled"))
        actions.add(self.map_button, visible=False)
        actions.add(self.send_button, visible=False)
        self.again_button = Button(actions, text="Review again", command=lambda: self.save_choice(False), state="disabled")
        self.undo_button = Button(actions, text="Undo last link…", command=self.undo, state="disabled")
        Tooltip(self.keep_button, "Remember that these copies or folders should stay separate. No files or notes are removed.")
        Tooltip(self.again_button, "Clear your Keep separate decision and return this finding to review.")
        Tooltip(self.undo_button, "Restore the paper relationships from the latest link made by this version. Original files and notes stay preserved.")
        self.more_button = actions.add(Button(actions, text="More…", command=self.show_more))
        Tooltip(self.more_button, "Open folder, copy selected paths, review a kept-separate finding again, undo the last link, or delete selected local PDFs.")
        self.more_menu = tk.Menu(self.more_button, tearoff=False, postcommand=self.update_more_menu)
        self.menu_actions = []
        for label, control in (("Open containing folder", self.open_folder_button), ("Copy selected paths", self.local_path_copy),
                               (None, None), ("Review again", self.again_button), ("Undo last link…", self.undo_button),
                               (None, None), ("Delete selected PDFs…", self.delete_pdf_button)):
            if control is None:
                self.more_menu.add_separator()
            else:
                menu_action(self.more_menu, label, control.invoke)
                self.menu_actions.append((self.more_menu.index("end"), control))
        self.update_more_menu()
        background(app, self.load_review_state, self.loaded_review_state, task='Loading library review details…')
        close = self.close_button = Button(action_row, text="Close", command=self.close)
        close.pack(side="right")
        Tooltip(close, "Close this review and cancel its unfinished scan. Confirmed links remain saved.")
        window.protocol("WM_DELETE_WINDOW", self.close)
        annotate_buttons(window)
        self.layout_after = None
        window.bind("<Configure>", self.schedule_layout, add="+")
        self.schedule_layout()

    def update_more_menu(self):
        for index, button in self.menu_actions:
            self.more_menu.entryconfigure(index, state="disabled" if button.instate(["disabled"]) else "normal")

    def show_more(self):
        try:
            self.more_menu.tk_popup(self.more_button.winfo_rootx(), self.more_button.winfo_rooty() + self.more_button.winfo_height())
        finally:
            self.more_menu.grab_release()

    def schedule_layout(self, event=None):
        if self.layout_after is None and self.window.winfo_exists():
            self.layout_after = self.app.root.after_idle(self.fit_review_tables)

    def fit_review_tables(self):
        """Give both tables visible rows before allocating extra detail space.

        Footer actions keep their normal size. High DPI and shorter windows
        reduce the copy/detail requests instead of squeezing the findings
        table out of existence; scrolling retains the rest of each list.
        """
        self.layout_after = None
        if not self.window.winfo_exists() or self.review_frame.winfo_height() <= 1:
            return
        from tkinter import font
        frame, footer = self.review_frame, self.review_footer
        parts = lambda value: (value,) if isinstance(value, (int, float)) else frame.tk.splitlist(value)
        pixels = lambda value: sum(frame.winfo_pixels(part) for part in parts(value))
        padding = parts(frame.cget("padding"))
        vertical = (2 * frame.winfo_pixels(padding[0]) if len(padding) == 1 else
                    2 * frame.winfo_pixels(padding[1]) if len(padding) == 2 else
                    frame.winfo_pixels(padding[1]) + frame.winfo_pixels(padding[-1])) if padding else 0
        header = 0
        for child in frame.pack_slaves():
            if child in (footer, self.tree.master, self.review_introduction):
                continue
            info = child.pack_info()
            pady = parts(info.get("pady", 0))
            header += child.winfo_reqheight() + (2 * frame.winfo_pixels(pady[0]) if len(pady) == 1 else pixels(pady))
        style = ttk.Style(self.tree)
        row_height = int(style.lookup("Treeview", "rowheight") or 24)
        tree_rows = int(self.tree.cget("height"))
        finding_chrome = self.tree.master.winfo_reqheight() - tree_rows * row_height
        finding_minimum = finding_chrome + 2 * row_height
        detail_lines = int(self.details.cget("height"))
        line_height = font.Font(root=self.window, font=self.details.cget("font")).metrics("linespace")
        detail_chrome = self.details_display.winfo_reqheight() - detail_lines * line_height
        copy_rows = int(self.local_copies.cget("height"))
        copy_chrome = self.local_copies.master.winfo_reqheight() - copy_rows * row_height
        fixed_footer = footer.winfo_reqheight() - self.details_display.winfo_reqheight() - self.local_copies.master.winfo_reqheight()
        room = frame.winfo_height() - vertical - header - finding_minimum - fixed_footer
        introduction_height = self.review_introduction.winfo_reqheight() + 20
        minimum_lists = detail_chrome + line_height + copy_chrome + row_height
        show_introduction = room >= minimum_lists + introduction_height
        if show_introduction:
            if not self.review_introduction.winfo_manager():
                self.review_introduction.pack(fill="x", pady=(8, 12), before=self.review_scope_row)
            room -= introduction_height
        elif self.review_introduction.winfo_manager():
            self.review_introduction.pack_forget()
        choices = ((3, 4), (3, 3), (2, 3), (2, 2), (1, 2), (1, 1))
        desired = next(((lines, rows) for lines, rows in choices
                        if detail_chrome + lines * line_height + copy_chrome + rows * row_height <= room), (1, 1))
        if detail_lines != desired[0]:
            self.details.configure(height=desired[0])
        if copy_rows != desired[1]:
            self.local_copies.configure(height=desired[1])

    def load_review_state(self):
        from .paper_registry import Registry
        return self.app.store.preference("reconciliation_choices", {}), Registry(self.app.store).latest_link_operation()

    def loaded_review_state(self, values):
        if self.window.winfo_exists():
            self.choices, self.undo_operation = values
            self.undo_button.configure(state="normal" if self.undo_operation else "disabled")
            self.render()

    @staticmethod
    def choice_key(row):
        import hashlib, json
        values = (row["id"], [(source.get("path", source.get("cloud_id", "")), source.get("digest", "")) for source in row.get("sources", [])])
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

    def state(self, row):
        sources = row.get("sources", [])
        same_paper = len(sources) >= 2 and all(source.get("paper_id") for source in sources) and len({source["paper_id"] for source in sources}) == 1
        if row.get("confidence") == "confirmed_link" or same_paper:
            return "Already linked"
        return "Kept separate" if self.choices.get(self.choice_key(row)) else "Needs review"

    def sort(self, column):
        self.sort_reverse = not self.sort_reverse if column == self.sort_column else False
        self.sort_column = column
        self.render()

    def render(self):
        if not hasattr(self, "tree") or not self.window.winfo_exists():
            return
        if self.checking:
            return
        selected = self.tree.selection()
        query = self.search.get().strip().casefold()
        rows = list(self.rows.values())
        self.tree.empty_label.configure(text="No findings match these filters." if rows else
                                        "No findings in this check." if hasattr(self, "checked_scope") else
                                        "Choose Check library to compare papers.")
        visible = [row for row in rows if (self.finding_type.get() == "All types" or row["kind"].replace("_", " ").capitalize() == self.finding_type.get())
                   and (self.review_state.get() == "All findings" or self.state(row) == self.review_state.get())
                   and (not query or query in (str(row.get("title", "")) + " " + row.get("reason", "") + " " + " ".join(row.get("local_paths", []))).casefold())]
        key = {"kind": "kind", "name": "title", "reason": "reason"}[self.sort_column]
        visible.sort(key=lambda row: (str(row.get(key, "")).casefold(), row["id"]), reverse=self.sort_reverse)
        self.app.update_rows(self.tree, [(row["id"], (row["kind"].replace("_", " ").capitalize(), row.get("title", ""), row.get("reason", ""))) for row in visible])
        for column, label in (("kind", "Finding"), ("name", "Paper / folder"), ("reason", "Explanation")):
            self.tree.heading(column, text=label + (" ▼" if self.sort_reverse else " ▲") if column == self.sort_column else label)
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
        self.selected()
        if rows:
            counts = {state: sum(self.state(row) == state for row in rows) for state in ("Needs review", "Already linked", "Kept separate")}
            self.feedback.set(f"{len(visible)} shown · {counts['Needs review']} need review · {counts['Already linked']} already linked · {counts['Kept separate']} kept separate. Comparisons use saved tablet information; no files were changed by the check.")

    def open_finding(self, row):
        if self.busy or self.checking:
            return
        self.tree.selection_set(row)
        self.tree.focus(row)
        self.selected()
        self.local_copies.focus_set()

    def open_copy(self, row):
        if self.busy or self.checking:
            return
        if row in self.copy_paths:
            self.app.open_file_or_folder(self.copy_paths[row])
        elif row in self.copy_sources:
            self.feedback.set("This is a saved tablet source. Sync its PDF first to open a local copy.")

    def open_pdf(self):
        path = self.selected_path()
        if path and Path(path).is_file() and Path(path).suffix.casefold() == ".pdf":
            self.app.open_path(path)

    def open_folder(self):
        if self.selected_path():
            path = Path(self.selected_path())
            self.app.open_path(str(path.parent if path.suffix.casefold() == ".pdf" else path))

    def selected_path(self):
        selection = self.local_copies.selection()
        return self.copy_paths.get(selection[0], "") if len(selection) == 1 else ""

    def selected_paths(self):
        return [self.copy_paths[key] for key in self.local_copies.selection() if key in self.copy_paths]

    def selected_sources(self):
        return [self.copy_sources[key] for key in self.local_copies.selection() if key in self.copy_sources]

    def copy_path(self):
        paths = self.selected_paths()
        if paths and not self.checking:
            self.local_copies.clipboard_clear()
            self.local_copies.clipboard_append("\n".join(paths))

    def copy_selected(self, event=None):
        if self.checking:
            self.open_actions()
            return
        selection = self.tree.selection()
        row = self.rows.get(selection[0], {}) if selection else {}
        text = row.get("reason", "")
        if self.selected_path():
            text += "\n\nSelected local copy: " + self.selected_path()
        elif self.local_copies.selection():
            text += f"\n\n{len(self.local_copies.selection())} copies selected."
        cloud_ids = row.get("cloud_ids", [])
        if cloud_ids:
            text += "\n" + "\n".join("Tablet ID: " + cloud_id for cloud_id in cloud_ids)
        self.details_display.set(text or self.action_detail or "Select a finding to inspect its files.", paths={"Selected local copy": (
            self.selected_path(), "This selected file belongs to the finding above. Only an explicitly confirmed Delete moves it to Recycle Bin.")}
            if self.selected_path() else {})
        self.open_actions()

    def open_actions(self):
        idle = not self.busy and not self.checking
        path = self.selected_path()
        available_pdf = bool(path and Path(path).is_file() and Path(path).suffix.casefold() == ".pdf")
        self.open_pdf_button.configure(state="normal" if available_pdf and idle else "disabled")
        self.open_folder_button.configure(state="normal" if path and idle else "disabled")
        self.local_path_copy.configure(state="normal" if self.selected_paths() and idle else "disabled")
        root = getattr(self, "checked_scope", "")
        paths = self.selected_paths()
        deletable = bool(root and paths and len(paths) == len(self.local_copies.selection()) and all(
            Path(value).is_file() and Path(value).suffix.casefold() == ".pdf"
            and Path(value).resolve().is_relative_to(Path(root).resolve()) for value in paths))
        self.delete_pdf_button.configure(state="normal" if deletable and idle
                                         and not self.check_button.instate(["disabled"]) else "disabled")
        selection = self.tree.selection()
        row = self.rows.get(selection[0], {}) if selection else {}
        self.link_button.configure(state="normal" if idle and len(self.selected_sources()) >= 2
                                   and len(self.selected_sources()) == len(self.local_copies.selection())
                                   and "link_papers" in row.get("actions", []) and self.state(row) == "Needs review" else "disabled")
        self.more_button.configure(state="normal" if idle else "disabled")
        self.update_more_menu()

    def delete_pdf(self):
        from .library_files import reviewed_pdf
        paths = self.selected_paths()
        if self.busy or self.checking or self.delete_pdf_button.instate(["disabled"]) or not paths:
            return
        selection = self.tree.selection()
        row = self.rows.get(selection[0], {}) if selection else {}
        sources = {os.path.normcase(os.path.abspath(source["path"])): source
                   for source in row.get("sources", []) if source.get("path")}
        root = getattr(self, "checked_scope", "")
        if not root:
            return
        self.busy = True
        self.selected()
        self.feedback.set("Checking the selected PDFs before deletion…")
        self.local_copies.set_status("Checking selected PDFs…")
        def failed(error):
            self.busy = False
            if self.window.winfo_exists():
                self.local_copies.set_status()
                self.feedback.set(str(error))
                self.selected()
        def checked(proofs):
            if not self.window.winfo_exists():
                self.busy = False
                return
            self.local_copies.set_status()
            def cancelled():
                self.busy = False
                self.feedback.set("Deletion cancelled. The selected PDFs were kept.")
                self.selected()
            def complete(result):
                self.busy = False
                self.app.service.command("export_pending")
                self.app.refresh()
                if self.window.winfo_exists():
                    self.local_copies.set_status()
                    if isinstance(result, str):
                        result = {"deleted": [result], "failed": []}
                    def refreshed(error):
                        count, failed_count = len(result["deleted"]), len(result["failed"])
                        text = f"Moved {count} {'PDF' if count == 1 else 'PDFs'} to Recycle Bin."
                        if failed_count:
                            text += f" {failed_count} {'file needs' if failed_count == 1 else 'files need'} attention."
                        self.feedback.set(text + " Saved notes and history were retained."
                                          + (f" Refresh failed: {error}" if error else ""))
                        if result["failed"]:
                            self.action_detail = "\n\n".join(item["path"] + "\n" + item["error"] for item in result["failed"])
                            self.copy_selected()
                    self.check(on_complete=refreshed)
            def execute():
                self.feedback.set("Moving selected PDFs to Recycle Bin…")
                self.local_copies.set_status("Moving selected PDFs to Recycle Bin…")
                action, values = ("recycle_pdf", proofs[0]) if len(proofs) == 1 else ("recycle_pdfs", proofs)
                background(self.app, lambda: self.app.service.storage_action(action, values), complete, failed,
                           task=f'Recycling {len(proofs)} reviewed PDF(s)…')
            warning = ("Saved annotations and history remain in this library. Other copies and tablet documents are kept. "
                       "Restore files from Recycle Bin to their original locations if needed.")
            if len(proofs) == 1:
                if messagebox.askokcancel("Delete selected local PDF", "Move this exact file to Windows Recycle Bin?\n\n"
                        + proofs[0]["path"] + "\n\n" + warning, parent=self.window, icon="warning"):
                    execute()
                else:
                    cancelled()
            else:
                self.confirm_copies("Delete selected local PDFs", f"Move these {len(proofs)} PDFs to Windows Recycle Bin?",
                                    [proof["path"] for proof in proofs], warning, "Move to Recycle Bin", execute, cancelled)
        def verify():
            return [reviewed_pdf(path, root, sources.get(os.path.normcase(os.path.abspath(path)), {}).get("digest", "")) for path in paths]
        background(self.app, verify, checked, failed, task='Verifying PDFs selected for removal…')

    def confirm_copies(self, title, prompt, labels, warning, action, execute, cancel):
        """Keep a large reviewed selection readable in one scrollable dialog."""
        confirm = self.confirmation = tk.Toplevel(self.window)
        confirm.title(title)
        confirm.configure(background=BACKGROUND)
        confirm.transient(self.window)
        frame = ttk.Frame(confirm, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=prompt, wraplength=700, style="Section.TLabel").pack(fill="x")
        listing = ReadOnlyText(frame, height=min(12, max(4, len(labels) * 2)), width=85,
                               value="\n\n".join(labels))
        listing.pack(fill="both", expand=True, pady=12)
        ttk.Label(frame, text=warning, wraplength=700).pack(fill="x", pady=(0, 12))
        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        def dismiss(callback):
            self.confirmation = None
            confirm.grab_release()
            confirm.destroy()
            callback()
        apply = Button(actions, text=action, command=lambda: dismiss(execute), style="Primary.TButton")
        apply.pack(side="right", padx=(8, 0))
        stop = Button(actions, text="Cancel", command=lambda: dismiss(cancel))
        stop.pack(side="right")
        Tooltip(apply, "Apply this action only to the exact selected copies listed above.")
        Tooltip(stop, "Cancel this action and keep the selected copies.")
        confirm.confirm_button, confirm.cancel_button, confirm.details = apply, stop, listing
        confirm.protocol("WM_DELETE_WINDOW", lambda: dismiss(cancel))
        bind_dialog_close(confirm, lambda: dismiss(cancel))
        fit_dialog(confirm, self.window)
        confirm.grab_set()
        stop.focus_set()

    def save_choice(self, separate):
        selection = self.tree.selection()
        row = self.rows.get(selection[0]) if selection else None
        if row is None or self.busy or self.checking:
            return
        key = self.choice_key(row)
        def saved():
            values = self.app.store.preference("reconciliation_choices", {})
            if separate:
                values[key] = True
            else:
                values.pop(key, None)
            self.app.store.set_preference("reconciliation_choices", values)
            return values
        self.busy = True
        self.selected()
        def complete(values):
            self.busy = False
            if self.window.winfo_exists():
                self.choices = values
                self.render()
        def failed(exc):
            self.busy = False
            if self.window.winfo_exists():
                self.feedback.set(str(exc))
                self.selected()
        background(self.app, saved, complete, failed, task='Saving the library review decision…')

    def undo(self):
        operation = getattr(self, "undo_operation", None)
        if not operation or self.busy or self.checking or not messagebox.askokcancel("Undo latest paper link", "Restore the separate paper relationships from the most recent link?\n\nOriginal PDFs, notes and annotation history are preserved.", parent=self.window):
            return
        self.busy = True
        self.selected()
        self.undo_button.configure(state="disabled")
        def complete(_):
            self.busy = False
            self.app.service.command("export_pending")
            self.app.refresh()
            if self.window.winfo_exists():
                self.undo_operation = None
                self.undo_button.configure(state="disabled")
                self.check()
        def failed(exc):
            self.busy = False
            if self.window.winfo_exists():
                self.feedback.set(str(exc))
                self.selected()
                self.undo_button.configure(state="normal")
        background(self.app, lambda: self.app.service.paper_identity_action("undo", operation["id"]), complete, failed, task='Undoing the last paper link…')

    def close(self):
        self.cancelled.set()
        if getattr(self, "layout_after", None) is not None:
            self.app.root.after_cancel(self.layout_after)
            self.layout_after = None
        self.window.destroy()

    def browse(self):
        folder = filedialog.askdirectory(parent=self.window, initialdir=self.scope.get() or None)
        if folder:
            self.scope.set(folder)

    def check(self, on_complete=None):
        from .reconciliation import scan_reconciliation
        if self.busy:
            return
        root = self.scope.get().strip()
        if not root:
            self.feedback.set("Choose the PC folder to compare.")
            return
        self.check_button.configure(state="disabled")
        self.action_detail = ""
        self.checking = True
        self.set_review_status("Checking library…")
        self.open_actions()
        self.scan_generation += 1
        generation = self.scan_generation
        self.feedback.set("Comparing papers and saved tablet sources…")
        config = self.app.cloud_config()
        def scanned(rows):
            if not self.window.winfo_exists() or generation != self.scan_generation:
                return
            self.checking = False
            self.checked_scope = root
            self.set_review_status()
            self.rows = {str(row["id"]): row for row in rows}
            self.tree.empty_label.configure(text="No findings in this check.")
            self.type_filter.configure(values=["All types"] + sorted({row["kind"].replace("_", " ").capitalize() for row in rows}))
            self.render()
            if not rows:
                self.feedback.set("No findings in this check. Saved tablet information may be incomplete.")
            self.check_button.configure(state="normal")
            self.open_actions()
            if on_complete:
                on_complete(None)
        def failed(exc):
            if self.window.winfo_exists() and generation == self.scan_generation:
                self.checking = False
                self.set_review_status()
                if not self.rows:
                    self.tree.set_status("Library check failed. See the message above.")
                    self.local_copies.set_status("Library check failed.")
                self.feedback.set(str(exc))
                self.check_button.configure(state="normal")
                self.selected()
                if on_complete:
                    on_complete(exc)
        background(self.app, lambda: scan_reconciliation(self.app.store, config, self.cancelled.is_set, local_root=root,
                   inspect_pdf=self.app.pdf_worker.inspect), scanned, failed, task='Finishing library reconciliation…')

    def set_review_status(self, message=None):
        self.tree.set_status(message)
        self.local_copies.set_status(message)
        if message:
            self.details_display.set(message)
        self.selected()

    def selected(self, event=None):
        if self.checking:
            for button in (self.keep_button, self.again_button, self.link_button, self.map_button, self.send_button):
                button.configure(state="disabled")
            self.open_actions()
            return
        selection = self.tree.selection()
        row = self.rows.get(selection[0], {}) if selection else {}
        sources = row.get("sources", [])
        paths = row.get("local_paths", [])
        finding = selection[0] if selection else None
        self.local_copies.empty_label.configure(text="This finding has no paper copies." if row else
                                                "Select a finding to see its copies.")
        previous = {("local", self.copy_paths[key]) if key in self.copy_paths else
                    ("cloud", self.copy_sources.get(key, {}).get("cloud_id", ""))
                    for key in self.local_copies.selection()}
        source_paths = {os.path.normcase(os.path.abspath(source["path"])): source for source in sources if source.get("path")}
        self.copy_paths = {str(number): path for number, path in enumerate(paths)}
        self.copy_sources = {key: source_paths[os.path.normcase(os.path.abspath(path))]
                             for key, path in self.copy_paths.items() if os.path.normcase(os.path.abspath(path)) in source_paths}
        copies = [(key, (Path(path).name, str(Path(path).parent),
                              "Available" if Path(path).is_file() else "Folder" if Path(path).is_dir() else "Missing"))
                              for key, path in self.copy_paths.items()]
        for source in sources:
            if source.get("cloud_id"):
                key = "cloud:" + source["cloud_id"]
                self.copy_sources[key] = source
                copies.append((key, (source.get("title") or "Tablet copy", "Tablet ID: " + source["cloud_id"], "Saved tablet")))
        self.app.update_rows(self.local_copies, copies)
        selected = [key for key, _ in copies if (("local", self.copy_paths[key]) if key in self.copy_paths else
                    ("cloud", self.copy_sources[key]["cloud_id"])) in previous] if finding == self.copy_finding else (
                        [copies[0][0]] if copies else [])
        self.copy_finding = finding
        self.local_copies.selection_set(selected)
        if selected:
            self.local_copies.focus(selected[0])
        self.copy_selected()
        self.keep_button.configure(state="normal" if row and self.state(row) == "Needs review" and not self.busy else "disabled")
        self.again_button.configure(state="normal" if row and self.state(row) == "Kept separate" and not self.busy else "disabled")
        enabled = self.app.cloud_config()["integration_enabled"]
        self.map_button.configure(state="normal" if enabled and len(row.get("folder_ids", [])) == 1 and "review_mapping" in row.get("actions", []) and not self.busy else "disabled")
        self.send_button.configure(state="normal" if enabled and len(row.get("local_paths", [])) == 1 and "review_upload" in row.get("actions", []) and not self.busy else "disabled")
        self.review_actions.set_visible(self.map_button, len(row.get("folder_ids", [])) == 1 and "review_mapping" in row.get("actions", []))
        self.review_actions.set_visible(self.send_button, len(row.get("local_paths", [])) == 1 and "review_upload" in row.get("actions", []))
        self.update_more_menu()

    def map_folder(self):
        if self.busy or self.checking:
            return
        selection = self.tree.selection()
        row = self.rows.get(selection[0], {}) if selection else {}
        if self.app.cloud_config()["integration_enabled"] and len(row.get("folder_ids", [])) == 1:
            self.app.set_cloud_mapping(row["folder_ids"][0], parent=self.window)

    def send(self):
        if self.busy or self.checking:
            return
        selection = self.tree.selection()
        row = self.rows.get(selection[0], {}) if selection else {}
        if len(row.get("local_paths", [])) == 1:
            self.app.send_pdf_path(row["local_paths"][0], parent=self.window)

    def link(self):
        selection = self.tree.selection()
        row = self.rows.get(selection[0], {}) if selection else {}
        sources = self.selected_sources()
        if self.busy or self.checking or len(sources) < 2 or len(sources) != len(self.local_copies.selection()) or "link_papers" not in row.get("actions", []) or self.state(row) != "Needs review":
            return
        prompt = f"Link these {len(sources)} selected sources as the same paper?"
        labels = [source.get("path") or "Tablet ID: " + source.get("cloud_id", "") for source in sources]
        warning = "Previously linked copies remain together. Files and independent notes are retained."
        def linked():
            return self.app.service.paper_identity_action("link", sources)
        def saved(_):
            self.busy = False
            self.app.service.command("export_pending")
            self.app.refresh()
            if self.window.winfo_exists():
                self.feedback.set("Paper identities linked. Original files and annotations are retained.")
                background(self.app, self.load_review_state, self.loaded_review_state, task='Refreshing linked-paper details…')
                self.check()
        def failed(exc):
            self.busy = False
            if self.window.winfo_exists():
                self.feedback.set(str(exc))
                self.selected()
                from .citations import CitationConflict
                if isinstance(exc, CitationConflict):
                    from .research_ui import review_citation_conflict
                    def choose(record):
                        self.busy = True
                        self.selected()
                        background(self.app, lambda: self.app.service.paper_identity_action(
                            "link", {"sources": sources, "citation": record}), saved, failed, task='Saving reviewed paper links…')
                    review_citation_conflict(self.app, exc.records, choose)
        def execute():
            self.busy = True
            self.selected()
            background(self.app, linked, saved, failed, task='Linking the reviewed paper copies…')
        if len(sources) > 6:
            self.busy = True
            self.selected()
            def cancelled():
                self.busy = False
                self.selected()
            self.confirm_copies("Link paper copies", prompt, labels, warning, "Link selected copies…", execute, cancelled)
        elif messagebox.askokcancel("Link paper copies", prompt + "\n\n" + "\n".join(labels) + "\n\n" + warning, parent=self.window):
            execute()
