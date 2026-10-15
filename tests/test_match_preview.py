"""Visible match ranges remain accurate when PDF whitespace is compacted."""
import unittest

from note_organizer.match_preview import excerpt_display
from note_organizer.research_search import hit_excerpts


class MatchPreviewTests(unittest.TestCase):
    def test_unicode_and_wrapped_phrases_map_to_their_visible_occurrences(self):
        context = "Header\nStraße and Spectral\n  CT then Straße."
        hits = hit_excerpts(context, 'strasse OR "spectral ct"')
        excerpt = {"start": 0, "end": len(context), "hit_indices": list(range(len(hits)))}
        text, ranges = excerpt_display(context, excerpt, hits)
        self.assertEqual([text[start:end] for start, end in ranges.values()], ["Straße", "Spectral CT", "Straße"])

    def test_trimmed_whitespace_and_ellipses_do_not_shift_match_selection(self):
        context = "Before the excerpt.\n  Tantalum\t  works.\nAfter the excerpt."
        hits = hit_excerpts(context, "tantalum")
        excerpt = {"start": context.index("\n"), "end": context.index("After"), "hit_indices": [0]}
        text, ranges = excerpt_display(context, excerpt, hits)
        self.assertTrue(text.startswith("…Tantalum"))
        self.assertTrue(text.endswith("works.…"))
        self.assertEqual(text[slice(*ranges[0])], "Tantalum")


if __name__ == "__main__":
    unittest.main()
