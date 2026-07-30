<?php
/**
 * GET /exam/api/report.php?pd=sqld[&at_id=123]
 *
 * 성적표(분석 리포트) 데이터. at_id 를 안 주면 **가장 최근 응시**를 쓴다.
 *
 * ── 정책: 로그인 회원 무료 ─────────────────────────────────────────────────
 * 오답노트와 같은 취급이다(schema.sql §14 주석: "회원에게 무료로 준다.
 * 유료 가치는 Q&A 에 있고 이건 재방문 유도 장치다").
 *
 * 성적표를 유료로 막으면 안 되는 이유가 명확하다 — 성적표는 **"네가 약한 곳이 여기다"**
 * 를 보여주는 화면이고, 그게 곧 질문할 이유를 만든다. 유료 전환의 입구를 잠그는 셈이 된다.
 * 비용이 드는 것(LLM 맞춤 코멘트)만 나중에 수강생으로 제한한다.
 *
 * ⚠ 비회원은 채점 기록이 남지 않는다(grade.php 는 mb_id 가 있을 때만 INSERT).
 *   그래서 성적표는 원리적으로 로그인이 필요하다 — 정책이 아니라 구조다.
 *
 * ── 새 테이블이 없다 ───────────────────────────────────────────────────────
 *   문항별 정오   ex_attempt_item
 *   점수·회차·시각 ex_attempt
 *   과목·난이도   ex_problem.sj_no / sj_name / difficulty
 *   취약 개념     ex_problem.tags_json
 *   누적 오답     ex_wrong (try_cnt, wrong_cnt)
 */
require_once __DIR__ . '/_boot.php';

$mb = ex_mb();
if ($mb === '') ex_fail('login_required', 401);

$pd    = ex_pd(isset($_GET['pd']) ? $_GET['pd'] : '', '');
$at_id = isset($_GET['at_id']) ? (int)$_GET['at_id'] : 0;
if ($pd === '') ex_fail('pd_required');

$mbq = sql_real_escape_string($mb);
$pdq = sql_real_escape_string($pd);

$prod = sql_fetch("select pd_id, pd_name, pd_config from ex_product where pd_id = '$pdq'");
if (!$prod) ex_fail('no_such_product', 404);

/* ── 응시 회차 ──────────────────────────────────────────────────────────────
 * ★ mb_id 를 WHERE 에 넣는다. at_id 만으로 찾으면 **남의 성적표를 볼 수 있다** —
 *   at_id 는 연속된 정수라 남의 것을 맞히기 쉽다.
 */
if ($at_id > 0) {
    $at = sql_fetch("select * from ex_attempt
                      where at_id = $at_id and mb_id = '$mbq' and pd_id = '$pdq'");
} else {
    $at = sql_fetch("select * from ex_attempt
                      where mb_id = '$mbq' and pd_id = '$pdq'
                      order by at_id desc limit 1");
}
if (!$at) ex_fail('no_attempt', 404);
$at_id = (int)$at['at_id'];

/* ── 합격 기준 ──────────────────────────────────────────────────────────────
 * 자격증마다 다르므로 ex_product.pd_config 에 둔다 — 코드 수정 없이 DB 로 바뀐다.
 *   {"pass": {"total": 60, "subject": 40}}
 * 기본값은 SQLD 기준(총점 60점 이상 · 과목별 40% 이상). 과목 기준을 0 으로 두면 과락 없음.
 */
$cfg  = ex_unjson($prod['pd_config'], array());
$pass = (is_array($cfg) && isset($cfg['pass']) && is_array($cfg['pass'])) ? $cfg['pass'] : array();
$pass_total = isset($pass['total']) ? (int)$pass['total'] : 60;
$pass_subj  = isset($pass['subject']) ? (int)$pass['subject'] : 40;

/* ── 문항별 ─────────────────────────────────────────────────────────────────
 * ex_attempt_item 이 pr_id 를 들고 있으므로 ex_problem 과 조인해 과목·난이도·본문을 붙인다.
 * choices_json 은 내보내지 않는다 — 성적표에 보기 전문까지 넣으면 응답이 커지고,
 * 문제를 다시 보려면 문제 화면으로 가는 게 맞다.
 */
$items = array();
$res = sql_query("select i.pr_id, i.chosen, i.is_ok,
                         p.pr_key, p.pr_no, p.rd_no, p.sj_no, p.sj_name, p.difficulty,
                         p.question, p.answer_index, p.answer_label, p.tags_json
                    from ex_attempt_item i
                    join ex_problem p on p.pr_id = i.pr_id
                   where i.at_id = $at_id
                   order by p.pr_no", false);
while ($res && $r = sql_fetch_array($res)) {
    $items[] = array(
        'pr_id'    => (int)$r['pr_id'],
        'pr_key'   => $r['pr_key'],
        'no'       => (int)$r['pr_no'],
        'sj_no'    => (int)$r['sj_no'],
        'sj_name'  => $r['sj_name'],
        'df'       => $r['difficulty'],
        'chosen'   => (int)$r['chosen'],
        'answer'   => $r['answer_index'] === null ? -1 : (int)$r['answer_index'],
        'label'    => $r['answer_label'],
        'ok'       => (int)$r['is_ok'],
        // 제목처럼 짧게. 전문은 문제 화면에서 본다.
        'q'        => mb_strimwidth(preg_replace('/\s+/u', ' ', (string)$r['question']), 0, 90, '…', 'UTF-8'),
        '_tags'    => ex_unjson($r['tags_json'], array()),
    );
}
if (!$items) ex_fail('no_items', 404);

/* ── 과목별 집계 ────────────────────────────────────────────────────────── */
$sj = array();
foreach ($items as $it) {
    $k = $it['sj_no'] . '|' . $it['sj_name'];
    if (!isset($sj[$k])) $sj[$k] = array('sj_no'=>$it['sj_no'], 'sj_name'=>$it['sj_name'],
                                         'total'=>0, 'correct'=>0, 'skipped'=>0);
    $sj[$k]['total']++;
    if ($it['ok']) $sj[$k]['correct']++;
    if ($it['chosen'] < 0) $sj[$k]['skipped']++;
}
$subjects = array();
foreach ($sj as $s) {
    $s['pct'] = $s['total'] ? (int)round($s['correct'] / $s['total'] * 100) : 0;
    /* 3단계 판정. '보완필요 / 일부보완 / 양호' 는 리포트 레퍼런스의 구분을 따른다.
       과락선(pass_subj)이 있으면 그 아래는 무조건 보완필요다 — 총점이 높아도 떨어진다. */
    if ($pass_subj > 0 && $s['pct'] < $pass_subj) $s['band'] = 'fail';
    elseif ($s['pct'] < 60)                        $s['band'] = 'weak';
    elseif ($s['pct'] < 80)                        $s['band'] = 'mid';
    else                                           $s['band'] = 'good';
    $subjects[] = $s;
}
usort($subjects, function ($a, $b) { return $a['sj_no'] - $b['sj_no']; });

/* ── 난이도별 ───────────────────────────────────────────────────────────── */
$dfm = array();
foreach ($items as $it) {
    $d = $it['df'] !== '' ? $it['df'] : '미분류';
    if (!isset($dfm[$d])) $dfm[$d] = array('df'=>$d, 'total'=>0, 'correct'=>0);
    $dfm[$d]['total']++;
    if ($it['ok']) $dfm[$d]['correct']++;
}
$ORDER = array('하'=>1, '중'=>2, '상'=>3, '미분류'=>9);
$difficulty = array();
foreach ($dfm as $d) {
    $d['pct'] = $d['total'] ? (int)round($d['correct'] / $d['total'] * 100) : 0;
    $difficulty[] = $d;
}
usort($difficulty, function ($a, $b) use ($ORDER) {
    $x = isset($ORDER[$a['df']]) ? $ORDER[$a['df']] : 5;
    $y = isset($ORDER[$b['df']]) ? $ORDER[$b['df']] : 5;
    return $x - $y;
});

/* ── 취약 개념 ──────────────────────────────────────────────────────────────
 * tags_json 을 집계한다. 과목보다 좁은 단위라 "무엇을 다시 볼지" 가 구체적으로 나온다.
 * 정답률이 낮은 태그를 앞으로. 표본이 1개인 태그는 우연이라 2개 이상만 본다.
 */
$tag = array();
foreach ($items as $it) {
    foreach ((array)$it['_tags'] as $t) {
        $t = trim((string)$t);
        if ($t === '') continue;
        if (!isset($tag[$t])) $tag[$t] = array('tag'=>$t, 'total'=>0, 'wrong'=>0);
        $tag[$t]['total']++;
        if (!$it['ok']) $tag[$t]['wrong']++;
    }
}
$weak = array();
foreach ($tag as $t) {
    if ($t['total'] < 2 && $t['wrong'] < 1) continue;      // 표본 1개 + 맞힘 → 의미 없음
    if ($t['wrong'] === 0) continue;                        // 다 맞힌 개념은 취약이 아니다
    $t['pct'] = (int)round(($t['total'] - $t['wrong']) / $t['total'] * 100);
    $weak[] = $t;
}
usort($weak, function ($a, $b) {
    if ($a['pct'] !== $b['pct']) return $a['pct'] - $b['pct'];    // 정답률 낮은 것 먼저
    return $b['wrong'] - $a['wrong'];                             // 같으면 많이 틀린 것
});
$weak = array_slice($weak, 0, 12);

/* ── 반복 오답 ──────────────────────────────────────────────────────────────
 * 이번 회차가 아니라 **누적**이다(ex_wrong). "계속 틀리는 문제" 는 이번 점수보다 중요하다.
 */
$repeat = array();
$res = sql_query("select w.pr_id, w.try_cnt, w.wrong_cnt, w.last_chosen, w.last_ok,
                         p.pr_key, p.pr_no, p.rd_no, p.sj_name, p.question
                    from ex_wrong w
                    join ex_problem p on p.pr_id = w.pr_id
                   where w.mb_id = '$mbq' and p.pd_id = '$pdq'
                     and w.wrong_cnt >= 2 and w.last_ok = 0
                   order by w.wrong_cnt desc, w.updated_at desc
                   limit 10", false);
while ($res && $r = sql_fetch_array($res)) {
    $repeat[] = array(
        'pr_key'  => $r['pr_key'],
        'rd_no'   => (int)$r['rd_no'],
        'no'      => (int)$r['pr_no'],
        'sj_name' => $r['sj_name'],
        'try'     => (int)$r['try_cnt'],
        'wrong'   => (int)$r['wrong_cnt'],
        'q'       => mb_strimwidth(preg_replace('/\s+/u', ' ', (string)$r['question']), 0, 80, '…', 'UTF-8'),
    );
}

/* ── 점수 추이 ──────────────────────────────────────────────────────────────
 * 같은 회차만 비교해도 되지만, 회차가 달라도 '전체 흐름'이 동기부여가 된다.
 * 오래된 것 → 최신 순으로 준다(차트가 왼쪽부터 그리게).
 */
$trend = array();
$res = sql_query("select at_id, rd_no, at_pct, created_at from ex_attempt
                   where mb_id = '$mbq' and pd_id = '$pdq'
                   order by at_id desc limit 10", false);
while ($res && $r = sql_fetch_array($res)) {
    $trend[] = array('at_id'=>(int)$r['at_id'], 'rd_no'=>(int)$r['rd_no'],
                     'pct'=>(int)$r['at_pct'], 'at'=>substr($r['created_at'], 2, 8));
}
$trend = array_reverse($trend);

/* ── 판정 ───────────────────────────────────────────────────────────────── */
$pct = (int)$at['at_pct'];
$fail_subjects = array();
foreach ($subjects as $s) {
    if ($pass_subj > 0 && $s['pct'] < $pass_subj) $fail_subjects[] = $s['sj_name'];
}
$judge = ($pct >= $pass_total && !$fail_subjects) ? 'pass' : 'fail';

/* 미응답이 많으면 점수 자체가 의미가 없다. 화면이 그걸 먼저 말해야 한다. */
$skipped = 0;
foreach ($items as $it) if ($it['chosen'] < 0) $skipped++;

// 내부 필드 제거 — 응답에 tags 배열까지 실을 이유가 없다
foreach ($items as &$it) unset($it['_tags']);
unset($it);

ex_out(array(
    'ok'      => 1,
    'pd'      => $pd,
    'pd_name' => $prod['pd_name'],
    'attempt' => array(
        'at_id'   => $at_id,
        'rd_no'   => (int)$at['rd_no'],
        'total'   => (int)$at['at_total'],
        'correct' => (int)$at['at_correct'],
        'pct'     => $pct,
        'sec'     => (int)$at['at_sec'],
        'filter'  => $at['at_filter'],
        'at'      => $at['created_at'],
        'skipped' => $skipped,
    ),
    'pass' => array(
        'total_line'   => $pass_total,
        'subject_line' => $pass_subj,
        'judge'        => $judge,
        'fail_subjects'=> $fail_subjects,
    ),
    'subjects'   => $subjects,
    'difficulty' => $difficulty,
    'weak'       => $weak,
    'repeat'     => $repeat,
    'trend'      => $trend,
    'items'      => $items,
));
