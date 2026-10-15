"""Research controls in hidden Tk windows with disposable papers."""
import base64
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch
from tkinter import ttk

import fitz
from PIL import Image

from note_organizer.citations import citation_for, save_citation
from note_organizer.supplement_library import attachments, proposed_name
from note_organizer.research_ui import CitationWindow, SupplementsWindow
from note_organizer.storage import digest_file
from tests import test_review_controls
from tests.ui_helpers import settle_library
from tests.test_preferences_ui import descendants


class ResearchUITests(unittest.TestCase):
    setUp = test_review_controls.ReviewControlTests.setUp
    tearDown = test_review_controls.ReviewControlTests.tearDown
    wait = test_review_controls.ReviewControlTests.wait

    def test_search_scope_changes_from_dropdown_and_note_filters_disable_for_pdfs(self):
        self.paper()
        app = self.app
        self.assertEqual(tuple(app.search_scope_control.cget("values")), ("Notes", "PDFs", "All"))
        app.search_scope_control.set("PDFs")
        self.assertEqual(app.search_scope.get(), "PDFs")
        self.wait(lambda: len(app.entries) == 1 and app.entries[0]["kind"] == "pdf")
        app.search_options()
        window = next(w for w in descendants(self.root) if isinstance(w, ttk.Button)
                      and w.cget("text") == "Apply").winfo_toplevel()
        self.assertFalse(any(isinstance(w, ttk.Radiobutton) and w.cget("text") in {"All", "PDFs", "Notes"}
                             for w in descendants(window)))
        fields = [w for w in descendants(window) if isinstance(w, ttk.Checkbutton)]
        self.assertTrue(fields)
        self.assertTrue(all(w.instate(["disabled"]) for w in fields))
        note_types = next(w for w in descendants(window) if isinstance(w, ttk.Combobox)
                          and "All notes" in w.cget("values"))
        self.assertTrue(note_types.instate(["disabled"]))
        next(w for w in descendants(window) if isinstance(w, ttk.Button) and w.cget("text") == "Cancel").invoke()
        self.assertEqual(app.search_scope.get(), "PDFs")
        app.search_scope_control.set("Notes")
        self.wait(lambda: len(app.entries) == 1 and app.entries[0]["kind"] == "drawing")

    def test_inbox_paths_stack_and_review_heading_aligns_with_incoming_heading(self):
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        self.app.tabs.select(self.app.inbox_tab)
        self.root.geometry("1000x700+0+0")
        self.root.update()
        labels = {w.cget("text"): w for w in descendants(self.app.inbox_tab) if isinstance(w, ttk.Label)}
        self.assertLessEqual(abs(labels["Incoming documents"].winfo_rooty() -
                                 labels["Review filename & destination"].winfo_rooty()), 2)
        self.assertGreater(labels["Library"].winfo_rooty(), labels["Inbox"].winfo_rooty())
        self.assertEqual(labels["Library"].winfo_rootx(), labels["Inbox"].winfo_rootx())
        inbox = self.app.inbox_view
        self.assertGreaterEqual(inbox.editor_form.scroll.winfo_rootx() -
                                (inbox.name_entry.winfo_rootx() + inbox.name_entry.winfo_width()), 12)

    def paper(self):
        path = self.pc / "Research paper.pdf"
        with fitz.open() as pdf:
            pdf.new_page().insert_text((50, 75), "Unique iodine experiment")
            pdf.save(path)
        project = self.store.add_project(self.pc)
        stream = BytesIO()
        Image.new("RGB", (51, 27), "blue").save(stream, format="PNG")
        self.store.save_scan(project, path, digest_file(path), "sig", "settings", {"title": "Research paper"}, [
            {"key": "drawing", "kind": "drawing", "page": 1, "rect": [1, 2, 3, 4],
             "comment": "Unique cobalt note", "image": base64.b64encode(stream.getvalue()).decode()}])
        self.app.refresh()
        settle_library(self.app, self.root)
        self.wait(lambda: len(self.app.entries) == 1 and self.app.image is not None)
        return path, self.store.documents()[0]["id"]

    def test_copy_uses_original_image_and_text_copy_binding_is_unchanged(self):
        self.paper()
        app = self.app
        original = app.image
        self.assertFalse(app.copy_image_button.instate(["disabled"]))
        with patch("note_organizer.ui.copy_image") as copied:
            app.copy_image_button.invoke()
            copied.assert_called_once_with(original, app.preview_text.winfo_id())
        self.assertIn("copied", app.action_feedback["notes"].get())
        app.preview_text.tag_add("sel", "1.0", "1.4")
        app.preview_image_focused = True
        with patch("note_organizer.ui.copy_image") as copied:
            self.assertIsNone(app.copy_preview())  # Preserve Tk's normal text copy.
            copied.assert_not_called()
        window = app.enlarge()
        try:
            with patch("note_organizer.image_viewport.copy_image") as copied:
                window.copy_image_button.invoke()
                copied.assert_called_once_with(original, window.image_canvas.winfo_id())
        finally:
            window.destroy()

    def test_mixed_search_pdf_reader_selection_and_open_target(self):
        path, _ = self.paper()
        app = self.app
        app.search.set("cobalt OR iodine")
        app.search_scope.set("All")
        self.wait(lambda: app.note_count.get() == "2 results")
        self.assertEqual([entry["kind"] for entry in app.entries], ["drawing", "pdf"])
        app.notes.selection_set("1")
        app.preview()
        self.assertIn("Unique iodine experiment", app.preview_text.get("1.0", "end"))
        self.assertEqual(Path(app.pdf_reader.entry["path"]), path)
        self.assertEqual(app.pdf_reader.entry["page"], 1)
        self.assertEqual(set(app.pdf_reader.terms), {"cobalt", "iodine"})
        self.assertIsNone(app.image)
        self.assertTrue(app.preview_text.tag_ranges("search_match"))
        self.assertTrue(app.copy_image_button.instate(["disabled"]))
        self.assertEqual(app.notes.set("1", "kind"), "PDF")
        self.assertEqual(app.tabs.tab(app.notes_tab, "text"), "Reader")
        self.assertFalse(app.full_page_button.instate(["disabled"]))
        with patch.object(app, "open_pdf") as opened:
            app.open_source()
        opened.assert_called_once_with(app.entries[1]["path"], 1, source_only=True)
        app.search_scope.set("PDFs")
        self.wait(lambda: app.note_count.get() == "1 result")
        self.assertTrue(app.export_button.instate(["disabled"]))
        app.search_scope.set("Notes")
        self.wait(lambda: app.note_count.get() == "1 note")

    def test_citation_draft_cancel_and_save_are_separate(self):
        _, document_id = self.paper()
        dialog = CitationWindow(self.app, document_id)
        self.wait(lambda: not dialog.save.instate(["disabled"]))
        dialog.fields["title"].set("Discarded draft")
        dialog.window.destroy()
        self.assertEqual(citation_for(self.store, document_id)["title"], "Research paper")
        dialog = CitationWindow(self.app, document_id)
        self.wait(lambda: not dialog.save.instate(["disabled"]))
        dialog.fields["title"].set("Saved reviewed citation")
        dialog.fields["authors"].set("Doe, Jane; Smith, A.")
        dialog.save.invoke()
        self.wait(lambda: not dialog.window.winfo_exists())
        self.assertEqual(citation_for(self.store, document_id)["title"], "Saved reviewed citation")

    def test_supplements_discovery_is_explicit_and_selected_url_is_visible(self):
        path, document_id = self.paper()
        with patch("note_organizer.research_ui.find_supplements", return_value=([
                {"url": "https://example.org/si.pdf", "label": "Supporting information", "source": "PDF page 1"}], [], "")) as find:
            dialog = SupplementsWindow(self.app, document_id, path)
            self.wait(lambda: not self.app.workflow_futures)
            find.assert_not_called()
            dialog.find.invoke()
            self.wait(lambda: len(dialog.links) == 1)
            dialog.tree.selection_set("0")
            dialog.selection_changed()
            self.assertEqual(dialog.selected_url.get(), "https://example.org/si.pdf")
            self.assertFalse(dialog.download.instate(["disabled"]))
            self.root.attributes("-alpha", 1)
            self.root.deiconify()
            dialog.window.attributes("-alpha", 1)
            dialog.window.attributes("-topmost", True)
            dialog.window.deiconify()
            dialog.window.lift()
            self.wait(lambda: bool(dialog.tree.bbox("0")))
            x, y, width, height = dialog.tree.bbox("0")
            # The actual row must receive pointer input; an overlapping frame
            # used to hide the entire table even though its rows were loaded.
            # Windows can expose a bbox before the transient is mapped by the
            # window manager; wait for native hit testing to settle as well.
            self.wait(lambda: dialog.tree.winfo_containing(dialog.tree.winfo_rootx() + x + 8,
                                                           dialog.tree.winfo_rooty() + y + height // 2) == dialog.tree)
            target = dialog.tree.winfo_containing(dialog.tree.winfo_rootx() + x + 8,
                                                  dialog.tree.winfo_rooty() + y + height // 2)
            self.assertEqual(target, dialog.tree)
            dialog.window.destroy()
            self.assertTrue(dialog.cancelled.is_set())

    def test_search_and_image_actions_fit_minimum_window(self):
        self.paper()
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        self.app.tabs.select(self.app.notes_tab)
        self.app.show_details.set(True)
        self.app.toggle_note_details()
        self.root.geometry("940x700+0+0")
        self.root.update()
        for widget in (self.app.search_entry, self.app.search_scope_control, self.app.copy_image_button,
                       self.app.full_page_button, self.app.enlarge_button):
            with self.subTest(widget=widget):
                self.assertTrue(widget.winfo_ismapped())
                self.assertGreater(widget.winfo_width(), 20)
                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                                     self.root.winfo_rootx() + self.root.winfo_width())
        self.assertFalse(self.errors)

    def test_local_si_candidate_can_be_attached_without_network_or_download(self):
        path, document_id = self.paper()
        existing = path.with_name(path.stem + "_SI.pdf")
        with fitz.open() as pdf:
            pdf.new_page().insert_text((50, 75), "Supporting information")
            pdf.save(existing)
        with patch("note_organizer.research_ui.find_supplements") as network:
            dialog = SupplementsWindow(self.app, document_id, path)
            self.wait(lambda: len(dialog.links) == 1)
            network.assert_not_called()
            dialog.tree.selection_set("0")
            dialog.selection_changed()
            self.assertTrue(dialog.download.instate(["disabled"]))
            self.assertFalse(dialog.use_existing.instate(["disabled"]))
            self.assertEqual(Path(dialog.selected_url.get()), existing.resolve())
            dialog.use_existing.invoke()
            self.wait(lambda: len(dialog.saved) == 1)
            self.assertEqual(Path(dialog.saved[0]["path"]), existing.resolve())
            self.assertTrue(existing.is_file())
            dialog.window.destroy()

    def test_download_dialog_proposes_sorter_name_and_reports_reused_file(self):
        path, document_id = self.paper()
        save_citation(self.store, document_id, {"title": "Article", "authors": ["Doe, Jane"], "journal": "Chemistry", "year": "2025"})
        existing = path.with_name("unrelated existing name.pdf")
        with fitz.open() as pdf:
            pdf.new_page().insert_text((50, 75), "Supplementary results")
            pdf.save(existing)
        target = path.with_name("download.pdf")
        response = BytesIO(existing.read_bytes())
        response.headers = {"Content-Type": "application/pdf"}
        with patch("note_organizer.research_ui.filedialog.asksaveasfilename", return_value=str(target)) as choose, \
                patch("note_organizer.supplements.open_url", return_value=response):
            dialog = SupplementsWindow(self.app, document_id, path)
            self.wait(lambda: not self.app.workflow_futures)
            dialog.web_links = [{"label": "SI", "source": "Publisher page", "url": "https://example.org/si.pdf"}]
            dialog.show_links()
            dialog.tree.selection_set("0")
            dialog.selection_changed()
            dialog.download.invoke()
            self.wait(lambda: "Reused existing file:" in dialog.status.get())
            self.assertEqual(choose.call_args.kwargs["initialfile"], proposed_name(self.store, document_id, ".pdf"))
            self.assertFalse(target.exists())
            self.assertEqual(Path(attachments(self.store, document_id)[0]["path"]), existing.resolve())
            dialog.window.destroy()


if __name__ == "__main__":
    unittest.main()
