"""Review-first literature workflows, using background work outside Tk."""
from pathlib import Path
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .icons import Button, icon
from .theme import BACKGROUND
from .widgets import Tooltip, PathField, ReadOnlyText, ScrollFrame, WrapToolbar, annotate_buttons, bind_dialog_close


def background(app, function, success, error=None):
    """Callbacks are drained by App.poll on the Tk thread."""
    future = app.workflow_executor.submit(function)
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
        ttk.Label(parent, text="Incoming documents", style="Section.TLabel").pack(anchor="w", pady=(0, 10))
        toolbar = WrapToolbar(parent)
        toolbar.pack(fill="x", pady=(0, 12))
        setup = Button(toolbar, text="Set up Inbox…", command=lambda: app.setup_inbox())
        Tooltip(setup, "Choose incoming documents and library folders directly in Sorting settings.")
        more = app.more_button(toolbar, [("Filing recovery…", app.filing_recovery), ("Review library…", app.review_library)])
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
        toolbar.add(setup)
        self.summary = tk.StringVar(value="Choose an inbox and library in Settings → Sorting, or import your sorter settings.")
        summary = ttk.Label(parent, textvariable=self.summary, style="Muted.TLabel", wraplength=900)
        summary.pack(fill="x", pady=(0, 12))
        summary.bind("<Configure>", lambda event: summary.configure(wraplength=max(120, event.width)))
        Tooltip(summary, lambda: self.summary.get())
        locations = ttk.Frame(parent)
        locations.pack(fill="x", pady=(0, 10))
        self.location_variables = {}
        for index, (key, label) in enumerate((("watch_folder", "Inbox"), ("library_root", "Library"))):
            column = index * 3
            ttk.Label(locations, text=label).grid(row=0, column=column, padx=(0 if index == 0 else 16, 8))
            variable = self.location_variables[key] = tk.StringVar()
            entry = ttk.Entry(locations, textvariable=variable, state="readonly", width=1)
            entry.grid(row=0, column=column+1, sticky="ew")
            locations.columnconfigure(column+1, weight=1)
            access = PathField(entry, "Incoming documents wait here for review." if key == "watch_folder" else "Reviewed documents are filed inside this library root.")
            access.add_copy_button(locations).grid(row=0, column=column+2, padx=(6, 0))
        pane = ttk.Panedwindow(parent, orient="horizontal")
        pane.pack(fill="both", expand=True)
        listing = ttk.Frame(pane, width=440)
        pane.add(listing, weight=1)
        controls = WrapToolbar(listing)
        controls.pack(fill="x", pady=(0, 8))
        self.review_button = Button(controls, text="Review selected", command=self.review, style="Primary.TButton")
        controls.add(self.review_button)
        Tooltip(self.review_button, "Identify the selected finished document using your naming settings, then suggest an editable filename. Review the name and destination before filing; this action does not move or upload the document.")
        self.skip_button = Button(controls, text="Skip", command=self.skip)
        controls.add(self.skip_button)
        Tooltip(self.skip_button, "Leave this document in the inbox and set it aside until its contents change.")
        self.retry_button = Button(controls, text="Retry lookup", command=lambda: self.review(force=True))
        controls.add(self.retry_button)
        Tooltip(self.retry_button, "Available after a Gemini identification failure. Try the lookup again using your current naming permissions. A filename you edited is kept; the new metadata appears below.")
        self.tree = app.tree(listing, [("name", "Document", 265), ("state", "Status", 150)], content_columns=(), empty_text="No incoming documents")
        self.tree.bind("<<TreeviewSelect>>", self.selected)
        self.tree.bind("<Double-1>", lambda _: self.review())
        self.tree.tooltip.value = lambda row, column: row if column == "name" else self.tree.set(row, column)
        self.tree.tooltip.extra = self.item_help
        self.editor_form = ScrollFrame(pane, width=490, height=1, padding=(16, 0, 0, 0))
        editor = self.editor_form.content
        pane.add(self.editor_form, weight=1)
        editor_heading = ttk.Label(editor, text="Review filename & destination", style="Section.TLabel")
        editor_heading.pack(fill="x", pady=(0, 12))
        editor_heading.bind("<Configure>", lambda event: editor_heading.configure(wraplength=max(100, event.width)))
        self.original = tk.StringVar(value="Select a document in the inbox.")
        original_row = ttk.Frame(editor)
        original_row.pack(fill="x", pady=(0, 12))
        self.original_label = original_label = ttk.Label(original_row, textvariable=self.original, width=1)
        original_label.pack(side="left", fill="x", expand=True)
        original_access = PathField(original_label, "This is the original document in the inbox. Naming and filing keep its document type.",
            value=lambda: self.original.get() if self.original.get() != "Select a document in the inbox." else "")
        self.original_path_copy = original_access.add_copy_button(original_row)
        self.original_path_copy.pack(side="left", padx=(8, 0))
        ttk.Label(editor, text="Filename").pack(anchor="w")
        self.filename = tk.StringVar()
        self.name_entry = ttk.Entry(editor, textvariable=self.filename)
        self.name_entry.pack(fill="x", pady=(4, 10))
        Tooltip(self.name_entry, lambda: (self.filename.get() + "\n\n" if self.filename.get() else "") +
            "Edit the filename only, without a folder path. The source .pdf, .docx, .ppt, or .pptx extension is kept and added if omitted. Existing destination files are never overwritten.")
        ttk.Label(editor, text="Destination folder").pack(anchor="w")
        destination = ttk.Frame(editor)
        destination.pack(fill="x", pady=(4, 12))
        self.destination = tk.StringVar()
        self.destination_entry = ttk.Entry(destination, textvariable=self.destination)
        self.destination_entry.pack(side="left", fill="x", expand=True)
        destination_access = PathField(self.destination_entry, "Choose a destination inside your library root. You can type a new subfolder path; it is created only when you file the document. The destination must be outside the inbox and app cache areas.")
        self.destination_path_copy = destination_access.add_copy_button(destination)
        self.destination_path_copy.pack(side="left", padx=(8, 0))
        destination_browse = Button(destination, text="Browse…", command=self.choose_destination)
        destination_browse.pack(side="left", padx=(8, 0))
        Tooltip(destination_browse, "Choose the destination folder for the reviewed document.")
        self.file_button = Button(editor, text="File document", command=self.file_document, style="Primary.TButton")
        self.file_button.pack(anchor="w", pady=(0, 10))
        Tooltip(self.file_button, "Confirm the name and destination, then move this document from the inbox into your library. Existing files are never overwritten. Only PDFs enter note analysis or an enabled tablet upload queue; Word and PowerPoint stay local.")
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
        if hasattr(app.root, "drop_target_register"):
            from tkinterdnd2 import DND_FILES
            self.tree.drop_target_register(DND_FILES)
            self.tree.dnd_bind("<<Drop>>", self.drop)

    def config(self):
        return self.app.inbox.config()

    def item_help(self, row, column):
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
        background(self.app, checked, self.refreshed, self.failed)

    def load_rows(self):
        if self.busy or self.app.closing:
            return
        self.busy = True
        background(self.app, self.app.inbox.list_items, self.refreshed, self.failed)

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
        if path != self.review_path or invalid:
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
        background(self.app, identify, prepared, self.failed)

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
        background(self.app, lambda: self.app.inbox.file_item(path, name, destination, expected_signature=reviewed_signature), filed, self.failed)

    def skip(self):
        selection = self.tree.selection()
        if selection and not self.busy:
            path = selection[0]
            self.busy = True
            self.update_controls()
            background(self.app, lambda: self.app.inbox.skip(path), self.mutated, self.failed)

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
        background(self.app, lambda: self.app.inbox.add_files(paths), self.mutated, self.failed)

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
        background(self.app, check, completed, lambda error: completed(str(error)))

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
                   lambda exc: self.help.set(str(exc)) if self.parent.winfo_exists() else None)


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
        self.cancelled = __import__("threading").Event()
        self.window = window = tk.Toplevel(app.root)
        window.title("Review duplicates & folder mismatches")
        window.configure(background=BACKGROUND)
        window.geometry("1000x700")
        window.transient(app.root)
        bind_dialog_close(window, self.close)
        self.scope = tk.StringVar(value=app.cloud_config().get("pc_root") or app.inbox.config().get("library_root", ""))
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Compare your library before changing it", style="Section.TLabel").pack(anchor="w")
        introduction = ttk.Label(frame, text="Find duplicates and differences using local files and the last downloaded tablet information. Different notes and files stay preserved.",
                  wraplength=900, style="Muted.TLabel")
        introduction.pack(fill="x", pady=(8, 12))
        introduction.bind("<Configure>", lambda event: introduction.configure(wraplength=max(80, event.width)))
        scope = ttk.Frame(frame)
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
        search.pack(side="left", fill="x", expand=True)
        Tooltip(self.type_filter, "Show one kind of finding, such as identical local copies or folder differences.")
        Tooltip(state, "Separate items still needing a decision from existing links and copies you chose to keep separate.")
        Tooltip(search, "Search paper names, explanations and file locations in these findings.")
        for variable in (self.finding_type, self.review_state, self.search):
            variable.trace_add("write", lambda *_: self.render())
        self.tree = app.tree(frame, [("kind", "Finding", 180), ("name", "Paper / folder", 290), ("reason", "Explanation", 450)], content_columns=())
        for column in ("kind", "name", "reason"):
            self.tree.heading(column, command=lambda key=column: self.sort(key))
        self.tree.bind("<<TreeviewSelect>>", self.selected)
        self.details_display = ReadOnlyText(frame, height=7)
        self.details_display.pack(fill="x", pady=10)
        self.details = self.details_display.text
        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        self.paths = ttk.Combobox(actions, state="disabled")
        self.paths.pack(side="left", fill="x", expand=True)
        self.paths.bind("<<ComboboxSelected>>", lambda _: self.open_actions())
        self.open_pdf_button = Button(actions, text="Open PDF", command=self.open_pdf, state="disabled")
        self.open_pdf_button.pack(side="left", padx=8)
        self.open_folder_button = Button(actions, text="Open containing folder", command=self.open_folder, state="disabled")
        self.open_folder_button.pack(side="left")
        local_path_access = PathField(self.paths, "Choose the local copy you want to inspect. Linking copies does not remove these files.")
        self.local_path_copy = local_path_access.add_copy_button(actions)
        self.local_path_copy.pack(side="left", padx=(8, 0), before=self.open_pdf_button)
        Tooltip(self.open_pdf_button, "Open the chosen local PDF to inspect its contents and annotations.")
        Tooltip(self.open_folder_button, "Open the folder containing the chosen copy in File Explorer.")
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(8, 0))
        self.link_button = Button(actions, text="Link selected copies…", command=self.link, state="disabled")
        self.link_button.pack(side="left")
        Tooltip(self.link_button, "Confirm that these sources are the same paper. Previously linked copies remain together under one paper entry and notebook heading; actual files, annotation history and independent notes are retained. Only proven inherited text marks appear once.")
        self.map_button = Button(actions, text="Map and sync…", command=self.map_folder, state="disabled")
        self.map_button.pack(side="left", padx=8)
        Tooltip(self.map_button, "Link the selected tablet folder to an existing PC folder, then sync enabled transfers. Different folder names can remain linked.")
        self.send_button = Button(actions, text="Send selected PDF…", command=self.send, state="disabled")
        self.send_button.pack(side="left")
        Tooltip(self.send_button, "Review an explicit transfer of this existing PDF. Enable reMarkable PDF transfers in Connections first.")
        decisions = ttk.Frame(frame)
        decisions.pack(fill="x", pady=(8, 0))
        self.keep_button = Button(decisions, text="Keep separate", command=lambda: self.save_choice(True), state="disabled")
        self.keep_button.pack(side="left")
        self.again_button = Button(decisions, text="Review again", command=lambda: self.save_choice(False), state="disabled")
        self.again_button.pack(side="left", padx=8)
        self.undo_button = Button(decisions, text="Undo last link…", command=self.undo, state="disabled")
        self.undo_button.pack(side="left")
        Tooltip(self.keep_button, "Remember that these copies or folders should stay separate. No files or notes are removed.")
        Tooltip(self.again_button, "Clear your Keep separate decision and return this finding to review.")
        Tooltip(self.undo_button, "Restore the paper relationships from the latest link made by this version. Original files and notes stay preserved.")
        background(app, self.load_review_state, self.loaded_review_state)
        close = Button(actions, text="Close", command=self.close)
        close.pack(side="right")
        Tooltip(close, "Close this review and cancel its unfinished scan. Confirmed links remain saved.")
        window.protocol("WM_DELETE_WINDOW", self.close)
        annotate_buttons(window)

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
        selected = self.tree.selection()
        query = self.search.get().strip().casefold()
        rows = list(self.rows.values())
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

    def open_pdf(self):
        if self.paths.get():
            self.app.open_path(self.paths.get())

    def open_folder(self):
        if self.paths.get():
            path = Path(self.paths.get())
            self.app.open_path(str(path.parent if path.suffix.casefold() == ".pdf" else path))

    def open_actions(self):
        path = self.paths.get()
        self.open_pdf_button.configure(state="normal" if path and Path(path).suffix.casefold() == ".pdf" else "disabled")
        self.open_folder_button.configure(state="normal" if path else "disabled")

    def save_choice(self, separate):
        selection = self.tree.selection()
        row = self.rows.get(selection[0]) if selection else None
        if row is None or self.busy:
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
        background(self.app, saved, complete, failed)

    def undo(self):
        operation = getattr(self, "undo_operation", None)
        if not operation or self.busy or not messagebox.askokcancel("Undo latest paper link", "Restore the separate paper relationships from the most recent link?\n\nOriginal PDFs, notes and annotation history are preserved.", parent=self.window):
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
        background(self.app, lambda: self.app.service.paper_identity_action("undo", operation["id"]), complete, failed)

    def close(self):
        self.cancelled.set()
        self.window.destroy()

    def browse(self):
        folder = filedialog.askdirectory(parent=self.window, initialdir=self.scope.get() or None)
        if folder:
            self.scope.set(folder)

    def check(self):
        from .reconciliation import scan_reconciliation
        root = self.scope.get().strip()
        if not root:
            self.feedback.set("Choose the PC folder to compare.")
            return
        self.check_button.configure(state="disabled")
        self.scan_generation += 1
        generation = self.scan_generation
        self.feedback.set("Comparing papers and saved tablet sources…")
        config = self.app.cloud_config()
        self.checked_scope = root
        def scanned(rows):
            if not self.window.winfo_exists() or generation != self.scan_generation:
                return
            self.rows = {str(row["id"]): row for row in rows}
            self.type_filter.configure(values=["All types"] + sorted({row["kind"].replace("_", " ").capitalize() for row in rows}))
            self.render()
            if not rows:
                self.feedback.set("No findings in this check. Saved tablet information may be incomplete.")
            self.check_button.configure(state="normal")
        def failed(exc):
            if self.window.winfo_exists() and generation == self.scan_generation:
                self.feedback.set(str(exc))
                self.check_button.configure(state="normal")
        background(self.app, lambda: scan_reconciliation(self.app.store, config, self.cancelled.is_set, local_root=root,
                   inspect_pdf=self.app.pdf_worker.inspect), scanned, failed)

    def selected(self, event=None):
        selection = self.tree.selection()
        row = self.rows.get(selection[0], {}) if selection else {}
        text = row.get("reason", "") + "\n\n" + "\n".join(row.get("local_paths", []))
        text += "\n" + "\n".join("Tablet ID: " + cloud_id for cloud_id in row.get("cloud_ids", []))
        self.details_display.set(text, paths={f"Local copy {number}": (path,
            "This local copy is part of the selected finding. Linking copies does not remove it.")
            for number, path in enumerate(row.get("local_paths", []), start=1)})
        sources = row.get("sources", [])
        paths = row.get("local_paths", [])
        previous = self.paths.get()
        self.paths.configure(values=paths, state="readonly" if paths else "disabled")
        self.paths.set(previous if previous in paths else paths[0] if paths else "")
        self.paths.path_access.refresh()
        self.open_actions()
        self.keep_button.configure(state="normal" if row and self.state(row) == "Needs review" and not self.busy else "disabled")
        self.again_button.configure(state="normal" if row and self.state(row) == "Kept separate" and not self.busy else "disabled")
        self.link_button.configure(state="normal" if len(sources) >= 2 and "link_papers" in row.get("actions", []) and self.state(row) == "Needs review" and not self.busy else "disabled")
        enabled = self.app.cloud_config()["integration_enabled"]
        self.map_button.configure(state="normal" if enabled and len(row.get("folder_ids", [])) == 1 and "review_mapping" in row.get("actions", []) and not self.busy else "disabled")
        self.send_button.configure(state="normal" if enabled and len(row.get("local_paths", [])) == 1 and "review_upload" in row.get("actions", []) and not self.busy else "disabled")

    def map_folder(self):
        if self.busy:
            return
        selection = self.tree.selection()
        row = self.rows.get(selection[0], {}) if selection else {}
        if self.app.cloud_config()["integration_enabled"] and len(row.get("folder_ids", [])) == 1:
            self.app.set_cloud_mapping(row["folder_ids"][0])

    def send(self):
        if self.busy:
            return
        selection = self.tree.selection()
        row = self.rows.get(selection[0], {}) if selection else {}
        if len(row.get("local_paths", [])) == 1:
            self.app.send_pdf_path(row["local_paths"][0], parent=self.window)

    def link(self):
        selection = self.tree.selection()
        row = self.rows.get(selection[0], {}) if selection else {}
        sources = row.get("sources", [])
        if self.busy or len(sources) < 2 or "link_papers" not in row.get("actions", []) or self.state(row) != "Needs review":
            return
        if not messagebox.askokcancel("Link paper copies", "Confirm these sources are the same paper?\n\nTheir previously linked copies will remain together. Files and independent notes are retained under one paper entry and notebook heading.", parent=self.window):
            return
        self.link_button.configure(state="disabled")
        self.busy = True
        self.selected()
        def linked():
            return self.app.service.paper_identity_action("link", sources)
        def saved(_):
            self.busy = False
            self.app.service.command("export_pending")
            self.app.refresh()
            if self.window.winfo_exists():
                self.feedback.set("Paper identities linked. Original files and annotations are retained.")
                background(self.app, self.load_review_state, self.loaded_review_state)
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
                            "link", {"sources": sources, "citation": record}), saved, failed)
                    review_citation_conflict(self.app, exc.records, choose)
        background(self.app, linked, saved, failed)
