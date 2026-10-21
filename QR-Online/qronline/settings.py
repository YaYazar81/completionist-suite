"""Einstellungen unter %APPDATA%\\QR-Online\\settings.json.

Der API-Schlüssel wird unter Windows per DPAPI verschlüsselt abgelegt: nur
dasselbe Windows-Konto kann ihn wieder lesen.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

_ENTROPY = b"QR-Online/api-key"


def user_dir() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / "QR-Online"


def _dpapi(data: bytes, protect: bool) -> bytes:
    if sys.platform != "win32":
        return data
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    def blob(raw: bytes):
        buf = ctypes.create_string_buffer(raw, len(raw))
        return Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    inp, _keep1 = blob(data)
    ent, _keep2 = blob(_ENTROPY)
    out = Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ui_forbidden = 0x1
    if not fn(ctypes.byref(inp), None, ctypes.byref(ent), None, None, ui_forbidden, ctypes.byref(out)):
        raise OSError(ctypes.GetLastError(), "DPAPI fehlgeschlagen")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def load() -> dict:
    try:
        data = json.loads((user_dir() / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    secret = data.pop("api_key_protected", None)
    if secret:
        try:
            data["api_key"] = _dpapi(base64.b64decode(secret), protect=False).decode("utf-8")
        except (OSError, ValueError):
            data["api_key"] = ""
    return data


def save(data: dict) -> None:
    data = dict(data)
    key = data.pop("api_key", "")
    if key:
        data["api_key_protected"] = base64.b64encode(
            _dpapi(key.encode("utf-8"), protect=True)).decode("ascii")
    try:
        path = user_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass
