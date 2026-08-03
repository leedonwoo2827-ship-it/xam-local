<?php
/**
 * GET /exam/api/attempts.php?pd=sqld
 *
 * 응시 이력. `ex_attempt` 는 grade.php 가 로그인 회원에게만 쌓는다.
 * 마이페이지의 점수 추이와, 나중에 분석 리포트의 '보관본 다시 보기' 가 여기서 온다.
 */
require_once __DIR__ . '/_boot.php';
require_once __DIR__ . '/lib/sample.php';

$sample = ex_sample_on();

$mb = ex_mb();
if ($mb === '' && !$sample) ex_fail('login_required', 401);

$pd  = ex_pd(isset($_GET['pd']) ? $_GET['pd'] : 'sqld');
$mbq = sql_real_escape_string($mb);
$pdq = sql_real_escape_string($pd);

/* ── 샘플 ───────────────────────────────────────────────────────────────────
 * 합성 응시 1건. 성적표 샘플과 **같은 답안지**에서 나오므로 점수가 서로 맞는다
 * (마이페이지에 34점, 성적표에 51점이 뜨면 데모가 신뢰를 잃는다).
 */
if ($sample) {
    $sh = ex_sample_sheet($pd, isset($_GET['rd']) ? (int)$_GET['rd'] : 1);
    if (!$sh) ex_fail('no_problems', 404);
    ex_out(array(
        'ok' => 1, 'pd' => $pd, 'sample' => 1,
        'summary' => array('count' => 1, 'avg_pct' => $sh['pct'], 'max_pct' => $sh['pct']),
        'best'  => array($sh['rd_no'] => array('pct' => $sh['pct'], 'tries' => 1)),
        'items' => array(array(
            'at_id' => 0, 'rd_no' => $sh['rd_no'], 'round' => $sh['rd_no'] . '회',
            'total' => $sh['total'], 'correct' => $sh['correct'], 'pct' => $sh['pct'],
            'sec' => 2340, 'filter' => '', 'at' => $sh['at'],
        )),
    ));
}

$rows = array();
$res = sql_query("select at_id, rd_no, at_total, at_correct, at_pct, at_sec, at_filter, created_at
                    from ex_attempt
                   where mb_id = '$mbq' and pd_id = '$pdq'
                   order by at_id desc limit 50", false);
while ($r = sql_fetch_array($res)) {
    $rows[] = array(
        'at_id'   => (int)$r['at_id'],
        'rd_no'   => (int)$r['rd_no'],
        'round'   => (int)$r['rd_no'] . '회',
        'total'   => (int)$r['at_total'],
        'correct' => (int)$r['at_correct'],
        'pct'     => (int)$r['at_pct'],
        'sec'     => (int)$r['at_sec'],
        'filter'  => $r['at_filter'],
        'at'      => $r['created_at'],
    );
}

/* 회차별 최고점 — "어느 회차를 아직 안 풀었나" 가 한눈에 보여야 한다 */
$best = array();
$res = sql_query("select rd_no, max(at_pct) as pct, count(*) as tries
                    from ex_attempt
                   where mb_id = '$mbq' and pd_id = '$pdq'
                   group by rd_no order by rd_no", false);
while ($r = sql_fetch_array($res)) {
    $best[(int)$r['rd_no']] = array('pct' => (int)$r['pct'], 'tries' => (int)$r['tries']);
}

$sum = sql_fetch("select count(*) as n, coalesce(avg(at_pct),0) as avg_pct,
                         coalesce(max(at_pct),0) as max_pct
                    from ex_attempt where mb_id = '$mbq' and pd_id = '$pdq'");

ex_out(array(
    'ok'      => 1,
    'pd'      => $pd,
    'summary' => array(
        'count'   => (int)$sum['n'],
        'avg_pct' => (int)round($sum['avg_pct']),
        'max_pct' => (int)$sum['max_pct'],
    ),
    'best'  => $best,     // {회차: {pct, tries}}
    'items' => $rows,
));
