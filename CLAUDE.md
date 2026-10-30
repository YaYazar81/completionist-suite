# Completionist Suite – Arbeitsregeln für Claude

Gearbeitet wird **nur lokal** unter Windows, ohne GitHub-Remote (seit 30.10.2026).
Versionierung und Setups übernimmt Claude – bei jeder Änderung an einer App vollständig nach
den Schritten unten, damit nichts vergessen wird. Antworten, Doku, Changelog und
Commit-Nachrichten auf Deutsch.

## Apps und Versionsnummern

Jede App hat ihre eigene Nummer *Haupt.Neben.Korrektur*, und sie steht an genau einer Stelle
(von dort lesen sie Setup, Fenstertitel und `.exe`):

| App | Nummer in | Tag-Präfix | Setup bauen |
| :--- | :--- | :--- | :--- |
| CompletionistPDF | `core/__init__.py` | `pdf-` | `.\build_setup.ps1 -App pdf` |
| CompletionistMD | `mdeditor/__init__.py` | `md-` | `.\build_setup.ps1 -App md` |
| CompletionistQR | `completionistqr/__init__.py` | `qr-` | `.\build_setup.ps1 -App qr` |
| CompletionistQR Online | `CompletionistQR-Online/qronline/__init__.py` | `qronline-` | `.\build_setup.ps1` im Ordner `CompletionistQR-Online` |

Gemeinsamer Code (`core/…`, etwa `core/printing.py`, `core/drive.py`, `core/office.py`) gehört zu
**jeder App, die ihn nutzt** – deren Nummern steigen mit.

## Wann welche Nummer steigt

- Neue Funktion: mittlere Zahl (1.9.1 → 1.10.0). Nur Fehlerkorrektur: letzte Zahl (1.9.1 → 1.9.2).
- **Einmal je Auslieferung, nicht je Commit.** Ob die jetzige Nummer schon ausgeliefert ist,
  zeigt der Tag: `git tag -l "md-*"`.
  - Gibt es den Tag zur aktuellen Nummer schon (z. B. `md-1.9.1`): Nummer erhöhen, neuer
    Changelog-Abschnitt.
  - Gibt es ihn noch nicht: Nummer bleibt, die Änderung kommt in den vorhandenen
    Changelog-Abschnitt dieser Nummer (eine Korrektur macht aus einer noch nicht
    ausgelieferten Neben-Version keine neue Korrektur-Version).

## Ablauf bei jeder Änderung an einer App

1. Code ändern, Tests dazu schreiben bzw. anpassen.
2. Nummer(n) nach den Regeln oben setzen.
3. `CHANGELOG.md`: neuer Abschnitt oben, Muster
   `## TT.MM.JJJJ – CompletionistMD 1.10.0 – Kurztitel`, darunter `### CompletionistMD 1.10.0`
   und Punkte, die erklären, was sich für den Nutzer ändert (bei Fehlern auch: was vorher
   passierte).
4. Doku der App nachziehen (`CompletionistPDF.md`, `CompletionistMD.md`, `CompletionistQR.md`,
   `README.md`), wenn sich Bedienung oder Aufbau ändern.
5. Editor-Bundle neu bauen, wenn sich etwas in `editor-src/src/` geändert hat:
   `.\build_editor.ps1`.
6. Tests (müssen grün sein, auch der Exit-Code – ein Absturz beim Beenden zählt als Fehler):
   ```
   $env:QT_QPA_PLATFORM = "offscreen"
   .venv\Scripts\python.exe -m pytest tests CompletionistQR-Online\tests -q -p no:cacheprovider
   ```
7. Commit (lokal, `main` oder ein Arbeitszweig), Nachricht mit App und Version vorn,
   z. B. `MD 1.10.0: …`.

## Auslieferung (Setups bauen)

Wenn der Nutzer ein Setup will oder eine Änderung fertig ist:

1. Schritte 1–7 oben sind erledigt, Arbeitsverzeichnis sauber (`git status`).
2. Setups der betroffenen Apps bauen (Tabelle oben; mehrere: `-App all`). Fertig liegen sie
   als `dist\<App>-Setup-<Version>.exe`.
3. Tag je ausgelieferter App setzen: `git tag md-1.10.0` usw.
4. Dem Nutzer sagen, welche Setups mit welcher Version wo liegen und was drin ist.

Voraussetzungen (einmalig, siehe `README.md`): `.venv` mit `requirements.lock.txt`
(für QR Online zusätzlich `CompletionistQR-Online\requirements.txt`), Inno Setup 6
(`winget install JRSoftware.InnoSetup`). Die `AppId` in den `installer\*.iss` darf sich nie
ändern.
