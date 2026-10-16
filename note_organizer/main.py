import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox
from . import APP_NAME
from .library_paths import resolve_data_directory, should_import_legacy
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
    startup = None

    def prepare_library(report):
        from .storage import Store
        store = Store(data / "library.sqlite3")
        if should_import_legacy(data, root_dir):
            report("Importing existing notes…")
            store.import_legacy([root_dir / "notes_watcher.db", root_dir / "dist" / "notes_watcher.db", root_dir.parent / "notes_watcher.db"])
        return store

    def build_workspace(store):
        nonlocal app
        from .ui import App
        app = App(root, store, data)
        return app

    def startup_failed(exc):
        show_startup_error(root, data, exc)
        root.quit()

    try:
        from .startup import StartupSplash
        startup = StartupSplash(root, prepare_library, build_workspace, startup_failed)
        root.mainloop()
    except Exception as exc:
        if startup is not None:
            startup.destroy()
        show_startup_error(root, data, exc)
    finally:
        if startup is not None:
            startup.wait_closed()
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
        try:
            root.destroy()
        except tk.TclError:
            pass
        lock.close()


def show_startup_error(root, data, exc):
    logging.error("Application failed", exc_info=(type(exc), exc, exc.__traceback__))
    if isinstance(exc, ModuleNotFoundError):
        message = (f"The Python running this app is missing a required package: {exc.name}.\n\n"
                   f"Active Python: {sys.executable}\n\n"
                   "Run 'Run PDF Note Organizer.ps1' from the project folder, or choose "
                   "'Notable - development library' in VS Code's Run and Debug panel. "
                   "These use the project's .venv with its installed packages.\n\n"
                   "If the project environment also needs packages, install requirements.txt using .venv's Python.")
    else:
        message = f"Unable to start: {exc}"
    messagebox.showerror(APP_NAME, f"{message}\n\nDetails: {data / 'app.log'}", parent=root)


if __name__ == "__main__":
    main()
