"""Window identity shared by source launches, previews and packaged builds."""
import ctypes
import logging
import os
from pathlib import Path
import sys

from PIL import Image, ImageTk


def set_process_identity():
    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Notable.Desktop")
        except (AttributeError, OSError):
            logging.debug("Windows app identity unavailable", exc_info=True)


def apply_app_icon(root):
    assets = Path(__file__).with_name("assets") / "branding"
    with Image.open(assets / "notable.png") as source:
        root._app_icons = [ImageTk.PhotoImage(source.resize((size, size), Image.Resampling.LANCZOS), master=root)
                           for size in (16, 32, 48, 64, 128, 256)]
    root.iconphoto(True, *root._app_icons)
    if os.name == "nt":
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        root.iconbitmap(default=str(base / "Note icon.ico"))
        root.iconbitmap(str(base / "Note icon.ico"))
