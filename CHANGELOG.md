# Änderungen

Jede App der Suite hat ihre eigene Versionsnummer nach dem Muster
*Haupt.Neben.Korrektur*: neue Funktionen erhöhen die mittlere Zahl, reine
Fehlerkorrekturen die letzte. Die Nummer steht an genau einer Stelle und landet
von dort im Setup, im Fenstertitel und in den Dateieigenschaften der `.exe`:

| App | Nummer in |
| :--- | :--- |
| CompletionistPDF | `core/__init__.py` |
| CompletionistMD | `mdeditor/__init__.py` |
| CompletionistQR | `completionistqr/__init__.py` |

CompletionistIMG ist ein eigenes Projekt mit eigenem Änderungsprotokoll. QR-Online
(Ordner `QR-Online/`) zählt die Version in `QR-Online/qronline/__init__.py`.

## 27.10.2026 – QR-Online 1.1.0, Tracker-Plugin 1.1.0 – Gestalter von CompletionistQR, kurze Domain

### QR-Online 1.1.0 – derselbe Gestalter wie CompletionistQR
* **„QR-Code gestalten und speichern …"** öffnet den Gestalter von CompletionistQR mit dem
  Kurzlink als festem Inhalt: Vorlagen, Formen, Farben, Verläufe, Logo, Rahmen,
  Beschriftung, Scan-Prüfung, Export als PNG, SVG oder PDF und in die Zwischenablage.
  Bisher gab es nur ein schlichtes PNG.
* Kein Nachbau: Bedienleiste, Vorschau und Fensterlogik liegen einmal im Paket
  `completionistqr` (`completionistqr/ui/designer.py`), CompletionistQR und QR-Online nutzen
  denselben Code. Was CompletionistQR künftig lernt, kann QR-Online damit automatisch auch.
* Das Design merkt sich QR-Online je Link; ein neuer Link beginnt mit dem zuletzt benutzten.
* **Fenster „Über QR-Online"** (ⓘ bzw. F1) wie in CompletionistQR: Version, Lizenz,
  Fremdkomponenten, Impressum, App-Icon, klickbare Links.

### QR-Online-Server und Tracker-Plugin 1.1.0 – eigene kurze Domain, nur noch Anzeige
* Neu in `config.php`: `'short_url' => 'https://c10t.de'`. Der Server liefert dann bei jedem
  Link die kurze Adresse für den QR-Code mit; App und WordPress-Plugin übernehmen sie von
  selbst. Gezählt und weitergeleitet wird unter jeder Adresse, die auf den Server-Ordner
  zeigt – schon gedruckte Codes bleiben gültig.
* **Das WordPress-Plugin ist nur noch der Tracker** (bisher nur auf einem Branch, jetzt in
  `main`): Links, Kennzahlen und Graphen ansehen. Anlegen, Ändern, Löschen und den
  QR-Code-Export gibt es dort nicht mehr – das geht ausschließlich in der App. Der REST-Proxy
  des Plugins reicht nur noch lesende Aufrufe an den Server weiter; die mitgelieferte
  JavaScript-QR-Bibliothek entfällt.

## 27.10.2026 – MD 1.6.0, QR 1.4.1 – Quellcode-Ansicht, schnellere große Guides

### CompletionistMD 1.6.0 – Quellcode und Nebeneinander-Ansicht
* **Quellcode-Ansicht** (Strg + Umschalt + M): der reine Markdown-Text zum Lesen und
  Bearbeiten. Formatknöpfe, Emojis, Suchen und Ersetzen wirken dort ebenfalls.
* **Nebeneinander** (Strg + Umschalt + D): links Vault, Bookmarks und Gliederung, in der
  Mitte der WYSIWYG-Editor, rechts der Quellcode; **⇄** tauscht die beiden Seiten. Beide
  gleichen sich nach 200 ms Tipp-Pause ab. Aus dem Quellcode werden nur die Absätze um die
  Änderung neu gelesen, der Schritt ist im Editor rückgängig zu machen. Ein Klick in der
  Gliederung springt in beiden Seiten, der Quellcode folgt dem Kapitel im Editor. Ansicht
  und Seite bleiben über einen Neustart erhalten.

### CompletionistMD 1.6.0 – Große Guides
Gemessen mit einem Guide aus 300 Kapiteln (rund 1 MB Markdown):
* **Öffnen** rund doppelt so schnell (3,0 s → 1,5 s): das Laden läuft nicht mehr durch alle
  Editor-Erweiterungen, und Absätze außerhalb des Sichtfelds setzt Chromium erst beim
  Hinscrollen (`content-visibility`; umflossene Bilder bleiben ausgenommen).
* **Tippen** spürbar flüssiger: Markdown, Wortzahl, Gliederung und die Syntax-Anzeige
  werden je Absatz gemerkt statt bei jeder Taste für das ganze Dokument neu berechnet
  (Markdown nach einem Tastendruck: 340 ms → 6 ms, Tastendruck selbst: 50–70 ms → 20 ms).

### CompletionistQR 1.4.1
* **SVG: die Schrift des Titels kommt überall an.** Die Beschriftung steht jetzt wie im PDF
  als Schriftkontur im SVG; die eingebettete Schrift zeigten nur Browser an.
* **„Über CompletionistQR" zeigt das App-Icon** in der Titelleiste (CustomTkinter setzte
  dort sein eigenes).
* **Links im Fenster „Über" sind klickbar**: E-Mail-Adresse, GitHub und alle Webadressen
  in Lizenz, Fremdkomponenten und Impressum.

### Fehlerkorrekturen
* **CompletionistMD: Codeblöcke, die selbst ` ``` ` enthalten, überstehen das Neuladen.**
  Der Editor schreibt sie mit längerem Zaun (` ```` `), las sie aber schon am ersten
  ` ``` ` als beendet.

## 26.10.2026 – QR-Online: Web-Dashboard für WordPress

### QR-Online-Dashboard 1.0.0 (WordPress-Plugin)
* **Neues Plugin** `QR-Online/wordpress/qr-online-dashboard/`: das Dashboard der
  QR-Online-App im WordPress-Admin – Links anlegen, Ziel und Namen ändern, löschen,
  Kennzahlen, Graphen (pro Tag/Woche, Uhrzeit, Wochentag, Gerät, Betriebssystem, Sprache),
  QR-Code als PNG, Link kopieren, Suche in der Liste. Funktioniert auch am Smartphone.
* Spricht dieselbe API wie die App; der API-Schlüssel bleibt auf dem WordPress-Server
  (Einstellungsseite oder `wp-config.php`), nur Administratoren sehen das Dashboard.
* Widget auf der WordPress-Startseite mit den fünf meistgescannten Links.

## 25.10.2026 – PDF 1.5.0, MD 1.5.0, QR 1.4.0 – Startbild und Impressum

### CompletionistPDF 1.5.0, CompletionistMD 1.5.0, CompletionistQR 1.4.0
* **Startbild beim Programmstart.** Jede App zeigt rund 1,2 Sekunden ihr eigenes
  Bild (`assets/splash_pdf.jpg`, `assets/splash_md.jpg`,
  `completionistqr/assets/splash.jpg`); das Hauptfenster wird in der Zeit schon
  aufgebaut und erscheint danach.
* **„Über …" zeigt das App-Bild** links neben den Reitern, bei jedem Reiter.
* **Neuer Reiter „Impressum"** im Fenster „Über …" mit Kontakt (E-Mail, GitHub) und
  dem Hinweis, dass die Apps ein privates, kostenloses Freizeitprojekt sind
  (Texte in `core/legal.py`). CompletionistQR zeigt Lizenz, Fremdkomponenten und
  Impressum jetzt ebenfalls in Reitern.
* **Kontakt-Adresse** ist jetzt überall kontakt@completionist-library.de (Über-Dialog,
  Setups, Dateieigenschaften der `.exe`, LICENSE, README).

### CompletionistMD 1.5.0 – Vault-Explorer
* **Einfachklick öffnet auch Bilder, Textdateien und PDFs** – in einem Vorschau-Tab,
  den der nächste Einfachklick ersetzt. Doppelklick öffnet wie bisher einen eigenen
  Tab (auch für eine Datei, die gerade in der Vorschau steht).
* **„Öffnen" im Kontextmenü für alle unterstützten Dateitypen** öffnet die Datei mit
  dem Standardprogramm des Systems; dazu „Hier öffnen" und „In neuem Tab öffnen".
* **Ordner klappen mit einem Klick auf und zu.**
* **Gliederung von Anfang an sichtbar** (ausblenden wie bisher mit ☰ bzw.
  Strg+Umschalt+G) und **hebt das aktuelle Kapitel hervor**: nach Tippen, Klicken
  oder einem Sprung die Überschrift am Cursor, beim Scrollen die oberste im
  Sichtfeld, solange der Cursor nicht zu sehen ist.

### CompletionistPDF 1.5.0, CompletionistMD 1.5.0 – Text in PDFs markieren
* **Text in PDFs markieren und kopieren** – in der Vorschau und im Reader von
  CompletionistPDF sowie im PDF-Tab von CompletionistMD: Ziehen markiert (auch über
  Seitengrenzen), Doppelklick ein Wort, Dreifachklick eine Zeile, Strg+A alles,
  Strg+C oder Rechtsklick → „Kopieren“, Esc bzw. ein Klick hebt die Auswahl auf.
  Auf Links folgt ein Klick weiterhin, Ziehen markiert auch dort. Beim Kopieren
  wird Silbentrennung wieder zum ganzen Wort, Emojis bleiben in ihrem Satz
  (`core/pdf_select.py`).

### Fehlerkorrekturen
* **PDF-Viewer: „keine Treffer" statt dauerhaft „sucht …".** Qt-Timer dürfen bis zu
  5 % zu früh auslösen; dann blieb bei einer Suche ohne Treffer „sucht …" stehen.
  Das Label plant sich jetzt für die Restzeit neu ein.
* **CompletionistMD: kein Absturz mehr durch den Drag&Drop-Filter.** Der Filter
  hing an der ganzen Anwendung und zwang PySide, für jedes interne QtQuick-Objekt
  von QtWebEngine einen Python-Wrapper zu bauen -- das löste neue Events aus, bis der
  Stapel überlief. Er sitzt jetzt nur noch auf den Kindwidgets des Editors.

## 25.10.2026 – PDF 1.4.2 – Linie unter Überschrift 2

### CompletionistPDF 1.4.2
* **`##`-Überschriften haben im PDF eine Linie darunter**, wie CompletionistMD sie
  anzeigt. Neue Einstellung unter Schriften & Typografie: „Linie unter Überschrift 2"
  (an in allen mitgelieferten Vorlagen; ältere eigene Vorlagen bekommen sie ebenfalls).

## 25.10.2026 – MD 1.4.3 – Kein verirrtes „\“ vor Überschriften und Listen

### CompletionistMD 1.4.3
* **Kein `\##` bzw. `\-` mehr vor Überschriften und Aufzählungen.** Zwei Wege führten
  dahin: Rauten einer Überschrift löschen, die Zeile verlassen und mit Strg+Z
  zurückholen (die Rauten landeten als Text im inzwischen normalen Absatz bzw. vor
  dem Titel, z. B. `#Titel`), und `- `, `1. `, `- [ ] ` oder `> ` vor einem
  formatierten Zeilenanfang tippen (`- **Begriff**: …`), wo die Listenerkennung nicht
  griff. Solche Syntax am Absatzanfang wird jetzt beim Verlassen der Zeile zur
  Überschrift, Liste, Aufgabe bzw. zum Zitat und schließt an eine Liste direkt davor an.
  Wer wirklich einen Strich als Text will, tippt `\- ` oder macht die
  Listenerkennung sofort mit Strg+Z rückgängig. In Tabellenzellen bleibt alles Text.

## 25.10.2026 – MD 1.4.2 – Speichern nur bei Änderungen

### CompletionistMD 1.4.2
* **Gespeichert wird nur noch, wenn sich die Datei wirklich ändert.** Bisher löste
  schon ein Klick in den Text das Auto-Save aus (das Auf- und Zuklappen der
  Markdown-Syntax ändert intern das Dokument), und beim Schließen oder Wechseln
  wurde die Datei neu formatiert geschrieben, auch ohne Änderung. Jetzt vergleicht
  der Editor das Markdown mit dem gespeicherten Stand; Klicken und Lesen lassen die
  Datei samt Zeitstempel und Drive-Sync in Ruhe.
* **`## **Überschrift**` verliert die Rauten nicht mehr.** Ein Klick in eine
  Überschrift, die ganz fett (oder kursiv, als Link …) ist, und wieder heraus machte
  aus ihr einen normalen Absatz.
* **Vault-Explorer: „Öffnen" für PDFs** im Kontextmenü öffnet die Datei im
  Standardprogramm des Systems.

## 21.10.2026 – PDF 1.4.1 · MD 1.4.1 · QR 1.3.0 – Qualität vor Größe

Neuer Grundsatz der Suite: Qualität hat Vorrang vor Programmgröße. Was bisher zugunsten
der Größe wegfiel und sichtbar schlechter war, ist zurück.

### CompletionistPDF 1.4.1 · CompletionistMD 1.4.1
* **Qt-Dialoge auf Deutsch.** Knöpfe wie Ja/Nein/OK/Abbrechen/Schließen und die
  Kontextmenüs der Textfelder (Kopieren, Einfügen …) erschienen auf Englisch, weil die
  Qt-Übersetzungen nicht mitgepackt und nicht geladen wurden. Jetzt lädt
  `core/qt_translations.py` sie in der Systemsprache; MD auch die der Editor-Ansicht.
* **PDF: Drucken mit bis zu 600 dpi** statt 300 dpi, für scharfe Schrift auf Laserdruckern.

### CompletionistQR 1.3.0
* **PDF-Export als echte Vektorgrafik** statt eines eingebetteten Rasterbilds: Module,
  Augen, Rahmen und Farbverläufe als Pfade, die Beschriftung als Schriftkontur (gesetzt mit
  HarfBuzz, samt Unterschneidung), das Logo in Originalauflösung. In jeder Druckgröße
  randscharf, keine Schriftabhängigkeit. Neue Abhängigkeit: `uharfbuzz`.
* **Behoben: Stil „Abgerundet (fließend)“ mit falschen Ecken** in PNG, Vorschau,
  Zwischenablage und Stapel-Export. Bei Radius = halbe Modulbreite landeten eckige Ecken
  auf der falschen Seite; statt durchgehender Bahnen gab es Kerben und halbe Kappen.
  Betraf den Modulstil „Abgerundet“ (Vorlagen „Rounded Soft“, „Scan-Me Banner“,
  „Midnight“) und die Pupille „Blatt“ („Neon Gradient“).
* **Behoben: Schlitze im SVG**, wo sich Formen überlappen (z. B. Augen-Pupille „Punkte“,
  Rauten-Spitzen). Das SVG füllte nach evenodd; jetzt nach nonzero wie Pillow, aus
  derselben Kontur wie das PDF.
* **Scharfe Vorschau bei Windows-Skalierung** (125 %, 150 % …). Vorschau und
  Vorlagen-Galerie werden in echten Bildschirmpixeln gerendert, statt hochgezogen zu werden.
* **Logos auch als AVIF.** Der AVIF-Decoder von Pillow wurde bisher aus Platzgründen
  weggelassen und ist wieder dabei.
* Build: `PIL._tkinter_finder` wird ausdrücklich mitgepackt. Ohne stürzte der gebaute
  Programmordner (geprüft unter Linux) beim Aufbau der Vorlagen-Galerie ab.

## 21.10.2026 – QR-Online 1.0.0

* **Neues Projekt QR-Online:** QR-Codes mit Scan-Statistik. Der Code enthält einen kurzen
  Link auf den eigenen Webspace; `server/index.php` (PHP + SQLite) zählt jeden Scan und
  leitet weiter. Gespeichert werden nur Zeit, Gerätetyp, Betriebssystem und Sprache, keine
  IP-Adresse. Die App zeigt Scans pro Tag/Woche, Uhrzeit, Wochentag, Gerät, Betriebssystem
  und Sprache als Graphen (matplotlib). Das Ziel eines Links lässt sich nachträglich ändern.
* Eigenes Programmsymbol im Stil der Suite (Violett, mit Balkendiagramm), erzeugt von
  `QR-Online/tools/make_icon.py`.

## 21.10.2026 – PDF 1.4.0 · MD 1.4.0 · QR 1.2.0

### Alle Apps
* **Über … / Lizenzen** (ⓘ bzw. F1): Version, Copyright, Lizenz, Fremdkomponenten.
  Die Setups legen einen Ordner `Lizenzen` mit allen Lizenztexten an.
* Herausgeber in Setup und Dateieigenschaften: „Completionist Library“,
  © 2026 Mike-Dominique Horch (Completionist Library).

### CompletionistPDF 1.4.0 · CompletionistMD 1.4.0
* **Umstieg von PyQt6 (GPL v3) auf PySide6 (LGPL v3)**: Damit lässt sich der eigene
  Code unter CC BY-NC-ND 4.0 veröffentlichen. Bedienung und Funktionen unverändert.

### CompletionistQR 1.2.0
* **Datei in Google Drive hochladen** beim Inhaltstyp „PDF, Bild oder Video“: lädt die
  Datei hoch, gibt sie für „Jeder mit dem Link“ frei und setzt den Link in den Code.

## 21.10.2026 – PDF 1.3.0 · MD 1.3.0 · QR 1.1.0

### CompletionistMD 1.3.0

**Neu**
* **Suchen und Ersetzen** (Strg + F / Strg + H) im Markdown- und Text-Tab, Treffer
  markiert, F3 / Umschalt + F3 springen weiter.
* **Im Vault suchen** (Strg + Umschalt + F): Volltextsuche über alle Notizen.
* **Gliederung** als zweite Seitenleiste links (☰, Strg + Umschalt + G).
* **Dateien zusammenführen**: mehrere `.md` im Vault markieren → eine neue Datei,
  getrennt durch `***` (Seitenumbruch im PDF); Bildpfade werden umgerechnet.
* **Ältere Fassungen**: beim Speichern höchstens alle 10 Minuten eine Sicherung in
  `.completionistmd/verlauf/`, ansehen und wiederherstellen über *Datei ▾*.
* **Zuletzt geöffnet** im Menü *Datei ▾*.
* **Mehrere Fenster**: Ändert ein anderes Fenster dieselbe Datei, lädt der Tab neu
  oder fragt bei eigenen ungespeicherten Änderungen nach.
* Version im Fenstertitel.

**Korrigiert**
* **Strg + V mit Bild** landet jetzt zuverlässig in `images/` (QtWebEngine hatte die
  Taste geschluckt).
* **Speichern ausfallsicher**: erst Zwischendatei, dann Ersetzen – nie mehr eine leere
  oder halbe Notiz nach einem Absturz.
* **Dateizuordnung**: Das Setup registriert `.md` mit Icon und löscht einen veralteten
  Benutzer-Schlüssel, der „Öffnen mit“ in eine Endlosschleife schickte.

### CompletionistPDF 1.3.0

**Neu**
* **Drucken** (Strg + P) im Viewer und für die Vorschau.
* **Zuletzt ▾** mit den letzten 15 Dateien.
* **Zusammenführen …** mehrerer Markdown-Dateien (wie in MD).
* Version im Fenstertitel.

**Korrigiert**
* Eine Zeile, die mit „Zahl + Punkt“ beginnt („…↵3. Platz“), wurde im PDF zur
  nummerierten Liste.
* Fehlende Bilder wurden im Protokoll doppelt gemeldet.
* Der Emoji-Test fror das Fenster kurz ein; ein zweiter wartender Export ging verloren.
* Setup: derselbe Schutz gegen einen veralteten „Öffnen mit“-Schlüssel wie bei MD.

### CompletionistQR 1.1.0

**Neu**
* Inhaltstypen **Zahlung** (SEPA-GiroCode mit IBAN-Prüfung oder PayPal.me),
  **WhatsApp**, **Social Media**, **App-Link**, **Feedback** und **PDF, Bild oder
  Video** – dort auch mit Upload der Datei nach Google Drive und Freigabe-Link.
* **Standort** als Kartenlink (öffnet auch auf dem iPhone) oder per Adresse.
* **In die Zwischenablage kopieren** (Strg + C) und **Stapel-Export** aus einer
  CSV-Liste.
* **Logo** per Drag & Drop oder Strg + V.
* Design, Inhaltstyp und Eingaben bleiben bis zum nächsten Start erhalten.
* Warnung vor dem Speichern, wenn der Code die Scan-Prüfung nicht besteht.

## Frühere Versionen

PDF 1.2.0, MD 1.2.1 und QR 1.0.0 (19.10.2026) sind die ersten Setup-Versionen; für
sie gibt es kein ausführliches Protokoll.
