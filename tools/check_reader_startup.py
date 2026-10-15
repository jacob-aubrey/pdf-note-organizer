"""Native startup/close regressions; run through run_ui_tests.py only."""
import ctypes
from ctypes import wintypes
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def isolated_desktop():
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user.GetThreadDesktop.argtypes = (wintypes.DWORD,)
    user.GetThreadDesktop.restype = wintypes.HANDLE
    user.GetUserObjectInformationW.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                              wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    name, required = ctypes.create_unicode_buffer(256), wintypes.DWORD()
    user.GetUserObjectInformationW(user.GetThreadDesktop(kernel.GetCurrentThreadId()), 2,
                                  name, ctypes.sizeof(name), ctypes.byref(required))
    if not name.value.startswith("NotableTests-") or name.value != os.environ.get("NOTABLE_TEST_DESKTOP"):
        raise RuntimeError("Run through tools/run_ui_tests.py on its private inactive desktop")


def host(connection, assets):
    isolated_desktop()
    if assets:
        import note_organizer.reader_server as module
        original = module.ReaderServer
        class UnreadyReaderServer(original):
            def __init__(self):
                super().__init__(assets_root=assets)
            def _serve(self, handler, *, head):
                super()._serve(handler, head=head)
                if handler.path.endswith("reader/index.html"):
                    connection.send({"kind": "unready-assets-loaded"})
        module.ReaderServer = UnreadyReaderServer
    from note_organizer.reader_host import run_reader_host
    run_reader_host(connection)


def main():
    isolated_desktop()
    context = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(dir=ROOT / ".test-tmp", prefix="startup-") as folder:
        assets = Path(folder)
        (assets / "reader").mkdir()
        (assets / "reader" / "index.html").write_text("<!doctype html><title>Assets without a ready bridge</title>", encoding="utf-8")
        for scenario in ("immediate-close", "assets-never-ready", "pending-opens-close", "assets-eof", "ready-close"):
            parent, child = context.Pipe()
            process = context.Process(target=host, args=(child, None if scenario in {"immediate-close", "ready-close"} else folder))
            process.start()
            child.close()
            messages = []
            connection_closed = False
            try:
                if scenario != "immediate-close":
                    expected = "native" if scenario == "ready-close" else "unready-assets-loaded"
                    deadline = time.monotonic() + 35
                    while time.monotonic() < deadline:
                        if parent.poll(.05):
                            message = parent.recv()
                            messages.append(message)
                            if message.get("kind") == expected:
                                break
                        if not process.is_alive():
                            raise AssertionError((scenario, "exited before setup", process.exitcode, messages))
                    else:
                        raise AssertionError((scenario, "setup timeout", messages))
                started = time.monotonic()
                if scenario == "pending-opens-close":
                    for generation in (1, 2, 3):
                        parent.send({"command": "open", "payload": {"id": generation, "path": str(assets / "absent.pdf")}})
                if scenario == "assets-eof":
                    parent.close()
                    connection_closed = True
                else:
                    parent.send({"command": "close"})
                deadline = time.monotonic() + 7
                while process.is_alive() and time.monotonic() < deadline:
                    if not connection_closed:
                        try:
                            if parent.poll(.05):
                                messages.append(parent.recv())
                        except EOFError:
                            connection_closed = True
                            parent.close()
                    else:
                        time.sleep(.01)
                process.join(0)
                assert not process.is_alive(), (scenario, "did not close promptly", messages)
                assert process.exitcode == 0, (scenario, process.exitcode, messages)
                assert not [message for message in messages if message.get("kind") == "error"], (scenario, messages)
                print(f"PASS: {scenario}, clean exit 0 after {time.monotonic() - started:.2f}s", flush=True)
            finally:
                if process.is_alive():
                    process.terminate()
                    process.join(2)
                if not connection_closed:
                    parent.close()
                process.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
