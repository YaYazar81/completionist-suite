# CompletionistPDF

Markdown zu professionellem PDF über [Typst](https://typst.app). Links die Einstellungen
(Deckblatt, Seitenformat, Schriften, Inhaltsverzeichnis, Kopf- und Fußzeile, Wasserzeichen,
Tabellen/Bilder/Code), rechts die Live-Vorschau. Fertige PDFs zeigt der Viewer-Modus an. Gehört zur Completionist Suite neben dem
Editor CompletionistMD und dem QR-Generator CompletionistQR.

## Starten

- **Installiert:** `CompletionistPDF-Setup-<Version>.exe` ausführen. Das Setup braucht keine
  Adminrechte und legt das Programm unter `%LOCALAPPDATA%\Programs\CompletionistPDF` ab; im
  ersten Dialog lässt sich auch „für alle Benutzer" wählen. Deinstallieren über die
  Windows-Programmliste.
- **Aus dem Quellcode:** `.venv\Scripts\python.exe main.py [datei.md]`

Eine Markdown-Datei als Argument (auch über *Öffnen mit*) wird sofort geladen und kompiliert.
Eigene Presets und die letzte Sitzung liegen unter `%APPDATA%\CompletionistPDF\` und bleiben bei
der Deinstallation erhalten.

### Viewer-Modus

Eine **.pdf** als Argument, per *Öffnen …* (Strg+O) oder per Drag & Drop öffnet den
Viewer-Modus: nur das PDF, ohne Einstellungsleiste. Es gibt Zoom (Strg+Plus, Strg+Minus,
Breite mit Strg+0, ganze Seite mit Strg+9; Start mit ganzer Seite), Seiten (Bild auf, Bild ab,
Seitenzahl eingeben) und die Suche (Strg+F, F3, Umschalt+F3).

Hat das PDF Lesezeichen, zeigt links eine Seitenleiste das Inhaltsverzeichnis. Ein Klick auf
einen Eintrag springt an die Stelle. **☰ Inhalt** oder F4 blendet die Leiste ein und aus. Links
im PDF sind klickbar, der Mauszeiger wird darüber zur Hand. Interne Links springen zur
Zielstelle. Externe Links öffnen den Browser, aber nur mit `http`, `https` und `mailto`.
QPdfView gibt die Lage der Seiten nicht heraus, deshalb rechnet `PdfFileView.page_rects` sie
selbst aus. Wird Qt aktualisiert, prüft `tests/test_pdf_viewer.py` die Rechnung gegen das
gerenderte Bild. Ändert ein anderes Programm die Datei, lädt der Viewer
sie neu und bleibt auf derselben Seite. F5 lädt von Hand neu. Die Datei wird aus dem Speicher
angezeigt und bleibt deshalb unter Windows ungesperrt. Kennwortgeschützte PDFs fragen nach dem
Kennwort.

Startet die App mit einer .pdf, lädt sie weder Typst noch die Schriftliste noch die letzte
Sitzung. Erst **► Markdown** oder das Öffnen einer .md baut den Markdown-Modus auf. Ein
reiner Viewer-Start überschreibt die gespeicherte Sitzung nicht. Im Markdown-Modus öffnet
**PDF ansehen** das exportierte PDF im Viewer.

Das Setup bietet die Aufgabe **„PDF-Dateien mit CompletionistPDF öffnen können“** an. Sie ist
vorausgewählt und lässt sich abwählen. Damit steht die App unter *Öffnen mit* für .pdf und .md.
Windows erlaubt einem Setup nicht, den Standard-Viewer festzulegen. Wer CompletionistPDF als
Standard will, wählt es einmal unter *Öffnen mit → Andere App auswählen → Immer*. Ein alter
Benutzer-Schlüssel `Applications\CompletionistPDF.exe` (etwa auf einen früheren Build-Pfad)
wird dabei gelöscht, sonst hinge „Öffnen mit“ in einer Schleife. **In Editor öffnen** öffnet die `.md` mit dem Standardprogramm;
**► QR** startet CompletionistQR (neben dem Programm oder über dessen Setup gefunden).

### Drucken, zuletzt geöffnet, zusammenführen

- **Drucken …** (Strg+P) druckt im Viewer-Modus das PDF, im Markdown-Modus die aktuelle
  Vorschau. Seitenbereich, Drucker und Kopien kommen aus dem Windows-Druckdialog; jede
  Seite wird mit höchstens 600 dpi gerastert und seitenfüllend gesetzt.
- Der Pfeil am Druckknopf bietet **Seitenansicht …** (Strg+F2: Zoom, Seite/Doppelseite/
  Übersicht, Hoch-/Querformat, Drucken aus der Vorschau) und **Seite einrichten …**
  (Papierformat, Ausrichtung, Ränder; gilt bis zum Programmende). Der Code liegt in
  `core/printing.py` und ist derselbe wie in CompletionistMD.
- **Zuletzt ▾** listet die letzten 15 geöffneten Markdown- und PDF-Dateien
  (`%APPDATA%\CompletionistPDF\completionistpdf_recent.json`).
- **Zusammenführen …** fügt mehrere Markdown-Dateien zu einer neuen zusammen, getrennt
  durch `***` (= Seitenumbruch), und lädt sie sofort. Bildpfade werden umgerechnet
  (`core/md_merge.py`, derselbe Dialog wie in CompletionistMD).

### Hinweise zum Konverter

Eine Zeile, die mit „Zahl + Punkt“ beginnt („…am Ende↵3. Platz“), wird maskiert – Typst
machte daraus sonst eine nummerierte Liste. `tests/test_md_converter.py` prüft solche
Fälle am echten Typst-Compiler.

Überschriften der Ebene 2 (`##`) bekommen wie in CompletionistMD eine feine Linie
darunter. Abschalten lässt sie sich je Vorlage unter **Schriften & Typografie → Linie
unter Überschrift 2** (`typography.h2_rule`).

## Bauen

```powershell
.venv\Scripts\python.exe build_exe.py --app pdf    # baut dist\CompletionistPDF\ (Programmordner)
.\build_setup.ps1 -App pdf                         # baut Ordner + Setup mit Inno Setup
```

Das Setup braucht **Inno Setup 6** (`winget install JRSoftware.InnoSetup`); das Skript
`installer\CompletionistPDF.iss` bekommt die Version aus `core/__init__.py` übergeben. Die
`AppId` darin ist die Kennung für Updates und Deinstallation und darf sich nie ändern —
CompletionistMD findet CompletionistPDF darüber (`APP_IDS` in `core/qr_launcher.py`).

### Was nicht mitgepackt wird

Der Programmordner ist von 166 auf 119 MB geschrumpft. Das meiste davon ist Typst selbst
(`_typst.pyd`, 59 MB) und Qt (Core, Gui, Widgets, Pdf). Weggelassen wird:

| | Grund |
| :--- | :--- |
| **opengl32sw.dll** (20 MB) | Software-OpenGL als Notlösung für Rechner ohne Grafiktreiber. Die Oberfläche besteht aus Qt-Widgets, die Vorschau aus QtPdf — beides zeichnet ohne OpenGL. |
| **Pillow** (11 MB, davon 7,5 MB AVIF-Decoder) | wurde nur gebraucht, um beim Emoji-Test die farbigen Pixel eines Probebilds zu zählen. Das macht jetzt `count_saturated_pixels` in `core/typst_engine.py` mit QImage — bei 18 Proben (6 Schriften × 3 Auflösungen) exakt dieselben Zahlen wie mit Pillow. |
| **Qt-Übersetzungen** außer `qtbase_*` | Die App lädt nur `qtbase` (`core/qt_translations.py`), damit Ja/Nein/Abbrechen und die Kontextmenüs der Textfelder auf Deutsch erscheinen. `qtbase_*` sind seit dem 21.10.2026 wieder dabei (rund 6 MB, der größte Teil der früher hier gesparten 6,4 MB). |
| **OpenSSL** (6 MB) | kommt über `_ssl` und `_hashlib` herein. Die App geht nie ins Netz, `hashlib.sha1` (Bildnamen) ist auch ohne `_hashlib` da. Mit OpenSSL entfallen die TLS-Plugins von Qt. |
| **assets/** bis auf Schriften und Icon | Editor-Bundle und Icons der anderen Apps lagen bisher mit drin. |

Geprüft am fertigen Build: Testdokument mit Bild, umflossenem Bild, `data:`-Bild, Tabelle,
Fußnote und Emoji kompiliert, Vorschau (5 Seiten), Export als PDF, Emoji-Test („Segoe UI Emoji
liefert farbige Emojis"), Protokoll ohne Fehler.

Die Ausschlüsse stehen in `build_exe.py`: `EXCLUDES` (Python-Module) und `DROP_COMMON`
(Dateien). Zusätzlich lässt der Build jede Qt-DLL weg, die keine mitgenommene Datei lädt
(`drop_unused_qt_dlls`). Wer eine neue Abhängigkeit aufnimmt, sollte danach einmal
`python build_exe.py` laufen lassen und die Größe von `dist\CompletionistPDF\` prüfen.
