"""Opt-in Windows/WebView2 integration regression with trusted pointer events.

Run with .venv/Scripts/python.exe tools/run_ui_tests.py tests/reader_webview_regression.py.
Uses only generated PDFs and an ephemeral loopback server; all windows remain
transparent and offscreen. It never moves the desktop cursor or activates a
window. Kept separate from unittest discovery because it requires WebView2,
local loopback permission, and a Windows GUI session.
"""
import ctypes
from ctypes import wintypes
import functools
import hashlib
import http.server
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys
import threading
import time
import tkinter as tk

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def host(pipe, url, easy_drag):
    import webview
    class API:
        def event(self, data):
            pipe.send({'event': data})
    window = webview.create_window('Notable hidden reader regression', url, js_api=API(),
        width=700, height=600, hidden=True, frameless=True, text_select=True,
        easy_drag=easy_drag, draggable=False, shadow=False, focus=False,
        background_color='#181a1b')
    def started():
        try:
            window.events.shown.wait(1)
            pipe.send({'hwnd': int(window.native.Handle.ToInt64())})
            while True:
                command = pipe.recv()
                if command == 'close':
                    from System import Action
                    from System.Windows.Forms import Application
                    def shutdown():
                        window.native.Hide()
                        window.native.browser.clear_user_data()
                        window.native.Dispose()
                        Application.ExitThread()
                    window.native.BeginInvoke(Action(shutdown))
                    return
                if command == 'show':
                    window.show()
                elif isinstance(command, dict):
                    try:
                        pipe.send({'response': command['name'], 'result': window.evaluate_js(command['js'])})
                    except Exception as exc:
                        pipe.send({'response': command['name'], 'error': str(exc)})
        except Exception as exc:
            pipe.send({'error': str(exc)})
            window.destroy()
    webview.start(started, gui='edgechromium', private_mode=True)


def main():
    import pymupdf
    from note_organizer.research_search import hit_excerpts
    pdf = ROOT / '.test-tmp/reader-assets.pdf'
    suppressed_popup_ids = {}
    with pymupdf.open() as doc:
        for number in range(1, 4):
            page = doc.new_page()
            page.insert_text((60, 80), f'PDF reader test page {number}', fontsize=18)
            page.insert_text((60, 120), 'Tantalum oxide. The next tantalum sample.', fontsize=14)
            page.insert_text((60, 150), 'Selectable text and continuous document scrolling.', fontsize=14)
            if number == 3:
                page.insert_text((60, 180), 'Zirconium marker on the last page only.', fontsize=14)
            if number == 1:
                page.insert_text((60, 220), 'External hyperlink', fontsize=14)
                page.insert_link({'kind': pymupdf.LINK_URI, 'from': pymupdf.Rect(60, 202, 210, 225),
                                 'uri': 'https://example.org/reader-pan-test'})
                page.insert_text((60, 260), 'Internal hyperlink to page 3', fontsize=14)
                # Page 3 does not exist until this loop completes.
                pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 30), False)
                pixmap.clear_with(170)
                page.insert_image(pymupdf.Rect(60, 290, 160, 350), pixmap=pixmap)
                page.insert_link({'kind': pymupdf.LINK_URI, 'from': pymupdf.Rect(60, 290, 160, 350),
                                 'uri': 'https://example.org/reader-linked-image'})
                quote = page.add_highlight_annot(page.search_for('Selectable text')[0])
                quote.set_info(subject='reMarkable highlight', content='Selectable text')
                quote.update()
                suppressed_popup_ids['1'] = [f'{quote.xref}R']
                genuine = page.add_highlight_annot(page.search_for('continuous document scrolling')[0])
                genuine.set_info(subject='reMarkable highlight', content='A genuine research comment.', title='Reader')
                genuine.update()
                genuine_id = f'{genuine.xref}R'
        doc[0].insert_link({'kind': pymupdf.LINK_GOTO, 'from': pymupdf.Rect(60, 242, 270, 265),
                            'page': 2, 'to': pymupdf.Point(0, 0)})
        doc.save(pdf)
    original_pdf_digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    def printed_hits(page, query, path=pdf):
        with pymupdf.open(path) as document:
            text = document[page - 1].get_text(sort=False)
        return [{**hit, 'field':'pdf', 'before':text[max(0,hit['start']-100):hit['start']],
                 'after':text[hit['end']:hit['end']+100]} for hit in hit_excerpts(text, query)] if query else []
    password_pdf = ROOT / '.test-tmp/reader-assets-password.pdf'
    with pymupdf.open() as doc:
        doc.new_page().insert_text((60, 80), 'Locked test document')
        doc.save(password_pdf, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                 user_pw='reader-test-password', owner_pw='reader-test-owner')
    repeated_pdf = ROOT / '.test-tmp/reader-assets-repeated.pdf'
    with pymupdf.open() as doc:
        for number in range(1, 4):
            page = doc.new_page(width=900 if number == 2 else 612, height=792)
            page.insert_text((45, 55), f'Repeated reader test page {number}', fontsize=18)
            for line in range(4):
                page.insert_text((45, 110 + line * 190),
                    f'Tantalum imaging passage {line + 1}. A selectable research sentence.', fontsize=12)
        repeated_text = doc.load_page(0).get_text(sort=True)
        repeated_hits = hit_excerpts(repeated_text, 'tantalum', 'Words / Boolean')
        doc.save(repeated_pdf)
    scoped_pdf = ROOT / '.test-tmp/reader-assets-scoped.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((60, 70), 'Tantalum in the document title', fontsize=18)
        page.insert_text((60, 140), 'iiiiiiii tantalum WWWWWWWW passage.', fontsize=14)
        page.insert_text((60, 210), 'Another tantalum occurrence stays unmarked.', fontsize=14)
        quote_rect = list(page.search_for('tantalum')[1] * ~page.transformation_matrix)
        doc.save(scoped_pdf)
    scoped_pdf_digest = hashlib.sha256(scoped_pdf.read_bytes()).hexdigest()
    source_order_pdf = ROOT / '.test-tmp/reader-assets-source-order.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page()
        for position, text in (((50, 80), 'Left first tantalum source.'), ((50, 160), 'Left second tantalum source.'),
                               ((320, 80), 'Right first tantalum source.'), ((320, 160), 'Right second tan-'),
                               ((320, 180), 'talum source.')):
            page.insert_text(position, text, fontsize=12)
        doc.save(source_order_pdf)
    union_pdf = ROOT / '.test-tmp/reader-assets-union.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((60, 90), 'Gold imaging and ordinary text.', fontsize=14)
        page.insert_text((60, 140), 'Straße and STRASSE research.', fontsize=14)
        doc.save(union_pdf)
    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript', '.wasm': 'application/wasm'}
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.GetThreadDesktop.argtypes = (wintypes.DWORD,)
    user.GetThreadDesktop.restype = wintypes.HANDLE
    user.GetUserObjectInformationW.argtypes = (wintypes.HANDLE, ctypes.c_int,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    desktop = user.GetThreadDesktop(kernel.GetCurrentThreadId())
    desktop_name, required = ctypes.create_unicode_buffer(256), wintypes.DWORD()
    assert user.GetUserObjectInformationW(desktop, 2, desktop_name,
        ctypes.sizeof(desktop_name), ctypes.byref(required))
    assert desktop_name.value == os.environ.get('NOTABLE_TEST_DESKTOP') and desktop_name.value.startswith('NotableTests-'), 'Use tools/run_ui_tests.py to isolate native viewer testing.'
    user.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user.GetParent.argtypes = (wintypes.HWND,)
    user.GetParent.restype = wintypes.HWND
    user.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user.MoveWindow.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.BOOL)
    user.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
    user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
    user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user.SetParent.argtypes = (wintypes.HWND, wintypes.HWND)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumChildWindows.argtypes = (wintypes.HWND, callback_type, wintypes.LPARAM)
    user.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user.GetForegroundWindow.restype = wintypes.HWND
    user.SetLayeredWindowAttributes.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_ubyte, wintypes.DWORD)
    user.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    foreground = user.GetForegroundWindow()
    output = []
    try:
        for easy_drag in (False,):
            root = tk.Tk()
            root.title('Isolated reader regression')
            root.geometry('980x760+30000+30000')
            root.attributes('-alpha', 0)
            frame = tk.Frame(root)
            frame.pack(fill='both', expand=True)
            root.update()
            parent, child = mp.get_context('spawn').Pipe()
            process = mp.get_context('spawn').Process(target=host, args=(child, origin + '/note_organizer/assets/reader/index.html', easy_drag), daemon=True)
            process.start()
            child.close()
            events = []
            responses = {}
            hwnd = None
            def collect(seconds):
                nonlocal hwnd
                until = time.monotonic() + seconds
                while time.monotonic() < until:
                    # This process is attached to a verified, inactive desktop.
                    # Native focus changes here cannot affect the user's apps.
                    root.update()
                    while parent.poll():
                        result = parent.recv()
                        if 'hwnd' in result:
                            hwnd = result['hwnd']
                        elif 'event' in result:
                            events.append(result['event'])
                        elif 'response' in result:
                            responses[result['response']] = result
                        else:
                            print(json.dumps(result), flush=True)
                    time.sleep(.01)
            def js(name, script, delay=.2):
                parent.send({'name': name, 'js': script})
                until = time.monotonic() + 10
                while name not in responses and time.monotonic() < until:
                    collect(.05)
                assert name in responses, (name, events)
                response = responses.pop(name)
                assert 'error' not in response, response
                if delay:
                    collect(delay)
                return response['result']
            def bounds():
                rectangle = wintypes.RECT()
                user.GetWindowRect(hwnd, ctypes.byref(rectangle))
                return [rectangle.left, rectangle.top, rectangle.right, rectangle.bottom]
            try:
                for _ in range(100):
                    collect(.2)
                    if hwnd and any(event['kind'] == 'ready' for event in events):
                        break
                assert hwnd and any(event['kind'] == 'ready' for event in events), events
                # Reproduce embedding in Tk on the private inactive desktop.
                style = user.GetWindowLongPtrW(hwnd, -16)
                user.SetWindowLongPtrW(hwnd, -16, (style & ~0x80000000 & ~0x00C00000 & ~0x00040000) | 0x40000000)
                user.SetParent(hwnd, frame.winfo_id())
                user.MoveWindow(hwnd, 0, 0, frame.winfo_width(), frame.winfo_height(), True)
                parent.send('show')
                collect(.5)
                payload = {'rect': [40, 600, 300, 700], 'id': 'notes-selected', 'url': origin + '/.test-tmp/reader-assets.pdf', 'title': 'Reader regression', 'page': 2, 'terms': ['tantalum'], 'hasSelection': True,
                           'suppressedPopupIds': suppressed_popup_ids, 'mainHits': printed_hits(2, 'tantalum')}
                js('open', 'void NotableReader.open(' + json.dumps(payload) + ');true', 2)
                state = js('state', 'NotableReader.state()')
                assert state['ready'] and state['renderedPages'] > 0 and not state['selectionOutlined'], state
                title_script = '(()=>{const h=document.getElementById("documentTitle"),bar=document.getElementById("documentInfo"),style=getComputedStyle(h);return {text:h.textContent,tip:h.title,hidden:bar.hidden,fontSize:style.fontSize,weight:style.fontWeight,height:h.getBoundingClientRect().height,lineHeight:parseFloat(style.lineHeight),top:bar.getBoundingClientRect().top,controlsBottom:document.getElementById("toolbar").getBoundingClientRect().bottom}})()'
                heading = js('initial-document-heading', title_script)
                assert heading['text'] == payload['title'] and heading['tip'] == payload['title'] and not heading['hidden'], heading
                assert heading['fontSize'] == '16px' and int(heading['weight']) >= 700 and heading['top'] >= heading['controlsBottom'], heading
                long_title = 'Tantalum imaging <research & review> ' * 50
                js('rename-current-document', 'NotableReader.setTitle(' + json.dumps(long_title) + ',' + json.dumps(payload['id']) + ')')
                renamed = js('renamed-document-heading', title_script)
                renamed_state = js('renamed-document-state', 'NotableReader.state()')
                assert renamed['text'] == long_title and renamed['tip'] == long_title, renamed
                assert renamed['height'] <= renamed['lineHeight'] * 2 + 1, renamed
                for key in ('id', 'url', 'page', 'scale', 'selectedMatch', 'findMode', 'findQuery'):
                    assert renamed_state[key] == state[key], (key, state, renamed_state)
                assert not js('ignore-stale-document-title', 'NotableReader.setTitle("Stale paper title","old-selection")')
                assert js('retained-document-heading', title_script)['text'] == long_title
                js('restore-current-document-title', 'NotableReader.setTitle(' + json.dumps(payload['title']) + ',' + json.dumps(payload['id']) + ')')
                js('pointerlog', 'window.pointerEvents=[];for(const name of ["mousedown","mousemove","mouseup","click","dblclick"])document.addEventListener(name,e=>pointerEvents.push({type:e.type,trusted:e.isTrusted,x:e.clientX,y:e.clientY,target:e.target.closest("button")?.id||e.target.id}),true);true')
                classes = []
                @callback_type
                def enum(child_handle, _):
                    class_name = ctypes.create_unicode_buffer(256)
                    user.GetClassNameW(child_handle, class_name, 256)
                    classes.append((int(child_handle), class_name.value))
                    return True
                user.EnumChildWindows(hwnd, enum, 0)
                targets = [handle for handle, name in classes if name in ('Chrome_RenderWidgetHostHWND', 'Chrome_WidgetWin_1')]
                assert targets, classes
                browser_hwnd = targets[0]
                before = bounds()
                coordinates = js('find-position', '(()=>{const r=document.getElementById("findToggle").getBoundingClientRect();return [Math.round((r.x+r.width/2)*devicePixelRatio),Math.round((r.y+r.height/2)*devicePixelRatio)]})()')
                x, y = coordinates
                lp = x | (y << 16)
                user.PostMessageW(browser_hwnd, 0x200, 0, lp)
                user.PostMessageW(browser_hwnd, 0x201, 1, lp)
                user.PostMessageW(browser_hwnd, 0x200, 1, (x + 1) | ((y + 1) << 16))
                user.PostMessageW(browser_hwnd, 0x202, 0, (x + 1) | ((y + 1) << 16))
                collect(.5)
                pointer = js('pointer', 'pointerEvents')
                after = bounds()
                # Win32 message injection is delivered as trusted browser pointer events.
                assert any(item['trusted'] and item['type'] == 'mousedown' and item['target'] == 'findToggle' for item in pointer), pointer
                if easy_drag:
                    assert before != after, (before, after, pointer)
                    result = {'easy_drag': True, 'before': before, 'after': after, 'reproduced_move': True, 'pointer': pointer}
                else:
                    assert before == after, (before, after, pointer)
                    def click(name):
                        x, y = js('click-position-' + name, '(()=>{const r=document.getElementById(' + json.dumps(name) + ').getBoundingClientRect();return [Math.round((r.x+r.width/2)*devicePixelRatio),Math.round((r.y+r.height/2)*devicePixelRatio)]})()')
                        lp = x | (y << 16)
                        user.PostMessageW(browser_hwnd, 0x200, 0, lp)
                        user.PostMessageW(browser_hwnd, 0x201, 1, lp)
                        user.PostMessageW(browser_hwnd, 0x200, 1, (x + 1) | ((y + 1) << 16))
                        user.PostMessageW(browser_hwnd, 0x202, 0, (x + 1) | ((y + 1) << 16))
                        collect(.25)
                    # Exercise the actual UI handlers, including repeated fit/find changes.
                    assert not js('find-opened', 'document.getElementById("findbar").hidden')
                    click('findClose')
                    results = []
                    for index in range(3):
                        click('zoomOut')
                        js(f'fit-{index}', 'document.getElementById("zoom").value="page-width";document.getElementById("zoom").dispatchEvent(new Event("change"));true')
                        click('findToggle')
                        assert not js(f'find-open-{index}', 'document.getElementById("findbar").hidden')
                        js(f'find-{index}', 'document.getElementById("findInput").value="oxide";document.getElementById("findInput").dispatchEvent(new Event("input"));true', .4)
                        finding = js(f'find-match-state-{index}', 'NotableReader.state()')
                        assert finding['findMode'] == 'pdf' and finding['matches']['total'] == 3, finding
                        click('findClose')
                        click('backToSelection')
                        click('viewerContainer')
                        results.append(js(f'check-{index}', '({...NotableReader.state(),backDisabled:document.getElementById("backToSelection").disabled,containerVisible:getComputedStyle(document.getElementById("viewerContainer")).visibility})'))
                    assert all(item['loaded'] and item['renderedPages'] and item['containerVisible'] == 'visible' and not item['backDisabled'] for item in results), results
                    # Main selection and occurrence arrows always reclaim search
                    # authority; opening PDF Find never changes the main terms.
                    click('findToggle')
                    js('pdf-find-authority', 'document.getElementById("findInput").value="oxide";document.getElementById("findInput").dispatchEvent(new Event("input"));true', .4)
                    payload.update(id='main-result-2', page=3)
                    payload['mainHits'] = printed_hits(3, 'tantalum')
                    js('main-result-reclaims', 'void NotableReader.open(' + json.dumps(payload) + ');true', .5)
                    reclaimed = js('main-result-state', '({...NotableReader.state(),findHidden:document.getElementById("findbar").hidden})')
                    assert reclaimed['findMode'] == 'library' and reclaimed['findHidden'] and reclaimed['findQuery'] == '' and reclaimed['page'] == 3, reclaimed
                    assert reclaimed['matches']['total'] == 2 and not reclaimed['selectionOutlined'], reclaimed
                    click('findToggle')
                    js('pdf-find-second-authority', 'document.getElementById("findInput").value="oxide";document.getElementById("findInput").dispatchEvent(new Event("input"));true', .4)
                    js('main-next-reclaims', 'NotableReader.selectMatch({index:0,term:"tantalum",context:"Tantalum oxide. The next tantalum sample.",before:"The next ",after:" sample."})', .5)
                    selected = js('main-next-state', '({...NotableReader.state(),findHidden:document.getElementById("findbar").hidden})')
                    assert selected['findMode'] == 'library' and selected['findHidden'] and selected['findQuery'] == '', selected
                    assert selected['selectedMatch'] == {'pageIdx':2,'matchIdx':1}, selected
                    # A delayed PDF.js callback must not advance the chosen hit.
                    collect(.5)
                    assert js('stable-main-next', 'NotableReader.state()')['selectedMatch'] == selected['selectedMatch']
                    js('absent-comment', 'NotableReader.selectMatch({index:0,term:"not printed in this PDF",context:"Private typed comment absent from the paper."})', .5)
                    absent = js('absent-comment-state', 'NotableReader.state()')
                    assert absent['page'] == 3 and absent['selectedMatch'] == {'pageIdx':-1,'matchIdx':-1}, absent
                    payload.update(id='changed-terms', terms=['oxide'], page=2)
                    payload['mainHits'] = printed_hits(2, 'oxide')
                    js('changed-terms-open', 'void NotableReader.open(' + json.dumps(payload) + ');true', .5)
                    changed = js('changed-terms-state', 'NotableReader.state()')
                    assert changed['matches']['total'] == 1 and changed['selectedMatch'] == {'pageIdx':1,'matchIdx':0}, changed
                    payload.update(id='term-absent-on-selected-page', terms=['zirconium'], page=2)
                    payload['mainHits'] = printed_hits(2, 'zirconium')
                    js('empty-selected-page', 'void NotableReader.open(' + json.dumps(payload) + ');true', .7)
                    empty_page = js('empty-selected-page-state', 'NotableReader.state()')
                    assert sum(empty_page['pageMatches']) == 0 and empty_page['page'] == 2 and empty_page['selectedMatch'] == {'pageIdx':-1,'matchIdx':-1}, empty_page
                    # A request queued before a different document load completes
                    # is applied after the text layer is available.
                    payload.update(id='queued-occurrence', url=origin + '/.test-tmp/reader-assets.pdf?new-document=1', terms=['tantalum'], page=2, expanded=True)
                    payload['mainHits'] = printed_hits(2, 'tantalum')
                    js('queued-open', 'void NotableReader.open(' + json.dumps(payload) + ');NotableReader.selectMatch({index:1,term:"tantalum",fitWidth:true});true', 1)
                    queued = js('queued-state', 'NotableReader.state()')
                    assert queued['loaded'] and queued['selectedMatch'] == {'pageIdx':1,'matchIdx':1}, queued
                    assert queued['expanded'] and abs(queued['scale'] - 1.25) < .001 and queued['scroll']['left'] < 1, queued
                    payload.update(id='pdf-browsing', page=1, terms=[], hasSelection=False, expanded=False)
                    payload['mainHits'] = []
                    js('browse', 'void NotableReader.open(' + json.dumps(payload) + ');true')
                    browse = js('browsecheck', '({...NotableReader.state(),backDisabled:document.getElementById("backToSelection").disabled})')
                    assert browse['backDisabled'] and not browse['hasSelection'] and browse['loaded'], browse
                    js('backguard', 'document.getElementById("backToSelection").click();true')
                    assert js('guardstate', 'NotableReader.state()')['loaded']
                    # Ctrl+left drag pans the viewport; the native child never moves.
                    js('pan-setup', 'document.getElementById("zoom").value="2";document.getElementById("zoom").dispatchEvent(new Event("change"));true', .5)
                    js('pan-position', 'document.getElementById("viewerContainer").scrollLeft=150;document.getElementById("viewerContainer").scrollTop=300;true')
                    pan_before = js('pan-before', 'NotableReader.state()')
                    x,y = js('pan-point', '(()=>{const r=document.getElementById("viewerContainer").getBoundingClientRect();return [Math.round((r.x+r.width*.7)*devicePixelRatio),Math.round((r.y+r.height*.7)*devicePixelRatio)]})()')
                    native_before_pan = bounds()
                    user.PostMessageW(browser_hwnd, 0x200, 8, x | (y << 16))
                    user.PostMessageW(browser_hwnd, 0x201, 9, x | (y << 16))
                    collect(.2)
                    assert js('pan-started', 'NotableReader.state()')['panning']
                    user.PostMessageW(browser_hwnd, 0x200, 9, (x-90) | ((y-105) << 16))
                    collect(.2)
                    user.PostMessageW(browser_hwnd, 0x202, 8, (x-90) | ((y-105) << 16))
                    collect(.2)
                    pan_after = js('pan-after', 'NotableReader.state()')
                    assert not pan_after['panning'] and pan_after['scroll']['left'] > pan_before['scroll']['left'] and pan_after['scroll']['top'] > pan_before['scroll']['top'], (pan_before, pan_after)
                    assert bounds() == native_before_pan
                    # Ctrl+double-click restores fit width and default pan at
                    # the current page, without losing the loaded document.
                    js('reset-page', 'document.getElementById("pageNumber").value="2";document.getElementById("pageNumber").dispatchEvent(new Event("change"));document.getElementById("viewerContainer").scrollLeft=150;document.getElementById("viewerContainer").scrollTop+=120;true', .3)
                    reset_before = js('reset-before', 'NotableReader.state()')
                    x,y = js('reset-point', '(()=>{const r=document.getElementById("viewerContainer").getBoundingClientRect();return [Math.round((r.x+r.width*.7)*devicePixelRatio),Math.round((r.y+r.height*.7)*devicePixelRatio)]})()')
                    lp = x | (y << 16)
                    user.PostMessageW(browser_hwnd, 0x200, 8, lp)
                    user.PostMessageW(browser_hwnd, 0x201, 9, lp)
                    user.PostMessageW(browser_hwnd, 0x202, 8, lp)
                    user.PostMessageW(browser_hwnd, 0x203, 9, lp)
                    user.PostMessageW(browser_hwnd, 0x202, 8, lp)
                    collect(.6)
                    reset = js('reset-after', 'NotableReader.state()')
                    assert reset['loaded'] and reset['page'] == reset_before['page'] and reset['scaleValue'] == 'page-width', (reset_before, reset)
                    assert reset['scroll']['left'] < 1 and not reset['panning'], reset
                    reset_top = js('reset-page-top', '(()=>{const p=document.querySelectorAll(".page")[NotableReader.state().page-1];return p.getBoundingClientRect().top-document.getElementById("viewerContainer").getBoundingClientRect().top})()')
                    assert abs(reset_top) < 2, reset_top
                    assert js('reset-selected-text', 'window.getSelection().toString()') == ''
                    assert any(item['trusted'] and item['type'] == 'dblclick' for item in js('reset-events', 'pointerEvents'))
                    assert bounds() == native_before_pan
                    js('ctrl-wheel', 'document.getElementById("viewerContainer").dispatchEvent(new WheelEvent("wheel",{ctrlKey:true,deltaY:-120,cancelable:true,bubbles:true}));true', .3)
                    assert js('ctrl-wheel-state', 'NotableReader.state()')['scale'] > reset['scale']
                    # Ctrl gestures take priority over all PDF links, including
                    # linked images. These are real native trusted events.
                    js('link-test-setup', 'document.getElementById("zoom").value="2";document.getElementById("zoom").dispatchEvent(new Event("change"));document.getElementById("pageNumber").value="1";document.getElementById("pageNumber").dispatchEvent(new Event("change"));window.linkPointers=[];document.addEventListener("pointerdown",e=>linkPointers.push({trusted:e.isTrusted,ctrl:e.ctrlKey,link:!!e.target.closest("a")}),true);true', .5)
                    link_selectors = (
                        'a[href="https://example.org/reader-pan-test"]',
                        '[data-internal-link] a',
                        'a[href="https://example.org/reader-linked-image"]',
                    )
                    def link_point(selector, name):
                        return js(name, '(()=>{const a=document.querySelector(' + json.dumps(selector) + ');if(!a)throw new Error("Missing PDF link");a.scrollIntoView({block:"center",inline:"center"});const r=a.getBoundingClientRect();return [Math.round((r.x+r.width*.5)*devicePixelRatio),Math.round((r.y+r.height*.5)*devicePixelRatio)]})()')
                    link_pan_states = []
                    for link_index, selector in enumerate(link_selectors):
                        x, y = link_point(selector, f'link-point-{link_index}')
                        links_before = len([event for event in events if event['kind'] == 'link'])
                        current_before = js(f'link-before-{link_index}', 'NotableReader.state()')
                        lp = x | (y << 16)
                        user.PostMessageW(browser_hwnd, 0x200, 8, lp)
                        user.PostMessageW(browser_hwnd, 0x201, 9, lp)
                        collect(.1)
                        assert js(f'link-pan-start-{link_index}', 'NotableReader.state()')['panning']
                        user.PostMessageW(browser_hwnd, 0x200, 9, (x-70) | ((y-70) << 16))
                        collect(.1)
                        user.PostMessageW(browser_hwnd, 0x202, 8, (x-70) | ((y-70) << 16))
                        collect(.2)
                        current_after = js(f'link-after-{link_index}', 'NotableReader.state()')
                        assert current_after['loaded'] and not current_after['panning'], current_after
                        assert current_after['scroll']['top'] > current_before['scroll']['top'] + 30, (current_before,current_after)
                        assert current_after['page'] == current_before['page'], (current_before,current_after)
                        assert len([event for event in events if event['kind'] == 'link']) == links_before, events
                        link_pan_states.append(current_after)
                    assert all(item['trusted'] and item['ctrl'] and item['link'] for item in js('link-trusted-pointers', 'linkPointers')), js('link-debug', 'linkPointers')
                    # Ctrl+double-click also resets when the target is a link.
                    x, y = link_point(link_selectors[0], 'link-reset-point')
                    lp = x | (y << 16)
                    user.PostMessageW(browser_hwnd, 0x201, 9, lp)
                    user.PostMessageW(browser_hwnd, 0x202, 8, lp)
                    user.PostMessageW(browser_hwnd, 0x203, 9, lp)
                    user.PostMessageW(browser_hwnd, 0x202, 8, lp)
                    collect(.4)
                    link_reset = js('link-reset-state', 'NotableReader.state()')
                    assert link_reset['scaleValue'] == 'page-width' and link_reset['scroll']['left'] < 1, link_reset
                    # Ordinary external/linked-image clicks report once; an
                    # ordinary internal link still opens its PDF destination.
                    for link_index in (0, 2):
                        x,y = link_point(link_selectors[link_index], f'ordinary-link-point-{link_index}')
                        links_before = len([event for event in events if event['kind'] == 'link'])
                        lp = x | (y << 16)
                        user.PostMessageW(browser_hwnd, 0x201, 1, lp)
                        user.PostMessageW(browser_hwnd, 0x202, 0, lp)
                        collect(.25)
                        assert len([event for event in events if event['kind'] == 'link']) == links_before + 1, events
                    x,y = link_point(link_selectors[1], 'ordinary-internal-point')
                    lp = x | (y << 16)
                    user.PostMessageW(browser_hwnd, 0x201, 1, lp)
                    user.PostMessageW(browser_hwnd, 0x202, 0, lp)
                    collect(.4)
                    assert js('ordinary-internal-state', 'NotableReader.state()')['page'] == 3
                    # Only verified legacy quote-only popups disappear. Genuine
                    # imported comments and the highlight appearance survive.
                    js('popup-page', 'document.getElementById("pageNumber").value="1";document.getElementById("pageNumber").dispatchEvent(new Event("change"));true', .3)
                    popup_state = js('popup-state', '(()=>{const legacy=document.querySelector("[data-annotation-id=\\"' + suppressed_popup_ids['1'][0] + '\\"]");const genuine=document.querySelector("[data-annotation-id=\\"' + genuine_id + '\\"]");return {legacyPresent:!!legacy,legacyPopup:legacy?.getAttribute("aria-haspopup"),legacyTrigger:!!legacy?.querySelector(".popupTriggerArea"),genuinePresent:!!genuine,genuinePopup:genuine?.getAttribute("aria-haspopup"),genuineTrigger:!!genuine?.querySelector(".popupTriggerArea")}})()')
                    assert popup_state['legacyPresent'] and not popup_state['legacyPopup'] and not popup_state['legacyTrigger'], popup_state
                    assert popup_state['genuinePresent'] and (popup_state['genuinePopup'] or popup_state['genuineTrigger']), popup_state
                    # Ordinary text dragging still selects text rather than panning.
                    js('text-setup', 'document.getElementById("zoom").value="2";document.getElementById("zoom").dispatchEvent(new Event("change"));document.getElementById("pageNumber").value="1";document.getElementById("pageNumber").dispatchEvent(new Event("change"));document.getElementById("viewerContainer").scrollLeft=0;document.getElementById("viewerContainer").scrollTop=0;window.getSelection().removeAllRanges();true', .3)
                    tx,ty = js('text-point', '(()=>{const r=document.querySelector(".textLayer span").getBoundingClientRect();return [Math.round((r.x+4)*devicePixelRatio),Math.round((r.y+r.height*.5)*devicePixelRatio)]})()')
                    user.PostMessageW(browser_hwnd, 0x200, 0, tx | (ty << 16))
                    user.PostMessageW(browser_hwnd, 0x201, 1, tx | (ty << 16))
                    user.PostMessageW(browser_hwnd, 0x200, 1, (tx+180) | (ty << 16))
                    user.PostMessageW(browser_hwnd, 0x202, 0, (tx+180) | (ty << 16))
                    collect(.2)
                    selected_text = js('selected-text', 'window.getSelection().toString()')
                    assert selected_text and not js('text-pan-absent', 'NotableReader.state()')['panning'], selected_text
                    print(json.dumps({'pan_before':pan_before['scroll'],'pan_after':pan_after['scroll'],'plain_selection':selected_text}),flush=True)
                    js('layout-warning', 'window.dispatchEvent(new ErrorEvent("error",{message:"ResizeObserver loop completed with undelivered notifications."}));true')
                    warning_state = js('warning-state', 'NotableReader.state()')
                    assert warning_state['loaded'] and warning_state['renderedPages'] and warning_state['lastWarning'].startswith('ResizeObserver'), warning_state
                    assert any(event['kind'] == 'warning' for event in events), events
                    errors = [event for event in events if event['kind'] == 'error']
                    assert not errors, errors
                    assert bounds() == before
                    js('restore-fit', 'document.getElementById("zoom").value="page-width";document.getElementById("zoom").dispatchEvent(new Event("change"));true', .3)
                    width_before = js('width-before', 'NotableReader.state()')
                    root.geometry('500x600+30000+30000')
                    root.update()
                    user.MoveWindow(hwnd, 0, 0, frame.winfo_width(), frame.winfo_height(), True)
                    collect(.5)
                    narrow = js('narrow', 'NotableReader.state()')
                    assert narrow['loaded'] and narrow['scale'] < width_before['scale'] and narrow['scaleValue'] == 'page-width', narrow
                    compact_toolbar = js('compact-toolbar', '(()=>{const b=document.getElementById("backToSelection");const t=document.getElementById("toolbar").getBoundingClientRect();return {label:getComputedStyle(b.querySelector(".button-label")).display,labelled:!!b.getAttribute("aria-label"),tip:!!b.title,right:b.getBoundingClientRect().right,toolbarRight:t.right}})()')
                    assert compact_toolbar['label'] == 'none' and compact_toolbar['labelled'] and compact_toolbar['tip'] and compact_toolbar['right'] <= compact_toolbar['toolbarRight'], compact_toolbar
                    js('narrow-long-document-title', 'NotableReader.setTitle(' + json.dumps(long_title) + ',' + json.dumps(payload['id']) + ')')
                    narrow_heading = js('narrow-document-heading', title_script)
                    assert narrow_heading['fontSize'] == '16px' and narrow_heading['height'] <= narrow_heading['lineHeight'] * 2 + 1, narrow_heading
                    assert narrow_heading['tip'] == long_title, narrow_heading
                    js('restore-narrow-document-title', 'NotableReader.setTitle(' + json.dumps(payload['title']) + ',' + json.dumps(payload['id']) + ')')
                    root.geometry('980x760+30000+30000')
                    root.update()
                    user.MoveWindow(hwnd, 0, 0, frame.winfo_width(), frame.winfo_height(), True)
                    collect(.5)
                    assert js('wide-restored', 'NotableReader.state()')['loaded']
                    toolbar_width = js('wide-toolbar-label', '({width:innerWidth,label:getComputedStyle(document.querySelector("#findToggle .button-label")).display})')
                    assert (toolbar_width['label'] == 'none') == (toolbar_width['width'] <= 700), toolbar_width
                    root.geometry('1400x760+30000+30000')
                    root.update()
                    user.MoveWindow(hwnd, 0, 0, frame.winfo_width(), frame.winfo_height(), True)
                    collect(.4)
                    assert js('full-toolbar-label', 'getComputedStyle(document.querySelector("#findToggle .button-label")).display') != 'none'
                    root.geometry('980x760+30000+30000')
                    root.update()
                    user.MoveWindow(hwnd, 0, 0, frame.winfo_width(), frame.winfo_height(), True)
                    collect(.3)
                    repeated_payload = {**payload,'id':'repeated-excerpts','url':origin + '/.test-tmp/reader-assets-repeated.pdf','page':1,'rect':None,'terms':['tantalum'],'hasSelection':True,
                                        'mainHits': printed_hits(1, 'tantalum', repeated_pdf)}
                    js('repeated-open', 'void NotableReader.open(' + json.dumps(repeated_payload) + ');true', .7)
                    repeated_states = []
                    js('reading-position-setup', 'document.getElementById("zoom").value="2";document.getElementById("zoom").dispatchEvent(new Event("change"));document.getElementById("viewerContainer").scrollLeft=80;document.getElementById("viewerContainer").scrollTop=160;true', .3)
                    reading_before = js('reading-before', 'NotableReader.state()')
                    js('reading-enter', 'NotableReader.setExpanded(true);true', .3)
                    assert abs(js('reading-enter-state', 'NotableReader.state()')['scale'] - 1.25) < .001
                    js('reading-manual-zoom', 'document.getElementById("zoom").value="1.5";document.getElementById("zoom").dispatchEvent(new Event("change"));NotableReader.setExpanded(true);true', .2)
                    assert abs(js('reading-manual-state', 'NotableReader.state()')['scale'] - 1.5) < .001
                    js('reading-exit', 'NotableReader.setExpanded(false);true', .4)
                    reading_restored = js('reading-restored', 'NotableReader.state()')
                    assert reading_restored['scale'] == reading_before['scale'], (reading_before,reading_restored)
                    assert abs(reading_restored['scroll']['top'] - reading_before['scroll']['top']) < 2 and abs(reading_restored['scroll']['left'] - reading_before['scroll']['left']) < 2, (reading_before,reading_restored)
                    # Exiting restores the previous zoom while retaining the
                    # user's current reading location, not the entry page.
                    js('reading-browse-enter', 'NotableReader.setExpanded(true);true', .3)
                    js('reading-browse-page', 'document.getElementById("pageNumber").value="3";document.getElementById("pageNumber").dispatchEvent(new Event("change"));document.getElementById("viewerContainer").scrollTop+=140;true', .3)
                    reading_browsed = js('reading-browsed', 'NotableReader.state()')
                    logical_before_exit = js('reading-logical-before-exit', '(()=>{const s=NotableReader.state(),p=document.querySelectorAll(".page")[s.page-1].getBoundingClientRect(),v=document.getElementById("viewerContainer").getBoundingClientRect();return {page:s.page,x:(v.left-p.left)/s.scale,y:(v.top-p.top)/s.scale}})()')
                    js('reading-browse-exit', 'NotableReader.setExpanded(false);true', .4)
                    reading_browse_restored = js('reading-browse-restored', 'NotableReader.state()')
                    logical_after_exit = js('reading-logical-after-exit', '(()=>{const s=NotableReader.state(),p=document.querySelectorAll(".page")[s.page-1].getBoundingClientRect(),v=document.getElementById("viewerContainer").getBoundingClientRect();return {page:s.page,x:(v.left-p.left)/s.scale,y:(v.top-p.top)/s.scale}})()')
                    assert reading_browse_restored['page'] == 3 and reading_browse_restored['scale'] == reading_before['scale'], (reading_browsed,reading_browse_restored)
                    assert abs(logical_after_exit['y'] - logical_before_exit['y']) < 2, (logical_before_exit,logical_after_exit)
                    for index, hit in enumerate(repeated_hits):
                        descriptor = {'index':index,'term':hit['term'],'context':hit['snippet'],
                            'before':repeated_text[max(0,hit['start']-100):hit['start']],
                            'after':repeated_text[hit['end']:hit['end']+100], 'fitWidth': True}
                        js(f'repeated-hit-{index}', 'NotableReader.selectMatch(' + json.dumps(descriptor) + ')', .3)
                        repeated_state = js(f'repeated-hit-state-{index}', 'NotableReader.state()')
                        assert repeated_state['selectedMatch'] == {'pageIdx':0,'matchIdx':index}, (descriptor,repeated_state)
                        assert repeated_state['scaleValue'] == 'page-width' and repeated_state['scroll']['left'] < 1, repeated_state
                        repeated_states.append(repeated_state)
                    assert len(repeated_states) == 4
                    js('local-find-zoom', 'document.getElementById("zoom").value="2";document.getElementById("zoom").dispatchEvent(new Event("change"));document.getElementById("findToggle").click();document.getElementById("findInput").value="passage";document.getElementById("findInput").dispatchEvent(new Event("input"));true', .5)
                    js('local-find-next', 'document.getElementById("findNext").click();true', .4)
                    local_find_state = js('local-find-fit-width-state', 'NotableReader.state()')
                    assert local_find_state['scaleValue'] == 'page-width' and local_find_state['scroll']['left'] < 1, local_find_state
                    # Every arrow must select AND reveal the exact occurrence,
                    # including offscreen lines, mixed page sizes and wrapping.
                    def check_local_hit(name, occurrence, scale_value='page-width'):
                        state = js(name, '''(()=>{
                            const s=NotableReader.state();
                            const page=document.querySelectorAll('.page')[s.selectedMatch.pageIdx];
                            const marks=Array.from(page?.querySelectorAll('.textLayer .highlight.selected') || []);
                            const v=document.getElementById('viewerContainer').getBoundingClientRect();
                            return {...s, selectedText:marks.map(m=>m.textContent).join(''),
                                visible:marks.length>0 && marks.every(m=>{
                                    const r=m.getBoundingClientRect();
                                    return r.height>0 && r.top>=v.top && r.bottom<=v.bottom;
                                })};
                        })()''')
                        assert state['selectedMatch'] == {'pageIdx':occurrence // 4,'matchIdx':occurrence % 4}, state
                        assert state['matches'] == {'current':occurrence + 1,'total':12}, state
                        assert state['selectedText'] == 'passage' and state['visible'], state
                        assert state['scaleValue'] == scale_value and state['scroll']['left'] < 1, state
                        assert not state['lastWarning'], state
                        return state
                    check_local_hit('local-find-first-next-visible', 1)
                    for direction, button in ((1, 'findNext'), (-1, 'findPrevious')):
                        for step in range(1, 13):
                            click(button)
                            check_local_hit(f'local-find-{direction}-{step}', (1 + direction * step) % 12)
                    # Clicking an arrow before the input debounce expires must
                    # cancel that delayed search rather than advancing twice.
                    js('local-find-pending-input', 'document.getElementById("findInput").dispatchEvent(new Event("input"));document.getElementById("findNext").click();true', .5)
                    check_local_hit('local-find-pending-input-stable', 2)
                    js('local-find-reading-mode', 'NotableReader.setExpanded(true);true', .3)
                    for occurrence, button in ((3, 'findNext'), (4, 'findNext'),
                                               (3, 'findPrevious'), (2, 'findPrevious')):
                        click(button)
                        check_local_hit(f'local-find-reading-{occurrence}', occurrence, '1.25')
                    js('local-find-reading-exit', 'NotableReader.setExpanded(false);true', .4)
                    js('local-find-rapid-arrows', 'for(let i=0;i<3;i++)document.getElementById("findNext").click();true', .5)
                    check_local_hit('local-find-rapid-arrows-state', 5)
                    js('local-find-close-keeps-zoom', 'document.getElementById("findClose").click();true', .4)
                    local_find_closed = js('local-find-close-fit-width-state', 'NotableReader.state()')
                    assert local_find_closed['scaleValue'] == 'page-width' and local_find_closed['scroll']['left'] < 1, local_find_closed
                    # Fitting uses the result page's dimensions even after
                    # browsing to a different-sized PDF page in local Find.
                    js('mixed-page-browse', 'document.getElementById("pageNumber").value="2";document.getElementById("pageNumber").dispatchEvent(new Event("change"));true', .2)
                    js('mixed-page-main-arrow', 'NotableReader.selectMatch({index:0,term:"tantalum",fitWidth:true});true', .4)
                    mixed_page = js('mixed-page-state', 'NotableReader.state()')
                    assert mixed_page['page'] == 1 and mixed_page['scroll']['left'] < 1 and abs(mixed_page['scale'] - repeated_states[0]['scale']) < .001, (mixed_page,repeated_states[0])
                    # Actual enabled-field occurrences define blue main-search
                    # marks; a reliable note rectangle disambiguates its single
                    # word from the same word in a disabled document title.
                    quote_hit = {'field':'quote','text':'tantalum','normalized_text':'tantalum',
                                 'term':'tantalum','before':'','after':'','snippet':'tantalum'}
                    scoped_payload = {**payload,'id':'enabled-quote-only','url':origin + '/.test-tmp/reader-assets-scoped.pdf',
                                      'page':1,'rect':quote_rect,'terms':['tantalum'],'mainHits':[quote_hit],
                                      'hasSelection':True,'expanded':False}
                    js('enabled-quote-open', 'void NotableReader.open(' + json.dumps(scoped_payload) + ');true', .8)
                    scoped = js('enabled-quote-state', 'NotableReader.state()')
                    assert scoped['matches']['total'] == 1 and scoped['selectedMatch'] == {'pageIdx':0,'matchIdx':0}, scoped
                    highlight_script = 'Array.from(document.querySelectorAll(".textLayer .highlight")).map(h=>({text:h.textContent,selected:h.classList.contains("selected"),color:getComputedStyle(h).backgroundColor}))'
                    scoped_marks = js('enabled-quote-marks', highlight_script)
                    assert len(scoped_marks) == 1 and scoped_marks[0]['text'].lower() == 'tantalum' and scoped_marks[0]['selected'], scoped_marks
                    assert scoped_marks[0]['color'].startswith('rgba(65, 105, 225,'), scoped_marks
                    for field in ('title','comment','ocr'):
                        hidden_hit = {**quote_hit,'field':field}
                        js('metadata-hit-' + field, 'document.getElementById("zoom").value="3";document.getElementById("zoom").dispatchEvent(new Event("change"));NotableReader.selectMatch(' + json.dumps({'index':0,**hidden_hit,'mainHits':[hidden_hit],'fitWidth':True}) + ');true', .3)
                        assert js('metadata-marks-' + field, highlight_script) == [], field
                        metadata_state = js('metadata-state-' + field, 'NotableReader.state()')
                        assert metadata_state['page'] == 1 and metadata_state['scaleValue'] == 'page-width', metadata_state
                    js('restore-quote-main', 'NotableReader.selectMatch(' + json.dumps({'index':0,**quote_hit,'mainHits':[quote_hit]}) + ');true', .3)
                    js('green-pdf-find', 'document.getElementById("findToggle").click();document.getElementById("findInput").value="tantalum";document.getElementById("findInput").dispatchEvent(new Event("input"));true', .5)
                    pdf_find_marks = js('green-pdf-find-marks', highlight_script)
                    assert len(pdf_find_marks) == 3 and all('40, 123, 72' in mark['color'] or '188, 229, 201' in mark['color'] for mark in pdf_find_marks), pdf_find_marks
                    close_size = js('find-clear-size', 'getComputedStyle(document.querySelector("#findClose .clear-icon")).width')
                    assert close_size == '20px', close_size
                    js('close-green-pdf-find', 'document.getElementById("findClose").click();true', .4)
                    assert js('restored-blue-main', highlight_script) == scoped_marks
                    js('reading-default-setup', 'document.getElementById("zoom").value="2";document.getElementById("zoom").dispatchEvent(new Event("change"));NotableReader.setExpanded(true);true', .3)
                    js('reading-arrow-default', 'document.getElementById("zoom").value="3";document.getElementById("zoom").dispatchEvent(new Event("change"));NotableReader.selectMatch(' + json.dumps({'index':0,**quote_hit,'mainHits':[quote_hit],'fitWidth':True}) + ');true', .4)
                    reading_arrow = js('reading-arrow-state', 'NotableReader.state()')
                    assert abs(reading_arrow['scale'] - 1.25) < .001 and reading_arrow['scroll']['left'] < 1, reading_arrow
                    hidden_hit = {**quote_hit,'field':'comment'}
                    js('reading-comment-arrow-default', 'document.getElementById("zoom").value="3";document.getElementById("zoom").dispatchEvent(new Event("change"));NotableReader.selectMatch(' + json.dumps({'index':0,**hidden_hit,'mainHits':[hidden_hit],'fitWidth':True}) + ');true', .3)
                    assert abs(js('reading-comment-arrow-state', 'NotableReader.state()')['scale'] - 1.25) < .001
                    js('reading-not-only-arrow-default', 'document.getElementById("zoom").value="3";document.getElementById("zoom").dispatchEvent(new Event("change"));NotableReader.selectMatch({index:0,mainHits:[],fitWidth:true});true', .3)
                    assert abs(js('reading-not-only-arrow-state', 'NotableReader.state()')['scale'] - 1.25) < .001
                    js('reading-reset-default', 'document.getElementById("zoom").value="3";document.getElementById("zoom").dispatchEvent(new Event("change"));NotableReader.resetView();true', .3)
                    assert abs(js('reading-reset-state', 'NotableReader.state()')['scale'] - 1.25) < .001
                    js('leave-reading-default-test', 'NotableReader.setExpanded(false);true', .3)
                    source_hits = printed_hits(1, 'tantalum', source_order_pdf)
                    assert len(source_hits) == 4 and 'tan-\ntalum' in source_hits[-1]['text'], source_hits
                    source_payload = {**scoped_payload,'id':'wrapped-source-order','url':origin + '/.test-tmp/reader-assets-source-order.pdf',
                                      'rect':None,'mainHits':source_hits}
                    js('source-order-open', 'void NotableReader.open(' + json.dumps(source_payload) + ');true', .7)
                    source_navigation = []
                    for index, hit in enumerate(source_hits):
                        js('source-order-hit-' + str(index), 'NotableReader.selectMatch(' + json.dumps({'index':index,**hit,'mainHits':source_hits,'fitWidth':True}) + ');true', .25)
                        source_state = js('source-order-state-' + str(index), 'NotableReader.state()')
                        assert source_state['selectedMatch'] == {'pageIdx':0,'matchIdx':index}, (hit,source_state)
                        source_navigation.append(source_state)
                    assert source_navigation[-1]['matches']['total'] == 4
                    for case, query, expected_count in (('overlapping', 'gold OR "old imaging"', 1),
                                                         ('casefold', 'strasse', 2)):
                        union_hits = printed_hits(1, query, union_pdf)
                        assert len(union_hits) == expected_count, union_hits
                        union_payload = {**source_payload,'id':case + '-union','url':origin + '/.test-tmp/reader-assets-union.pdf',
                                         'mainHits':union_hits,'terms':[query]}
                        js(case + '-open', 'void NotableReader.open(' + json.dumps(union_payload) + ');true', .5)
                        for index, hit in enumerate(union_hits):
                            js(case + '-hit-' + str(index), 'NotableReader.selectMatch(' + json.dumps({'index':index,**hit,'mainHits':union_hits}) + ');true', .2)
                            union_state = js(case + '-state-' + str(index), 'NotableReader.state()')
                            assert union_state['selectedMatch'] == {'pageIdx':0,'matchIdx':index} and union_state['matches']['total'] == expected_count, (hit,union_state)
                    # Failed/locked loads show actionable errors, then a later
                    # selection recovers without a stale page or black surface.
                    invalid_payload = {**payload, 'id':'missing-pdf', 'url':origin + '/.test-tmp/missing-reader-test.pdf'}
                    js('missing-open', 'void NotableReader.open(' + json.dumps(invalid_payload) + ');true', .6)
                    invalid = js('missing-state', 'NotableReader.state()')
                    assert not invalid['loaded'] and invalid['message'], invalid
                    locked_payload = {**payload, 'id':'locked-pdf', 'url':origin + '/.test-tmp/reader-assets-password.pdf'}
                    js('locked-open', 'void NotableReader.open(' + json.dumps(locked_payload) + ');true', .7)
                    locked = js('locked-state', 'NotableReader.state()')
                    assert not locked['loaded'] and 'password protected' in locked['message'], locked
                    payload.update(id='recovered-reader', page=1)
                    js('recovery-open', 'void NotableReader.open(' + json.dumps(payload) + ');true', .8)
                    recovered = js('recovery-state', 'NotableReader.state()')
                    assert recovered['loaded'] and recovered['renderedPages'] and recovered['message'] == '', recovered
                    # Superseded errors must never replace the most recent PDF.
                    payload.update(id='rapid-latest')
                    js('rapid-replace', 'void NotableReader.open(' + json.dumps(invalid_payload) + ');void NotableReader.open(' + json.dumps(payload) + ');true', .8)
                    latest = js('rapid-latest-state', 'NotableReader.state()')
                    assert latest['loaded'] and latest['id'] == 'rapid-latest' and latest['message'] == '', latest
                    initialization_bursts = []
                    for burst, delay_ms in enumerate((0, 2, 8, 20, 50, 100)):
                        first = {**payload,'id':f'initializing-{burst}','url':origin + f'/.test-tmp/reader-assets.pdf?burst={burst}-first','page':1}
                        final = {**payload,'id':f'latest-{burst}','url':origin + f'/.test-tmp/reader-assets.pdf?burst={burst}-latest','page':3}
                        js(f'initialization-burst-{burst}', 'void NotableReader.open(' + json.dumps(first) + ');setTimeout(()=>void NotableReader.open(' + json.dumps(final) + '),' + str(delay_ms) + ');true', .7)
                        state = js(f'initialization-burst-state-{burst}', 'NotableReader.state()')
                        assert state['loaded'] and state['id'] == final['id'] and state['page'] == 3 and state['renderedPages'] > 0 and not state['message'], state
                        initialization_bursts.append(state)
                    js('clear-viewer', 'void NotableReader.clear("Select another result.","cleared");NotableReader.resetView();true', .3)
                    cleared = js('cleared-state', '({...NotableReader.state(),backDisabled:document.getElementById("backToSelection").disabled,findDisabled:document.getElementById("findToggle").disabled})')
                    assert not cleared['loaded'] and cleared['backDisabled'] and cleared['findDisabled'] and 'Select another' in cleared['message'], cleared
                    cleared_heading = js('cleared-document-heading', title_script)
                    assert cleared_heading['hidden'] and not cleared_heading['text'] and not cleared_heading['tip'], cleared_heading
                    js('after-clear-open', 'void NotableReader.open(' + json.dumps(payload) + ');true', .7)
                    assert js('after-clear-state', 'NotableReader.state()')['loaded']
                    result = {'easy_drag': False, 'before': before, 'after': after, 'pointer': pointer, 'states': results, 'browse': browse,
                              'reclaimed':reclaimed,'selected':selected,'queued':queued,'absent':absent,'empty_selected_page':empty_page,
                              'reset_before':reset_before,'reset_after':reset,'invalid':invalid,'locked':locked,'recovered':recovered,
                              'latest':latest,'initialization_bursts':initialization_bursts,'repeated_states':repeated_states,
                              'link_pan_states':link_pan_states,'link_reset':link_reset,'popup_state':popup_state,
                              'reading_before':reading_before,'reading_restored':reading_restored,
                              'reading_browsed':reading_browsed,'reading_browse_restored':reading_browse_restored,
                              'cleared':cleared,'errors_before_expected_failures':errors}
                output.append(result)
                print(json.dumps({'loaded':result['latest']['loaded'],'repeated_occurrences':len(result['repeated_states']),
                    'rapid_initializations':len(result['initialization_bursts']),'ctrl_double_reset':result['reset_after']['scaleValue'],
                    'missing_password_recovery':result['recovered']['loaded'],'unexpected_errors':len(result['errors_before_expected_failures'])}),flush=True)
            finally:
                if process.is_alive():
                    try:
                        if hwnd:
                            user.ShowWindow(hwnd, 0)
                            user.SetParent(hwnd, None)
                        parent.send('close')
                    except (BrokenPipeError, EOFError):
                        pass
                deadline = time.monotonic() + 8
                while process.is_alive() and time.monotonic() < deadline:
                    root.update()
                    try:
                        while parent.poll():
                            parent.recv()
                    except (EOFError, BrokenPipeError, OSError):
                        pass
                    time.sleep(.01)
                process.join(0)
                if process.is_alive():
                    process.terminate()
                    process.join(2)
                parent.close()
                root.destroy()
                assert process.exitcode == 0, f'Reader host did not close cleanly: {process.exitcode}'
    finally:
        server.shutdown()
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == original_pdf_digest, 'Reader modified its source PDF'
        assert hashlib.sha256(scoped_pdf.read_bytes()).hexdigest() == scoped_pdf_digest, 'Reader modified its scoped source PDF'
        (ROOT / '.test-tmp/reader-frontend-results.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print('TRUSTED POINTER AND READER REGRESSIONS PASSED', flush=True)


if __name__ == '__main__':
    mp.freeze_support()
    main()
