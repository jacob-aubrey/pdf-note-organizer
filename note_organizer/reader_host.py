"""Isolated WebView2 host. Its GUI loop never runs in Tk's interpreter."""
import json
import os
from pathlib import Path
import threading
import time
from collections import deque


def await_reader_ready(connection, shown, ready, stopped, shown_timeout=20, ready_timeout=25):
    """Keep close/EOF responsive while the browser and local assets initialize."""
    pending = deque()
    deadline = time.monotonic() + shown_timeout
    browser_shown = False
    while not stopped.is_set():
        if shown.is_set() and not browser_shown:
            browser_shown = True
            deadline = time.monotonic() + ready_timeout
        if browser_shown and ready.is_set():
            return pending
        if time.monotonic() >= deadline:
            raise RuntimeError("The PDF reader could not initialize. Check that Microsoft Edge WebView2 Runtime is installed.")
        if connection.poll(.05):
            command = connection.recv()
            if command.get("command") == "close":
                return None
            pending.append(command)
    return None


def run_reader_host(connection, dpi_awareness=0):
    """Private pipe commands load only locally registered PDFs into PDF.js."""
    if os.name == "nt":
        import ctypes
        # Set this once before WinForms starts. pywebview's later legacy call
        # then cannot change it. Matching Tk prevents SetParent from resetting
        # DPI after the WebView2 control has already calculated its bounds.
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.SetProcessDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
        user.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
        user.SetProcessDpiAwarenessContext({0: -1, 1: -2, 2: -4}.get(dpi_awareness, -1))
    from .reader_server import ReaderServer
    server = None
    send_lock = threading.Lock()
    ready = threading.Event()
    stopped = threading.Event()
    shutdown_scheduled = threading.Event()
    shutdown_lock = threading.Lock()

    def send(payload):
        try:
            with send_lock:
                connection.send(payload)
        except (OSError, EOFError):
            stopped.set()

    class Bridge:
        def event(self, payload):
            if not isinstance(payload, dict):
                return
            kind = payload.get("kind")
            if kind not in {"ready", "state", "error", "warning", "expand", "external", "link"}:
                return
            if kind == "ready":
                ready.set()
            send(payload)

    try:
        import webview
        server = ReaderServer()
        webview.settings["ALLOW_DOWNLOADS"] = False
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
        window = webview.create_window("Notable PDF reader", server.url, js_api=Bridge(),
            width=700, height=600, hidden=True, frameless=True, focus=False,
            background_color="#202224", text_select=True,
            easy_drag=False, draggable=False, shadow=False)

        def shutdown_native():
            if os.name != "nt" or window.native is None:
                return
            with shutdown_lock:
                if shutdown_scheduled.is_set():
                    return
                shutdown_scheduled.set()
            from System import Action
            from System.Windows.Forms import Application
            def shutdown():
                # A reparented Form is not a top-level application window.
                # End its own loop rather than waiting on FormClosed bookkeeping.
                try:
                    window.native.Hide()
                    window.native.browser.clear_user_data()
                    window.native.Dispose()
                finally:
                    Application.ExitThread()
            window.native.BeginInvoke(Action(shutdown))

        def navigation_guard(sender, args):
            # PDF links go through the explicit click bridge. A PDF must never
            # replace our trusted page with a remote page exposing the bridge.
            uri = str(args.Uri)
            if not uri.startswith(server.origin + "/"):
                args.Cancel = True

        def before_show():
            if os.name == "nt":
                window.native.browser.webview.NavigationStarting += navigation_guard
                # Close can arrive before WinForms has created its handle.
                # BeginInvoke runs once the just-created GUI loop starts.
                if stopped.is_set():
                    shutdown_native()

        window.events.before_show += before_show

        def commands():
            current_source = None
            document_url = None
            try:
                pending = await_reader_ready(connection, window.events.shown, ready, stopped)
                if pending is None:
                    return
                if os.name == "nt":
                    # focus=False keeps the hidden startup Form from taking
                    # activation. Once it becomes a child, normal input must
                    # work: otherwise pywebview's Activated handler reapplies
                    # WS_EX_NOACTIVATE after NativeChild removes it.
                    window.focus = True
                    send({"kind": "native", "hwnd": int(window.native.Handle.ToInt64())})
                else:
                    # Windows supports an embedded native surface. Other
                    # backends retain a normal viewer window when available.
                    send({"kind": "native", "hwnd": None})
                while not stopped.is_set():
                    if pending:
                        command = pending.popleft()
                    elif connection.poll(.1):
                        command = connection.recv()
                    else:
                        continue
                    action = command.get("command")
                    if action == "close":
                        break
                    if action == "open":
                        payload = dict(command["payload"])
                        path = Path(payload.pop("path")).resolve()
                        stat = path.stat()
                        identity = (str(path), stat.st_dev, stat.st_ino, stat.st_size,
                                    stat.st_mtime_ns, stat.st_ctime_ns)
                        if identity != current_source:
                            document_url = server.register_document(path)
                            current_source = identity
                        payload["url"] = document_url
                        window.evaluate_js("void window.NotableReader.open(" + json.dumps(payload) + ")")
                    elif action == "prepare":
                        window.evaluate_js("window.NotableReader.prepare(" + json.dumps(command.get("id")) + ")")
                    elif action == "clear":
                        server.clear_document()
                        current_source = None
                        window.evaluate_js("window.NotableReader.clear(" + json.dumps(command.get("message", "Choose a paper or note."))
                                           + "," + json.dumps(command.get("id")) + ")")
                    elif action == "match":
                        window.evaluate_js("window.NotableReader.selectMatch(" + json.dumps(command["index"])
                                           + ("," + json.dumps(command["id"]) if "id" in command else "") + ")")
                    elif action == "expanded":
                        window.evaluate_js("window.NotableReader.setExpanded(" + json.dumps(bool(command.get("value"))) + ")")
                    elif action == "title":
                        window.evaluate_js("window.NotableReader.setTitle(" + json.dumps(command.get("title", ""))
                                           + "," + json.dumps(command.get("id")) + ")")
                    elif action == "inspect":
                        # Used by local integration checks, never exposed to PDF content.
                        send({"kind": "inspection", "state": window.evaluate_js("window.NotableReader.state()")})
            except (EOFError, BrokenPipeError):
                pass
            except Exception as exc:
                send({"kind": "error", "id": locals().get("command", {}).get("payload", {}).get("id"),
                      "message": str(exc)})
            finally:
                stopped.set()
                if os.name == "nt":
                    shutdown_native()
                else:
                    window.destroy()

        webview.start(commands, gui="edgechromium" if os.name == "nt" else None,
                      private_mode=True, debug=False)
    except Exception as exc:
        send({"kind": "error", "message": str(exc)})
    finally:
        stopped.set()
        if server:
            server.close()
        connection.close()


class NativeChild:
    """Pointer-sized Win32 handles with clipping inside one Tk host frame."""
    def __init__(self, hwnd, parent):
        import ctypes
        from ctypes import wintypes
        self.hwnd = hwnd
        self.parent = parent
        self.visible = None
        self.focus_binding = None
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.user.SetParent.argtypes = (wintypes.HWND, wintypes.HWND)
        self.user.SetParent.restype = wintypes.HWND
        self.user.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
        self.user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.user.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
        self.user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.user.MoveWindow.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_int, wintypes.BOOL)
        self.user.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
        self.user.IsWindow.argtypes = (wintypes.HWND,)
        self.user.IsWindow.restype = wintypes.BOOL
        self.user.GetFocus.restype = wintypes.HWND
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.user.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
        self.user.GetAncestor.restype = wintypes.HWND
        self.user.IsChild.argtypes = (wintypes.HWND, wintypes.HWND)
        self.user.IsChild.restype = wintypes.BOOL
        self.user.SetFocus.argtypes = (wintypes.HWND,)
        self.user.SetFocus.restype = wintypes.HWND
        style = self.user.GetWindowLongPtrW(hwnd, -16)
        self.user.SetWindowLongPtrW(hwnd, -16,
            (style & ~0x80000000 & ~0x00C00000 & ~0x00040000 & ~0x00080000) | 0x40000000 | 0x04000000)
        extended = self.user.GetWindowLongPtrW(hwnd, -20)
        self.user.SetWindowLongPtrW(hwnd, -20,
            (extended & ~0x00040000 & ~0x08000000) | 0x00000080)
        ctypes.set_last_error(0)
        previous = self.user.SetParent(hwnd, parent.winfo_id())
        if not previous and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())
        self.resize()
        self.toplevel = parent.winfo_toplevel()
        from weakref import WeakSet
        if not hasattr(self.toplevel, "_native_reader_children"):
            self.toplevel._native_reader_children = WeakSet()
        self.toplevel._native_reader_children.add(self)
        self.focus_binding = self.toplevel.bind("<ButtonPress-1>", self.restore_tk_focus, add="+")

    def owner_is_foreground(self):
        """Allow hover help in Tk while the embedded browser owns keyboard focus."""
        if not self.user.IsWindow(self.hwnd):
            return False
        root_handle = self.user.GetAncestor(self.parent.winfo_id(), 2)
        return bool(root_handle and self.user.GetForegroundWindow() == root_handle)

    def restore_tk_focus(self, event):
        """Finish a user's click when Tk and the native child disagree on focus.

        Tk can still remember an Entry as focused after WebView2 receives the
        native keyboard focus. Its normal Entry binding then skips SetFocus.
        This runs after widget/class bindings, preserves Tk's chosen widget,
        and only repairs focus left inside this reader while this app already
        owns foreground activation. It never activates a background app.
        """
        if not self.user.IsWindow(self.hwnd):
            return
        root_handle = self.user.GetAncestor(self.parent.winfo_id(), 2)  # GA_ROOT
        if self.user.GetForegroundWindow() != root_handle:
            return
        focused = self.user.GetFocus()
        if not focused or not (focused == self.hwnd or self.user.IsChild(self.hwnd, focused)):
            return
        import tkinter as tk
        try:
            target = event.widget.focus_get()
            if target is None:
                # Tk reports no focus while a foreign GUI owns it. Choose
                # only the input the user clicked (or its hint overlay),
                # rather than forcing focus onto unrelated toolbar controls.
                target = event.widget
                if target.winfo_class() == "Label" and getattr(target, "master", None) is not None:
                    target = target.master
                if target.winfo_class() not in {"Entry", "TEntry", "Text", "TCombobox",
                                               "Spinbox", "TSpinbox", "Listbox", "Treeview"}:
                    return
            if (target is None or not target.winfo_ismapped()
                    or target.winfo_toplevel() != self.toplevel):
                return
            # No focus_force/SetForegroundWindow: the ordinary Tk click has
            # already chosen the target and this app is already foreground.
            self.user.SetFocus(target.winfo_id())
        except (tk.TclError, KeyError):
            # A click can destroy a popup/widget before this toplevel binding.
            pass

    def resize(self):
        if self.user.IsWindow(self.hwnd):
            self.user.MoveWindow(self.hwnd, 0, 0, max(1, self.parent.winfo_width()),
                                 max(1, self.parent.winfo_height()), True)

    def show(self, visible):
        visible = bool(visible)
        if visible != self.visible and self.user.IsWindow(self.hwnd):
            self.user.ShowWindow(self.hwnd, 4 if visible else 0)  # no activation
            self.visible = visible

    def detach(self):
        """Keep Tk destruction from destroying the other GUI's native Form."""
        children = getattr(self.toplevel, "_native_reader_children", None)
        if children is not None:
            children.discard(self)
        if self.focus_binding:
            import tkinter as tk
            try:
                self.toplevel.unbind("<ButtonPress-1>", self.focus_binding)
            except tk.TclError:
                pass
            self.focus_binding = None
        if self.user.IsWindow(self.hwnd):
            self.show(False)
            self.user.SetParent(self.hwnd, None)
            style = self.user.GetWindowLongPtrW(self.hwnd, -16)
            self.user.SetWindowLongPtrW(self.hwnd, -16, (style & ~0x40000000) | 0x80000000)


def parent_dpi_awareness(widget):
    if os.name != "nt":
        return 0
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetWindowDpiAwarenessContext.argtypes = (wintypes.HWND,)
    user.GetWindowDpiAwarenessContext.restype = ctypes.c_void_p
    user.GetAwarenessFromDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
    user.GetAwarenessFromDpiAwarenessContext.restype = ctypes.c_int
    return user.GetAwarenessFromDpiAwarenessContext(user.GetWindowDpiAwarenessContext(widget.winfo_id()))
