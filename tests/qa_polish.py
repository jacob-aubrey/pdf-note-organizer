"""Disposable, offline demo of the library/reMarkable interface polish."""
from pathlib import Path
import sys
import tempfile
from tests.test_ui_audit import UIAuditTests
from tests.ui_helpers import settle_library
from note_organizer import APP_NAME


def main():
    directory = Path("tmp/test-runtime").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(directory)
    case = UIAuditTests()
    case.setUp()
    app, store, root = case.app, case.store, case.root
    for index, name in enumerate(("Aubrey_et_al_Phys_Med_Biol_2025.pdf", "Deblonde_et_al_Dalton_Transactions_2016.pdf",
                                  "Ibrahim_et_al_Materials_Today_Advances_2026.pdf")):
        path = case.pc / name
        path.touch()
        project = store.add_project(case.pc)
        store.save_scan(project, path, f"digest-{index}", "signature", "settings", {},
                        [{"key": f"mark-{index}", "kind": "highlight", "quote": "A selected passage from the source article.",
                          "page": index + 1, "rect": [1, 1, 20, 20]}])
        store.save_remarkable_item(str(index), {"name": name, "state": "review", "parent": "missing",
                                  "cloud_path": "/Literature/Research papers/Metal nanoparticles/" + name,
                                  "review_pdf": str(path), "reason_kind": "routing",
                                  "reason": "No matching PC folder. Map this cloud folder to a PC folder."})
    app.service.remarkable.vault.path.parent.mkdir(parents=True, exist_ok=True)
    app.service.remarkable.vault.path.touch()
    app.refresh()
    settle_library(app, root)
    app.tabs.select(app.remarkable_tab)
    app.cloud_review.selection_set("0")
    app.cloud_folders.selection_set("literature")
    app.cloud_review_selected()
    app.cloud_selection_changed()
    if "--library" in sys.argv:
        app.tabs.select(app.library_tab)
        app.papers.selection_set(app.papers.get_children()[0])
        app.paper_selected()
    root.title(f"{APP_NAME} - offline polish demo" + (" (Library)" if "--library" in sys.argv else ""))
    root.geometry("940x620+40+40" if "--small" in sys.argv else "1250x780+40+40")
    root.deiconify()
    root.protocol("WM_DELETE_WINDOW", root.quit)
    root.after(180000, root.quit)
    try:
        root.mainloop()
    finally:
        case.tearDown()


if __name__ == "__main__":
    main()
