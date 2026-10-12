"""Consistent, locally bundled Lucide icons for buttons and action menus."""
from pathlib import Path
from tkinter import ttk
from PIL import Image, ImageTk

ASSETS = Path(__file__).with_name("assets") / "icons"

# Labels remain intact for keyboard help, tooltips and action identification.
BUTTON_ICONS = {
    "Copy image": "copy", "Citation details…": "book-open", "Export citations…": "download",
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
    "Export view…": "download", "Search in…": "list-filter", "Source PDF": "file-text",
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
    "Remove saved key": "trash-2",
    "Undo removal": "rotate-ccw",
}
ICON_ONLY = {"Settings", "Help", "Copy full path", "More ▾", "Dismiss"}


def icon(master, name, disabled=False):
    root = master._root()
    size = max(16, round(16 * float(root.tk.call("tk", "scaling")) / (96 / 72)))
    cache = getattr(root, "_action_icons", None)
    if cache is None:
        root._action_icons = cache = {}
    key = (name, disabled, size)
    if key not in cache:
        with Image.open(ASSETS / f"{name}.png") as source:
            mask = source.getchannel("A").resize((size, size), Image.Resampling.LANCZOS)
        image = Image.new("RGBA", (size, size), "#777E86" if disabled else "#DCE4EE")
        image.putalpha(mask)
        cache[key] = ImageTk.PhotoImage(image, master=root)
    return cache[key]


class Button(ttk.Button):
    """A ttk button whose icon also follows dynamic label and disabled state."""

    def __init__(self, master=None, **kwargs):
        self.icon_name = None
        super().__init__(master, **kwargs)
        self._set_icon()

    def _set_icon(self):
        label = str(self.cget("text"))
        # The dot marks active search options; it does not change the action.
        self.icon_name = BUTTON_ICONS[label.removesuffix(" •")]
        self.action_label = label
        normal, muted = icon(self, self.icon_name), icon(self, self.icon_name, True)
        super().configure(image=(normal, "disabled", muted),
                          compound="image" if label in ICON_ONLY else "left")

    def configure(self, cnf=None, **kwargs):
        result = super().configure(cnf, **kwargs)
        if "text" in kwargs or isinstance(cnf, dict) and "text" in cnf:
            self._set_icon()
        return result

    config = configure


def menu_action(menu, label, command):
    menu.add_command(label=label, command=command, image=icon(menu, BUTTON_ICONS[label]), compound="left")
