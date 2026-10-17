"""Capture current UI walkthroughs on an inactive desktop using example data only.

Run: .venv/Scripts/python.exe tools/run_ui_tests.py scripts/capture_manual.py
No account is contacted and no window appears on the user's desktop.
"""
from pathlib import Path
import ctypes
from ctypes import wintypes
import gc
import faulthandler
import json
from multiprocessing import freeze_support
import os
import re
import sys
import threading
import time
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from note_organizer.archive_ui import ArchiveReviewWindow
from note_organizer.extraction import extract
from note_organizer.service import Service
from note_organizer.storage import Store, DEFAULT_SETTINGS
from note_organizer.library_paths import inspect_library
from note_organizer.ui import App
from note_organizer.widgets import dismiss_tooltips, fit_dialog
from tests.reader_app_regression import capture_test_window, require_private_desktop
from tests.test_notebook import sample_pdf
from tests.test_preferences_ui import descendants
from tests.ui_helpers import settle_library

OUTPUT = ROOT / '.test-tmp' / 'manual-captures'


def manual_reader_host(connection, dpi_awareness=0):
    """Use the real reader host; drive its own DOM only for offline screenshots."""
    import webview
    from note_organizer.reader_host import run_reader_host
    original = webview.create_window
    finished=threading.Event()
    def create(*args, **kwargs):
        window = original(*args, **kwargs)
        def inspect():
            found = False
            window.events.loaded.wait(30)
            for _ in range(6000):
                if finished.is_set() or (window.native is not None and window.native.IsDisposed):
                    return
                try:
                    if (OUTPUT/'pdf-find-request').exists() and not found:
                        ready = window.evaluate_js('Boolean(window.NotableReader?.state().loaded)')
                        if ready:
                            window.evaluate_js('document.getElementById("findToggle").click();'
                                'document.getElementById("findInput").value="stable";'
                                'document.getElementById("findInput").dispatchEvent(new Event("input"));true')
                            found = True
                    data = window.evaluate_js('JSON.stringify({dpr:devicePixelRatio,ready:Boolean(window.NotableReader?.state().loaded),'
                        'find:!document.getElementById("findbar").hidden,controls:Object.fromEntries('
                        '["zoom","findToggle","findInput","findNext","findPrevious","findClose","backToSelection"].map(id=>'
                        '{let e=document.getElementById(id),r=e?.getBoundingClientRect();return [id,r?'
                        '[r.x,r.y,r.width,r.height]:null]}))})')
                    info = json.loads(data)
                    if info['ready']:
                        (OUTPUT/'pdf-controls.json').write_text(json.dumps(info),encoding='utf-8')
                    if found and info['find']:
                        return
                except Exception:
                    pass
                time.sleep(.1)
        threading.Thread(target=inspect,daemon=True).start()
        return window
    try:
        with patch.object(webview,'create_window',side_effect=create):
            run_reader_host(connection,dpi_awareness)
    finally:
        finished.set()


def main():
    require_private_desktop()
    faulthandler.dump_traceback_later(180, repeat=True)
    user = ctypes.windll.user32
    user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    previous_dpi = user.SetThreadDpiAwarenessContext(-4)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename in ('pdf-find-request','pdf-controls.json'):
        (OUTPUT/filename).unlink(missing_ok=True)
    folder = OUTPUT / 'example-library' / ('session-' + str(time.time_ns()))
    papers, inbox = folder / 'Papers', folder / 'Inbox'
    papers.mkdir(parents=True, exist_ok=True)
    inbox.mkdir(parents=True, exist_ok=True)
    # Regenerating the fixture uses a fresh isolated database, never user data.
    data = folder / 'Data'
    store = Store(data / 'library.sqlite3')
    project = store.add_project(papers)
    for name in ('Catalyst stability', 'Control experiment', 'Supporting measurements'):
        path = papers / (name + '.pdf')
        sample_pdf(path)
        digest, signature, metadata, notes = extract(path, DEFAULT_SETTINGS)
        store.save_scan(project, path, digest, signature, 'manual example', {**metadata, 'title': name}, notes)
    sample_pdf(inbox / 'New research paper.pdf')
    store.set_preference('remarkable', {'integration_enabled': True, 'pc_root': str(papers),
        'source_folder_id': 'literature', 'enabled': False})
    store.set_preference('remarkable_folders', [
        {'id': 'literature', 'name': 'Literature', 'path': '/Literature', 'ancestor_ids': [], 'parent': ''},
        {'id': 'experiments', 'name': 'Experiments', 'path': '/Literature/Experiments',
         'ancestor_ids': ['literature'], 'parent': 'literature'}])
    store.save_remarkable_item('review', {'name': 'Catalyst stability.pdf', 'state': 'review', 'parent': 'experiments',
        'cloud_path': '/Literature/Experiments/Catalyst stability.pdf',
        'review_pdf': str(papers / 'Catalyst stability.pdf'), 'reason_kind': 'routing',
        'reason': 'This tablet folder needs a PC destination. Review both locations before mapping.'})
    root = tk.Tk()
    root.withdraw()
    root.tk.call('tk', 'scaling', 1.25 * 96 / 72)
    errors = []
    root.report_callback_exception = lambda *args: errors.append(str(args[1]))
    host_patch = patch('note_organizer.reader_host.run_reader_host', manual_reader_host)
    host_patch.start()
    reader_load_patch=patch('note_organizer.pdf_reader.PDFReader.load_entry') if any(
        flag in sys.argv for flag in ('--only-settings','--only-menus')) else None
    if reader_load_patch:
        reader_load_patch.start()
    diagnostics_patch=patch('note_organizer.dialogs.library_diagnostics',
        side_effect=lambda active:{'active':{**inspect_library(active),'name':'Example library'},'alternatives':[]})
    diagnostics_patch.start()
    with patch.object(Service, 'start'):
        app = App(root, store, data)
        settle_library(app, root)
    app.inbox.save_config({'watch_folder': str(inbox), 'library_root': str(papers), 'naming_mode': 'Basic'})
    # Pairing presence is simulated for offline example screens only.
    app.service.remarkable.vault.path.parent.mkdir(parents=True, exist_ok=True)
    app.service.remarkable.vault.path.touch()
    app.refresh()
    settle_library(app, root)
    from note_organizer import __version__
    root.title(f'Notable {__version__} — Example library')
    root.geometry('1440x900+20+20')
    root.deiconify()
    settings_only='--only-settings' in sys.argv
    manifest = json.loads((OUTPUT/'manifest.json').read_text(encoding='utf-8')) if settings_only else {}

    def settle(seconds=.15):
        deadline = time.monotonic() + 20
        start = time.monotonic()
        while time.monotonic() < deadline:
            root.update()
            app.poll()
            pending = app.workflow_futures or (app.query_future and not app.query_future.done())
            pending = pending or getattr(app, 'notes_batch_after', None)
            if not pending and time.monotonic() - start > seconds:
                break
            time.sleep(.01)
        root.update()

    def widgets(window):
        return [w for w in descendants(window) if w.winfo_toplevel() == window and w.winfo_viewable()]

    def rect(w, window):
        return [w.winfo_rootx() - window.winfo_rootx(), w.winfo_rooty() - window.winfo_rooty(),
                w.winfo_width(), w.winfo_height()]

    def capture(name, window=root, extra=None, settle_before=True):
        if settle_before:
            settle()
        if window is not root:
            fit_dialog(window, root)
            settle(.1)
        dismiss_tooltips()
        window.lift()
        root.update()
        destination = OUTPUT / (name + '.png')
        capture_test_window(window, destination)
        # PrintWindow includes the title bar; coordinates start at window bounds.
        user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user.GetAncestor.restype = wintypes.HWND
        user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        bounds = wintypes.RECT()
        user.GetWindowRect(user.GetAncestor(window.winfo_id(), 2), ctypes.byref(bounds))
        dx, dy = window.winfo_rootx() - bounds.left, window.winfo_rooty() - bounds.top
        targets, masks = {}, []
        for w in widgets(window):
            box = rect(w, window)
            box[0] += dx
            box[1] += dy
            if 'text' in w.keys():
                label = str(w.cget('text'))
                if label:
                    targets.setdefault(label, box)
                if str(ROOT).casefold() in label.casefold():
                    safe=re.sub(re.escape(str(folder)),'Example library',label,flags=re.I)
                    safe=re.sub(re.escape(str(ROOT)),'Example library',safe,flags=re.I)
                    masks.append({'rect': box, 'text': safe})
            if isinstance(w, (ttk.Entry, ttk.Combobox)):
                value = w.get()
                targets.setdefault('field:' + value, box)
                if str(ROOT).casefold() in value.casefold():
                    masks.append({'rect': [box[0]+3, box[1]+3, box[2]-25, box[3]-6],
                                  'text': 'Example library/' + Path(value).name})
            if isinstance(w, tk.Text):
                start = '1.0'
                while True:
                    found = w.search(str(ROOT), start, stopindex='end', nocase=True)
                    if not found:
                        break
                    info = w.dlineinfo(found)
                    if info:
                        x, y, width, height, _ = info
                        masks.append({'rect': [box[0]+x, box[1]+y, min(w.winfo_width()-x-4, width), height],
                                      'text': 'Example library/' + w.get(found, found + ' lineend').split('example-library')[-1].lstrip('\\/')})
                    start = found + ' lineend +1c'
            if isinstance(w, ttk.Treeview):
                for row in w.get_children():
                    rowbox = w.bbox(row)
                    if rowbox:
                        targets['row:' + str(w.item(row, 'values')[0])] = [box[0]+rowbox[0], box[1]+rowbox[1], rowbox[2], rowbox[3]]
                    for col in w['columns']:
                        value = w.set(row, col)
                        cell = w.bbox(row, col)
                        if cell and str(ROOT).casefold() in value.casefold():
                            masks.append({'rect': [box[0]+cell[0], box[1]+cell[1], cell[2], cell[3]],
                                          'text': 'Example library/' + Path(value).name})
            if isinstance(w, ttk.Notebook):
                spans = {}
                for xx in range(w.winfo_width()):
                    try:
                        index = w.index('@' + str(xx) + ',10')
                    except tk.TclError:
                        continue
                    spans.setdefault(index, []).append(xx)
                for index, xs in spans.items():
                    targets.setdefault(w.tab(index, 'text'), [box[0]+min(xs), box[1], max(xs)-min(xs)+1, 38])
        for key, value in (extra or {}).items():
            box = rect(value, window) if hasattr(value, 'winfo_rootx') else list(value)
            box[0] += dx
            box[1] += dy
            targets[key] = box
        manifest[name] = {'file': destination.name, 'targets': targets, 'masks': masks}
        print('Captured', name, flush=True)

    def find(window, label):
        return next(w for w in widgets(window) if 'text' in w.keys() and str(w.cget('text')) == label)

    def dialog(action):
        before = set(root.winfo_children())
        result = action()
        settle()
        if hasattr(result, 'window'):
            return result.window
        if isinstance(result, tk.Toplevel):
            return result
        return next(w for w in root.winfo_children() if w not in before and isinstance(w, tk.Toplevel))

    def menu_capture(name, button):
        menu = button.action_menu
        labels = {n: menu.entrycget(n, 'label') for n in range(menu.index('end')+1)
                  if menu.type(n) != 'separator'}
        result = []
        def native_capture():
            user.SetThreadDpiAwarenessContext(-4)
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user.SendMessageW.restype = ctypes.c_ssize_t
            user.GetMenuItemRect.argtypes = [wintypes.HWND, wintypes.HMENU, wintypes.UINT, ctypes.POINTER(wintypes.RECT)]
            user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            for _ in range(100):
                handles = []
                def inspect(hwnd, _):
                    pid = wintypes.DWORD()
                    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    label = ctypes.create_unicode_buffer(128)
                    user.GetClassNameW(hwnd, label, 128)
                    if pid.value == os.getpid() and label.value == '#32768' and user.IsWindowVisible(hwnd):
                        handles.append(hwnd)
                    return True
                user.EnumWindows(callback_type(inspect), 0)
                if handles:
                    hwnd = handles[0]
                    try:
                        time.sleep(.5)
                        user.RedrawWindow(hwnd,None,None,0x185)
                        capture_test_window(SimpleNamespace(winfo_id=lambda: hwnd), OUTPUT / (name+'.png'),flags=0)
                        bounds = wintypes.RECT()
                        user.GetWindowRect(hwnd, ctypes.byref(bounds))
                        native_menu = user.SendMessageW(hwnd, 0x1E1, 0, 0)
                        targets = {}
                        for n, label in labels.items():
                            box = wintypes.RECT()
                            if user.GetMenuItemRect(hwnd, native_menu, n, ctypes.byref(box)):
                                targets[label] = [box.left-bounds.left, box.top-bounds.top,
                                                  box.right-box.left, box.bottom-box.top]
                        manifest[name] = {'file': name+'.png', 'targets': targets, 'masks': []}
                        print('Captured', name, flush=True)
                    except BaseException as error:
                        result.append(error)
                    finally:
                        user.PostMessageW(hwnd, 0x100, 0x1B, 0)
                    return
                time.sleep(.03)
            result.append(RuntimeError('Native menu did not appear'))
        thread = threading.Thread(target=native_capture, daemon=True)
        thread.start()
        menu.post(button.winfo_rootx(), button.winfo_rooty()+button.winfo_height())
        thread.join(5)
        menu.unpost()
        if result:
            raise result[0]

    try:
        settle()
        if '--only-menus' in sys.argv:
            manifest.update(json.loads((OUTPUT/'manifest.json').read_text(encoding='utf-8')))
            app.tabs.select(app.library_tab)
            app.projects.selection_set(str(project))
            app.project_selected()
            settle()
            app.papers.selection_set(app.papers.get_children()[0])
            app.paper_selected()
            settle()
            for label,name in [('Library actions ▾','library-actions'),('Folder actions ▾','folder-actions'),('Actions ▾','paper-actions')]:
                menu_capture(name,find(root,label))
            app.view_notes()
            settle()
            menu_capture('reader-actions',find(root,'Actions ▾'))
            review=app.review_library()
            settle()
            review.more_button.action_menu=review.more_menu
            menu_capture('review-actions',review.more_button)
            review.window.destroy()
            (OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
            print('Refreshed native menu screenshots.',flush=True)
            return
        if settings_only:
            app.global_settings()
            settings=app.preferences_dialog
            for index,name in enumerate(('processing','diagnostics','sorting','connections')):
                settings.tabs.select(index)
                capture(name,settings.window)
                if name=='sorting':
                    settings.sorting_canvas.yview_moveto(1)
                    capture('sorting-permissions',settings.window)
            settings.window.destroy()
            (OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
            print('Refreshed settings screenshots.',flush=True)
            return
        app.tabs.select(app.library_tab)
        capture('library', extra={'folders': app.projects, 'papers': app.papers})
        app.projects.selection_set(str(project))
        app.project_selected()
        settle()
        app.papers.selection_set(app.papers.get_children()[0])
        app.paper_selected()
        capture('library-selected', extra={'folders': app.projects, 'papers': app.papers})
        for label, name in [('Library actions ▾', 'library-actions'), ('Folder actions ▾', 'folder-actions'), ('Actions ▾', 'paper-actions')]:
            menu_capture(name, find(root, label))
        app.activity_toggle.invoke()
        capture('sync-details')
        app.activity_toggle.invoke()
        window = dialog(app.settings)
        capture('folder-settings', window)
        window.destroy()
        app.view_notes()
        settle()
        capture('reader', extra={'results': app.notes, 'query': app.search_entry, 'folder': app.reader_folder,
                               'paper': app.reader_paper, 'labels': app.label_picker})
        menu_capture('reader-actions', find(root, 'Actions ▾'))
        # Keep a note selected for citation, labels and note context actions.
        note = next(i for i, e in enumerate(app.entries) if e['kind'] == 'highlight')
        app.note_view_button.invoke()
        app.notes.selection_set(str(note))
        app.preview()
        settle()
        capture('note-selected', extra={'results': app.notes})
        window = dialog(app.search_options)
        capture('search-filters', window)
        window.destroy()
        for name, action in [('citation', app.citation_details), ('supplements', app.supplementary_files),
                             ('labels', app.organize_paper), ('saved-searches', app.saved_searches),
                             ('history', app.history), ('document-details', app.reader_document_details),
                             ('help', app.help)]:
            window = dialog(action)
            capture(name, window)
            if name == 'labels':
                entries = [w for w in widgets(window) if isinstance(w, ttk.Entry)]
                entries[0].insert(0, 'catalysts; follow up')
                entries[1].insert(0, 'Thesis reading')
                capture('labels-filled', window)
                find(window, 'Save labels').invoke()
                settle()
            elif name == 'saved-searches':
                entries = [w for w in widgets(window) if isinstance(w, ttk.Entry)]
                entries[0].insert(0, 'Catalyst reading')
                capture('saved-searches-named', window)
                find(window, 'Save current search').invoke()
                settle()
                capture('saved-searches-saved', window)
                window.destroy()
            else:
                window.destroy()
        app.search.set('stable')
        app.refresh_notes()
        settle(.5)
        capture('search-results', extra={'results': app.notes, 'query': app.search_entry})
        app.search.set('')
        app.refresh_notes()
        settle()
        drawing = next(i for i, e in enumerate(app.entries) if e['kind'] == 'drawing')
        app.notes.selection_set(str(drawing))
        app.preview()
        settle()
        capture('drawing')
        window = dialog(app.enlarge)
        capture('enlarge', window)
        window.destroy()
        window = dialog(app.full_page_context)
        if app.context_future:
            app.context_future.result(timeout=30)
        settle(.4)
        capture('page-context', window)
        window.destroy()
        # Native PDF.js is exercised for the document screen; no screenshot mock.
        app.pdf_view_button.invoke()
        deadline = time.monotonic()+60
        while time.monotonic() < deadline and not app.pdf_reader.displayed:
            settle(.05)
        if not app.pdf_reader.displayed:
            raise RuntimeError('PDF reader did not display for manual capture: ' + str(app.pdf_reader.state))
        settle(1)
        def pdf_controls():
            info=json.loads((OUTPUT/'pdf-controls.json').read_text(encoding='utf-8'))
            host=app.pdf_reader.host
            x,y=host.winfo_rootx()-root.winfo_rootx(),host.winfo_rooty()-root.winfo_rooty()
            return {key:[x+value[0]*info['dpr'],y+value[1]*info['dpr'],value[2]*info['dpr'],value[3]*info['dpr']]
                    for key,value in info['controls'].items() if value and value[2] and value[3]}
        capture('pdf-reader', extra={'viewer': app.pdf_reader, 'results': app.notes, **pdf_controls()})
        (OUTPUT/'pdf-find-request').touch()
        settle(1)
        for _ in range(100):
            if json.loads((OUTPUT/'pdf-controls.json').read_text(encoding='utf-8')).get('find'):
                break
            settle(.1)
        settle(.5)
        capture('pdf-find',extra={'viewer':app.pdf_reader,**pdf_controls()})
        app.note_view_button.invoke()
        app.tabs.select(app.inbox_tab)
        app.inbox_view.refresh()
        settle()
        settle(2.2)
        app.inbox_view.refresh()
        settle()
        capture('inbox', extra={'incoming': app.inbox_view.tree})
        rows = app.inbox_view.tree.get_children()
        if rows:
            app.inbox_view.tree.selection_set(rows[0])
            app.inbox_view.selected()
            capture('inbox-selected', extra={'incoming': app.inbox_view.tree})
            app.inbox_view.review()
            settle()
            capture('inbox-reviewed', extra={'filename': app.inbox_view.name_entry,
                                           'destination': app.inbox_view.destination_entry})
            if not app.inbox_view.review_path:
                raise RuntimeError('Example Inbox document was not ready for review')
            with patch('note_organizer.workflow_ui.messagebox.askyesno', return_value=True), patch('note_organizer.workflow_ui.messagebox.askokcancel', return_value=True):
                app.inbox_view.file_document()
                settle()
            if not app.inbox_view.feedback.get().startswith('Filed:'):
                raise RuntimeError('Example filing failed: '+app.inbox_view.feedback.get())
            capture('inbox-filed', extra={'incoming': app.inbox_view.tree})
        app.global_settings()
        settings = app.preferences_dialog
        for index, name in enumerate(('processing', 'diagnostics', 'sorting', 'connections')):
            settings.tabs.select(index)
            capture(name, settings.window)
            if name == 'sorting':
                settings.sorting_canvas.yview_moveto(1)
                capture('sorting-permissions',settings.window)
        settings.window.destroy()
        app.tabs.select(app.library_tab)
        review = app.review_library()
        settle()
        capture('review', review.window, {'findings': review.tree, 'copies': review.local_copies})
        from note_organizer.reconciliation import scan_reconciliation
        gate = threading.Event()
        def delayed_check(*args, **kwargs):
            gate.wait(5)
            return scan_reconciliation(*args, **kwargs)
        with patch('note_organizer.reconciliation.scan_reconciliation', side_effect=delayed_check):
            review.check()
            capture('review-checking', review.window, {'findings': review.tree, 'copies': review.local_copies}, settle_before=False)
            gate.set()
            settle()
        capture('review-results', review.window, {'findings': review.tree, 'copies': review.local_copies})
        rows = sorted(review.tree.get_children(),key=lambda key:-len(review.rows[key].get('local_paths',[])))
        if rows:
            review.tree.selection_set(rows[0])
            review.selected()
            capture('review-selected', review.window, {'findings': review.tree, 'copies': review.local_copies})
            copies = review.local_copies.get_children()
            if len(copies) > 1:
                review.local_copies.selection_set(copies[:2])
                review.copy_selected()
                capture('review-multiple', review.window, {'copies': review.local_copies})
        review.more_button.action_menu = review.more_menu
        menu_capture('review-actions', review.more_button)
        review.window.destroy()
        for name, action in [('maintenance', app.storage_maintenance),
                             ('archives', lambda: ArchiveReviewWindow(app)),
                             ('cleanup', app.review_extra_pdfs)]:
            window = dialog(action)
            capture(name, window)
            if name == 'maintenance':
                with patch('note_organizer.maintenance_ui.filedialog.asksaveasfilename', return_value=str(folder/'Example-backup.zip')):
                    find(window, 'Create verified backup…').invoke()
                    settle()
                status=next((w for w in widgets(window) if 'text' in w.keys() and str(w.cget('text')).startswith('Verified backup saved:')),None)
                if status is None:
                    raise RuntimeError('Example backup did not report verified completion')
                capture('backup-verified', window, {'backup-status':status})
            window.destroy()
        app.tabs.select(app.remarkable_tab)
        capture('cloud')
        app.cloud_folders.selection_set('experiments')
        app.cloud_selection_changed()
        app.cloud_review.selection_set('review')
        app.cloud_review_selected()
        capture('cloud-selected', extra={'mappings': app.cloud_folders, 'attention': app.cloud_review})
        app.toggle_cloud_setup()
        capture('cloud-setup', extra={'source': app.cloud_scope, 'destination': app.cloud_pc_entry})
        app.toggle_cloud_setup()
        window = dialog(app.pair_remarkable)
        capture('pairing', window)
        window.destroy()
        window = dialog(app.transfers)
        capture('transfers', window)
        window.destroy()
        if errors:
            raise RuntimeError('UI callbacks failed: ' + '; '.join(errors))
        (OUTPUT / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
        print('Saved', len(manifest), 'screens and target coordinates.', flush=True)
    finally:
        app.closing = True
        app.inbox.stop()
        app.service.stop()
        app.query_cancel.set()
        app.preview_cancel.set()
        app.pdf_reader.close()
        app.workflow_executor.shutdown(wait=True, cancel_futures=True)
        app.query_executor.shutdown(wait=True, cancel_futures=True)
        app.context_executor.shutdown(wait=True, cancel_futures=True)
        app.pdf_worker.shutdown(wait=True)
        app.pdf_reader.wait_closed()
        host_patch.stop()
        if reader_load_patch:
            reader_load_patch.stop()
        diagnostics_patch.stop()
        gc.collect()
        for callback in root.tk.call('after', 'info'):
            root.after_cancel(callback)
        root.destroy()
        user.SetThreadDpiAwarenessContext(previous_dpi)
        faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    freeze_support()
    main()
