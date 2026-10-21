# Fremdkomponenten

Diese Komponenten gehören nicht zum eigenen Code und stehen unter ihren eigenen
Lizenzen. Sie sind von der Lizenz in `LICENSE` ausgenommen.

## Im Repository enthalten

| Komponente | Wo | Lizenz |
| :--- | :--- | :--- |
| Tiptap, ProseMirror (gebündelt) | `assets/editor/tiptap.bundle.js` (Lizenzhinweise am Dateiende) | MIT |
| Inter, Montserrat, Poppins, Oswald, Bebas Neue, Anton, Playfair Display, Lora, Roboto Mono, Caveat | `completionistqr/assets/fonts/` (je `OFL.txt`) | SIL Open Font License 1.1 |

## Benutzte Bibliotheken (über `requirements.txt`, in den Setups enthalten)

| Bibliothek | Benutzt von | Lizenz |
| :--- | :--- | :--- |
| PyQt6, PyQt6-WebEngine | PDF, MD | GPL v3 (oder kommerzielle Lizenz von Riverbank) |
| Qt 6 / Qt WebEngine (Chromium) | PDF, MD | LGPL v3 / GPL; Chromium: BSD u. a. |
| typst (Python) | PDF | Apache 2.0 |
| markdown-it-py, mdit-py-plugins | PDF | MIT |
| google-auth, google-auth-oauthlib | MD, QR | Apache 2.0 |
| requests | MD, QR | Apache 2.0 |
| Pillow | QR | MIT-CMU (HPND) |
| qrcode | QR | BSD |
| customtkinter | QR | MIT |
| zxing-cpp | QR | Apache 2.0 |
| Python | alle | PSF License |
| PyInstaller (nur zum Bauen; Bootloader in den .exe) | alle | GPL v2 mit Ausnahme für gebaute Programme |
