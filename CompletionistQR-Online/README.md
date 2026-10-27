# CompletionistQR Online

QR-Codes, deren Scans gezählt werden, mit Graphen in einer Windows-App.

Ein gedruckter QR-Code meldet von sich aus nichts. CompletionistQR Online legt deshalb nicht das
eigentliche Ziel in den Code, sondern eine kurze Adresse auf dem eigenen Webspace
(z. B. `https://qr.example.de/A7KX9P`). Ein kleines PHP-Skript zählt dort jeden Aufruf und
leitet sofort zum Ziel weiter. Die App zeigt die Zahlen als Graphen.

Eigenes Programm neben CompletionistQR, aber mit demselben Gestalter: **„QR-Code gestalten
und speichern …“** öffnet die Bedienleiste und Vorschau von CompletionistQR (Vorlagen, Formen,
Farben, Logo, Rahmen, Beschriftung, Scan-Prüfung, Export als PNG, SVG oder PDF) mit dem
Kurzlink als festem Inhalt. Der Code dafür liegt nur einmal im Paket `completionistqr`
(`completionistqr/ui/designer.py`); was CompletionistQR neu lernt, kann CompletionistQR Online damit
automatisch auch. Das Design merkt sich CompletionistQR Online je Link.

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
| **Gestalten** | wie in CompletionistQR: Vorlagen, Formen, Farben, Verläufe, Logo, Rahmen, Beschriftung, Scan-Prüfung; je Link gemerkt |
| **Export** | PNG (512–4096 px, 150–600 dpi), SVG und PDF als Vektorgrafik, Zwischenablage; Link in die Zwischenablage |
| **Über** | ⓘ bzw. F1: Version, Lizenz, Fremdkomponenten, Impressum (wie in CompletionistQR) |

Hell/Dunkel folgt der Windows-Einstellung; im Gestalter lässt es sich umschalten.

## Server einrichten (einmalig)

Voraussetzung: Webspace mit **PHP 8** und **SQLite** (`pdo_sqlite`, bei fast allen
Hostern dabei) und Apache mit `mod_rewrite`. Am besten eine eigene Subdomain wie
`qr.example.de`, dann bleiben die Links kurz.

Beim ersten Start führt die App durch die Einrichtung (später jederzeit unter **Server …**):

1. **Neuen Server einrichten** wählen und die künftige Server-Adresse eintragen, z. B.
   `https://qr.example.de`. Die App hat schon einen zufälligen API-Schlüssel erzeugt.
2. **Server-Dateien speichern …**: die App legt `index.php`, `.htaccess`, `data/.htaccess` und
   eine fertige `config.php` mit diesem Schlüssel in einen Ordner und öffnet ihn.
3. Den Inhalt des Ordners **per FTP** in das Verzeichnis laden, auf das die Adresse zeigt
   (FileZilla oder Dateimanager des Hosters). `.htaccess` und `data/.htaccess` gehören dazu;
   manche FTP-Programme blenden Dateien mit Punkt aus. SSL für die Adresse einschalten.
4. **Verbindung testen** und **Speichern**.

Wer schon einen Server hat, wählt **Vorhandenen verbinden** und trägt Adresse und den
Schlüssel aus dessen `config.php` ein.

Von Hand geht es auch: den Inhalt von `server/` hochladen (das Setup legt ihn unter
*Startmenü → CompletionistQR Online – Server-Dateien* ab), `config.sample.php` als
`config.php` kopieren und einen langen Zufallsschlüssel eintragen, z. B. erzeugt mit
`php -r "echo bin2hex(random_bytes(24));"`.

Danach prüfen: `https://qr.example.de/data/` und `https://qr.example.de/config.php` müssen
**403** liefern. Die Datenbank darf nicht abrufbar sein.

Die Datenbank `data/qronline.sqlite` legt das Skript beim ersten Aufruf selbst an. Für eine
Sicherung genügt es, diese Datei zu kopieren.

**Ohne mod_rewrite:** Die Links funktionieren auch als `https://qr.example.de/index.php?c=A7KX9P`.
Die App zeigt aber immer die kurze Form. Gibt es kein mod_rewrite, in der App unter
**Server …** die Adresse `https://qr.example.de/index.php` eintragen. Dann lauten die Links
`…/index.php/A7KX9P`, und auch das funktioniert.

### Eigene kurze Domain für die Links

Die Adresse im QR-Code muss nicht die des Servers sein. Mit einer eigenen kurzen Domain
(z. B. `c10t.de`) lauten die Links `https://c10t.de/A7KX9P`, während App und Plugin den
Server weiter unter seiner Adresse ansprechen (z. B. `https://completionist-library.de/qr`).

1. Die kurze Domain auf denselben Ordner zeigen lassen, in dem `index.php` liegt – in Plesk
   z. B. als eigene Website, deren Dokumentstamm dieser Ordner ist, oder als Domain-Alias.
   SSL (Let's Encrypt) für die kurze Domain einschalten.
2. In der `config.php` des Servers eintragen:

   ```php
   'short_url' => 'https://c10t.de',
   ```

Fertig: der Server liefert bei jedem Link die kurze Adresse mit, App und WordPress-Plugin
zeigen und kodieren sie von selbst – in beiden muss nichts umgestellt werden. Gezählt und
weitergeleitet wird unter beiden Adressen; schon gedruckte Codes mit der alten Adresse
funktionieren also weiter.

Alternativ kann der ganze Server auf die kurze Domain umziehen (Inhalt des Ordners samt
`data/` ins Hauptverzeichnis der Domain, in App und Plugin die Adresse `https://c10t.de`
eintragen). Dann laufen alte Codes nur weiter, solange der alte Ordner bleibt.

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
| `GET /api/ping` | Schlüssel prüfen; meldet auch `short_url` |
| `GET /api/links` | alle Links mit Scan-Zahl und letztem Scan |
| `POST /api/links` `{"target", "label"}` | neuer Link (Code: 6 Zeichen ohne 0/O/1/I/L) |
| `GET` / `POST` / `DELETE /api/links/<CODE>` | lesen, Ziel/Name ändern, löschen (samt Scans) |
| `GET /api/scans/<CODE>?since=YYYY-MM-DD` | einzelne Scans, Zeit in UTC |

Mit `short_url` in der `config.php` tragen alle Links zusätzlich das Feld `url` (die
Adresse für den QR-Code).

## Tracker in WordPress

Die Scans gibt es auch im Browser: das Plugin `wordpress/completionistqr-online-tracker/` zeigt im
WordPress-Admin unter **CompletionistQR Online** die Liste der Links, Kennzahlen und alle Graphen. Es ist
**nur der Tracker**: Links anlegen, Ziel ändern, löschen und QR-Codes gestalten geht
ausschließlich in der App. Das Plugin reicht deshalb nur lesende Aufrufe an den Server
weiter. Es zählt nichts selbst, sondern spricht dieselbe API wie die App; der Server von
oben bleibt also nötig, App und Plugin können ihn gleichzeitig benutzen.

1. Plugin als Zip packen: `python wordpress/build_zip.py` (legt
   `dist/completionistqr-online-tracker.zip` an) oder den Ordner `completionistqr-online-tracker/` selbst zippen.
2. In WordPress **Plugins → Installieren → Plugin hochladen**, die Zip-Datei wählen,
   aktivieren.
3. **CompletionistQR Online → Einstellungen**: Server-Adresse und API-Schlüssel eintragen und speichern.
   Die Seite meldet sofort, ob die Verbindung steht.

Wer die Zugangsdaten nicht in der Datenbank haben will, trägt sie stattdessen in die
`wp-config.php` ein; die Felder in den Einstellungen sind dann gesperrt:

```php
define('QR_ONLINE_SERVER', 'https://qr.example.de');
define('QR_ONLINE_API_KEY', '…');
```

Sicherheit: Der API-Schlüssel bleibt auf dem WordPress-Server. Der Browser ruft nur
`/wp-json/qr-online/v1/…` auf, und das nur mit Anmeldung als Administrator
(Recht `manage_options`) und gültiger WordPress-Nonce. Das Plugin reicht die Aufrufe dann
mit dem Schlüssel an den QR-Server weiter. Auf der WordPress-Startseite zeigt ein kleines
Widget die fünf meistgescannten Links (5 Minuten zwischengespeichert).

Die Graphen zählen nach der Zeitzone des Browsers, wie die App nach der von Windows.
Voraussetzung: WordPress 6.0 und PHP 8.0 oder neuer; die Seite funktioniert mit und ohne
„schöne“ Permalinks.

## Starten

- **Installiert:** `CompletionistQR-Online-Setup-<Version>.exe`, ohne Adminrechte.
- **Aus dem Quellcode** (venv der Suite, siehe Haupt-README):

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m qronline
```

## Entwicklung

```powershell
..\.venv\Scripts\python.exe -m pip install pytest pyinstaller
..\.venv\Scripts\python.exe -m pytest tests      # Server-Tests brauchen php im PATH
..\.venv\Scripts\python.exe build_exe.py         # dist\CompletionistQR-Online\ (Programmordner)
.\build_setup.ps1                                # Ordner + Setup (Inno Setup 6)
..\.venv\Scripts\python.exe tools\make_icon.py   # Programmsymbol neu erzeugen (assets\)
```

Die Server-Tests starten `server/index.php` mit dem eingebauten PHP-Server und gehen den
ganzen Weg: Link anlegen, scannen mit iPhone-, Android- und Windows-Kennung, Statistik
abrufen, Ziel ändern, löschen. Ohne PHP werden sie übersprungen.

Aufbau: `server/index.php` (Weiterleitung und API, eine Datei),
`wordpress/completionistqr-online-tracker/` (WordPress-Plugin, nur Anzeige; PHP und JavaScript ohne Build-Schritt), `qronline/client.py`
(API-Aufrufe), `qronline/stats.py` (Auswertung nach lokaler Zeit), `qronline/charts.py`
(Diagramme mit matplotlib), `qronline/design.py` (Fenster „QR-Code gestalten“ mit dem
Gestalter aus `completionistqr`), `qronline/app.py` (Oberfläche, CustomTkinter),
`qronline/settings.py` (Einstellungen unter `%APPDATA%\CompletionistQR Online`, der API-Schlüssel per
Windows-DPAPI verschlüsselt).

**Schneller Start:** Verteilt wird ein Programmordner statt einer einzelnen .exe, so wird
beim Start nichts entpackt. matplotlib lädt erst, wenn das Fenster schon steht. Die
Netzwerkaufrufe laufen im Hintergrund, die Oberfläche bleibt bedienbar.
