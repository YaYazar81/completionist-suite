# Completionist Suite

Drei Windows-Programme rund um Spiele-Guides und Dokumente:

| App | Was sie tut | Anleitung |
| :--- | :--- | :--- |
| **CompletionistMD** | WYSIWYG-Markdown-Editor (Tiptap in QtWebEngine) mit Vault-Explorer, Gliederung, Suchen/Ersetzen, Google-Drive-Sync, Dateien zusammenführen | [CompletionistMD.md](CompletionistMD.md) |
| **CompletionistPDF** | Markdown zu professionellem PDF über Typst, mit Live-Vorschau und PDF-Viewer | [CompletionistPDF.md](CompletionistPDF.md) |
| **CompletionistQR** | Gestaltete QR-Codes mit Logo, Rahmen und Beschriftung, Scan-Prüfung, Stapel-Export | [CompletionistQR.md](CompletionistQR.md) |

Änderungen und Versionsnummern: [CHANGELOG.md](CHANGELOG.md).

## Installieren

Die Setups (`CompletionistPDF-Setup-<Version>.exe` usw.) brauchen keine Adminrechte.

## Aus dem Quellcode

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.venv\Scripts\python.exe main.py                  # CompletionistPDF
.venv\Scripts\python.exe main_md.py               # CompletionistMD
.venv\Scripts\python.exe -m completionistqr       # CompletionistQR
.venv\Scripts\python.exe -m pytest                # Tests
.\build_setup.ps1 -App all                        # alle Setups (Inno Setup 6)
```

Das Editor-Bundle von CompletionistMD baut `build_editor.ps1` mit einem portablen Node
unter `tools\node` (nicht im Repository, siehe CompletionistMD.md). Die Schriften von
CompletionistQR lädt `tools\fetch_fonts.py`.

## Lizenz

Der eigene Quellcode steht unter **CC BY-NC-ND 4.0** – siehe [LICENSE](LICENSE).
Mitgelieferte und benutzte Fremdkomponenten behalten ihre eigenen Lizenzen:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
