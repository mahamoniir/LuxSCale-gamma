<?php
/**
 * Browser viewer for JSON-lines chat logs under logs/chat/ (one file per ISO week).
 * Log files older than 7 days are removed by the Flask app (luxscale/chat_file_log.py).
 *
 * Security (required): open only from localhost, OR set env LUXSCALE_CHAT_LOG_PHP_KEY
 * and call: print_chat_log.php?key=YOUR_KEY
 */
declare(strict_types=1);

$root = __DIR__;
$logDir = $root . '/logs/chat';

$remote = $_SERVER['REMOTE_ADDR'] ?? '';
$isLocal = ($remote === '127.0.0.1' || $remote === '::1');
$key = getenv('LUXSCALE_CHAT_LOG_PHP_KEY') ?: '';
$qkey = $_GET['key'] ?? '';
$ok = $isLocal || ($key !== '' && is_string($qkey) && hash_equals($key, $qkey));

if (!$ok) {
    http_response_code(403);
    header('Content-Type: text/plain; charset=utf-8');
    echo "Forbidden. Use localhost, or set LUXSCALE_CHAT_LOG_PHP_KEY and ?key=...\n";
    exit(1);
}

$lines = isset($_GET['lines']) ? max(1, min(5000, (int) $_GET['lines'])) : 200;

if (!is_dir($logDir)) {
    header('Content-Type: text/html; charset=utf-8');
    echo '<!DOCTYPE html><html><head><title>Chat log</title><meta charset="utf-8"></head><body>';
    echo '<p>No <code>logs/chat/</code> yet (no requests logged).</p></body></html>';
    exit(0);
}

$files = glob($logDir . '/chat_*.log') ?: [];
usort($files, function ($a, $b) {
    return filemtime($b) <=> filemtime($a);
});
if (count($files) === 0) {
    header('Content-Type: text/html; charset=utf-8');
    echo '<!DOCTYPE html><html><head><title>Chat log</title><meta charset="utf-8"></head><body>';
    echo '<p>Empty <code>logs/chat/</code> directory.</p></body></html>';
    exit(0);
}

$target = $files[0];
if (isset($_GET['file']) && is_string($_GET['file'])) {
    $f = basename($_GET['file']);
    if (preg_match('/^chat_\\d{4}_W\\d{2}\\.log$/', $f)) {
        $maybe = $logDir . '/' . $f;
        if (is_file($maybe)) {
            $target = $maybe;
        }
    }
}

$raw = @file($target, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) ?: [];
$tail = array_slice($raw, -$lines);

header('Content-Type: text/html; charset=utf-8');
echo '<!DOCTYPE html><html><head><title>Chat log (LuxScale)</title><meta charset="utf-8">';
echo '<style>body{font:13px/1.45 Consolas,monospace;background:#111;color:#e0e0e0;max-width:1200px;margin:0 auto;padding:16px;}h1{font-size:15px;color:#888}pre{white-space:pre-wrap;word-break:break-all;background:#1a1a1a;border:1px solid #333;padding:12px;overflow-x:auto}code{color:#7dd} .meta{color:#666;font-size:12px;margin-bottom:8px} a{color:#6ae}</style></head><body>';
echo '<h1>Chat audit log (tail ' . (int) $lines . ' lines)</h1>';
echo '<div class="meta">File: <code>' . htmlspecialchars($target) . '</code> · ';
echo '<a href="?lines=' . (int) $lines . '">this view</a> · ';
echo 'IP allow: localhost, or LUXSCALE_CHAT_LOG_PHP_KEY+?key=</div>';

echo '<h2>Available week files</h2><ul style="color:#999;font-size:12px;">';
foreach ($files as $p) {
    $b = basename($p);
    echo '<li><a href="?file=' . rawurlencode($b) . '&lines=' . (int) $lines . (isset($_GET['key']) ? '&key=' . rawurlencode((string) $_GET['key']) : '') . '">' . htmlspecialchars($b) . '</a></li>';
}
echo '</ul><pre>';
foreach ($tail as $line) {
    $obj = json_decode($line, true);
    if (is_array($obj)) {
        echo htmlspecialchars(json_encode($obj, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)) . "\n\n";
    } else {
        echo htmlspecialchars($line) . "\n";
    }
}
echo '</pre></body></html>';
