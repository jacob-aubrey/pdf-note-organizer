"""Wait for disposable async library snapshots while pumping the Tk loop."""
import time


def settle_library(app, root, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        app.poll()
        if app.library_loaded and app.library_future is None and app.cloud_path_future is None:
            root.update()
            return
        time.sleep(.005)
    raise AssertionError("Library snapshot did not settle")
