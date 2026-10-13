"""Offline visual audit of every workspace and secondary window.

Run with --capture to save screenshots and geometry findings under tmp/qa.
Otherwise --screen selects a disposable interactive preview for inspection.
"""
import argparse
import ctypes
import json
from multiprocessing import freeze_support
from pathlib import Path
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

from PIL import ImageGrab
from note_organizer.archive_ui import ArchiveReviewWindow
from note_organizer.extraction import extract
from note_organizer.research_ui import review_citation_conflict
from note_organizer.service import Service
from note_organizer.storage import Store, DEFAULT_SETTINGS
from note_organizer.ui import App
from note_organizer.widgets import dismiss_tooltips
from tests.test_notebook import sample_pdf
from tests.test_preferences_ui import descendants
from tests.ui_helpers import settle_library


def main():
    freeze_support()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--scale", type=float, default=1.25)
    parser.add_argument("--small", action="store_true")
    parser.add_argument("--screen", default="notes")
    parser.add_argument("--duration", type=int, default=180)
    options = parser.parse_args()
    output = Path("tmp/qa/pristine") / f"{options.scale:g}-{'small' if options.small else 'desktop'}"
    output.mkdir(parents=True, exist_ok=True)
    runtime = Path("tmp/test-runtime").resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(runtime)
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        papers, inbox = folder / "Papers", folder / "Inbox"
        papers.mkdir()
        inbox.mkdir()
        store = Store(folder / "data/library.sqlite3")
        project = store.add_project(papers)
        for index, name in enumerate(("Catalyst stability", "Control experiment", "Supporting measurements")):
            path = papers / (name + ".pdf")
            sample_pdf(path)
            digest, signature, metadata, notes = extract(path, DEFAULT_SETTINGS)
            store.save_scan(project, path, digest, signature, "audit", {**metadata, "title": name}, notes)
        sample_pdf(inbox / "New research paper.pdf")
        store.set_preference("remarkable", {"integration_enabled": True, "pc_root": str(papers),
                                             "source_folder_id": "literature", "enabled": False})
        store.set_preference("remarkable_folders", [
            {"id": "literature", "name": "Literature", "path": "/Literature", "ancestor_ids": [], "parent": ""},
            {"id": "missing", "name": "New experiments", "path": "/Literature/New experiments",
             "ancestor_ids": ["literature"], "parent": "literature"}])
        store.save_remarkable_item("review", {"name": "Catalyst stability.pdf", "state": "review", "parent": "missing",
            "cloud_path": "/Literature/New experiments/Catalyst stability.pdf",
            "review_pdf": str(papers / "Catalyst stability.pdf"), "reason_kind": "routing",
            "reason": "This tablet folder needs a PC destination. Review both locations before mapping."})
        root = tk.Tk()
        root.withdraw()
        original_scaling = root.tk.call("tk", "scaling")
        root.tk.call("tk", "scaling", (96 / 72) * options.scale)
        errors = []
        root.report_callback_exception = lambda *args: errors.append(str(args[1]))
        with patch.object(Service, "start"):
            app = App(root, store, store.path.parent)
            settle_library(app, root)
        app.inbox.save_config({"watch_folder": str(inbox), "library_root": str(papers), "naming_mode": "Basic"})
        app.service.remarkable.vault.path.parent.mkdir(parents=True, exist_ok=True)
        app.service.remarkable.vault.path.touch()
        app.refresh()
        settle_library(app, root)
        root.title("Notable - UI audit (offline sample)")
        root.geometry("940x620+40+40" if options.small else "1250x820+40+40")
        root.deiconify()

        def settle():
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                root.update()
                app.poll()
                if not app.workflow_futures and not (app.query_future and not app.query_future.done()):
                    break
                time.sleep(.01)
            for _ in range(3):
                root.update()
                time.sleep(.03)

        settle()
        app.projects.selection_set(str(project))
        app.project_selected()
        settle()
        app.papers.selection_set(app.papers.get_children()[0])
        app.paper_selected()
        app.view_notes()
        settle()

        def settings_page(index, advanced=False):
            app.global_settings()
            dialog = app.preferences_dialog
            dialog.tabs.select(index)
            if advanced:
                dialog.processing.advanced.set(True)
                for control in descendants(dialog.window):
                    if isinstance(control, ttk.Checkbutton) and str(control.cget("text")).startswith("Advanced:"):
                        control.invoke()
                        control.invoke()
            return dialog.window

        def open_window(action):
            before = set(root.winfo_children())
            action()
            return next((w for w in root.winfo_children() if w not in before and isinstance(w, tk.Toplevel)), root)

        def drawing():
            index = next(index for index, entry in enumerate(app.entries) if entry["kind"] == "drawing")
            app.notes.selection_set(str(index))
            app.preview()
            settle()

        builders = {
            "preferences": lambda: settings_page(0),
            "preferences-advanced": lambda: settings_page(0, True),
            "diagnostics": lambda: settings_page(1),
            "sorting": lambda: settings_page(2),
            "connections": lambda: settings_page(3),
            "folder-settings": lambda: open_window(app.settings),
            "search-options": lambda: open_window(app.search_options),
            "citation": lambda: open_window(app.citation_details),
            "supplements": lambda: open_window(app.supplementary_files),
            "saved-searches": lambda: open_window(app.saved_searches),
            "labels": lambda: open_window(app.organize_paper),
            "review": lambda: app.review_library().window,
            "transfers": app.transfers,
            "pairing": lambda: open_window(app.pair_remarkable),
            "history": lambda: open_window(app.history),
            "help": lambda: open_window(app.help),
            "maintenance": lambda: app.storage_maintenance().window,
            "archives": lambda: ArchiveReviewWindow(app).window,
            "cleanup": lambda: open_window(app.review_extra_pdfs),
            "conflict": lambda: open_window(lambda: review_citation_conflict(app,
                [{"title": "Catalyst stability", "authors": ["Example Researcher"], "year": "2026"},
                 {"title": "Catalyst stability (reviewed)", "authors": ["Example Researcher"], "year": "2025"}], lambda _: None)),
        }
        workspaces = {"inbox": app.inbox_tab, "library": app.library_tab, "notes": app.notes_tab, "cloud": app.remarkable_tab}
        findings = []

        def capture(name, window):
            window.lift()
            window.attributes("-topmost", True)
            settle()
            dismiss_tooltips()
            root.update()
            handle = ctypes.windll.user32.GetParent(window.winfo_id())
            ImageGrab.grab(window=handle).save(output / f"{name}.png")
            visible_controls = []
            def selected_page(widget):
                child = widget
                while child is not window:
                    parent = child.master
                    if isinstance(parent, ttk.Notebook) and str(child) in parent.tabs() and parent.select() != str(child):
                        return False
                    child = parent
                return True
            for widget in descendants(window):
                if not isinstance(widget, (ttk.Button, ttk.Entry, ttk.Combobox, ttk.Checkbutton, ttk.Radiobutton)):
                    continue
                if widget.winfo_toplevel() != window:
                    continue
                if not selected_page(widget):
                    continue
                parent = widget.master
                if not widget.winfo_viewable():
                    if widget.winfo_manager() and parent.winfo_viewable():
                        findings.append({"screen": name, "control": str(widget.cget("text")) if "text" in widget.keys() else widget.winfo_class(),
                                         "issue": "Control was allocated no visible space"})
                    continue
                visible_controls.append(widget)
                x, y = widget.winfo_rootx() - parent.winfo_rootx(), widget.winfo_rooty() - parent.winfo_rooty()
                clipped = x < -2 or y < -2 or x + widget.winfo_width() > parent.winfo_width() + 2 or y + widget.winfo_height() > parent.winfo_height() + 2
                clipped_label = isinstance(widget, ttk.Button) and widget.winfo_width() < widget.winfo_reqwidth() - 2
                if clipped or clipped_label:
                    findings.append({"screen": name, "control": str(widget.cget("text")) if "text" in widget.keys() else widget.winfo_class(),
                                     "size": [widget.winfo_width(), widget.winfo_height()], "requested": [widget.winfo_reqwidth(), widget.winfo_reqheight()]})
            for index, first in enumerate(visible_controls):
                for second in visible_controls[index+1:]:
                    if first.master is not second.master:
                        continue
                    x_overlap = min(first.winfo_x()+first.winfo_width(), second.winfo_x()+second.winfo_width()) - max(first.winfo_x(), second.winfo_x())
                    y_overlap = min(first.winfo_y()+first.winfo_height(), second.winfo_y()+second.winfo_height()) - max(first.winfo_y(), second.winfo_y())
                    if x_overlap > 2 and y_overlap > 2:
                        findings.append({"screen": name, "issue": "Overlapping controls", "controls": [str(first), str(second)]})
            for table in descendants(window):
                if isinstance(table, ttk.Treeview) and table.winfo_viewable() and selected_page(table) and table.get_children():
                    boxes = [table.bbox(row) for row in table.get_children()]
                    if not any(box and box[1] + box[3] <= table.winfo_height() for box in boxes):
                        findings.append({"screen": name, "issue": "Table has no room for a complete row", "table": str(table),
                                         "height": table.winfo_height(), "rows": boxes, "scroll": table.yview()})
            window.attributes("-topmost", False)

        try:
            if options.capture:
                for name, tab in workspaces.items():
                    app.tabs.select(tab)
                    capture(name, root)
                app.cloud_folders.selection_set("literature")
                app.cloud_selection_changed()
                app.cloud_review.selection_set("review")
                app.cloud_review_selected()
                capture("cloud-selected", root)
                app.toggle_cloud_setup()
                capture("cloud-setup", root)
                app.toggle_cloud_setup()
                app.tabs.select(app.library_tab)
                app.activity_toggle.invoke()
                capture("library-sync", root)
                app.activity_toggle.invoke()
                app.tabs.select(app.notes_tab)
                for name, builder in builders.items():
                    window = builder()
                    if window is root:
                        raise RuntimeError(f"No dialog opened for {name}")
                    capture(name, window)
                    window.destroy()
                drawing()
                capture("drawing", root)
                enlargement = app.enlarge()
                capture("enlarge", enlargement)
                enlargement.destroy()
                context = open_window(app.full_page_context)
                if app.context_future:
                    app.context_future.result(timeout=20)
                capture("page-context", context)
                context.destroy()
                report = {"scale": options.scale, "small": options.small, "findings": findings, "callback_errors": errors}
                (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                print(json.dumps(report, indent=2))
            else:
                if options.screen in workspaces:
                    app.tabs.select(workspaces[options.screen])
                elif options.screen == "drawing":
                    drawing()
                else:
                    builders[options.screen]()
                root.after(options.duration * 1000, root.quit)
                root.protocol("WM_DELETE_WINDOW", root.quit)
                root.mainloop()
        finally:
            app.closing = True
            app.inbox.stop()
            app.service.stop()
            app.query_cancel.set()
            app.preview_cancel.set()
            app.workflow_executor.shutdown(wait=True, cancel_futures=True)
            app.query_executor.shutdown(wait=True, cancel_futures=True)
            app.context_executor.shutdown(wait=True, cancel_futures=True)
            app.pdf_worker.shutdown(wait=True)
            for callback in root.tk.call("after", "info"):
                root.after_cancel(callback)
            root.tk.call("tk", "scaling", original_scaling)
            root.destroy()


if __name__ == "__main__":
    main()
