"""Per-user Windows shortcuts sharing the packaged application's taskbar ID.

Only shortcuts targeting this exact executable are repaired. No shortcut is
pinned, and source/test launches never register themselves in the Start menu.
"""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import logging
import os
from pathlib import Path
import re
import sys
import subprocess
import uuid

from . import APP_DISPLAY_NAME

APP_ID = "Notable.Desktop"


def _guid(value):
    return (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le)


def _call(pointer, index, types=(), *args):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(table[index])(pointer, *args)


def _check(result):
    if result < 0:
        raise OSError(f"Windows shortcut operation failed (0x{result & 0xffffffff:08X})")
    return result


class _PropertyKey(ctypes.Structure):
    _fields_ = [("format", ctypes.c_ubyte * 16), ("id", wintypes.DWORD)]


class _PropVariant(ctypes.Structure):
    # PROPVARIANT's union includes a counted array (two pointers on x64).
    _fields_ = [("type", ctypes.c_ushort), ("reserved", ctypes.c_ushort * 3),
                ("value", ctypes.c_void_p), ("extra", ctypes.c_void_p)]


@contextmanager
def _link(path=None, write=False):
    ole = ctypes.WinDLL("ole32")
    ole.CoInitializeEx.argtypes = (ctypes.c_void_p, wintypes.DWORD)
    initialized = ole.CoInitializeEx(None, 2)
    if initialized != -2147417850:  # RPC_E_CHANGED_MODE: use the existing apartment.
        _check(initialized)
    link, persist, props = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    try:
        ole.CoCreateInstance.argtypes = (ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        _check(ole.CoCreateInstance(_guid("00021401-0000-0000-C000-000000000046"), None, 1,
                                    _guid("000214F9-0000-0000-C000-000000000046"), ctypes.byref(link)))
        for pointer, iid in ((persist, "0000010b-0000-0000-C000-000000000046"),
                             (props, "886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")):
            _check(_call(link, 0, (ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
                         _guid(iid), ctypes.byref(pointer)))
        if path is not None:
            _check(_call(persist, 5, (wintypes.LPCWSTR, wintypes.DWORD), str(path), 2 if write else 0))
        yield link, persist, props
    finally:
        for pointer in (props, persist, link):
            if pointer:
                _call(pointer, 2)
        if initialized in (0, 1):
            ole.CoUninitialize()


def _property(props, identifier, value=None):
    key = _PropertyKey(_guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), identifier)
    variant = _PropVariant()
    if value is None:
        try:
            _check(_call(props, 5, (ctypes.c_void_p, ctypes.c_void_p), ctypes.byref(key), ctypes.byref(variant)))
            return ctypes.wstring_at(variant.value) if variant.type == 31 else ""
        finally:
            ctypes.WinDLL("ole32").PropVariantClear(ctypes.byref(variant))
    buffer = ctypes.create_unicode_buffer(value)
    variant.type, variant.value = 31, ctypes.cast(buffer, ctypes.c_void_p).value
    _check(_call(props, 6, (ctypes.c_void_p, ctypes.c_void_p), ctypes.byref(key), ctypes.byref(variant)))


def _identity(props, value=None):
    return _property(props, 5, value)


@contextmanager
def _window_properties(root):
    user = ctypes.WinDLL("user32")
    user.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user.GetAncestor.restype = wintypes.HWND
    handle = user.GetAncestor(root.winfo_id(), 2)
    shell = ctypes.WinDLL("shell32")
    shell.SHGetPropertyStoreForWindow.argtypes = (wintypes.HWND, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
    props = ctypes.c_void_p()
    _check(shell.SHGetPropertyStoreForWindow(handle, _guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), ctypes.byref(props)))
    try:
        yield props
    finally:
        _call(props, 2)


def relaunch_command():
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([sys.executable])
    interpreter = Path(sys.executable)
    windowed = interpreter.with_name("pythonw.exe")
    if windowed.exists():
        interpreter = windowed
    return subprocess.list2cmdline([str(interpreter), str(Path(__file__).resolve().parent.parent / "PDF Note Organizer.py")])


def configure_taskbar(root):
    """Give the main window a versioned label, including Python launches."""
    if os.name != "nt":
        return
    try:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        with _window_properties(root) as props:
            # Relaunch properties require an explicit window identity as well
            # as the process identity; the ID itself stays stable across versions.
            _property(props, 2, relaunch_command())
            _property(props, 3, str(base / "Note icon.ico") + ",0")
            _property(props, 4, APP_DISPLAY_NAME)
            _identity(props, APP_ID)
    except OSError:
        logging.debug("Windows taskbar label unavailable", exc_info=True)


def _text(link, index):
    buffer = ctypes.create_unicode_buffer(32768)
    if index == 3:
        _check(_call(link, index, (wintypes.LPWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD),
                     buffer, len(buffer), None, 4))  # SLGP_RAWPATH: never resolve a missing old executable.
    else:
        _check(_call(link, index, (wintypes.LPWSTR, ctypes.c_int), buffer, len(buffer)))
    return buffer.value


def read_shortcut(path):
    with _link(path) as (link, _, props):
        icon, index = ctypes.create_unicode_buffer(32768), ctypes.c_int()
        _check(_call(link, 16, (wintypes.LPWSTR, ctypes.c_int, ctypes.POINTER(ctypes.c_int)),
                     icon, len(icon), ctypes.byref(index)))
        return dict(target=_text(link, 3), arguments=_text(link, 10), working_directory=_text(link, 8),
                    description=_text(link, 6), icon=icon.value, icon_index=index.value, app_id=_identity(props))


def _save(persist, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".notable-{uuid.uuid4().hex}.lnk")
    try:
        _check(_call(persist, 6, (wintypes.LPCWSTR, wintypes.BOOL), str(staged), True))
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)
    shell = ctypes.WinDLL("shell32")
    shell.SHChangeNotify.argtypes = (wintypes.LONG, wintypes.UINT, wintypes.LPCWSTR, ctypes.c_void_p)
    shell.SHChangeNotify(0x2000, 0x1005, str(path), None)  # UPDATEITEM, PATHW | FLUSHNOWAIT


def create_shortcut(path, executable):
    executable = Path(executable).resolve()
    with _link() as (link, persist, props):
        for index, value in ((20, str(executable)), (9, str(executable.parent)),
                             (7, APP_DISPLAY_NAME)):
            _check(_call(link, index, (wintypes.LPCWSTR,), value))
        _check(_call(link, 17, (wintypes.LPCWSTR, ctypes.c_int), str(executable), 0))
        _identity(props, APP_ID)
        _save(persist, path)


def repair_shortcut(path, executable):
    before = read_shortcut(path)
    if os.path.normcase(os.path.abspath(before["target"])) != os.path.normcase(str(Path(executable).resolve())):
        return False
    description = before["description"]
    owned_description = (description.casefold() == "notable research document organizer" or
                         bool(re.fullmatch(r"Notable \d+\.\d+\.\d+", description)))
    update_description = owned_description and description != APP_DISPLAY_NAME
    if before["app_id"] == APP_ID and not update_description:
        return False
    with _link(path, write=True) as (link, persist, props):
        _identity(props, APP_ID)
        if update_description:
            _check(_call(link, 7, (wintypes.LPCWSTR,), APP_DISPLAY_NAME))
        _save(persist, path)
    return True


def _known_folder(identifier):
    shell = ctypes.WinDLL("shell32")
    shell.SHGetKnownFolderPath.argtypes = (ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE,
                                         ctypes.POINTER(ctypes.c_void_p))
    result = ctypes.c_void_p()
    _check(shell.SHGetKnownFolderPath(_guid(identifier), 0, None, ctypes.byref(result)))
    try:
        return Path(ctypes.wstring_at(result))
    finally:
        ole = ctypes.WinDLL("ole32")
        ole.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
        ole.CoTaskMemFree(result)


def shortcut_locations():
    programs = _known_folder("A77F5D77-2E2B-44C3-A6A2-ABA601054A51")
    desktop = _known_folder("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")
    roaming = _known_folder("3EB685DB-65F9-4CF6-A03A-E3EF65729F3D")
    pinned = roaming / "Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar"
    return programs, desktop, pinned


def ensure_shortcuts(executable, locations):
    """Register one Start entry; repair only links launching this exact copy."""
    programs, desktop, pinned = map(Path, locations)
    entry = programs / "Notable.lnk"
    if not entry.exists():
        create_shortcut(entry, executable)
    else:
        existing = read_shortcut(entry)
        if existing["app_id"] == APP_ID and existing["target"] != str(Path(executable).resolve()):
            # Only the standard entry owned by Notable follows a moved/new copy.
            create_shortcut(entry, executable)
    changed = []
    for folder, recursive in ((programs, True), (desktop, False), (pinned, False)):
        for path in folder.rglob("*.lnk") if recursive else folder.glob("*.lnk"):
            try:
                if repair_shortcut(path, executable):
                    changed.append(path)
            except OSError:
                logging.debug("Could not inspect or update shortcut %s", path, exc_info=True)
    return changed


def prepare_packaged_shortcuts():
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    # Isolated executable tests must never change the real user's shortcuts.
    try:
        if os.environ.get("NOTABLE_TEST_DESKTOP"):
            root = os.environ.get("NOTABLE_TEST_SHELL_ROOT")
            if not root:
                return
            locations = tuple(Path(root).resolve() / name for name in ("Programs", "Desktop", "TaskBar"))
        else:
            locations = shortcut_locations()
        ensure_shortcuts(sys.executable, locations)
    except OSError:
        # Restricted/managed Start menus must not prevent reading a library.
        logging.warning("Windows shortcut registration unavailable", exc_info=True)
