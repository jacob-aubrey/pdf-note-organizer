"""Main workspace layouts, kept separate from application coordination."""
import tkinter as tk
from tkinter import ttk
from .storage import SEARCH_FIELDS
from .research_search import SCOPES
from .theme import PANEL, text_options
from .icons import Button, icon, menu_action
from .widgets import Tooltip, PathField, PathTextTooltip, SelectionDetails, WrapToolbar
from .pages import page_description


class WorkspaceLayouts:
    def build_library(self):
        tab = self.library_tab
        heading = ttk.Frame(tab)
        heading.pack(fill="x", pady=(0, 12))
        ttk.Label(heading, text="Your PDF library", style="Section.TLabel").pack(side="left")
        Button(heading, text="Add folder…", command=self.add).pack(side="right")
        self.more_button(heading, [("Library storage & backups…", self.storage_maintenance)]).pack(side="right", padx=8)
        review_library = Button(heading, text="Review library…", command=self.review_library)
        review_library.pack(side="right", padx=8)
        Tooltip(review_library, "Find duplicate papers and folder differences using local files and saved tablet information. Review proposed links before changing anything.")
        guidance = ttk.Label(tab, text="Combining existing libraries? Review library checks duplicate papers and folder differences before you enable transfers.",
                             style="Muted.TLabel", wraplength=900)
        guidance.pack(fill="x", pady=(0, 10))
        guidance.bind("<Configure>", lambda event: guidance.configure(wraplength=max(100, event.width)))
        self.build_feedback(tab, "library")
        self.library_actions = []
        self.local_sync_summary = tk.StringVar()
        self.location = tk.StringVar()
        # Sync status and its expandable log stay together below the workspace.
        self.library_sync = ttk.Frame(tab, padding=(10, 8), style="Card.TFrame")
        self.library_sync.pack(side="bottom", fill="x", pady=(12, 0))
        sync_row = ttk.Frame(self.library_sync, style="Card.TFrame")
        sync_row.pack(fill="x")
        Button(sync_row, text="Sync PDFs", command=self.service.request_sync).pack(side="right")
        self.activity_toggle = Button(sync_row, text="Show sync details", command=self.toggle_activity, style="Quiet.TButton")
        self.activity_toggle.pack(side="right", padx=8)
        summary = ttk.Label(sync_row, textvariable=self.local_sync_summary, style="CardTitle.TLabel", wraplength=650)
        summary.pack(side="left", fill="x", expand=True)
        summary.bind("<Configure>", lambda e: summary.configure(wraplength=max(100, e.width)))
        self.activity_frame = ttk.Frame(self.library_sync)
        log_locations = ttk.Frame(self.activity_frame)
        log_locations.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Label(log_locations, text="Location").pack(side="left", padx=(0, 8))
        self.activity_location_paths = {}
        self.activity_locations = ttk.Combobox(log_locations, state="disabled", width=30)
        self.activity_locations.pack(side="left", fill="x", expand=True)
        self.activity_path_access = PathField(self.activity_locations,
            "Choose a saved sync location or retained recovery copy to inspect and copy its complete path.",
            value=lambda: self.activity_location_paths.get(self.activity_locations.get(), ""))
        self.activity_path_copy = self.activity_path_access.add_copy_button(log_locations)
        self.activity_path_copy.pack(side="right", padx=(6, 0))
        log_body = ttk.Frame(self.activity_frame)
        log_body.pack(fill="both", expand=True)
        self.activity = tk.Text(log_body, height=5, wrap="word", state="disabled", **text_options())
        self.activity_path_tooltip = PathTextTooltip(self.activity)
        log_scroll = ttk.Scrollbar(log_body, orient="vertical", command=self.activity.yview)
        log_scroll.pack(side="right", fill="y")
        self.activity.pack(fill="both", expand=True)
        self.activity.configure(yscrollcommand=log_scroll.set)
        self.library_pane = ttk.Panedwindow(tab, orient="horizontal")
        self.library_pane.pack(fill="both", expand=True)
        folders = ttk.Frame(self.library_pane, width=280, height=300, padding=(0, 0, 14, 0))
        folders.pack_propagate(False)
        ttk.Label(folders, text="Watched folders", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        folder_actions = ttk.Frame(folders)
        folder_actions.pack(fill="x", pady=(0, 10))
        self.folder_actions_button = settings = self.more_button(folder_actions, [("Folder settings", self.settings),
            ("Locate moved folder…", self.locate_folder), ("Rebuild notebook…", self.rebuild),
            ("Remove folder…", self.remove)], text="Folder actions ▾")
        folder_actions.columnconfigure(0, weight=1)
        settings.grid(row=0, column=0, sticky="w")
        self.library_actions.append(settings)
        self.library_folder_button = Button(folder_actions, text="Open folder", command=self.open_selected_folder, state="disabled")
        self.library_folder_button.grid(row=1, column=0, sticky="w", pady=(8, 0))
        Tooltip(self.library_folder_button, lambda: f"{self.selected_project()['root']}\n\nOpen the selected watched folder in File Explorer." if not self.library_folder_button.instate(["disabled"]) and self.selected_project() else
                "Select an available watched folder. For a moved folder, right-click it and choose Locate moved folder.")
        self.folder_details = SelectionDetails(folders, "Watched folder", height=2)
        self.folder_details.pack(side="bottom", fill="x", pady=(10, 0))
        self.projects = self.tree(folders, [("name", "Folder", 170), ("state", "Status", 145)])
        self.projects.tooltip.value = lambda row, column: self.watched_folder_path(row) if column == "name" else self.projects.set(row, column)
        self.projects.tooltip.extra = lambda row, column: "Select this watched folder to inspect and copy its full path." if column == "name" else ""
        self.projects.tooltip.full_with_help = True
        self.projects.bind("<<TreeviewSelect>>", self.project_selected)
        self.folder_menu = tk.Menu(self.projects, tearoff=False, background=PANEL, foreground="#DCE4EE",
                                   activebackground="#1B629B", activeforeground="white", borderwidth=0)
        menu_action(self.folder_menu, "Rebuild notebook…", self.rebuild)
        menu_action(self.folder_menu, "Remove folder…", self.remove)
        menu_action(self.folder_menu, "Locate moved folder…", self.locate_folder)
        self.projects.bind("<Button-3>", self.show_folder_menu)
        self.projects.bind("<Shift-F10>", self.show_folder_menu)
        self.projects.bind("<Menu>", self.show_folder_menu)
        self.library_pane.add(folders, weight=1)
        papers = ttk.Frame(self.library_pane, width=650, height=300)
        papers.pack_propagate(False)
        self.paper_heading = tk.StringVar(value="Papers")
        paper_heading = ttk.Label(papers, textvariable=self.paper_heading, style="Section.TLabel")
        paper_heading.pack(fill="x", pady=(0, 8))
        paper_heading.bind("<Configure>", lambda e: paper_heading.configure(wraplength=max(100, e.width)))
        Tooltip(paper_heading, lambda: self.paper_heading.get())
        paper_actions = ttk.Frame(papers)
        paper_actions.pack(fill="x", pady=(0, 10))
        view = Button(paper_actions, text="View notes", command=self.view_notes, style="Primary.TButton")
        view.pack(side="left")
        self.library_actions.append(view)
        Tooltip(view, lambda: "Read notes from the selected folder and paper." if self.selected_project() else "Select a watched folder first.")
        self.library_source_button = Button(paper_actions, text="Open PDF", command=self.open_paper, state="disabled")
        self.library_source_button.pack(side="left", padx=8)
        Tooltip(self.library_source_button, lambda: f"{self.library_paper_path(self.papers.selection()[0])}\n\nOpen the selected paper with its combined PC and tablet notes. Uncertain versions need review first." if self.papers.selection() else "Select a paper to open its PDF and saved notes.")
        self.more_button(paper_actions, [("Export annotated PDF…", self.export_paper_pdf),
            ("Citation details…", self.citation_details), ("Export citations…", self.export_citation_selection),
            ("Find supplementary files…", self.supplementary_files),
            ("Review extra PDFs…", self.review_extra_pdfs)]).pack(side="left", padx=(0, 8))
        self.library_send_button = Button(paper_actions, text="Send selected PDF…", command=self.send_paper, state="disabled")
        Tooltip(self.library_send_button, "Send a selected existing original PDF after reviewing duplicates and enabling PDF transfers in Settings → Connections.")
        self.paper_details = SelectionDetails(papers, "Selected paper", height=2)
        self.paper_details.pack(side="bottom", fill="x", pady=(10, 0))
        self.papers = self.tree(papers, [("name", "Paper", 320), ("count", "Notes", 65), ("state", "Status", 115)])
        self.papers.tooltip.value = lambda row, column: self.library_paper_path(row) if column == "name" else self.papers.set(row, column)
        self.papers.tooltip.extra = lambda row, column: "Select this PDF to inspect and copy its full path." if column == "name" else ""
        self.papers.tooltip.full_with_help = True
        self.papers.bind("<<TreeviewSelect>>", self.paper_selected)
        self.papers.bind("<Double-1>", self.view_notes)
        self.library_pane.add(papers, weight=3)
        self.initial_split(self.library_pane, .30)


    def build_reader(self):
        tab = self.notes_tab
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", pady=(0, 14))
        ttk.Label(toolbar, text="Read your notes", style="Section.TLabel").pack(side="left")
        self.more_button(toolbar, [("Save editable copy…", self.editable_copy),
                                   ("Export annotated PDF…", self.export_note_pdf),
                                   ("Citation details…", self.citation_details),
                                   ("Export citations…", self.export_citation_selection),
                                   ("Find supplementary files…", self.supplementary_files),
                                   ("Change history", self.history), ("Tags & collections…", self.organize_paper),
                                   ("Saved searches…", self.saved_searches),
                                   ("Accessible reading view…", self.accessible_reader)]).pack(side="right")
        self.notebook_button = Button(toolbar, text="Open notebook", command=self.open_notebook, style="Primary.TButton")
        self.notebook_button.pack(side="right", padx=8)
        self.export_button = Button(toolbar, text="Export view…", command=self.export_view)
        self.export_button.pack(side="right")
        Tooltip(self.export_button, lambda: "Export the notes currently shown to a separate Word document." if self.entries else "Choose a folder or search with matching notes before exporting.")
        Tooltip(self.notebook_button, lambda: "Open this folder's generated Word notebook." if not self.notebook_button.instate(["disabled"]) else "Select one folder instead of All folders to open its notebook.")
        self.notes_folder_button = Button(toolbar, text="Open folder", command=lambda: self.open_selected_folder(notes=True), state="disabled")
        self.notes_folder_button.pack(side="left", padx=(16, 0))
        Tooltip(self.notes_folder_button, lambda: f"{self.reader_folder_path()}\n\nOpen the PC folder selected below in File Explorer." if not self.notes_folder_button.instate(["disabled"]) else
                "Select one available folder instead of All folders.")
        self.build_feedback(tab, "notes")
        filters = ttk.Frame(tab)
        filters.pack(fill="x", pady=(0, 10))
        filters.columnconfigure(3, weight=1)
        ttk.Label(filters, text="Folder").grid(row=0, column=0, padx=(0, 8))
        folder_filter = ttk.Frame(filters)
        folder_filter.grid(row=0, column=1, sticky="ew")
        self.reader_folder = ttk.Combobox(folder_filter, state="readonly", width=24)
        self.reader_folder.pack(side="left", fill="x", expand=True)
        self.reader_folder.bind("<<ComboboxSelected>>", self.reader_folder_selected)
        ttk.Label(filters, text="Paper").grid(row=0, column=2, padx=(16, 8))
        paper_filter = ttk.Frame(filters)
        paper_filter.grid(row=0, column=3, sticky="ew")
        self.reader_paper = ttk.Combobox(paper_filter, state="readonly", width=25)
        self.reader_paper.pack(side="left", fill="x", expand=True)
        self.reader_paper.bind("<<ComboboxSelected>>", self.reader_paper_selected)
        self.reader_folder_path_access = PathField(self.reader_folder, "Choose All folders to search across the whole active library.", value=self.reader_folder_path)
        self.reader_folder_copy = self.reader_folder_path_access.add_copy_button(folder_filter)
        self.reader_folder_copy.pack(side="right", padx=(6, 0))
        self.reader_paper_path_access = PathField(self.reader_paper,
            lambda: "Select one folder to choose its paper. Copy full path uses the selected note's source PDF." if self.all_projects.get() else "Choose All papers to read every paper in the selected folder. With All papers selected, Copy full path uses the selected note's source PDF.",
            value=self.reader_paper_path)
        self.reader_paper_copy = self.reader_paper_path_access.add_copy_button(paper_filter)
        self.reader_paper_copy.pack(side="right", padx=(6, 0))
        self.reader_project_ids = []
        self.reader_paper_ids = []
        self.active_project_id = None
        self.all_projects = tk.BooleanVar(value=False)
        ttk.Label(filters, text="Collection or tag").grid(row=1, column=0, sticky="w", pady=(8, 0), padx=(0, 8))
        self.label_filter = tk.StringVar(value="All papers")
        self.label_picker = ttk.Combobox(filters, textvariable=self.label_filter, values=["All papers"], state="readonly")
        self.label_picker.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(8, 0))
        Tooltip(self.label_picker, "Show papers in a research collection or with a tag. Tags & collections in Actions edits the selected paper; All papers clears this filter.")
        self.label_filter.trace_add("write", self.search_changed)
        self.refresh_label_choices()
        searchbar = ttk.Frame(tab)
        searchbar.pack(fill="x", pady=(0, 16))
        self.search_label = ttk.Label(searchbar, text="Search", image=icon(searchbar, "search"), compound="left")
        self.search_label.pack(side="left", padx=(0, 8))
        self.search = tk.StringVar()
        self.search_fields = list(SEARCH_FIELDS)
        self.search_mode = "Words / Boolean"
        self.note_type = "All notes"
        self.search_entry = ttk.Entry(searchbar, textvariable=self.search, width=52)
        self.search_entry.pack(side="left", fill="x", expand=True)
        Tooltip(self.search_entry, 'Search notes, printed PDF text, or both in the chosen folder and paper. Spaces mean AND; uppercase AND, OR, NOT, quotes and parentheses are supported. PDF results match within one page; scanned pages need a text layer.')
        self.search_scope = tk.StringVar(value="Notes")
        self.search_scope_control = ttk.Combobox(searchbar, textvariable=self.search_scope, values=SCOPES,
                                                state="readonly", width=7)
        self.search_scope_control.pack(side="left", padx=(8, 0))
        Tooltip(self.search_scope_control, "Notes searches saved annotations. PDFs searches printed text on every page, including papers without notes. All combines both. Enter a query to search PDFs; the first search builds a local text cache. Search in… fields and note types apply to note results.")
        self.search_scope.trace_add("write", self.search_changed)
        self.search_options_button = Button(searchbar, text="Search in…", command=self.search_options)
        self.search_options_button.pack(side="left", padx=(8, 0))
        self.search.trace_add("write", self.search_changed)
        self.note_count = tk.StringVar()
        ttk.Label(searchbar, textvariable=self.note_count, style="Muted.TLabel", width=12, anchor="e").pack(side="right")
        self.search_summary = tk.StringVar()
        self.search_summary_label = ttk.Label(tab, textvariable=self.search_summary, style="Muted.TLabel")
        self.search_error = tk.StringVar()
        self.search_error_label = ttk.Label(tab, textvariable=self.search_error, foreground="#FFB4AB", wraplength=800)
        self.search_warning = tk.StringVar()
        self.search_warning_label = ttk.Label(tab, style="Muted.TLabel", wraplength=800)
        Tooltip(self.search_warning_label, lambda: self.search_warning.get())
        self.reader_pane = ttk.Panedwindow(tab, orient="horizontal")
        self.reader_pane.pack(fill="both", expand=True)
        left = ttk.Frame(self.reader_pane, width=280, padding=(0, 0, 16, 0))
        self.notes = self.tree(left, [("page", "PDF page", 78), ("kind", "Type", 70), ("text", "Note", 210)])
        self.notes.configure(displaycolumns=("page", "text"))
        self.notes.bind("<<TreeviewSelect>>", self.preview)
        self.notes.bind("<Double-1>", lambda event: self.open_source())
        self.notes.bind("<Return>", lambda event: self.open_source())
        self.notes.tooltip.extra = lambda row, column: self.note_help() if column == "page" else ""
        self.notes.tooltip.value = self.note_cell_value
        self.reader_pane.add(left, weight=1)
        right = ttk.Frame(self.reader_pane)
        buttons = ttk.Frame(right)
        buttons.pack(fill="x", pady=(0, 10))
        self.show_details = tk.BooleanVar(value=False)
        ttk.Checkbutton(buttons, text="Details", variable=self.show_details, command=self.preview).pack(side="right", anchor="n", padx=(12, 0))
        self.preview_actions = actions = WrapToolbar(buttons)
        actions.pack(side="left", fill="x", expand=True)
        self.source_button = actions.add(Button(actions, text="Open PDF", command=self.open_source))
        self.full_page_button = actions.add(Button(actions, text="Full page context", command=self.full_page_context, state="disabled"))
        self.enlarge_button = actions.add(Button(actions, text="Enlarge image", command=self.enlarge))
        self.copy_image_button = actions.add(Button(actions, text="Copy image", command=self.copy_note_image, state="disabled"))
        Tooltip(self.copy_image_button, "Copy the loaded note image at its original resolution. Click the inline image and press Ctrl+C, or right-click it.")
        Tooltip(self.enlarge_button, lambda: "Inspect this drawing or handwriting preview. Fit width or height, drag to pan, double-click to fit width, and Ctrl + scroll to zoom." if self.image else
                "Select a drawing or handwriting note with a loaded preview. Highlights use extracted text and Open PDF.")
        Tooltip(self.full_page_button, lambda: "Open the complete PDF page, including retained margins. Fit width or height, drag to pan, double-click to fit width, and Ctrl + scroll to zoom. Generated on demand; Copy image copies the complete page." if self.selected_entry() and self.selected_entry()["kind"] in {"drawing", "pdf"} else
                "Select a drawing, handwriting note, or PDF text result first. Highlights use Open PDF.")
        text_frame = ttk.Frame(right)
        text_frame.pack(fill="both", expand=True)
        self.preview_text = tk.Text(text_frame, height=9, width=35, wrap="word", state="disabled", **text_options())
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.preview_text.yview)
        scroll.pack(side="right", fill="y")
        self.preview_text.pack(fill="both", expand=True)
        self.preview_text.configure(yscrollcommand=scroll.set)
        self.preview_text.mark_set("preview_image", "end-1c")
        self.preview_text.mark_gravity("preview_image", "left")
        self.preview_image_name = None
        self.preview_image_focused = False
        self.preview_text.bind("<Configure>", self.schedule_image_resize)
        self.preview_text.bind("<Button-1>", self.focus_preview_image)
        self.preview_text.bind("<<Copy>>", self.copy_preview)
        self.preview_text.bind("<Button-3>", self.show_image_menu)
        self.preview_text.bind("<Shift-F10>", self.show_image_menu)
        self.image_menu = tk.Menu(self.preview_text, tearoff=False)
        menu_action(self.image_menu, "Copy image", self.copy_note_image)
        Tooltip(self.source_button, lambda: f"{self.entry_paper_path(self.selected_entry())}\n\nOpen the combined PC and tablet notes at physical PDF page {self.selected_entry()['page']}.\n{page_description(self.selected_entry())}" if self.selected_entry() else "Select a note first. Open PDF navigates using the physical PDF page position.")
        self.reader_pane.add(right, weight=3)
