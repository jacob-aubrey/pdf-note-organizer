import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox
from . import APP_NAME
from .library_paths import resolve_data_directory, should_import_legacy
from .storage import Store
from .branding import set_process_identity, apply_app_icon


def main():
    from multiprocessing import freeze_support
    freeze_support()
    set_process_identity()
    root_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    data = resolve_data_directory(root_dir)
    data.mkdir(parents=True, exist_ok=True)
    lock = open(data / "instance.lock", "a+b")
    # Each library has one worker process; separate development data stays isolated.
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
        apply_app_icon(root)
        messagebox.showinfo(APP_NAME, f"{APP_NAME} is already running.")
        root.destroy()
        lock.close()
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
                        handlers=[RotatingFileHandler(data / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")])
    logging.info("Active library: %s", data)
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except (ImportError, tk.TclError):
        root = tk.Tk()
    root.withdraw()
    app = None
    try:
        from .ui import App
        store = Store(data / "library.sqlite3")
        if should_import_legacy(data, root_dir):
            store.import_legacy([root_dir / "notes_watcher.db", root_dir / "dist" / "notes_watcher.db", root_dir.parent / "notes_watcher.db"])
        app = App(root, store, data)
        root.deiconify()
        root.mainloop()
    except Exception as exc:
        logging.exception("Application failed")
        if isinstance(exc, ModuleNotFoundError):
            message = (f"The Python running this app is missing a required package: {exc.name}.\n\n"
                       f"Active Python: {sys.executable}\n\n"
                       "Run 'Run PDF Note Organizer.ps1' from the project folder, or choose "
                       "'Notable - development library' in VS Code's Run and Debug panel. "
                       "These use the project's .venv with its installed packages.\n\n"
                       "If the project environment also needs packages, install requirements.txt using .venv's Python.")
        else:
            message = f"Unable to start: {exc}"
        messagebox.showerror(APP_NAME, f"{message}\n\nDetails: {data / 'app.log'}")
        root.destroy()
    finally:
        if app is not None:
            app.pdf_reader.close()
            app.inbox.stop()
            app.workflow_executor.shutdown(wait=True, cancel_futures=True)
            app.service.stop()
            app.query_cancel.set()
            app.preview_cancel.set()
            app.pdf_worker.cancel()
            app.context_executor.shutdown(wait=True, cancel_futures=True)
            app.query_executor.shutdown(wait=True, cancel_futures=True)
            if app.service.thread:
                app.service.thread.join()
            app.pdf_worker.shutdown(wait=True)
            app.pdf_reader.wait_closed()
        lock.close()


if __name__ == "__main__":
    main()
