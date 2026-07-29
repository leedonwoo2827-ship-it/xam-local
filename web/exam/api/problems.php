<?php
/**
 * GET /exam/api/problems.php?pd=sqld&round=1
 *
 * DB 에서 문제 목록을 준다. 정답·해설을 포함한다 — 이 서비스는 문제·정답·해설이
 * 전면 공개이고, 유료 가치는 Q&A 에 있다(PLAN §3).
 *
 * 반환 형태를 **problems.js(window.PROBLEMS)와 동일하게** 맞춘다.
 * check_template.html 의 StaticDS 와 ApiDS 가 같은 렌더 코드를 쓰기 때문이다.
 * 필드명을 바꾸면 정적 폴백이 깨진다.
 */
require_once __DIR__ . '/_boot.php';

$pd    = ex_pd(isset($_GET['pd']) ? $_GET['pd'] : 'sqld');
$round = ex_rd(isset($_GET['round']) ? $_GET['round'] : 0);   // 0 = 전 회차

$pdq = sql_real_escape_string($pd);

/* ── ETag ───────────────────────────────────────────────────────────────
 * MAX(updated_at) 만으로는 부족하다. 문제를 pr_open=0 으로 숨기면
 * updated_at 이 안 바뀔 수 있는데 응답 내용은 달라진다 → 개수도 함께 넣는다.
 * 관리자가 문제를 고치면 updated_at 이 올라가 자동 무효화된다. */
$where = "pd_id = '$pdq' and pr_open = 1" . ($round ? " and rd_no = " . (int)$round : '');
$sig = sql_fetch("select count(*) as c, coalesce(max(updated_at), '') as m
                    from ex_problem where $where");
$etag = '"' . md5($pd . '|' . $round . '|' . $sig['m'] . '|' . $sig['c']) . '"';

header('ETag: ' . $etag);
header('Cache-Control: private, max-age=0, must-revalidate');

$inm = isset($_SERVER['HTTP_IF_NONE_MATCH']) ? trim($_SERVER['HTTP_IF_NONE_MATCH']) : '';
if ($inm !== '' && $inm === $etag) {
    http_response_code(304);
    exit;   // 본문 없음
}

/* ── 문제 ──────────────────────────────────────────────────────────────── */
$problems = array();
$res = sql_query("select rd_no, pr_key, bundle, pr_no, sj_no, sj_name, difficulty,
                         question, passage, sql_text, table_json, figures_json,
                         choices_json, n_choices, answer_index, answer_label,
                         explanation, tags_json, verified, reviewed, needs_review
                    from ex_problem
                   where $where
                   order by rd_no, pr_no", false);

while ($r = sql_fetch_array($res)) {
    $problems[] = array(
        // ↓ 이름은 problems.js 와 반드시 같아야 한다 (StaticDS/ApiDS 호환)
        'round_num'   => (int)$r['rd_no'],
        'round'       => $r['rd_no'] . '회',
        'bundle'      => $r['bundle'],
        'number'      => (int)$r['pr_no'],
        'subject'     => $r['sj_name'],
        'subject_no'  => (int)$r['sj_no'],
        'difficulty'  => $r['difficulty'],
        'question'    => $r['question'],
        'passage'     => (string)$r['passage'],
        'sql'         => (string)$r['sql_text'],
        'table'       => ex_unjson($r['table_json'], null),
        'figures'     => ex_unjson($r['figures_json'], array()),
        'choices'     => ex_unjson($r['choices_json'], array()),
        'n_choices'   => (int)$r['n_choices'],
        'answer_index'=> ($r['answer_index'] === null) ? null : (int)$r['answer_index'],
        'answer'      => $r['answer_label'],
        'explanation' => (string)$r['explanation'],
        'tags'        => ex_unjson($r['tags_json'], array()),
        'verified'    => (bool)$r['verified'],
        'reviewed'    => (bool)$r['reviewed'],
        'needs_review'=> (bool)$r['needs_review'],
    );
}

/* ── 회차 · 과목 ───────────────────────────────────────────────────────── */
$rounds = array();
$res = sql_query("select rd_no, rd_label, rd_count, rd_free
                    from ex_round where pd_id = '$pdq' and rd_open = 1
                   order by rd_no", false);
while ($r = sql_fetch_array($res)) {
    $rounds[] = array(
        'no'    => (int)$r['rd_no'],
        'label' => $r['rd_label'],
        'count' => (int)$r['rd_count'],
        'free'  => (bool)$r['rd_free'],
    );
}

// 과목은 실제로 노출 중인 문제에서 뽑는다 — ex_round 처럼 별도 테이블이 없다.
$subjects = array();
$res = sql_query("select distinct sj_no, sj_name from ex_problem
                   where pd_id = '$pdq' and pr_open = 1 and sj_name <> ''
                   order by sj_no", false);
while ($r = sql_fetch_array($res)) {
    $subjects[] = array('sj_no' => (int)$r['sj_no'], 'sj_name' => $r['sj_name']);
}

ex_out(array(
    'ok'       => 1,
    'pd'       => $pd,
    'round'    => $round,
    'problems' => $problems,
    'rounds'   => $rounds,
    'subjects' => $subjects,
));
