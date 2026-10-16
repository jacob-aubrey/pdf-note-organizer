"""Shared result navigation and view transitions, with disposable note rows."""
from concurrent.futures import Future
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from note_organizer.image_viewport import ImageViewport
from note_organizer.search import positive_terms, SearchSyntaxError
from note_organizer.storage import DEFAULT_SEARCH_FIELDS
from tests import test_ui_audit


class ReaderNavigationUITests(unittest.TestCase):
    setUp = test_ui_audit.UIAuditTests.setUp
    tearDown = test_ui_audit.UIAuditTests.tearDown

    def rows(self):
        return [{"document_id": paper, "key": key, "kind": kind,
                 "path": str(self.pc / (paper + ".pdf")), "page": page,
                 "metadata": {"title": paper}, "quote": quote, "comment": comment,
                 "rect": [10, 20, 100, 40]}
                for paper, key, kind, page, quote, comment in (
                    ("Alpha", "a", "highlight", 1, "Gold and more gold.", ""),
                    ("Alpha", "b", "text", 2, "", "Gold typed note."),
                    ("Beta", "c", "drawing", 3, "", "Gold drawing comment."))]

    def replace(self, rows, query="gold"):
        app = self.app
        app.query_cancel.set()
        app.query_generation += 1
        if app.search_after:
            self.root.after_cancel(app.search_after)
            app.search_after = None
        app.search_fields = ["quote", "comment", "ocr"]
        app.pending_search = (query, "Words / Boolean")
        app.result_terms = positive_terms(*app.pending_search)
        future = Future()
        future.set_result(rows)
        app.finish_query(app.query_generation, None, future)
        self.root.update()
        return app

    def show(self):
        self.root.attributes("-alpha", 0)
        self.root.geometry("1250x820+0+0")
        self.app.tabs.select(self.app.notes_tab)
        self.root.deiconify()
        self.root.update()

    def test_arrows_visit_every_occurrence_across_papers_and_both_views(self):
        app = self.replace(self.rows())
        self.show()
        self.assertEqual(app.match_count.get(), "Main search · Match 1 of 4")
        for view in (app.note_details, app.pdf_reader):
            app.reader_views.select(view)
            self.root.update()
            with patch.object(app.pdf_reader, "select_match") as select:
                expected = [("0", 1), ("1", 0), ("2", 0), ("0", 0)]
                for ordinal, (row, index) in enumerate(expected, 2):
                    app.next_match_button.invoke()
                    self.root.update()
                    self.assertEqual(app.notes.selection(), (row,))
                    self.assertEqual(app.notes.focus(), row)
                    self.assertEqual(app.current_match_index, index)
                    self.assertIn(f"Match {(ordinal - 1) % 4 + 1} of 4", app.match_count.get())
                    ranges = app.preview_text.tag_ranges("current_search_match")
                    self.assertEqual(app.preview_text.get(*ranges).casefold(), "gold")
                    self.assertEqual(select.call_args.args[0]["index"], index)
                app.previous_match_button.invoke()
                self.root.update()
                self.assertEqual(app.notes.selection(), ("2",))
                # Return to the first occurrence for the other view.
                app.next_match_button.invoke()
                self.root.update()
        self.assertFalse(self.errors)

    def test_sort_changes_traversal_and_counter_without_changing_selection(self):
        app = self.replace(self.rows())
        app.notes.selection_set("1")
        app.preview()
        selected = app.notes.selection()
        app.sort_reader("kind")
        self.assertEqual(app.notes.selection(), selected)
        order = app.notes.get_children()
        app.current_match_index = 0
        app.navigate_match(-1)
        self.assertEqual(app.notes.selection(), (order[(order.index("1") - 1) % len(order)],))
        self.assertIn("of 4", app.match_count.get())

    def test_keyboard_continues_from_the_row_selected_by_match_buttons(self):
        app = self.replace(self.rows())
        app.navigate_match(2)
        self.assertEqual(app.notes.selection(), ("1",))
        self.assertEqual(app.notes.focus(), "1")
        # Dispatch the same class action as Down without changing desktop focus.
        self.root.tk.call("ttk::treeview::Keynav", str(app.notes), "down")
        self.root.update()
        self.assertEqual(app.notes.selection(), ("2",))
        self.assertEqual(app.pdf_reader.entry["key"], "c")
        self.assertEqual(app.pdf_reader.pending_match["term"].casefold(), "gold")

    def test_view_switch_preserves_reader_identity_state_and_pending_match(self):
        app = self.replace(self.rows())
        self.show()
        app.pdf_reader.state = {"page": 7, "scale": 1.9, "scrollTop": 840}
        identity, generation = app.pdf_reader.identity, app.pdf_reader.generation
        app.pdf_reader.select_match({"index": 1, "term": "gold"})
        pending = app.pdf_reader.pending_match
        for _ in range(4):
            for view in (app.note_details, app.pdf_reader):
                app.reader_views.select(view)
                self.root.update()
                self.assertEqual(app.pdf_reader.identity, identity)
                self.assertEqual(app.pdf_reader.generation, generation)
                self.assertEqual(app.pdf_reader.state["scrollTop"], 840)
                self.assertEqual(app.pdf_reader.pending_match, pending)

    def test_navigation_while_note_view_open_is_delivered_once_pdf_loads(self):
        app = self.replace(self.rows())
        app.reader_views.select(app.note_details)
        app.navigate_match(1)
        self.assertEqual(app.pdf_reader.pending_match["index"], 1)
        app.pdf_reader.connection = connection = Mock()
        app.pdf_reader.handle_event({"kind": "state", "id": app.pdf_reader.generation, "loaded": True})
        self.assertEqual(connection.send.call_args.args[0]["index"]["index"], 1)
        self.assertIsNone(app.pdf_reader.pending_match)
        connection.send.reset_mock()
        app.pdf_reader.handle_event({"kind": "state", "id": app.pdf_reader.generation, "loaded": True})
        connection.send.assert_not_called()
        app.pdf_reader.connection = None

    def test_same_result_navigation_sends_one_match_without_rebuilding_preview(self):
        app = self.replace(self.rows())
        app.pdf_reader.loaded = True
        with patch.object(app, "preview") as preview, patch.object(app.pdf_reader, "select_match") as select:
            app.navigate_match(1)
        preview.assert_not_called()
        select.assert_called_once()
        self.assertEqual(select.call_args.args[0]["index"], 1)
        self.assertTrue(select.call_args.args[0]["fitWidth"])

    def test_new_result_navigation_sends_only_its_requested_match(self):
        app = self.replace(self.rows())
        with patch.object(app.pdf_reader, "select_match") as select:
            app.navigate_match(2)
            self.root.update()
        select.assert_called_once()
        self.assertEqual(app.notes.selection(), ("1",))
        self.assertEqual(select.call_args.args[0]["index"], 0)

    def test_current_result_click_reclaims_main_search_without_reloading_document(self):
        app = self.replace(self.rows())
        self.show()
        identity, generation = app.pdf_reader.identity, app.pdf_reader.generation
        row = app.notes.selection()[0]
        with patch.object(app.notes, "identify_row", return_value=row), patch.object(app.pdf_reader, "select_match") as select:
            app.activate_reader_result(SimpleNamespace(y=50))
        self.assertEqual(select.call_args.args[0]["term"].casefold(), "gold")
        self.assertEqual(app.pdf_reader.identity, identity)
        self.assertEqual(app.pdf_reader.generation, generation)

    def test_surrounding_text_is_off_by_default_and_match_source_is_explicit(self):
        app = self.app
        self.assertEqual(tuple(app.search_fields), DEFAULT_SEARCH_FIELDS)
        row = self.rows()[0]
        row.update(quote="An unrelated highlighted sentence.", context="The surrounding text contains tantalum.")
        app.search_fields = ["context"]
        app.pending_search = ("tantalum", "Words / Boolean")
        app.result_terms = ["tantalum"]
        from note_organizer.research_search import enrich_note_matches
        enriched = enrich_note_matches(row, "tantalum", ["context"])
        # replace() sets its own fields, but enriched source metadata persists.
        self.replace([enriched], "tantalum")
        text = app.preview_text.get("1.0", "end")
        self.assertIn("Match in surrounding text", text)
        self.assertIn("surrounding text contains tantalum", text)
        self.assertIn("surrounding text", app.notes.item("0", "values")[-1].casefold())

    def test_search_filter_reset_leaves_surrounding_text_off(self):
        from tkinter import ttk
        app = self.app
        app.search_fields = ["context"]
        app.search_options()
        window = next(w for w in self.root.winfo_children()
                      if w.winfo_toplevel() == w and w != self.root and w.title() == "Search filters")
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        widgets = list(descendants(window))
        reset = next(w for w in widgets if isinstance(w, ttk.Button) and w.cget("text") == "Reset all")
        reset.invoke()
        checks = {w.cget("text"): bool(int(self.root.getvar(w.cget("variable"))))
                  for w in widgets if isinstance(w, ttk.Checkbutton)}
        self.assertFalse(checks["Surrounding printed text"])
        self.assertTrue(all(value for key, value in checks.items() if key != "Surrounding printed text"))
        window.destroy()

    def test_blank_and_not_only_searches_keep_rows_navigable_without_fake_hits(self):
        for query in ("", "NOT iodine"):
            app = self.replace(self.rows(), query)
            app.notes.selection_set("0")
            app.preview()
            self.assertEqual(app.current_match_index, None)
            self.assertIn("Result 1 of 3", app.match_count.get())
            app.navigate_match(-1)
            self.assertEqual(app.notes.selection(), ("2",))
            self.assertEqual(app.preview_text.tag_ranges("current_search_match"), ())
            if query:
                self.assertIn("without a positive term", app.preview_text.get("1.0", "end"))

    def test_stale_and_invalid_query_cannot_restore_old_results_or_occurrences(self):
        app = self.replace(self.rows())
        generation = app.query_generation
        app.query_generation += 1
        stale = Future()
        stale.set_result([])
        app.finish_query(generation, None, stale)
        self.assertEqual(len(app.entries), 3)
        error = Future()
        error.set_exception(SearchSyntaxError("Unclosed parenthesis"))
        app.finish_query(app.query_generation, None, error)
        self.assertEqual(app.entries, [])
        self.assertEqual(app.result_terms, [])
        self.assertEqual(app.match_count.get(), "No results")
        self.assertTrue(app.next_match_button.instate(["disabled"]))
        self.assertIsNone(app.pdf_reader.pending_match)


class ImageResetUITests(unittest.TestCase):
    def test_control_double_click_resets_opening_scale_and_both_pan_axes(self):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.attributes("-alpha", 0)
        root.geometry("600x500+0+0")
        viewport = ImageViewport(root, root, lambda _: None)
        viewport.pack(fill="both", expand=True)
        root.deiconify()
        root.update()
        try:
            for fit_width in (False, True):
                canvas = viewport.canvas
                canvas.set_image(Image.new("RGB", (1200, 2000), "white"), fit_width=fit_width)
                root.update()
                opening_zoom = canvas.zoom
                for _ in range(3):
                    canvas.event_generate("<MouseWheel>", x=200, y=180, delta=120, state=4)
                canvas.xview_moveto(.2)
                canvas.yview_moveto(.3)
                self.assertGreater(canvas.zoom, opening_zoom)
                self.assertGreater(canvas.yview()[0], 0)
                for stamp in (1000, 1100):
                    canvas.event_generate("<ButtonPress-1>", x=200, y=180, state=4, time=stamp)
                    canvas.event_generate("<ButtonRelease-1>", x=200, y=180, state=4, time=stamp + 1)
                root.update()
                self.assertAlmostEqual(canvas.zoom, opening_zoom, delta=.002)
                self.assertEqual(canvas.fit_mode, "width" if fit_width else None)
                self.assertEqual(canvas.xview()[0], 0)
                self.assertEqual(canvas.yview()[0], 0)
                self.assertFalse(canvas.panning)
                self.assertEqual(canvas.cget("cursor"), "")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
