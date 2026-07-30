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
</style>

<div class="exq">

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
    <table>
      <tr>
        <th>#</th><th>상태</th><th>문제집 · 과목</th><th>질문</th>
        <th>회원</th><th>포인트</th><th>등록</th><th>처리</th>
      </tr>
      <?php foreach ($rows as $q):
        $s = isset($ST[$q['qa_status']]) ? $ST[$q['qa_status']] : array('', $q['qa_status']); ?>
      <tr>
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
    <h2>읽는 법</h2>
    <div class="hint">
      <b>정렬</b> — 검수 대기가 맨 위, 그 다음 <b>오래된 질문 순</b>이다. 오래 기다린 사람이 먼저 답을 받아야 한다.<br>
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
