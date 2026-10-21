<?php
/*
 * QR-Online – Weiterleitung mit Scan-Zaehlung.
 *
 *   GET  /<CODE>                 zaehlt den Scan und leitet zum Ziel weiter (302)
 *   GET  /api/ping               prueft den API-Schluessel
 *   GET  /api/links              alle Links mit Scan-Zahl
 *   POST /api/links              {"target": "...", "label": "..."} -> neuer Link
 *   GET  /api/links/<CODE>       ein Link
 *   POST /api/links/<CODE>       {"target"?, "label"?} -> Ziel/Name aendern
 *   DELETE /api/links/<CODE>     Link samt Scans loeschen
 *   GET  /api/scans/<CODE>?since=YYYY-MM-DD   einzelne Scans (Zeit in UTC)
 *
 * Die API verlangt den Schluessel aus config.php im Kopf "X-Api-Key".
 * Pro Scan werden nur Zeitpunkt, Geraetetyp, Betriebssystem und Browsersprache
 * gespeichert -- keine IP-Adresse, keine Cookies.
 */

declare(strict_types=1);

const CODE_ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'; // ohne 0/O, 1/I/L
const CODE_LENGTH = 6;
// Vorschau-Abrufe von Messengern und Suchmaschinen sind keine Scans
const BOT_PATTERN = '/bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|telegram|'
    . 'slack|discord|skype|curl|wget|python-requests|headless/i';

$config = require __DIR__ . '/config.php';

function db(array $config): PDO
{
    $dir = dirname($config['db']);
    if (!is_dir($dir)) {
        mkdir($dir, 0700, true);
    }
    // Bei gleichzeitigen Scans bis zu 5 s auf die Sperre warten statt abzubrechen
    $pdo = new PDO('sqlite:' . $config['db'], null, null,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_TIMEOUT => 5]);
    $pdo->exec('PRAGMA journal_mode = WAL');
    $pdo->exec('PRAGMA foreign_keys = ON');
    $pdo->exec('CREATE TABLE IF NOT EXISTS links (
        code TEXT PRIMARY KEY, target TEXT NOT NULL, label TEXT NOT NULL DEFAULT "",
        created TEXT NOT NULL)');
    $pdo->exec('CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY, code TEXT NOT NULL REFERENCES links(code) ON DELETE CASCADE,
        ts TEXT NOT NULL, device TEXT NOT NULL, os TEXT NOT NULL, lang TEXT NOT NULL)');
    $pdo->exec('CREATE INDEX IF NOT EXISTS scans_code_ts ON scans(code, ts)');
    return $pdo;
}

function now_utc(): string
{
    return gmdate('Y-m-d\TH:i:s\Z');
}

function json_out(int $status, $data): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function fail(int $status, string $message): void
{
    json_out($status, ['error' => $message]);
}

function classify(string $ua): array
{
    if (preg_match('/iPhone|iPad|iPod/i', $ua)) {
        $os = 'iOS';
    } elseif (stripos($ua, 'Android') !== false) {
        $os = 'Android';
    } elseif (stripos($ua, 'Windows') !== false) {
        $os = 'Windows';
    } elseif (stripos($ua, 'Macintosh') !== false) {
        $os = 'macOS';
    } elseif (preg_match('/Linux|CrOS/i', $ua)) {
        $os = 'Linux';
    } else {
        $os = 'Sonstige';
    }
    if (preg_match('/iPad|Tablet/i', $ua) || ($os === 'Android' && stripos($ua, 'Mobile') === false)) {
        $device = 'Tablet';
    } elseif (preg_match('/Mobi|iPhone|iPod|Android/i', $ua)) {
        $device = 'Smartphone';
    } else {
        $device = 'Computer';
    }
    return [$device, $os];
}

function language(string $header): string
{
    return preg_match('/^\s*([a-z]{2})/i', $header, $m) ? strtolower($m[1]) : '';
}

function valid_target(string $url): bool
{
    return strlen($url) <= 2000 && preg_match('#^https?://[^\s/?\#]+#i', $url) === 1
        && filter_var($url, FILTER_VALIDATE_URL) !== false;
}

function new_code(PDO $pdo): string
{
    $check = $pdo->prepare('SELECT 1 FROM links WHERE code = ?');
    do {
        $code = '';
        for ($i = 0; $i < CODE_LENGTH; $i++) {
            $code .= CODE_ALPHABET[random_int(0, strlen(CODE_ALPHABET) - 1)];
        }
        $check->execute([$code]);
    } while ($check->fetchColumn());
    return $code;
}

function link_row(PDO $pdo, string $code): ?array
{
    $q = $pdo->prepare('SELECT l.code, l.target, l.label, l.created,
            COUNT(s.id) AS scans, MAX(s.ts) AS last_scan
        FROM links l LEFT JOIN scans s ON s.code = l.code WHERE l.code = ? GROUP BY l.code');
    $q->execute([$code]);
    $row = $q->fetch(PDO::FETCH_ASSOC);
    if (!$row) {
        return null;
    }
    $row['scans'] = (int)$row['scans'];
    return $row;
}

function body(): array
{
    $data = json_decode((string)file_get_contents('php://input'), true);
    return is_array($data) ? $data : [];
}

function handle_redirect(PDO $pdo, string $code, array $config): void
{
    $q = $pdo->prepare('SELECT target FROM links WHERE code = ?');
    $q->execute([$code]);
    $target = $q->fetchColumn();
    if ($target === false) {
        http_response_code(404);
        header('Content-Type: text/plain; charset=utf-8');
        echo "Dieser QR-Code ist nicht (mehr) vergeben.\n";
        exit;
    }
    $ua = $_SERVER['HTTP_USER_AGENT'] ?? '';
    if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'GET' && $ua !== '' && !preg_match(BOT_PATTERN, $ua)) {
        [$device, $os] = classify($ua);
        try {
            $pdo->prepare('INSERT INTO scans (code, ts, device, os, lang) VALUES (?, ?, ?, ?, ?)')
                ->execute([$code, now_utc(), $device, $os, language($_SERVER['HTTP_ACCEPT_LANGUAGE'] ?? '')]);
        } catch (Throwable $e) {
            // Lieber einen Scan nicht zaehlen, als den Besucher nicht weiterzuleiten
            error_log('QR-Online: Scan nicht gespeichert: ' . $e->getMessage());
        }
    }
    // 302 und no-store: sonst merkt sich der Browser das Ziel und spaetere Scans fehlen
    header('Cache-Control: no-store');
    header('Location: ' . $target, true, 302);
    exit;
}

function handle_api(PDO $pdo, array $parts, string $method, array $config): void
{
    $key = $_SERVER['HTTP_X_API_KEY'] ?? '';
    if (!is_string($config['api_key'] ?? null) || strlen($config['api_key']) < 16
            || str_starts_with($config['api_key'], 'HIER-')) {
        fail(500, 'In config.php ist noch kein API-Schlüssel eingetragen.');
    }
    if (!hash_equals($config['api_key'], $key)) {
        fail(401, 'API-Schlüssel fehlt oder ist falsch.');
    }
    $what = $parts[0] ?? '';
    $code = strtoupper($parts[1] ?? '');

    if ($what === 'ping') {
        json_out(200, ['ok' => true, 'time' => now_utc()]);
    }
    if ($what === 'links' && $code === '') {
        if ($method === 'GET') {
            $rows = $pdo->query('SELECT l.code, l.target, l.label, l.created,
                    COUNT(s.id) AS scans, MAX(s.ts) AS last_scan
                FROM links l LEFT JOIN scans s ON s.code = l.code
                GROUP BY l.code ORDER BY l.created DESC')->fetchAll(PDO::FETCH_ASSOC);
            foreach ($rows as &$r) {
                $r['scans'] = (int)$r['scans'];
            }
            json_out(200, $rows);
        }
        if ($method === 'POST') {
            $in = body();
            $target = trim((string)($in['target'] ?? ''));
            if (!valid_target($target)) {
                fail(400, 'Das Ziel muss eine Adresse mit http:// oder https:// sein.');
            }
            $code = new_code($pdo);
            $pdo->prepare('INSERT INTO links (code, target, label, created) VALUES (?, ?, ?, ?)')
                ->execute([$code, $target, mb_substr(trim((string)($in['label'] ?? '')), 0, 200), now_utc()]);
            json_out(201, link_row($pdo, $code));
        }
        fail(405, 'Methode nicht erlaubt.');
    }
    if (($what === 'links' || $what === 'scans') && $code !== '') {
        $link = link_row($pdo, $code);
        if ($link === null) {
            fail(404, 'Diesen Code gibt es nicht.');
        }
        if ($what === 'scans' && $method === 'GET') {
            $since = (string)($_GET['since'] ?? '');
            if ($since !== '' && !preg_match('/^\d{4}-\d{2}-\d{2}/', $since)) {
                fail(400, 'since erwartet ein Datum wie 2026-10-01.');
            }
            $q = $pdo->prepare('SELECT ts, device, os, lang FROM scans
                WHERE code = ? AND ts >= ? ORDER BY ts');
            $q->execute([$code, $since]);
            json_out(200, $q->fetchAll(PDO::FETCH_ASSOC));
        }
        if ($what === 'links' && $method === 'GET') {
            json_out(200, $link);
        }
        if ($what === 'links' && ($method === 'POST' || $method === 'PATCH')) {
            $in = body();
            if (array_key_exists('target', $in)) {
                $target = trim((string)$in['target']);
                if (!valid_target($target)) {
                    fail(400, 'Das Ziel muss eine Adresse mit http:// oder https:// sein.');
                }
                $pdo->prepare('UPDATE links SET target = ? WHERE code = ?')->execute([$target, $code]);
            }
            if (array_key_exists('label', $in)) {
                $pdo->prepare('UPDATE links SET label = ? WHERE code = ?')
                    ->execute([mb_substr(trim((string)$in['label']), 0, 200), $code]);
            }
            json_out(200, link_row($pdo, $code));
        }
        if ($what === 'links' && $method === 'DELETE') {
            $pdo->prepare('DELETE FROM links WHERE code = ?')->execute([$code]);
            json_out(200, ['deleted' => $code]);
        }
        fail(405, 'Methode nicht erlaubt.');
    }
    fail(404, 'Unbekannte Anfrage.');
}

// ---------------------------------------------------------------- Routing

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
// Liegt das Skript in einem Unterordner (z. B. /qr/index.php), den Ordner abschneiden
$base = rtrim(str_replace('\\', '/', dirname($_SERVER['SCRIPT_NAME'] ?? '/')), '/');
if ($base !== '' && str_starts_with($path, $base . '/')) {
    $path = substr($path, strlen($base));
}
$path = trim(preg_replace('#^/index\.php#', '', $path), '/');
$parts = $path === '' ? [] : explode('/', $path);

try {
    $pdo = db($config);
    if (($parts[0] ?? '') === 'api') {
        handle_api($pdo, array_slice($parts, 1), $method, $config);
    }
    // Ohne URL-Umschreibung (mod_rewrite) geht auch index.php?c=CODE
    $code = strtoupper((string)($parts[0] ?? ($_GET['c'] ?? '')));
    if (count($parts) <= 1 && preg_match('/^[' . CODE_ALPHABET . ']{' . CODE_LENGTH . '}$/', $code)) {
        handle_redirect($pdo, $code, $config);
    }
    if (!empty($config['home'])) {
        header('Location: ' . $config['home'], true, 302);
        exit;
    }
    http_response_code(404);
    header('Content-Type: text/plain; charset=utf-8');
    echo "Nicht gefunden.\n";
} catch (Throwable $e) {
    error_log('QR-Online: ' . $e->getMessage());
    if (($parts[0] ?? '') === 'api') {
        fail(500, 'Serverfehler: ' . $e->getMessage());
    }
    http_response_code(500);
    header('Content-Type: text/plain; charset=utf-8');
    echo "Serverfehler.\n";
}
