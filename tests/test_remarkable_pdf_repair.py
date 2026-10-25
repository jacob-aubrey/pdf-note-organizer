"""Readable PDFs with dangling resources retain their visible content and ink."""
from io import BytesIO
import unittest
from unittest.mock import patch

import pymupdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import IndirectObject, NameObject

from note_organizer.remarkable_pdf import annotated_pdf, _repair_copy_source, UnsupportedAnnotations
from tests.test_remarkable import fixture


def damaged_source():
    item, bundle = fixture()
    with pymupdf.open(stream=bundle[item.id + '.pdf'], filetype='pdf') as source:
        source.set_toc([[1, 'Retained section', 1]])
        source[0].insert_link({'kind': pymupdf.LINK_URI, 'from': pymupdf.Rect(60, 140, 160, 160), 'uri': 'https://example.org/paper'})
        original = source.tobytes()
    writer = PdfWriter()
    writer.clone_document_from_reader(PdfReader(BytesIO(original)))
    writer.pages[0]['/Resources']['/Font'][NameObject('/Unused')] = IndirectObject(999999, 0, writer)
    stream = BytesIO(); writer.write(stream)
    bundle[item.id + '.pdf'] = stream.getvalue()
    return item, bundle


class CopyRepairTests(unittest.TestCase):
    def test_dangling_unused_resource_is_repaired_without_losing_navigation_or_tablet_notes(self):
        item, bundle = damaged_source()
        before = dict(bundle)
        with pymupdf.open(stream=bundle[item.id + '.pdf'], filetype='pdf') as source, pymupdf.open() as output:
            with self.assertRaisesRegex(RuntimeError, 'source object number out of range'):
                output.insert_pdf(source)
        result = annotated_pdf(item, bundle)
        self.assertEqual(bundle, before)
        with pymupdf.open(stream=result, filetype='pdf') as output:
            self.assertEqual(output.get_toc(), [[1, 'Retained section', 1]])
            self.assertEqual(output[0].get_links()[0]['uri'], 'https://example.org/paper')
            kinds = {annotation.type[1] for annotation in output[0].annots()}
            self.assertTrue({'Ink', 'Highlight', 'Text'} <= kinds)

    def test_repair_rejects_a_changed_page_appearance(self):
        item, bundle = damaged_source()
        with pymupdf.open() as different:
            different.new_page(width=600, height=800).insert_text((60, 100), 'Different printed content')
            different.set_toc([[1, 'Retained section', 1]])
            different[0].insert_link({'kind': pymupdf.LINK_URI, 'from': pymupdf.Rect(60, 140, 160, 160), 'uri': 'https://example.org/paper'})
            changed = different.tobytes()
        class ChangedWriter:
            def clone_document_from_reader(self, reader): pass
            def write(self, target): target.write(changed)
        with patch('pypdf.PdfWriter', ChangedWriter):
            with self.assertRaisesRegex(UnsupportedAnnotations, 'appearance'):
                _repair_copy_source(bundle[item.id + '.pdf'], lambda: False)

    def test_repair_remains_cancellable(self):
        item, bundle = damaged_source()
        with self.assertRaises(InterruptedError):
            _repair_copy_source(bundle[item.id + '.pdf'], lambda: True)
