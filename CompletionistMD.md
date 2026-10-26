# CompletionistMD

WYSIWYG-Markdown-Editor der CompletionistPDF-Suite: schreiben wie in Typora,
speichern als ganz normales Markdown, das der vorhandene Typst-Konverter liest.

```bash
.\.venv\Scripts\python.exe main_md.py
```

Optional mit Datei: `python main_md.py "Kapitel 1.md"` (taugt auch für
*Öffnen mit* im Explorer).

## Aufbau

| Datei | Aufgabe |
| :--- | :--- |
| `main_md.py` | Startpunkt, Palette, Fensteraufbau |
| `mdeditor/window.py` | Hauptfenster, Toolbar, Kontextmenü, Auto-Save, Suchen, PDF-Übergabe |
| `mdeditor/tabs.py` | Tabs: Markdown, Text, PDF, Bild; Beobachten der Dateien |
| `mdeditor/vault.py` | Vault-Explorer links: Verzeichnisbaum, Dateiaktionen, Bookmarks, Mehrfachauswahl |
| `mdeditor/panels.py` | Gliederung, Suchleiste, Volltextsuche im Vault |
| `mdeditor/history_dialog.py` | Ältere Fassungen ansehen und wiederherstellen |
| `mdeditor/settings_dialog.py` | Einstellungen: Vault-Verzeichnis, Bookmarks, Google Drive |
| `mdeditor/gdrive.py` | Google-Drive-Sync (nur hochladen, lokal gewinnt) |
| `core/drive.py` | Anmeldung, DPAPI-Token und Drive-REST ohne Qt; teilt sich MD mit CompletionistQR (Datei hochladen und freigeben) |
| `mdeditor/emoji_dialog.py` | Emoji-Fenster mit Raster, Kategorien und Suche |
| `mdeditor/webview.py` | `QWebEngineView` + Brücke JS → Python, Drag & Drop |
| `mdeditor/markdown_io.py` | Ausfallsicheres Speichern, ältere Fassungen, Frontmatter |
| `mdeditor/images.py` | Bilder nach `images/` neben der `.md` |
| `core/md_merge.py`, `core/merge_dialog.py` | Dateien zusammenführen (auch in CompletionistPDF) |
| `assets/editor/` | Was die App lädt: `index.html`, `editor.css`, `markdown.js`, `tiptap.bundle.js` |
| `editor-src/` | Quelltext des Bundles (Tiptap 3 / ProseMirror) |
| `tools/node/` | Portables Node.js-LTS, nur zum Bauen des Bundles |

Der Schreibbereich ist ein [Tiptap](https://tiptap.dev)-Editor (ProseMirror) in
QtWebEngine. Die App lädt ausschließlich lokale Dateien und braucht zur
Laufzeit weder Node noch Netz.

- **Markdown → Editor:** `assets/editor/markdown.js` erzeugt HTML, das die
  Parse-Regeln der Knoten in `editor-src/src/nodes.js` lesen.
- **Editor → Markdown:** `editor-src/src/serialize.js` schreibt das
  ProseMirror-Dokument direkt als Markdown. Was eingelesen wird, kommt
  zeichengleich wieder heraus (Round-Trip).
- **Eigene Knoten:** Bild mit Ausrichtung/Breite, Bild im Satz, zwei Arten
  Trennlinie, weicher/harter Zeilenumbruch, Codeblock mit Sprache, roher
  HTML-Block (wird unverändert durchgereicht), Tabellenzellen mit
  Spaltenausrichtung.
- **Render-in-Place:** `editor-src/src/reveal.js` (siehe unten).
- **Python ↔ JS:** `window.CM` (`setMarkdown`, `getMarkdown`, `exec`,
  `insertTable`, `insertImage`, `tableOp`, `imageOp`, `undo`, `redo`,
  `selectAll`, `deleteSelection`, …); zurück nur kurze Meldungen über die
  Konsole (`@@CM@@`), darunter `contextmenu` für das Rechtsklick-Menü.

### Bundle bauen

Nach jeder Änderung in `editor-src/src/`:

```bash
.\build_editor.ps1
```

Das Skript nutzt das Node aus `tools/node` (PATH bleibt unberührt), installiert
beim ersten Lauf die Pakete exakt nach `package-lock.json` und schreibt
`assets/editor/tiptap.bundle.js`. Mit `-Watch` baut es bei jeder Änderung neu.
Die Versionen sind fest: Tiptap 3.31.4, esbuild 0.28.2, Node 24.21.0 LTS.

### Installieren und bauen

Verteilt wird CompletionistMD über `CompletionistMD-Setup-<Version>.exe` (rund 92 MB). Das
Setup braucht keine Adminrechte und legt das Programm unter
`%LOCALAPPDATA%\Programs\CompletionistMD` ab; im ersten Dialog lässt sich auch „für alle
Benutzer" wählen. Deinstallieren über die Windows-Programmliste.

Das Setup trägt CompletionistMD als Programm für `.md` ein (eigene ProgID
`CompletionistMD.md` mit Icon, „Öffnen mit“). Den Standard legt Windows nicht per Setup
fest: einmal *Öffnen mit → CompletionistMD → Immer*. Vorher löscht das Setup einen alten
Benutzer-Schlüssel `Applications\CompletionistMD.exe` – zeigte der auf einen früheren
Build-Pfad, landete „Öffnen mit“ in einer Endlosschleife und das Icon fehlte.

```bash
.\.venv\Scripts\python.exe build_exe.py --app md
.\build_setup.ps1 -App md
```

Das erste baut den Programmordner `dist\CompletionistMD\`, das zweite baut ihn neu und
packt ihn mit Inno Setup 6 (`winget install JRSoftware.InnoSetup`) ins Setup
(`installer\CompletionistMD.iss`, Version aus `mdeditor/__init__.py`, `-SkipBuild` nimmt
den vorhandenen Ordner). Die `AppId` in der `.iss` darf sich nie ändern. Das
Tiptap-Bundle muss vorher gebaut sein. `-App all` baut die Setups aller drei Programme.

#### Was nicht mitgepackt wird

Der Programmordner ist von 507 auf 282 MB geschrumpft. Gut 200 MB davon sind
`Qt6WebEngineCore.dll` (Chromium) und lassen sich nicht verkleinern. Weggelassen wird:

| | MB | Grund |
| :--- | ---: | :--- |
| `*.debug.pak`, `v8_context_snapshot.debug.bin` | 77 | nur für Debug-Builds von Qt |
| Qt-DLLs ohne Aufrufer | 48 | Qt Quick 3D, Quick Controls, Multimedia, Pdf … — PyInstallers Qt-Hooks sammeln sie ein, geladen werden sie nie. Der Build behält nur, was über die Importtabellen der `.pyd`, Plugins und `QtWebEngineProcess.exe` erreichbar ist (`drop_unused_qt_dlls`). |
| `qtwebengine_locales` außer `de`, `en-US`, `en-GB` | 42 | Texte von Kontextmenü und Fehlerseiten; fehlt die Systemsprache, nimmt Chromium Englisch |
| `opengl32sw.dll` | 20 | Software-OpenGL. QtWebEngine zeichnet unter Windows über Direct3D (geprüft: der alte Build lädt die DLL nie, auch nicht mit `--disable-gpu`; mit erzwungenem `QT_OPENGL=software` + OpenGL-Backend stürzt er trotz DLL ab) |
| `qtwebengine_devtools_resources.pak` | 11 | Chromium-Entwicklerwerkzeuge, die App öffnet sie nicht |
| Qt-Übersetzungen außer `qtbase_*`, `qtwebengine_*` | – | geladen werden nur diese beiden (`core/qt_translations.py`): Ja/Nein/Abbrechen, Kontextmenüs von Textfeldern und Editor auf Deutsch. Seit dem 21.10.2026 wieder dabei (rund 6 MB der früher gesparten 9 MB) |
| `qml/` | 8 | QML-Module; `QWebEngineView` ist ein Widget |
| TLS-Plugins von Qt | – | Chromium bringt sein eigenes TLS (BoringSSL) mit. Pythons OpenSSL (`_ssl`) bleibt dagegen drin: der Google-Drive-Sync spricht HTTPS |
| PySide6-Module Quick, Qml, OpenGL, Positioning … | 3 | `QtWebEngineWidgets` lädt auf Python-Seite nur QtNetwork, QtWebChannel und QtPrintSupport nach |

Geprüft am fertigen Build und nach Installation per Setup: Datei öffnen, tippen, Strg+S,
Bild über **Bild ▾** einfügen (landet in `images/`), **► PDF** startet das installierte
CompletionistPDF mit der Datei.

Die Listen stehen in `build_exe.py` (`EXCLUDES_MD`, `DROP_COMMON`, `DROP_MD`,
`KEEP_WEBENGINE_LOCALES`). Nach einem Update von PySide6 einmal bauen und prüfen, ob die App
startet. Die DLL-Auswahl passt sich von selbst an, die Dateilisten nicht.

## Speichern

Jede Änderung geht rund 300 ms später in die geöffnete `.md`. YAML-Frontmatter wird
unverändert durchgereicht.

- **Nur bei echten Änderungen:** Der Editor vergleicht das Markdown mit dem zuletzt
  geladenen bzw. gespeicherten Stand (`CM.unsavedMarkdown()`, `CM.markSaved()`).
  Klicken, Lesen und das Auf- und Zuklappen der Syntax fassen die Datei nicht an –
  auch nicht beim Schließen oder Dateiwechsel, wenn der Editor sie anders
  formatieren würde (z. B. `*`-Listen). Wer bis zum gespeicherten Stand zurück
  tippt oder rückgängig macht, sieht wieder „gespeichert", ohne dass geschrieben wird.

- **Ausfallsicher:** Geschrieben wird erst in eine versteckte Zwischendatei
  `.<Name>.tmp` daneben, die dann in einem Schritt die Datei ersetzt. Ein Absturz
  oder Stromausfall mitten im Speichern hinterlässt so nie eine leere oder halbe Notiz
  (die der Drive-Sync sonst hochladen würde).
- **Ältere Fassungen:** Vor dem Überschreiben sichert der Editor höchstens alle 10 Minuten
  den bisherigen Stand nach `.completionistmd/verlauf/<Datei>/` neben der Datei; die
  letzten 30 bleiben. **Datei ▾ → Ältere Fassungen …** zeigt sie an und stellt eine
  wieder her (der jetzige Stand wird dabei ebenfalls gesichert). Ordner mit Punkt zeigt
  der Vault-Explorer nicht, und der Drive-Sync lässt sie aus.
- **Gilt auch für `.txt`-Tabs.**

## Mehrere Fenster

CompletionistMD darf mehrfach laufen (z. B. um mit Alt+Tab zwischen Dateien zu kopieren).
Nur das erste Fenster stellt beim Start die zuletzt offenen Tabs wieder her und merkt sie
sich; jedes weitere öffnet nur die Datei, mit der es gestartet wurde.

Jeder Tab beobachtet seine Datei. Ändert ein anderes Fenster oder Programm sie und der
Tab hat keine ungespeicherten Änderungen, lädt er still neu. Hat er welche, fragt er:
**Meine Fassung behalten** oder **Andere Fassung laden** – die jeweils andere landet in
den älteren Fassungen.

## Suchen, Gliederung, zuletzt geöffnet

- **Strg + F** sucht im aktiven Tab (Markdown oder Text), **Strg + H** ersetzt. Treffer
  sind gelb markiert, F3 / Umschalt + F3 oder Enter springen weiter, Esc schließt.
  „Aa“ beachtet Groß-/Kleinschreibung. Im PDF-Tab springt Strg + F in dessen Suchfeld.
- **Strg + Umschalt + F** durchsucht alle Notizen im Vault (`.md`, `.txt`, ohne Ordner mit
  Punkt). Doppelklick öffnet die Datei und markiert den Begriff.
- **☰** (Strg + Umschalt + G) blendet links neben dem Vault-Explorer die **Gliederung**
  ein: alle Überschriften des aktiven Dokuments, Klick springt hin. Sie folgt dem Tippen.
- **Datei ▾ → Zuletzt geöffnet** listet die letzten 15 Dateien.

## Dateien zusammenführen

Im Vault-Explorer mehrere `.md` mit Strg- bzw. Umschalt-Klick markieren, Rechtsklick →
**n Dateien zusammenführen …** (oder **Datei ▾ → Dateien zusammenführen …**). Im Dialog
die Reihenfolge per Ziehen festlegen und den Namen der neuen Datei wählen. Zwischen je
zwei Dateien steht eine harte Trennlinie `***` – in CompletionistPDF ein Seitenumbruch.
Relative Bild- und Linkpfade werden auf den Ordner der neuen Datei umgerechnet; YAML-
Frontmatter bleibt nur von der ersten Datei. Die Quelldateien bleiben unverändert.

## Render-in-Place (Typora-Stil)

Ohne Cursor ist alles gerendert. Steht der Cursor in einem formatierten
Element, zeigt der Editor dessen Markdown-Syntax grau an — und zwar als
echten, editierbaren Text:

| Element | Am Cursor sichtbar | Bearbeiten |
| :--- | :--- | :--- |
| fett, kursiv, durchgestrichen, Code, Link | `**…**`, `*…*`, `~~…~~`, `` `…` ``, `[…](url)` | Begrenzer und URL direkt ändern; beim Verlassen wird neu gelesen (`*` statt `**` macht kursiv) |
| Überschrift | `## ` | Rauten ändern die Ebene sofort; ohne Rauten wird es Fließtext. Holt Strg+Z gelöschte Rauten zurück, zählen sie wieder zur Ebene |
| Trennlinie | `***` bzw. `---` als Textzeile | Zeichen ändern (`***` ↔ `---`), Text daraus machen |
| Bild | Markdown in der Bildleiste (`![…](…)` oder `<img …>`) | Enter übernimmt, Esc verwirft |
| Codeblock | ` ```sprache ` oben, ` ``` ` unten | Sprache direkt im Feld ändern |
| Zitat, Liste, Aufgabe | `> `, `- `, `1. `, `- [ ] ` vor dem Absatz | über die Tastatur wie gewohnt |

Steht vor aufgeklapptem Quelltext am Absatzanfang Blocksyntax (`## `, `- `, `1. `,
`- [ ] `, `> `, z. B. weil sie vor `**Begriff**` getippt wurde, wo Tiptaps
Eingaberegeln nicht greifen), wird der Absatz beim Zuklappen zu diesem Block
(`collapseBlockPrefix` in `reveal.js`). Nur in Tabellenzellen bleibt sie Text.

Verlässt der Fokus den Editor, wird alles wieder gerendert. Aufgeklappter
Quelltext trägt die Markierung `mdSource` und wird unverändert gespeichert;
die Datei ist in beiden Zuständen gleich. Auf- und Zuklappen ändern nur die
Begrenzer, nicht den Text dazwischen, und laufen außerhalb der Historie —
Rückgängig springt also über das Aufklappen hinweg.

Beim Tippen wandelt der Editor Markdown sofort um: `## ` → Überschrift,
`***`/`---` + Enter → Trennlinie, ` ```py ` + Enter → Codeblock,
`[Text](url)` → Link, `![Alt](pfad)` → Bild, `- [ ] ` → Aufgabe, dazu `**…**`
usw. wie bisher.

## Vault-Explorer und Bookmarks

**📁** (Strg + Shift + E) blendet links den Verzeichnisbaum ein und aus. Das
Hauptverzeichnis steht unter **Einstellungen** (Zahnrad) in der Statusleiste
(Ordnerdialog) und wird beim Start geladen. Der Baum zeigt Ordner, `.md` und
Bilder; Ordner mit Punkt am Anfang (`.obsidian`, `.trash`) bleiben verborgen.

- **Klick** auf eine `.md` öffnet sie, **Doppelklick** auf ein Bild öffnet es
  im Standardprogramm.
- **Rechtsklick:** bei PDFs **Öffnen** im Standardprogramm (PDF-Reader) oder in
  einem neuen Tab; Neue Datei, Neuer Ordner, Umbenennen, Löschen (in den
  Papierkorb), Im Explorer anzeigen, Als Bookmark hinzufügen. Wird die offene
  Datei oder ihr Ordner umbenannt, zieht der Editor mit.
- **Bookmarks** stehen als Kacheln unten im Panel. Ein Klick klappt den Baum bis
  zum Zielordner auf. Anlegen über **+**, Rechtsklick auf eine Kachel
  (Bearbeiten, verschieben, entfernen) oder in den Einstellungen.

Vault-Pfad, Bookmarks, Sichtbarkeit und Breite des Panels liegen in
`%APPDATA%\CompletionistPDF\completionistmd.json`.

## Kontextmenü und Emojis

Rechtsklick im Text öffnet ein natives Menü: Rückgängig, Wiederholen,
Ausschneiden, Kopieren, Einfügen, Löschen, Alles auswählen, **Emoji einfügen**
(die Guide-Symbole 📜 🗺️ 🏆 💎 🚨 ✅ ⚔️ 🧩 🔑 ⭐ ⏱️ 📍 🔴 🟢), Format, Absatz,
Neu einfügen und in Tabellen bzw. auf Bildern deren Aktionen.

**Weitere Emojis …** (Toolbar-Menü 😀 und Kontextmenü) öffnet ein eigenes
Fenster mit allen Emoji-Gruppen in `Segoe UI Emoji`, Kategorien links und
Suche nach englischem Unicode-Namen oder deutschen Begriffen (Herz, Stern,
Pfeil, Schwert …). Jeder Klick fügt am Cursor ein; das Fenster bleibt offen.

## Bilder und Textumfluss

- **Strg + V** oder **Drag & Drop** legt das Bild in `images/` neben der `.md`
  ab (PNG; SVG aus der Zwischenablage bleibt SVG) und fügt es an der
  Cursorstelle ein. Nie als `data:`-URI.
- Klick auf ein Bild öffnet die schwebende Leiste: links umflossen, zentriert,
  rechts umflossen, Breite ±5 %, Bildunterschrift, löschen. Rechtsklick bietet
  dasselbe im Menü.
- Umflossene Bilder stehen im Editor als `float` im Textfluss — der Text
  schmiegt sich live an die Bildkante.

Gespeichert wird:

| Ausrichtung | Markdown |
| :--- | :--- |
| zentriert | `![Alt](images/bild-001.png)` |
| zentriert mit Breite | `<img src="…" align="center" width="60%" alt="…">` |
| links / rechts umflossen | `<img src="…" align="left" width="40%" alt="…">` |

Beide Formen liest der Konverter von CompletionistPDF. Bei `align="left"`
bzw. `"right"` wird das Bild auch im PDF umflossen (`md-wrap` in
`templates/helpers.typ`): Umflossen werden die Blöcke nach dem Bild bis zur
nächsten Überschrift, Trennlinie, Tabelle oder zum nächsten Bild. Im PDF ist
der Umfluss **absatzweise**, nicht zeilengenau wie im Editor: Neben das Bild
kommen so viele ganze Absätze, wie etwa seiner Höhe entsprechen, der Rest
läuft darunter in voller Breite. Ein sehr langer erster Absatz bleibt deshalb
ganz in der schmalen Spalte neben dem Bild. Folgt kein Text, steht das Bild
allein am linken bzw. rechten Rand.

## Tabellen

Toolbar → **Tabelle ▾** zeigt ein 8×8-Raster; Ziehen wählt die Größe. Im
selben Menü und per Rechtsklick in der Tabelle: Zeile oberhalb/unterhalb,
Spalte links/rechts, Zeile/Spalte löschen, Kopfzeile umschalten,
Spaltenausrichtung, Tabelle löschen. **Tab** springt zur nächsten Zelle und
hängt am Ende eine Zeile an.

## Trennlinien

Die Suite unterscheidet zwei Linien, der Editor zeigt sie verschieden an:

- `***` — **harte Trennlinie**, wird im PDF zum Seitenumbruch (gestrichelt, mit
  Beschriftung „Seitenumbruch“).
- `---` — **visuelle Linie**, reine Optik (dünne graue Linie).

## Tastatur

| Taste | Wirkung |
| :--- | :--- |
| `#` … `######` | Überschrift |
| `-` , `*` , `1.` | Liste |
| `[ ]` am Zeilenanfang | Aufgabe |
| `>` | Zitat |
| `` ``` `` + Leertaste/Enter | Codeblock (`` ```python `` mit Sprache) |
| `---` | visuelle Linie |
| `***` (mit Leertaste oder Enter) | harte Trennlinie |
| `[Text](url)`, `![Alt](pfad)` | Link, Bild |
| `**…**`, `*…*`, `` `…` ``, `~~…~~` | formatiert beim Tippen |
| Umschalt + Enter | Zeilenumbruch im Absatz |
| Tab / Umschalt + Tab | nächste Zelle · Listenpunkt ein-/ausrücken |
| Strg + Z / Strg + Y | rückgängig / wiederholen |
| Strg + B/I/\`/Shift+X | fett, kursiv, Code, durchgestrichen |
| Strg + 0 … 6 | Fließtext, Überschrift 1–6 |
| Strg + Shift + L/O/T | Aufzählung, Nummerierung, Aufgabe |
| Strg + S | sofort speichern |
| Strg + F / Strg + H | suchen / ersetzen |
| Strg + Shift + F | im Vault suchen |
| Strg + Shift + E | Vault-Explorer ein-/ausblenden |
| Strg + Shift + G | Gliederung ein-/ausblenden |
| Strg + V | Text einfügen; Bild aus der Zwischenablage landet in `images/` |
| F5 | an CompletionistPDF übergeben |

## CompletionistPDF starten

**► PDF** speichert und startet CompletionistPDF mit der aktuellen Datei.
Gesucht wird `CompletionistPDF.exe` neben der App, in `dist/` (auch als
Programmordner), unter `%LOCALAPPDATA%\Programs\CompletionistPDF` und zuletzt
über den Uninstall-Eintrag des Setups; aus dem Quellcode heraus sonst
`main.py` mit demselben Python.
