import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox
from .storage import Store


def main():
    data = Path(os.environ.get("PDF_NOTES_DATA_DIR") or (Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PDF Note Organizer"))
    data.mkdir(parents=True, exist_ok=True)
    lock = open(data / "instance.lock", "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            if not lock.read(1):
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("PDF Note Organizer", "PDF Note Organizer is already running.")
        root.destroy()
        lock.close()
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
                        handlers=[RotatingFileHandler(data / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")])
    root = tk.Tk()
    app = None
    try:
        from .ui import App
        root_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
        icon = Path(getattr(sys, "_MEIPASS", root_dir)) / "Note icon.ico"
        if icon.exists():
            root.iconbitmap(str(icon))
        store = Store(data / "library.sqlite3")
        if os.environ.get("PDF_NOTES_SKIP_LEGACY_IMPORT") != "1":
            store.import_legacy([root_dir / "notes_watcher.db", root_dir / "dist" / "notes_watcher.db", root_dir.parent / "notes_watcher.db"])
        app = App(root, store, data)
        root.mainloop()
    except Exception as exc:
        logging.exception("Application failed")
        messagebox.showerror("PDF Note Organizer", f"Unable to start: {exc}\n\nDetails: {data / 'app.log'}")
        root.destroy()
    finally:
        if app is not None:
            app.service.stop()
            if app.service.thread:
                app.service.thread.join()
        lock.close()


if __name__ == "__main__":
    main()
