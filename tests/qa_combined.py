"""Source preview with synthetic inbox documents, no personal settings/cloud."""
from pathlib import Path
import tkinter as tk
from docx import Document
from note_organizer.storage import Store
from note_organizer.inbox import InboxController
from note_organizer.ui import App
from note_organizer import APP_NAME
from tests.test_notebook import sample_pdf


def main():
    from multiprocessing import freeze_support
    freeze_support()
    folder = Path("tmp/qa/combined").resolve()
    inbox, topics = folder / "Inbox", folder / "Topics"
    inbox.mkdir(parents=True, exist_ok=True)
    topics.mkdir(parents=True, exist_ok=True)
    sorted_folder = topics / "Sorted"
    sorted_folder.mkdir(exist_ok=True)
    if not (inbox / "Example_paper.pdf").exists():
        sample_pdf(inbox / "Example_paper.pdf")
    if not (inbox / "Research_protocol.docx").exists():
        document = Document()
        document.core_properties.title = "Research protocol"
        document.core_properties.author = "Example Researcher"
        document.add_paragraph("Methods and research protocol for local filing.")
        document.save(inbox / "Research_protocol.docx")
    store = Store(folder / "data" / "library.sqlite3")
    controller = InboxController(store, store.path.parent)
    controller.save_config({"watch_folder": str(inbox), "library_root": str(topics), "naming_mode": "Basic"})
    controller.stop()
    root = tk.Tk()
    app = App(root, store, store.path.parent)
    root.title(f"{APP_NAME} - isolated preview")
    root.geometry("1150x800")
    root.after(500, app.inbox_view.refresh)
    root.after(3000, app.inbox_view.refresh)
    root.after(600000, app.close)
    try:
        root.mainloop()
    finally:
        app.inbox.stop()
        app.workflow_executor.shutdown(wait=True, cancel_futures=True)
        app.query_executor.shutdown(wait=True, cancel_futures=True)
        app.context_executor.shutdown(wait=True, cancel_futures=True)
        app.pdf_worker.shutdown(wait=True)


if __name__ == "__main__":
    main()
