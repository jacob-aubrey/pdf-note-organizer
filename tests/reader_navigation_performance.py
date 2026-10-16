"""Measure loaded-page main-hit navigation in the real Windows PDF reader.

Run with tools/run_ui_tests.py to keep WebView2 on an inactive desktop.
"""
import json
import multiprocessing as mp
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.reader_webview_regression import host
from tests.reader_app_regression import require_private_desktop


def main():
    import pymupdf
    from note_organizer.reader_server import ReaderServer
    from note_organizer.research_search import hit_excerpts

    require_private_desktop()
    path = ROOT / '.test-tmp/reader-navigation-performance.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page(width=612, height=900)
        for line in range(60):
            page.insert_text((45, 50 + line * 13), f'Tantalum passage number {line + 1} in this dense research page.', fontsize=9)
        text = page.get_text(sort=False)
        doc.save(path)
    hits = [{**hit, 'field': 'pdf'} for hit in hit_excerpts(text, 'tantalum')]
    assert len(hits) == 60
    server = ReaderServer()
    parent, child = mp.get_context('spawn').Pipe()
    process = mp.get_context('spawn').Process(target=host, args=(child, server.url, False))
    process.start()
    child.close()
    serial = 0

    def js(script):
        nonlocal serial
        serial += 1
        name = str(serial)
        parent.send({'name': name, 'js': script})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if not parent.poll(.02):
                continue
            result = parent.recv()
            if result.get('response') == name:
                assert 'error' not in result, result
                return result['result']
        raise AssertionError('Reader command timed out')

    try:
        parent.send('show')
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if js('!!window.NotableReader'):
                break
            time.sleep(.05)
        payload = {'id': 'navigation-performance', 'url': server.register_document(path),
                   'page': 1, 'mainHits': hits, 'terms': ['tantalum'], 'hasSelection': True}
        js('void NotableReader.open(' + json.dumps(payload) + ');true')
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            state = js('NotableReader.state()')
            if state['ready'] and state['matches']['total'] == 60:
                break
            time.sleep(.02)
        else:
            raise AssertionError(state)
        before = state.get('mainMappingBuilds')
        assert isinstance(before, int) and before > 0, state
        samples = []
        for index in range(1, 21):
            sample = js('(()=>{const start=performance.now();NotableReader.selectMatch({index:' + str(index) +
                        ',fitWidth:true});return {ms:performance.now()-start,state:NotableReader.state()}})()')
            assert sample['state']['selectedMatch'] == {'pageIdx': 0, 'matchIdx': index}, sample
            assert sample['state']['matches']['total'] == 60, sample
            samples.append(sample['ms'])
        after = js('NotableReader.state()')
        assert after['mainMappingBuilds'] == before, after
        print(json.dumps({'main_navigation_ms_median': statistics.median(samples),
                          'main_navigation_ms_max': max(samples),
                          'mapping_builds_before': before,
                          'mapping_builds_after': after.get('mainMappingBuilds')}), flush=True)
    finally:
        parent.send('close')
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join(3)
        parent.close()
        server.close()


if __name__ == '__main__':
    mp.freeze_support()
    main()
