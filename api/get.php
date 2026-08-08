<?php
/**
 * Loads a study by token (written by submit.php). Shape matches what result.html expects.
 */
header('Content-Type: application/json; charset=utf-8');

$token = isset($_GET['token']) ? (string) $_GET['token'] : '';
if (!preg_match('/^[a-f0-9]{32}$/', $token)) {
    http_response_code(400);
    echo json_encode(['status' => 'error', 'message' => 'Invalid token']);
    exit;
}

$path = __DIR__ . '/data/studies/' . $token . '.json';
if (!is_file($path)) {
    http_response_code(404);
    echo json_encode(['status' => 'error', 'message' => 'Study not found']);
    exit;
}

$record = json_decode(file_get_contents($path), true);
if (!is_array($record) || empty($record['payload']) || !is_array($record['payload'])) {
    http_response_code(500);
    echo json_encode(['status' => 'error', 'message' => 'Corrupt study record']);
    exit;
}

$p = $record['payload'];
$sides = $p['sides'];
$w = max((float) $sides[0], (float) $sides[2]);
$l = max((float) $sides[1], (float) $sides[3]);
// Prefer explicit CAD dims when present (length_eq / width_eq from /cad_calc)
if (isset($p['width']) && is_numeric($p['width'])) {
    $w = (float) $p['width'];
}
if (isset($p['length']) && is_numeric($p['length'])) {
    $l = (float) $p['length'];
}

$req = [
    'project_name' => $p['project_name'] ?? '',
    'sides' => $p['sides'],
    'height' => $p['height'],
    'width' => $w,
    'length' => $l,
];
if (isset($p['place'])) {
    $req['place'] = $p['place'];
}
if (isset($p['standard_ref_no'])) {
    $req['standard_ref_no'] = $p['standard_ref_no'];
}
if (isset($p['standard_category'])) {
    $req['standard_category'] = $p['standard_category'];
}
if (isset($p['standard_task_or_activity'])) {
    $req['standard_task_or_activity'] = $p['standard_task_or_activity'];
}
if (isset($p['standard_lighting'])) {
    $req['standard_lighting'] = $p['standard_lighting'];
}
if (isset($p['mounting_height'])) {
    $req['mounting_height'] = $p['mounting_height'];
}
if (isset($p['notes'])) {
    $req['notes'] = $p['notes'];
}

$meta = $p['calculation_meta'] ?? new stdClass();

$out = [
    'status' => 'success',
    'results' => $p['results'],
    'calculation_meta' => $meta,
    'project_info' => [
        'Project Name' => $p['project_name'] ?? '',
        'Client Name' => $p['name'] ?? '',
        'Client Number' => $p['phone'] ?? '',
        'Company Name' => $p['company'] ?? '',
    ],
    'request' => $req,
    'customer' => [
        'name' => $p['name'] ?? '',
        'phone' => $p['phone'] ?? '',
        'company' => $p['company'] ?? '',
        'email' => $p['email'] ?? '',
    ],
    'width' => $w,
    'length' => $l,
];

if (isset($p['standard_lighting'])) {
    $out['standard_lighting'] = $p['standard_lighting'];
}

echo json_encode($out, JSON_UNESCAPED_UNICODE);
