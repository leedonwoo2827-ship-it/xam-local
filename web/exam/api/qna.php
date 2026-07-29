<?php
/**
 * /exam/api/qna.php — 질문 등록 · 조회
 *
 *   POST                       질문 등록 (로그인 필수)
 *   GET  ?keys=a,b,c           그 문제들의 **승인·공개** 답변만 (문제 카드에 먼저 보여줄 것)
 *   GET  ?mine=1               내 질문 전체 (상태 포함)
 *   GET  ?pd=sqld&page=1       공개 Q&A 목록 (게시판형 화면용)
 *
 * ★★ qa_draft 는 어떤 경로로도 SELECT 하지 않는다.
 *    LLM 초안이 검수 없이 새어나가는 경로를 구조적으로 없애는 장치다.
 *    아래 SELECT 문에 qa_draft 가 등장하면 그 자체가 버그다. (검증 C-31)
 *
 * ⚠ 크레딧 차감은 아직 붙이지 않았다(내부 오픈 + 강제 지급 운영).
 *   대신 cost_units = 0 으로 기록한다 — '무료 기간에 받은 질문'이라는 사실이 남고,
 *   나중에 차감을 켜도 과거 질문의 환불액이 0원으로 정확하다.
 *   차감을 켤 때 이 파일의 §차감 자리에 ex_credit_debit() 만 끼우면 된다. 스키마 변경 0.
 */
require_once __DIR__ . '/_boot.php';

$mb     = ex_mb();
$method = $_SERVER['REQUEST_METHOD'];

/* 회원에게 내보내도 되는 컬럼만. qa_draft 없음. */
const QNA_PUB_COLS  = 'qa_id, qa_parent, pd_id, kind, pr_key, qa_question, qa_chosen,
                       qa_status, qa_answer, qa_public, qa_answered_at, created_at';
const QNA_MINE_COLS = QNA_PUB_COLS . ', cost_units, qa_refunded';

/* ═══════════════════════════════════════════════════════════════════════
 *  POST — 질문 등록
 * ═══════════════════════════════════════════════════════════════════════ */
if ($method === 'POST') {
    if (!ex_same_origin()) ex_fail('bad_origin', 403);
    if ($mb === '')        ex_fail('login_required', 401);
    if (!ex_csrf_ok())     ex_fail('bad_csrf', 403);

    $ext = ex_ext($mb);
    if (!empty($ext['blocked'])) ex_fail('blocked', 403);

    $body   = ex_body();
    $pd     = ex_pd(isset($body['pd']) ? $body['pd'] : 'sqld');
    $kind   = isset($body['kind']) ? (string)$body['kind'] : 'qna';
    $pr_key = isset($body['pr_key']) ? trim((string)$body['pr_key']) : '';
    $q      = isset($body['question']) ? trim((string)$body['question']) : '';
    $chosen = isset($body['chosen']) ? (int)$body['chosen'] : -1;
    $parent = isset($body['parent']) ? (int)$body['parent'] : 0;

    if (!in_array($kind, array('qna', 'report'), true)) $kind = 'qna';

    // 문제 오류 신고는 우리에게 이득이므로 대가를 받지 않고 제한도 느슨하게 둔다.
    $limit = ($kind === 'report') ? 30 : 20;
    if (!ex_rate($kind, $limit, 86400)) ex_fail('too_many_today', 429);

    if ($pr_key !== '' && !ex_valid_key($pr_key)) ex_fail('bad_pr_key');
    if ($kind === 'report' && $pr_key === '')     ex_fail('pr_key_required');

    $len = mb_strlen($q, 'UTF-8');
    if ($len < 5)    ex_fail('too_short');
    if ($len > 2000) ex_fail('too_long');
    if ($chosen < -1 || $chosen > 20) $chosen = -1;

    // 문제가 실재하고 노출 중인지 확인 — 없는 문제로 질문이 쌓이면 검수 화면이 깨진다
    if ($pr_key !== '') {
        $p = sql_fetch("select pr_id from ex_problem
                         where pd_id = '" . ex_s2($pd) . "'
                           and pr_key = '" . ex_s2($pr_key) . "' and pr_open = 1");
        if (!$p) ex_fail('no_such_problem', 404);
    }

    // 차감 단가 — 지금은 기록만 한다
    $prod = sql_fetch("select cost_units from ex_product where pd_id = '" . ex_s2($pd) . "'");
    $unit = $prod ? (int)$prod['cost_units'] : 10;

    /* ── §차감 자리 ────────────────────────────────────────────────────
     * 크레딧을 켤 때 여기에 넣는다(PLAN §5-3 순서):
     *   1) ex_qna INSERT (아래)                      → qa_id 확보
     *   2) ex_credit_debit($mb, $unit, "qna:$qa_id") → false 면 ex_qna DELETE + 402
     *   3) ex_qna UPDATE qa_credit_ok = 1
     * 이 순서라야 "질문권은 빠졌는데 질문이 없다"가 원리적으로 안 생긴다.
     * 지금은 무료 기간이므로 cost_units = 0, qa_credit_ok = 1 로 넣는다.
     */
    $cost = 0;   // 무료 기간. 켜면 $unit 으로 바꾼다.

    sql_query("insert into ex_qna
                   (qa_parent, mb_id, pd_id, kind, pr_key, qa_question, qa_chosen,
                    qa_status, cost_units, qa_credit_ok, qa_public, created_at)
               values (" . (int)$parent . ", '" . ex_s2($mb) . "', '" . ex_s2($pd) . "',
                       '" . ex_s2($kind) . "', '" . ex_s2($pr_key) . "',
                       '" . ex_s2($q) . "', " . (int)$chosen . ",
                       'pending', " . (int)$cost . ", 1, 1, '" . G5_TIME_YMDHIS . "')", false);

    $qa_id = (int)sql_insert_id();
    if (!$qa_id) ex_fail('insert_failed', 500);

    sql_query("update ex_user_ext set qna_total = qna_total + 1
                where mb_id = '" . ex_s2($mb) . "'", false);
    ex_log($kind, 'qna:' . $qa_id);

    ex_out(array('ok' => 1, 'qa_id' => $qa_id, 'status' => 'pending', 'unit' => $unit, 'charged' => $cost));
}

/* ═══════════════════════════════════════════════════════════════════════
 *  GET
 * ═══════════════════════════════════════════════════════════════════════ */
if ($method !== 'GET') ex_fail('bad_method', 405);

/* ── ?keys=a,b,c — 문제별 공개 답변 일괄 조회 ───────────────────────────
 * 문제 카드마다 요청을 날리면 50요청이 된다. 한 번에 받는다.
 * 질문 폼을 열기 전에 이걸 먼저 보여주는 게 중복 질문을 막는 핵심 장치다. */
if (isset($_GET['keys'])) {
    $raw = explode(',', (string)$_GET['keys']);
    $keys = array();
    foreach ($raw as $k) {
        $k = trim($k);
        if (ex_valid_key($k)) $keys[] = "'" . ex_s2($k) . "'";
        if (count($keys) >= 100) break;      // 한 화면에 50문제면 충분하다
    }
    if (!$keys) ex_out(array('ok' => 1, 'items' => new stdClass()));

    $items = array();
    $res = sql_query("select " . QNA_PUB_COLS . "
                        from ex_qna
                       where pr_key in (" . implode(',', $keys) . ")
                         and qa_status = 'approved' and qa_public = 1
                       order by qa_answered_at desc
                       limit 200", false);
    while ($r = sql_fetch_array($res)) {
        $items[$r['pr_key']][] = array(
            'qa_id'    => (int)$r['qa_id'],
            'question' => $r['qa_question'],
            'chosen'   => (int)$r['qa_chosen'],
            'answer'   => (string)$r['qa_answer'],
            'at'       => $r['qa_answered_at'],
        );
    }
    ex_out(array('ok' => 1, 'items' => $items ? $items : new stdClass()));
}

/* ── ?mine=1 — 내 질문 ─────────────────────────────────────────────────── */
if (!empty($_GET['mine'])) {
    if ($mb === '') ex_fail('login_required', 401);

    $page = max(1, (int)(isset($_GET['page']) ? $_GET['page'] : 1));
    $per  = 20;
    $off  = ($page - 1) * $per;

    $cnt = sql_fetch("select count(*) as c from ex_qna where mb_id = '" . ex_s2($mb) . "'");
    $rows = array();
    $res = sql_query("select " . QNA_MINE_COLS . "
                        from ex_qna where mb_id = '" . ex_s2($mb) . "'
                       order by qa_id desc limit $off, $per", false);
    while ($r = sql_fetch_array($res)) $rows[] = ex_qna_row($r, true);

    ex_out(array('ok' => 1, 'total' => (int)$cnt['c'], 'page' => $page, 'per' => $per, 'items' => $rows));
}

/* ── 공개 Q&A 목록 (게시판형) ──────────────────────────────────────────── */
$pd   = ex_pd(isset($_GET['pd']) ? $_GET['pd'] : 'sqld');
$page = max(1, (int)(isset($_GET['page']) ? $_GET['page'] : 1));
$per  = 20;
$off  = ($page - 1) * $per;

$w = "pd_id = '" . ex_s2($pd) . "' and qa_status = 'approved' and qa_public = 1";
$cnt = sql_fetch("select count(*) as c from ex_qna where $w");

$rows = array();
$res = sql_query("select " . QNA_PUB_COLS . " from ex_qna
                   where $w order by qa_answered_at desc limit $off, $per", false);
while ($r = sql_fetch_array($res)) $rows[] = ex_qna_row($r, false);

ex_out(array('ok' => 1, 'pd' => $pd, 'total' => (int)$cnt['c'],
             'page' => $page, 'per' => $per, 'items' => $rows));


/* ═══════════════════════════════════════════════════════════════════════ */

function ex_qna_row($r, $mine) {
    $o = array(
        'qa_id'    => (int)$r['qa_id'],
        'pd'       => $r['pd_id'],
        'kind'     => $r['kind'],
        'pr_key'   => $r['pr_key'],
        'question' => $r['qa_question'],
        'chosen'   => (int)$r['qa_chosen'],
        'status'   => $r['qa_status'],
        'at'       => $r['created_at'],
    );
    // 답변은 승인된 것만 내보낸다. drafting/draft_ready 상태의 내용은 절대 나가지 않는다.
    if ($r['qa_status'] === 'approved') {
        $o['answer']      = (string)$r['qa_answer'];
        $o['answered_at'] = $r['qa_answered_at'];
    }
    if ($mine) {
        $o['cost']     = (int)$r['cost_units'];
        $o['refunded'] = (int)$r['qa_refunded'];
    }
    return $o;
}

/** 짧은 이스케이프 별칭 — adm/exam_lib/problem.php 의 ex_s() 와 이름이 겹치지 않게. */
function ex_s2($v) { return sql_real_escape_string((string)$v); }
