<?php
/**
 * /exam/api/_boot.php — 모든 회원 API 의 공통 부트스트랩.
 *
 * 그누보드의 세션·DB·$member 만 재사용하고 출력 파이프라인(스킨/테마/head)은 쓰지 않는다.
 * 영카트 shop/ 이 같은 패턴이다 — 독립 디렉터리 + ../common.php include.
 */

// /www/exam/api/_boot.php → /www/common.php
include_once(dirname(__DIR__, 2) . '/common.php');

/* ── 응답 압축 ──────────────────────────────────────────────────────────
 * 실측: 카페24는 mod_deflate 가 켜져 있지만 **정적 파일에만** 적용된다
 *   (css 27,451B → 6,490B 압축됨 / PHP JSON 61,820B → 그대로).
 *   공유호스팅이 CPU 를 아끼려고 동적 콘텐츠를 제외한 것으로 보인다.
 *   .htaccess 의 AddOutputFilterByType 로는 해결되지 않았다.
 *
 * 그래서 PHP 에서 직접 압축한다. 50문제 JSON 62KB → 약 15KB.
 * 트래픽 한도가 월 4,000MB 라 4배 여유가 생긴다.
 *
 * ob_gzhandler 가 Content-Encoding 과 Vary 헤더를 알아서 붙인다.
 * 출력이 시작되기 전에 걸어야 하므로 여기가 유일한 자리다. */
if (function_exists('ob_gzhandler')
    && !ini_get('zlib.output_compression')
    && !empty($_SERVER['HTTP_ACCEPT_ENCODING'])
    && strpos($_SERVER['HTTP_ACCEPT_ENCODING'], 'gzip') !== false) {
    @ob_start('ob_gzhandler');
}

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Cache-Control: private, no-store');

/* ── 출력 ──────────────────────────────────────────────────────────────── */

function ex_out($a) {
    echo json_encode($a, JSON_UNESCAPED_UNICODE);
    exit;
}

function ex_fail($m, $c = 400) {
    http_response_code($c);
    ex_out(array('ok' => 0, 'err' => $m));
}

/* ── 신원 ──────────────────────────────────────────────────────────────── */

/**
 * 로그인 회원 아이디. 비로그인은 ''.
 *
 * ⚠ 절대 $member['mb_level'] 로 로그인을 판정하지 않는다 —
 *   비로그인도 mb_level 이 1 이다. 반드시 mb_id 의 존재로 본다.
 */
function ex_mb() {
    global $member;
    return isset($member['mb_id']) ? (string)$member['mb_id'] : '';
}

function ex_is_admin() {
    global $member;
    return ex_mb() !== '' && isset($member['mb_level']) && (int)$member['mb_level'] >= 10;
}

/* ── CSRF ──────────────────────────────────────────────────────────────── */
/*
 * 그누보드의 check_token() 을 쓰지 않는다. 이유 둘:
 *   ① 실패 시 alert()(JS)를 출력한다 → JSON 응답에 HTML 이 섞인다
 *   ② $_POST['token'] 만 읽는다 → JSON 바디 요청에서 못 쓴다
 * (관리자 영역은 또 다른 체계다 — check_admin_token(). GNUBOARD-FACTS §6 참조)
 *
 * 그래서 세션 기반 토큰을 직접 발급하고 X-Exam-Csrf 헤더로 받는다.
 */

function ex_csrf() {
    $t = get_session('ss_exam_csrf');
    if (!$t) {
        $t = bin2hex(random_bytes(16));
        set_session('ss_exam_csrf', $t);
    }
    return $t;
}

function ex_csrf_ok() {
    $sent = isset($_SERVER['HTTP_X_EXAM_CSRF']) ? (string)$_SERVER['HTTP_X_EXAM_CSRF'] : '';
    $have = (string)get_session('ss_exam_csrf');
    return $have !== '' && $sent !== '' && hash_equals($have, $sent);
}

/**
 * 같은 출처에서 온 요청인가. CSRF 의 보조 방어선.
 * Origin 이 없으면(구형 브라우저·일부 프록시) Referer 로 본다. 둘 다 없으면 통과시킨다 —
 * 여기서 막으면 정상 이용자가 새는 쪽이 더 크고, 진짜 방어는 ex_csrf_ok() 다.
 */
function ex_same_origin() {
    $host = isset($_SERVER['HTTP_HOST']) ? $_SERVER['HTTP_HOST'] : '';
    if ($host === '') return true;

    $src = '';
    if (!empty($_SERVER['HTTP_ORIGIN']))       $src = $_SERVER['HTTP_ORIGIN'];
    elseif (!empty($_SERVER['HTTP_REFERER']))  $src = $_SERVER['HTTP_REFERER'];
    if ($src === '') return true;

    $h = parse_url($src, PHP_URL_HOST);
    return ($h !== null && strcasecmp($h, preg_replace('/:\d+$/', '', $host)) === 0);
}

/* ── 로그 · rate limit ─────────────────────────────────────────────────── */

function ex_client_ip() {
    $ip = isset($_SERVER['REMOTE_ADDR']) ? $_SERVER['REMOTE_ADDR'] : '';
    return substr($ip, 0, 45);
}

function ex_log($act, $ref = '') {
    $mb = sql_real_escape_string(ex_mb());
    $a  = sql_real_escape_string(substr((string)$act, 0, 16));
    $r  = sql_real_escape_string(substr((string)$ref, 0, 40));
    $ip = sql_real_escape_string(ex_client_ip());
    sql_query("insert into ex_log (mb_id, lo_act, lo_ref, lo_ip, created_at)
                    values ('$mb', '$a', '$r', '$ip', '" . G5_TIME_YMDHIS . "')", false);
}

/**
 * $sec 초 안에 $max 건까지. 초과하면 false.
 * 로그인 회원은 mb_id 로, 비로그인은 IP 로 센다.
 */
function ex_rate($act, $max, $sec) {
    $a  = sql_real_escape_string(substr((string)$act, 0, 16));
    $mb = ex_mb();
    $since = date('Y-m-d H:i:s', G5_SERVER_TIME - (int)$sec);

    if ($mb !== '') {
        $w = "mb_id = '" . sql_real_escape_string($mb) . "'";
    } else {
        $w = "lo_ip = '" . sql_real_escape_string(ex_client_ip()) . "'";
    }
    $r = sql_fetch("select count(*) as c from ex_log
                     where $w and lo_act = '$a' and created_at >= '" . sql_real_escape_string($since) . "'");
    return ((int)$r['c'] < (int)$max);
}

/* ── 회원 확장행 ───────────────────────────────────────────────────────── */

/** ex_user_ext 가 없으면 만든다(최초 접속 시 자동 생성). */
function ex_ext($mb_id) {
    if ($mb_id === '') return null;
    $mb = sql_real_escape_string($mb_id);
    $r = sql_fetch("select * from ex_user_ext where mb_id = '$mb'");
    if (!$r) {
        sql_query("insert into ex_user_ext (mb_id, created_at)
                        values ('$mb', '" . G5_TIME_YMDHIS . "')", false);
        $r = sql_fetch("select * from ex_user_ext where mb_id = '$mb'");
    }
    return $r;
}

/* ── 잡동사니 ──────────────────────────────────────────────────────────── */

/** 'sqld' 같은 품목 코드만 통과. */
function ex_pd($v, $default = 'sqld') {
    $v = trim((string)$v);
    return preg_match('/^[a-z0-9\-]{1,20}$/', $v) ? $v : $default;
}

/** '1회' · '1' · 1 → 1. 숫자가 없으면 0. */
function ex_rd($v) {
    if (preg_match('/\d+/', (string)$v, $m)) return (int)$m[0];
    return 0;
}

/**
 * pr_key 형식 검증 — build_check.py 가 만드는 형식만 통과. 'm01-1#7'
 * 클라이언트가 보낸 키는 이걸 통과한 것만 배열 첨자로 쓴다.
 */
function ex_valid_key($k) {
    return (bool)preg_match('/^m\d{2}-\d{1,2}#\d{1,3}$/', (string)$k);
}

/** JSON 바디를 배열로. 잘못됐으면 빈 배열. */
function ex_body() {
    $raw = file_get_contents('php://input');
    if ($raw === false || $raw === '') return array();
    $d = json_decode($raw, true);
    return is_array($d) ? $d : array();
}

/** TEXT 컬럼에 든 JSON 을 배열로. */
function ex_unjson($s, $default = null) {
    if ($s === null || $s === '') return $default;
    $d = json_decode($s, true);
    return ($d === null && json_last_error() !== JSON_ERROR_NONE) ? $default : $d;
}

/**
 * sql_affected_rows() 래퍼 존재가 코어에서 확인되지 않았다(GNUBOARD-FACTS §14-13).
 * 있으면 쓰고 없으면 mysqli 를 직접 부른다.
 * ⚠ S6 크레딧 차감의 정확성이 이 함수에 통째로 의존한다.
 */
if (!function_exists('ex_affected')) {
    function ex_affected() {
        global $g5;
        if (function_exists('sql_affected_rows')) return (int)sql_affected_rows();
        return (int)mysqli_affected_rows($g5['connect_db']);
    }
}
