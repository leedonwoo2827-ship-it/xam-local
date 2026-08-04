<?php
/**
 * 문제 목록 — **실 정답률로 문제 오류를 먼저 찾는 화면.**
 *
 * 기본 정렬이 '정답률 낮은 순' 인 것이 이 화면의 전부다.
 * 정답률 20% 미만인 문항은 대개 (a) 정답이 틀렸거나 (b) 문제·보기가 모호하다.
 * 이용자 신고를 기다리면 그 사이 수백 명이 같은 문제로 헷갈린다.
 *
 * ── 왜 이게 가능한가 ───────────────────────────────────────────────────────
 * 문제를 DB 에 넣었기 때문이다. `ex_attempt_item(at_id, pr_id, chosen, is_ok)` 에
 * `KEY idx_pr (pr_id, is_ok)` 를 두었으므로 `GROUP BY pr_id` 한 번이면 문항별
 * 정답률이 나온다. 정적 JS 파일이었다면 답안과 조인할 대상이 아예 없다.
 *
 * ⚠ 표본이 작으면 정답률은 의미가 없다. 3명이 풀어 다 틀린 문제(0%)가
 *   300명이 풀어 18% 인 문제보다 위에 오면 안 된다. 그래서
 *   **기본은 `응시 N건 이상`으로 걸러서 보고**, 표본 수를 항상 함께 보여준다.
 *
 * ⚠ 검색은 `LIKE` 다. MariaDB 의 FULLTEXT 는 한국어에서 쓸모가 없다 —
 *   MySQL 8.0 의 ngram 파서가 MariaDB 에 없어서 조사가 붙은 어절이 각각
 *   다른 단어로 색인된다(_context/PLAN.md §4). 문제가 1,500행 수준이라
 *   풀스캔이 수 ms 이고 관리자 화면이라 호출 빈도도 낮다.
 *
 * ⚠ 읽기 전용이다. 편집 화면(exam_problem_form.php)은 아직 없다 —
 *   `pr_open` 토글(오류 신고 즉시 숨김)만 여기서 처리한다. 그게 오류를 발견한
 *   직후에 필요한 유일한 동작이고, 본문 수정은 `02/` 원본 → 재임포트가 정석이다.
 */
/* 600300 은 과목게시판이 쓴다 — 같은 코드를 쓰면 두 화면의 권한이 함께 움직인다.
   문제 임포트(600400) 뒤에 붙여 '문제 관련' 으로 묶는다. */
$sub_menu = '600450';
require_once './_common.php';

auth_check_menu($auth, $sub_menu, 'r');

$msg = ''; $err = '';

/* ── 처리 — pr_open 토글만 ────────────────────────────────────────────────
 * 오류를 발견한 순간 필요한 것은 '고치기' 가 아니라 '내리기' 다.
 * 고치는 데는 시간이 걸리고 그 사이에도 이용자가 계속 그 문제를 만난다.
 */
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    auth_check_menu($auth, $sub_menu, 'w');
    // 관리자 영역은 check_admin_token() 이다 — admin.js 가 토큰을 덮어쓴다
    if (function_exists('check_admin_token')) check_admin_token();
    else                                     check_token();

    $pr_id = (int)(isset($_POST['pr_id']) ? $_POST['pr_id'] : 0);
    $act   = isset($_POST['act']) ? $_POST['act'] : '';

    if ($pr_id > 0 && ($act === 'hide' || $act === 'show')) {
        $to = ($act === 'hide') ? 0 : 1;
        sql_query("update ex_problem set pr_open = $to, updated_at = '" . G5_TIME_YMDHIS . "'
                    where pr_id = $pr_id", false);
        $msg = '#' . $pr_id . ($to ? ' 를 다시 공개했습니다.' : ' 를 숨겼습니다. 이용자 화면에서 즉시 사라집니다.');
    }
}

/* ── 필터 ──────────────────────────────────────────────────────────────── */
$pd    = preg_match('/^[a-z0-9\-]{1,20}$/', isset($_GET['pd']) ? $_GET['pd'] : '') ? $_GET['pd'] : '';
$rd    = (int)(isset($_GET['rd']) ? $_GET['rd'] : 0);
$view  = isset($_GET['view']) ? $_GET['view'] : 'low';   // low|review|hidden|edited|all
$min   = isset($_GET['min']) ? (int)$_GET['min'] : 10;   // 최소 응시 수
$q     = isset($_GET['q']) ? trim($_GET['q']) : '';
$page  = max(1, (int)(isset($_GET['page']) ? $_GET['page'] : 1));
$per   = 50;
$off   = ($page - 1) * $per;
if ($min < 0) $min = 0;

$w = array('1=1');
if ($pd !== '') $w[] = "p.pd_id = '" . sql_real_escape_string($pd) . "'";
if ($rd > 0)    $w[] = "p.rd_no = $rd";
if ($q !== '') {
    $qq = sql_real_escape_string($q);
    // 문제 본문·지문·해설·pr_key 를 함께 본다. 오류 신고는 보통 본문 한 조각으로 온다.
    $w[] = "(p.question like '%$qq%' or p.passage like '%$qq%'
             or p.explanation like '%$qq%' or p.pr_key like '%$qq%')";
}
if     ($view === 'review') $w[] = "p.needs_review = 1";
elseif ($view === 'hidden') $w[] = "p.pr_open = 0";
elseif ($view === 'edited') $w[] = "p.edited_by <> ''";
$where = implode(' and ', $w);

/* ── 목록 ──────────────────────────────────────────────────────────────────
 * ★ LEFT JOIN 이다. 아무도 안 푼 문제도 목록에 있어야 한다 —
 *   INNER JOIN 이면 '응시 0건' 문제가 조용히 사라지고, 그게 하필
 *   방금 임포트한 새 회차다.
 * ★ chosen >= 0 만 센다. 미응답을 오답으로 세면 정답률이 실제보다 낮게 나와
 *   정상인 문제가 '오류 후보' 로 올라온다.
 */
$having = ($view === 'low') ? "having tries >= $min" : '';
$order  = ($view === 'low')
        ? "order by pct asc, tries desc"
        : "order by p.pd_id, p.rd_no, p.pr_no";

$sql = "select p.pr_id, p.pd_id, p.pr_key, p.rd_no, p.pr_no, p.sj_no, p.sj_name,
               p.difficulty, p.question, p.answer_label, p.needs_review, p.verified,
               p.reviewed, p.pr_open, p.edited_by, p.edited_at,
               count(i.pr_id)                                  as tries,
               coalesce(sum(i.is_ok), 0)                       as hits,
               case when count(i.pr_id) = 0 then null
                    else round(sum(i.is_ok) * 100 / count(i.pr_id), 1) end as pct
          from ex_problem p
          left join ex_attempt_item i on i.pr_id = p.pr_id and i.chosen >= 0
         where $where
         group by p.pr_id
         $having
         $order
         limit $off, $per";
$res = sql_query($sql, false);

$rows = array();
while ($res && $r = sql_fetch_array($res)) $rows[] = $r;

/* 전체 건수 — HAVING 이 붙으므로 서브쿼리로 센다 */
$cnt_sql = "select count(*) as c from (
              select p.pr_id, count(i.pr_id) as tries
                from ex_problem p
                left join ex_attempt_item i on i.pr_id = p.pr_id and i.chosen >= 0
               where $where group by p.pr_id $having) t";
$cr = sql_fetch($cnt_sql);
$total = $cr ? (int)$cr['c'] : 0;

/* ── 상단 요약 ─────────────────────────────────────────────────────────── */
$pdw = ($pd !== '') ? " and pd_id = '" . sql_real_escape_string($pd) . "'" : '';
$sum = sql_fetch("select count(*) as n,
                         sum(case when needs_review = 1 then 1 else 0 end) as review,
                         sum(case when pr_open = 0 then 1 else 0 end)      as hidden,
                         sum(case when edited_by <> '' then 1 else 0 end)  as edited
                    from ex_problem where 1=1 $pdw");
$samp = sql_fetch("select count(*) as n from ex_attempt_item i
                    join ex_problem p on p.pr_id = i.pr_id
                   where i.chosen >= 0 $pdw");
/* 가장 많이 풀린 문항의 응시 수. 이게 `min` 보다 작으면 목록이 통째로 빈다 —
   운영 초기에 반드시 겪는 상황이라 빈 화면에 그 이유를 적어줘야 한다.
   (실제로 그랬다: 응시 47건 · 문항별 1건인데 기본 필터가 10건 이상이었다) */
$mx = sql_fetch("select max(t.c) as m from (
                   select count(*) as c from ex_attempt_item i
                     join ex_problem p on p.pr_id = i.pr_id
                    where i.chosen >= 0 $pdw
                    group by i.pr_id) t");
$max_tries = $mx && $mx['m'] !== null ? (int)$mx['m'] : 0;
/* 오류 후보 — 화면 기본값과 같은 기준으로 센다 */
$cand = sql_fetch("select count(*) as c from (
                     select p.pr_id, count(i.pr_id) as tries,
                            sum(i.is_ok) * 100 / count(i.pr_id) as pct
                       from ex_problem p
                       join ex_attempt_item i on i.pr_id = p.pr_id and i.chosen >= 0
                      where p.pr_open = 1 $pdw
                      group by p.pr_id
                     having tries >= $min and pct < 20) t");

$books = array();
$res2 = sql_query("select pd_id, pd_name from ex_product order by pd_sort, pd_id", false);
while ($res2 && $r2 = sql_fetch_array($res2)) $books[] = $r2;

$rounds = array();
if ($pd !== '') {
    $res3 = sql_query("select rd_no, rd_label from ex_round
                        where pd_id = '" . sql_real_escape_string($pd) . "'
                        order by rd_no", false);
    while ($res3 && $r3 = sql_fetch_array($res3)) $rounds[] = $r3;
}

$g5['title'] = '문제 목록';
require_once './admin.head.php';

function exp_h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
function exp_url($over = array())
{
    $base = array('pd' => '', 'rd' => 0, 'view' => 'low', 'min' => 10, 'q' => '', 'page' => 1);
    foreach ($base as $k => $v) {
        $cur = isset($_GET[$k]) ? $_GET[$k] : $v;
        $base[$k] = isset($over[$k]) ? $over[$k] : $cur;
    }
    return 'exam_problem_list.php?' . http_build_query($base);
}
$VIEWS = array('low' => '정답률 낮은 순', 'review' => '검수 필요', 'hidden' => '숨김',
               'edited' => '웹 수정본', 'all' => '전체');
?>

<style>
.exprb{max-width:1400px}
.exprb .box{background:#fff;border:1px solid #e3e6ec;border-radius:8px;padding:18px 20px;margin:0 0 16px}
.exprb h2{font-size:15px;margin:0 0 12px;font-weight:700}
.exprb .msg{padding:11px 16px;border-radius:6px;margin:0 0 14px;font-size:14px;line-height:1.6}
.exprb .msg.good{background:#e9f7ef;border:1px solid #0a7f3f;color:#075c2d}
.exprb .msg.err{background:#fdeced;border:1px solid #c22638;color:#8c1220}
.exprb .audit{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;align-items:baseline}
.exprb .audit b{font-size:16px}
/* 보조 설명 — 숫자만으로는 '10건 이상' 같은 기준이 안 보인다 */
.exprb .audit small{color:#888;font-size:12px;margin-left:4px}
.exprb .audit .bad b{color:#c22638}
.exprb .tabs{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 10px}
.exprb .tabs a{display:inline-block;padding:6px 13px;border:1px solid #e3e6ec;border-radius:999px;
  background:#fff;color:#444;text-decoration:none;font-size:13px}
.exprb .tabs a.on{background:#0f172a;border-color:#0f172a;color:#fff;font-weight:700}
.exprb .srch{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:10px 0 0}
.exprb .srch input[type=text]{padding:5px 9px;border:1px solid #dde1e8;border-radius:4px;font-size:13px}
.exprb .srch input[name=q]{width:280px}
.exprb .srch input[name=min]{width:60px;text-align:right}
.exprb table.list{border-collapse:collapse;width:100%;font-size:13px}
.exprb .list th,.exprb .list td{border:1px solid #e3e6ec;padding:7px 9px;text-align:left;vertical-align:top}
.exprb .list th{background:#f7f8fa;font-weight:600;white-space:nowrap}
.exprb .list td.n{text-align:right;white-space:nowrap}
.exprb .list td.c{text-align:center;white-space:nowrap}
.exprb .q{line-height:1.6;max-width:560px}
.exprb .q small{color:#888;display:block;margin-top:2px}
.exprb .pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700}
.exprb .pill.rv{background:#fff6e5;color:#8a5a00}
.exprb .pill.hd{background:#fdeced;color:#8c1220}
.exprb .pill.ed{background:#eef2ff;color:#2c3f9e}
.exprb .pill.vf{background:#e9f7ef;color:#075c2d}
/* 정답률 — 색이 정보다. 20% 미만이 오류 후보 */
.exprb .rate{font-weight:800;font-size:14px}
.exprb .rate.r0{color:#c22638}
.exprb .rate.r1{color:#c77700}
.exprb .rate.r2{color:#0a7f3f}
.exprb .rate.rn{color:#aaa;font-weight:600}
.exprb .bar{display:block;height:4px;background:#eef0f4;border-radius:99px;margin-top:4px;width:72px}
.exprb .bar i{display:block;height:100%;border-radius:99px}
.exprb .hint{color:#666;font-size:13px;line-height:1.7}
.exprb code{background:#f4f5f7;padding:1px 5px;border-radius:3px;font-family:Consolas,monospace}
.exprb .pg{margin:14px 0 0;display:flex;gap:5px;flex-wrap:wrap}
.exprb .pg a,.exprb .pg span{padding:4px 10px;border:1px solid #e3e6ec;border-radius:4px;
  font-size:13px;text-decoration:none;color:#444}
.exprb .pg span.on{background:#0f172a;border-color:#0f172a;color:#fff;font-weight:700}
.exprb .act .btn_submit{padding:3px 9px;font-size:12px}
</style>

<div class="exprb">

<?php if ($msg): ?><div class="msg good"><?php echo exp_h($msg) ?></div><?php endif; ?>
<?php if ($err): ?><div class="msg err"><?php echo exp_h($err) ?></div><?php endif; ?>

  <div class="box">
    <h2>문제 품질</h2>
    <div class="audit">
      <span>문제 <b><?php echo number_format((int)$sum['n']) ?></b></span>
      <span class="<?php echo (int)$cand['c'] ? 'bad' : '' ?>">
        오류 후보 <b><?php echo number_format((int)$cand['c']) ?></b>
        <small>정답률 20% 미만 · 응시 <?php echo $min ?>건 이상</small></span>
      <span>검수 필요 <b><?php echo number_format((int)$sum['review']) ?></b></span>
      <span>숨김 <b><?php echo number_format((int)$sum['hidden']) ?></b></span>
      <span>웹 수정본 <b><?php echo number_format((int)$sum['edited']) ?></b></span>
      <span>응시 표본 <b><?php echo number_format((int)$samp['n']) ?></b>
        <?php if ($max_tries > 0) { ?><small>문항당 최대 <?php echo $max_tries ?>건</small><?php } ?></span>
    </div>
    <div class="hint" style="margin-top:8px">
      정답률 <b>20% 미만</b>은 대개 정답이 틀렸거나 보기가 모호한 문항이다 —
      4지선다에서 찍어도 25% 는 맞는다. 이용자 신고를 기다리지 않고 여기서 먼저 찾는다.<br>
      ⚠ <b>표본이 작으면 정답률은 의미가 없다.</b> 3명이 풀어 다 틀린 0% 가
      300명이 풀어 18% 인 문제보다 급하지 않다. 그래서 <code>응시 N건 이상</code>으로 걸러서 보고,
      표본 수를 항상 함께 표시한다.
    </div>
  </div>

  <div class="box">
    <div class="tabs">
      <?php foreach ($VIEWS as $k => $lab) { ?>
        <a href="<?php echo exp_url(array('view' => $k, 'page' => 1)) ?>"
           class="<?php echo $view === $k ? 'on' : '' ?>"><?php echo $lab ?></a>
      <?php } ?>
    </div>
    <div class="tabs">
      <a href="<?php echo exp_url(array('pd' => '', 'rd' => 0, 'page' => 1)) ?>"
         class="<?php echo $pd === '' ? 'on' : '' ?>">전 문제집</a>
      <?php foreach ($books as $b) { ?>
        <a href="<?php echo exp_url(array('pd' => $b['pd_id'], 'rd' => 0, 'page' => 1)) ?>"
           class="<?php echo $pd === $b['pd_id'] ? 'on' : '' ?>"><?php echo exp_h($b['pd_name']) ?></a>
      <?php } ?>
    </div>
    <?php if ($rounds) { ?>
    <div class="tabs">
      <a href="<?php echo exp_url(array('rd' => 0, 'page' => 1)) ?>"
         class="<?php echo $rd === 0 ? 'on' : '' ?>">전 회차</a>
      <?php foreach ($rounds as $r0) { ?>
        <a href="<?php echo exp_url(array('rd' => (int)$r0['rd_no'], 'page' => 1)) ?>"
           class="<?php echo $rd === (int)$r0['rd_no'] ? 'on' : '' ?>"><?php echo exp_h($r0['rd_label']) ?></a>
      <?php } ?>
    </div>
    <?php } ?>

    <form class="srch" method="get" action="exam_problem_list.php">
      <input type="hidden" name="pd" value="<?php echo exp_h($pd) ?>">
      <input type="hidden" name="rd" value="<?php echo (int)$rd ?>">
      <input type="hidden" name="view" value="<?php echo exp_h($view) ?>">
      <input type="text" name="q" value="<?php echo exp_h($q) ?>" placeholder="문제·지문·해설·pr_key 검색">
      <label class="hint">응시 <input type="text" name="min" value="<?php echo (int)$min ?>">건 이상</label>
      <input type="submit" class="btn_submit" value="검색">
      <span class="hint"><?php echo number_format($total) ?>건</span>
    </form>
  </div>

  <div class="box">
    <?php if (!$rows) { ?>
      <?php if ($view === 'low' && (int)$samp['n'] === 0) { ?>
        <p class="hint"><b>아직 응시 기록이 없습니다.</b>
          정답률은 회원이 채점을 시작하면 쌓입니다 — 그때까지는
          <a href="<?php echo exp_url(array('view' => 'all', 'page' => 1)) ?>">전체</a> 탭으로 보십시오.</p>
      <?php } elseif ($view === 'low' && $max_tries > 0 && $max_tries < $min) { ?>
        <?php /* 목록이 빈 게 '문제가 없다' 가 아니라 '표본이 아직 적다' 임을 말해야 한다.
                 이 안내가 없으면 화면이 고장난 것으로 읽힌다. */ ?>
        <p class="hint">
          <b>표본이 아직 적어서 걸러졌습니다.</b>
          지금 가장 많이 풀린 문항도 <b><?php echo $max_tries ?>건</b>이고
          필터가 <b><?php echo $min ?>건 이상</b>입니다.<br>
          정답률은 표본이 쌓여야 의미가 있지만, 지금 상태를 보려면
          <a href="<?php echo exp_url(array('min' => 1, 'page' => 1)) ?>"><b>응시 1건 이상으로 보기</b></a>
          — 또는 <a href="<?php echo exp_url(array('view' => 'all', 'page' => 1)) ?>">전체</a> 탭.
        </p>
      <?php } else { ?>
        <p class="hint">해당하는 문제가 없습니다.
          <?php if ($q !== '') { ?>검색어 <code><?php echo exp_h($q) ?></code> 와 일치하는 문항이 없습니다.<?php } ?></p>
      <?php } ?>
    <?php } else { ?>
      <table class="list">
        <tr>
          <th>회차·번호</th><th>과목</th><th>난이도</th>
          <th style="width:96px">정답률</th><th>응시</th>
          <th>문항</th><th>정답</th><th>상태</th><th>동작</th>
        </tr>
        <?php foreach ($rows as $r) {
            $pct   = ($r['pct'] === null) ? null : (float)$r['pct'];
            $tries = (int)$r['tries'];
            $cls   = ($pct === null) ? 'rn' : ($pct < 20 ? 'r0' : ($pct < 50 ? 'r1' : 'r2'));
            $col   = ($pct === null) ? '#ccc' : ($pct < 20 ? '#c22638' : ($pct < 50 ? '#e0930f' : '#0a7f3f'));
        ?>
        <tr<?php echo ((int)$r['pr_open'] === 0) ? ' style="background:#fcf6f6"' : '' ?>>
          <td class="c">
            <b><?php echo (int)$r['rd_no'] ?>회 <?php echo (int)$r['pr_no'] ?>번</b><br>
            <small><code><?php echo exp_h($r['pr_key']) ?></code></small>
          </td>
          <td><?php echo exp_h($r['sj_name']) ?></td>
          <td class="c"><?php echo exp_h($r['difficulty']) ?></td>
          <td class="n">
            <span class="rate <?php echo $cls ?>"><?php
              echo ($pct === null) ? '—' : $pct . '%' ?></span>
            <?php if ($pct !== null) { ?>
              <span class="bar"><i style="width:<?php echo max(2, (int)$pct) ?>%;background:<?php echo $col ?>"></i></span>
            <?php } ?>
          </td>
          <td class="n"><?php echo $tries ?>건<br><small><?php echo (int)$r['hits'] ?> 정답</small></td>
          <td class="q"><?php
            echo exp_h(mb_strimwidth(preg_replace('/\s+/u', ' ', (string)$r['question']), 0, 120, '…', 'UTF-8'));
            if ($r['edited_by'] !== '') { ?>
              <small>웹 수정 — <?php echo exp_h($r['edited_by']) ?>
                <?php echo exp_h(substr((string)$r['edited_at'], 0, 16)) ?></small>
            <?php } ?></td>
          <td class="c"><?php echo exp_h($r['answer_label']) ?></td>
          <td class="c">
            <?php if ((int)$r['pr_open'] === 0) { ?><span class="pill hd">숨김</span><?php } ?>
            <?php if ((int)$r['needs_review'] === 1) { ?><span class="pill rv">검수</span><?php } ?>
            <?php if ($r['edited_by'] !== '') { ?><span class="pill ed">수정</span><?php } ?>
            <?php if ((int)$r['verified'] === 1) { ?><span class="pill vf">확인</span><?php } ?>
          </td>
          <td class="act">
            <!-- 정답률이 낮은 문항을 발견한 직후에 필요한 것은 '숨기기' 와 '고치기' 둘이다.
                 고치는 화면(exam_problem_form.php)이 없어서 숨기기만 있었다. -->
            <a class="btn_submit" style="display:inline-block;margin-bottom:4px;text-decoration:none"
               href="exam_problem_form.php?pr_id=<?php echo (int)$r['pr_id'] ?>">보기·고치기</a>
            <form method="post" action="exam_problem_list.php?<?php echo exp_h($_SERVER['QUERY_STRING']) ?>"
                  onsubmit="return confirm('<?php echo (int)$r['pr_open'] ? '이 문제를 이용자 화면에서 숨깁니다.' : '다시 공개합니다.' ?>')">
              <?php echo isset($token) ? '<input type="hidden" name="token" value="'.$token.'">' : '' ?>
              <input type="hidden" name="pr_id" value="<?php echo (int)$r['pr_id'] ?>">
              <input type="hidden" name="act" value="<?php echo (int)$r['pr_open'] ? 'hide' : 'show' ?>">
              <input type="submit" class="btn_submit"
                     value="<?php echo (int)$r['pr_open'] ? '숨기기' : '공개' ?>">
            </form>
          </td>
        </tr>
        <?php } ?>
      </table>

      <?php $pages = (int)ceil($total / $per); if ($pages > 1) { ?>
      <div class="pg">
        <?php for ($i = 1; $i <= min($pages, 20); $i++) {
            if ($i === $page) { ?><span class="on"><?php echo $i ?></span><?php }
            else { ?><a href="<?php echo exp_url(array('page' => $i)) ?>"><?php echo $i ?></a><?php }
        } ?>
        <?php if ($pages > 20) { ?><span>… <?php echo $pages ?></span><?php } ?>
      </div>
      <?php } ?>
    <?php } ?>
  </div>

  <div class="box">
    <h2>읽는 법</h2>
    <div class="hint">
      <b>정답률 낮은 순</b>이 기본이다. 4지선다에서 찍어도 25% 는 맞으므로
      <b>20% 미만은 통계적으로 이상하다</b> — 정답 자체가 틀렸을 가능성이 가장 크다.<br>
      <b>—</b> 은 아직 아무도 안 푼 문항이다(응시 0건). 방금 임포트한 회차가 여기 있다.<br>
      <span class="pill rv">검수</span> <code>needs_review</code> — <code>02/</code> 집필 단계에서 표시된 것.
      정답률과 교차하면 <b>검수 우선순위가 자동으로 나온다.</b><br>
      <span class="pill ed">수정</span> <code>edited_by</code> 가 있는 행은
      <b>재임포트에서 건너뛴다.</b> 웹 수정본이 원본 재seed 에 덮이지 않게 하는 장치다.<br><br>

      <b>숨기기</b>는 <code>pr_open = 0</code> 이다. 이용자 화면·API 에서 즉시 사라진다.
      오류를 발견한 직후에 필요한 것은 '고치기' 가 아니라 <b>'내리기'</b>다 — 고치는 데는
      시간이 걸리고 그 사이에도 이용자가 계속 그 문제를 만난다.<br>
      ⚠ 숨겨도 <b>이미 쌓인 채점 기록은 지우지 않는다.</b> 성적표·오답노트의 과거 기록이
      깨지면 안 되기 때문이다.<br><br>

      <b>본문 수정은 여기서 하지 않는다.</b> 단일 진실 원천이 <code>02/</code>(집필 원본)이므로
      거기서 고치고 재임포트하는 것이 정석이다 — <code>pr_hash</code> 가 변경분만 UPDATE 한다.
      급한 오타 하나 때문에 원본과 DB 가 갈리는 것이 더 비싸다.
    </div>
  </div>
</div>

<?php
require_once './admin.tail.php';
