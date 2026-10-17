"""Actual Tk application + embedded WebView2 regression on an inactive desktop.

Run with:
    .venv/Scripts/python.exe tools/run_ui_tests.py tests/reader_app_regression.py

This intentionally is not a unittest discovery target: it starts the installed
native reader runtime and a local HTTP server. Every PDF and library is synthetic.
"""
import ctypes
from ctypes import wintypes
import multiprocessing
import os
from pathlib import Path
import re
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf as fitz
from PIL import Image

from note_organizer.storage import digest_file
from tests.test_review_controls import ReviewControlTests
from tests.ui_helpers import settle_library


def require_private_desktop():
    """Never map native test windows onto the user's working desktop."""
    if os.name != "nt":
        raise RuntimeError("This integration test exercises the Windows reader.")
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user.GetThreadDesktop.argtypes = (wintypes.DWORD,)
    user.GetThreadDesktop.restype = wintypes.HANDLE
    user.GetUserObjectInformationW.argtypes = (wintypes.HANDLE, ctypes.c_int,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    name, required = ctypes.create_unicode_buffer(256), wintypes.DWORD()
    desktop = user.GetThreadDesktop(kernel.GetCurrentThreadId())
    if not user.GetUserObjectInformationW(desktop, 2, name, ctypes.sizeof(name), ctypes.byref(required)):
        raise ctypes.WinError(ctypes.get_last_error())
    hosted = (os.environ.get("GITHUB_ACTIONS") == "true" and
              os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted" and
              os.environ.get("NOTABLE_TEST_HOSTED_RUNNER") == "1")
    if name.value != os.environ.get("NOTABLE_TEST_DESKTOP") or not (name.value.startswith("NotableTests-") or hosted):
        raise RuntimeError("Use tools/run_ui_tests.py to isolate native viewer testing.")


def make_paper(path, title):
    with fitz.open() as doc:
        for number in range(1, 4):
            page = doc.new_page(width=612, height=792)
            page.insert_text((45, 55), f"{title} - page {number}", fontsize=18)
            for line in range(4):
                x, y = (45 if line < 2 else 330), 110 + (line % 2) * 64
                page.insert_text((x, y), f"Tantalum imaging passage {line + 1}.", fontsize=12)
                page.insert_text((x, y + 16), "A selectable research sentence.", fontsize=12)
            page.insert_text((45, 330), "Iodine also appears on this research page.", fontsize=12)
            if number == 1:
                note = page.add_highlight_annot(page.search_for("Tantalum")[0])
                note.set_info(subject="reMarkable highlight", content="Tantalum", title="")
                note.update()
                rect = list(note.rect)
                genuine = page.add_highlight_annot(page.search_for("Tantalum")[1])
                genuine.set_info(subject="reMarkable highlight", content="A real reviewer comment", title="Reviewer")
                genuine.update()
        doc.save(path)
    return rect


def capture_test_window(root, destination, flags=2):
    """Capture our inactive-desktop window; native menus use PrintWindow flags=0."""
    require_private_desktop()
    user = ctypes.WinDLL("user32", use_last_error=True)
    gdi = ctypes.WinDLL("gdi32", use_last_error=True)
    user.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user.GetAncestor.restype = wintypes.HWND
    user.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
    gdi.CreateCompatibleDC.argtypes = (wintypes.HDC,)
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
    gdi.SelectObject.restype = wintypes.HGDIOBJ
    gdi.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
    gdi.DeleteDC.argtypes = (wintypes.HDC,)

    class BitmapInfoHeader(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("width", wintypes.LONG), ("height", wintypes.LONG),
            ("planes", wintypes.WORD), ("bit_count", wintypes.WORD), ("compression", wintypes.DWORD),
            ("size_image", wintypes.DWORD), ("x_pixels", wintypes.LONG), ("y_pixels", wintypes.LONG),
            ("colors_used", wintypes.DWORD), ("colors_important", wintypes.DWORD)]

    gdi.CreateDIBSection.argtypes = (wintypes.HDC, ctypes.POINTER(BitmapInfoHeader), wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD)
    gdi.CreateDIBSection.restype = wintypes.HBITMAP
    hwnd = user.GetAncestor(root.winfo_id(), 2)
    bounds = wintypes.RECT()
    if not user.GetWindowRect(hwnd, ctypes.byref(bounds)):
        raise ctypes.WinError(ctypes.get_last_error())
    width, height = bounds.right - bounds.left, bounds.bottom - bounds.top
    header = BitmapInfoHeader(ctypes.sizeof(BitmapInfoHeader), width, -height, 1, 32, 0,
        width * height * 4, 0, 0, 0, 0)
    memory = ctypes.c_void_p()
    dc = gdi.CreateCompatibleDC(None)
    bitmap = gdi.CreateDIBSection(dc, ctypes.byref(header), 0, ctypes.byref(memory), None, 0)
    if not bitmap or not memory.value:
        gdi.DeleteDC(dc)
        raise ctypes.WinError(ctypes.get_last_error())
    previous = gdi.SelectObject(dc, bitmap)
    try:
        if not user.PrintWindow(hwnd, dc, flags):
            raise ctypes.WinError(ctypes.get_last_error())
        pixels = ctypes.string_at(memory, width * height * 4)
        Image.frombytes("RGB", (width, height), pixels, "raw", "BGRX").save(destination)
    finally:
        gdi.SelectObject(dc, previous)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(dc)


def main():
    require_private_desktop()
    case = ReviewControlTests("test_saved_recovery_copies_remain_visible_after_restart")
    case.enable_pdf_reader = True
    case.setUp()
    app, root = case.app, case.root
    process = None
    sources = {}
    checks = []
    sent_matches = []
    original_send = app.pdf_reader.send

    def recording_send(payload):
        if payload.get("command") == "match":
            sent_matches.append(payload["index"])
        return original_send(payload)

    app.pdf_reader.send = recording_send

    def passed(message):
        checks.append(message)
        print("PASS:", message, flush=True)

    def wait(predicate, message, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            root.update()
            app.poll()
            if case.errors:
                raise AssertionError(f"Tk callback failed during {message}: {case.errors!r}")
            if predicate():
                return
            time.sleep(.01)
        raise AssertionError(f"Timed out: {message}; count={app.note_count.get()!r}; "
            f"selected={app.notes.selection()!r}; current_match={app.current_match_index!r}; "
            f"recent_match_requests={sent_matches[-4:]!r}; reader={app.pdf_reader.state!r}; "
            f"message={app.pdf_reader.message.get()!r}")

    def inspect():
        app.pdf_reader.inspection = None
        app.pdf_reader.send({"command": "inspect"})
        wait(lambda: app.pdf_reader.inspection is not None, "native reader inspection", timeout=8)
        return app.pdf_reader.inspection

    def available():
        assert app.search_entry.instate(["!disabled", "!readonly"])
        assert app.search_scope_control.instate(["readonly", "!disabled"])

    def search(scope, query, expected):
        app.search_scope.set(scope)
        app.search.set(query)
        app.refresh_notes()
        wait(lambda: app.note_count.get() == expected and app.notes_after is None,
            f"{scope} search {query!r} -> {expected}", timeout=30)
        available()

    def select(predicate):
        row = next(str(index) for index, entry in enumerate(app.entries) if predicate(entry))
        app.notes.selection_set(row)
        app.notes.focus(row)
        app.notes.see(row)
        app.preview()
        root.update()
        return row

    def loaded(page=None):
        wait(lambda: app.pdf_reader.loaded and app.pdf_reader.state.get("id") == app.pdf_reader.generation
            and (page is None or app.pdf_reader.state.get("page") == page),
            f"PDF loaded at page {page}", timeout=35)
        wait(lambda: app.pdf_reader.state.get("renderedPages", 0) > 0
            and app.pdf_reader.state.get("textLayers", 0) > 0,
            "rendered canvas and selectable text", timeout=20)
        assert app.pdf_reader.native
        assert app.pdf_reader.native.user.IsWindowVisible(app.pdf_reader.native.hwnd)
        state = inspect()
        assert state["loaded"] and not state["selectionOutlined"], state
        return state

    def native_match_index(entry, hit_index):
        # Both search paths must now follow the source flow through columns
        # (1,2,3,4). Verify the uniquely numbered source occurrence as well.
        hit = entry["search_hits"][hit_index]
        following = entry["context"][hit["end"]:hit["end"] + 100]
        number = re.search(r"imaging\s+passage\s+(\d+)", following, re.I)
        assert number, (hit, following)
        return int(number.group(1)) - 1

    try:
        project = case.store.add_project(case.pc)
        for name in ("Alpha", "Beta"):
            path = case.pc / f"{name} reader integration.pdf"
            rect = make_paper(path, f"{name} reader integration")
            sources[path] = path.read_bytes()
            notes = [{"key": f"{name}-first", "kind": "highlight", "page": 1,
                "rect": rect, "quote": "Tantalum imaging. Tantalum imaging."}]
            if name == "Alpha":
                notes.extend([
                    {"key": "Alpha-second", "kind": "text", "page": 2,
                     "rect": [45, 100, 400, 150], "comment": "Tantalum typed note"},
                    {"key": "Alpha-context", "kind": "highlight", "page": 3,
                     "rect": [45, 320, 400, 340], "quote": "Iodine research",
                     "context": "Tantalum is nearby, but the selected note says iodine."},
                ])
            case.store.save_scan(project, path, digest_file(path), "reader-app-regression", "{}",
                {"title": f"{name} reader integration"}, notes)
        app.refresh()
        settle_library(app, root)
        wait(lambda: app.note_count.get() == "4 notes", "initial disposable notes")
        assert "context" not in app.search_fields, app.search_fields
        root.geometry("1250x820+20+20")
        root.deiconify()
        app.tabs.select(app.notes_tab)
        root.update()
        first = select(lambda entry: entry["key"] == "Alpha-first")
        state = loaded(1)
        process = app.pdf_reader.process
        assert state["pages"] == 3 and state["hasSelection"], state
        assert state["annotationEditorMode"] == -1 and not state["renderForms"] and not state["enableScripting"], state
        assert app.pdf_reader.pending.get("suppressedPopupIds", {}).get("1"), app.pdf_reader.pending
        wait(lambda: app.pdf_reader.state.get("suppressedPopupCount", 0) >= 1,
            "verified legacy quote popup suppression reaches the PDF display layer")
        passed("native embedding, rendered selectable PDF, no selection outlines or editing, surrounding text off")
        passed("legacy quote-only popup metadata reaches native PDF display without changing highlight/source bytes")

        # Citation-only updates must cross the real native-host boundary
        # without opening the PDF again or reclaiming its current search.
        before_rename = inspect()
        original_generation = app.pdf_reader.generation
        entry = app.selected_entry()
        original_title = entry.get("logical_paper_title")
        entry["logical_paper_title"] = "Updated Alpha reader integration"
        app.preview()
        wait(lambda: app.pdf_reader.state.get("title") == entry["logical_paper_title"],
            "current document title reaches native heading")
        after_rename = inspect()
        assert app.note_document_title.title == entry["logical_paper_title"]
        assert app.pdf_reader.generation == original_generation
        for key in ("page", "scale", "scaleValue", "scroll", "findMode", "findQuery", "selectedMatch"):
            assert after_rename[key] == before_rename[key], (key, before_rename, after_rename)
        if original_title is None:
            entry.pop("logical_paper_title", None)
        else:
            entry["logical_paper_title"] = original_title
        app.preview()
        wait(lambda: app.pdf_reader.state.get("title") == "Alpha reader integration",
            "restored citation title reaches native heading")
        passed("title refresh reaches Note/PDF headings without reloading, moving the page, or resetting search")

        with patch.object(app.pdf_worker, "materialize_cancellable",
                          wraps=app.pdf_worker.materialize_cancellable) as prepare:
            select(lambda entry: entry["key"] == "Alpha-second")
            loaded(2)
        prepare.assert_not_called()
        assert app.pdf_reader.process is process
        with patch("note_organizer.ui.open_pdf_page", return_value=("Opened original", True)) as opened:
            app.source_button.invoke()
        opened.assert_called_once_with(str(next(path for path in sources if path.name.startswith("Alpha"))).lower(), 2, {"viewer": "system"})
        passed("same-document note page jumps reuse preparation and the native reader; external action targets the original PDF")

        before_switch = inspect()
        app.reader_views.select(app.note_details)
        root.update()
        assert not app.pdf_reader.native.user.IsWindowVisible(app.pdf_reader.native.hwnd)
        assert "Tantalum typed note" in app.preview_text.get("1.0", "end")
        assert app.note_document_title.winfo_ismapped()
        assert app.note_document_title.title == "Alpha reader integration"
        assert "Alpha reader integration" not in app.preview_text.get("1.0", "end")
        assert "PDF page" not in app.preview_text.get("1.0", "end")
        app.reader_views.select(app.pdf_reader)
        root.update()
        state = loaded(2)
        assert state["scale"] == before_switch["scale"] and state["scroll"] == before_switch["scroll"], (before_switch, state)
        passed("Note/PDF view switching preserves selected result, zoom and viewport; native child hides in Note view")

        app.reader_views.select(app.note_details)
        root.update()
        split = app.reader_pane.sashpos(0)
        saved_view = app.reader_views.select()
        reading_before = inspect()
        app.toggle_reader_expanded()
        root.update()
        assert len(app.reader_pane.panes()) == 1 and not app.reader_controls.winfo_ismapped()
        assert app.reader_views.select() == str(app.pdf_reader)
        assert app.reader_expand_button.cget("text") == "Exit reading mode"
        loaded(2)
        wait(lambda: app.pdf_reader.state.get("expanded") and abs(app.pdf_reader.state.get("scale", 0) - 1.25) < .001,
            "Reading mode enters at 125 percent")
        assert inspect()["title"] == "Alpha reader integration"
        app.note_view_button.invoke()
        root.update()
        assert app.note_document_title.winfo_ismapped() and app.note_document_title.title == "Alpha reader integration"
        app.pdf_view_button.invoke()
        root.update()
        app.toggle_reader_expanded()
        root.update()
        assert len(app.reader_pane.panes()) == 2 and app.reader_controls.winfo_ismapped()
        assert app.reader_views.select() == saved_view
        assert abs(app.reader_pane.sashpos(0) - split) <= 2, (split, app.reader_pane.sashpos(0))
        app.pdf_view_button.invoke()
        root.update()
        wait(lambda: not app.pdf_reader.state.get("expanded")
            and app.pdf_reader.state.get("scaleValue") == reading_before["scaleValue"]
            and abs(app.pdf_reader.state.get("scale", 0) - reading_before["scale"]) < .001,
            "Reading mode restores prior zoom")
        wait(lambda: abs(app.pdf_reader.state.get("scroll", {}).get("top", 0) - reading_before["scroll"]["top"]) < 3,
            "Reading mode restores prior logical viewport")
        reading_after = inspect()
        assert abs(reading_after["scale"] - reading_before["scale"]) < .001, (reading_before, reading_after)
        assert abs(reading_after["scroll"]["top"] - reading_before["scroll"]["top"]) < 3, (reading_before, reading_after)
        assert abs(reading_after["scroll"]["left"] - reading_before["scroll"]["left"]) < 3, (reading_before, reading_after)
        app.note_view_button.invoke()
        root.update()
        passed("Reading mode starts at 125%; exit restores previous zoom/position, view, controls and sash")

        for scope, count in (("Notes", "4 notes"), ("PDFs", "2 PDFs"), ("All", "6 items")):
            search(scope, "", count)
        for scope, count in (("Notes", "3 notes"), ("PDFs", "6 results"), ("All", "9 results")):
            search(scope, "tantalum", count)
        passed("blank and populated Notes/PDFs/All searches remain browsable and controls stay enabled")

        search("Notes", "tantalum", "3 notes")
        select(lambda entry: entry["key"] == "Alpha-first")
        app.note_view_button.invoke()
        root.update()
        body = app.preview_text.get("1.0", "end")
        assert body.count("Tantalum imaging.") == 2 and "Main search matches" not in body, body
        assert len(app.preview_match_ranges) == 2 and all(group is None for _, _, group in app.preview_match_ranges)
        assert not app.preview_actions.winfo_ismapped()
        root.geometry("940x760+20+20")
        root.update()
        header_left = app.reader_header.winfo_rootx()
        header_right = header_left + app.reader_header.winfo_width()
        for control in (app.note_view_button, app.pdf_view_button, app.source_button,
                        app.reader_expand_button, app.previous_match_button,
                        app.next_match_button, app.match_count_label):
            assert control.winfo_ismapped(), control
            assert header_left <= control.winfo_rootx() and control.winfo_rootx() + control.winfo_width() <= header_right, (
                control, header_left, header_right, control.winfo_rootx(), control.winfo_width())
        assert app.reader_header.winfo_height() < 52
        assert app.next_match_button.winfo_rootx() + app.next_match_button.winfo_width() <= app.match_count_label.winfo_rootx()
        capture_test_window(root, Path(__file__).resolve().parents[1] / ".test-tmp" / "reader-note-view-940.png")
        root.geometry("1250x820+20+20")
        root.update()
        passed("compact Note view renders its passage once with inline hits and one visible header at minimum window width")

        # Nearby printed words must be an explicit opt-in, with their source
        # stated in Note view instead of implying the note itself matched.
        default_fields = list(app.search_fields)
        app.search_fields.append("context")
        search("Notes", "tantalum", "4 notes")
        select(lambda entry: entry["key"] == "Alpha-context")
        context_preview = app.preview_text.get("1.0", "end")
        assert "Match in surrounding text" in context_preview, context_preview
        assert "Tantalum is nearby" in context_preview, context_preview
        app.search_fields = default_fields
        search("Notes", "tantalum", "3 notes")
        assert all(entry["key"] != "Alpha-context" for entry in app.entries)
        passed("surrounding-text matches appear only after opting in and identify their source in Note view")

        search("PDFs", "tantalum", "6 results")
        # Resolve a different result while hidden, then request its second
        # occurrence. The pending request must survive until PDF view maps.
        select(lambda entry: entry.get("kind") == "pdf" and entry["page"] == 2
            and "Alpha" in entry.get("metadata", {}).get("title", ""))
        assert not app.pdf_reader.loaded and app.pdf_reader.awaiting_entry
        app.navigate_match(1)
        assert app.current_match_index == 1
        assert app.pdf_reader.pending_match and app.pdf_reader.pending_match["index"] == 1
        assert "Match" in app.match_count.get() and "of 24" in app.match_count.get(), app.match_count.get()
        app.reader_views.select(app.pdf_reader)
        state = loaded(2)
        queued_native_index = native_match_index(app.selected_entry(), 1)
        wait(lambda: app.pdf_reader.state.get("selectedMatch", {}).get("matchIdx") == queued_native_index,
            "queued main-search occurrence after PDF view mapping")
        assert app.pdf_reader.pending_match is None
        assert inspect()["findMode"] == "library"
        passed("occurrence navigation in Note view queues the correct hit until PDF view is opened")

        app.next_match_button.invoke()
        retry_native_index = native_match_index(app.selected_entry(), 2)
        wait(lambda: app.pdf_reader.state.get("selectedMatch", {}).get("matchIdx") == retry_native_index,
            "third occurrence before retry")
        retry_counter = app.match_count.get()
        retry_selection = app.notes.selection()
        assert app.current_match_index == 2
        old_process = app.pdf_reader.process
        app.pdf_reader.reload()
        loaded(2)
        wait(lambda: app.pdf_reader.state.get("selectedMatch", {}).get("matchIdx") == retry_native_index,
            "reader retry restores the selected main-search occurrence")
        assert app.pdf_reader.process is not old_process
        assert app.current_match_index == 2 and app.match_count.get() == retry_counter
        assert app.notes.selection() == retry_selection
        passed("Retry reader restarts the host and preserves the selected main-search occurrence and counter")

        rows = app.notes.get_children()
        app.notes.selection_set(rows[0])
        app.preview()
        root.update()
        loaded(1)
        assert app.current_match_index == 0
        for expected_hit in (1, 2, 3):
            app.next_match_button.invoke()
            assert app.current_match_index == expected_hit, (expected_hit, app.current_match_index, sent_matches[-4:])
            expected_native = native_match_index(app.selected_entry(), expected_hit)
            wait(lambda: app.pdf_reader.state.get("selectedMatch", {}).get("matchIdx") == expected_native,
                f"next occurrence {expected_hit + 1}")
            assert app.current_match_index == expected_hit
            # Dispatching a delayed same-row tree selection event must not
            # replace the explicit arrow's fit-width selector with a passive
            # preview update. The third/fourth occurrences are right-column.
            app.notes.event_generate("<<TreeviewSelect>>")
            root.update()
            wait(lambda: app.pdf_reader.state.get("scaleValue") == "page-width", "main arrow fits page width")
            arrow_state = inspect()
            assert arrow_state["selectedMatch"]["matchIdx"] == expected_native, arrow_state
            assert arrow_state["scroll"]["left"] < 1, arrow_state
        with patch.object(app.pdf_worker, "reader_location", wraps=app.pdf_worker.reader_location) as location, \
             patch.object(app.pdf_reader.native, "show", wraps=app.pdf_reader.native.show) as visibility:
            app.next_match_button.invoke()
            assert app.notes.selection() == (rows[1],), (app.notes.selection(), rows)
            loaded(2)
        location.assert_not_called()
        assert all(call.args == (True,) for call in visibility.call_args_list), visibility.call_args_list
        passed("cached main-search page navigation bypasses the PDF worker and never hides the native surface")
        assert app.current_match_index == 0
        app.previous_match_button.invoke()
        assert app.notes.selection() == (rows[0],)
        loaded(1)
        wait(lambda: app.pdf_reader.state.get("selectedMatch", {}).get("matchIdx") == 3,
            "previous occurrence crossing to the prior result")
        # Previous from the first global occurrence wraps to the last paper.
        app.current_match_index = 0
        app.previous_match_button.invoke()
        assert app.notes.selection() == (rows[-1],)
        loaded(3)
        assert app.selected_entry()["path"] != str(next(path for path in sources if path.name.startswith("Alpha"))).lower()
        assert app.current_match_index == 3 and "24 of 24" in app.match_count.get(), app.match_count.get()
        passed("main arrows visit every occurrence, cross pages and papers, and wrap in visible result order")

        # Reading mode uses 125% for entry and every main navigation reset.
        # Exit restores the entry zoom/layout
        # while keeping the page the user reached during that reading session.
        app.notes.selection_set(rows[0])
        app.preview()
        root.update()
        mode_entry = loaded(1)
        app.toggle_reader_expanded()
        root.update()
        wait(lambda: app.pdf_reader.state.get("expanded") and abs(app.pdf_reader.state.get("scale", 0) - 1.25) < .001,
            "Reading mode starts at 125 percent before navigation")
        app.navigate_match(4)
        loaded(2)
        wait(lambda: abs(app.pdf_reader.state.get("scale", 0) - 1.25) < .001,
            "main navigation in Reading mode resets to 125 percent")
        app.toggle_reader_expanded()
        root.update()
        wait(lambda: not app.pdf_reader.state.get("expanded")
            and abs(app.pdf_reader.state.get("scale", 0) - mode_entry["scale"]) < .001,
            "Reading mode exit restores entry zoom after browsing to another page")
        mode_exit = inspect()
        assert mode_exit["page"] == 2 and mode_exit["selectedPage"] == 2, mode_exit
        assert app.notes.selection() == (rows[1],)
        passed("Reading mode entry and main arrows use 125%; exit retains the newly reached page and restores prior zoom")

        for scope in ("Notes", "PDFs", "All"):
            search(scope, "tantalum AND (", "Check search")
            assert app.search_error.get() and not app.entries
            app.clear_search_button.invoke()
            expected = {"Notes": "4 notes", "PDFs": "2 PDFs", "All": "6 items"}[scope]
            wait(lambda: app.note_count.get() == expected and not app.search_error.get(), "clear invalid query")
            available()
        # Submit several generations before either search worker or native
        # reader can finish. Only the final scope/query may populate the UI.
        for scope, query in (("PDFs", "tantalum"), ("Notes", "not-present-anywhere"),
                             ("All", "iodine"), ("PDFs", "not-present-anywhere"), ("Notes", "tantalum")):
            app.search_scope.set(scope)
            app.search.set(query)
            app.refresh_notes()
        wait(lambda: app.note_count.get() == "3 notes" and len(app.entries) == 3,
            "rapid stale searches leave only the final generation", timeout=30)
        assert app.search_scope.get() == "Notes" and app.search.get() == "tantalum"
        assert all(entry["kind"] != "pdf" and entry["key"] != "Alpha-context" for entry in app.entries)
        available()
        passed("invalid Boolean queries recover in every scope; clearing and rapid stale searches preserve the final query")

        app.reader_views.select(app.pdf_reader)
        loaded()
        for tab in (app.inbox_tab, app.library_tab, app.remarkable_tab):
            app.tabs.select(tab)
            root.update()
            assert not app.pdf_reader.native.user.IsWindowVisible(app.pdf_reader.native.hwnd)
            app.tabs.select(app.notes_tab)
            root.update()
            assert app.pdf_reader.native.user.IsWindowVisible(app.pdf_reader.native.hwnd)
            available()
        assert all(path.read_bytes() == before for path, before in sources.items())
        assert not case.errors, case.errors
        passed("all application tab transitions hide/show the embedded child; original PDF bytes are unchanged")
    finally:
        prior_failure = sys.exc_info()[0] is not None
        app.pdf_reader.close()
        # Match App.wait_close: keep Tk's message loop alive while the
        # reparented WinForms child releases its native parent/focus handles.
        deadline = time.monotonic() + 9
        while any(reaper.is_alive() for reaper in app.pdf_reader.reapers) and time.monotonic() < deadline:
            root.update()
            time.sleep(.01)
        app.pdf_reader.wait_closed()
        code = app.pdf_reader.last_exitcode
        case.tearDown()
        if process:
            if code == 0:
                passed("embedded reader exits cleanly and its process is reaped")
            elif prior_failure:
                print(f"ADDITIONAL FAILURE: Reader shutdown exit code: {code}", flush=True)
            else:
                raise AssertionError(f"Reader shutdown exit code: {code}")
    print(f"Completed {len(checks)} actual-App regression groups.", flush=True)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
