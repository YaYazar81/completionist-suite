# CompletionistQR

Windows-App für gestaltete QR-Codes: Logo in der Mitte, verschiedene Designs, Rahmen und
Beschriftung in wählbarer Schriftart. Mit Live-Vorschau und automatischer Scan-Prüfung.

Eigenständiges Fenster neben CompletionistPDF und CompletionistMD; aus beiden lässt es sich
über den Knopf **► QR** in der Werkzeugleiste starten. Die Oberfläche baut auf CustomTkinter
auf, nicht auf Qt wie die beiden anderen Programme.

## Starten

- **Installiert:** `CompletionistQR-Setup-<Version>.exe` ausführen. Das Setup braucht keine
  Adminrechte und legt das Programm unter `%LOCALAPPDATA%\Programs\CompletionistQR` ab; im
  ersten Dialog lässt sich auch „für alle Benutzer" wählen. Deinstallieren über die
  Windows-Programmliste.
- **Aus dem Quellcode:** `.venv\Scripts\python.exe -m completionistqr`

## Funktionen

| Reiter | Inhalt |
| :--- | :--- |
| **Inhalt** | Website, Kontakt (vCard), WLAN, E-Mail, SMS, WhatsApp, Telefon, Zahlung (SEPA-GiroCode oder PayPal.me), Standort (Kartenlink oder `geo:`), Social Media (Instagram, TikTok, YouTube …), App-Link, Feedback (Formular oder E-Mail), PDF/Bild/Video als Link, Freitext; Fehlerkorrektur L/M/Q/H |
| **Design** | 8 Vorlagen + eigene Vorlagen speichern; Modulform (Quadrate, Punkte, abgerundet, Rauten, Balken …), Farbe oder Verlauf (linear/radial), Hintergrund oder transparent, Ruhezone; Ecken-Marker mit eigener Form und Farbe |
| **Logo** | PNG/JPG/WebP/AVIF in der Mitte (wählen, ins Fenster ziehen oder Strg+V), Größe 10–30 %, farbige Unterlage mit Eckenradius und Innenabstand |
| **Beschriftung** | Rahmen (Linie, Karte, Banner oben/unten, Ticket), ein- oder zweizeiliger Text, 10 Schriftarten, fett, Größe, Farbe |
| **Export** | PNG in 512–4096 px und 150/300/600 dpi, SVG und PDF als echte Vektorgrafik (Strg+S); in die Zwischenablage (Strg+C); Stapel-Export aus einer CSV-Liste |

Design, Inhaltstyp und Formularwerte merkt sich die App bis zum nächsten Start.

**Statische Codes:** Alles steht im Code selbst, ohne Server und ohne Ablaufdatum. Was
Online-Generatoren als „PDF“, „Bild“, „Video“ oder „Mehrere Links“ anbieten, sind
dynamische Codes auf eine dort gehostete Seite. Hier enthält der Code den Freigabe-Link
(Google Drive, Dropbox, YouTube …). „Mehrere Links“ bräuchte eine eigene Webseite und fehlt
deshalb.

**Datei in Google Drive hochladen:** Beim Inhaltstyp „PDF, Bild oder Video (Link)“ lädt der
Knopf **Datei in Google Drive hochladen …** eine lokale Datei in das eigene Google Drive
(Ordner „CompletionistQR Dateien“), gibt sie für „Jeder mit dem Link: Betrachter“ frei und
setzt den kurzen Link `https://drive.google.com/file/d/<ID>/view` in den Code. Hochgeladen
wird im Hintergrund in Stücken zu 8 MB, mit Fortschrittsbalken und „Abbrechen“; reißt die
Verbindung ab, macht der Upload dort weiter, wo Google steht. Die Anmeldung teilt sich die
App mit dem Google-Drive-Sync von CompletionistMD (`client_secret.json` und das per DPAPI
verschlüsselte Token unter `%LOCALAPPDATA%\CompletionistLibrary\CompletionistMD\credentials`).
Ist dort noch nichts, fragt die App einmal nach der `client_secret.json` (OAuth-Client vom Typ
„Desktop-App“ mit aktivierter Google Drive API) und öffnet dann die Anmeldung im Browser.
Scope ist `drive.file`: die App sieht nur Dateien, die sie selbst angelegt hat.

**Zahlung:** Der GiroCode (EPC-QR, Version 002) wird von den Banking-Apps deutscher Banken
und Sparkassen gelesen; die IBAN wird per Prüfziffer kontrolliert, Betrag leer = frei.

**Stapel-Export:** CSV (auch aus Excel, Trennzeichen `;`) mit dem Inhalt in der ersten
Spalte, optional dem Dateinamen in der zweiten; eine Kopfzeile wie `Inhalt;Dateiname` wird
erkannt. Alle Codes bekommen das aktuelle Design; auf Wunsch wird jeder auf Lesbarkeit
geprüft. Eine CSV lässt sich auch einfach ins Fenster ziehen.

**Export-Warnung:** Besteht der Code die Scan-Prüfung nicht, fragt „Speichern“ vorher nach.

Unter der Vorschau steht, ob der Code die **Scan-Prüfung** besteht. Dafür wird das fertige Bild
mit der ZXing-Engine zurückgelesen, die auch in vielen Scanner-Apps steckt. Wird die Prüfung
nicht bestanden, Logo verkleinern, Kontrast erhöhen oder eckigere Augen wählen. Vor dem Druck
trotzdem einmal mit dem Handy testen.

Eigene Vorlagen liegen unter `%APPDATA%\CompletionistQR\presets\`. Vorlagen aus der Zeit, als
die App noch QR Studio hiess (`%APPDATA%\QRStudio\`), werden beim ersten Start übernommen.

**Hell/Dunkel:** Mit dem Umschalter oben rechts lässt sich die Oberfläche hell, dunkel oder
passend zu Windows darstellen; die Wahl wird gespeichert. Die Vorlage **Midnight** ist ein
dunkler QR-Code (helle Module auf dunklem Grund). Aktuelle iPhone- und Android-Kameras lesen
solche invertierten Codes, manche ältere Scanner-Apps nicht – bei breitem Publikum im Zweifel
dunkel auf hell verwenden.

## Schriftarten

Inter, Montserrat, Poppins, Oswald, Bebas Neue, Anton, Playfair Display, Lora, Roboto Mono und
Caveat – alle von Google Fonts unter der SIL Open Font License (Lizenztexte liegen jeweils neben
den Dateien in `completionistqr\assets\fonts\`).

Das **PDF** ist eine echte Vektorgrafik: Module, Augen, Rahmen und Farbverläufe sind Pfade,
die Beschriftung steht als Schriftkontur darin (gesetzt mit HarfBuzz, samt Unterschneidung),
das Logo in Originalauflösung. Damit ist der Code in jeder Druckgröße randscharf und sieht in
jedem Programm gleich aus, auch ohne installierte Schrift. Breite und dpi legen beim PDF
nur die Seitengröße fest (1024 px bei 300 dpi = 86,7 mm). Für den Druck ist PDF die beste Wahl.

Im **SVG** ist die gewählte Schrift eingebettet. Browser und Inkscape zeigen sie korrekt an,
manche Office-Programme ignorieren eingebettete Schriften jedoch.

## Entwicklung

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install pytest          # nur fuer die Tests
.venv\Scripts\python.exe tools\fetch_fonts.py           # Schriftarten laden (einmalig, braucht Internet)
.venv\Scripts\python.exe -m pytest tests                # Tests inkl. Scan-Prüfung aller Vorlagen
.venv\Scripts\python.exe build_exe.py --app qr          # baut dist\CompletionistQR\ (Programmordner)
.\build_setup.ps1                                       # baut Ordner + Setup mit Inno Setup
.\build_setup.ps1 -App all                              # Setups für PDF, MD und QR
```

Verteilt werden alle drei Programme nur noch per Setup, Einzeldateien (`--onefile`) werden
nicht mehr gebaut. Das Setup braucht **Inno Setup 6** (`winget install JRSoftware.InnoSetup`); das Skript
`installer\CompletionistQR.iss` bekommt die Version aus `completionistqr/__init__.py`
übergeben. Die `AppId` darin ist die Kennung für Updates und Deinstallation und darf sich
nie ändern; CompletionistPDF und CompletionistMD finden die App darüber (`APP_IDS` in
`core/qr_launcher.py`, dort stehen auch die AppIds der beiden anderen Setups).

Das Programmsymbol liegt als `completionistqr\assets\icon_source.png` (1024 px, transparent)
daneben; `python tools\make_icon.py` macht daraus `icon.ico` mit allen Windows-Größen. Das
Skript läuft nicht automatisch beim Build mit — es überschreibt `icon.ico`.

Aufbau: `completionistqr/core` enthält Encoder (`matrix.py`), Geometrie (`geometry.py`, `shapes.py`),
die Renderer für Raster (`render_pil.py`) und Vektor (`render_svg.py`, `render_pdf.py`) sowie
Export und Vorlagen. Alle drei zeichnen dieselbe Szene, deshalb sehen PNG, PDF und SVG identisch
aus; SVG und PDF bekommen ihre Pfade aus derselben Kontur (`shapes.py`) und füllen wie Pillow
nach der Regel nonzero. `tests/test_vector_export.py` rastert jedes Vorlagen-PDF mit QtPdf und
prüft es auf Lesbarkeit.
`completionistqr/ui` enthält die Oberfläche (CustomTkinter), `ui/drive_upload.py` den Knopf
zum Hochladen. Anmeldung und Drive-Aufrufe liegen ohne Qt in `core/drive.py` im Hauptordner;
CompletionistMD nutzt dieselben (`mdeditor/gdrive.py`).

### Was nicht mitgepackt wird

Die App kommt mit Pillow, qrcode, CustomTkinter, zxing-cpp und uharfbuzz (Beschriftung im
Vektor-PDF) aus, dazu google-auth und requests für das Hochladen nach Google Drive. Bewusst
draußen ist nur NumPy, weil es ohne Einbuße an Qualität ersetzt ist:

| | Grund |
| :--- | :--- |
| **NumPy** (26 MB) | wurde nur für den Farbverlauf gebraucht. `core/colors.py` zieht stattdessen eine kleine Vorlage mit einer affinen Abbildung auf die Zielgröße — das rechnet Pillow in C. |
| ~~**AVIF-Decoder** (7,5 MB)~~ | war bis 1.2.0 draußen. Seit 1.3.0 dürfen Logos auch AVIF sein. |
| ~~**OpenSSL** (6 MB)~~ | war bis 1.1.0 draußen. Seit dem Hochladen nach Google Drive spricht die App HTTPS und braucht `ssl`, `_ssl` und `_hashlib` wieder. |

Gemessen am 21.10.2026: Mit dem Upload wuchs das Setup von 14,6 auf 21,1 MB und
`dist\CompletionistQR\` von 35,8 auf 56,1 MB. Der größte Teil ist `cryptography` (9,4 MB), das
google-auth zwingend lädt (auch für die reine Benutzer-Anmeldung), dazu OpenSSL (rund 6 MB),
requests und certifi.

Die Ausschlussliste steht als `EXCLUDES_QR` in `build_exe.py`. Wer eine neue Abhängigkeit
aufnimmt, sollte danach einmal `python build_exe.py --app qr` laufen lassen und die Größe
von `dist\CompletionistQR\` prüfen.
