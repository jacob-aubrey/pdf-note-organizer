import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from note_organizer.search import compile_search, positive_terms, match_spans, SearchSyntaxError
from note_organizer.storage import Store, matches_search
from note_organizer.viewers import open_pdf_page, viewer_command, executable_from_command


class BooleanSearchTests(unittest.TestCase):
    def test_highlight_terms_follow_boolean_polarity_and_literal_phrases(self):
        self.assertEqual(positive_terms('(gold OR "spectral CT") AND NOT (iodine OR phantom)'),
                         ["gold", "spectral ct"])
        self.assertEqual(positive_terms('NOT NOT gold OR NOT (iodine AND NOT cobalt)'), ["gold", "cobalt"])
        self.assertEqual(positive_terms('gold OR iodine', 'Exact phrase'), ["gold or iodine"])
        self.assertEqual(positive_terms('NOT gold'), [])
        self.assertEqual(positive_terms(''), [])

    def test_highlight_spans_preserve_unicode_and_wrapped_phrase_offsets(self):
        text = "Straße: Spectral\n  CT; GOLD gold."
        spans = match_spans(text, ["strasse", "spectral ct", "gold"])
        self.assertEqual([text[start:end] for start, end in spans],
                         ["Straße", "Spectral\n  CT", "GOLD", "gold"])

    def test_precedence_groups_and_implicit_and(self):
        self.assertTrue(compile_search("iodine OR gold AND CT")(["iodine"]))
        self.assertFalse(compile_search("(iodine OR gold) AND CT")(["iodine"]))
        self.assertTrue(compile_search('(iodine OR gold) "spectral ct" NOT phantom')(["gold spectral ct"]))
        self.assertFalse(compile_search('(iodine OR gold) "spectral ct" NOT phantom')(["gold spectral ct phantom"]))
        self.assertTrue(compile_search("NOT NOT gold")(["gold"]))

    def test_phrases_case_and_literal_operators(self):
        self.assertTrue(compile_search('"GOLD   imaging" OR iodine')(["gold imaging"]))
        self.assertFalse(compile_search('"gold imaging"')(["gold", "imaging"]))
        self.assertTrue(compile_search('"OR"')(["or"]))
        self.assertFalse(compile_search("gold or iodine")(["gold"]))
        self.assertTrue(compile_search("gold OR iodine", "Exact phrase")(["gold or iodine"]))
        self.assertFalse(compile_search("gold OR iodine", "Exact phrase")(["gold"]))
        self.assertTrue(compile_search(r'"a \"quoted\" word"')(['a "quoted" word']))

    def test_not_respects_selected_fields(self):
        entry = {"path": "phantom.pdf", "kind": "highlight", "quote": "gold imaging", "comment": "phantom"}
        self.assertTrue(matches_search(entry, "gold NOT phantom", ["quote"], "All words", "All notes"))
        self.assertFalse(matches_search(entry, "gold NOT phantom", ["quote", "comment"], "All words", "All notes"))
        self.assertTrue(matches_search(entry, "gold AND phantom", ["quote", "comment"], "All words", "All notes"))

    def test_invalid_or_excessive_queries_have_friendly_errors(self):
        for query in ['"unfinished', "gold AND", "OR gold", "()", "gold )", "(gold", '""',
                      "gold OR OR iodine", "("*40+"gold"+")"*40, "gold "*300, "x"*5000]:
            with self.subTest(query=query[:30]), self.assertRaises(SearchSyntaxError):
                compile_search(query)
        self.assertTrue(compile_search("   ")([]))

    def test_invalid_query_is_checked_even_in_empty_library(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "test.sqlite3")
            with self.assertRaises(SearchSyntaxError):
                store.entries(query="gold AND")


class ViewerTests(unittest.TestCase):
    def test_acrobat_and_sumatra_get_page_and_path_as_separate_arguments(self):
        path = Path('paper with spaces & special # characters.pdf').resolve()
        self.assertEqual(viewer_command("Acrobat.exe", path, 3), ["Acrobat.exe", "/A", "page=3", str(path)])
        self.assertEqual(viewer_command("SumatraPDF.exe", path, 7),
                         ["SumatraPDF.exe", "-reuse-instance", "-page", "7", str(path)])

    def test_registry_command_extracts_only_executable(self):
        command = '"C:\\Program Files\\Adobe\\Acrobat.exe" "%1" /other'
        self.assertEqual(executable_from_command(command), r"C:\Program Files\Adobe\Acrobat.exe")
        self.assertEqual(executable_from_command("invalid"), "")

    def test_browser_page_links_preserve_special_characters(self):
        path = Path('paper with spaces & # and é.pdf').resolve()
        for viewer in ("msedge.exe", "chrome.exe", "firefox.exe"):
            self.assertEqual(viewer_command(viewer, path, 4), [viewer, path.as_uri()+"#page=4"])

    def test_explicit_edge_choice_overrides_windows_default(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.pdf"
            path.touch()
            with patch("note_organizer.viewers.find_viewer", return_value="msedge.exe") as find, \
                 patch("note_organizer.viewers.subprocess.Popen") as launch:
                _, supported = open_pdf_page(path, 4, {"viewer": "edge"})
                self.assertTrue(supported)
                find.assert_called_once_with("edge")
                launch.assert_called_once_with(["msedge.exe", path.as_uri()+"#page=4"], close_fds=True)

    def test_missing_preferred_viewer_does_not_silently_switch(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.pdf"
            path.touch()
            with patch("note_organizer.viewers.find_viewer", return_value=None), \
                 patch("note_organizer.viewers.open_system_pdf") as fallback:
                with self.assertRaises(FileNotFoundError):
                    open_pdf_page(path, 2, {"viewer": "edge"})
                fallback.assert_not_called()

    def test_viewer_preference_survives_reopening_library(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "library.sqlite3"
            store = Store(path)
            self.assertEqual(store.preference("pdf_viewer", {"viewer": "system"}), {"viewer": "system"})
            store.set_preference("pdf_viewer", {"viewer": "edge"})
            self.assertEqual(Store(path).preference("pdf_viewer"), {"viewer": "edge"})

    def test_custom_viewer_opens_original_file_without_inventing_page_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.pdf"
            executable = Path(folder) / "another-viewer.exe"
            path.touch()
            executable.touch()
            with patch("note_organizer.viewers.subprocess.Popen") as launch:
                status, supported = open_pdf_page(path, 2, {"viewer": "custom", "path": str(executable)})
                self.assertFalse(supported)
                self.assertIn("page 2", status)
                launch.assert_called_once_with([str(executable), str(path)], close_fds=True)

    def test_open_uses_viewer_command_and_missing_file_does_not_launch(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.pdf"
            path.touch()
            with patch("note_organizer.viewers.find_viewer", return_value="Acrobat.exe"), \
                 patch("note_organizer.viewers.subprocess.Popen") as launch:
                status, exact = open_pdf_page(path, 3)
                self.assertTrue(exact)
                self.assertIn("page 3", status)
                launch.assert_called_once_with(["Acrobat.exe", "/A", "page=3", str(path)], close_fds=True)
                for bad in (0, -1, True, "3"):
                    with self.assertRaises(ValueError):
                        open_pdf_page(path, bad)
                with self.assertRaises(FileNotFoundError):
                    open_pdf_page(path.with_name("absent.pdf"), 3)
                self.assertEqual(launch.call_count, 1)

    def test_fallback_reports_page_navigation_is_not_guaranteed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test #.pdf"
            path.touch()
            for viewer in (None, "unrecognized.exe"):
                with patch("note_organizer.viewers.find_viewer", return_value=viewer), \
                     patch("note_organizer.viewers.open_system_pdf") as system:
                    status, supported = open_pdf_page(path, 2)
                    self.assertFalse(supported)
                    self.assertIn("page 2", status)
                    system.assert_called_once_with(path)


if __name__ == "__main__":
    unittest.main()
