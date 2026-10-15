"""Disposable-file Windows recycle smoke and private-desktop review captures."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from note_organizer import library_files
from note_organizer.storage import canonical, digest_file
from tests.reader_app_regression import capture_test_window, require_private_desktop
from tests.test_library_review_files import LibraryReviewFileTests


def recycle_bin_count(drive):
    class BinInfo(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("bytes", ctypes.c_longlong), ("items", ctypes.c_longlong)]
    shell = ctypes.OleDLL("shell32")
    shell.SHQueryRecycleBinW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(BinInfo))
    shell.SHQueryRecycleBinW.restype = ctypes.c_long
    info = BinInfo()
    info.size = ctypes.sizeof(info)
    library_files._hresult(shell.SHQueryRecycleBinW(drive, ctypes.byref(info)))
    return info.items


def main():
    require_private_desktop()
    case = LibraryReviewFileTests("test_local_rows_replace_dropdown_and_drive_actions_details_and_copy")
    case.setUp()
    try:
        review, registry, sources, paths = case.file_review()
        assert paths[0].resolve().is_relative_to(ROOT / ".test-tmp"), "Only disposable workspace files may be recycled."
        original = paths[0].read_bytes()
        before_history = {source["id"]: registry.revisions(source["id"]) for source in sources}
        before_notes = len(case.store.entries())
        with case.store.connect() as db:
            annotation_history = [tuple(row) for row in db.execute("SELECT * FROM history ORDER BY id")]
        root = case.root
        root.attributes("-alpha", 0)
        root.geometry("1100x760+0+0")
        root.deiconify()
        review.window.attributes("-alpha", 1)
        review.window.geometry("1100x780+0+0")
        review.window.deiconify()
        case.select_copy(review, paths[1])
        for _ in range(10):
            root.update()
            time.sleep(.02)
        capture_test_window(review.window, ROOT / ".test-tmp" / "library-review-selectable-copies.png")
        help_window = case.app.help()
        help_window.geometry("1000x760+0+0")
        help_window.attributes("-alpha", 1)
        help_window.deiconify()
        for _ in range(10):
            root.update()
            time.sleep(.02)
        capture_test_window(help_window, ROOT / ".test-tmp" / "help-documentation-buttons.png")
        help_window.destroy()
        # This is a real Shell recycle of one generated test PDF. A guard held
        # across PerformOperations must reject an editor's attempt to write.
        native_call = library_files._com_call
        blocked_writes = []
        def verify_guard(pointer, index, argument_types=(), *arguments):
            if index == 21:
                try:
                    with paths[1].open("r+b"):
                        pass
                except OSError:
                    blocked_writes.append(True)
                else:
                    raise AssertionError("A writer was allowed during recycling.")
            return native_call(pointer, index, argument_types, *arguments)
        proof = library_files.reviewed_pdf(paths[1], case.pc, sources[1]["digest"])
        bin_count = recycle_bin_count(paths[1].anchor)
        # A changed revision must fail even at the final native guard, after a
        # DeleteItem has been queued but before PerformOperations can run.
        try:
            library_files._recycle_windows(str(paths[0]), "0" * 64)
        except ValueError:
            pass
        else:
            raise AssertionError("The native guard accepted a different PDF revision.")
        assert paths[0].read_bytes() == original
        with patch.object(library_files, "_com_call", side_effect=verify_guard):
            deleted = case.app.service.storage_action("recycle_pdf", proof)
        assert deleted == canonical(paths[1])
        assert blocked_writes == [True]
        assert not paths[1].exists()
        assert recycle_bin_count(paths[1].anchor) > bin_count, "The generated PDF did not enter Recycle Bin."
        assert paths[0].read_bytes() == original
        assert len(case.store.entries()) == before_notes
        assert {source["id"]: registry.revisions(source["id"]) for source in sources} == before_history
        with case.store.connect() as db:
            assert [tuple(row) for row in db.execute("SELECT * FROM history ORDER BY id")] == annotation_history
        records = {row["path"]: row for row in case.store.documents()}
        assert records[canonical(paths[1])]["missing"] and not records[canonical(paths[0])]["missing"]
        print("Real Windows recycle passed: generated PDF removed, other copy unchanged, notes and revisions preserved, writer denied during operation.")
        print("Captures: .test-tmp/library-review-selectable-copies.png and .test-tmp/help-documentation-buttons.png")
        assert not case.errors, case.errors
    finally:
        case.tearDown()


if __name__ == "__main__":
    main()
