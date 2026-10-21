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

CompletionistIMG ist ein eigenes Projekt mit eigenem Änderungsprotokoll.

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
