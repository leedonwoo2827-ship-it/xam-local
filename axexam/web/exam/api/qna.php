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
const QNA_PUB_COLS  = 'qa_id, qa_parent, pd_id, kind, pr_key, sj_no, bo_table, wr_id,
                       qa_question, qa_chosen,
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
    $pd     = ex_pd(isset($body['pd']) ? $body['pd'] : '', '');
    $kind   = isset($body['kind']) ? (string)$body['kind'] : 'qna';
    $pr_key = isset($body['pr_key']) ? trim((string)$body['pr_key']) : '';
    $q      = isset($body['question']) ? trim((string)$body['question']) : '';
    $chosen = isset($body['chosen']) ? (int)$body['chosen'] : -1;
    $parent = isset($body['parent']) ? (int)$body['parent'] : 0;
    $sj_no  = isset($body['sj_no'])  ? (int)$body['sj_no']  : 0;

    /* 품목을 기본값으로 때우지 않는다. 예전에는 'sqld' 로 떨어졌는데, 문제집이 여러 개인
     * 지금은 그게 **다른 문제집 질문이 조용히 SQLD 로 들어가는** 경로가 된다.
     * 실재 확인까지 한다 — 형식만 맞는 오타('sqldd')가 살아 있는 품목이 되면 안 된다. */
    if ($pd === '') ex_fail('pd_required');
    // pd_config 까지 가져온다 — 아래 §차감 의 charge 스위치가 여기 들어 있다
    $prod = sql_fetch("select pd_id, cost_units, pd_config from ex_product
                        where pd_id = '" . ex_s2($pd) . "' and pd_open = 1");
    if (!$prod) ex_fail('no_such_product', 404);

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

    // 문제가 실재하고 노출 중인지 확인 — 없는 문제로 질문이 쌓이면 검수 화면이 깨진다.
    // 과목(sj_no)을 문제에서 가져온다. 이용자가 고른 값보다 문제가 가진 값이 정확하다.
    if ($pr_key !== '') {
        $p = sql_fetch("select pr_id, sj_no from ex_problem
                         where pd_id = '" . ex_s2($pd) . "'
                           and pr_key = '" . ex_s2($pr_key) . "' and pr_open = 1");
        if (!$p) ex_fail('no_such_problem', 404);
        $sj_no = (int)$p['sj_no'];
    }
    if ($sj_no < 0 || $sj_no > 127) $sj_no = 0;   // TINYINT 범위

    $unit = (int)$prod['cost_units'] > 0 ? (int)$prod['cost_units'] : 10;

    /* ── §차감 ─────────────────────────────────────────────────────────
     * 순서가 중요하다(PLAN §5-3). 이 순서라야 "포인트는 빠졌는데 질문이 없다"가 안 생긴다:
     *   1) ex_qna INSERT (qa_credit_ok = 0)                → qa_id 확보
     *   2) ex_credit_debit(...)  → false 면 ex_qna DELETE + 402
     *   3) ex_qna UPDATE qa_credit_ok = 1
     * 3) 이 실패해도 원장에 차감 기록이 남아 회계는 정합하다. qa_credit_ok=0 인 질문은
     * 검수 화면에 빨간 경고로 떠서 수동 확인 대상이 된다.
     *
     * ⚠ 지금은 **무료 기간**이다. 차감을 켜는 스위치는 ex_product.pd_config 의
     *   {"charge":true} 다 — 품목별로 따로 켤 수 있다. 코드 수정 없이 DB 한 줄로 바뀐다.
     *   무료 기간에는 cost_units = 0 으로 기록한다: '무료로 받은 질문'이라는 사실이 남고,
     *   나중에 차감을 켜도 과거 질문의 환불액이 0원으로 정확하다.
     *
     * 문제 오류 신고(report)는 우리에게 이득이므로 차감하지 않는다 — 켜져 있어도 무료다.
     */
    $cfg    = ex_unjson(isset($prod['pd_config']) ? $prod['pd_config'] : '', array());
    $charge = (is_array($cfg) && !empty($cfg['charge']) && $kind !== 'report');
    $cost   = $charge ? $unit : 0;

    // 차감할 거라면 넣기 전에 잔액을 본다. 부족하면 질문을 만들지 않는다(빠른 실패).
    if ($charge) {
        require_once __DIR__ . '/lib/credit.php';
        ex_settle($mb, $pd);                                  // 밀린 월 지급을 먼저 반영
        if (ex_credit_balance($mb, $pd) < $cost) {
            ex_fail('no_credit', 402);
        }
    }

    sql_query("insert into ex_qna
                   (qa_parent, mb_id, pd_id, kind, pr_key, sj_no, qa_question, qa_chosen,
                    qa_status, cost_units, qa_credit_ok, qa_public, created_at)
               values (" . (int)$parent . ", '" . ex_s2($mb) . "', '" . ex_s2($pd) . "',
                       '" . ex_s2($kind) . "', '" . ex_s2($pr_key) . "', " . (int)$sj_no . ",
                       '" . ex_s2($q) . "', " . (int)$chosen . ",
                       'pending', " . (int)$cost . ", " . ($charge ? 0 : 1) . ", 1,
                       '" . G5_TIME_YMDHIS . "')", false);

    $qa_id = (int)sql_insert_id();
    if (!$qa_id) ex_fail('insert_failed', 500);

    if ($charge) {
        if (!ex_credit_debit($mb, $pd, $cost, 'qna:' . $qa_id, '질문 등록')) {
            // 사전 체크 이후에 잔액이 사라진 경우(동시 요청). 질문을 되돌린다.
            // ex_credit_debit 이 부분 차감분을 스스로 환불하므로 여기서는 행만 지운다.
            sql_query("delete from ex_qna where qa_id = " . $qa_id, false);
            ex_fail('no_credit', 402);
        }
        sql_query("update ex_qna set qa_credit_ok = 1 where qa_id = " . $qa_id, false);
    }

    sql_query("update ex_user_ext set qna_total = qna_total + 1
                where mb_id = '" . ex_s2($mb) . "'", false);
    ex_log($kind, 'qna:' . $qa_id);

    ex_out(array('ok' => 1, 'qa_id' => $qa_id, 'status' => 'pending',
                 'sj_no' => $sj_no, 'unit' => $unit, 'charged' => $cost));
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

/* ── ?mine=1[&pd=sqld] — 내 질문 ───────────────────────────────────────────
 * ★ pd 를 주면 그 문제집만. 안 주면 전체.
 *   문제집별로 따로 수강하는 구조에서 마이페이지가 두 문제집 질문을 섞어 보여주면
 *   "내가 SQLD 에서 몇 개 썼나"를 알 수 없다. 마이페이지는 항상 pd 를 붙여 부른다. */
if (!empty($_GET['mine'])) {
    if ($mb === '') ex_fail('login_required', 401);

    $page = max(1, (int)(isset($_GET['page']) ? $_GET['page'] : 1));
    $per  = 20;
    $off  = ($page - 1) * $per;

    $w = "mb_id = '" . ex_s2($mb) . "'";
    if (!empty($_GET['pd'])) {
        $w .= " and pd_id = '" . ex_s2(ex_pd($_GET['pd'], '')) . "'";
    }

    $cnt = sql_fetch("select count(*) as c from ex_qna where $w");
    $rows = array();
    $res = sql_query("select " . QNA_MINE_COLS . "
                        from ex_qna where $w
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
        'sj_no'    => (int)$r['sj_no'],       // 과목(게시판 말머리)
        'question' => $r['qa_question'],
        'chosen'   => (int)$r['qa_chosen'],
        'status'   => $r['qa_status'],
        'at'       => $r['created_at'],
    );
    // 게시판 글로 등록된 질문이면 그 글로 가는 링크를 만들 수 있게 넘긴다
    if (!empty($r['bo_table']) && !empty($r['wr_id'])) {
        $o['bo_table'] = $r['bo_table'];
        $o['wr_id']    = (int)$r['wr_id'];
    }
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
