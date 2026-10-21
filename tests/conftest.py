import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_status = {"code": 0}


def pytest_sessionfinish(session, exitstatus):
    _status["code"] = int(exitstatus)


def pytest_unconfigure(config):
    # QtWebEngine (Chromium) stuerzt beim Aufraeumen am Interpreter-Ende ab,
    # nachdem alle Tests gelaufen sind. Dann sofort mit dem echten Ergebnis
    # beenden, statt den Absturz als Fehlschlag zu melden.
    if "PySide6.QtWebEngineWidgets" in sys.modules:
        sys.stdout.flush()
        sys.stderr.flush()
        if sys.platform == "win32":
            # Auch os._exit laesst Chromium noch aufraeumen (DLL-Abmeldung) und
            # stuerzt dabei ab; TerminateProcess beendet ohne diesen Schritt.
            import ctypes

            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = ctypes.c_void_p  # Pseudo-Handle -1, 64 Bit
            k32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            k32.TerminateProcess(k32.GetCurrentProcess(), _status["code"])
        os._exit(_status["code"])
