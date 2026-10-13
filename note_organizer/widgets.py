"""Small reusable Tk helpers."""
import tkinter as tk
from tkinter import ttk, font
from weakref import WeakSet
from .icons import Button, menu_action
from .screens import work_area, popup_position
from .theme import BACKGROUND, SURFACE, text_options


BUTTON_HELP = {
    "Create verified backup…": "Save the library, note history, private sources and available original files in an integrity-checked backup archive.",
    "Compact library…": "Create a verified backup, share repeated note images, and reclaim unused database pages while retaining history.",
    "Restore backup…": "Verify a backup and restore an independent library with its own original file snapshots. Inbox watching and cloud services start paused.",
    "Review recovery archives…": "Compare raw recovery archives with retained baseline and tablet layer assets before reviewing backed-up cleanup.",
    "Open restored library": "Open this restored library in a separate app window with its own data and recovered original files.",
    "Save labels": "Save tags and research collections for the selected paper and all its linked copies.",
    "Save current search": "Save the current query, search fields, note type and collection filter under the entered name.",
    "Apply saved search": "Run the selected saved search within the folder and paper currently selected in Notes.",
    "Delete saved search": "Remove the selected saved search from this library. Notes and papers stay preserved.",
    "Open attached file": "Open the selected supplementary file in its default application.",
    "Use citation and link": "Use the reviewed citation for the linked paper while preserving independent source files and note history.",
    "Use citation draft": "Load this citation into the editor for review. Save citation applies the reviewed details to all linked copies.",
    "Help": "Read the workflow guide and page-number conventions.",
    "Settings": "Configure document sorting, your own optional Gemini key, the PDF viewer and processing defaults; enable optional reMarkable services or inspect the active library.",
    "Add folder…": "Watch an existing PC folder for new and changed annotated PDFs.",
    "Sync PDFs": "Check watched PC folders for new or changed PDFs and update their notes and notebooks.",
    "Folder settings": "Change extraction and Word layout for the selected watched folder.",
    "View notes": "Read the notes from the selected folder or paper.",
    "Export view…": "Save the notes currently displayed by your folder, paper and search filters to a separate Word file.",
    "Open notebook": "Open the selected folder's generated Word notebook.",
    "Enlarge image": "View the selected drawing or handwriting preview at its original size.",
    "Details": "Show annotation metadata and nearby printed text in the note preview.",
    "Search in…": "Choose searchable fields, matching rules and the types of notes to show.",
    "Show sync details": "Expand the processing log, including unavailable folders and PDF read errors.",
    "Hide sync details": "Collapse the processing log.",
    "Show details": "Open Library's sync details and the latest issue summary.",
    "View sync details": "Open Library's latest sync summary and processing log, including retained recovery copies.",
    "Change…": "Expand the reMarkable cloud source and PC destination settings.",
    "Hide setup": "Collapse setup to its saved reMarkable cloud source and PC destination summary.",
    "Edit setup": "Change the selected reMarkable cloud source and its PC destination.",
    "Copy details": "Copy the complete selected item details, including its paths.",
    "Apply folder changes": "Save this reMarkable cloud source and PC destination; automatic checks use the saved routing.",
    "Connect reMarkable…": "Pair this PC with your reMarkable account using a one-time code.",
    "Connection ▾": "Reconnect your reMarkable account or disconnect this PC. Downloaded PDFs remain on disk.",
    "Open review folder": "Open the PC holding folder for reMarkable PDFs needing attention. Its PDFs are excluded from note analysis.",
    "Open PDF": "Open the selected retained reMarkable review PDF on this PC; unsupported files keep their raw source data.",
    "Reset all": "Select every search field and restore the default matching and note-type filters.",
    "Clear fields": "Deselect the search fields so you can choose just the fields you need.",
    "Apply": "Apply the options in this dialog.",
    "Apply changes": "Save these settings and update the selected folder's PDFs.",
    "Open reMarkable pairing page": "Open reMarkable's sign-in page to generate an eight-character pairing code.",
    "Connect": "Use the one-time code to pair this PC; your account password stays with reMarkable.",
    "Dismiss": "Hide this action message. Its details remain in the sync log.",
}


class DataTable(ttk.Treeview):
    """A table with a quiet empty state that never becomes a selectable row."""

    def __init__(self, parent, empty_text="No items to show", **kwargs):
        super().__init__(parent, **kwargs)
        self.empty_label = ttk.Label(self, text=empty_text, style="Empty.TLabel", anchor="center", justify="center")
        self.bind("<Configure>", self.update_empty, add="+")

    def update_empty(self, event=None):
        if self.get_children():
            self.empty_label.place_forget()
        elif self.winfo_height() > 80:
            self.empty_label.configure(wraplength=max(60, self.winfo_width() - 40))
            self.empty_label.place(relx=.5, rely=.5, y=12, anchor="center")
        else:
            self.empty_label.place_forget()

    def insert(self, *args, **kwargs):
        row = super().insert(*args, **kwargs)
        self.empty_label.place_forget()
        return row

    def delete(self, *items):
        super().delete(*items)
        self.update_empty()


class ScrollFrame(ttk.Frame):
    """A width-fitting form with scrolling and keyboard focus kept in view."""

    def __init__(self, parent, height=440, width=540, padding=14):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, height=height, width=width, background=BACKGROUND,
                                highlightthickness=0, takefocus=False, yscrollincrement=20)
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.content = ttk.Frame(self.canvas, padding=padding)
        self.content_id = self.canvas.create_window(0, 0, window=self.content, anchor="nw")
        self.content.bind("<Configure>", self.update_region)
        self.canvas.bind("<Configure>", self.resize)

    def update_region(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def resize(self, event):
        self.canvas.itemconfigure(self.content_id, width=event.width)
        self.wrap_labels(self.content, max(80, event.width - 28))

    def wrap_labels(self, parent, width):
        for widget in parent.winfo_children():
            if isinstance(widget, ttk.Label) and int(widget.cget("wraplength") or 0):
                widget.configure(wraplength=width)
            self.wrap_labels(widget, width)

    def bind_content(self):
        def wheel(event):
            if self.canvas.bbox("all")[3] > self.canvas.winfo_height():
                self.canvas.yview_scroll(-int(event.delta / 120) or (-1 if event.delta > 0 else 1), "units")
            return "break"

        def reveal(event):
            widget = event.widget
            self.update_idletasks()
            top = widget.winfo_rooty() - self.content.winfo_rooty()
            bottom = top + widget.winfo_height()
            visible = self.canvas.canvasy(0)
            height = self.canvas.winfo_height()
            total = max(1, self.content.winfo_height())
            if top < visible:
                self.canvas.yview_moveto(max(0, top - 8) / total)
            elif bottom > visible + height:
                self.canvas.yview_moveto((bottom - height + 8) / total)

        def bind(parent):
            parent.bind("<FocusIn>", reveal, add="+")
            if not isinstance(parent, (ttk.Combobox, ttk.Spinbox, tk.Text, tk.Listbox)):
                parent.bind("<MouseWheel>", wheel, add="+")
            for child in parent.winfo_children():
                bind(child)
        bind(self.content)
        self.canvas.bind("<MouseWheel>", wheel)


class WrapToolbar(ttk.Frame):
    """Flow controls into as many rows as their measured widths require."""
    def __init__(self, parent, gap=8, **kwargs):
        super().__init__(parent, width=1, **kwargs)
        self.gap, self.controls, self.pending, self.layout = gap, [], None, None
        self.hidden = set()
        self.grid_propagate(False)
        self.bind("<Configure>", self.schedule)
        self.bind("<Destroy>", self.cancel, add="+")

    def add(self, control, visible=True):
        self.controls.append(control)
        if not visible:
            self.hidden.add(control)
        control.bind("<Configure>", self.schedule, add="+")
        self.schedule()
        return control

    def set_visible(self, control, visible):
        if visible:
            self.hidden.discard(control)
        else:
            self.hidden.add(control)
            control.place_forget()
        self.schedule()

    def schedule(self, event=None):
        if self.pending is None:
            self.pending = self._root().after_idle(self.reflow)

    def cancel(self, event=None):
        if event is None or event.widget is self:
            if self.pending is not None:
                self._root().after_cancel(self.pending)
                self.pending = None

    def reflow(self):
        self.pending = None
        controls = [control for control in self.controls if control not in self.hidden]
        widths = tuple(control.winfo_reqwidth() for control in controls)
        signature = (self.winfo_width(), tuple(zip(controls, widths)))
        if signature == self.layout:
            return
        self.layout = signature
        column = used = height = row_height = 0
        for control, width in zip(controls, widths):
            if column and used + self.gap + width > signature[0]:
                height += row_height + self.gap
                column, used, row_height = 0, 0, 0
            control.place(x=used + (self.gap if column else 0), y=height, width=width, height=control.winfo_reqheight())
            used += width + (self.gap if column else 0)
            row_height = max(row_height, control.winfo_reqheight())
            column += 1
        self.configure(height=max(1, height + row_height))


def annotate_buttons(parent):
    """Finish tooltip coverage without replacing specific contextual help."""
    for widget in parent.winfo_children():
        if isinstance(widget, (ttk.Button, ttk.Checkbutton)) and not hasattr(widget, "tooltip"):
            label = widget.cget("text").replace(" •", "")
            if label in BUTTON_HELP:
                Tooltip(widget, lambda current=widget: BUTTON_HELP.get(current.cget("text").replace(" •", ""), "Choose this action."))
        annotate_buttons(widget)


def fit_dialog(window, parent):
    """Center a compact dialog within the screen and its owning window."""
    window.update_idletasks()
    left, top, right, bottom = work_area(parent)
    width = min(window.winfo_reqwidth(), right - left - 16)
    height = min(window.winfo_reqheight(), bottom - top - 16)
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    x = max(left + 8, min(x, right - width - 8))
    y = max(top + 8, min(y, bottom - height - 8))
    window.geometry(f"{width}x{height}+{x}+{y}")


def bind_dialog_close(window, callback=None):
    """Escape follows the same guarded action as a dialog's Cancel or Close."""
    def close(event):
        (callback or window.destroy)()
        return "break"
    window.bind("<Escape>", close)


def dismiss_tooltips(event=None):
    """Cancel all hover help when navigation or window focus changes."""
    for tooltip in tuple(Tooltip._instances):
        tooltip.hide()


class Tooltip:
    """One hover popup at a time, restricted to the control under the pointer."""

    _instances = WeakSet()
    _active = None

    def __init__(self, widget, text, delay=500, allow_text=False):
        self.widget, self.text, self.delay = widget, text, delay
        self.pending = self.window = None
        widget.tooltip = self
        # Containers and whole static tables are too broad for hover help.
        self.enabled = not isinstance(widget, (tk.Frame, ttk.Frame, ttk.Notebook,
                                              tk.Canvas, tk.Text, tk.PanedWindow, ttk.Panedwindow))
        if allow_text and isinstance(widget, tk.Text):
            self.enabled = True
        if isinstance(widget, ttk.Treeview) and not callable(text):
            self.enabled = False
        Tooltip._instances.add(self)
        if not self.enabled:
            return
        widget.bind("<Enter>", self.schedule, add="+")
        for event in ("<Leave>", "<ButtonPress>", "<Destroy>"):
            widget.bind(event, self.hide, add="+")
        owner = widget.winfo_toplevel()
        if not getattr(owner, "_tooltip_dismiss_bound", False):
            owner._tooltip_dismiss_bound = True
            for event in ("<FocusOut>", "<Unmap>", "<ButtonPress>", "<<NotebookTabChanged>>"):
                owner.bind(event, dismiss_tooltips, add="+")

    def schedule(self, event=None):
        dismiss_tooltips()
        if self.enabled:
            try:
                self.pending = self.widget.after(self.delay, self.show)
            except tk.TclError:
                pass

    def pointer_over(self):
        """Recheck delayed help; focus alone or an obscured control never qualifies."""
        try:
            if not self.enabled or not self.widget.winfo_exists() or not self.widget.winfo_viewable():
                return False
            owner = self.widget.winfo_toplevel()
            focused = owner.focus_displayof()
            if focused is None or focused.winfo_toplevel() != owner:
                return False
            x, y = self.widget.winfo_pointerxy()
            if self.widget.winfo_containing(x, y) != self.widget:
                return False
            if isinstance(self.widget, ttk.Treeview):
                local_x, local_y = x - self.widget.winfo_rootx(), y - self.widget.winfo_rooty()
                return (self.widget.identify_region(local_x, local_y) == "cell"
                        and bool(self.widget.identify_row(local_y)))
            return True
        except tk.TclError:
            return False

    def show(self):
        self.hide()
        if not self.pointer_over():
            self.hide()
            return
        text = self.text() if callable(self.text) else self.text
        if not text:
            self.hide()
            return
        dismiss_tooltips()
        if not self.pointer_over():
            return
        window = self.window = tk.Toplevel(self.widget)
        window.withdraw()
        window.overrideredirect(True)
        point = self.widget.winfo_pointerxy()
        left, top, right, bottom = work_area(self.widget, point)
        maximum_width = max(80, right - left - 16)
        maximum_height = max(40, bottom - top - 16)
        width = min(356, maximum_width)
        label = ttk.Label(window, text=text, padding=8, wraplength=max(32, width-16), relief="solid", style="Tooltip.TLabel")
        label.pack()
        window.update_idletasks()
        # A long path can need a wider tooltip to remain inside this monitor.
        while window.winfo_reqheight() > maximum_height and width < maximum_width:
            width = min(maximum_width, width + 160)
            label.configure(wraplength=max(32, width-16))
            window.update_idletasks()
        x, y = self.popup_position()
        window.geometry(f"+{x}+{y}")
        window.deiconify()
        Tooltip._active = self

    def popup_position(self):
        point = self.widget.winfo_pointerxy()
        return popup_position(point, (self.window.winfo_reqwidth(), self.window.winfo_reqheight()),
                              work_area(self.widget, point))

    def hide(self, event=None):
        pending, self.pending = self.pending, None
        window, self.window = self.window, None
        if Tooltip._active is self:
            Tooltip._active = None
        if pending is not None:
            try:
                self.widget.after_cancel(pending)
            except tk.TclError:
                pass
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass


class CellTooltip(Tooltip):
    """Reveal the cell under the pointer, only when its content is clipped."""

    def __init__(self, tree, value=None, extra=None):
        self.cell = None
        self.value = value
        self.extra = extra
        super().__init__(tree, self.cell_text)
        tree.bind("<Motion>", self.motion, add="+")
        for event in ("<MouseWheel>", "<Configure>", "<<TreeviewSelect>>"):
            tree.bind(event, self.reset, add="+")

    def reset(self, event=None):
        self.cell = None
        self.hide()

    def identify(self, x, y):
        tree = self.widget
        if tree.identify_region(x, y) != "cell":
            return None
        row, display = tree.identify_row(y), tree.identify_column(x)
        if not row or not display or display == "#0":
            return None
        columns = tree.cget("displaycolumns")
        if columns == ("#all",):
            columns = tree.cget("columns")
        index = int(display[1:]) - 1
        return (row, str(columns[index]), display) if index < len(columns) else None

    def motion(self, event):
        cell = self.identify(event.x, event.y)
        if cell != self.cell:
            self.reset()
            self.cell = cell
            if cell:
                self.schedule()

    def cell_text(self):
        tree = self.widget
        x, y = tree.winfo_pointerxy()
        current = self.identify(x - tree.winfo_rootx(), y - tree.winfo_rooty())
        if not self.cell or current != self.cell:
            return ""
        row, column, display = current
        box = tree.bbox(row, display)
        if not box:
            return ""
        text = str(tree.set(row, column))
        full = str(self.value(row, column)) if self.value else text
        extra = self.extra(row, column) if self.extra else ""
        x, _, width, _ = box
        visible = max(0, min(x + width, tree.winfo_width() - 2) - max(2, x) - 12)
        style = ttk.Style(tree)
        face = style.lookup(tree.cget("style") or "Treeview", "font") or "TkDefaultFont"
        clipped = font.Font(root=tree, font=face).measure(text) > visible or x < 0
        if extra:
            return f"{full}\n\n{extra}" if clipped or full != text or getattr(self, "full_with_help", False) else extra
        return full if clipped or full != text else ""

    def popup_position(self):
        return super().popup_position()


def path_values(paths):
    """Normalize explicitly supplied locations; never infer paths from prose."""
    result = {}
    for label, value in (paths or {}).items():
        path, help_text = value if isinstance(value, tuple) else (value, str(label))
        if path:
            result[str(label)] = (str(path), str(help_text))
    return result


class PathTextTooltip(Tooltip):
    """Full path and context on hover over known path spans in a text panel."""

    def __init__(self, text):
        self.spans = []
        self.current = None
        super().__init__(text, self.path_text, allow_text=True)
        text.bind("<Motion>", self.motion, add="+")
        for event in ("<MouseWheel>", "<Configure>"):
            text.bind(event, self.reset, add="+")

    def set_paths(self, paths):
        self.reset()
        self.spans = []
        for label, (path, help_text) in path_values(paths).items():
            position = "1.0"
            while found := self.widget.search(path, position, stopindex="end", exact=True):
                end = self.widget.index(f"{found}+{len(path)}c")
                self.spans.append((found, end, path, help_text))
                position = end

    def identify(self):
        x, y = self.widget.winfo_pointerxy()
        x, y = x-self.widget.winfo_rootx(), y-self.widget.winfo_rooty()
        index = self.widget.index(f"@{x},{y}")
        box = self.widget.bbox(index)
        if not box or not (box[0] <= x < box[0]+box[2] and box[1] <= y < box[1]+box[3]):
            return None
        return next((span for span in self.spans if self.widget.compare(index, ">=", span[0])
                     and self.widget.compare(index, "<", span[1])), None)

    def motion(self, event=None):
        current = self.identify()
        if current != self.current:
            self.current = current
            self.hide()
            if current:
                self.schedule()

    def reset(self, event=None):
        self.current = None
        self.hide()

    def pointer_over(self):
        return super().pointer_over() and bool(self.identify())

    def path_text(self):
        span = self.identify()
        return f"{span[2]}\n\n{span[3]}" if span else ""


class ReadOnlyText(ttk.Frame):
    """Wrapped text that can be selected, copied and scrolled at any width."""

    def __init__(self, parent, value="", height=3, width=1, textvariable=None):
        super().__init__(parent)
        self.value = None
        self.text = tk.Text(self, height=height, width=width, wrap="word", state="disabled",
                            cursor="xterm", **text_options(background=SURFACE, compact=True))
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.scroll.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        self.text.configure(yscrollcommand=self.scroll.set)
        self.text.bind("<Control-a>", self.select_all)
        self.path_tooltip = PathTextTooltip(self.text)
        self.menu = tk.Menu(self, tearoff=False)
        menu_action(self.menu, "Copy all text", self.copy)
        self.text.bind("<Button-3>", self.popup)
        self.text.bind("<Shift-F10>", self.popup)
        self.set(textvariable.get() if textvariable is not None else value)
        if textvariable is not None:
            trace = textvariable.trace_add("write", lambda *_: self.set(textvariable.get()))
            def remove_trace(event):
                if event.widget is self:
                    textvariable.trace_remove("write", trace)
            self.bind("<Destroy>", remove_trace)

    def set(self, value, paths=None):
        changed = value != self.value
        if changed:
            self.value = value
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.insert("1.0", value)
            self.text.configure(state="disabled")
        if changed or paths is not None:
            self.path_tooltip.set_paths(paths)

    def select_all(self, event=None):
        self.text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.value)

    def popup(self, event):
        x, y = self.text.winfo_rootx() + 8, self.text.winfo_rooty() + 8
        if event.keysym != "F10":
            x, y = event.x_root, event.y_root
        try:
            self.menu.tk_popup(x, y)
        finally:
            self.menu.grab_release()
        return "break"


class PathField:
    """The same full-value hover help and compact copy action for every path."""

    def __init__(self, widget, help_text, value=None):
        self.widget = widget
        self.get_value = value or widget.get
        self.help_text = help_text
        self.copy_buttons = []
        self.copy_button = None
        self.pending_refresh = None
        widget.path_access = self
        Tooltip(widget, self.help)
        if hasattr(widget, "selection_range"):
            widget.bind("<Control-a>", self.select_all, add="+")
        for event in ("<<ComboboxSelected>>", "<KeyRelease>", "<Map>", "<FocusIn>"):
            widget.bind(event, self.refresh, add="+")
        try:
            variable = str(widget.cget("textvariable"))
        except tk.TclError:
            variable = ""
        if variable:
            command = widget.register(lambda *_: self.schedule_refresh())
            widget.tk.call("trace", "add", "variable", variable, "write", command)
            def detach(event):
                if event.widget is widget:
                    if self.pending_refresh is not None:
                        try:
                            widget._root().after_cancel(self.pending_refresh)
                        except tk.TclError:
                            pass
                        self.pending_refresh = None
                    try:
                        widget.tk.call("trace", "remove", "variable", variable, "write", command)
                    except tk.TclError:
                        pass
            widget.bind("<Destroy>", detach, add="+")

    def value(self):
        try:
            return str(self.get_value() or "")
        except tk.TclError:
            return ""

    def help(self):
        text = self.help_text() if callable(self.help_text) else self.help_text
        return "\n\n".join(part for part in (self.value(), text) if part)

    def add_copy_button(self, parent):
        button = Button(parent, text="Copy full path", command=self.copy, style="Compact.TButton")
        Tooltip(button, lambda: "\n\n".join(part for part in (self.value(), "Copy full path: copy this complete file or folder location.") if part))
        self.copy_buttons.append(button)
        self.copy_button = button
        self.refresh()
        return button

    def refresh(self, event=None):
        state = "normal" if self.value() else "disabled"
        for button in self.copy_buttons:
            if button.winfo_exists():
                button.configure(state=state)

    def schedule_refresh(self):
        # Entry's own variable trace may not have applied its new value yet.
        if self.pending_refresh is None:
            self.pending_refresh = self.widget._root().after_idle(self.finish_refresh)

    def finish_refresh(self):
        self.pending_refresh = None
        self.refresh()

    def copy(self):
        value = self.value()
        if value:
            self.widget.clipboard_clear()
            self.widget.clipboard_append(value)

    def select_all(self, event=None):
        self.widget.selection_range(0, "end")
        self.widget.icursor("end")
        return "break"


class SelectionDetails(ttk.Frame):
    """A compact, selectable and copyable place for complete paths and reasons."""

    def __init__(self, parent, title="Selection details", height=3):
        super().__init__(parent, padding=(8, 6), style="Card.TFrame")
        self.value = ""
        self.paths = {}
        self.compact = False
        header = self.header = ttk.Frame(self, style="Card.TFrame")
        header.pack(fill="x")
        title_label = ttk.Label(header, text=title, style="CardTitle.TLabel", width=1)
        title_label.pack(side="left", fill="x", expand=True)
        title_label.bind("<Configure>", lambda event: title_label.configure(wraplength=max(40, event.width)))
        self.copy_button = Button(header, text="Copy details", command=self.copy, style="Compact.TButton", state="disabled")
        self.copy_button.pack(side="right")
        Tooltip(self.copy_button, "Copy the complete selected item details, including its paths.")
        self.path_row = ttk.Frame(self, style="Card.TFrame")
        self.path_selector = ttk.Combobox(self.path_row, state="readonly", width=1)
        self.path_selector.pack(side="left", fill="x", expand=True)
        self.path_access = PathField(self.path_selector, self.selected_path_help, value=self.selected_path)
        self.path_copy_button = self.path_access.add_copy_button(self.path_row)
        self.path_copy_button.pack(side="left", padx=(6, 0))
        body = self.body = ttk.Frame(self, style="Card.TFrame")
        body.pack(fill="both", expand=True)
        self.text = tk.Text(body, height=height, width=1, wrap="word", state="disabled",
                            cursor="xterm", **text_options(background=SURFACE, compact=True))
        self.text.configure(padx=0, pady=3)
        scroll = self.scroll = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        scroll.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.bind("<Control-a>", self.select_all)
        self.path_tooltip = PathTextTooltip(self.text)

    def selected_path(self):
        return self.paths.get(self.path_selector.get(), ("", ""))[0]

    def set_compact(self, compact):
        if self.compact != compact:
            self.compact = compact
            self.arrange()

    def arrange(self):
        self.header.pack_forget()
        self.path_row.pack_forget()
        self.body.pack_forget()
        if not self.compact:
            self.header.pack(fill="x")
        if self.paths:
            self.path_row.pack(fill="x", pady=(0 if self.compact else 4, 2))
        if not self.compact or not self.paths:
            self.body.pack(fill="both", expand=True)

    def selected_path_help(self):
        return self.paths.get(self.path_selector.get(), ("", "Choose a location to copy its complete path."))[1]

    def select_all(self, event=None):
        self.text.tag_add("sel", "1.0", "end-1c")
        return "break"

    def set(self, text, selected=True, paths=None):
        self.value = text if selected else ""
        if self.text.get("1.0", "end-1c") != text:
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.insert("1.0", text)
            self.text.configure(state="disabled")
        self.paths = path_values(paths) if selected else {}
        previous = self.path_selector.get()
        self.path_selector.configure(values=list(self.paths))
        self.path_selector.set(previous if previous in self.paths else next(iter(self.paths), ""))
        self.arrange()
        self.path_access.refresh()
        self.path_tooltip.set_paths(self.paths)
        self.copy_button.configure(state="normal" if self.value else "disabled")

    def copy(self):
        if self.value:
            self.clipboard_clear()
            self.clipboard_append(self.value)
