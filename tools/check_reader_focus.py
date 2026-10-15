"""Real native focus checks, permitted only on an inactive test desktop."""
import ctypes
from ctypes import wintypes
import functools
import http.server
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from note_organizer.reader_host import NativeChild
from note_organizer.widgets import EntryPlaceholder


class GUIInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("hwndActive", wintypes.HWND), ("hwndFocus", wintypes.HWND),
                ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND),
                ("rcCaret", wintypes.RECT)]


def host(pipe, url, unused):
    import webview
    class API:
        def event(self, data):
            pipe.send({'event': data})
    window = webview.create_window('Isolated focus regression', url, js_api=API(),
        width=700, height=600, hidden=True, frameless=True, text_select=True,
        easy_drag=False, draggable=False, shadow=False, focus=False)
    def started():
        window.events.shown.wait(20)
        window.focus = True  # same startup-to-embedded transition as production
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
            try:
                pipe.send({'response': command['name'], 'result': window.evaluate_js(command['js'])})
            except Exception as exc:
                pipe.send({'response': command['name'], 'error': str(exc)})
    webview.start(started, gui='edgechromium', private_mode=True)


def main():
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.GetThreadDesktop.argtypes = (wintypes.DWORD,)
    user.GetThreadDesktop.restype = wintypes.HANDLE
    user.GetUserObjectInformationW.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                              wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    name, required = ctypes.create_unicode_buffer(256), wintypes.DWORD()
    user.GetUserObjectInformationW(user.GetThreadDesktop(kernel.GetCurrentThreadId()), 2,
                                  name, ctypes.sizeof(name), ctypes.byref(required))
    assert name.value.startswith('NotableTests-') and name.value == os.environ.get('NOTABLE_TEST_DESKTOP'), \
        'Focus checks may run only through tools/run_ui_tests.py on its private inactive desktop'
    print('ISOLATED DESKTOP', name.value, flush=True)
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.GetGUIThreadInfo.argtypes = (wintypes.DWORD, ctypes.POINTER(GUIInfo))
    user.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user.SendMessageW.restype = wintypes.LPARAM
    root = tk.Tk()
    root.withdraw()
    root.geometry('980x760+20+20')
    query = tk.StringVar()
    entry = ttk.Entry(root, textvariable=query)
    entry.pack(fill='x')
    EntryPlaceholder(entry, 'Search notes…', query)
    scope = ttk.Combobox(root, values=('Notes', 'PDFs', 'All'), state='readonly')
    scope.current(0)
    scope.pack(fill='x')
    frame = tk.Frame(root)
    frame.pack(fill='both', expand=True)
    root.update_idletasks()
    user.GetParent.argtypes = (wintypes.HWND,)
    user.GetParent.restype = wintypes.HWND
    wrapper = user.GetParent(root.winfo_id())
    user.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
    user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
    user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user.SetFocus.argtypes = (wintypes.HWND,)
    user.SetFocus.restype = wintypes.HWND
    root.deiconify()
    root.update()
    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript', '.wasm': 'application/wasm'}
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    parent, child = mp.get_context('spawn').Pipe()
    process = mp.get_context('spawn').Process(target=host, args=(child, f'http://127.0.0.1:{server.server_port}/note_organizer/assets/reader/index.html', False), daemon=True)
    process.start()
    child.close()
    events, responses = [], {}
    hwnd = None
    def collect(seconds):
        nonlocal hwnd
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            root.update()
            while parent.poll():
                data = parent.recv()
                if 'hwnd' in data: hwnd = data['hwnd']
                elif 'response' in data: responses[data['response']] = data
                elif 'event' in data: events.append(data['event'])
                else: print(data, flush=True)
            time.sleep(.01)
    def js(name, code):
        parent.send({'name': name, 'js': code})
        until = time.monotonic() + 10
        while name not in responses and time.monotonic() < until: collect(.05)
        assert name in responses, name
        result = responses.pop(name)
        assert 'error' not in result, result
        return result['result']
    def info(handle):
        tid = user.GetWindowThreadProcessId(handle, None)
        result = GUIInfo(cbSize=ctypes.sizeof(GUIInfo))
        user.GetGUIThreadInfo(tid, ctypes.byref(result))
        return {'thread': tid, 'active': result.hwndActive, 'focus': result.hwndFocus, 'capture': result.hwndCapture}
    def snapshot(label):
        print(json.dumps({'label': label, 'foreground': user.GetForegroundWindow(), 'tk_focus': str(root.focus_get()), 'root': info(root.winfo_id()), 'reader': info(hwnd)}), flush=True)
    native = None
    try:
        until = time.monotonic() + 40
        while time.monotonic() < until and not (hwnd and any(e.get('kind') == 'ready' for e in events)): collect(.1)
        assert hwnd and any(e.get('kind') == 'ready' for e in events), events
        native = NativeChild(hwnd, frame)
        native.show(True)
        collect(.5)
        native_user = native.user
        # Windows intentionally exposes no foreground HWND on an inactive
        # desktop. The production guard is independently tested; substitute
        # this desktop's actual active window solely for that guard here.
        user.GetActiveWindow.restype = wintypes.HWND
        class InactiveDesktopUser:
            def __getattr__(self, name):
                return getattr(native_user, name)
            def GetForegroundWindow(self):
                assert user.GetForegroundWindow() is None
                return user.GetActiveWindow()
        native.user = InactiveDesktopUser()
        import pymupdf
        pdf = ROOT / '.test-tmp/reader-focus.pdf'
        with pymupdf.open() as document:
            for number in (1, 2):
                page = document.new_page()
                page.insert_text((60, 80), f'Focus regression page {number}', fontsize=18)
                page.insert_text((60, 120), 'Tantalum oxide selectable text.', fontsize=14)
            document.save(pdf)
        payload = {'id': 'focus-check', 'url': f'http://127.0.0.1:{server.server_port}/.test-tmp/reader-focus.pdf',
                   'title': 'Native focus regression', 'page': 1, 'terms': ['tantalum'], 'hasSelection': True}
        js('open', 'void NotableReader.open(' + json.dumps(payload) + ');true')
        collect(1)
        until = time.monotonic() + 15
        while not js('loaded-check', 'NotableReader.state().loaded') and time.monotonic() < until:
            collect(.1)
        assert js('loaded-final', 'NotableReader.state().loaded')
        snapshot('embedded')
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        handles=[]
        @callback_type
        def enum(handle, _):
            name=ctypes.create_unicode_buffer(256)
            user.GetClassNameW(handle, name, 256)
            handles.append((int(handle), name.value))
            return True
        user.EnumChildWindows.argtypes = (wintypes.HWND, callback_type, wintypes.LPARAM)
        user.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        user.EnumChildWindows(hwnd, enum, 0)
        print(json.dumps({'hwnd': hwnd, 'entry': entry.winfo_id(), 'exstyle': hex(native.user.GetWindowLongPtrW(hwnd, -20)), 'handles': handles}), flush=True)
        browser = next(h for h,n in handles if n in ('Chrome_RenderWidgetHostHWND', 'Chrome_WidgetWin_1'))
        clicks = []
        root.bind('<ButtonPress-1>', lambda event: clicks.append(str(event.widget)), add='+')
        # Reproduce the native/Tk disagreement with the repair temporarily
        # disconnected, then exercise exactly the same click class bindings.
        root.unbind('<ButtonPress-1>', native.focus_binding)
        native.focus_binding = None
        user.PostMessageW(browser,0x201,1,50|(20<<16))
        user.PostMessageW(browser,0x202,0,50|(20<<16))
        collect(.1)
        entry.event_generate('<ButtonPress-1>', x=10, y=10)
        entry.event_generate('<ButtonRelease-1>', x=10, y=10)
        collect(.1)
        broken = user.GetFocus() != entry.winfo_id()
        print('BASELINE DISAGREEMENT REPRODUCED', broken, info(entry.winfo_id()), flush=True)
        assert broken, 'The expected native/Tk focus disagreement was not reproduced'
        native.focus_binding = root.bind('<ButtonPress-1>', native.restore_tk_focus, add='+')
        clicks.clear()
        for index in range(12):
            if index in (2, 7):
                scope.event_generate('<ButtonPress-1>', x=max(5, scope.winfo_width()-10), y=10)
                scope.event_generate('<ButtonRelease-1>', x=max(5, scope.winfo_width()-10), y=10)
                collect(.1)
                root.tk.call('ttk::combobox::Unpost', str(scope))
                scope.set(('Notes', 'PDFs', 'All')[index % 3])
                assert scope.instate(['readonly'])
            if index in (4, 9):
                native.show(False)
                frame.pack_forget()
                collect(.1)
                frame.pack(fill='both', expand=True)
                root.update()
                native.resize()
                native.show(True)
                collect(.1)
            js('find-open-'+str(index), 'document.getElementById("findToggle").click();document.getElementById("findInput").value="oxide";document.getElementById("findInput").dispatchEvent(new Event("input"));document.getElementById("findInput").focus();true')
            collect(.1)
            snapshot('js-find-focus-'+str(index))
            lp=400|(300<<16)
            user.PostMessageW(browser,0x201,1,lp)
            user.PostMessageW(browser,0x202,0,lp)
            collect(.1)
            snapshot('pdf-click-'+str(index))
            entry.delete(0,'end')
            entry.insert(0,'existing' if index % 2 else '')
            user.PostMessageW(entry.winfo_id(),0x201,1,10|(10<<16))
            user.PostMessageW(entry.winfo_id(),0x202,0,10|(10<<16))
            collect(.1)
            snapshot('entry-click-'+str(index))
            target = entry.placeholder.label if index % 2 == 0 and entry.placeholder.label.winfo_ismapped() else entry
            target.event_generate('<ButtonPress-1>', x=10, y=10)
            target.event_generate('<ButtonRelease-1>', x=10, y=10)
            collect(.1)
            snapshot('tk-class-click-'+str(index))
            assert user.GetFocus() == entry.winfo_id(), info(entry.winfo_id())
            user.PostMessageW(entry.winfo_id(),0x102,ord('x'),0)
            collect(.1)
            print('ENTRY VALUE', entry.get(), flush=True)
            assert 'x' in entry.get(), (index, entry.get())
            assert not native.user.GetWindowLongPtrW(hwnd, -20) & 0x08000000
            assert js('still-loaded-'+str(index), 'NotableReader.state().loaded')
        assert len([item for item in clicks if 'entry' in item]) == 12, clicks
        print('PASS: 12 native WebView focus -> Tk class click -> native keyboard insertion cycles, empty/populated fields, Find, dropdown, hide/remap', flush=True)
    finally:
        if native: native.detach()
        parent.send('close')
        until = time.monotonic() + 6
        while process.is_alive() and time.monotonic() < until:
            root.update()
            time.sleep(.01)
        process.join(0)
        if process.is_alive(): process.terminate();process.join(2)
        print('EXITCODE', process.exitcode, flush=True)
        parent.close()
        root.destroy()
        server.shutdown()


if __name__ == '__main__':
    mp.freeze_support()
    main()
