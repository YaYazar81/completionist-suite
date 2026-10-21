"""Bild in die Windows-Zwischenablage legen (ohne Zusatzpakete).

Gelegt werden zwei Formate: "PNG" (behaelt Transparenz; Word, PowerPoint,
Browser und Grafikprogramme nehmen es) und CF_DIB als Rueckfall fuer aeltere
Programme (dort auf weissem Grund).
"""
from __future__ import annotations

import io
import sys

from PIL import Image

CF_DIB = 8
GMEM_MOVEABLE = 0x0002


def copy_image(img: Image.Image, background: str = "#FFFFFF") -> None:
    if sys.platform != "win32":
        raise OSError("Kopieren in die Zwischenablage geht nur unter Windows.")
    import ctypes
    from ctypes import wintypes

    png = io.BytesIO()
    img.save(png, "PNG")
    flat = img
    if img.mode in ("RGBA", "LA", "P"):
        flat = Image.new("RGB", img.size, background)
        flat.paste(img, mask=img.convert("RGBA").getchannel("A"))
    bmp = io.BytesIO()
    flat.convert("RGB").save(bmp, "BMP")
    dib = bmp.getvalue()[14:]  # ohne BITMAPFILEHEADER

    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.RegisterClipboardFormatW.restype = wintypes.UINT

    def put(fmt: int, data: bytes) -> None:
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise OSError("Kein Speicher für die Zwischenablage.")
        ptr = kernel32.GlobalLock(handle)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(fmt, handle):
            raise OSError("Die Zwischenablage hat das Bild nicht angenommen.")

    for _ in range(10):  # ein anderes Programm kann sie kurz offen halten
        if user32.OpenClipboard(None):
            break
        kernel32.Sleep(50)
    else:
        raise OSError("Die Zwischenablage ist gerade von einem anderen Programm belegt.")
    try:
        user32.EmptyClipboard()
        put(user32.RegisterClipboardFormatW("PNG"), png.getvalue())
        put(CF_DIB, dib)
    finally:
        user32.CloseClipboard()
