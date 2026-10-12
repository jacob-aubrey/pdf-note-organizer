"""Citation editing and supplementary-file review for a selected library paper."""
from pathlib import Path
import re
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from urllib.parse import unquote, urlsplit
import webbrowser

from .citations import FIELDS, citation_for, citation_text, lookup_citation, save_citation
from .supplements import find_supplements, download_supplement, attach_file, attachments, EXTENSIONS
from .icons import Button
from .theme import BACKGROUND
from .widgets import Tooltip, ReadOnlyText, PathField, bind_dialog_close, fit_dialog, annotate_buttons
from .workflow_ui import background


class CitationWindow:
    def __init__(self, app, document_id):
        self.app, self.document_id = app, document_id
        self.window = window = tk.Toplevel(app.root)
        window.title("Citation details")
        window.configure(background=BACKGROUND)
        window.transient(app.root)
        bind_dialog_close(window, window.destroy)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        self.fields, self.inputs = {}, []
        for row, (key, label) in enumerate(FIELDS):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
            variable = self.fields[key] = tk.StringVar()
            entry = ttk.Entry(frame, textvariable=variable, width=60, state="disabled")
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            self.inputs.append(entry)
            Tooltip(entry, "Review or edit this citation field. Author names use semicolons between authors; commas can remain inside a name.")
        self.status = tk.StringVar(value="Loading citation…")
        ttk.Label(frame, textvariable=self.status, wraplength=650, style="Muted.TLabel").grid(
            row=len(FIELDS), column=0, columnspan=2, sticky="w", pady=12)
        controls = ttk.Frame(frame)
        controls.grid(row=len(FIELDS)+1, column=0, columnspan=2, sticky="ew")
        self.lookup = Button(controls, text="Look up DOI", command=self.look_up, state="disabled")
        self.lookup.pack(side="left")
        Tooltip(self.lookup, "Send only this DOI to Crossref/DataCite and fill available citation fields for your review. Save citation keeps your edits; Cancel discards them.")
        self.copy = Button(controls, text="Copy citation", command=self.copy_text, state="disabled")
        self.copy.pack(side="left", padx=8)
        Tooltip(self.copy, "Copy the current fields as a plain-text reference. This does not save draft edits.")
        self.save = Button(controls, text="Save citation", command=self.save_record, style="Primary.TButton", state="disabled")
        self.save.pack(side="right")
        Tooltip(self.save, "Save these reviewed details with this paper and its linked sources. PDF rescans keep your citation edits.")
        cancel = Button(controls, text="Cancel", command=window.destroy)
        cancel.pack(side="right", padx=8)
        Tooltip(cancel, "Close without saving draft citation changes.")
        annotate_buttons(window)
        fit_dialog(window, app.root)
        background(app, lambda: citation_for(app.store, document_id), self.loaded, self.failed)

    def alive(self):
        return not self.app.closing and self.window.winfo_exists()

    def busy(self, busy):
        for widget in self.inputs + [self.lookup, self.copy, self.save]:
            widget.configure(state="disabled" if busy else "normal")

    def fill(self, record):
        for key, variable in self.fields.items():
            value = record.get(key, "")
            variable.set("; ".join(value) if key == "authors" else value)

    def draft(self):
        return {key: variable.get() for key, variable in self.fields.items()}

    def loaded(self, record):
        if not self.alive():
            return
        self.fill(record)
        self.busy(False)
        self.status.set("Review the details before saving or exporting. DOI lookup is optional and sends only the identifier.")

    def failed(self, error):
        if self.alive():
            self.busy(False)
            self.status.set(str(error))

    def look_up(self):
        doi = self.fields["doi"].get()
        self.busy(True)
        self.status.set("Looking up DOI…")
        def found(record):
            if not self.alive():
                return
            # An optional lookup is a draft; nothing is saved automatically.
            self.fill({**self.draft(), **{key: value for key, value in record.items() if value}})
            self.busy(False)
            self.status.set("DOI details loaded. Check that they describe this paper, then Save citation.")
        background(self.app, lambda: lookup_citation(doi), found, self.failed)

    def copy_text(self):
        try:
            text = citation_text(self.draft())
            self.window.clipboard_clear()
            self.window.clipboard_append(text)
            self.status.set("Citation copied as plain text.")
        except (ValueError, tk.TclError) as exc:
            self.status.set(str(exc))

    def save_record(self):
        record = self.draft()
        self.busy(True)
        self.status.set("Saving citation…")
        def saved(result):
            self.app.notify("Citation saved.", "notes" if self.app.tabs.select() == str(self.app.notes_tab) else "library")
            self.app.query_signature = None
            self.app.refresh_notes()
            if self.alive():
                self.window.destroy()
        background(self.app, lambda: save_citation(self.app.store, self.document_id, record), saved, self.failed)


class SupplementsWindow:
    def __init__(self, app, document_id, paper_path):
        self.app, self.document_id, self.paper_path = app, document_id, Path(paper_path)
        self.cancelled = threading.Event()
        self.links, self.saved, self.landing = [], [], ""
        self.window = window = tk.Toplevel(app.root)
        window.title("Supplementary files — " + self.paper_path.stem)
        window.configure(background=BACKGROUND)
        window.transient(app.root)
        bind_dialog_close(window, window.destroy)
        window.bind("<Destroy>", lambda event: self.cancelled.set() if event.widget == window else None, add="+")
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Find files linked by the PDF, DOI metadata, or publisher page. Review a link before downloading.",
                  wraplength=760).pack(anchor="w", pady=(0, 10))
        self.tree = self.scroll_table(frame, columns=("label", "source", "url"), show="headings", height=7)
        for key, label, width in (("label", "Candidate file", 260), ("source", "Found in", 140), ("url", "Link", 360)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width)
        self.tree.bind("<<TreeviewSelect>>", self.selection_changed)
        self.selected_url = tk.StringVar()
        link_field = ttk.Entry(frame, textvariable=self.selected_url, state="readonly")
        link_field.pack(fill="x", pady=(6, 0))
        Tooltip(link_field, lambda: self.selected_url.get() or "Select a candidate to inspect or copy its full URL.")
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=10)
        self.find = Button(actions, text="Find files", command=self.discover)
        self.find.pack(side="left")
        Tooltip(self.find, "Inspect PDF hyperlinks locally and request this paper's DOI metadata and publisher page. No PDF or note text is uploaded.")
        self.open = Button(actions, text="Open selected link", command=self.open_link, state="disabled")
        self.open.pack(side="left", padx=8)
        Tooltip(self.open, "Open this candidate in your browser. Publisher access or a manual file download may be needed.")
        self.download = Button(actions, text="Download selected…", command=self.download_selected, state="disabled")
        self.download.pack(side="left")
        Tooltip(self.download, "Choose a new filename and download this file, up to 100 MB. Existing files are preserved; HTML pages cannot be saved as supplementary PDFs.")
        self.article = Button(actions, text="Open article", command=lambda: webbrowser.open(self.landing), state="disabled")
        self.article.pack(side="left", padx=8)
        Tooltip(self.article, "Open the article's publisher page in your browser to look for supplementary files when automatic discovery is incomplete.")
        ttk.Label(frame, text="Attached files", style="Section.TLabel").pack(anchor="w", pady=(8, 6))
        self.attached = self.scroll_table(frame, columns=("path",), show="headings", height=4)
        self.attached.heading("path", text="File location")
        self.attached.column("path", width=760)
        self.attached.bind("<<TreeviewSelect>>", self.selection_changed)
        path_row = ttk.Frame(frame)
        path_row.pack(fill="x", pady=(6, 0))
        self.attached_path = tk.StringVar()
        path_entry = ttk.Entry(path_row, textvariable=self.attached_path, state="readonly")
        path_entry.pack(side="left", fill="x", expand=True)
        self.path_access = PathField(path_entry, "The selected supplementary file stays at this location.")
        self.path_access.add_copy_button(path_row).pack(side="right", padx=(6, 0))
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=10)
        add = Button(controls, text="Add file…", command=self.add_file)
        add.pack(side="left")
        Tooltip(add, "Attach an already downloaded supplementary file to this paper. The file stays in its existing location.")
        self.open_file = Button(controls, text="Open containing folder", command=self.open_attachment, state="disabled")
        self.open_file.pack(side="left", padx=8)
        Tooltip(self.open_file, "Open the folder containing the selected attachment so you can inspect the saved file.")
        close = Button(controls, text="Close", command=window.destroy)
        close.pack(side="right")
        Tooltip(close, "Close this supplementary-file review. A pending download is stopped before publishing its completed file.")
        self.status = tk.StringVar(value="Choose Find files, or attach a file you already downloaded.")
        status = ReadOnlyText(frame, textvariable=self.status, height=4, width=80)
        status.pack(fill="x")
        annotate_buttons(window)
        fit_dialog(window, app.root)
        self.refresh_attached()

    @staticmethod
    def scroll_table(parent, **options):
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        tree = ttk.Treeview(container, **options)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)
        return tree

    def alive(self):
        return not self.app.closing and self.window.winfo_exists()

    def failed(self, error):
        if self.alive():
            self.find.configure(state="normal")
            self.downloading = False
            self.selection_changed()
            self.status.set(str(error))

    def selection_changed(self, event=None):
        selected = bool(self.tree.selection())
        self.open.configure(state="normal" if selected else "disabled")
        self.download.configure(state="normal" if selected and not getattr(self, "downloading", False) else "disabled")
        self.open_file.configure(state="normal" if self.attached.selection() else "disabled")
        self.article.configure(state="normal" if self.landing else "disabled")
        self.selected_url.set(self.links[int(self.tree.selection()[0])]["url"] if selected else "")
        self.attached_path.set(self.saved[int(self.attached.selection()[0])]["path"] if self.attached.selection() else "")
        self.path_access.refresh()

    def discover(self):
        self.find.configure(state="disabled")
        self.status.set("Checking PDF links, DOI metadata, and publisher page…")
        def found(result):
            if not self.alive():
                return
            self.links, warnings, self.landing = result
            self.tree.delete(*self.tree.get_children())
            for i, link in enumerate(self.links):
                self.tree.insert("", "end", iid=str(i), values=(link["label"], link["source"], link["url"]))
            self.find.configure(state="normal")
            self.selection_changed()
            self.status.set((f"{len(self.links)} candidate link(s). Review before downloading." if self.links else
                             "No supplementary links found. You can download files in your browser and use Add file….") +
                            ("\n" + "\n".join(warnings) if warnings else ""))
        background(self.app, lambda: find_supplements(self.app.store, self.app.pdf_worker, self.document_id), found, self.failed)

    def open_link(self):
        if self.tree.selection():
            webbrowser.open(self.links[int(self.tree.selection()[0])]["url"])

    def refresh_attached(self):
        def loaded(rows):
            if not self.alive():
                return
            self.saved = rows
            self.attached.delete(*self.attached.get_children())
            for i, row in enumerate(rows):
                self.attached.insert("", "end", iid=str(i), values=(row["path"],))
            self.selection_changed()
        background(self.app, lambda: attachments(self.app.store, self.document_id), loaded, self.failed)

    def add_file(self):
        path = filedialog.askopenfilename(parent=self.window, title="Attach supplementary file")
        if path:
            background(self.app, lambda: attach_file(self.app.store, self.document_id, path),
                       lambda _: self.refresh_attached() if self.alive() else None, self.failed)

    def open_attachment(self):
        if self.attached.selection():
            self.app.open_path(Path(self.saved[int(self.attached.selection()[0])]["path"]).parent)

    def download_selected(self):
        if not self.tree.selection():
            return
        link = dict(self.links[int(self.tree.selection()[0])])
        filename = Path(unquote(urlsplit(link["url"]).path)).name
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
        if Path(filename).suffix.lower() not in EXTENSIONS:
            filename = "Supplementary information.pdf"
        target = filedialog.asksaveasfilename(parent=self.window, title="Save supplementary file (new filename)",
                                            initialdir=self.paper_path.parent, initialfile=filename,
                                            filetypes=[("Supplementary files", "*.pdf *.zip *.docx *.xlsx *.pptx *.csv *.tsv *.txt *.json *.sdf *.mol")])
        if not target:
            return
        self.downloading = True
        self.download.configure(state="disabled")
        self.status.set("Downloading supplementary file…")
        def job():
            path = download_supplement(link["url"], target, lambda: self.cancelled.is_set() or self.app.closing)
            attach_file(self.app.store, self.document_id, path, link["url"])
            return path
        def saved(path):
            if self.alive():
                self.downloading = False
                self.selection_changed()
                self.status.set(f"Downloaded and attached: {path}")
                self.refresh_attached()
        background(self.app, job, saved, self.failed)
