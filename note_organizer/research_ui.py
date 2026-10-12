"""Citation editing and supplementary-file review for a selected library paper."""
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from urllib.parse import unquote, urlsplit
import webbrowser

from .citations import FIELDS, CitationConflict, citation_for, citation_text, lookup_citation, save_citation
from .supplements import find_supplements, download_and_attach, attach_file, attachments, EXTENSIONS
from .supplement_library import find_existing, proposed_name
from .icons import Button
from .theme import BACKGROUND
from .widgets import Tooltip, ReadOnlyText, PathField, bind_dialog_close, fit_dialog, annotate_buttons
from .workflow_ui import background


def review_citation_conflict(app, records, chosen, action_label="Use citation and link"):
    window = tk.Toplevel(app.root)
    window.title("Choose the paper's citation")
    window.transient(app.root)
    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="These copies have different saved citations. Review and choose one for the linked paper.",
              wraplength=620).pack(anchor="w")
    choice = tk.IntVar(value=0)
    for index, record in enumerate(records):
        ttk.Radiobutton(frame, text=f"Citation {index+1}", variable=choice, value=index).pack(anchor="w", pady=(12, 2))
        ReadOnlyText(frame, height=4, value=citation_text(record)).pack(fill="x")
    controls = ttk.Frame(frame)
    controls.pack(fill="x", pady=(14, 0))
    def accept():
        record = records[choice.get()]
        window.destroy()
        chosen(record)
    Button(controls, text=action_label, command=accept, style="Primary.TButton").pack(side="right")
    Button(controls, text="Cancel", command=window.destroy).pack(side="right", padx=8)
    bind_dialog_close(window, window.destroy)
    fit_dialog(window, app.root)


class CitationWindow:
    def __init__(self, app, document_id):
        self.app, self.document_id = app, document_id
        self.saving = False
        self.window = window = tk.Toplevel(app.root)
        window.title("Citation details")
        window.configure(background=BACKGROUND)
        window.transient(app.root)
        bind_dialog_close(window, self.close)
        window.protocol("WM_DELETE_WINDOW", self.close)
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
        self.cancel = cancel = Button(controls, text="Cancel", command=self.close)
        cancel.pack(side="right", padx=8)
        Tooltip(cancel, "Close without saving draft citation changes.")
        annotate_buttons(window)
        fit_dialog(window, app.root)
        background(app, lambda: citation_for(app.store, document_id), self.loaded, self.failed)

    def alive(self):
        return not self.app.closing and self.window.winfo_exists()

    def close(self):
        if not self.saving:
            self.window.destroy()

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
            self.saving = False
            self.cancel.configure(state="normal")
            self.busy(False)
            self.status.set(str(error))
            if isinstance(error, CitationConflict):
                def chosen(record):
                    if self.alive():
                        self.fill(record)
                        self.status.set("Chosen citation loaded as a draft. Review the fields, then Save citation to apply it to every linked copy.")
                review_citation_conflict(self.app, error.records, chosen, "Use citation draft")

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
        if self.saving:
            return
        record = self.draft()
        self.saving = True
        self.cancel.configure(state="disabled")
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
        self.local_links, self.web_links = [], []
        self.window = window = tk.Toplevel(app.root)
        window.title("Supplementary files — " + self.paper_path.stem)
        window.configure(background=BACKGROUND)
        window.transient(app.root)
        bind_dialog_close(window, window.destroy)
        window.bind("<Destroy>", lambda event: self.cancelled.set() if event.widget == window else None, add="+")
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Review existing library files first. Find files also checks PDF links, DOI metadata, and the publisher page.",
                  wraplength=760).pack(anchor="w", pady=(0, 10))
        self.tree = self.scroll_table(frame, columns=("label", "source", "url"), show="headings", height=7)
        for key, label, width in (("label", "Candidate file", 220), ("source", "Found in", 220), ("url", "Location or link", 320)):
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
        Tooltip(self.download, "Use the sorter's naming style with the parent citation and _SI suffix. Identical library files are reused; different existing files are never overwritten. Limit: 100 MB.")
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
        self.use_existing = Button(controls, text="Use existing file", command=self.use_local, state="disabled")
        self.use_existing.pack(side="left", padx=8)
        Tooltip(self.use_existing, "Attach the selected library candidate in its current location. A similar filename alone does not confirm that it belongs to this paper.")
        self.open_file = Button(controls, text="Open containing folder", command=self.open_attachment, state="disabled")
        self.open_file.pack(side="left", padx=8)
        Tooltip(self.open_file, "Open the folder containing the selected attachment so you can inspect the saved file.")
        self.open_attachment_file = Button(controls, text="Open attached file", command=self.open_saved_file, state="disabled")
        self.open_attachment_file.pack(side="left")
        self.attached.bind("<Return>", lambda _: self.open_saved_file())
        self.attached.bind("<Double-1>", lambda _: self.open_saved_file())
        close = Button(controls, text="Close", command=window.destroy)
        close.pack(side="right")
        Tooltip(close, "Close this supplementary-file review. A pending download is stopped before publishing its completed file.")
        self.status = tk.StringVar(value="Checking existing library files. Choose Find files to also check publisher links.")
        status = ReadOnlyText(frame, textvariable=self.status, height=4, width=80)
        status.pack(fill="x")
        annotate_buttons(window)
        fit_dialog(window, app.root)
        self.refresh_attached()
        self.refresh_existing()

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
            self.selection_changed()
            self.status.set(str(error))

    def download_failed(self, error):
        if self.alive():
            self.downloading = False
            self.failed(error)

    def selection_changed(self, event=None):
        selected = bool(self.tree.selection())
        link = self.links[int(self.tree.selection()[0])] if selected else {}
        local = bool(link.get("path"))
        self.open.configure(state="normal" if selected and not local else "disabled")
        self.download.configure(state="normal" if selected and not local and not getattr(self, "downloading", False) else "disabled")
        self.use_existing.configure(state="normal" if local else "disabled")
        self.open_file.configure(state="normal" if self.attached.selection() else "disabled")
        self.open_attachment_file.configure(state="normal" if self.attached.selection() else "disabled")
        self.article.configure(state="normal" if self.landing else "disabled")
        self.selected_url.set(link.get("path") or link.get("url", ""))
        self.attached_path.set(self.saved[int(self.attached.selection()[0])]["path"] if self.attached.selection() else "")
        self.path_access.refresh()

    def discover(self):
        self.find.configure(state="disabled")
        self.status.set("Checking PDF links, DOI metadata, and publisher page…")
        def found(result):
            if not self.alive():
                return
            self.local_links, remote = result
            self.web_links, warnings, self.landing = remote
            self.show_links()
            self.find.configure(state="normal")
            self.selection_changed()
            self.status.set((f"{len(self.local_links)} existing library candidate(s); {len(self.web_links)} web link(s). Review before attaching or downloading." if self.links else
                             "No supplementary links found. You can download files in your browser and use Add file….") +
                            ("\n" + "\n".join(warnings) if warnings else ""))
        background(self.app, lambda: (find_existing(self.app.store, self.document_id, self.cancelled.is_set),
                                     find_supplements(self.app.store, self.app.pdf_worker, self.document_id)), found, self.failed)

    def show_links(self):
        self.links = self.local_links + self.web_links
        self.tree.delete(*self.tree.get_children())
        for i, link in enumerate(self.links):
            self.tree.insert("", "end", iid=str(i), values=(link["label"], link["source"], link.get("path") or link["url"]))
        self.selection_changed()

    def refresh_existing(self, message=None):
        def loaded(rows):
            if self.alive():
                self.local_links = rows
                self.show_links()
                self.refresh_attached()
                if message:
                    self.status.set(message)
                elif not self.web_links:
                    self.status.set(f"{len(rows)} existing library candidate(s). Review and Use existing file, or choose Find files to check publisher links.")
        background(self.app, lambda: find_existing(self.app.store, self.document_id, self.cancelled.is_set), loaded, self.failed)

    def use_local(self):
        if self.tree.selection():
            link = self.links[int(self.tree.selection()[0])]
            if link.get("path"):
                background(self.app, lambda: attach_file(self.app.store, self.document_id, link["path"]),
                           lambda _: self.refresh_existing() if self.alive() else None, self.failed)

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
                       lambda _: self.refresh_existing() if self.alive() else None, self.failed)

    def open_attachment(self):
        if self.attached.selection():
            self.app.open_path(Path(self.saved[int(self.attached.selection()[0])]["path"]).parent)

    def open_saved_file(self):
        if self.attached.selection():
            path = Path(self.saved[int(self.attached.selection()[0])]["path"])
            if path.is_file():
                self.app.open_path(path)
            else:
                self.status.set("This attachment moved or is unavailable. Use Find files to reconnect it.")

    def download_selected(self):
        if not self.tree.selection():
            return
        link = dict(self.links[int(self.tree.selection()[0])])
        if link.get("path") or getattr(self, "downloading", False):
            return
        filename = Path(unquote(urlsplit(link["url"]).path)).name
        suffix = Path(filename).suffix.lower()
        if suffix not in EXTENSIONS:
            suffix = ".pdf"
        self.downloading = True
        self.selection_changed()
        background(self.app, lambda: proposed_name(self.app.store, self.document_id, suffix),
                   lambda name: self.choose_download(link, name), self.download_failed)

    def choose_download(self, link, filename):
        if not self.alive():
            return
        original, index = Path(filename), 1
        while (self.paper_path.parent / filename).exists():
            index += 1
            filename = f"{original.stem} ({index}){original.suffix}"
        target = filedialog.asksaveasfilename(parent=self.window, title="Save supplementary file (new filename)",
                                            initialdir=self.paper_path.parent, initialfile=filename,
                                            filetypes=[("Supplementary files", "*.pdf *.zip *.docx *.xlsx *.pptx *.csv *.tsv *.txt *.json *.sdf *.mol")])
        if not target:
            self.downloading = False
            self.selection_changed()
            return
        self.downloading = True
        self.download.configure(state="disabled")
        self.status.set("Downloading supplementary file…")
        def job():
            return download_and_attach(self.app.store, self.document_id, link["url"], target,
                                       lambda: self.cancelled.is_set() or self.app.closing)
        def saved(result):
            if self.alive():
                self.downloading = False
                self.selection_changed()
                self.refresh_existing(("Reused existing file: " if result["reused"] else "Downloaded and attached: ") + result["path"])
        background(self.app, job, saved, self.download_failed)
