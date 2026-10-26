"""Shared source resources, repeated pages and diagnostic failure stay safe."""
import json
from types import SimpleNamespace
import unittest

import pymupdf
from note_organizer.remarkable_pdf import annotated_pdf


def shared_source():
    with pymupdf.open() as doc:
        image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 32, 32), False)
        image.clear_with(187)
        xref = None
        for number in range(30):
            page = doc.new_page(width=300, height=400)
            page.insert_text((30, 40), 'Synthetic page ' + str(number))
            xref = page.insert_image(pymupdf.Rect(50, 80, 180, 210), **({'xref': xref} if xref else {'stream': image.tobytes('png')}))
        doc[0].insert_link({'kind': pymupdf.LINK_URI, 'from': pymupdf.Rect(20, 20, 100, 30), 'uri': 'https://example.org'})
        doc.set_toc([[1, 'Synthetic section', 1]])
        source = doc.tobytes()
    mapping = list(range(30)) + [0, -1, 2]
    content = {'fileType': 'pdf', 'pages': ['page-' + str(i) for i in range(len(mapping))], 'redirectionPageMap': mapping}
    return source, mapping, {'synthetic.pdf': source, 'synthetic.content': json.dumps(content).encode()}


class PDFSaveTests(unittest.TestCase):
    def test_unresolved_source_named_targets_remain_unchanged_without_blocking_the_paper(self):
        target = 'unresolved (synthetic)\\target α'
        with pymupdf.open() as doc:
            doc.new_page(width=300, height=400)
            doc[0].insert_text((30, 80), 'Synthetic content remains readable')
            doc[0].insert_link({'kind': pymupdf.LINK_GOTO, 'from': pymupdf.Rect(20, 20, 100, 40), 'page': 0})
            link = doc.reload_page(doc[0]).get_links()[0]['xref']
            doc.xref_set_key(link, 'A', 'null')
            doc.xref_set_key(link, 'Dest', pymupdf.get_pdf_str(target))
            doc.set_toc([[1, 'Synthetic unresolved bookmark', 1]])
            bookmark = doc.get_outline_xrefs()[0]
            doc.xref_set_key(bookmark, 'A', 'null')
            doc.xref_set_key(bookmark, 'Dest', pymupdf.get_pdf_str(target))
            source = doc.tobytes()
        with pymupdf.open(stream=source, filetype='pdf') as original:
            expected_toc = original.get_toc()
            expected_link_name = original[0].get_links()[0]['nameddest']
            expected_bookmark_name = original.get_toc(simple=False)[0][3]['nameddest']
            self.assertEqual(original.xref_get_key(link, 'Dest')[1], target)
        rows = []
        bundle = {'synthetic.pdf': source, 'synthetic.content': json.dumps({'fileType': 'pdf', 'pages': ['p0']}).encode()}
        result = annotated_pdf(SimpleNamespace(id='synthetic'), bundle,
                               diagnostic=lambda event, **fields: rows.append({'event': event, **fields}))
        with pymupdf.open(stream=result, filetype='pdf') as output:
            self.assertIn('Synthetic content remains readable', output[0].get_text())
            restored_link = output[0].get_links()[0]
            self.assertEqual(restored_link['nameddest'], expected_link_name)
            self.assertEqual(output.get_toc(simple=False)[0][3]['nameddest'], expected_bookmark_name)
            self.assertEqual(output.xref_get_key(restored_link['xref'], 'A/D')[1], target)
            self.assertEqual(output.xref_get_key(output.get_outline_xrefs()[0], 'Dest')[1], target)
            self.assertEqual(output.get_toc(), expected_toc)
        warning = next(row for row in rows if row['event'] == 'navigation_preserved_unresolved')
        self.assertEqual((warning['links'], warning['bookmarks']), (1, 1))
        self.assertNotIn('unresolved (synthetic)', json.dumps(rows))

    def test_named_link_and_bookmark_keep_resolved_targets_without_a_names_tree(self):
        with pymupdf.open() as doc:
            doc.new_page(width=300, height=400)
            doc.new_page(width=300, height=400)
            dest = doc.get_new_xref()
            doc.update_object(dest, '<< /Names [(target) [' + str(doc.page_xref(1)) + ' 0 R /XYZ 20 300 0]] >>')
            doc.xref_set_key(doc.pdf_catalog(), 'Names', '<< /Dests ' + str(dest) + ' 0 R >>')
            doc[0].insert_link({'kind': pymupdf.LINK_GOTO, 'from': pymupdf.Rect(20, 20, 100, 40), 'page': 1})
            page = doc.reload_page(doc[0])
            link = page.get_links()[0]['xref']
            doc.xref_set_key(link, 'A', 'null')
            doc.xref_set_key(link, 'Dest', '(target)')
            doc.set_toc([[1, 'Synthetic named bookmark', 2]])
            bookmark = doc.get_outline_xrefs()[0]
            doc.xref_set_key(bookmark, 'A', 'null')
            doc.xref_set_key(bookmark, 'Dest', '(target)')
            source = doc.tobytes()
        with pymupdf.open(stream=source, filetype='pdf') as original:
            self.assertEqual(original[0].get_links()[0]['kind'], pymupdf.LINK_NAMED)
            self.assertEqual(original.get_toc()[0][2], 2)
        result = annotated_pdf(SimpleNamespace(id='synthetic'), {'synthetic.pdf': source,
                               'synthetic.content': json.dumps({'fileType': 'pdf', 'pages': ['p0', 'p1']}).encode()})
        with pymupdf.open(stream=result, filetype='pdf') as output:
            self.assertEqual(output.get_toc(), [[1, 'Synthetic named bookmark', 2]])
            link = output[0].get_links()[0]
            self.assertEqual(link['kind'], pymupdf.LINK_GOTO)
            self.assertEqual(link['page'], 1)
            self.assertAlmostEqual(link['to'].x, 20)
            self.assertAlmostEqual(link['to'].y, 100)

    def test_shared_resources_and_repeated_pages_preserve_pixels_navigation_and_labels(self):
        source, mapping, bundle = shared_source()
        before = dict(bundle)
        rows = []
        result = annotated_pdf(SimpleNamespace(id='synthetic'), bundle,
                               diagnostic=lambda event, **fields: rows.append({'event': event, **fields}))
        self.assertEqual(bundle, before)
        with pymupdf.open(stream=source, filetype='pdf') as original, pymupdf.open(stream=result, filetype='pdf') as output:
            self.assertEqual(len(output), len(mapping))
            image_objects = set()
            for index, source_index in enumerate(mapping):
                if source_index < 0:
                    continue
                image_objects.update(entry[0] for entry in output[index].get_images())
                self.assertEqual(output[index].get_pixmap().samples, original[source_index].get_pixmap().samples)
            self.assertEqual(len(image_objects), 1)
            self.assertEqual(output.get_toc(), [[1, 'Synthetic section', 1]])
            self.assertEqual(output[0].get_links()[0]['uri'], 'https://example.org')
            self.assertEqual(output[30].get_label(), '1')
        self.assertEqual(rows[-1]['event'], 'render_pdf_finished')
        self.assertLess(next(i for i, row in enumerate(rows) if row['event'] == 'render_save_started'),
                        next(i for i, row in enumerate(rows) if row['event'] == 'render_save_finished'))

    def test_render_progress_allows_cancellation_and_broken_log_does_not_change_pdf(self):
        _, _, bundle = shared_source()
        stopped = False
        def diagnostic(event, **fields):
            nonlocal stopped
            if event == 'render_page_finished' and fields['page'] == 2:
                stopped = True
        with self.assertRaises(InterruptedError):
            annotated_pdf(SimpleNamespace(id='synthetic'), bundle, lambda: stopped, diagnostic=diagnostic)
        def failed(*args, **kwargs):
            raise OSError('Diagnostic disk unavailable')
        result = annotated_pdf(SimpleNamespace(id='synthetic'), bundle, diagnostic=failed)
        with pymupdf.open(stream=result, filetype='pdf') as output:
            self.assertEqual(len(output), 33)


if __name__ == '__main__':
    unittest.main()
