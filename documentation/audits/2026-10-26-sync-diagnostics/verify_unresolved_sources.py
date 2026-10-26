"""Offline copies of held sources; no network, grants or production writes."""
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import pymupdf
from note_organizer.remarkable_sources import source_bundle
from note_organizer.remarkable_pdf import annotated_pdf, page_map


def names(page, index):
    return [(index, link['nameddest']) for link in page.get_links()
            if link.get('kind') == pymupdf.LINK_NAMED and 'nameddest' in link and link.get('page', -1) < 0]


def main():
    private = ROOT / '.test-tmp/sync-diagnostics-20261026'
    identities = list(json.loads((private / 'unfinished-render-boundaries.json').read_text()))
    state = Path(os.environ['APPDATA']) / 'Zotero/Zotero/Profiles/9v5afvrs.default/notable'
    config = json.loads((state / 'config.json').read_text())
    active = state if config.get('connection_id', 'legacy') == 'legacy' else state / 'connections' / config['connection_id']
    results = []
    for key in identities:
        result = {'tablet_key': key}
        try:
            bundle = source_bundle(SimpleNamespace(path=active / 'bridge/sources/library.sqlite3'), key)
            diagnostics = []
            data = annotated_pdf(SimpleNamespace(id=key), bundle,
                                 diagnostic=lambda event, **fields: diagnostics.append({'event': event, **fields}))
            with pymupdf.open(stream=bundle[key + '.pdf'], filetype='pdf') as original, \
                    pymupdf.open(stream=data, filetype='pdf') as output:
                mapping = page_map(json.loads(bundle[key + '.content']), len(original))
                old, new, equal = [], [], True
                for index, (_, source) in enumerate(mapping):
                    if source < 0:
                        continue
                    equal = equal and original[source].get_text() == output[index].get_text()
                    old.extend(names(original[source], index))
                    new.extend(names(output[index], index))
                result.update(pages=len(output), printed_text_equal=equal, unresolved_links=len(old),
                              unresolved_targets_unchanged=old == new,
                              warnings=sum(row['event'] == 'navigation_preserved_unresolved' for row in diagnostics),
                              source_sha256=hashlib.sha256(bundle[key + '.pdf']).hexdigest())
        except Exception as error:
            result['error_type'] = type(error).__name__
        results.append(result)
    report = {'scope': 'Offline immutable copies; no cloud/library writes, target guesses or text export',
              'tested_documents': len(results), 'results': results}
    Path(__file__).with_name('unresolved-navigation-copy-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    passed = all(row.get('printed_text_equal') and row.get('unresolved_targets_unchanged') for row in results)
    print(json.dumps({'tested_documents': len(results), 'all_passed': passed}))
    assert passed


if __name__ == '__main__':
    main()
