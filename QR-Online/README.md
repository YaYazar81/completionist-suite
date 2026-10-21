# QR-Online

QR-Codes, deren Scans gezählt werden, mit Graphen in einer Windows-App.

Ein gedruckter QR-Code meldet von sich aus nichts. QR-Online legt deshalb nicht das
eigentliche Ziel in den Code, sondern eine kurze Adresse auf dem eigenen Webspace
(z. B. `https://qr.example.de/A7KX9P`). Ein kleines PHP-Skript zählt dort jeden Aufruf und
leitet sofort zum Ziel weiter. Die App zeigt die Zahlen als Graphen.

Eigenes Projekt neben der Completionist Suite. CompletionistQR bleibt bei statischen Codes
ohne Server. Für einen gestalteten Code (Logo, Rahmen) den kurzen Link aus QR-Online in
CompletionistQR als „Website“ einfügen.

## Was gezählt wird

Pro Scan speichert der Server nur **Zeitpunkt, Gerätetyp** (Smartphone/Tablet/Computer),
**Betriebssystem** und **Browsersprache**. **Keine IP-Adresse, keine Cookies**, kein
Fingerprinting. Damit lässt sich niemand wiedererkennen. Vorschau-Abrufe von WhatsApp,
Telegram, Suchmaschinen usw. werden nicht mitgezählt, ebenso `HEAD`-Anfragen.

Die Weiterleitung antwortet mit `302` und `Cache-Control: no-store`, damit Browser das Ziel
nicht zwischenspeichern und auch wiederholte Scans ankommen.

## Funktionen

| | |
| :--- | :--- |
| **Links** | anlegen, Ziel und Namen jederzeit ändern (der gedruckte Code bleibt gültig), löschen |
| **Kennzahlen** | Scans im Zeitraum, heute, insgesamt, letzter Scan |
| **Graphen** | Scans pro Tag (bei „1 Jahr“ pro Woche), Uhrzeit, Wochentag, Gerät, Betriebssystem, Sprache; Tooltip beim Überfahren |
| **Zeitraum** | 7 Tage, 30 Tage, 90 Tage, 1 Jahr; gezählt nach lokaler Zeit |
| **Export** | QR-Code als PNG (schlicht, Fehlerkorrektur M), Link in die Zwischenablage |

Hell/Dunkel folgt der Windows-Einstellung.

## Server einrichten (einmalig)

Voraussetzung: Webspace mit **PHP 8** und **SQLite** (`pdo_sqlite`, bei fast allen
Hostern dabei) und Apache mit `mod_rewrite`. Am besten eine eigene Subdomain wie
`qr.example.de`, dann bleiben die Links kurz.

1. Den Inhalt von `server/` auf den Webspace laden (das Setup legt ihn unter
   *Startmenü → QR-Online – Server-Dateien* ab). `.htaccess` und `data/.htaccess` gehören
   dazu. Manche FTP-Programme blenden Dateien mit Punkt aus.
2. `config.sample.php` als `config.php` kopieren und einen langen Zufallsschlüssel
   eintragen, z. B. erzeugt mit `php -r "echo bin2hex(random_bytes(24));"`.
3. Prüfen: `https://qr.example.de/data/` und `https://qr.example.de/config.php` müssen
   **403** liefern. Die Datenbank darf nicht abrufbar sein.
4. In QR-Online unter **Server …** die Adresse (`https://qr.example.de`) und den Schlüssel
   eintragen und auf **Verbindung testen** klicken.

Die Datenbank `data/qronline.sqlite` legt das Skript beim ersten Aufruf selbst an. Für eine
Sicherung genügt es, diese Datei zu kopieren.

**Ohne mod_rewrite:** Die Links funktionieren auch als `https://qr.example.de/index.php?c=A7KX9P`.
Die App zeigt aber immer die kurze Form. Gibt es kein mod_rewrite, in der App unter
**Server …** die Adresse `https://qr.example.de/index.php` eintragen. Dann lauten die Links
`…/index.php/A7KX9P`, und auch das funktioniert.

**nginx:** statt `.htaccess`

```nginx
location / { try_files $uri /index.php$is_args$args; }
location ~ ^/(data/|config(\.sample)?\.php) { deny all; }
```

### API

Die App spricht den Server über eine kleine JSON-API an. Der Schlüssel steht im Kopf
`X-Api-Key`; `Authorization` wird von manchen Hostern verschluckt.

| Aufruf | |
| :--- | :--- |
| `GET /api/ping` | Schlüssel prüfen |
| `GET /api/links` | alle Links mit Scan-Zahl und letztem Scan |
| `POST /api/links` `{"target", "label"}` | neuer Link (Code: 6 Zeichen ohne 0/O/1/I/L) |
| `GET` / `POST` / `DELETE /api/links/<CODE>` | lesen, Ziel/Name ändern, löschen (samt Scans) |
| `GET /api/scans/<CODE>?since=YYYY-MM-DD` | einzelne Scans, Zeit in UTC |

## Starten

- **Installiert:** `QR-Online-Setup-<Version>.exe`, ohne Adminrechte.
- **Aus dem Quellcode** (venv der Suite, siehe Haupt-README):

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m qronline
```

## Entwicklung

```powershell
..\.venv\Scripts\python.exe -m pip install pytest pyinstaller
..\.venv\Scripts\python.exe -m pytest tests      # Server-Tests brauchen php im PATH
..\.venv\Scripts\python.exe build_exe.py         # dist\QR-Online\ (Programmordner)
.\build_setup.ps1                                # Ordner + Setup (Inno Setup 6)
..\.venv\Scripts\python.exe tools\make_icon.py   # Programmsymbol neu erzeugen (assets\)
```

Die Server-Tests starten `server/index.php` mit dem eingebauten PHP-Server und gehen den
ganzen Weg: Link anlegen, scannen mit iPhone-, Android- und Windows-Kennung, Statistik
abrufen, Ziel ändern, löschen. Ohne PHP werden sie übersprungen.

Aufbau: `server/index.php` (Weiterleitung und API, eine Datei), `qronline/client.py`
(API-Aufrufe), `qronline/stats.py` (Auswertung nach lokaler Zeit), `qronline/charts.py`
(Diagramme mit matplotlib), `qronline/app.py` (Oberfläche, CustomTkinter),
`qronline/settings.py` (Einstellungen unter `%APPDATA%\QR-Online`, der API-Schlüssel per
Windows-DPAPI verschlüsselt).

**Schneller Start:** Verteilt wird ein Programmordner statt einer einzelnen .exe, so wird
beim Start nichts entpackt. matplotlib lädt erst, wenn das Fenster schon steht. Die
Netzwerkaufrufe laufen im Hintergrund, die Oberfläche bleibt bedienbar.
