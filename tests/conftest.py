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
    if "PyQt6.QtWebEngineWidgets" in sys.modules:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(_status["code"])
