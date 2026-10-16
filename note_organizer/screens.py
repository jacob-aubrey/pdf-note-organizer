"""Place popups within the work area of their owning monitor."""
import ctypes
from ctypes import wintypes
import os


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
