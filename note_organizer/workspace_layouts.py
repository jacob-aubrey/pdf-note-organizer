"""Main workspace layouts, kept separate from application coordination."""
import tkinter as tk
from tkinter import ttk
from .storage import SEARCH_FIELDS, DEFAULT_SEARCH_FIELDS
from .theme import PANEL, text_options
from .icons import Button, icon, menu_action
from .widgets import Tooltip, PathField, PathTextTooltip, SelectionDetails, WrapToolbar, EntryPlaceholder, bind_item_open
from .pdf_reader import PDFReader
from .reader_title import DocumentTitle


class WorkspaceLayouts:
    def build_library(self):
        tab = self.library_tab
        heading = WrapToolbar(tab)
        heading.pack(fill="x", pady=(0, 8))
        heading.add(Button(heading, text="Add folder…", command=self.add))
        heading.add(self.more_button(heading, [("Review library…", self.review_library),
            ("Library storage & backups…", self.storage_maintenance)], text="Library actions ▾"))
        self.build_feedback(tab, "library")
        self.library_actions = []
        self.local_sync_summary = tk.StringVar()
        self.location = tk.StringVar()
        # Sync status and its expandable log stay together below the workspace.
        self.library_sync = ttk.Frame(tab, padding=(10, 6), style="Card.TFrame")
        self.library_sync.pack(side="bottom", fill="x", pady=(8, 0))
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
        self.activity.configure(pady=4)
        self.activity_path_tooltip = PathTextTooltip(self.activity)
        log_scroll = ttk.Scrollbar(log_body, orient="vertical", command=self.activity.yview)
        log_scroll.pack(side="right", fill="y")
        self.activity.pack(fill="both", expand=True)
        self.activity.configure(yscrollcommand=log_scroll.set)
        def size_activity(event):
            self.activity.configure(height=1 if event.height < 600 else 5)
        tab.bind("<Configure>", size_activity, add="+")
        self.library_pane = ttk.Panedwindow(tab, orient="horizontal")
        self.library_pane.pack(fill="both", expand=True)
        folders = ttk.Frame(self.library_pane, width=280, height=300, padding=(0, 0, 14, 0))
        folders.pack_propagate(False)
        ttk.Label(folders, text="Watched folders", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        folder_actions = ttk.Frame(folders)
        folder_actions.pack(fill="x", pady=(0, 8))
        self.folder_actions_button = settings = self.more_button(folder_actions, [("Open folder", self.open_selected_folder), ("Folder settings", self.settings),
            ("Locate moved folder…", self.locate_folder), ("Rebuild notebook…", self.rebuild),
            ("Remove folder…", self.remove)], text="Folder actions ▾")
        folder_actions.columnconfigure(0, weight=1)
        settings.grid(row=0, column=0, sticky="w")
        self.library_actions.append(settings)
        settings.action_menu.entryconfigure("Open folder", state="disabled")
        self.folder_details = SelectionDetails(folders, "Watched folder", height=2)
        self.folder_details.pack(side="bottom", fill="x", pady=(8, 0))
        self.projects = self.tree(folders, [("name", "Folder", 170), ("state", "Status", 145)], empty_text="No watched folders")
        self.projects.tooltip.value = lambda row, column: self.watched_folder_path(row) if column == "name" else self.projects.set(row, column)
        self.projects.tooltip.extra = lambda row, column: "Select this watched folder to inspect and copy its full path." if column == "name" else ""
        self.projects.tooltip.full_with_help = True
        self.projects.bind("<<TreeviewSelect>>", self.project_selected)
        bind_item_open(self.projects, lambda row: self.open_file_or_folder(self.watched_folder_path(row)))
        self.folder_menu = tk.Menu(self.projects, tearoff=False)
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
        paper_actions = WrapToolbar(papers)
        paper_actions.pack(fill="x", pady=(0, 8))
        view = Button(paper_actions, text="View in Reader", command=self.view_notes, style="Primary.TButton")
        paper_actions.add(view)
        self.library_actions.append(view)
        Tooltip(view, lambda: "Open the selected folder or paper in Reader with fresh, unfiltered PDF and note results." if self.selected_project() else "Select a watched folder first.")
        self.library_source_button = Button(paper_actions, text="Open externally", command=self.open_paper, state="disabled")
        paper_actions.add(self.library_source_button)
        Tooltip(self.library_source_button, lambda: f"{self.library_paper_path(self.papers.selection()[0])}\n\nOpen the selected paper in your computer's default PDF viewer, with its combined PC and tablet notes. Uncertain versions need review first." if self.papers.selection() else "Select a paper to open externally.")
        self.library_paper_actions = self.more_button(paper_actions, [("Export annotated PDF…", self.export_paper_pdf),
            ("Citation details…", self.citation_details), ("Export citations…", self.export_citation_selection),
            ("Find supplementary files…", self.supplementary_files),
            ("Review extra PDFs…", self.review_extra_pdfs), ("Send selected PDF…", self.send_paper)])
        paper_actions.add(self.library_paper_actions)
        self.library_paper_actions.action_menu.entryconfigure("Send selected PDF…", state="disabled")
        self.paper_details = SelectionDetails(papers, "Selected paper", height=2)
        self.paper_details.pack(side="bottom", fill="x", pady=(8, 0))
        self.papers = self.tree(papers, [("name", "Paper", 320), ("count", "Notes", 65), ("state", "Status", 115)], empty_text="No papers in this folder")
        self.papers.tooltip.value = lambda row, column: self.library_paper_path(row) if column == "name" else self.papers.set(row, column)
        self.papers.tooltip.extra = lambda row, column: "Double-click or press Enter to open this paper in Reader. Open externally uses your default PDF viewer." if column == "name" else ""
        self.papers.tooltip.full_with_help = True
        self.papers.bind("<<TreeviewSelect>>", self.paper_selected)
        bind_item_open(self.papers, self.open_library_reader)
        self.library_pane.add(papers, weight=3)
        self.initial_split(self.library_pane, .30)


    def build_reader(self):
        tab = self.notes_tab
        controls = self.reader_controls = ttk.Frame(tab)
        controls.pack(fill="x")
        toolbar = ttk.Frame(controls)
        toolbar.pack(fill="x", pady=(0, 14))
        ttk.Label(toolbar, text="Papers & notes", style="Section.TLabel").pack(side="left", anchor="n", pady=7)
        header_actions = WrapToolbar(toolbar)
        header_actions.pack(side="left", fill="x", expand=True, padx=(16, 0))
        more = self.more_button(header_actions, [("Save editable copy…", self.editable_copy),
                                   ("Export view…", self.export_view),
                                   ("Export annotated PDF…", self.export_note_pdf),
                                   ("Citation details…", self.citation_details),
                                   ("Export citations…", self.export_citation_selection),
                                   ("Find supplementary files…", self.supplementary_files),
                                   ("Change history", self.history), ("Tags & collections…", self.organize_paper),
                                   ("Document details…", self.reader_document_details),
                                   ("Saved searches…", self.saved_searches),
                                   ("Accessible reading view…", self.accessible_reader)])
        self.reader_actions_button = more
        # Retain the existing state hook while Export view is now a menu action.
        self.export_button = Button(header_actions, text="Export view…", command=self.export_view)
        self.notebook_button = Button(header_actions, text="Open notebook", command=self.open_notebook, style="Primary.TButton")
        Tooltip(self.notebook_button, lambda: "Open this folder's generated Word notebook." if not self.notebook_button.instate(["disabled"]) else "Select one folder instead of All folders to open its notebook.")
        self.notes_folder_button = Button(header_actions, text="Open folder", command=lambda: self.open_selected_folder(notes=True), state="disabled")
        for button in (self.notes_folder_button, self.notebook_button, more):
            header_actions.add(button)
        Tooltip(self.notes_folder_button, lambda: f"{self.reader_folder_path()}\n\nOpen the PC folder selected below in File Explorer." if not self.notes_folder_button.instate(["disabled"]) else
                "Select one available folder instead of All folders.")
        self.build_feedback(controls, "notes")
        filters = ttk.Frame(controls)
        filters.pack(fill="x", pady=(0, 10))
        for column in (1, 4, 7):
            filters.columnconfigure(column, weight=1, uniform="reader_filter_choices")
        ttk.Label(filters, text="Folder").grid(row=0, column=0, padx=(0, 8))
        self.reader_folder = ttk.Combobox(filters, state="readonly", width=1)
        self.reader_folder.grid(row=0, column=1, sticky="ew")
        self.reader_folder.bind("<<ComboboxSelected>>", self.reader_folder_selected)
        ttk.Label(filters, text="Paper").grid(row=0, column=3, padx=(16, 8))
        self.reader_paper = ttk.Combobox(filters, state="readonly", width=1)
        self.reader_paper.grid(row=0, column=4, sticky="ew")
        self.reader_paper.bind("<<ComboboxSelected>>", self.reader_paper_selected)
        self.reader_folder_path_access = PathField(self.reader_folder, "Choose All folders to search across the whole active library.", value=self.reader_folder_path)
        self.reader_folder_copy = self.reader_folder_path_access.add_copy_button(filters)
        self.reader_folder_copy.grid(row=0, column=2, padx=(6, 0))
        self.reader_paper_path_access = PathField(self.reader_paper,
            lambda: "Select one folder to choose its paper. Copy full path uses the selected note's source PDF." if self.all_projects.get() else "Choose All papers to read every paper in the selected folder. With All papers selected, Copy full path uses the selected note's source PDF.",
            value=self.reader_paper_path)
        self.reader_paper_copy = self.reader_paper_path_access.add_copy_button(filters)
        self.reader_paper_copy.grid(row=0, column=5, padx=(6, 0))
        self.reader_project_ids = []
        self.reader_paper_ids = []
        self.active_project_id = None
        self.all_projects = tk.BooleanVar(value=False)
        ttk.Label(filters, text="Collection or tag").grid(row=0, column=6, sticky="w", padx=(16, 8))
        self.label_filter = tk.StringVar(value="All papers")
        self.label_picker = ttk.Combobox(filters, textvariable=self.label_filter, values=["All papers"], state="readonly", width=1)
        self.label_picker.grid(row=0, column=7, sticky="ew")
        Tooltip(self.label_picker, "Show papers in a research collection or with a tag. Tags & collections in Actions edits the selected paper; All papers clears this filter.")
        self.label_filter.trace_add("write", self.search_changed)
        self.refresh_label_choices()
        searchbar = ttk.Frame(controls)
        searchbar.pack(fill="x", pady=(0, 16))
        self.search_label = ttk.Label(searchbar, text="Search", image=icon(searchbar, "search"), compound="left")
        self.search_label.pack(side="left", padx=(0, 8))
        self.search_scope = tk.StringVar(value="Notes")
        self.search_scope_control = ttk.Combobox(searchbar, textvariable=self.search_scope,
                                                values=("Notes", "PDFs", "All"), state="readonly", width=7)
        self.search_scope_control.pack(side="left", padx=(0, 8))
        Tooltip(self.search_scope_control, "Browse or search Notes, PDFs, or All in the selected folder, paper, and collection.")
        self.search = tk.StringVar()
        self.search_fields = list(DEFAULT_SEARCH_FIELDS)
        self.search_mode = "Words / Boolean"
        self.note_type = "All notes"
        self.search_entry = ttk.Entry(searchbar, textvariable=self.search, width=52)
        EntryPlaceholder(self.search_entry, lambda: {"Notes": "Search notes…", "PDFs": "Search PDF text…",
            "All": "Search notes and PDF text…"}.get(self.search_scope.get(), "Search notes and PDF text…"), self.search)
        self.search_scope.trace_add("write", self.search_entry.placeholder.refresh)
        Tooltip(self.search_entry, 'Search within the chosen folder, paper, and collection or tag. Spaces mean AND; uppercase AND, OR, NOT, quotes and parentheses are supported. Surrounding note text is off by default in Search filters. PDF results match within one page; scanned pages need a text layer.')
        self.search_scope.trace_add("write", self.search_scope_changed)
        self.search_options_button = Button(searchbar, text="Search filters…", command=self.search_options)
        self.search.trace_add("write", self.search_changed)
        self.note_count = tk.StringVar()
        self.note_count_label = ttk.Label(searchbar, textvariable=self.note_count, style="Muted.TLabel", anchor="e")
        self.note_count_label.pack(side="right", padx=(10, 0))
        self.search_progress = ttk.Progressbar(searchbar, mode="indeterminate", length=70)
        Tooltip(self.note_count_label, self.search_progress_help)
        Tooltip(self.search_progress, self.search_progress_help)
        self.search_options_button.pack(side="right", padx=(8, 0))
        self.clear_search_button = Button(searchbar, text="Clear search", command=self.clear_search, style="Compact.TButton", state="disabled")
        self.clear_search_button.pack(side="right", padx=(8, 0))
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<Escape>", self.clear_search)
        self.search_summary = tk.StringVar()
        self.search_summary_label = ttk.Label(controls, textvariable=self.search_summary, style="Muted.TLabel")
        self.search_error = tk.StringVar()
        self.search_error_label = ttk.Label(controls, textvariable=self.search_error, style="Error.TLabel", wraplength=800)
        self.search_warning = tk.StringVar()
        self.search_warning_label = ttk.Label(controls, style="Muted.TLabel", wraplength=800)
        Tooltip(self.search_warning_label, lambda: self.search_warning.get())
        self.reader_pane = ttk.Panedwindow(tab, orient="horizontal")
        self.reader_pane.pack(fill="both", expand=True)
        left = ttk.Frame(self.reader_pane, width=280, padding=(0, 0, 16, 0))
        left.pack_propagate(False)
        self.notes = self.tree(left, [("paper", "Paper", 230), ("page", "Page", 55), ("kind", "Type", 80),
                                     ("text", "Match", 210)], empty_text="No matching results")
        self.notes.heading("paper", command=lambda: self.sort_reader("paper"))
        self.notes.heading("kind", command=lambda: self.sort_reader("kind"))
        self.notes.heading("page", command=lambda: self.sort_reader("page"))
        self.notes.bind("<<TreeviewSelect>>", self.preview)
        self.notes.bind("<ButtonRelease-1>", self.activate_reader_result, add="+")
        bind_item_open(self.notes, lambda row: self.open_entry_pdf(self.entries[int(row)]))
        self.notes.tooltip.extra = self.note_tooltip_help
        self.notes.tooltip.value = self.note_cell_value
        self.notes.tooltip.full_with_help = True
        self.reader_pane.add(left, weight=1)
        self.reader_results_pane = left
        self.reader_expanded = False
        right = ttk.Frame(self.reader_pane)
        buttons = self.reader_header = ttk.Frame(right)
        buttons.pack(fill="x", pady=(0, 6))
        self.show_details = tk.BooleanVar(value=False)
        self.style.layout("ReaderContent.TNotebook.Tab", [])
        self.style.layout("ReaderView.TRadiobutton", self.style.layout("TNotebook.Tab"))
        self.style.configure("ReaderView.TRadiobutton", padding=(10, 6), background="#2b2b2b", foreground="#AAB0B5")
        self.style.map("ReaderView.TRadiobutton", background=[("selected", "#1B629B"), ("active", "#343638")],
                       foreground=[("selected", "white")])
        view_choices = ttk.Frame(buttons)
        view_choices.pack(side="left", padx=(0, 8))
        self.reader_view = tk.StringVar(value="pdf")
        self.note_view_button = ttk.Radiobutton(view_choices, text="Note view", variable=self.reader_view, value="note",
            style="ReaderView.TRadiobutton", command=lambda: self.reader_views.select(self.note_details))
        self.pdf_view_button = ttk.Radiobutton(view_choices, text="PDF view", variable=self.reader_view, value="pdf",
            style="ReaderView.TRadiobutton", command=lambda: self.reader_views.select(self.pdf_reader))
        self.note_view_button.pack(side="left")
        self.pdf_view_button.pack(side="left")
        Tooltip(self.note_view_button, "Read the selected note's text, comments, handwriting transcription and drawing close-up. The main search and PDF position stay the same.")
        Tooltip(self.pdf_view_button, "Read the full PDF at the selected result. Switching views keeps the PDF zoom, position and current search.")
        self.source_button = Button(buttons, text="Open externally", command=self.open_source_external)
        self.source_button.pack(side="left", padx=(0, 6))
        self.reader_expand_button = Button(buttons, text="Reading mode", command=self.toggle_reader_expanded)
        self.reader_expand_button.pack(side="left", padx=(0, 6))
        Tooltip(self.reader_expand_button, lambda: "Exit reading mode and restore the previous view, layout and zoom while keeping your current PDF reading position." if self.reader_expanded else
                "Give the PDF the full Reader area at 125% zoom. Main-match arrows and Ctrl+double-click reset to 125% here; normal mode resets to Fit width. Exit restores your previous view and zoom.")
        self.match_toolbar = buttons
        self.match_count = tk.StringVar()
        self.match_display = tk.StringVar(value="No results")
        self.match_count_label = ttk.Label(buttons, textvariable=self.match_display, style="Muted.TLabel")
        self.match_count_label.pack(side="right", padx=(6, 0))
        Tooltip(self.match_count_label, lambda: self.match_count.get() + ". The arrows follow the main result list, separately from Find in PDF.")
        self.match_actions = buttons
        self.next_match_button = Button(buttons, text="Next match", command=lambda: self.navigate_match(1), state="disabled")
        self.previous_match_button = Button(buttons, text="Previous match", command=lambda: self.navigate_match(-1), state="disabled")
        self.next_match_button.pack(side="right", padx=(4, 0))
        self.previous_match_button.pack(side="right", padx=(4, 0))
        for button in (self.previous_match_button, self.next_match_button):
            Tooltip(button, lambda current=button: ("Only one main-search match or result is available. " if current.instate(["disabled"]) and self.entries else
                "Choose a result first. " if not self.entries else "") +
                "Move through actual main-search hits in reading order, across occurrences, pages and papers. Reset to 125% in Reading mode or Fit width normally, keeping the page centered. This returns from Find in PDF to the blue main-search marks.")
        self.reader_views = ttk.Notebook(right, style="ReaderContent.TNotebook")
        self.reader_views.pack(fill="both", expand=True)
        self.note_details = ttk.Frame(self.reader_views)
        self.note_document_title = DocumentTitle(self.note_details)
        self.preview_actions = actions = WrapToolbar(self.note_details)
        actions.pack(fill="x", pady=(0, 8))
        self.full_page_button = actions.add(Button(actions, text="Full page context", command=self.full_page_context, state="disabled"))
        self.enlarge_button = actions.add(Button(actions, text="Enlarge image", command=self.enlarge))
        self.copy_image_button = actions.add(Button(actions, text="Copy image", command=self.copy_note_image, state="disabled"))
        Tooltip(self.copy_image_button, "Copy the loaded drawing or PDF page image at its original resolution, including temporary search highlights. Click the inline image and press Ctrl+C, or right-click it.")
        Tooltip(self.enlarge_button, lambda: "Inspect this PDF page or drawing. Ctrl + drag to pan, Ctrl + scroll to zoom, and Ctrl + double-click to reset the view." if self.image else
                "Select a drawing or handwriting note with a loaded close-up in Note view. Use PDF view to read its document.")
        Tooltip(self.full_page_button, lambda: "Open the complete PDF page, including retained margins. Ctrl + drag to pan, Ctrl + scroll to zoom, and Ctrl + double-click to reset the view. Generated on demand; Copy image copies the complete page." if self.selected_entry() and self.selected_entry()["kind"] in {"drawing", "pdf"} else
                "Select a drawing, handwriting note, or PDF text result first. Highlights can be read in PDF view.")
        self.expand_matches_button = actions.add(Button(actions, text="Show all matches", command=self.toggle_match_excerpts))
        actions.set_visible(self.expand_matches_button, False)
        text_frame = ttk.Frame(self.note_details)
        text_frame.pack(fill="both", expand=True)
        self.preview_text = tk.Text(text_frame, height=6, width=35, wrap="word", state="disabled", **text_options())
        self.preview_text.configure(spacing1=2, spacing3=2)
        self.preview_text.tag_configure("section_label", font=("Segoe UI", 9, "bold"), foreground=self.style.lookup("Muted.TLabel", "foreground"))
        self.preview_text.tag_configure("document_warning", foreground="#FFB4AB")
        self.preview_text.tag_configure("search_match", background="#B9D1FF", foreground="#14254A")
        self.preview_text.tag_configure("current_search_match", background="#4169E1", foreground="white")
        self.preview_text.tag_raise("sel")
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
        Tooltip(self.source_button, self.external_pdf_help)
        self.pdf_reader = PDFReader(self.reader_views, self.load_reader_document, self.open_source_external,
                                    self.toggle_reader_expanded, reuse=self.reuse_reader_document)
        self.reader_views.add(self.note_details, text="Note view")
        self.reader_views.add(self.pdf_reader, text="PDF view")
        self.reader_views.select(self.pdf_reader)
        self.reader_views.bind("<<NotebookTabChanged>>", self.reader_view_changed)
        self.reader_pane.add(right, weight=1)
        self.initial_split(self.reader_pane, .38)
