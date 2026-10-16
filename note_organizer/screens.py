"""Place popups within the work area of their owning monitor."""
import ctypes
from ctypes import wintypes
import os
import tkinter as tk


def _monitor_work_area(handle):
    if os.name != "nt":
        return None
    try:
        class MonitorInfo(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                        ("work", wintypes.RECT), ("flags", wintypes.DWORD)]
        user32 = ctypes.windll.user32
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        info = MonitorInfo(size=ctypes.sizeof(MonitorInfo))
        if handle and user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            rect = info.work
            return rect.left, rect.top, rect.right, rect.bottom
    except (AttributeError, OSError):
        pass
    return None


def round_window_corners(widget, radius=16):
    """Clip a borderless Tk window to the same rounded shape as native windows."""
    if os.name != "nt":
        return
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
        user32.SetWindowRgn.restype = ctypes.c_int
        gdi32.CreateRoundRectRgn.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int,
        ]
        gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
        width, height = widget.winfo_width(), widget.winfo_height()
        region = gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius * 2, radius * 2)
        if region:
            user32.SetWindowRgn(widget.winfo_id(), region, True)
    except (AttributeError, OSError, tk.TclError):
        pass


def launch_source_work_area():
    """Return the work area containing the window that launched the app."""
    if os.name == "nt":
        try:
            user32 = ctypes.windll.user32
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
            user32.MonitorFromWindow.restype = wintypes.HANDLE
            foreground = user32.GetForegroundWindow()
            monitor = user32.MonitorFromWindow(foreground, 2)
            bounds = _monitor_work_area(monitor)
            if bounds:
                return bounds
        except (AttributeError, OSError):
            pass
    return None


def work_area(widget, point=None):
    if point is None:
        point = (widget.winfo_rootx() + widget.winfo_width() // 2,
                 widget.winfo_rooty() + widget.winfo_height() // 2)
    if os.name == "nt":
        try:
            user32 = ctypes.windll.user32
            user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            user32.MonitorFromPoint.restype = wintypes.HANDLE
            monitor = user32.MonitorFromPoint(wintypes.POINT(*point), 2)
            bounds = _monitor_work_area(monitor)
            if bounds:
                return bounds
        except (AttributeError, OSError):
            pass
    left, top = widget.winfo_vrootx(), widget.winfo_vrooty()
    return left, top, left + widget.winfo_vrootwidth(), top + widget.winfo_vrootheight()


def popup_position(point, size, bounds, gap=(14, 20)):
    """Prefer below/right of the pointer, flipping at monitor edges."""
    px, py = point
    width, height = size
    left, top, right, bottom = bounds
    x, y = px + gap[0], py + gap[1]
    if x + width > right - 8:
        x = px - width - gap[0]
    if y + height > bottom - 8:
        y = py - height - gap[1]
    return (max(left + 8, min(x, right - width - 8)),
            max(top + 8, min(y, bottom - height - 8)))
