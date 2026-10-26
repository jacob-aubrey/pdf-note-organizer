"""Compare all pages of the private failing-document copy; export no text."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import pymupdf
from note_organizer.remarkable_pdf import page_map


def links(page):
    def value(item):
        if isinstance(item, (pymupdf.Rect, pymupdf.Point)):
            return [round(v, 4) for v in item]
        return item
    result = []
    for row in page.get_links():
        row = dict(row)
        if row.get('kind') == pymupdf.LINK_NAMED and 'nameddest' in row and row.get('page', -1) >= 0:
            row.pop('nameddest')
            row['kind'] = pymupdf.LINK_GOTO
            row['to'] = pymupdf.Point(row.get('to', (0, 0))) * page.parent[row['page']].transformation_matrix
        result.append({key: value(item) for key, item in row.items() if key not in {'xref', 'id'}})
    return result


def same_links(left, right):
    if len(left) != len(right):
        return False
    for a, b in zip(left, right):
        if a.keys() != b.keys():
            return False
        for key in a:
            if key in {'from', 'to'} and isinstance(a[key], list) and isinstance(b[key], list):
                if len(a[key]) != len(b[key]) or any(abs(x - y) > .01 for x, y in zip(a[key], b[key])):
                    return False
            elif a[key] != b[key]:
                return False
    return True


def main():
    private = ROOT / '.test-tmp/sync-diagnostics-20261026/pdf-save-reproduction'
    with zipfile.ZipFile(private / 'source.zip') as archive:
        name = next(name for name in archive.namelist() if name.endswith('.pdf'))
        raw = archive.read(name)
        content = json.loads(archive.read(name[:-4] + '.content'))
    result = json.loads((private / 'current-result.json').read_text())
    mismatch = {'pixels': [], 'text': [], 'geometry': [], 'links': []}
    annotations = Counter()
    with pymupdf.open(stream=raw, filetype='pdf') as original, pymupdf.open(private / 'current.pdf') as output:
        mapping = page_map(content, len(original))
        assert len(output) == len(mapping)
        for index, (_, source) in enumerate(mapping):
            if source < 0:
                continue
            before, after = original[source], output[index]
            for annotation in after.annots() or ():
                annotations[annotation.type[1]] += 1
            if before.rect != after.rect:
                mismatch['geometry'].append(index)
            a = before.get_pixmap(matrix=pymupdf.Matrix(.5, .5), annots=False, alpha=False)
            b = after.get_pixmap(matrix=pymupdf.Matrix(.5, .5), clip=before.rect, annots=False, alpha=False)
            if (a.width, a.height, a.samples) != (b.width, b.height, b.samples):
                mismatch['pixels'].append(index)
            if before.get_text() != after.get_text():
                mismatch['text'].append(index)
            if not same_links(links(before), links(after)):
                mismatch['links'].append(index)
        result.update(all_pages_compared=len(mapping), comparison_dpi=36,
                      link_coordinate_tolerance_points=.01,
                      identity_page_map=[source for _, source in mapping] == list(range(len(original))),
                      navigation_toc_equal=original.get_toc() == output.get_toc(),
                      mismatch_counts={key: len(values) for key, values in mismatch.items()},
                      output_annotation_types=dict(annotations),
                      source_archive_sha256=hashlib.sha256((private / 'source.zip').read_bytes()).hexdigest(),
                      source_unmodified=hashlib.sha256(raw).hexdigest() == result['source_sha256'])
    (private / 'comparison-private.json').write_text(json.dumps(mismatch, indent=2))
    Path(__file__).with_name('pdf-save-copy-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    assert not any(result['mismatch_counts'].values()), 'Private page-copy comparison needs review'
    assert result['navigation_toc_equal'] and result['source_unmodified']


if __name__ == '__main__':
    main()
