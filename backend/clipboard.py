"""Read and write text on the Windows clipboard.

WebView2 shows a permission prompt for navigator.clipboard.readText(), so the Paste
button (and the "Copy link" menu) asks Python instead.
"""
import logging

log = logging.getLogger(__name__)


def read_text() -> str:
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]

        cf_unicodetext = 13
        if not user32.OpenClipboard(None):
            return ""
        try:
            handle = user32.GetClipboardData(cf_unicodetext)
            if not handle:
                return ""
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return ""
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception as exc:
        log.debug("Clipboard not readable: %s", exc)
        return ""


def write_text(text: str) -> bool:
    """Put `text` on the clipboard; False when the clipboard is busy."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]

        cf_unicodetext, gmem_moveable = 13, 0x0002
        data = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(data)
        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            handle = kernel32.GlobalAlloc(gmem_moveable, size)
            if not handle:
                return False
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                kernel32.GlobalFree(handle)
                return False
            ctypes.memmove(ptr, data, size)
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(cf_unicodetext, handle):
                kernel32.GlobalFree(handle)   # the clipboard did not take it over
                return False
            return True
        finally:
            user32.CloseClipboard()
    except Exception as exc:
        log.debug("Clipboard not writable: %s", exc)
        return False
