"""The sorter's tiny synthetic CFF fixture verifies embedded font decoding."""
import unittest
from tests.sorting_fixtures import synthetic_cff_font_pdf

class SortingEmbeddedFontTests(unittest.TestCase):
    def test_cff_embedded_encoding_overrides_pdf_character_byte(self):
        from pypdf import PdfReader
        self.assertEqual(PdfReader(synthetic_cff_font_pdf()).pages[0].extract_text().strip(), "A")
