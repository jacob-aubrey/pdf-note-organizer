"""Manual visual QA against isolated synthetic files, never personal watched folders."""
from pathlib import Path
import sys
import tkinter as tk
from note_organizer.storage import Store
from note_organizer import APP_NAME
from note_organizer.ui import App
from tests.test_notebook import sample_pdf

def main():
    from multiprocessing import freeze_support
    freeze_support()
    folder = Path("tmp/qa/app").resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if not (folder / "paper.pdf").exists():
        sample_pdf(folder / "paper.pdf")
    store = Store(folder / "library.sqlite3")
    project_id = store.add_project(folder)
    store.mark_dirty(project_id)
    root = tk.Tk()
    app = App(root, store, folder)
    root.title(f"{APP_NAME} - synthetic example")
    if "--small" in sys.argv:
        root.geometry("940x620")
    if "--auto-close" in sys.argv:
        root.after(180000, app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
