<?php
/**
 * GET /exam/api/wrong.php?pd=sqld&page=1&only=wrong
 *
 * 오답노트. `ex_wrong` 은 grade.php 가 채운다(응답한 문항만).
 *
 * 회원에게 무료로 준다 — 유료 가치는 Q&A 에 있고, 오답노트는 재방문 유도 장치다.
 * (COST.md §3)
 */
require_once __DIR__ . '/_boot.php';
require_once __DIR__ . '/lib/sample.php';

$sample = ex_sample_on();

$mb = ex_mb();
if ($mb === '' && !$sample) ex_fail('login_required', 401);

$pd   = ex_pd(isset($_GET['pd']) ? $_GET['pd'] : 'sqld');
$page = max(1, (int)(isset($_GET['page']) ? $_GET['page'] : 1));
$per  = 20;
$off  = ($page - 1) * $per;
$only = isset($_GET['only']) ? $_GET['only'] : 'wrong';   // wrong | starred | all

$mbq = sql_real_escape_string($mb);
$pdq = sql_real_escape_string($pd);

/* ── 샘플 ───────────────────────────────────────────────────────────────────
 * 성적표 샘플과 같은 답안지에서 틀린 문항만 뽑는다 → 두 화면의 숫자가 맞는다.
 * `ex_wrong` 을 읽지 않으므로 누적치(try_cnt·wrong_cnt)는 1회분으로 둔다.
 */
if ($sample) {
    $sh = ex_sample_sheet($pd, isset($_GET['rd']) ? (int)$_GET['rd'] : 1);
    if (!$sh) ex_fail('no_problems', 404);
    $rows = array();
    foreach ($sh['rows'] as $r) {
        if ((int)$r['is_ok'] === 1) continue;          // 맞춘 것은 오답노트에 없다
        if ((int)$r['chosen'] < 0) continue;           // 미응답은 ex_wrong 에 안 쌓인다(응답한 문항만)
        $rows[] = array(
            'pr_key' => $r['pr_key'], 'round' => (int)$r['rd_no'] . '회',
            'rd_no' => (int)$r['rd_no'], 'number' => (int)$r['pr_no'],
            'subject' => $r['sj_name'], 'difficulty' => $r['difficulty'],
            'question' => $r['question'],
            'choices' => ex_unjson($r['choices_json'], array()),
            'answer_index' => ($r['answer_index'] === null) ? null : (int)$r['answer_index'],
            'answer' => $r['answer_label'],
            'explanation' => (string)$r['explanation'],
            'try_cnt' => 1, 'wrong_cnt' => 1,
            'last_chosen' => (int)$r['chosen'], 'last_ok' => 0, 'starred' => 0,
            'at' => $sh['at'],
        );
    }
    $n = count($rows);
    ex_out(array(
        'ok' => 1, 'pd' => $pd, 'sample' => 1,
        'total' => $n, 'page' => 1, 'per' => $n,
        'summary' => array('problems' => $n, 'still_wrong' => $n,
                           'tries' => $n, 'misses' => $n),
        'items' => array_slice($rows, 0, 20),
    ));
}

/* 마지막에 틀린 것만 = 오답노트. 맞춘 뒤로는 목록에서 빠진다.
   틀린 이력(wrong_cnt)은 남아 있어 "몇 번 틀렸는지" 는 계속 보인다. */
$w = "w.mb_id = '$mbq' and p.pd_id = '$pdq' and p.pr_open = 1";
if ($only === 'wrong')        $w .= " and w.last_ok = 0";
elseif ($only === 'starred')  $w .= " and w.starred = 1";

$cnt = sql_fetch("select count(*) as c
                    from ex_wrong w join ex_problem p on p.pr_id = w.pr_id
                   where $w");

$rows = array();
$res = sql_query("select p.pr_key, p.rd_no, p.pr_no, p.sj_name, p.difficulty,
                         p.question, p.choices_json, p.answer_index, p.answer_label,
                         p.explanation,
                         w.try_cnt, w.wrong_cnt, w.last_chosen, w.last_ok, w.starred, w.updated_at
                    from ex_wrong w join ex_problem p on p.pr_id = w.pr_id
                   where $w
                   order by w.wrong_cnt desc, w.updated_at desc
                   limit $off, $per", false);

while ($r = sql_fetch_array($res)) {
    $rows[] = array(
        'pr_key'      => $r['pr_key'],
        'round'       => (int)$r['rd_no'] . '회',
        'rd_no'       => (int)$r['rd_no'],
        'number'      => (int)$r['pr_no'],
        'subject'     => $r['sj_name'],
        'difficulty'  => $r['difficulty'],
        'question'    => $r['question'],
        'choices'     => ex_unjson($r['choices_json'], array()),
        'answer_index'=> ($r['answer_index'] === null) ? null : (int)$r['answer_index'],
        'answer'      => $r['answer_label'],
        'explanation' => (string)$r['explanation'],
        'try_cnt'     => (int)$r['try_cnt'],
        'wrong_cnt'   => (int)$r['wrong_cnt'],
        'last_chosen' => (int)$r['last_chosen'],
        'last_ok'     => (int)$r['last_ok'],
        'starred'     => (int)$r['starred'],
        'at'          => $r['updated_at'],
    );
}

/* 요약 — 화면 상단에 쓴다 */
$sum = sql_fetch("select count(*) as total,
                         sum(case when w.last_ok = 0 then 1 else 0 end) as still_wrong,
                         sum(w.try_cnt) as tries, sum(w.wrong_cnt) as misses
                    from ex_wrong w join ex_problem p on p.pr_id = w.pr_id
                   where w.mb_id = '$mbq' and p.pd_id = '$pdq' and p.pr_open = 1");

ex_out(array(
    'ok'    => 1,
    'pd'    => $pd,
    'total' => (int)$cnt['c'],
    'page'  => $page,
    'per'   => $per,
    'summary' => array(
        'problems'    => (int)$sum['total'],
        'still_wrong' => (int)$sum['still_wrong'],
        'tries'       => (int)$sum['tries'],
        'misses'      => (int)$sum['misses'],
    ),
    'items' => $rows,
));
