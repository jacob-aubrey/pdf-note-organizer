"""Exercise actual WebView2 paints during same/different PDF transitions.

Run through tools/run_ui_tests.py; no windows appear on the active desktop.
"""
import json
import multiprocessing as mp
from pathlib import Path
import sys
import threading
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
    folder = ROOT / '.test-tmp'
    folder.mkdir(exist_ok=True)
    papers, texts = [], []
    for paper in range(3):
        path = folder / f'reader-transition-{paper}.pdf'
        with pymupdf.open() as doc:
            for page_number in range(3):
                page = doc.new_page(width=612, height=900)
                page.insert_text((45, 70), f'Document {paper}, page {page_number + 1}', fontsize=20)
                for line in range(12):
                    page.insert_text((45, 130 + line * 52), f'Tantalum passage {line + 1} for this page.', fontsize=12)
            texts.append([page.get_text() for page in doc])
            doc.save(path)
        papers.append(path)

    class DelayedServer(ReaderServer):
        blocked = None
        release = threading.Event()

        def _serve_file(self, handler, path, *, head, document=None):
            if document and path == self.blocked:
                self.release.wait(10)
            return super()._serve_file(handler, path, head=head, document=document)

    server = DelayedServer()
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

    def wait(predicate):
        deadline = time.monotonic() + 20
        state = None
        while time.monotonic() < deadline:
            state = js('NotableReader.state()')
            if predicate(state):
                return state
            time.sleep(.02)
        raise AssertionError(state)

    def payload(identifier, url, paper=0, page=1, match=0):
        hits = [{**hit, 'field': 'pdf'} for hit in hit_excerpts(texts[paper][page - 1], 'tantalum')]
        return {'id': identifier, 'url': url, 'title': f'Document {paper}', 'page': page,
                'mainHits': hits, 'terms': ['tantalum'], 'hasSelection': True,
                'match': {'index': match, 'fitWidth': True}}

    def open_pdf(value):
        return js('void NotableReader.open(' + json.dumps(value) + ');NotableReader.state()')

    def settled(identifier, page, match=0):
        return wait(lambda state: state['id'] == identifier and state['ready'] and
                    not state['transitioning'] and state['page'] == page and
                    state['selectedMatch'] == {'pageIdx': page - 1, 'matchIdx': match})

    try:
        parent.send('show')
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if js('!!window.NotableReader'):
                break
            time.sleep(.05)
        url = server.register_document(papers[0])
        open_pdf(payload(1, url))
        settled(1, 1)

        # Observe every animation frame, not just the final loaded state.
        js("""window.paintAudit={frames:0,blank:0,loading:0};
          window.auditPaint=function(){
            const state=NotableReader.state(), audit=window.paintAudit;
            audit.frames++;
            if(document.getElementById('transitionCover').hidden &&
               getComputedStyle(document.getElementById('viewerContainer')).visibility==='hidden') audit.blank++;
            if(state.loadingVisible) audit.loading++;
            window.auditFrame=requestAnimationFrame(window.auditPaint);
          };window.auditFrame=requestAnimationFrame(window.auditPaint);true""")
        for number, page, match in ((2, 2, 3), (3, 3, 7), (4, 1, 10)):
            immediate = open_pdf(payload(number, url, page=page, match=match))
            assert immediate['ready'] and not immediate['transitioning'], immediate
            assert not immediate['loadingVisible'] and not immediate['retainedPage'], immediate
            settled(number, page, match)
        same_pdf_audit = js('({...window.paintAudit})')
        assert same_pdf_audit['blank'] == 0 and same_pdf_audit['loading'] == 0, same_pdf_audit

        # Freeze the current page while source preparation is still pending.
        retained = js("""window.oldCanvasBox=document.querySelector('#viewer .page[data-page-number="1"] canvas').getBoundingClientRect().toJSON();
          NotableReader.prepare(5);window.retainedPixels=document.querySelector('#transitionCover canvas').toDataURL();NotableReader.state()""")
        assert retained['retainedPage'] and retained['transitioning'] and not retained['loadingVisible'], retained
        assert js("document.getElementById('transitionCover').inert && !document.querySelector('#transitionCover [id]')")
        assert js("""(()=>{const copy=document.querySelector('#transitionCover canvas').getBoundingClientRect();
          return ['left','top','width','height'].every(key=>Math.abs(copy[key]-window.oldCanvasBox[key])<1)})()""")
        time.sleep(.25)
        assert js('NotableReader.state().loadingVisible')

        # Delay bytes for the new PDF and verify the previous painted pixels
        # survive even after PDF.js has cleared its live document.
        server.blocked = papers[1].resolve()
        url2 = server.register_document(papers[1])
        loading = open_pdf(payload(5, url2, paper=1, page=2, match=4))
        assert loading['retainedPage'] and loading['transitioning'], loading
        assert js("document.querySelector('#transitionCover canvas').toDataURL()===window.retainedPixels")
        time.sleep(.25)
        assert js('NotableReader.state().retainedPage && NotableReader.state().loadingVisible')
        server.release.set()
        settled(5, 2, 4)
        assert js("document.getElementById('transitionCover').childElementCount===0")

        # A slow superseded open must never overwrite a newer document/hit.
        server.release.clear()
        server.blocked = papers[0].resolve()
        slow_url = server.register_document(papers[0])
        open_pdf(payload(6, slow_url, page=3))
        latest_url = server.register_document(papers[2])
        open_pdf(payload(7, latest_url, paper=2, page=1, match=8))
        server.release.set()
        settled(7, 1, 8)
        time.sleep(.2)
        assert js('NotableReader.state().id===7 && !NotableReader.state().retainedPage')
        assert js('NotableReader.selectMatch({index:0},6)') is False
        navigation_audit = js('({...window.paintAudit})')
        assert navigation_audit['blank'] == 0, navigation_audit

        # Clear and errors must remove the old page, not conceal a failure.
        js("NotableReader.prepare(8);void NotableReader.clear('Choose another PDF',8);true")
        state = js('NotableReader.state()')
        assert not state['transitioning'] and not state['retainedPage'] and not state['loadingVisible'], state
        open_pdf(payload(9, latest_url, paper=2))
        settled(9, 1)
        error_payload = payload(10, server.origin + '/invalid.pdf')
        open_pdf(error_payload)
        wait(lambda state: bool(state['message']) and not state['retainedPage'] and not state['transitioning'])
        audit = js('cancelAnimationFrame(window.auditFrame);({...window.paintAudit})')
        # Clear/error intentionally expose a message; inspect the audit before
        # those actions separately above for seamless navigation.
        print(json.dumps({'same_pdf_paints': same_pdf_audit,
                          'navigation_paints': navigation_audit,
                          'different_pdf_retained_pixels': True,
                          'rapid_navigation_latest_hit': True, 'total_observed_frames': audit['frames']}), flush=True)
    finally:
        server.release.set()
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
