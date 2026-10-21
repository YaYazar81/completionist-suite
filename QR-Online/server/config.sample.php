<?php
// Als config.php neben index.php speichern und den Schluessel eintragen.
// Einen Schluessel erzeugt z. B.:  php -r "echo bin2hex(random_bytes(24));"
return [
    // Muss in QR-Online unter „Server …“ genauso eingetragen werden (mindestens 16 Zeichen)
    'api_key' => 'HIER-EINEN-LANGEN-ZUFALLSSCHLUESSEL-EINTRAGEN',
    // SQLite-Datenbank; der Ordner data/ ist per .htaccess gesperrt
    'db' => __DIR__ . '/data/qronline.sqlite',
    // Wohin die blosse Adresse ohne Code fuehrt ('' = Seite „Nicht gefunden“)
    'home' => '',
];
