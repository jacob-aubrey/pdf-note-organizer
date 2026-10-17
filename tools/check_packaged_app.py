"""Smoke-test the real portable executable on the inactive UI-test desktop.

Run through tools/run_ui_tests.py. Uses generated PDFs and an explicit fresh
data directory; legacy import and cloud services remain disabled.
"""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from note_organizer import __version__
from note_organizer.extraction import extract
from note_organizer.storage import Store, DEFAULT_SETTINGS
from tests.test_notebook import sample_pdf
from tests.reader_app_regression import capture_test_window, require_private_desktop
from note_organizer.windows_identity import APP_ID, create_shortcut, read_shortcut, _link, _identity, _save


def main():
    require_private_desktop()
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.SetThreadDpiAwarenessContext.argtypes=[ctypes.c_void_p]
    user.SetThreadDpiAwarenessContext.restype=ctypes.c_void_p
    user.SetThreadDpiAwarenessContext(-4)
    user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.IsWindowVisible.argtypes=[wintypes.HWND]
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    folder=ROOT/'.test-tmp'/('packaged-smoke-'+str(time.time_ns()))
    data,papers=folder/'data',folder/'Papers'
    papers.mkdir(parents=True)
    sample_pdf(papers/'Example research paper.pdf')
    store=Store(data/'library.sqlite3')
    project=store.add_project(papers)
    path=papers/'Example research paper.pdf'
    digest,signature,metadata,entries=extract(path,DEFAULT_SETTINGS)
    store.save_scan(project,path,digest,signature,'packaged smoke',metadata,entries)
    exe=ROOT/'dist'/'releases'/('v'+__version__)/f'Notable-{__version__}-windows-x64.exe'
    shell_root=folder/'shell-profile'
    pin=shell_root/'TaskBar'/'Downloaded Notable.lnk'
    create_shortcut(pin,exe)
    with _link(pin,write=True) as (_,persist,props):
        _identity(props,'')
        _save(persist,pin)
    pin_before=read_shortcut(pin)
    env={**os.environ,'PDF_NOTES_DATA_DIR':str(data),'PDF_NOTES_SKIP_LEGACY_IMPORT':'1',
         'NOTABLE_TEST_SHELL_ROOT':str(shell_root)}
    process=subprocess.Popen([str(exe)],env=env,cwd=folder,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    windows=[]
    def describe(hwnd,_):
        title,kind=ctypes.create_unicode_buffer(512),ctypes.create_unicode_buffer(128)
        user.GetWindowTextW(hwnd,title,512)
        user.GetClassNameW(hwnd,kind,128)
        windows.append((hwnd,title.value,kind.value,bool(user.IsWindowVisible(hwnd))))
        return True
    def list_windows():
        windows.clear()
        user.EnumWindows(callback_type(describe),0)
        return list(windows)
    hwnd=None
    start=time.monotonic()
    try:
        while time.monotonic()-start<120:
            for handle,title,kind,visible in list_windows():
                if title.startswith('Notable '+__version__) and kind=='TkTopLevel' and visible:
                    hwnd=handle
            if hwnd:
                break
            if process.poll() is not None:
                raise AssertionError('Executable exited before the workspace appeared: '+str(process.communicate()[0]))
            time.sleep(.1)
        if not hwnd:
            raise AssertionError('Packaged startup timed out; windows: '+repr(list_windows()))
        workspace_seconds=round(time.monotonic()-start,2)
        print('Packaged workspace appeared after',workspace_seconds,'seconds',flush=True)
        start_entry=read_shortcut(shell_root/'Programs'/'Notable.lnk')
        assert start_entry['app_id']==APP_ID and start_entry['target']==str(exe)
        assert read_shortcut(pin)=={**pin_before,'app_id':APP_ID}
        print('Packaged first launch registered Start entry and repaired existing pin in isolated profile',flush=True)
        native=None
        deadline=time.monotonic()+70
        while time.monotonic()<deadline:
            windows.clear()
            user.EnumChildWindows(hwnd,callback_type(describe),0)
            native=next((handle for handle,title,kind,visible in windows if title=='Notable PDF reader' and visible),None)
            if native:
                time.sleep(2)
                break
            time.sleep(.1)
        capture_test_window(SimpleNamespace(winfo_id=lambda:hwnd),folder/'packaged-workspace.png')
        if not native:
            raise AssertionError('Bundled embedded reader was not visible; inspect '+str(folder))
        user.PostMessageW(hwnd,0x10,0,0)
        output=process.communicate(timeout=90)[0].decode('utf-8',errors='replace')
        (folder/'process-output.txt').write_text(output,encoding='utf-8')
        if process.returncode:
            raise AssertionError('Portable executable did not close cleanly: '+str(process.returncode))
        log=(data/'app.log').read_text(encoding='utf-8')
        if 'Traceback (most recent call last)' in log or 'ERROR' in log:
            raise AssertionError('Packaged log has an error; inspect '+str(data/'app.log'))
        result={'executable':str(exe),'startup_seconds':workspace_seconds,'total_seconds':round(time.monotonic()-start,2),
                'embedded_reader_visible':bool(native),'shortcut_registration_verified':True,
                'exit_code':process.returncode,'fixture':str(folder)}
        (folder/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True)
    finally:
        if process.poll() is None:
            if hwnd:
                user.PostMessageW(hwnd,0x10,0,0)
            try:
                process.wait(15)
            except subprocess.TimeoutExpired:
                # This PID is the executable launched above with isolated data.
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)


if __name__=='__main__':
    main()
