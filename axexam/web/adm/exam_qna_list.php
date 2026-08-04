<?php
/**
 * 질문 검수 — 목록.
 *
 * 제품의 핵심이다. 문제 풀다 막힌 회원이 질문하고, 여기서 답이 나간다.
 * (과목게시판은 이 데이터를 이용자 쪽에서 보여주는 화면이고, 원장은 ex_qna 다)
 *
 * 상태 흐름:  pending → drafting → draft_ready → approved | rejected
 *   · pending      회원이 질문함. 답변 대기
 *   · drafting     LLM 초안 생성 중 (S8. 아직 안 붙였다)
 *   · draft_ready  초안 나옴. 관리자 검수 대기
 *   · approved     관리자가 확정 → **이용자에게 공개된다**
 *   · rejected     반려 → 포인트 환불
 *
 * ★ qa_draft(LLM 초안)는 회원 API 로 절대 나가지 않는다(api/qna.php 의 SELECT 목록에 없다).
 *   관리자 화면이 유일한 예외다 — 검수하려면 봐야 한다.
 */
$sub_menu = '600200';
require_once './_common.php';

auth_check_menu($auth, $sub_menu, 'r');

require_once './exam_lib/board_qna.php';   // 게시판 ↔ ex_qna 다리
require_once './exam_lib/prompt.php';      // ex_draft_one()

$msg = ''; $err = ''; $warns = array();

/* ── 처리 ──────────────────────────────────────────────────────────────────
 *
 * ★ 필터는 계속 $_GET 에서 읽는다. 아래 폼들이 `action="<?= $qs() ?>"` 로 **현재
 *   쿼리스트링을 그대로 달고** POST 하므로, 처리 후에도 보고 있던 탭·문제집이 유지된다.
 *   ($_REQUEST 로 바꾸면 필터 파싱 전체의 신뢰 경계가 넓어진다.)
 *
 * ★ 처리를 조회보다 먼저 둔다. 뒤에 두면 방금 가져온 질문이 목록에 안 보인다.
 */
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    auth_check_menu($auth, $sub_menu, 'w');
    if (function_exists('check_admin_token')) check_admin_token();
    else                                     check_token();

    $act = isset($_POST['act']) ? $_POST['act'] : '';

    if ($act === 'pull') {
        /* 게시판 원글 → ex_qna. 문제집이 선택돼 있으면 그것만, 아니면 열린 것 전부. */
        $targets = array();
        $pp = isset($_POST['pull_pd']) ? preg_replace('/[^a-z0-9\-]/', '', $_POST['pull_pd']) : '';
        if ($pp !== '') {
            $targets[] = $pp;
        } else {
            $r2 = sql_query("select pd_id from ex_product where pd_open = 1 order by pd_sort, pd_id", false);
            while ($r2 && $x = sql_fetch_array($r2)) $targets[] = $x['pd_id'];
        }

        $tot_new = 0; $lines = array();
        foreach ($targets as $t) {
            $r = exbq_pull_board($t, $member['mb_id']);
            if (empty($r['ok'])) { $warns[] = $t . ' — ' . $r['msg']; continue; }
            $tot_new += (int)$r['new'];
            $lines[] = $t . ' ' . (int)$r['new'] . '건';
            // ★ 상한에 걸려 남은 것은 반드시 알린다. 조용히 잘리면 '다 가져왔다'고 믿는다.
            if (!empty($r['more'])) $warns[] = $t . ' — 남은 글이 더 있습니다. 한 번 더 누르십시오.';
            foreach ($r['fail'] as $f) $warns[] = $f;
        }
        $msg = $tot_new
             ? ('게시판에서 ' . $tot_new . '건을 가져왔습니다 (' . implode(' · ', $lines) . '). '
                . '이제 체크해서 [선택 초안 요청] 을 누르십시오.')
             : '새로 가져올 글이 없습니다. 이미 다 등록돼 있습니다.';

    } elseif ($act === 'draft') {
        /* 선택 건 초안 일괄 생성.
         *
         * ★ 벽시계 예산으로 끊는다. 초안 1건은 LLM 호출이라 최대 60초까지 걸린다
         *   (llm.php 의 timeout). 10건을 한 번에 돌리면 PHP max_execution_time 이
         *   먼저 죽고, **어디까지 처리됐는지 모른 채 화면이 끊긴다.**
         *   그래서 예산을 넘기면 멈추고 "몇 건 남았다"를 돌려준다. 서버 설정이
         *   무엇이든 같은 방식으로 동작한다.
         */
        @set_time_limit(0);
        $BUDGET = 100;                       // 초. 카페24 기본 제한(대개 300)보다 넉넉히 안쪽
        $t0 = microtime(true);

        $ids = isset($_POST['chk']) && is_array($_POST['chk']) ? $_POST['chk'] : array();
        $ids = array_values(array_unique(array_map('intval', $ids)));

        if (!$ids) {
            $err = '초안을 만들 질문을 먼저 체크해 주십시오.';
        } else {
            $ok = 0; $ng = 0; $left = 0; $cost = 0.0; $over = 0;
            foreach ($ids as $i => $id) {
                if (microtime(true) - $t0 > $BUDGET) { $left = count($ids) - $i; break; }
                $r = ex_draft_one($id, $member['mb_id']);
                if (!empty($r['ok'])) {
                    $ok++;
                    $cost += (float)$r['cost'];
                    if (!empty($r['over_cap'])) $over++;
                } else {
                    $ng++;
                    $warns[] = $r['msg'];
                }
            }
            $msg = '초안 ' . $ok . '건 생성 · 원가 ' . number_format($cost, 4) . '원';
            if ($ng)   $msg .= ' · 실패 ' . $ng . '건';
            if ($over) $msg .= ' · 원가 상한 초과 ' . $over . '건';
            if ($left) {
                $msg .= ' · ' . $left . '건은 시간이 부족해 남겼습니다 — 다시 체크해서 눌러 주십시오.';
            }
            if ($ok) $msg .= '  이제 한 건씩 열어 초안을 검수·승인하십시오.';
        }
    }
}

/* ── 필터 ──────────────────────────────────────────────────────────────── */
$st   = isset($_GET['st'])   ? preg_replace('/[^a-z_]/', '', $_GET['st'])       : 'open';
$pd   = isset($_GET['pd'])   ? preg_replace('/[^a-z0-9\-]/', '', $_GET['pd'])   : '';
$kind = isset($_GET['kind']) ? preg_replace('/[^a-z]/', '', $_GET['kind'])      : '';
$sj   = isset($_GET['sj'])   ? (int)$_GET['sj']                                  : -1;
$stx  = isset($_GET['stx'])  ? trim($_GET['stx'])                                : '';
$page = max(1, (int)(isset($_GET['page']) ? $_GET['page'] : 1));
$per  = 30;

$w = array('1=1');
// 'open' = 아직 답이 안 나간 것 전부. 검수자가 가장 자주 보는 화면이라 기본값으로 둔다.
if     ($st === 'open') $w[] = "q.qa_status in ('pending','drafting','draft_ready')";
elseif ($st !== 'all' && $st !== '') $w[] = "q.qa_status = '" . sql_real_escape_string($st) . "'";
if ($pd !== '')   $w[] = "q.pd_id = '" . sql_real_escape_string($pd) . "'";
if ($kind !== '') $w[] = "q.kind = '" . sql_real_escape_string($kind) . "'";
if ($sj >= 0)     $w[] = "q.sj_no = " . $sj;
// LIKE 로 검색한다. FULLTEXT 를 안 쓰는 이유는 schema.sql 머리 주석에 있다 —
// MariaDB 기본 토크나이저는 공백 기준이라 조사가 붙는 한국어에서 무용지물이다.
if ($stx !== '') {
    $e = sql_real_escape_string($stx);
    $w[] = "(q.qa_question like '%$e%' or q.qa_answer like '%$e%' or q.mb_id like '%$e%')";
}
$where = implode(' and ', $w);

$cnt   = sql_fetch("select count(*) as c from ex_qna q where $where");
$total = (int)$cnt['c'];
$off   = ($page - 1) * $per;

$rows = array();
$res = sql_query("select q.qa_id, q.mb_id, q.pd_id, q.kind, q.pr_key, q.sj_no,
                         q.bo_table, q.wr_id, q.qa_question, q.qa_status, q.qa_answer,
                         q.qa_draft is not null as has_draft,
                         q.cost_units, q.qa_credit_ok, q.qa_refunded, q.qa_public,
                         q.created_at, q.qa_answered_at,
                         d.pd_name, m.mb_nick,
                         p.sj_name, p.rd_no, p.pr_no
                    from ex_qna q
                    left join ex_product d on d.pd_id = q.pd_id
                    left join g5_member  m on m.mb_id = q.mb_id
                    left join ex_problem p on p.pd_id = q.pd_id and p.pr_key = q.pr_key
                   where $where
                   order by
                     -- 검수 대기(draft_ready)를 맨 위로, 그 다음 오래된 질문 순.
                     -- 오래 기다린 사람이 먼저 답을 받아야 한다.
                     field(q.qa_status,'draft_ready','pending','drafting') desc,
                     q.qa_id asc
                   limit $off, $per", false);
while ($r = sql_fetch_array($res)) $rows[] = $r;

/* 상태별 건수 */
$counts = array();
$res = sql_query("select qa_status, count(*) as c from ex_qna group by qa_status", false);
while ($r = sql_fetch_array($res)) $counts[$r['qa_status']] = (int)$r['c'];
$open_n = (isset($counts['pending']) ? $counts['pending'] : 0)
        + (isset($counts['drafting']) ? $counts['drafting'] : 0)
        + (isset($counts['draft_ready']) ? $counts['draft_ready'] : 0);

$prods = array();
$res = sql_query("select pd_id, pd_name from ex_product order by pd_sort, pd_id", false);
while ($r = sql_fetch_array($res)) $prods[] = $r;

/* 초안 1건의 원가 상한 — 확인창에 "N건 · 최대 M원" 을 적기 위한 값이다.
   문제집마다 다를 수 있으니 **가장 큰 값**을 쓴다. 적게 어림하면 안 된다. */
$cap1 = sql_fetch("select max(cost_cap) as c from ex_product where pd_open = 1");
$CAP1 = $cap1 ? (float)$cap1['c'] : 3.0;

/* 아직 ex_qna 로 안 들어온 게시판 글이 몇 건인가 — [가져오기] 버튼 옆에 띄운다.
   0 이면 버튼을 눌러도 아무 일이 없으므로, 누르기 전에 알려 준다. */
$pending_board = 0;
$board_missing = array();
$res = sql_query("select pd_id from ex_product where pd_open = 1 order by pd_sort, pd_id", false);
while ($res && $r = sql_fetch_array($res)) {
    $bo = exbq_bo($r['pd_id']);
    if (!exbq_board_exists($bo)) { $board_missing[] = $r['pd_id'] . ' → ' . $bo; continue; }
    $wt  = exbq_wt($bo);
    $boq = sql_real_escape_string($bo);
    $c = sql_fetch("select count(*) as c from `$wt` w
                     where w.wr_is_comment = 0
                       and not exists (select 1 from ex_qna q
                                        where q.bo_table = '$boq' and q.wr_id = w.wr_id)");
    if ($c) $pending_board += (int)$c['c'];
}

/* 과목 목록 — 선택된 문제집이 있을 때만. 문제집마다 과목이 달라 섞으면 의미가 없다. */
$subs = array();
if ($pd !== '') {
    $res = sql_query("select distinct sj_no, sj_name from ex_problem
                       where pd_id = '" . sql_real_escape_string($pd) . "' and sj_no > 0
                       order by sj_no", false);
    while ($r = sql_fetch_array($res)) $subs[] = $r;
}

$g5['title'] = '질문 검수';
require_once './admin.head.php';

function exq_h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
function exq_cut($s, $n = 90) {
    $s = preg_replace('/\s+/u', ' ', (string)$s);
    return mb_strlen($s, 'UTF-8') > $n ? mb_substr($s, 0, $n, 'UTF-8') . '…' : $s;
}

$ST = array(
    'pending'     => array('wait', '대기'),
    'drafting'    => array('wait', '초안 생성 중'),
    'draft_ready' => array('rev',  '검수 대기'),
    'approved'    => array('ok',   '완료'),
    'rejected'    => array('no',   '반려'),
);
$qs = function ($over = array()) use ($st, $pd, $kind, $sj, $stx) {
    $a = array('st' => $st, 'pd' => $pd, 'kind' => $kind, 'sj' => $sj, 'stx' => $stx);
    foreach ($over as $k => $v) $a[$k] = $v;
    $out = array();
    foreach ($a as $k => $v) {
        if ($v === '' || $v === null) continue;
        if ($k === 'sj' && (int)$v < 0) continue;
        $out[] = $k . '=' . urlencode($v);
    }
    return '?' . implode('&amp;', $out);
};
?>

<style>
.exq{max-width:1280px}
.exq .box{background:#fff;border:1px solid #e3e6ec;border-radius:8px;padding:16px 18px;margin:0 0 14px}
.exq h2{font-size:15px;margin:0 0 10px;font-weight:700}
.exq .tabs{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 10px}
.exq .tabs a{display:inline-block;padding:5px 12px;border:1px solid #e3e6ec;border-radius:999px;
  background:#fff;color:#444;text-decoration:none;font-size:13px}
.exq .tabs a.on{background:#0f172a;border-color:#0f172a;color:#fff;font-weight:700}
.exq .tabs a b{color:#c22638;margin-left:4px}
.exq .tabs a.on b{color:#ffd34d}
.exq table{border-collapse:collapse;width:100%;font-size:13px}
.exq th,.exq td{border:1px solid #e3e6ec;padding:7px 9px;text-align:left;vertical-align:top}
.exq th{background:#f7f8fa;font-weight:600;white-space:nowrap}
.exq .pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11.5px;font-weight:700;white-space:nowrap}
.exq .pill.wait{background:#fff6e5;color:#8a5a00}
.exq .pill.rev{background:#e8efff;color:#1b3faa}
.exq .pill.ok{background:#e9f7ef;color:#075c2d}
.exq .pill.no{background:#f2f3f5;color:#666}
.exq .tag{display:inline-block;padding:1px 7px;border:1px solid #e3e6ec;border-radius:4px;
  font-size:11.5px;color:#555;background:#fafbfc;white-space:nowrap}
.exq .tag.red{border-color:#c22638;color:#c22638;background:#fdeced;font-weight:700}
.exq .tag.blue{border-color:#1b3faa;color:#1b3faa;background:#eef3ff}
.exq .q{color:#222;line-height:1.55}
.exq .q a{color:#1b3faa;text-decoration:none;font-weight:600}
.exq .q a:hover{text-decoration:underline}
.exq .meta{color:#888;font-size:11.5px;margin-top:3px}
.exq .hint{color:#666;font-size:13px;line-height:1.7}
.exq code{background:#f4f5f7;padding:1px 5px;border-radius:3px;font-family:Consolas,monospace}
.exq .srch{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.exq .srch input[type=text]{padding:6px 9px;border:1px solid #dde1e8;border-radius:5px;font-size:13px;min-width:220px}
.exq .pg{margin-top:12px;display:flex;gap:5px;flex-wrap:wrap}
.exq .pg a,.exq .pg span{padding:4px 10px;border:1px solid #e3e6ec;border-radius:4px;
  text-decoration:none;color:#444;font-size:12.5px}
.exq .pg span.cur{background:#0f172a;border-color:#0f172a;color:#fff;font-weight:700}
.exq .note{border-radius:6px;padding:10px 13px;margin:0 0 14px;font-size:13px;line-height:1.7}
.exq .note.ok{background:#e9f7ef;border:1px solid #0f7355;color:#0a5c3c}
.exq .note.er{background:#fdeced;border:1px solid #c22638;color:#8e1524}
.exq .note.wa{background:#fff8e5;border:1px solid #a5820a;color:#6f5600}
.exq .note ul{margin:6px 0 0;padding-left:20px}
/* 일괄 처리 바 — 표 위·아래에 같은 것을 둔다. 30건을 스크롤한 뒤 위로 돌아가지
   않아도 되게. 아래쪽이 실제로 더 많이 쓰인다. */
.exq .bulk{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin:0 0 10px}
.exq .bulk.bot{margin:12px 0 0}
.exq .bulk .n{font-weight:700}
.exq td.ck,.exq th.ck{width:34px;text-align:center}
</style>

<div class="exq">

<?php if ($msg): ?><div class="note ok"><?php echo exq_h($msg) ?></div><?php endif; ?>
<?php if ($err): ?><div class="note er"><?php echo exq_h($err) ?></div><?php endif; ?>
<?php if ($warns): ?>
  <div class="note wa">
    <b>확인하실 것 <?php echo count($warns) ?>건</b>
    <ul><?php foreach (array_slice($warns, 0, 12) as $w0): ?>
      <li><?php echo exq_h($w0) ?></li>
    <?php endforeach; ?></ul>
    <?php if (count($warns) > 12): ?><div>… 외 <?php echo count($warns) - 12 ?>건</div><?php endif; ?>
  </div>
<?php endif; ?>

  <!-- ── 게시판에서 가져오기 ──────────────────────────────────────────────
       질문은 그누보드 과목게시판으로 들어온다. 이 버튼이 그것을 ex_qna 로 옮긴다.
       ★ 이게 없으면 초안·검수·승인 흐름 전체가 빈 큐 위에서 돌아간다. -->
  <div class="box">
    <h2>게시판에서 가져오기
      <span class="hint">— 과목게시판 글을 검수 큐로 옮깁니다</span></h2>
    <form method="post" action="<?php echo $qs() ?>" class="srch">
      <input type="hidden" name="token" value="">
      <input type="hidden" name="act" value="pull">
      <select name="pull_pd" style="padding:6px 9px;border:1px solid #dde1e8;border-radius:5px;font-size:13px">
        <option value="">열린 문제집 전부</option>
        <?php foreach ($prods as $p): ?>
          <option value="<?php echo exq_h($p['pd_id']) ?>"<?php echo $pd === $p['pd_id'] ? ' selected' : '' ?>>
            <?php echo exq_h($p['pd_name']) ?></option>
        <?php endforeach; ?>
      </select>
      <button type="submit" class="btn_submit">가져오기</button>
      <span class="hint">
        <?php if ($pending_board): ?>
          아직 안 가져온 게시판 글 <b><?php echo number_format($pending_board) ?>건</b>
        <?php else: ?>
          가져올 새 글이 없습니다.
        <?php endif; ?>
      </span>
    </form>
    <?php if ($board_missing): ?>
      <div class="hint" style="margin-top:8px;color:#c22638">
        과목게시판이 없는 문제집: <?php echo exq_h(implode(' · ', $board_missing)) ?>
        — 그누보드 관리자 → 게시판 관리에서 <b>그 이름 그대로</b> 만드십시오.
      </div>
    <?php endif; ?>
    <div class="hint" style="margin-top:8px">
      같은 글을 두 번 가져오지 않습니다(<code>bo_table</code> + <code>wr_id</code> 로 판정).
      제목의 <code>1회 61번</code> 같은 표식에서 문항을 자동으로 찾아 붙입니다 —
      <b>문항이 붙으면 초안 품질이 크게 올라갑니다</b>(발문·보기·정답·해설이 프롬프트에 들어갑니다).
      제목에 '오류·신고·틀린·잘못'이 있으면 <span class="tag red">오류 신고</span>로 분류합니다.
    </div>
  </div>

  <div class="box">
    <div class="tabs">
      <?php
      $tabs = array('open' => '미처리', 'draft_ready' => '검수 대기', 'pending' => '대기',
                    'approved' => '완료', 'rejected' => '반려', 'all' => '전체');
      foreach ($tabs as $k => $lab) {
          if ($k === 'open')      $n = $open_n;
          elseif ($k === 'all')   $n = array_sum($counts);
          else                    $n = isset($counts[$k]) ? $counts[$k] : 0;
          echo '<a class="' . ($st === $k ? 'on' : '') . '" href="' . $qs(array('st' => $k, 'page' => null)) . '">'
             . exq_h($lab) . ($n ? ' <b>' . $n . '</b>' : '') . '</a>';
      }
      ?>
    </div>

    <div class="tabs">
      <a class="<?php echo $pd === '' ? 'on' : '' ?>" href="<?php echo $qs(array('pd' => '', 'sj' => -1)) ?>">전 문제집</a>
      <?php foreach ($prods as $p): ?>
        <a class="<?php echo $pd === $p['pd_id'] ? 'on' : '' ?>"
           href="<?php echo $qs(array('pd' => $p['pd_id'], 'sj' => -1)) ?>"><?php echo exq_h($p['pd_name']) ?></a>
      <?php endforeach; ?>
      <span style="width:12px"></span>
      <a class="<?php echo $kind === '' ? 'on' : '' ?>" href="<?php echo $qs(array('kind' => '')) ?>">전체 종류</a>
      <a class="<?php echo $kind === 'qna' ? 'on' : '' ?>" href="<?php echo $qs(array('kind' => 'qna')) ?>">질문</a>
      <a class="<?php echo $kind === 'report' ? 'on' : '' ?>" href="<?php echo $qs(array('kind' => 'report')) ?>">오류 신고</a>
    </div>

    <?php if ($subs): ?>
    <div class="tabs">
      <a class="<?php echo $sj < 0 ? 'on' : '' ?>" href="<?php echo $qs(array('sj' => -1)) ?>">전 과목</a>
      <?php foreach ($subs as $s): ?>
        <a class="<?php echo $sj === (int)$s['sj_no'] ? 'on' : '' ?>"
           href="<?php echo $qs(array('sj' => (int)$s['sj_no'])) ?>"><?php echo exq_h($s['sj_name']) ?></a>
      <?php endforeach; ?>
    </div>
    <?php endif; ?>

    <form method="get" class="srch">
      <input type="hidden" name="st"   value="<?php echo exq_h($st) ?>">
      <input type="hidden" name="pd"   value="<?php echo exq_h($pd) ?>">
      <input type="hidden" name="kind" value="<?php echo exq_h($kind) ?>">
      <input type="hidden" name="sj"   value="<?php echo (int)$sj ?>">
      <input type="text" name="stx" value="<?php echo exq_h($stx) ?>" placeholder="질문·답변·아이디 검색">
      <input type="submit" class="btn_submit" value="검색">
      <?php if ($stx !== ''): ?>
        <a href="<?php echo $qs(array('stx' => '')) ?>" class="tag">검색 해제</a>
      <?php endif; ?>
      <span class="hint" style="margin-left:auto"><?php echo number_format($total) ?>건</span>
    </form>
  </div>

  <div class="box">
    <?php if (!$rows): ?>
      <p class="hint">해당하는 질문이 없습니다.
        <?php if ($st === 'open'): ?><b>미처리가 0건입니다 — 다 답변했습니다.</b><?php endif; ?></p>
    <?php else: ?>
    <form method="post" action="<?php echo $qs() ?>" id="bulkForm">
    <input type="hidden" name="token" value="">
    <input type="hidden" name="act" value="draft">

    <?php
    /* 일괄 바를 표 위·아래에 같은 내용으로 둔다. 30건을 훑고 내려온 뒤 위로 다시
       올라가지 않아도 되게. `$bulkbar` 로 한 번만 쓰고 두 번 출력한다 —
       두 벌을 손으로 유지하면 반드시 갈린다. */
    $bulkbar = function ($cls) use ($CAP1) { ?>
      <div class="bulk <?php echo $cls ?>">
        <button type="submit" class="btn_submit" id="draftBtn<?php echo $cls ?>">
          선택 초안 요청</button>
        <span class="hint">
          체크한 <b class="n" id="selN<?php echo $cls ?>">0</b>건에 LLM 초안을 만듭니다 ·
          건당 최대 <?php echo number_format($CAP1, 2) ?>원
        </span>
      </div>
    <?php };
    /* ★ 위쪽 바는 **행이 많을 때만** 낸다.
     *   한 페이지가 30건이라 다 훑고 내려온 뒤 위로 돌아가지 않게 두 개를 뒀는데,
     *   5건일 때는 두 줄이 붙어 보여 군더더기가 된다("버튼이 왜 2개냐"는 질문이 나왔다).
     *   기준을 8로 둔 이유: 그 이하는 한 화면에 표가 다 들어와 아래 바만으로 충분하다. */
    if (count($rows) >= 8) $bulkbar('top');
    ?>

    <table>
      <tr>
        <th class="ck"><input type="checkbox" id="ckAll" title="전체 선택"></th>
        <th>#</th><th>상태</th><th>문제집 · 과목</th><th>질문</th>
        <th>회원</th><th>포인트</th><th>등록</th><th>처리</th>
      </tr>
      <?php foreach ($rows as $q):
        $s = isset($ST[$q['qa_status']]) ? $ST[$q['qa_status']] : array('', $q['qa_status']); ?>
      <tr>
        <?php
        /* 초안을 만들 수 있는 상태만 체크할 수 있게 한다.
           ex_draft_one() 이 pending|draft_ready 만 집으므로(원자적 잠금), 완료·반려를
           체크해 보내면 그쪽에서 "대상이 아닙니다" 로 떨어진다. 눌러도 안 되는 것을
           체크하게 두면 실패 목록만 길어진다 — 여기서 막는다. */
        $ckable = in_array($q['qa_status'], array('pending', 'draft_ready'), true);
        ?>
        <td class="ck">
          <?php if ($ckable): ?>
            <input type="checkbox" class="ck1" name="chk[]" value="<?php echo (int)$q['qa_id'] ?>">
          <?php endif; ?>
        </td>
        <td><?php echo (int)$q['qa_id'] ?></td>
        <td>
          <span class="pill <?php echo $s[0] ?>"><?php echo exq_h($s[1]) ?></span>
          <?php if ($q['has_draft'] && $q['qa_status'] !== 'approved'): ?>
            <br><span class="tag blue">초안 있음</span>
          <?php endif; ?>
          <?php if (!(int)$q['qa_public']): ?><br><span class="tag">비공개</span><?php endif; ?>
        </td>
        <td>
          <?php echo exq_h($q['pd_name'] ? $q['pd_name'] : $q['pd_id']) ?>
          <?php if ($q['sj_name']): ?><br><span class="tag"><?php echo exq_h($q['sj_name']) ?></span><?php endif; ?>
          <?php if ($q['kind'] === 'report'): ?><br><span class="tag red">오류 신고</span><?php endif; ?>
        </td>
        <td>
          <div class="q">
            <a href="./exam_qna_form.php?qa_id=<?php echo (int)$q['qa_id'] ?>"><?php echo exq_h(exq_cut($q['qa_question'])) ?></a>
          </div>
          <div class="meta">
            <?php if ($q['pr_key']): ?>
              <code><?php echo exq_h($q['pr_key']) ?></code>
              <?php if ($q['rd_no']): ?> · <?php echo (int)$q['rd_no'] ?>회 <?php echo (int)$q['pr_no'] ?>번<?php endif; ?>
            <?php else: ?>
              일반 질문
            <?php endif; ?>
            <?php if ($q['bo_table'] && $q['wr_id']): ?>
              · <a href="<?php echo G5_BBS_URL ?>/board.php?bo_table=<?php echo exq_h($q['bo_table']) ?>&amp;wr_id=<?php echo (int)$q['wr_id'] ?>" target="_blank">게시판 글</a>
            <?php endif; ?>
          </div>
        </td>
        <td><?php echo exq_h($q['mb_nick'] ? $q['mb_nick'] : $q['mb_id']) ?>
            <div class="meta"><?php echo exq_h($q['mb_id']) ?></div></td>
        <td>
          <?php if ((int)$q['cost_units'] === 0): ?>
            <span class="tag">무료</span>
          <?php else: ?>
            <?php echo number_format((int)$q['cost_units']) ?>원
            <?php if (!(int)$q['qa_credit_ok']): ?>
              <br><span class="tag red">차감 미확정</span>
            <?php endif; ?>
            <?php if ((int)$q['qa_refunded']): ?><br><span class="tag">환불됨</span><?php endif; ?>
          <?php endif; ?>
        </td>
        <td><small><?php echo exq_h(substr($q['created_at'], 0, 16)) ?>
          <?php if ($q['qa_answered_at']): ?><br>→ <?php echo exq_h(substr($q['qa_answered_at'], 0, 16)) ?><?php endif; ?>
        </small></td>
        <td><a class="btn_submit" style="padding:4px 10px;font-size:12px"
               href="./exam_qna_form.php?qa_id=<?php echo (int)$q['qa_id'] ?>">답변</a></td>
      </tr>
      <?php endforeach; ?>
    </table>

    <?php $bulkbar('bot'); ?>
    </form>

    <script>
    /* 선택 개수 표시 + 확인창. 인라인으로 두는 이유: 이 화면 하나에만 쓰이고,
       adm/ 에 별도 js 파일을 늘리면 캐시 무효화까지 따라온다. */
    (function () {
      var caps = <?php echo json_encode(number_format($CAP1, 2)) ?>;
      var boxes = function () { return document.querySelectorAll('#bulkForm .ck1'); };
      var all   = document.getElementById('ckAll');

      function sel() {
        var n = 0, b = boxes();
        for (var i = 0; i < b.length; i++) if (b[i].checked) n++;
        return n;
      }
      function paint() {
        var n = sel();
        ['top', 'bot'].forEach(function (k) {
          var e = document.getElementById('selN' + k);
          if (e) e.textContent = n;
        });
      }
      if (all) all.onclick = function () {
        var b = boxes();
        for (var i = 0; i < b.length; i++) b[i].checked = all.checked;
        paint();
      };
      var b = boxes();
      for (var i = 0; i < b.length; i++) b[i].onclick = paint;
      paint();

      /* ★ 확인창은 **건수와 돈**을 말한다. "진행할까요?" 만 묻는 창은 아무 정보가 없어서
         사람이 습관적으로 확인을 누르게 되고, 그때 원가가 나간다. */
      document.getElementById('bulkForm').onsubmit = function () {
        var n = sel();
        if (!n) { alert('초안을 만들 질문을 먼저 체크해 주십시오.'); return false; }
        return confirm(n + '건에 LLM 초안을 만듭니다.\n'
          + '예상 원가 최대 ' + caps + '원 × ' + n + '건\n\n'
          + '초안은 이용자에게 보이지 않습니다. 검수·승인한 답변만 공개됩니다.\n'
          + '시간이 오래 걸리면 일부만 처리하고 남은 건수를 알려 드립니다.');
      };
    })();
    </script>

    <?php
    $pages = (int)ceil($total / $per);
    if ($pages > 1):
      $from = max(1, $page - 4); $to = min($pages, $page + 4);
    ?>
    <div class="pg">
      <?php if ($page > 1): ?><a href="<?php echo $qs(array('page' => $page - 1)) ?>">이전</a><?php endif; ?>
      <?php for ($i = $from; $i <= $to; $i++): ?>
        <?php if ($i === $page): ?><span class="cur"><?php echo $i ?></span>
        <?php else: ?><a href="<?php echo $qs(array('page' => $i)) ?>"><?php echo $i ?></a><?php endif; ?>
      <?php endfor; ?>
      <?php if ($page < $pages): ?><a href="<?php echo $qs(array('page' => $page + 1)) ?>">다음</a><?php endif; ?>
    </div>
    <?php endif; ?>
    <?php endif; ?>
  </div>

  <div class="box">
    <h2>아침에 하는 일</h2>
    <div class="hint">
      <b>①</b> 위 <b>[가져오기]</b> — 과목게시판 새 질문을 이 큐로 옮긴다.<br>
      <b>②</b> 체크 → <b>[선택 초안 요청]</b> — 건수와 예상 원가를 확인하고 진행한다.
        전체 선택은 표 머리의 체크박스다.<br>
      <b>③</b> 한 건씩 <b>[답변]</b> → 초안을 읽고 <b>[초안을 답변란으로 복사]</b> → 고쳐서 <b>[승인 · 공개]</b>.<br>
      <b>④</b> 승인하면 <b>게시판 원글에 답변 댓글이 자동으로 달린다.</b> 질문자는 게시판에서
        답을 본다 — 우리 DB 에만 넣으면 그 사람 입장에서는 아무 일도 안 일어난 것이다.
        오타를 고쳐 다시 승인하면 그 댓글이 갱신된다(새로 달지 않는다).<br>
      <br>
      ★ <b>초안은 공짜가 아니다.</b> 1건 = LLM 호출 1건이다. 그래서 [초안 요청] 은 반드시
        건수와 예상 원가를 먼저 보여준다. 모델·상한은 <a href="./exam_llm.php">답변 초안 설정</a>에서
        문제집별로 바꾼다(<code>ex_product</code> 한 행 — PHP 를 고치지 않는다).<br>
      ★ 초안이 오래 걸려 <b>일부만 처리</b>되면 남은 건수를 알려 준다. 다시 체크해서 누르면 이어진다.
        조용히 끊기지 않게 벽시계 예산으로 끊는다.
    </div>
  </div>

  <div class="box">
    <h2>읽는 법</h2>
    <div class="hint">
      <b>정렬</b> — 검수 대기가 맨 위, 그 다음 <b>오래된 질문 순</b>이다. 오래 기다린 사람이 먼저 답을 받아야 한다.<br>
      <b>문항 연결</b> — 질문 밑에 <code>m01-7#61</code> 처럼 뜨면 그 문항의 발문·보기·정답·해설이
      초안 프롬프트에 들어간다. <b>초안 품질을 가장 크게 좌우한다.</b> 게시판 제목의
      <code>1회 61번</code> 표식에서 자동으로 찾는다 — 표식이 없으면 과목만으로 초안을 쓴다.<br>
      <span class="tag red">차감 미확정</span> — 포인트는 빠졌는데 <code>qa_credit_ok</code> 가 0 이다.
      질문 등록 3단계 중 마지막이 실패한 경우다. 원장에는 차감이 남아 회계는 맞지만 <b>수동 확인 대상</b>이다.<br>
      <span class="tag blue">초안 있음</span> — LLM 초안(<code>qa_draft</code>)이 있다.
      <b>이용자에게는 절대 보이지 않는다</b> — 회원 API 의 SELECT 목록에 그 컬럼이 없다.
      승인해서 <code>qa_answer</code> 로 확정한 것만 공개된다.<br>
      <b>반려</b>하면 <code>cost_units</code> 만큼 환불된다. 답을 못 하는데 포인트를 가져가면 민원이 된다.
    </div>
  </div>

</div>

<?php
require_once './admin.tail.php';
