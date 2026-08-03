<?php
/**
 * GET /exam/api/report.php?pd=sqld[&at_id=123]
 *
 * 성적표(분석 리포트) 데이터. at_id 를 안 주면 **가장 최근 응시**를 쓴다.
 *
 * ── 정책: 무료 회차의 성적표는 누구나, 나머지는 수강생 ──────────────────────
 *
 * 판정 기준은 **회차**다. `ex_round.rd_free` 를 본다 —
 * 스키마가 처음부터 그 컬럼을 "무료 공개 스위치"로 예약해뒀다(schema.sql §3).
 * SQLD 21회차 중 1회차만 무료로 열려면:
 *
 *   UPDATE ex_round SET rd_free = 0 WHERE pd_id = 'sqld' AND rd_no > 1;
 *
 * 왜 '열람 횟수' 가 아니라 '회차' 인가
 *   열람으로 세면 새로고침·재방문에 소진된다. 이용자는 자기가 뭘 잘못했는지 모르고
 *   억울해하고, 문의가 온다. 회차 기준이면 소진되지 않고 규칙이 한 줄로 설명된다 —
 *   "1회차 성적표는 무료로 보여드립니다." 같은 회차를 몇 번 다시 풀어도 계속 볼 수 있다.
 *   ⚠ 문제 임포트가 rd_free 를 건드리지 않는다(exam_import.php) — 재임포트해도 설정이 유지된다.
 *
 * 왜 잠글 때도 점수는 주는가
 *   점수·합격 판정은 채점 화면에서 이미 봤다. 가려도 아무것도 지키지 못하면서
 *   "돈 내라" 만 남는다. 분석(과목별·취약개념·문항별·누적오답)만 가리고,
 *   **몇 개가 있는지는 숫자로 알려준다.** 그래야 무엇을 사는지가 보인다.
 *   완전 잠금은 전환율이 낮다.
 *
 * 전면 공개로 되돌리려면 ex_product.pd_config 에 {"report":{"free_all":true}}.
 * 정책을 바꿀 때 코드를 만지지 않는다.
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
require_once __DIR__ . '/lib/sample.php';

/* 샘플(데모) — 로그인 없이 열린다. 회원 테이블을 한 줄도 읽지 않는다.
   근거와 안전장치는 lib/sample.php 주석 참조. */
$sample = ex_sample_on();

$mb = ex_mb();
if ($mb === '' && !$sample) ex_fail('login_required', 401);

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
$sheet = null;
if ($sample) {
    /* ex_attempt 을 아예 조회하지 않는다 — 샘플이 남의 성적표를 여는 뒷문이 되면 안 된다. */
    $sheet = ex_sample_sheet($pd, isset($_GET['rd']) ? (int)$_GET['rd'] : 1);
    if (!$sheet) ex_fail('no_problems', 404);
    $at = array(
        'at_id' => 0, 'rd_no' => $sheet['rd_no'],
        'at_total' => $sheet['total'], 'at_correct' => $sheet['correct'],
        'at_pct' => $sheet['pct'], 'at_sec' => 2340,
        'at_filter' => '', 'created_at' => $sheet['at'],
    );
    $at_id = 0;
} elseif ($at_id > 0) {
    $at = sql_fetch("select * from ex_attempt
                      where at_id = $at_id and mb_id = '$mbq' and pd_id = '$pdq'");
} else {
    $at = sql_fetch("select * from ex_attempt
                      where mb_id = '$mbq' and pd_id = '$pdq'
                      order by at_id desc limit 1");
}
if (!$at) ex_fail('no_attempt', 404);
if (!$sample) $at_id = (int)$at['at_id'];

/* ── 합격 기준 ──────────────────────────────────────────────────────────────
 * 자격증마다 다르므로 ex_product.pd_config 에 둔다 — 코드 수정 없이 DB 로 바뀐다.
 *   {"pass": {"total": 60, "subject": 40}}
 * 기본값은 SQLD 기준(총점 60점 이상 · 과목별 40% 이상). 과목 기준을 0 으로 두면 과락 없음.
 */
$cfg  = ex_unjson($prod['pd_config'], array());
$pass = (is_array($cfg) && isset($cfg['pass']) && is_array($cfg['pass'])) ? $cfg['pass'] : array();
$pass_total = isset($pass['total']) ? (int)$pass['total'] : 60;
$pass_subj  = isset($pass['subject']) ? (int)$pass['subject'] : 40;

/* ── 열람 권한 ──────────────────────────────────────────────────────────────
 * 회차 단위다. ex_round.rd_free = 1 이면 누구나, 0 이면 수강생만.
 * PK 가 (pd_id, rd_no) 라 **문제집마다 무료 회차를 다르게** 고를 수 있다.
 */
$rd_no = (int)$at['rd_no'];
$rd = sql_fetch("select rd_free, rd_label from ex_round
                  where pd_id = '$pdq' and rd_no = " . $rd_no);
$free_round = $rd ? ((int)$rd['rd_free'] === 1) : false;

// 수강생 — ex_entitlement 에 (회원, 문제집) 행이 있으면 전 회차 열람
$entitled = false;
if (!$sample) {
    $ent = sql_fetch("select mb_id from ex_entitlement where mb_id = '$mbq' and pd_id = '$pdq'");
    $entitled = !empty($ent);
}

$rcfg = (is_array($cfg) && isset($cfg['report']) && is_array($cfg['report'])) ? $cfg['report'] : array();
$free_all = !empty($rcfg['free_all']);

/* 샘플은 잠그지 않는다 — 잠근 샘플은 아무것도 보여주지 못해 존재 이유가 없다.
   진짜 회차의 유료 게이트와는 무관하다(샘플은 회원 응시 기록을 읽지 않는다). */
$locked = $sample ? false : !($free_all || $free_round || $entitled || ex_is_admin());

/* ── 문항별 ─────────────────────────────────────────────────────────────────
 * ex_attempt_item 이 pr_id 를 들고 있으므로 ex_problem 과 조인해 과목·난이도·본문을 붙인다.
 * choices_json 은 내보내지 않는다 — 성적표에 보기 전문까지 넣으면 응답이 커지고,
 * 문제를 다시 보려면 문제 화면으로 가는 게 맞다.
 */
$items = array();
/* 샘플은 합성 답안지를, 실제는 ex_attempt_item 조인을 흘려보낸다.
   ★ 아래 집계 전부(과목·난이도·태그·판정)는 두 경우에 **같은 코드가 돈다** —
     샘플 전용 집계를 따로 만들면 화면이 바뀔 때 한쪽만 낡는다. */
if ($sample) {
    $res = $sheet['rows'];
} else {
    $res = sql_query("select i.pr_id, i.chosen, i.is_ok,
                             p.pr_key, p.pr_no, p.rd_no, p.sj_no, p.sj_name, p.difficulty,
                             p.question, p.answer_index, p.answer_label, p.tags_json
                        from ex_attempt_item i
                        join ex_problem p on p.pr_id = i.pr_id
                       where i.at_id = $at_id
                       order by p.pr_no", false);
}
while ($r = ($sample ? array_shift($res) : ($res ? sql_fetch_array($res) : null))) {
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
/* 샘플은 누적이 없다 — ex_wrong 은 회원 테이블이라 읽지 않는다.
   '반복 오답' 블록은 데이터가 없으면 화면이 스스로 감춘다. */
$res = $sample ? false : sql_query("select w.pr_id, w.try_cnt, w.wrong_cnt, w.last_chosen, w.last_ok,
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
$res = $sample ? false : sql_query("select at_id, rd_no, at_pct, created_at from ex_attempt
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

/* ── 응답 ───────────────────────────────────────────────────────────────────
 * 잠긴 회차는 **분석을 응답에 담지 않는다.** 화면에서 가리는 것만으로는 소용없다 —
 * 개발자도구로 응답을 열면 다 보인다. 서버가 안 보내는 것이 유일한 게이트다.
 *
 * 대신 '몇 개가 있는지' 는 숫자로 준다. 그게 무엇을 사는지 보여준다.
 * 점수·합격 판정은 채점 화면에서 이미 본 값이라 가리지 않는다.
 */
$out = array(
    'ok'      => 1,
    'pd'      => $pd,
    'pd_name' => $prod['pd_name'],
    'attempt' => array(
        'at_id'   => $at_id,
        'rd_no'   => $rd_no,
        'rd_label'=> $rd ? $rd['rd_label'] : ($rd_no . '회'),
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
    'access' => array(
        'locked'     => $locked ? 1 : 0,
        'free_round' => $free_round ? 1 : 0,
        'entitled'   => $entitled ? 1 : 0,
    ),
);

if ($locked) {
    // 무료로 열려 있는 회차 목록 — "1회차는 무료입니다" 를 화면이 정확히 안내할 수 있게
    $free_list = array();
    $res = sql_query("select rd_no, rd_label from ex_round
                       where pd_id = '$pdq' and rd_free = 1 and rd_open = 1
                       order by rd_no", false);
    while ($res && $r = sql_fetch_array($res)) {
        $free_list[] = array('rd_no' => (int)$r['rd_no'], 'label' => $r['rd_label']);
    }

    $weak_subj = 0;
    foreach ($subjects as $s) if ($s['band'] === 'weak' || $s['band'] === 'fail') $weak_subj++;

    $out['teaser'] = array(
        'weak_subjects' => $weak_subj,          // 보완이 필요한 과목 수
        'weak_tags'     => count($weak),        // 취약 개념 수
        'wrong'         => count(array_filter($items, function ($x) { return !$x['ok']; })),
        'repeat'        => count($repeat),       // 계속 틀리는 문제 수
        'free_rounds'   => $free_list,
    );
} else {
    $out['subjects']   = $subjects;
    $out['difficulty'] = $difficulty;
    $out['weak']       = $weak;
    $out['repeat']     = $repeat;
    $out['trend']      = $trend;
    $out['items']      = $items;
}

ex_out($out);
