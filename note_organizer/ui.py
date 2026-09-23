"""Tk interface with searchable notes, original page context and activity."""
import base64
from datetime import datetime
from io import BytesIO
import json
import os
from pathlib import Path
import queue
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
from . import __version__
from .exporting import paper_title
from .service import Service
from .storage import SEARCH_FIELDS, NOTE_TYPES
from .search import SearchSyntaxError
from .viewers import open_pdf_page, VIEWERS, find_viewer
from .theme import apply_theme, text_options, BACKGROUND, PANEL


class App:
    def __init__(self, root, store, data_dir):
        self.root, self.store, self.data_dir = root, store, Path(data_dir)
        self.service = Service(store)
        self.viewer_preference = store.preference("pdf_viewer", {"viewer": "system"})
        if not isinstance(self.viewer_preference, dict) or self.viewer_preference.get("viewer") not in VIEWERS:
            self.viewer_preference = {"viewer": "system"}
        self.entries = []
        self.image = None
        self.closing = False
        self.search_after = None
        self.style = apply_theme(root)
        root.title(f"PDF Note Organizer {__version__}")
        root.geometry(f"{min(1250, root.winfo_screenwidth()-80)}x{min(820, root.winfo_screenheight()-100)}")
        root.minsize(940, 620)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.build()
        self.refresh()
        if self.entries:
            self.tabs.select(self.notes_tab)
        self.service.start()
        root.after(250, self.poll)

    def build(self):
        header = ttk.Frame(self.root, padding=(20, 16, 20, 12))
        header.pack(fill="x")
        ttk.Label(header, text="PDF Note Organizer", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="Help", command=self.help).pack(side="right")
        self.status = tk.StringVar(value="Starting…")
        status = ttk.Label(self.root, textvariable=self.status, style="Muted.TLabel", padding=(20, 10))
        status.pack(side="bottom", fill="x")
        status.bind("<Configure>", lambda e: status.configure(wraplength=max(100, e.width-40)))
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=20, pady=(0, 4))
        self.library_tab = ttk.Frame(self.tabs, padding=(12, 16))
        self.notes_tab = ttk.Frame(self.tabs, padding=(12, 16))
        self.tabs.add(self.library_tab, text="Library")
        self.tabs.add(self.notes_tab, text="Notes")
        self.build_library()
        self.build_reader()

    def tree(self, parent, columns, height=8):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings",
                            height=height, selectmode="browse")
        for key, title, width in columns:
            tree.heading(key, text=title, anchor="w")
            tree.column(key, width=width, minwidth=40, stretch=key in {"name", "text"})
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        tree.configure(yscrollcommand=scrollbar.set)
        return tree

    def more_button(self, parent, actions):
        button = ttk.Button(parent, text="More ▾")
        menu = tk.Menu(button, tearoff=False, background=PANEL, foreground="#DCE4EE",
                       activebackground="#1F6AA5", activeforeground="white", borderwidth=0)
        for label, action in actions:
            menu.add_command(label=label, command=action)
        def show():
            try:
                menu.tk_popup(button.winfo_rootx(), button.winfo_rooty()+button.winfo_height())
            finally:
                menu.grab_release()
        button.configure(command=show)
        return button

    def build_library(self):
        tab = self.library_tab
        ttk.Label(tab, text="Manage your PDFs", style="Section.TLabel").pack(anchor="w")
        ttk.Label(tab, text="Choose folders to watch. New and changed PDFs are analyzed automatically.",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 16))
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", pady=(0, 16))
        ttk.Button(toolbar, text="Add folder", command=self.add, style="Primary.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Sync now", command=self.service.request_sync).pack(side="left")
        self.library_actions = []
        for label, action in [("Settings", self.settings), ("View notes →", self.view_notes)]:
            button = ttk.Button(toolbar, text=label, command=action)
            button.pack(side="left", padx=(8, 0))
            self.library_actions.append(button)
        more = self.more_button(toolbar, [("Rebuild notebook", self.rebuild), ("Open source PDF", self.open_paper),
                                           ("Remove selected folder…", self.remove)])
        more.pack(side="right")
        self.library_actions.append(more)
        self.activity_frame = ttk.Frame(tab)
        self.activity = tk.Text(self.activity_frame, height=6, wrap="word", state="disabled", **text_options())
        log_scroll = ttk.Scrollbar(self.activity_frame, orient="vertical", command=self.activity.yview)
        log_scroll.pack(side="right", fill="y")
        self.activity.pack(fill="both", expand=True)
        self.activity.configure(yscrollcommand=log_scroll.set)
        self.activity_toggle = ttk.Button(tab, text="Show activity ▾", command=self.toggle_activity)
        self.activity_toggle.pack(side="bottom", anchor="w", pady=(12, 0))
        self.location = tk.StringVar()
        location = ttk.Label(tab, textvariable=self.location, style="Muted.TLabel")
        location.pack(side="bottom", fill="x", pady=(12, 0))
        location.bind("<Configure>", lambda e: location.configure(wraplength=max(100, e.width)))
        self.library_pane = ttk.Panedwindow(tab, orient="horizontal")
        self.library_pane.pack(fill="both", expand=True)
        folders = ttk.Frame(self.library_pane, padding=(0, 0, 14, 0))
        ttk.Label(folders, text="Watched folders", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self.projects = self.tree(folders, [("name", "Folder", 180), ("state", "Status", 150)])
        self.projects.bind("<<TreeviewSelect>>", self.project_selected)
        self.library_pane.add(folders, weight=1)
        papers = ttk.Frame(self.library_pane)
        ttk.Label(papers, text="Papers", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self.papers = self.tree(papers, [("name", "Paper", 300), ("count", "Notes", 55), ("state", "Status", 90)])
        self.papers.bind("<<TreeviewSelect>>", self.paper_selected)
        self.papers.bind("<Double-1>", self.view_notes)
        self.library_pane.add(papers, weight=2)

    def build_reader(self):
        tab = self.notes_tab
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", pady=(0, 14))
        ttk.Label(toolbar, text="Read your notes", style="Section.TLabel").pack(side="left")
        self.more_button(toolbar, [("Save editable copy…", self.editable_copy),
                                   ("Change history", self.history), ("PDF viewer…", self.viewer_settings)]).pack(side="right")
        self.notebook_button = ttk.Button(toolbar, text="Open notebook", command=self.open_notebook)
        self.notebook_button.pack(side="right", padx=8)
        self.export_button = ttk.Button(toolbar, text="Export view", command=self.export_view, style="Primary.TButton")
        self.export_button.pack(side="right")
        filters = ttk.Frame(tab)
        filters.pack(fill="x", pady=(0, 10))
        filters.columnconfigure(1, weight=1)
        filters.columnconfigure(3, weight=2)
        ttk.Label(filters, text="Folder").grid(row=0, column=0, padx=(0, 8))
        self.reader_folder = ttk.Combobox(filters, state="readonly", width=18)
        self.reader_folder.grid(row=0, column=1, sticky="ew")
        self.reader_folder.bind("<<ComboboxSelected>>", self.reader_folder_selected)
        ttk.Label(filters, text="Paper").grid(row=0, column=2, padx=(16, 8))
        self.reader_paper = ttk.Combobox(filters, state="readonly", width=25)
        self.reader_paper.grid(row=0, column=3, sticky="ew")
        self.reader_paper.bind("<<ComboboxSelected>>", self.reader_paper_selected)
        self.reader_project_ids = []
        self.reader_paper_ids = []
        self.active_project_id = None
        self.all_projects = tk.BooleanVar(value=False)
        searchbar = ttk.Frame(tab)
        searchbar.pack(fill="x", pady=(0, 16))
        ttk.Label(searchbar, text="Search").pack(side="left", padx=(0, 8))
        self.search = tk.StringVar()
        self.search_fields = list(SEARCH_FIELDS)
        self.search_mode = "Words / Boolean"
        self.note_type = "All notes"
        ttk.Entry(searchbar, textvariable=self.search).pack(side="left", fill="x", expand=True)
        self.search_options_button = ttk.Button(searchbar, text="Search in…", command=self.search_options)
        self.search_options_button.pack(side="left", padx=(8, 0))
        self.search.trace_add("write", self.search_changed)
        self.note_count = tk.StringVar()
        ttk.Label(searchbar, textvariable=self.note_count, style="Muted.TLabel", width=12, anchor="e").pack(side="right")
        self.search_summary = tk.StringVar()
        self.search_summary_label = ttk.Label(tab, textvariable=self.search_summary, style="Muted.TLabel")
        self.search_error = tk.StringVar()
        self.search_error_label = ttk.Label(tab, textvariable=self.search_error, foreground="#FFB4AB", wraplength=800)
        self.reader_pane = ttk.Panedwindow(tab, orient="horizontal")
        self.reader_pane.pack(fill="both", expand=True)
        left = ttk.Frame(self.reader_pane, width=280, padding=(0, 0, 16, 0))
        self.notes = self.tree(left, [("page", "Page", 50), ("kind", "Type", 70), ("text", "Note", 210)])
        self.notes.configure(displaycolumns=("page", "text"))
        self.notes.bind("<<TreeviewSelect>>", self.preview)
        self.reader_pane.add(left, weight=1)
        right = ttk.Frame(self.reader_pane)
        buttons = ttk.Frame(right)
        buttons.pack(fill="x", pady=(0, 10))
        self.source_button = ttk.Button(buttons, text="Source PDF", command=self.open_source)
        self.source_button.pack(side="left", padx=(0, 8))
        self.enlarge_button = ttk.Button(buttons, text="Enlarge image", command=self.enlarge)
        self.enlarge_button.pack(side="left")
        self.show_details = tk.BooleanVar(value=False)
        ttk.Checkbutton(buttons, text="Details", variable=self.show_details, command=self.preview).pack(side="right")
        self.context_pane = ttk.Panedwindow(right, orient="vertical")
        self.context_pane.pack(fill="both", expand=True)
        text_frame = ttk.Frame(self.context_pane)
        self.preview_text = tk.Text(text_frame, height=9, width=35, wrap="word", state="disabled", **text_options())
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.preview_text.yview)
        scroll.pack(side="right", fill="y")
        self.preview_text.pack(fill="both", expand=True)
        self.preview_text.configure(yscrollcommand=scroll.set)
        self.context_pane.add(text_frame, weight=1)
        self.canvas = tk.Canvas(self.context_pane, height=200, width=300, background=PANEL, highlightthickness=0)
        self.context_pane.add(self.canvas, weight=2)
        self.canvas.bind("<Configure>", lambda _: self.draw_image())
        self.reader_pane.add(right, weight=3)

    def toggle_activity(self):
        if self.activity_frame.winfo_manager():
            self.activity_frame.pack_forget()
            self.activity_toggle.configure(text="Show activity ▾")
        else:
            self.activity_frame.pack(side="bottom", fill="x", before=self.activity_toggle, pady=(12, 0))
            self.activity_toggle.configure(text="Hide activity ▴")

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
        self.sync_reader_filters()
        self.refresh_notes()


    def selected_project(self):
        sel = self.projects.selection()
        return self.store.project(int(sel[0])) if sel else None

    def search_options(self):
        window = tk.Toplevel(self.root)
        window.title("Search options")
        window.configure(background=BACKGROUND)
        window.transient(self.root)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Search in", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        fields = {key: tk.BooleanVar(value=key in self.search_fields) for key in SEARCH_FIELDS}
        for index, (key, label) in enumerate(SEARCH_FIELDS.items()):
            ttk.Checkbutton(frame, text=label, variable=fields[key]).grid(row=1+index//2, column=index%2, sticky="w", padx=(0, 20), pady=5)
        ttk.Label(frame, text="Handwriting matches available OCR only. Printed text beneath ink is a separate field.",
                  wraplength=500, style="Muted.TLabel").grid(row=6, column=0, columnspan=2, sticky="w", pady=12)
        mode, kind = tk.StringVar(value=self.search_mode), tk.StringVar(value=self.note_type)
        ttk.Label(frame, text="Match").grid(row=7, column=0, sticky="w", pady=5)
        ttk.Combobox(frame, textvariable=mode, values=["Words / Boolean", "Exact phrase"], state="readonly").grid(row=7, column=1, sticky="ew")
        ttk.Label(frame, text="Show").grid(row=8, column=0, sticky="w", pady=5)
        ttk.Combobox(frame, textvariable=kind, values=NOTE_TYPES, state="readonly").grid(row=8, column=1, sticky="ew")
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
            filtered = len(selected) != len(SEARCH_FIELDS) or self.search_mode != "Words / Boolean" or self.note_type != "All notes"
            self.search_options_button.configure(text="Search in… •" if filtered else "Search in…")
            self.search_summary.set(" · ".join([f"{len(selected)} search fields", self.search_mode, self.note_type]) if filtered else "")
            if filtered:
                self.search_summary_label.pack(fill="x", before=self.reader_pane, pady=(0, 8))
            else:
                self.search_summary_label.pack_forget()
            self.refresh_notes()
            window.destroy()
        buttons = ttk.Frame(frame)
        ttk.Label(frame, text='Words / Boolean: use uppercase AND, OR, NOT, quotes, and parentheses.\n'
                  'Example: (iodine OR gold) AND "spectral CT" NOT phantom\n'
                  'Spaces mean AND. Exact phrase treats operators as ordinary text.',
                  style="Muted.TLabel", wraplength=500).grid(row=9, column=0, columnspan=2, sticky="w", pady=(12, 0))
        buttons.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        ttk.Button(buttons, text="Reset all", command=reset).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Clear fields", command=lambda: [v.set(False) for v in fields.values()]).pack(side="left")
        ttk.Button(buttons, text="Apply", command=apply, style="Primary.TButton").pack(side="right")
        window.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width()-window.winfo_reqwidth())//2
        y = self.root.winfo_rooty() + (self.root.winfo_height()-window.winfo_reqheight())//2
        window.geometry(f"+{max(0, x)}+{max(0, y)}")
        window.resizable(False, False)

    def selected_entry(self):
        sel = self.notes.selection()
        return self.entries[int(sel[0])] if sel and int(sel[0]) < len(self.entries) else None

    def viewer_settings(self):
        window = tk.Toplevel(self.root)
        window.title("PDF viewer")
        window.configure(background=BACKGROUND)
        window.transient(self.root)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Open source PDFs with", style="Section.TLabel").pack(anchor="w", pady=(0, 12))
        choice = tk.StringVar(value=VIEWERS[self.viewer_preference["viewer"]])
        picker = ttk.Combobox(frame, textvariable=choice, values=list(VIEWERS.values()), state="readonly", width=42)
        picker.pack(fill="x")
        path = tk.StringVar(value=self.viewer_preference.get("path", ""))
        file_row = ttk.Frame(frame)
        file_row.pack(fill="x", pady=12)
        entry = ttk.Entry(file_row, textvariable=path, width=42)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        def browse():
            value = filedialog.askopenfilename(parent=window, title="Choose your PDF viewer application",
                                               filetypes=[("Windows application", "*.exe")])
            if value:
                path.set(value)
        browse_button = ttk.Button(file_row, text="Browse…", command=browse)
        browse_button.pack(side="right")
        def selection_changed(event=None):
            state = "normal" if choice.get() == VIEWERS["custom"] else "disabled"
            entry.configure(state=state)
            browse_button.configure(state=state)
        picker.bind("<<ComboboxSelected>>", selection_changed)
        selection_changed()
        ttk.Label(frame, text="Known viewers receive the selected note's PDF page. For other viewers, the file opens normally and the requested page is shown in the app.\n\nThis choice is saved for this library and does not change Windows defaults.",
                  style="Muted.TLabel", wraplength=470).pack(anchor="w", pady=(0, 16))
        def save():
            viewer = next(key for key, value in VIEWERS.items() if value == choice.get())
            preference = {"viewer": viewer}
            if viewer == "custom":
                target = Path(path.get().strip())
                if target.suffix.lower() != ".exe" or not target.is_file():
                    messagebox.showerror("Choose an application", "Browse to the PDF viewer's .exe file.", parent=window)
                    return
                preference["path"] = str(target.resolve())
            elif viewer != "system" and not find_viewer(viewer):
                messagebox.showerror("Viewer not found", "Choose Other application and browse to its .exe, or choose Windows default.", parent=window)
                return
            self.store.set_preference("pdf_viewer", preference)
            self.viewer_preference = preference
            self.status.set(f"Source PDFs will open with {VIEWERS[viewer]}.")
            window.destroy()
        ttk.Button(frame, text="Save", command=save, style="Primary.TButton").pack(anchor="e")
        window.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width()-window.winfo_reqwidth())//2
        y = self.root.winfo_rooty() + (self.root.winfo_height()-window.winfo_reqheight())//2
        window.geometry(f"+{max(0, x)}+{max(0, y)}")
        window.resizable(False, False)

    def add(self):
        path = filedialog.askdirectory(title="Choose a folder of annotated PDFs")
        if path:
            self.service.command("add", path)

    def remove(self):
        p = self.selected_project()
        if p and messagebox.askyesno("Remove folder", "Remove this folder and its saved annotation history from the library?\n\nPDFs and Word notebooks remain on disk."):
            self.service.command("remove", p["id"])

    def rebuild(self):
        p = self.selected_project()
        if p:
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
        return Path(target).resolve() in [Path(r["output"]).resolve() for r in self.store.projects()]

    def editable_copy(self):
        if self.all_projects.get():
            messagebox.showinfo("Choose a folder", "Select one folder in Notes to copy its notebook, or use Export view for notes from all folders.")
            return
        p = self.selected_project()
        if not p:
            return
        if not Path(p["output"]).exists():
            messagebox.showinfo("Notebook", "The notebook has not been exported yet. Check Activity for progress.")
            return
        target = filedialog.asksaveasfilename(defaultextension=".docx", filetypes=[("Word document", "*.docx")],
                                            initialfile=f"My notes on {Path(p['root']).name}.docx")
        if target:
            if self.reserved_output(target):
                messagebox.showerror("Choose another filename", "An editable copy must be separate from a generated notebook.")
                return
            try:
                shutil.copy2(p["output"], target)
                self.open_path(target)
            except Exception as exc:
                messagebox.showerror("Copy failed", str(exc))

    def export_view(self):
        target = filedialog.asksaveasfilename(defaultextension=".docx", initialfile="Selected research notes.docx",
                                            filetypes=[("Word document", "*.docx")])
        if target:
            if self.reserved_output(target):
                messagebox.showerror("Choose another filename", "Use a separate file for a filtered export.")
                return
            self.service.command("export_view", target, list(self.entries))

    def settings(self):
        p = self.selected_project()
        if not p:
            messagebox.showinfo("Settings", "Select a watched folder first.")
            return
        settings = json.loads(p["settings"])
        window = tk.Toplevel(self.root)
        window.configure(background=BACKGROUND)
        window.title("Extraction settings")
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Group drawings and handwriting").grid(row=0, column=0, sticky="w")
        mode = tk.StringVar(value=settings.get("grouping", "Nearby blocks"))
        ttk.Combobox(frame, textvariable=mode, values=["Nearby blocks", "Nearby lines", "Whole page"], state="readonly").grid(row=0, column=1, padx=10)
        ttk.Label(frame, text="Join nearby strokes within (points)").grid(row=1, column=0, sticky="w", pady=8)
        gap = tk.StringVar(value=str(settings.get("gap", 24)))
        ttk.Spinbox(frame, from_=4, to=100, textvariable=gap, width=8).grid(row=1, column=1, sticky="w", padx=10)
        ttk.Label(frame, text="Surrounding context margin (points)").grid(row=2, column=0, sticky="w")
        padding = tk.StringVar(value=str(settings.get("context_padding", 36)))
        ttk.Spinbox(frame, from_=8, to=200, textvariable=padding, width=8).grid(row=2, column=1, sticky="w", padx=10)
        ocr = tk.BooleanVar(value=settings.get("ocr", False))
        ttk.Checkbutton(frame, text="Suggest handwriting transcription (optional Tesseract OCR)", variable=ocr).grid(row=3, column=0, columnspan=2, pady=10, sticky="w")
        available = shutil.which("tesseract")
        ttk.Label(frame, text="Tesseract available" if available else "Tesseract not installed. Context images work without it.").grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Nearby blocks joins separate letters and nearby lines.\nWhole page preserves all marks and their context together.\nChanges re-extract this folder's PDFs.").grid(row=5, column=0, columnspan=2, sticky="w", pady=10)
        layout = tk.StringVar(value=settings.get("notebook_style", "Reading"))
        ttk.Label(frame, text="Word notebook layout").grid(row=6, column=0, sticky="w")
        ttk.Combobox(frame, textvariable=layout, values=["Reading", "Detailed"], state="readonly").grid(row=6, column=1, padx=10)
        ttk.Label(frame, text="Reading groups notes by paper and page. Detailed includes extraction metadata.",
                  wraplength=470).grid(row=7, column=0, columnspan=2, sticky="w", pady=8)

        def save():
            try:
                g, pad = float(gap.get()), float(padding.get())
                if not 4 <= g <= 100 or not 8 <= pad <= 200:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Invalid settings", "Use a stroke distance from 4 to 100 and margin from 8 to 200.", parent=window)
                return
            if ocr.get() and not available:
                messagebox.showerror("OCR unavailable", "Tesseract is not installed. Turn off transcription to continue.", parent=window)
                return
            settings.update(grouping=mode.get(), gap=g, context_padding=pad, ocr=ocr.get(), notebook_style=layout.get())
            self.service.command("settings", p["id"], settings)
            window.destroy()
        ttk.Button(frame, text="Apply changes", command=save).grid(row=8, column=1, sticky="e")

    def refresh(self):
        selection = self.projects.selection()
        self.projects.delete(*self.projects.get_children())
        projects = self.store.projects()
        self.reader_project_ids = [p["id"] for p in projects]
        names = [Path(p["root"]).name for p in projects]
        labels = [name if names.count(name) == 1 else f"{name} — {Path(p['root']).parent.name} [{p['id']}]"
                  for name, p in zip(names, projects)]
        self.reader_folder.configure(values=["All folders"] + labels)
        for p in projects:
            state = "Export pending" if p["error"] else "Needs export" if p["dirty"] else "Saved " + p["exported_at"][11:16] + " UTC"
            errors = self.store.errors(p["id"])
            if errors:
                state = f"{len(errors)} PDF read errors"
            if not Path(p["root"]).is_dir():
                state = "Folder unavailable"
            self.projects.insert("", "end", iid=str(p["id"]), values=(Path(p["root"]).name, state))
        children = self.projects.get_children()
        if children:
            self.projects.selection_set(selection[0] if selection and selection[0] in children else children[0])
        self.project_selected()

    def project_selected(self, event=None):
        old = self.papers.selection()
        self.failed_papers = {}
        self.papers.delete(*self.papers.get_children())
        p = self.selected_project()
        pid = p["id"] if p else None
        if pid != self.active_project_id:
            self.all_projects.set(False)
            self.active_project_id = pid
        for button in self.library_actions:
            button.configure(state="normal" if p else "disabled")
        self.location.set(p["root"] if p else "Add a folder to begin collecting PDF annotations.")
        if p:
            errors = {r["path"]: r["error"] for r in self.store.errors(p["id"])}
            shown = set()
            for d in self.store.documents(p["id"]):
                shown.add(d["path"])
                relative = str(Path(d["path"]).relative_to(Path(p["root"])))
                self.papers.insert("", "end", iid=d["id"], values=(relative, d["count"], "Read error" if d["path"] in errors else "Unavailable" if d["missing"] else "Available"))
            for index, path in enumerate(sorted(errors.keys() - shown)):
                relative = str(Path(path).relative_to(Path(p["root"])))
                iid = f"error-{index}"
                self.failed_papers[iid] = (path, errors[path])
                self.papers.insert("", "end", iid=iid, values=(relative, "—", "Read error"))
        if old and self.papers.exists(old[0]):
            self.papers.selection_set(old[0])
        self.sync_reader_filters()
        self.refresh_notes()

    def all_papers(self):
        self.papers.selection_remove(*self.papers.selection())
        self.refresh_notes()

    def search_changed(self, *_):
        if self.search_after:
            self.root.after_cancel(self.search_after)
        self.search_after = self.root.after(250, self.refresh_notes)

    def refresh_notes(self):
        if self.search_after:
            self.root.after_cancel(self.search_after)
        self.search_after = None
        p = self.selected_project()
        paper = self.papers.selection()
        current = self.selected_entry()
        try:
            self.entries = self.store.entries(project_id=p["id"] if p and not self.all_projects.get() else None,
                                          document_id=paper[0] if paper and not self.all_projects.get() else None,
                                          query=self.search.get(), fields=self.search_fields,
                                          match_mode=self.search_mode, note_type=self.note_type)
        except SearchSyntaxError as exc:
            self.entries = []
            self.search_error.set(f"Search: {exc}")
            self.search_error_label.pack(fill="x", before=self.reader_pane, pady=(0, 8))
        else:
            self.search_error.set("")
            self.search_error_label.pack_forget()
        self.notes.delete(*self.notes.get_children())
        selected = None
        for i, e in enumerate(self.entries):
            text = e.get("comment") or e.get("quote") or e.get("ocr") or "Drawing with page context"
            if self.all_projects.get():
                text = Path(e["path"]).stem + ": " + text
            self.notes.insert("", "end", iid=str(i), values=(e["label"], e["kind"], text.replace("\n", " ")[:180]))
            if current and (e["document_id"], e["key"]) == (current["document_id"], current["key"]):
                selected = str(i)
        if self.entries:
            self.notes.selection_set(selected or "0")
        self.note_count.set("Check search" if self.search_error.get() else f"{len(self.entries)} notes")
        self.export_button.configure(state="normal" if self.entries else "disabled")
        self.preview()

    def preview(self, event=None):
        e = self.selected_entry()
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.image = None
        if e:
            title = paper_title(e["path"], e.get("metadata", {}))
            lines = [f"{title} · Page {e['label']}"]
            if e.get("quote"):
                lines.append(e["quote"])
            for key, label in [("comment", "Note"), ("ocr", "Transcription to check")]:
                if e.get(key):
                    lines.append(f"{label}: {e[key]}")
            if self.show_details.get():
                lines.append(f"{Path(e['path']).name} | PDF page {e['page']} | {e['kind']} {e.get('color', '')}")
                if e.get("context"):
                    lines.append("Nearby text: " + e["context"])
                lines.extend(e.get("metadata", {}).get("warnings", []))
            self.preview_text.insert("1.0", "\n\n".join(lines))
            if e.get("image"):
                with Image.open(BytesIO(base64.b64decode(e["image"]))) as img:
                    self.image = img.copy()
        elif self.search_error.get():
            self.preview_text.insert("1.0", "Complete or correct your search to see matching notes.")
        elif self.papers.selection() and self.papers.selection()[0] in self.failed_papers:
            path, error = self.failed_papers[self.papers.selection()[0]]
            self.preview_text.insert("1.0", f"{Path(path).name}\n\nCould not read this PDF:\n{error}\n\nUse Sync now to retry.")
        else:
            self.preview_text.insert("1.0", "No notes to show.\n\nTry another paper or search, or add a PDF folder in Library.")
        self.source_button.configure(state="normal" if e else "disabled")
        self.enlarge_button.configure(state="normal" if self.image else "disabled")
        self.preview_text.configure(state="disabled")
        self.draw_image()

    def draw_image(self):
        self.canvas.delete("all")
        if self.image:
            copy = self.image.copy()
            copy.thumbnail((max(20, self.canvas.winfo_width()-16), max(20, self.canvas.winfo_height()-16)))
            self.tk_image = ImageTk.PhotoImage(copy)
            self.canvas.create_image(self.canvas.winfo_width()/2, 8, image=self.tk_image, anchor="n")

    def enlarge(self):
        if not self.image:
            return
        window = tk.Toplevel(self.root)
        window.title("Original annotation and page context")
        window.geometry("1000x750")
        window.configure(background=BACKGROUND)
        canvas = tk.Canvas(window, background=PANEL, highlightthickness=0)
        xscroll = ttk.Scrollbar(window, orient="horizontal", command=canvas.xview)
        yscroll = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
        xscroll.pack(side="bottom", fill="x")
        yscroll.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        canvas.image = ImageTk.PhotoImage(self.image)
        canvas.create_image(0, 0, image=canvas.image, anchor="nw")
        canvas.configure(scrollregion=canvas.bbox("all"))

    def open_source(self):
        e = self.selected_entry()
        if e:
            if not Path(e["path"]).exists():
                messagebox.showinfo("Source unavailable", "The PDF has moved or is offline. Your extracted notes are still available.")
            else:
                self.open_pdf(e["path"], e["page"])

    def open_pdf(self, path, page=1):
        try:
            status, page_supported = open_pdf_page(path, page, self.viewer_preference)
            self.status.set(status)
            if not page_supported:
                messagebox.showinfo("PDF page navigation", status, parent=self.root)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Unable to open source PDF", str(exc), parent=self.root)

    def open_paper(self):
        selection = self.papers.selection()
        if selection:
            if selection[0] in self.failed_papers:
                self.open_pdf(self.failed_papers[selection[0]][0])
                return
            for d in self.store.documents():
                if d["id"] == selection[0]:
                    self.open_pdf(d["path"])

    def history(self):
        e = self.selected_entry()
        if not e:
            return
        window = tk.Toplevel(self.root)
        window.title("Paper annotation history")
        window.configure(background=BACKGROUND)
        window.geometry("800x550")
        text = tk.Text(window, wrap="word", **text_options())
        text.pack(fill="both", expand=True)
        for h in self.store.history(e["document_id"]):
            payload = json.loads(h["payload"])
            summary = payload.get("comment") or payload.get("quote") or payload.get("ocr") or "Drawing with saved context image"
            text.insert("end", f"{h['at']} | {h['action']} | page {payload['page']}\n{summary}\n\n")
        text.configure(state="disabled")

    def help(self):
        messagebox.showinfo("PDF Note Organizer", "Library: add folders, sync PDFs, and adjust extraction settings. Expand Show activity to check progress.\n\n"
            "Notes: choose a folder and paper, search annotations, read their page context, and export. More contains editable copies and history.\n\n"
            "Drawings retain surrounding text and figures. Settings adjusts grouping and context margins; Whole page keeps all marks together.\n\n"
            "Sync checks PDFs. Rebuild recreates Word from saved notes. Save editable copy makes a separate notebook for your writing. "
            "External edits to generated notebooks are preserved in Notebook backups before regeneration.\n\n"
            "Updates are watched while the app is open, checked every five minutes, and caught up at startup. "
            "Closing the app stops watching.\n\n"
            f"Data and logs: {self.data_dir}\nVersion {__version__}")

    def poll(self):
        refresh = False
        for _ in range(100):
            try:
                text, changed = self.service.messages.get_nowait()
            except queue.Empty:
                break
            self.status.set(text)
            self.activity.configure(state="normal")
            self.activity.insert("end", f"{datetime.now():%H:%M:%S}  {text}\n")
            if int(self.activity.index("end-1c").split(".")[0]) > 2500:
                self.activity.delete("1.0", "500.0")
            self.activity.see("end")
            self.activity.configure(state="disabled")
            refresh |= changed
        if refresh:
            self.refresh()
        if not self.closing:
            self.root.after(250, self.poll)

    def close(self):
        self.closing = True
        self.status.set("Finishing the current PDF safely before closing…")
        self.service.stop()
        self.wait_close()

    def wait_close(self):
        if self.service.thread and self.service.thread.is_alive():
            self.root.after(100, self.wait_close)
        else:
            self.root.destroy()
