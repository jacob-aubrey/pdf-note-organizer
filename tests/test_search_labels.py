"""Search controls are visibly named and stay usable with narrower windows."""
import unittest

from tests import test_review_controls
from tests.ui_helpers import settle_library


class SearchLabelTests(unittest.TestCase):
    setUp = test_review_controls.ReviewControlTests.setUp
    tearDown = test_review_controls.ReviewControlTests.tearDown
    wait = test_review_controls.ReviewControlTests.wait
    review = test_review_controls.ReviewControlTests.review
    rows = test_review_controls.ReviewControlTests.rows
    populated_review = test_review_controls.ReviewControlTests.populated_review

    def assert_search_visible(self, label, entry, window):
        self.assertTrue(label.winfo_ismapped())
        self.assertEqual(label.cget("text"), "Search")
        self.assertEqual(str(label.cget("compound")), "left")
        image_name = self.root.tk.splitlist(label.cget("image"))[0]
        self.assertTrue(image_name)
        self.assertGreater(int(self.root.tk.call("image", "width", image_name)), 0)
        self.assertLessEqual(label.winfo_rootx() + label.winfo_width(), entry.winfo_rootx())
        self.assertGreater(entry.winfo_width(), 30)
        self.assertLessEqual(entry.winfo_rootx() + entry.winfo_width(),
                             window.winfo_rootx() + window.winfo_width() + 2)

    def test_notes_and_review_search_labels_fit_normal_and_narrow_windows(self):
        review = self.populated_review()
        original_scaling = self.root.tk.call("tk", "scaling")
        self.root.attributes("-alpha", 0)
        self.root.deiconify()
        self.app.tabs.select(self.app.notes_tab)
        review.window.deiconify()
        try:
            for scale in (1, 1.5):
                self.root.tk.call("tk", "scaling", (96 / 72) * scale)
                for notes_width, review_width in ((1000, 1000), (940, 760)):
                    with self.subTest(scale=scale, notes_width=notes_width, review_width=review_width):
                        self.root.geometry(f"{notes_width}x700+0+0")
                        review.window.geometry(f"{review_width}x700+0+0")
                        self.root.update()
                        self.assert_search_visible(self.app.search_label, self.app.search_entry, self.root)
                        self.assert_search_visible(review.search_label, review.search_entry, review.window)
                        self.assertEqual(self.app.search_label.cget("image"), review.search_label.cget("image"))
                        self.assertFalse(self.errors)
        finally:
            self.root.tk.call("tk", "scaling", original_scaling)

    def test_visible_search_controls_keep_filtering_notes_and_review_findings(self):
        project = self.store.add_project(self.pc)
        path = self.pc / "Synthetic paper.pdf"
        path.touch()
        self.store.save_scan(project, path, "synthetic-digest", "signature", "settings", {}, [
            {"key": "one", "kind": "highlight", "page": 1, "rect": [1, 2, 3, 4], "quote": "A unique cobalt observation"},
            {"key": "two", "kind": "highlight", "page": 2, "rect": [1, 2, 3, 4], "quote": "Another zinc observation"},
        ])
        self.app.refresh()
        settle_library(self.app, self.root)
        self.app.search.set("cobalt")
        self.wait(lambda: self.app.note_count.get() == "1 notes")
        self.assertEqual([entry["key"] for entry in self.app.entries], ["one"])
        self.app.search.set("")
        self.wait(lambda: self.app.note_count.get() == "2 notes")
        review = self.populated_review()
        review.search.set("LOCATION-NEEDLE")
        self.assertEqual(review.tree.get_children(), ("z",))
        review.search.set("")
        self.assertEqual(set(review.tree.get_children()), {"a", "z"})

if __name__ == "__main__":
    unittest.main()
