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

## 25.10.2026 – MD 1.4.2 – Speichern nur bei Änderungen, fette Überschriften

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
