"""Compact preferences and reusable processing controls."""
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .library_paths import library_diagnostics
from .theme import BACKGROUND
from .viewers import VIEWERS, find_viewer
from .icons import Button
from .widgets import Tooltip, PathField, SelectionDetails, ScrollFrame, WrapToolbar, annotate_buttons, bind_dialog_close, fit_dialog


class ProcessingFields:
    """The same controls edit folder settings or defaults for future folders."""

    def __init__(self, parent, settings):
        self.group = tk.StringVar(value=settings.get("grouping", "Nearby blocks"))
        self.gap = tk.StringVar(value=str(settings.get("gap", 24)))
        self.margin = tk.StringVar(value=str(settings.get("context_padding", 36)))
        self.ocr = tk.BooleanVar(value=settings.get("ocr", False))
        self.layout = tk.StringVar(value=settings.get("notebook_style", "Reading"))
        self.ocr_available = bool(shutil.which("tesseract"))
        labels = ["Group handwriting", "Join strokes within (points)", "Context margin (points)", "Word layout"]
        for row, label in enumerate(labels):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 16), pady=5)
        group = ttk.Combobox(parent, textvariable=self.group, state="readonly", width=20,
                             values=["Nearby blocks", "Nearby lines", "Whole page"])
        group.grid(row=0, column=1, sticky="w")
        gap = ttk.Spinbox(parent, textvariable=self.gap, from_=4, to=100, width=8)
        gap.grid(row=1, column=1, sticky="w")
        margin = ttk.Spinbox(parent, textvariable=self.margin, from_=8, to=200, width=8)
        margin.grid(row=2, column=1, sticky="w")
        layout = ttk.Combobox(parent, textvariable=self.layout, state="readonly", values=["Reading", "Detailed"], width=20)
        layout.grid(row=3, column=1, sticky="w")
        ocr = ttk.Checkbutton(parent, text="Suggest handwriting transcription", variable=self.ocr)
        ocr.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 4))
        Tooltip(group, "Nearby blocks joins adjacent letters and lines. Nearby lines uses less vertical joining. Whole page keeps a page's drawings in one note.")
        Tooltip(gap, "Distance used to join nearby drawing strokes. Whole page groups drawings regardless of this value; highlights and typed comments remain separate notes.")
        Tooltip(margin, "Printed text and figures retained around a drawing. Complete intersecting text lines and drawing blocks can extend the crop beyond this margin. Larger margins create larger previews.")
        Tooltip(layout, "Reading organizes quotations and notes by paper and page. Detailed adds extraction metadata. Reliable overlapping drawing previews can share one screenshot; uncertain matches retain their separate previews.")
        Tooltip(ocr, "Optional local handwriting transcription. Check the suggestions against the source PDF. Requires Tesseract.")
        self.explanation = tk.StringVar()
        ttk.Label(parent, textvariable=self.explanation, wraplength=510, style="Muted.TLabel").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
        def explain(*_):
            whole_page = self.group.get() == "Whole page"
            gap.configure(state="disabled" if whole_page else "normal")
            grouping = {"Whole page": "All drawings on a page stay together.",
                        "Nearby lines": "A smaller vertical joining distance keeps nearby lines more separate.",
                        "Nearby blocks": "Adjacent letters and lines are joined into readable blocks."}.get(
                            self.group.get(), "Choose how nearby pen strokes are grouped.")
            availability = " Local transcription is available." if self.ocr_available else " Local transcription is unavailable; previews still work."
            layout_help = " Reading keeps quotations and notes concise." if self.layout.get() == "Reading" else " Detailed also includes extraction metadata."
            self.explanation.set(grouping + layout_help + availability)
        self.group.trace_add("write", explain)
        self.layout.trace_add("write", explain)
        explain()
        # Keep precision controls available without making first-time setup busy.
        self.advanced = tk.BooleanVar(value=False)
        precision = [widget for widget in parent.winfo_children() if widget.winfo_manager() == "grid" and int(widget.grid_info()["row"]) in {1, 2}]
        for widget in parent.winfo_children():
            if widget.winfo_manager() == "grid" and int(widget.grid_info()["row"]) >= 1:
                widget.grid_configure(row=int(widget.grid_info()["row"])+1)
        def advanced():
            for widget in precision:
                widget.grid() if self.advanced.get() else widget.grid_remove()
        advanced_toggle = ttk.Checkbutton(parent, text="Advanced: stroke distance & context margin", variable=self.advanced, command=advanced)
        advanced_toggle.grid(row=1, column=0, columnspan=2, sticky="w", pady=5)
        Tooltip(advanced_toggle, "Show precise stroke joining and context crop settings. The example illustrates how the grouping mode treats nearby handwriting.")
        advanced()
        preview = tk.Canvas(parent, width=300, height=48, background=BACKGROUND, highlightthickness=0, takefocus=False)
        preview.grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))
        def draw(*_):
            preview.delete("all")
            whole = self.group.get() == "Whole page"
            lines = self.group.get() == "Nearby lines"
            boxes = [(8, 5, 292, 43)] if whole else [(8, 5, 140, 21), (8, 27, 140, 43), (158, 5, 292, 43)] if lines else [(8, 5, 140, 43), (158, 5, 292, 43)]
            for box in boxes:
                preview.create_rectangle(*box, outline="#87C5F5", width=2)
            for x, y in ((18, 13), (18, 35), (168, 13), (168, 35)):
                preview.create_line(x, y, x+42, y-2, x+55, y+2, x+95, y-1, fill="#DCE4EE", width=2)
        self.group.trace_add("write", draw)
        draw()

    def values(self, parent):
        try:
            gap, margin = float(self.gap.get()), float(self.margin.get())
            if not 4 <= gap <= 100 or not 8 <= margin <= 200:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid settings", "Use a stroke distance from 4 to 100 and a margin from 8 to 200.", parent=parent)
            return None
        if self.ocr.get() and not self.ocr_available:
            messagebox.showerror("Transcription unavailable", "Install Tesseract or leave handwriting transcription off.", parent=parent)
            return None
        return {"grouping": self.group.get(), "gap": gap, "context_padding": margin,
                "ocr": self.ocr.get(), "notebook_style": self.layout.get()}


class PreferencesDialog:
    def __init__(self, app):
        self.app = app
        self.saving = False
        self.locked_controls = []
        self.window = window = tk.Toplevel(app.root)
        window.title("Settings")
        window.configure(background=BACKGROUND)
        window.transient(app.root)
        window.protocol("WM_DELETE_WINDOW", self.cancel)
        bind_dialog_close(window, self.cancel)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        self.tabs = tabs = ttk.Notebook(frame)
        tabs.pack(fill="both", expand=True)
        self.form_pages = []
        def page(title):
            form = ScrollFrame(tabs)
            tabs.add(form, text=title)
            self.form_pages.append(form)
            return form.content
        general = page("Preferences")
        library = page("Library & diagnostics")
        self.sorting = self.integration = None
        if hasattr(app, "inbox"):
            from .workflow_ui import SortingFields, IntegrationFields
            sorting_content = page("Sorting")
            self.sorting_tab = self.form_pages[-1]
            self.sorting_canvas = self.sorting_tab.canvas
            connections_tab = page("Connections")
            self.sorting = SortingFields(app, sorting_content)
            self.integration = IntegrationFields(app, connections_tab)
        Tooltip(tabs, "Preferences sets the PDF viewer and defaults for future folders. Sorting configures filing and optional naming services; Connections enables optional reMarkable features. Library & diagnostics identifies saved libraries.")
        ttk.Label(general, text="PDF viewer", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self.viewer = tk.StringVar(value=VIEWERS[app.viewer_preference["viewer"]])
        picker = ttk.Combobox(general, textvariable=self.viewer, values=list(VIEWERS.values()), state="readonly", width=44)
        picker.pack(anchor="w")
        Tooltip(picker, "Choose the application used by Library's Open PDF and exported PDF actions. Supported viewers receive the physical PDF page position. Reader's Open externally always uses the computer default viewer.")
        self.viewer_path = tk.StringVar(value=app.viewer_preference.get("path", ""))
        row = ttk.Frame(general)
        row.pack(fill="x", pady=8)
        self.path_entry = ttk.Entry(row, textvariable=self.viewer_path, width=1)
        self.browse_button = Button(row, text="Browse…", command=self.browse_viewer)
        self.browse_button.pack(side="right")
        self.viewer_path_access = PathField(self.path_entry, "For Other application, enter the full path to its .exe file.")
        self.viewer_path_copy = self.viewer_path_access.add_copy_button(row)
        self.viewer_path_copy.pack(side="right", padx=(0, 8))
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        Tooltip(self.browse_button, "Choose Other application first, then select its PDF viewer executable.")
        self.viewer_help = tk.StringVar()
        ttk.Label(general, textvariable=self.viewer_help, wraplength=510, style="Muted.TLabel").pack(anchor="w", pady=(0, 14))
        self.viewer.trace_add("write", self.viewer_changed)
        self.viewer_changed()
        ttk.Label(general, text="Defaults for new watched folders", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
        fields = ttk.Frame(general)
        fields.pack(anchor="w")
        self.processing = ProcessingFields(fields, getattr(app, "view", app.store).default_settings())
        ttk.Label(general, text="Existing folders keep their settings. Edit them in Library → Folder settings.",
                  style="Muted.TLabel", wraplength=510).pack(anchor="w", pady=(10, 0))
        ttk.Label(library, text="Active library", style="Section.TLabel").pack(anchor="w")
        library_path_row = ttk.Frame(library)
        library_path_row.pack(fill="x", pady=8)
        self.library_path_entry = ttk.Entry(library_path_row, width=1)
        self.library_path_entry.insert(0, str(app.data_dir.resolve()))
        self.library_path_entry.configure(state="readonly")
        self.library_path_entry.pack(side="left", fill="x", expand=True)
        self.library_path_access = PathField(self.library_path_entry,
            "This window reads and writes this library. Launching a different library preserves its separate notes and settings.")
        self.library_path_copy = self.library_path_access.add_copy_button(library_path_row)
        self.library_path_copy.pack(side="left", padx=(8, 0))
        actions = WrapToolbar(library)
        actions.pack(fill="x", pady=(0, 12))
        for label, action, help_text in [
            ("Open data folder", lambda: app.open_path(app.data_dir), "Open the active library's database, cache and log directory."),
            ("Library storage & backups…", lambda: app.storage_maintenance(), "Create or restore a verified backup and reclaim database storage while preserving history."),
            ("Show sync details", app.show_sync_details, "Open the latest processing log in Library."),
        ]:
            button = actions.add(Button(actions, text=label, command=action))
            Tooltip(button, help_text)
        self.diagnostics = tk.StringVar(value="Checking saved libraries…")
        self.diagnostic_paths = {}
        self.diagnostics_display = SelectionDetails(library, title="Saved libraries", height=8)
        self.diagnostics_display.set(self.diagnostics.get())
        diagnostics_trace = self.diagnostics.trace_add("write", self.update_diagnostics_display)
        self.diagnostics_display.bind("<Destroy>", lambda event: self.diagnostics.trace_remove("write", diagnostics_trace)
            if event.widget is self.diagnostics_display else None, add="+")
        self.diagnostics_display.pack(fill="both", expand=True)
        future = app.query_executor.submit(library_diagnostics, app.data_dir)
        future.add_done_callback(lambda result: app.dialog_results.put((window, self.show_diagnostics, result)))
        self.save_status = tk.StringVar()
        status = ttk.Label(frame, textvariable=self.save_status, style="Muted.TLabel", wraplength=525)
        status.pack(side="bottom", fill="x", pady=(8, 0), before=tabs)
        buttons = ttk.Frame(frame)
        # Reserve the actions before the expanding notebook on shorter screens.
        buttons.pack(side="bottom", fill="x", pady=(14, 0), before=status)
        cancel = Button(buttons, text="Cancel", command=self.cancel)
        self.save_button = apply = Button(buttons, text="Save preferences", command=self.save, style="Primary.TButton")
        apply.pack(side="right")
        cancel.pack(side="right", padx=(0, 8))
        Tooltip(apply, "Save the edited preferences, Sorting settings and Connections switches. Pending Gemini key removal becomes permanent and turns Gemini off. Existing watched folders keep their processing settings.")
        Tooltip(buttons.winfo_children()[0], "Close without saving draft edits, including pending Gemini key removal. Your saved key stays unchanged. Preferences already being saved must finish first.")
        annotate_buttons(window)
        for form in self.form_pages:
            form.bind_content()
        fit_dialog(window, app.root)
        window.minsize(window.winfo_width(), min(400, window.winfo_height()))

    def browse_viewer(self):
        path = filedialog.askopenfilename(parent=self.window, title="Choose PDF viewer application", filetypes=[("Windows application", "*.exe")])
        if path:
            self.viewer_path.set(path)

    def viewer_changed(self, *_):
        custom = self.viewer.get() == VIEWERS["custom"]
        for widget in (self.path_entry, self.browse_button):
            widget.configure(state="normal" if custom else "disabled")
        self.viewer_help.set("This viewer opens the file normally; the requested PDF page stays visible in Reader." if custom else
                             "Supported viewers receive the physical PDF page. Windows default uses the registered application when possible.")

    def copy_path(self):
        self.window.clipboard_clear()
        self.window.clipboard_append(str(self.app.data_dir.resolve()))

    def update_diagnostics_display(self, *_):
        self.diagnostics_display.set(self.diagnostics.get(), paths=self.diagnostic_paths)

    def show_diagnostics(self, future):
        try:
            result = future.result()
        except Exception as exc:
            self.diagnostic_paths = {}
            self.diagnostics.set(f"Library details unavailable: {exc}")
            return
        active = result["active"]
        lines = [f"{active['name']} · {active.get('documents', 0)} stored papers · {active.get('notes', 0)} stored notes"]
        if active.get("error"):
            lines.append(active["error"])
        self.diagnostic_paths = {}
        for number, alternate in enumerate(result["alternatives"], start=1):
            self.diagnostic_paths[f"{number}. {alternate['name']}"] = (str(alternate["path"]),
                "This is another saved app library with separate notes and settings. This window uses the active library above.")
            lines.append(f"\nOther saved library: {alternate['name']}\n{alternate['path']}\n"
                         f"{alternate.get('documents', 0)} stored papers · {alternate.get('notes', 0)} stored notes. This window uses the active library above.")
        if not result["alternatives"]:
            lines.append("\nNo other saved app library was found.")
        lines.append("\nLibraries and their pairing credentials are kept separate. No databases are merged or moved.")
        self.diagnostics.set("\n".join(lines))
        fit_dialog(self.window, self.app.root)

    def save(self):
        if self.saving:
            return
        settings = self.processing.values(self.window)
        if settings is None:
            return
        viewer = next(key for key, label in VIEWERS.items() if label == self.viewer.get())
        preference = {"viewer": viewer}
        if viewer == "custom":
            path = Path(self.viewer_path.get().strip())
            if not path.is_file() or path.suffix.lower() != ".exe":
                messagebox.showerror("Choose an application", "Browse to the PDF viewer's .exe file.", parent=self.window)
                return
            preference["path"] = str(path.resolve())
        elif viewer != "system" and not find_viewer(viewer):
            messagebox.showerror("Viewer unavailable", "Choose an installed viewer or browse to Other application.", parent=self.window)
            return
        integration_changes = self.integration.changes() if self.integration else {}
        draft = self.sorting.values() if self.sorting else {}
        def complete(_=None):
            self.app.viewer_preference = preference
            self.saving = False
            if self.window.winfo_exists():
                self.window.destroy()
            if self.sorting:
                self.app.inbox_view.refresh()
        def failed(exc):
            if self.window.winfo_exists():
                self.save_status.set(f"Preferences were not saved: {exc}")
                if self.sorting:
                    self.sorting.help.set(str(exc))
                self.saving = False
                for widget, state in self.locked_controls:
                    widget.configure(state=state)
                self.locked_controls.clear()
        from .workflow_ui import background
        self.saving = True
        self.save_status.set("Saving preferences…")
        if self.sorting:
            self.sorting.help.set("Saving preferences…")
        self.lock_controls(self.window)
        background(self.app, lambda: self.app.service.save_preferences(draft, preference, settings, integration_changes),
                   complete, failed)

    def cancel(self):
        if not self.saving:
            self.window.destroy()

    def lock_controls(self, parent):
        for widget in parent.winfo_children():
            if isinstance(widget, (ttk.Button, ttk.Checkbutton, ttk.Entry, ttk.Combobox, ttk.Spinbox)):
                self.locked_controls.append((widget, str(widget.cget("state"))))
                widget.configure(state="disabled")
            self.lock_controls(widget)
