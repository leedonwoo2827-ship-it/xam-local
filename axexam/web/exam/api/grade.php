<?php
/**
 * POST /exam/api/grade.php
 *   body: {"round": 1, "keys": ["m01-1#1", ...], "answers": {"m01-1#1": 2, ...}, "filter": "..."}
 *
 * 서버 채점. 정답이 공개라도 서버에서 채점하는 이유(PLAN §3):
 *   · 오답노트·정답률이 공짜로 붙는다
 *   · 나중에 유료 회차를 만들 때 게이팅 지점이 이미 있다
 *   · 클라이언트 채점 코드가 한 벌로 줄어든다
 *
 * 비로그인도 채점은 된다. 기록만 안 남는다(회원가입 유도).
 *
 * ★ 답안 화이트리스트: 클라이언트가 보낸 키로 DB 를 조회하지 않는다.
 *   **DB 행을 순회하면서 클라이언트 답안을 찾아본다.** 방향이 반대다.
 *   그래서 임의 키를 섞어 보내도 다른 회차 정답이 샐 경로가 원리적으로 없고,
 *   키는 배열 첨자로만 쓰이므로 SQL 에 닿지도 않는다.
 */
require_once __DIR__ . '/_boot.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') ex_fail('post_only', 405);
if (!ex_same_origin())                     ex_fail('bad_origin', 403);

$mb = ex_mb();

// 로그인 회원은 기록을 남기므로 CSRF 를 요구한다.
// 비로그인은 남길 게 없어 같은 출처 검사로 충분하다.
if ($mb !== '' && !ex_csrf_ok()) ex_fail('bad_csrf', 403);

if (!ex_rate('grade', 200, 3600)) ex_fail('too_many', 429);

$body    = ex_body();
$pd      = ex_pd(isset($body['pd']) ? $body['pd'] : 'sqld');
$round   = ex_rd(isset($body['round']) ? $body['round'] : 0);
$answers = (isset($body['answers']) && is_array($body['answers'])) ? $body['answers'] : array();
$keys    = (isset($body['keys'])    && is_array($body['keys']))    ? $body['keys']    : array();
$filter  = isset($body['filter']) ? substr((string)$body['filter'], 0, 60) : '';

if ($round <= 0) ex_fail('bad_round');

/* 화면에 보이던 문제 집합(과목·난이도 필터 반영). 없으면 회차 전체를 채점한다. */
$shown = null;
if ($keys) {
    $shown = array();
    foreach ($keys as $k) {
        if (ex_valid_key($k)) $shown[(string)$k] = true;
    }
    if (!$shown) ex_fail('bad_keys');
}

/* ── 채점 ──────────────────────────────────────────────────────────────── */
$pdq = sql_real_escape_string($pd);
$res = sql_query("select pr_id, pr_key, answer_index, explanation
                    from ex_problem
                   where pd_id = '$pdq' and rd_no = " . (int)$round . " and pr_open = 1
                   order by pr_no", false);

$results = array();
$items   = array();     // ex_attempt_item 용
$ok = 0; $total = 0;

while ($r = sql_fetch_array($res)) {
    $key = $r['pr_key'];
    if ($shown !== null && !isset($shown[$key])) continue;   // 화면에 없던 문제는 건너뛴다

    $total++;
    $ai = ($r['answer_index'] === null) ? -1 : (int)$r['answer_index'];

    // 클라이언트 답안 — 유효한 형식의 키만 조회하고, 값은 정수로 강제한다
    $chosen = -1;
    if (ex_valid_key($key) && array_key_exists($key, $answers) && $answers[$key] !== null) {
        $chosen = (int)$answers[$key];
        if ($chosen < 0 || $chosen > 20) $chosen = -1;   // 보기 번호 범위 밖은 미응답 취급
    }

    $good = ($chosen >= 0 && $chosen === $ai);
    if ($good) $ok++;

    $results[] = array(
        'key'          => $key,
        'ok'           => $good,
        'chosen'       => $chosen,
        'answer_index' => $ai,
        'explanation'  => (string)$r['explanation'],
    );
    $items[] = array((int)$r['pr_id'], $chosen, $good ? 1 : 0);
}

if (!$total) ex_fail('no_problems', 404);

$pct = (int)round($ok / $total * 100);

/* ── 기록 (로그인 회원만) ──────────────────────────────────────────────── */
$at_id = 0;
if ($mb !== '' && $items) {
    ex_ext($mb);                       // ex_user_ext 없으면 생성
    $mbq = sql_real_escape_string($mb);
    $now = G5_TIME_YMDHIS;

    sql_query("insert into ex_attempt
                   (mb_id, pd_id, rd_no, at_total, at_correct, at_pct, at_sec, at_filter, created_at)
               values ('$mbq', '$pdq', " . (int)$round . ", " . (int)$total . ", " . (int)$ok . ",
                       " . (int)$pct . ", " . (int)(isset($body['sec']) ? (int)$body['sec'] : 0) . ",
                       '" . sql_real_escape_string($filter) . "', '$now')", false);
    $at_id = (int)sql_insert_id();

    if ($at_id) {
        // 50행을 한 번에 넣는다 — 문항당 쿼리 1개면 공유호스팅에서 체감된다
        $vals = array();
        foreach ($items as $it) {
            $vals[] = '(' . $at_id . ',' . (int)$it[0] . ',' . (int)$it[1] . ',' . (int)$it[2] . ')';
        }
        sql_query("insert into ex_attempt_item (at_id, pr_id, chosen, is_ok)
                        values " . implode(',', $vals), false);
    }

    /* 오답노트 — 실제로 응답한 문항만 센다. 미응답을 '틀림'으로 기록하면
       회차를 열어보기만 해도 오답이 쌓여 지표가 망가진다. */
    foreach ($items as $it) {
        list($pr_id, $chosen, $is_ok) = $it;
        if ($chosen < 0) continue;
        $wrong = $is_ok ? 0 : 1;
        sql_query("insert into ex_wrong
                       (mb_id, pr_id, try_cnt, wrong_cnt, last_chosen, last_ok, updated_at)
                   values ('$mbq', " . (int)$pr_id . ", 1, $wrong, " . (int)$chosen . ", " . (int)$is_ok . ", '$now')
                   on duplicate key update
                       try_cnt     = try_cnt + 1,
                       wrong_cnt   = wrong_cnt + $wrong,
                       last_chosen = " . (int)$chosen . ",
                       last_ok     = " . (int)$is_ok . ",
                       updated_at  = '$now'", false);
    }

    ex_log('grade', 'rd:' . $round);
}

ex_out(array(
    'ok'      => 1,
    'login'   => $mb !== '' ? 1 : 0,
    'at_id'   => $at_id,
    'score'   => array('correct' => $ok, 'total' => $total, 'pct' => $pct),
    'results' => $results,
));
