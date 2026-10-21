"""Dateien aus dem Explorer auf ein Tk-Fenster ziehen (Windows, WM_DROPFILES).

Tkinter kennt kein Drag & Drop von aussen. Hier wird die Fensterprozedur des
Toplevel-Fensters per ctypes umgehaengt: WM_DROPFILES liefert die Pfade, alles
andere geht unveraendert an die alte Prozedur.
"""
from __future__ import annotations

import sys
from typing import Callable

WM_DROPFILES = 0x0233
GWLP_WNDPROC = -4

_keep: list = []  # Rueckruf-Objekte muessen leben, solange das Fenster lebt


def enable(widget, on_drop: Callable[[list[str]], None]) -> bool:
    """Meldet ``on_drop(pfade)`` fuer auf ``widget`` (dessen Fenster) gezogene Dateien."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                       wintypes.WPARAM, wintypes.LPARAM]
    user32.CallWindowProcW.restype = LRESULT
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.GetParent.restype = wintypes.HWND
    shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_wchar_p, wintypes.UINT]
    shell32.DragQueryFileW.restype = wintypes.UINT
    shell32.DragFinish.argtypes = [ctypes.c_void_p]
    shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]

    widget.update_idletasks()
    hwnd = user32.GetParent(widget.winfo_id()) or widget.winfo_id()
    old = None

    def proc(h, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            count = shell32.DragQueryFileW(wparam, 0xFFFFFFFF, None, 0)
            paths = []
            for i in range(count):
                n = shell32.DragQueryFileW(wparam, i, None, 0) + 1
                buf = ctypes.create_unicode_buffer(n)
                shell32.DragQueryFileW(wparam, i, buf, n)
                paths.append(buf.value)
            shell32.DragFinish(wparam)
            widget.after(0, lambda: on_drop(paths))
            return 0
        return user32.CallWindowProcW(old, h, msg, wparam, lparam)

    callback = WNDPROC(proc)
    old = user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(callback, ctypes.c_void_p))
    if not old:
        return False
    shell32.DragAcceptFiles(hwnd, True)
    _keep.append(callback)
    return True
