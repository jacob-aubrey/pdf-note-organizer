"""Paper Sorter's dark charcoal / CustomTkinter blue palette, on native ttk.

Values come from C:/Paper Sorter/src/app.py and CustomTkinter's blue theme.
No dependency on the other application, its settings, or a new UI toolkit.
"""
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk

BACKGROUND = "#242424"
SURFACE = "#2b2b2b"
PANEL = "#18191a"
FIELD = "#343638"
TEXT = "#DCE4EE"
MUTED = "#AAB0B5"
BLUE = "#1B629B"
HOVER = "#144870"
PRESSED = "#103B5C"
BORDER = "#565B5E"


def apply_theme(root):
    root.configure(background=BACKGROUND)
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", BLUE)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BACKGROUND, foreground=TEXT, font=("Segoe UI", 10), bordercolor=BORDER,
                    darkcolor=BACKGROUND, lightcolor=BACKGROUND, troughcolor=PANEL)
    style.configure("TFrame", background=BACKGROUND)
    style.configure("TLabelframe", background=BACKGROUND, bordercolor=BORDER, relief="flat")
    style.configure("TLabelframe.Label", background=BACKGROUND, foreground=MUTED, font=("Segoe UI", 10, "bold"))
    style.configure("TLabel", background=BACKGROUND, foreground=TEXT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
    style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"))
    style.configure("TButton", background=BACKGROUND, foreground=TEXT, padding=(12, 7), width=0,
                    borderwidth=0, focusthickness=1, focuscolor=TEXT)
    style.map("TButton", background=[("disabled", BACKGROUND), ("pressed", BACKGROUND), ("active", BACKGROUND)],
              foreground=[("disabled", MUTED)])
    # Nine-slice images retain rounded corners while buttons grow with their labels.
    root._button_images = []
    for color in (FIELD, BORDER, SURFACE, SURFACE, BLUE, HOVER, PRESSED, SURFACE):
        image = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
        ImageDraw.Draw(image).rounded_rectangle((0, 0, 95, 95), radius=24, fill=color)
        root._button_images.append(ImageTk.PhotoImage(image.resize((24, 24), Image.Resampling.LANCZOS), master=root))
    if "PaperButton.border" not in style.element_names():
        style.element_create("PaperButton.border", "image", root._button_images[0],
                             ("disabled", root._button_images[3]), ("pressed", root._button_images[2]),
                             ("active", root._button_images[1]), border=8, padding=0, sticky="nsew")
    # The image border controls slicing only. Without explicit zero padding it also
    # adds 16 pixels to the button's size, on top of Button.padding below.
    style.layout("TButton", [("PaperButton.border", {"sticky": "nsew", "children": [
        ("Button.focus", {"sticky": "nsew", "children": [("Button.padding", {"sticky": "nsew", "children": [
            ("Button.label", {"sticky": "nsew"})]})]})]})])
    if "PrimaryButton.border" not in style.element_names():
        style.element_create("PrimaryButton.border", "image", root._button_images[4],
                             ("disabled", root._button_images[7]), ("pressed", root._button_images[6]),
                             ("active", root._button_images[5]), border=8, padding=0, sticky="nsew")
    style.layout("Primary.TButton", [("PrimaryButton.border", {"sticky": "nsew", "children": [
        ("Button.focus", {"sticky": "nsew", "children": [("Button.padding", {"sticky": "nsew", "children": [
            ("Button.label", {"sticky": "nsew"})]})]})]})])
    for name in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(name, fieldbackground=FIELD, foreground=TEXT, insertcolor=TEXT,
                        background=FIELD, bordercolor=BORDER, arrowcolor=TEXT, padding=5)
        style.map(name, fieldbackground=[("readonly", FIELD), ("disabled", BACKGROUND)],
                  foreground=[("readonly", TEXT), ("disabled", MUTED)], selectbackground=[("!disabled", BLUE)],
                  selectforeground=[("!disabled", TEXT)])
    style.configure("Card.TFrame", background=SURFACE)
    style.configure("CardTitle.TLabel", background=SURFACE, foreground=MUTED, font=("Segoe UI", 9, "bold"))
    style.configure("Quiet.TButton", padding=(9, 6))
    style.configure("Compact.TButton", padding=(5, 3))
    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                    rowheight=30, borderwidth=0)
    style.map("Treeview", background=[("selected", BLUE)], foreground=[("selected", "#ffffff")])
    style.configure("Treeview.Heading", background=SURFACE, foreground=TEXT, padding=(8, 8), relief="flat", font=("Segoe UI", 10, "bold"))
    style.map("Treeview.Heading", background=[("active", FIELD)])
    style.configure("TNotebook", background=BACKGROUND, borderwidth=0)
    style.configure("TNotebook.Tab", background=SURFACE, foreground=MUTED, padding=(16, 8))
    style.map("TNotebook.Tab", background=[("selected", BLUE), ("active", FIELD)], foreground=[("selected", TEXT)],
              padding=[("selected", (16, 8))], expand=[("selected", (0, 0, 0, 0))],
              lightcolor=[("selected", BLUE), ("!selected", SURFACE)],
              bordercolor=[("selected", BLUE), ("!selected", SURFACE)])
    style.configure("TCheckbutton", background=BACKGROUND, foreground=TEXT, indicatorbackground=FIELD, indicatorforeground=TEXT)
    style.map("TCheckbutton", background=[("active", BACKGROUND)], indicatorbackground=[("selected", BLUE)])
    for name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(name, background=BORDER, arrowcolor=TEXT, borderwidth=0, troughcolor=PANEL)
        style.map(name, background=[("active", MUTED)])
    return style


def text_options():
    return dict(background=PANEL, foreground=TEXT, insertbackground=TEXT,
                selectbackground=BLUE, selectforeground="white", relief="flat", borderwidth=0,
                padx=12, pady=10, font=("Segoe UI", 10))
