"""Consistent, locally bundled Lucide icons for buttons and action menus."""
from pathlib import Path
from tkinter import ttk
from PIL import Image, ImageTk

ASSETS = Path(__file__).with_name("assets") / "icons"

# Labels remain intact for keyboard help, tooltips and action identification.
BUTTON_ICONS = {
    "Actions ▾": "ellipsis", "Library actions ▾": "ellipsis", "Folder actions ▾": "folder-open", "Set up Inbox…": "settings",
    "Library storage & backups…": "files", "Create verified backup…": "save",
    "Compact library…": "refresh-cw", "Restore backup…": "rotate-ccw",
    "Tags & collections…": "folder-plus", "Saved searches…": "search",
    "Save labels": "save", "Save current search": "save", "Apply saved search": "search",
    "Delete saved search": "trash-2", "Use citation and link": "link",
    "Use citation draft": "book-open",
    "Accessible reading view…": "book-open", "Test connection": "plug",
    "Open attached file": "external-link", "Open restored library": "folder-open",
    "Review recovery archives…": "history", "Back up & remove duplicates…": "files",
    "Copy image": "copy", "Copy all text": "copy", "Citation details…": "book-open", "Export citations…": "download",
    "Find supplementary files…": "folder-search", "Look up DOI": "search", "Copy citation": "copy",
    "Save citation": "save", "Find files": "search", "Download selected…": "download",
    "Open selected link": "external-link", "Add file…": "files", "Use existing file": "files",
    "Open article": "external-link",
    "Settings": "settings", "Help": "circle-help", "Add folder…": "folder-plus",
    "Sync PDFs": "refresh-cw", "Apply & sync PDFs": "refresh-cw", "Refresh folders": "folder-sync",
    "Folder settings": "sliders-horizontal", "View notes": "notebook-pen",
    "More ▾": "ellipsis", "Connection ▾": "plug", "Connect reMarkable…": "plug",
    "Connect": "plug", "Reconnect…": "plug", "Disconnect": "unplug",
    "Change…": "pencil", "Edit setup": "pencil", "Hide setup": "chevron-up",
    "Browse…": "folder-open", "Apply folder changes": "check", "Map folder…": "folder-input",
    "Map its folder…": "folder-input", "Unlink folder…": "unlink", "Open PDF": "file-text",
    "Open review folder": "folder-open", "Dismiss": "x", "Cancel": "x", "Close": "x",
    "Open reMarkable pairing page": "external-link", "Open notebook": "book-open",
    "Export view…": "download", "Search in…": "list-filter", "Search options…": "list-filter", "Source PDF": "file-text",
    "Export annotated PDF…": "download", "Review extra PDFs…": "files", "Remove reviewed copies": "trash-2",
    "Enlarge image": "zoom-in", "Full page context": "file-image", "Reset all": "rotate-ccw",
    "Fit width": "move-horizontal", "Remove folder…": "folder-minus",
    "Fit height": "move-vertical",
    "Clear fields": "list-x", "Apply": "check", "Apply changes": "check",
    "Save preferences": "save", "Show details": "logs", "View sync details": "logs",
    "Open folder": "folder-open", "Open containing folder": "folder-open",
    "Locate moved folder…": "folder-input", "Undo last link…": "rotate-ccw",
    "Keep separate": "check", "Review again": "refresh-cw",
    "Retry selected…": "refresh-cw", "Cancel selected transfer": "x",
    "Copy selection details": "copy", "Filing recovery…": "history",
    "Map and sync…": "folder-input",
    "Show sync details": "chevron-down", "Hide sync details": "chevron-up",
    "Copy path": "copy", "Copy full path": "copy", "Copy details": "copy", "Open data folder": "folder-open",
    "Rebuild notebook…": "refresh-cw", "Open source PDF": "file-text",
    "Save editable copy…": "save",
    "Change history": "history",
    "Add documents…": "files", "Review selected": "file-search",
    "File document": "folder-input", "Skip": "skip-forward", "Refresh inbox": "refresh-cw",
    "Open inbox": "folder-open", "Open library": "folder-open",
    "Review library…": "folder-search", "Check library": "folder-search", "Link selected copies…": "link",
    "Import sorter settings…": "folder-input", "Import settings": "check",
    "Send selected PDF…": "file-up", "Transfer queue…": "list-todo",
    "Retry transfers": "refresh-cw", "Use this folder": "folder-input",
    "Retry lookup": "refresh-cw",
    "Search filters…": "list-filter", "Clear search": "x",
    "Give feedback…": "circle-help", "Check for updates…": "refresh-cw",
    "Copy report": "copy", "Open feedback email…": "external-link", "Open feedback form…": "external-link",
    "Check again": "refresh-cw", "Open release…": "external-link", "Download update…": "download", "Download source…": "download",
    "Previous match": "chevron-up", "Next match": "chevron-down",
    "Show all matches": "chevron-down", "Show fewer matches": "chevron-up",
    "Open externally": "external-link", "Reading mode": "maximize",
    "Exit reading mode": "minimize", "Retry reader": "refresh-cw",
    "Document details…": "logs",
    "Open manual": "book-open", "Open README": "file-text", "Delete selected PDF…": "trash-2",
    "Remove saved key": "trash-2",
    "Undo removal": "rotate-ccw",
}
ICON_ONLY = {"Settings", "Help", "Copy full path", "More ▾", "Dismiss", "Transfer queue…", "Connection ▾", "Clear search"}


def icon(master, name, disabled=False, logical_size=16):
    root = master._root()
    size = max(logical_size, round(logical_size * float(root.tk.call("tk", "scaling")) / (96 / 72)))
    cache = getattr(root, "_action_icons", None)
    if cache is None:
        root._action_icons = cache = {}
    key = (name, disabled, size)
    if key not in cache:
        with Image.open(ASSETS / f"{name}.png") as source:
            mask = source.getchannel("A").resize((size, size), Image.Resampling.LANCZOS)
        image = Image.new("RGBA", (size, size), "#9CA3AB" if disabled else "#DCE4EE")
        image.putalpha(mask)
        cache[key] = ImageTk.PhotoImage(image, master=root)
    return cache[key]


class Button(ttk.Button):
    """A ttk button whose icon also follows dynamic label and disabled state."""

    def __init__(self, master=None, **kwargs):
        self.icon_name = None
        self.compact = False
        self._width_cache = {}
        self._responsive_pending = None
        super().__init__(master, **kwargs)
        self._set_icon()
        # Buttons created after a dialog's tooltip pass still adapt to its row.
        # Import lazily: widgets imports Button to build its shared controls.
        self._responsive_pending = self._root().after_idle(self._register_responsive)
        self.bind("<Destroy>", self._cancel_responsive_registration, add="+")
        self.bind("<<ThemeChanged>>", self._theme_changed, add="+")

    def _theme_changed(self, _event=None):
        self._set_icon()
        controller = getattr(self.master, "_responsive_buttons", None)
        if controller is not None:
            controller.schedule()
        elif hasattr(self.master, "schedule"):
            self.master.schedule()

    def _register_responsive(self):
        self._responsive_pending = None
        from .widgets import ResponsiveButtons
        ResponsiveButtons.attach(self.master)

    def _cancel_responsive_registration(self, event):
        if event.widget is self and self._responsive_pending is not None:
            self._root().after_cancel(self._responsive_pending)
            self._responsive_pending = None

    @property
    def always_icon(self):
        return self.action_label.removesuffix(" •") in ICON_ONLY

    @property
    def retain_label(self):
        """Keep consequential actions readable until no other labels fit."""
        label = self.action_label.removesuffix(" •")
        return label == "File document" or label.split(" ", 1)[0] in {"Save", "Delete", "Remove"}

    def set_compact(self, compact):
        """Hide the visual label while retaining text, command and focus order."""
        compact = bool(compact) and not self.always_icon
        if self.compact != compact:
            self.compact = compact
            super().configure(compound="image" if compact or self.always_icon else "left")

    def measured_width(self, compact=False):
        """Measure both presentations without an idle redraw or label mutation."""
        target = "image" if compact or self.always_icon else "left"
        if target in self._width_cache:
            return self._width_cache[target]
        previous = str(self.cget("compound"))
        if previous != target:
            super().configure(compound=target)
        width = self.winfo_reqwidth()
        if previous != target:
            super().configure(compound=previous)
        self._width_cache[target] = width
        return width

    def _set_icon(self):
        self._width_cache.clear()
        label = str(self.cget("text"))
        # The dot marks active search options; it does not change the action.
        self.icon_name = BUTTON_ICONS[label.removesuffix(" •")]
        self.action_label = label
        size = 20 if label.removesuffix(" •") == "Clear search" else 16
        normal, muted = icon(self, self.icon_name, logical_size=size), icon(self, self.icon_name, True, size)
        super().configure(image=(normal, "disabled", muted),
                          compound="image" if self.compact or self.always_icon else "left")

    def configure(self, cnf=None, **kwargs):
        result = super().configure(cnf, **kwargs)
        options = {**(cnf if isinstance(cnf, dict) else {}), **kwargs}
        if any(option in options for option in ("text", "style", "padding", "width", "image")):
            self._width_cache.clear()
        if "text" in kwargs or isinstance(cnf, dict) and "text" in cnf:
            self._set_icon()
        controller = getattr(self.master, "_responsive_buttons", None)
        if controller is not None:
            controller.schedule()
        return result

    config = configure


def menu_action(menu, label, command):
    menu.add_command(label=label, command=command, image=icon(menu, BUTTON_ICONS[label]), compound="left")
