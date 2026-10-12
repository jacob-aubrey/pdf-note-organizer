"""Copy original image pixels to the Windows clipboard without a temp file."""
import ctypes
from ctypes import wintypes
from io import BytesIO
import sys

from PIL import Image


def image_dib(image):
    """CF_DIB is a BMP without its 14-byte file header; flatten alpha on white."""
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", image.size, "white")
    background.alpha_composite(rgba)
    stream = BytesIO()
    background.convert("RGB").save(stream, format="BMP")
    return stream.getvalue()[14:]


def copy_image(image, owner):
    if sys.platform != "win32":
        raise OSError("Image clipboard copying currently requires Windows.")
    data = image_dib(image)
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user.OpenClipboard.argtypes, user.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
    user.EmptyClipboard.argtypes, user.EmptyClipboard.restype = [], wintypes.BOOL
    user.CloseClipboard.argtypes, user.CloseClipboard.restype = [], wintypes.BOOL
    user.SetClipboardData.argtypes, user.SetClipboardData.restype = [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE
    kernel.GlobalAlloc.argtypes, kernel.GlobalAlloc.restype = [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL
    kernel.GlobalLock.argtypes, kernel.GlobalLock.restype = [wintypes.HGLOBAL], ctypes.c_void_p
    kernel.GlobalUnlock.argtypes, kernel.GlobalUnlock.restype = [wintypes.HGLOBAL], wintypes.BOOL
    kernel.GlobalFree.argtypes, kernel.GlobalFree.restype = [wintypes.HGLOBAL], wintypes.HGLOBAL
    handle = kernel.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE; Windows owns it after SetClipboardData.
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    opened = False
    try:
        pointer = kernel.GlobalLock(handle)
        if not pointer:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            ctypes.memmove(pointer, data, len(data))
        finally:
            kernel.GlobalUnlock(handle)
        if not user.OpenClipboard(owner):
            raise OSError("The clipboard is busy. Try copying the image again.")
        opened = True
        if not user.EmptyClipboard() or not user.SetClipboardData(8, handle):  # CF_DIB
            raise ctypes.WinError(ctypes.get_last_error())
        handle = None
    finally:
        if opened:
            user.CloseClipboard()
        if handle:
            kernel.GlobalFree(handle)
