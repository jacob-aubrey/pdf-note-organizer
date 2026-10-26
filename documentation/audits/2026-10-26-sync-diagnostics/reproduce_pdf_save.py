"""Offline failing-document-copy benchmark. Outputs stay under ignored .test-tmp.

No cloud, Zotero API, state writes, grants, document text or process injection.
Modes change only supported PyMuPDF copy/save parameters in this child process.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import pymupdf
from note_organizer.remarkable_pdf import annotated_pdf, page_map


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['original', 'current', 'graft', 'save3', 'graft-save3', 'graft-save2'])
    args = parser.parse_args()
    root = ROOT / '.test-tmp/sync-diagnostics-20261026/pdf-save-reproduction'
    with zipfile.ZipFile(root / 'source.zip') as archive:
        bundle = {name: archive.read(name) for name in archive.namelist()}
    identity = next(name[:-4] for name in bundle if name.endswith('.pdf'))
    original = bundle[identity + '.pdf']
    with pymupdf.open(stream=original, filetype='pdf') as pdf:
        pages = page_map(json.loads(bundle[identity + '.content']), len(pdf))
        source_pages = len(pdf)
    copies = sum(source >= 0 for _, source in pages)
    started = time.monotonic()
    trace = root / (args.mode + '-boundaries.jsonl')
    def emit(event, **fields):
        with trace.open('a') as stream:
            stream.write(json.dumps({'event': event, 'elapsed_s': round(time.monotonic() - started, 3), **fields}) + '\n')
            stream.flush()
    insert, save = pymupdf.Document.insert_pdf, pymupdf.Document.tobytes
    count = 0
    def copy(self, other, *a, **kwargs):
        nonlocal count
        count += 1
        if args.mode.startswith('graft'):
            kwargs['final'] = int(count == copies)
        elif args.mode != 'current':
            kwargs.pop('final', None)  # Historical default: discard each graft map.
        value = insert(self, other, *a, **kwargs)
        if count % 50 == 0 or count == copies:
            emit('copied_pages', copies=count, xrefs=self.xref_length())
        return value
    def write(self, *a, **kwargs):
        if args.mode != 'current':
            kwargs['garbage'] = 4  # Reproduce the old policy after source repair.
        if args.mode.endswith('save3'):
            kwargs['garbage'] = 3
        if args.mode.endswith('save2'):
            kwargs['garbage'] = 2
        emit('save_started', xrefs=self.xref_length(), options=kwargs)
        value = save(self, *a, **kwargs)
        emit('save_finished', bytes=len(value))
        return value
    pymupdf.Document.insert_pdf, pymupdf.Document.tobytes = copy, write
    result = annotated_pdf(SimpleNamespace(id=identity), bundle)
    (root / (args.mode + '.pdf')).write_bytes(result)
    metadata = {'mode': args.mode, 'duration_s': round(time.monotonic() - started, 3),
                'source_pages': source_pages, 'output_pages': len(pages), 'source_bytes': len(original),
                'source_sha256': hashlib.sha256(original).hexdigest(), 'output_bytes': len(result)}
    (root / (args.mode + '-result.json')).write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
