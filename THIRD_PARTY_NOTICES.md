# Fremdkomponenten

Diese Komponenten gehören nicht zum eigenen Code und stehen unter ihren eigenen
Lizenzen. Sie sind von der Lizenz in `LICENSE` ausgenommen.

## Im Repository enthalten

| Komponente | Wo | Lizenz |
| :--- | :--- | :--- |
| Tiptap, ProseMirror (gebündelt) | `assets/editor/tiptap.bundle.js` (Lizenzhinweise am Dateiende) | MIT |
| Lucide Icons (Auswahl, unverändert bzw. eingefärbt) | `assets/icons/lucide/` (`LICENSE.txt`), gerastert in `completionistqr/assets/icons/` | ISC |
| Inter, Montserrat, Poppins, Oswald, Bebas Neue, Anton, Playfair Display, Lora, Roboto Mono, Caveat | `completionistqr/assets/fonts/` (je `OFL.txt`) | SIL Open Font License 1.1 |

## LGPL v3 (Qt, PySide6)

Qt und PySide6 werden unverändert und dynamisch gelinkt verwendet: Die Bibliotheken liegen
als eigene DLL-/PYD-Dateien im Programmordner (`_internal`) und dürfen durch eigene,
kompatible Fassungen ersetzt werden. Die vollständigen Lizenztexte liegen nach der
Installation im Ordner `Lizenzen` des Programms; der Dialog *Über …* (F1) zeigt diese Liste.

## Benutzte Bibliotheken (über `requirements.txt`, in den Setups enthalten)

| Bibliothek | Benutzt von | Lizenz |
| :--- | :--- | :--- |
| PySide6 (Qt for Python), shiboken6 | PDF, MD | LGPL v3 – Quellcode: https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| Qt 6, Qt WebEngine, Qt PDF | PDF, MD | LGPL v3 – Quellcode: https://download.qt.io/official_releases/qt/ ; Chromium in Qt WebEngine: BSD u. a. (Hinweise in der Qt-Dokumentation) |
| typst (Python) | PDF | Apache 2.0 |
| markdown-it-py, mdit-py-plugins | PDF | MIT |
| google-auth, google-auth-oauthlib | MD, QR | Apache 2.0 |
| requests | MD, QR | Apache 2.0 |
| Pillow | QR | MIT-CMU (HPND) |
| qrcode | QR | BSD |
| customtkinter | QR | MIT |
| zxing-cpp | QR | Apache 2.0 |
| uharfbuzz (mit HarfBuzz) | QR | Apache 2.0 (uharfbuzz), MIT (HarfBuzz) |
| Python | alle | PSF License |
| PyInstaller (nur zum Bauen; Bootloader in den .exe) | alle | GPL v2 mit Ausnahme für gebaute Programme |
