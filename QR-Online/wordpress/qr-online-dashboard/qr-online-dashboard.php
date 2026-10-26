<?php
/**
 * Plugin Name:       QR-Online Dashboard
 * Description:       Web-Dashboard für QR-Online: Links anlegen und ändern, Scans als Graphen – direkt im WordPress-Admin.
 * Version:           1.0.0
 * Requires at least: 6.0
 * Requires PHP:      8.0
 * Author:            Mike-Dominique Horch (Completionist Library)
 * Author URI:        https://completionist-library.de
 * License:           CC BY-NC-ND 4.0
 * License URI:       https://creativecommons.org/licenses/by-nc-nd/4.0/
 * Text Domain:       qr-online
 */

/*
 * Das Plugin zaehlt nichts selbst. Es spricht die API von QR-Online/server/index.php an
 * (dieselbe wie die Windows-App) und reicht die Antworten an das Dashboard im Browser weiter.
 * Der API-Schluessel bleibt dabei auf dem WordPress-Server; der Browser redet nur mit
 * /wp-json/qr-online/v1/ und braucht dafuer ein angemeldetes Konto mit "manage_options".
 *
 * Statt in den Einstellungen koennen Adresse und Schluessel auch in der wp-config.php stehen:
 *   define('QR_ONLINE_SERVER', 'https://qr.example.de');
 *   define('QR_ONLINE_API_KEY', '...');
 */

defined('ABSPATH') || exit;

const QR_ONLINE_VERSION = '1.0.0';
const QR_ONLINE_CAP = 'manage_options';
const QR_ONLINE_NS = 'qr-online/v1';
const QR_ONLINE_CODE = '[23456789A-HJ-NP-Za-hj-np-z]{6}'; // Alphabet wie in index.php

function qr_online_server(): string
{
    $url = defined('QR_ONLINE_SERVER') ? (string)QR_ONLINE_SERVER : (string)get_option('qr_online_server', '');
    return rtrim(trim($url), '/');
}

function qr_online_key(): string
{
    return trim(defined('QR_ONLINE_API_KEY') ? (string)QR_ONLINE_API_KEY : (string)get_option('qr_online_key', ''));
}

function qr_online_configured(): bool
{
    return qr_online_server() !== '' && qr_online_key() !== '';
}

/**
 * Ein Aufruf der Server-API. Liefert die dekodierte Antwort oder WP_Error mit der Meldung
 * des Servers (die ist schon fuer Menschen geschrieben).
 */
function qr_online_call(string $method, string $path, ?array $body = null, array $query = [])
{
    $base = qr_online_server();
    if (!preg_match('#^https?://#i', $base)) {
        return new WP_Error('qr_online_config', 'Bitte unter „QR-Online → Einstellungen“ die Server-Adresse mit https:// eintragen.', ['status' => 500]);
    }
    $url = $base . '/api/' . $path;
    if ($query) {
        $url = add_query_arg(array_map('rawurlencode', $query), $url);
    }
    $args = [
        'method' => $method,
        'timeout' => 15,
        'redirection' => 0,
        'headers' => ['X-Api-Key' => qr_online_key(), 'Accept' => 'application/json'],
    ];
    if ($body !== null) {
        $args['headers']['Content-Type'] = 'application/json';
        $args['body'] = wp_json_encode($body);
    }
    $response = wp_remote_request($url, $args);
    if (is_wp_error($response)) {
        return new WP_Error('qr_online_unreachable', 'Server nicht erreichbar: ' . $response->get_error_message(), ['status' => 502]);
    }
    $status = (int)wp_remote_retrieve_response_code($response);
    $data = json_decode(wp_remote_retrieve_body($response), true);
    if ($status >= 400 || !is_array($data)) {
        $msg = is_array($data) && isset($data['error']) ? (string)$data['error']
            : "Unerwartete Antwort vom Server (HTTP $status). Liegt index.php unter dieser Adresse?";
        // 401 vom QR-Server nicht als 401 weitergeben, sonst haelt der Browser die WP-Anmeldung fuer abgelaufen
        return new WP_Error('qr_online_server', $msg, ['status' => $status >= 400 && $status !== 401 ? $status : 502]);
    }
    return $data;
}

/** Ergaenzt einen Link um die Adresse, die im QR-Code steht (wie client.short_url). */
function qr_online_with_url(array $row): array
{
    $row['url'] = qr_online_server() . '/' . $row['code'];
    return $row;
}

// ---------------------------------------------------------------- REST-Proxy

add_action('rest_api_init', function () {
    $can = fn() => current_user_can(QR_ONLINE_CAP);
    $code = '(?P<code>' . QR_ONLINE_CODE . ')';

    register_rest_route(QR_ONLINE_NS, '/ping', [
        'methods' => 'GET', 'permission_callback' => $can,
        'callback' => fn() => qr_online_call('GET', 'ping'),
    ]);
    register_rest_route(QR_ONLINE_NS, '/links', [
        ['methods' => 'GET', 'permission_callback' => $can, 'callback' => function () {
            $rows = qr_online_call('GET', 'links');
            return is_wp_error($rows) ? $rows : array_map('qr_online_with_url', $rows);
        }],
        ['methods' => 'POST', 'permission_callback' => $can, 'callback' => function (WP_REST_Request $r) {
            delete_transient('qr_online_widget');
            $row = qr_online_call('POST', 'links', [
                'target' => (string)$r->get_param('target'), 'label' => (string)$r->get_param('label')]);
            return is_wp_error($row) ? $row : new WP_REST_Response(qr_online_with_url($row), 201);
        }],
    ]);
    register_rest_route(QR_ONLINE_NS, '/links/' . $code, [
        ['methods' => 'GET', 'permission_callback' => $can, 'callback' => function (WP_REST_Request $r) {
            $row = qr_online_call('GET', 'links/' . strtoupper($r['code']));
            return is_wp_error($row) ? $row : qr_online_with_url($row);
        }],
        ['methods' => 'POST', 'permission_callback' => $can, 'callback' => function (WP_REST_Request $r) {
            $in = [];
            foreach (['target', 'label'] as $field) {
                if ($r->has_param($field)) {
                    $in[$field] = (string)$r->get_param($field);
                }
            }
            $row = qr_online_call('POST', 'links/' . strtoupper($r['code']), $in);
            return is_wp_error($row) ? $row : qr_online_with_url($row);
        }],
        ['methods' => 'DELETE', 'permission_callback' => $can, 'callback' => function (WP_REST_Request $r) {
            delete_transient('qr_online_widget');
            return qr_online_call('DELETE', 'links/' . strtoupper($r['code']));
        }],
    ]);
    register_rest_route(QR_ONLINE_NS, '/scans/' . $code, [
        'methods' => 'GET', 'permission_callback' => $can,
        'args' => ['since' => ['type' => 'string', 'pattern' => '^\d{4}-\d{2}-\d{2}$', 'required' => false]],
        'callback' => function (WP_REST_Request $r) {
            $since = (string)$r->get_param('since');
            return qr_online_call('GET', 'scans/' . strtoupper($r['code']), null, $since !== '' ? ['since' => $since] : []);
        },
    ]);
});

// ---------------------------------------------------------------- Admin-Seiten

add_action('admin_menu', function () {
    add_menu_page('QR-Online', 'QR-Online', QR_ONLINE_CAP, 'qr-online', 'qr_online_dashboard_page',
        'dashicons-chart-bar', 26);
    add_submenu_page('qr-online', 'QR-Online – Dashboard', 'Dashboard', QR_ONLINE_CAP, 'qr-online',
        'qr_online_dashboard_page');
    add_submenu_page('qr-online', 'QR-Online – Einstellungen', 'Einstellungen', QR_ONLINE_CAP,
        'qr-online-settings', 'qr_online_settings_page');
});

add_action('admin_enqueue_scripts', function (string $hook) {
    if ($hook !== 'toplevel_page_qr-online') {
        return;
    }
    $base = plugin_dir_url(__FILE__) . 'assets/';
    wp_enqueue_style('qr-online', $base . 'dashboard.css', [], QR_ONLINE_VERSION);
    wp_enqueue_script('qr-online-qrcode', $base . 'vendor/qrcode.js', [], '1.4.4', true);
    wp_enqueue_script('qr-online', $base . 'dashboard.js', ['qr-online-qrcode'], QR_ONLINE_VERSION, true);
    wp_add_inline_script('qr-online', 'window.QR_ONLINE = ' . wp_json_encode([
        'api' => esc_url_raw(rest_url(QR_ONLINE_NS . '/')),
        'nonce' => wp_create_nonce('wp_rest'),
        'configured' => qr_online_configured(),
        'settings' => admin_url('admin.php?page=qr-online-settings'),
    ]) . ';', 'before');
});

function qr_online_dashboard_page(): void
{
    echo '<div class="wrap qro"><h1 class="wp-heading-inline">QR-Online</h1>'
        . '<div id="qro-app"><p>Lade …</p></div>'
        . '<noscript><p>Das Dashboard braucht JavaScript.</p></noscript></div>';
}

add_action('admin_init', function () {
    register_setting('qr_online', 'qr_online_server', [
        'type' => 'string',
        'sanitize_callback' => fn($v) => rtrim(esc_url_raw(trim((string)$v), ['http', 'https']), '/'),
    ]);
    register_setting('qr_online', 'qr_online_key', [
        'type' => 'string',
        // Leeres Feld = Schluessel behalten; er wird nie wieder ins Formular geschrieben
        'sanitize_callback' => function ($v) {
            $v = trim((string)$v);
            return $v === '' ? (string)get_option('qr_online_key', '') : $v;
        },
    ]);
});

function qr_online_settings_page(): void
{
    $server_fixed = defined('QR_ONLINE_SERVER');
    $key_fixed = defined('QR_ONLINE_API_KEY');
    $has_key = qr_online_key() !== '';
    ?>
    <div class="wrap">
        <h1>QR-Online – Einstellungen</h1>
        <?php
        if (qr_online_configured()) {
            $ping = qr_online_call('GET', 'ping');
            if (is_wp_error($ping)) {
                echo '<div class="notice notice-error"><p><strong>Keine Verbindung:</strong> '
                    . esc_html($ping->get_error_message()) . '</p></div>';
            } else {
                echo '<div class="notice notice-success"><p>✓ Verbindung steht, Schlüssel passt. '
                    . '<a href="' . esc_url(admin_url('admin.php?page=qr-online')) . '">Zum Dashboard</a></p></div>';
            }
        }
        ?>
        <form method="post" action="options.php">
            <?php settings_fields('qr_online'); ?>
            <table class="form-table" role="presentation">
                <tr>
                    <th scope="row"><label for="qr_online_server">Server-Adresse</label></th>
                    <td>
                        <input type="url" class="regular-text code" id="qr_online_server" name="qr_online_server"
                               placeholder="https://qr.example.de" value="<?php echo esc_attr(qr_online_server()); ?>"
                            <?php disabled($server_fixed); ?>>
                        <p class="description">Wo <code>index.php</code> aus <code>QR-Online/server/</code> liegt.
                            Genau diese Adresse steht vor dem Code in jedem QR-Code.
                            <?php if ($server_fixed) echo '<br>Festgelegt in der wp-config.php.'; ?></p>
                    </td>
                </tr>
                <tr>
                    <th scope="row"><label for="qr_online_key">API-Schlüssel</label></th>
                    <td>
                        <input type="password" class="regular-text" id="qr_online_key" name="qr_online_key"
                               autocomplete="new-password" value=""
                               placeholder="<?php echo $has_key ? 'gespeichert – leer lassen zum Behalten' : ''; ?>"
                            <?php disabled($key_fixed); ?>>
                        <p class="description">Der Schlüssel aus der <code>config.php</code> des Servers.
                            Er bleibt auf diesem WordPress-Server und erreicht den Browser nie.
                            <?php if ($key_fixed) echo '<br>Festgelegt in der wp-config.php.'; ?></p>
                    </td>
                </tr>
            </table>
            <?php if (!($server_fixed && $key_fixed)) submit_button('Speichern und Verbindung testen'); ?>
        </form>
    </div>
    <?php
}

add_filter('plugin_action_links_' . plugin_basename(__FILE__), function (array $links) {
    array_unshift($links, '<a href="' . esc_url(admin_url('admin.php?page=qr-online-settings')) . '">Einstellungen</a>');
    return $links;
});

// ---------------------------------------------------------------- Widget auf der WP-Startseite

add_action('wp_dashboard_setup', function () {
    if (current_user_can(QR_ONLINE_CAP) && qr_online_configured()) {
        wp_add_dashboard_widget('qr_online_widget', 'QR-Online: meistgescannt', 'qr_online_widget');
    }
});

function qr_online_widget(): void
{
    // Kurz zwischenspeichern, damit nicht jeder Aufruf der WP-Startseite den QR-Server fragt
    $rows = get_transient('qr_online_widget');
    if ($rows === false) {
        $rows = qr_online_call('GET', 'links');
        if (is_wp_error($rows)) {
            echo '<p>' . esc_html($rows->get_error_message()) . '</p>';
            return;
        }
        set_transient('qr_online_widget', $rows, 5 * MINUTE_IN_SECONDS);
    }
    if (!$rows) {
        echo '<p>Noch keine Links.</p>';
    } else {
        usort($rows, fn($a, $b) => $b['scans'] <=> $a['scans']);
        echo '<table class="widefat striped"><tbody>';
        foreach (array_slice($rows, 0, 5) as $r) {
            $title = $r['label'] !== '' ? $r['label'] : $r['target'];
            echo '<tr><td>' . esc_html($title) . ' <code>' . esc_html($r['code']) . '</code></td>'
                . '<td style="text-align:right"><strong>' . (int)$r['scans'] . '</strong></td></tr>';
        }
        echo '</tbody></table>';
    }
    echo '<p><a href="' . esc_url(admin_url('admin.php?page=qr-online')) . '">Zum Dashboard →</a></p>';
}
