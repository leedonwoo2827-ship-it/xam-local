<?php
/**
 * 수강 신청 관리 — 승인하면 구독권이 생기고 첫 달 포인트가 지급된다.
 *
 * buy.php 가 ex_order 에 pending 으로 남긴 것을 여기서 처리한다.
 * 결제(PG)를 붙이지 않았으므로 **이 화면이 실운영 경로 그 자체다.**
 *
 * 승인이 하는 일 (ex_order_approve() — /exam/api/lib/credit.php):
 *   1) od_status: pending → paid  (조건부 UPDATE. 동시 클릭 중 하나만 통과)
 *   2) ex_entitlement upsert       (월 지급의 원천. months_paid 누적)
 *   3) ex_settle()                 (첫 달 + 밀린 달 즉시 지급)
 *
 * ★ 멱등이다. 원장 키가 'drip:<pd>:<YYYY-MM>' 이고 uq_month 제약이 겹쳐 있어
 *   버튼을 두 번 눌러도 포인트가 두 번 들어가지 않는다.
 *   운영 화면에서 가장 흔한 사고가 중복 클릭인데 그걸 DB 차원에서 막는다.
 */
$sub_menu = '600600';
require_once './_common.php';

auth_check_menu($auth, $sub_menu, 'r');

require_once G5_PATH . '/exam/api/lib/credit.php';

$msg = ''; $err = '';

/* ── 처리 ──────────────────────────────────────────────────────────────── */
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    auth_check_menu($auth, $sub_menu, 'w');

    /* ★ 관리자 영역은 check_token() 이 아니라 check_admin_token() 이다.
     * adm/admin.js 가 모든 submit 을 가로채 ajax.token.php 에서 받은 관리자 토큰으로
     * input[name=token] 을 덮어쓴다. 그래서 get_token() 으로 렌더해도 소용이 없다.
     * (exam_import.php 에 같은 주석이 있다 — 실측으로 확인된 동작이다) */
    if (function_exists('check_admin_token')) check_admin_token();
    else                                     check_token();

    $act   = isset($_POST['act']) ? $_POST['act'] : '';
    $od_id = (int)(isset($_POST['od_id']) ? $_POST['od_id'] : 0);

    if ($act === 'approve') {
        $r = ex_order_approve($od_id, $member['mb_id']);
        if ($r['ok']) $msg = '#' . $od_id . ' ' . $r['msg'];
        else          $err = '#' . $od_id . ' ' . $r['msg'];

    } elseif ($act === 'cancel') {
        // 취소는 포인트를 회수하지 않는다. 이미 지급된 것을 빼앗으면 민원이 된다 —
        // 회수가 필요하면 포인트 지급 화면에서 음수 조정을 남긴다(감사 흔적이 남는다).
        sql_query("update ex_order set od_status = 'canceled'
                    where od_id = " . $od_id . " and od_status = 'pending'", false);
        if (ex_affected() === 1) $msg = '#' . $od_id . ' 취소했습니다.';
        else                     $err = '#' . $od_id . ' 대기 중인 신청이 아닙니다.';

    } elseif ($act === 'memo') {
        $m = isset($_POST['admin_memo']) ? $_POST['admin_memo'] : '';
        sql_query("update ex_order set admin_memo = '" . sql_real_escape_string(mb_substr($m, 0, 250)) . "'
                    where od_id = " . $od_id, false);
        $msg = '#' . $od_id . ' 메모를 저장했습니다.';
    }
}

/* ── 목록 ──────────────────────────────────────────────────────────────── */
$st = isset($_GET['st']) ? preg_replace('/[^a-z]/', '', $_GET['st']) : 'pending';
$pd = isset($_GET['pd']) ? preg_replace('/[^a-z0-9\-]/', '', $_GET['pd']) : '';

$w = array('1=1');
if ($st !== '' && $st !== 'all') $w[] = "o.od_status = '" . sql_real_escape_string($st) . "'";
if ($pd !== '')                  $w[] = "o.pd_id = '" . sql_real_escape_string($pd) . "'";
$where = implode(' and ', $w);

// 상태별 건수 — 탭에 숫자를 붙여야 "처리할 게 남았나"를 한눈에 안다
$counts = array();
$res = sql_query("select od_status, count(*) as c from ex_order group by od_status", false);
while ($r = sql_fetch_array($res)) $counts[$r['od_status']] = (int)$r['c'];

$rows = array();
$res = sql_query("select o.*, d.pd_name, p.pl_name, m.mb_nick, m.mb_email, m.mb_hp
                    from ex_order o
                    left join ex_product d on d.pd_id = o.pd_id
                    left join ex_plan    p on p.pl_id = o.pl_id
                    left join g5_member  m on m.mb_id = o.mb_id
                   where $where
                   order by o.od_id desc
                   limit 200", false);
while ($r = sql_fetch_array($res)) $rows[] = $r;

// 문제집 필터용
$prods = array();
$res = sql_query("select pd_id, pd_name from ex_product order by pd_sort, pd_id", false);
while ($r = sql_fetch_array($res)) $prods[] = $r;

$audit = ex_credit_audit();

$g5['title'] = '수강 신청 관리';
require_once './admin.head.php';

function exo_h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }

$ST_LABEL = array('pending' => '대기', 'paid' => '승인', 'canceled' => '취소', 'refunded' => '환불');
?>

<style>
.exord{max-width:1240px}
.exord .box{background:#fff;border:1px solid #e3e6ec;border-radius:8px;padding:18px 20px;margin:0 0 16px}
.exord h2{font-size:15px;margin:0 0 12px;font-weight:700}
.exord .msg{padding:11px 16px;border-radius:6px;margin:0 0 14px;font-size:14px;line-height:1.6}
.exord .msg.err{background:#fdeced;border:1px solid #c22638;color:#8c1220}
.exord .msg.good{background:#e9f7ef;border:1px solid #0a7f3f;color:#075c2d}
.exord .tabs{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 14px}
.exord .tabs a{display:inline-block;padding:6px 13px;border:1px solid #e3e6ec;border-radius:999px;
  background:#fff;color:#444;text-decoration:none;font-size:13px}
.exord .tabs a.on{background:#0f172a;border-color:#0f172a;color:#fff;font-weight:700}
.exord .tabs a b{color:#c22638;margin-left:4px}
.exord .tabs a.on b{color:#ffd34d}
.exord table.list{border-collapse:collapse;width:100%;font-size:13px}
.exord .list th,.exord .list td{border:1px solid #e3e6ec;padding:7px 9px;text-align:left;vertical-align:top}
.exord .list th{background:#f7f8fa;font-weight:600;white-space:nowrap}
.exord .list td.n{text-align:right;white-space:nowrap}
.exord .pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700}
.exord .pill.pending{background:#fff6e5;color:#8a5a00}
.exord .pill.paid{background:#e9f7ef;color:#075c2d}
.exord .pill.canceled,.exord .pill.refunded{background:#f2f3f5;color:#666}
.exord .who b{display:block}
.exord .who small{color:#888}
.exord .act{white-space:nowrap}
.exord .act .btn_submit{padding:4px 10px;font-size:12px}
.exord .memo input{width:100%;box-sizing:border-box;padding:4px 6px;border:1px solid #dde1e8;border-radius:4px;font-size:12px}
.exord .hint{color:#666;font-size:13px;line-height:1.7}
.exord code{background:#f4f5f7;padding:1px 5px;border-radius:3px;font-family:Consolas,monospace}
.exord .audit{display:flex;gap:18px;flex-wrap:wrap;font-size:13px}
.exord .audit b{font-size:15px}
.exord .ok{color:#0a7f3f}.exord .bad{color:#c22638}
</style>

<div class="exord">

<?php if ($msg): ?><div class="msg good"><?php echo exo_h($msg) ?></div><?php endif; ?>
<?php if ($err): ?><div class="msg err"><?php echo exo_h($err) ?></div><?php endif; ?>

  <div class="box">
    <h2>포인트 정합성</h2>
    <div class="audit">
      <span>원장 합계 <b><?php echo number_format($audit['ledger']) ?></b></span>
      <span>유효 잔액 <b><?php echo number_format($audit['avail']) ?></b></span>
      <span>미기록 만료 <b><?php echo number_format($audit['pending']) ?></b></span>
      <span class="<?php echo $audit['ok'] ? 'ok' : 'bad' ?>">
        <b><?php echo $audit['ok'] ? '일치' : '불일치' ?></b>
      </span>
    </div>
    <div class="hint" style="margin-top:8px">
      원장은 append-only 라 언제든 대조된다. <code>원장 합계 − 미기록 만료 = 유효 잔액</code> 이면 정상이다.
      만료 기록이 lazy 이므로(조회하는 사람이 남긴다) 아무도 안 본 만료분은 아직 원장에 없다 —
      그게 <b>미기록 만료</b> 이고 오류가 아니다. 불일치가 나면 <code>lg_ref</code> 로 추적한다.
    </div>
  </div>

  <div class="tabs">
    <?php
    $tabs = array('pending' => '대기', 'paid' => '승인', 'canceled' => '취소', 'refunded' => '환불', 'all' => '전체');
    foreach ($tabs as $k => $lab) {
        $n = ($k === 'all') ? array_sum($counts) : (isset($counts[$k]) ? $counts[$k] : 0);
        $q = 'st=' . $k . ($pd !== '' ? '&amp;pd=' . urlencode($pd) : '');
        echo '<a class="' . ($st === $k ? 'on' : '') . '" href="?' . $q . '">' . exo_h($lab)
           . ($n ? ' <b>' . $n . '</b>' : '') . '</a>';
    }
    ?>
  </div>

  <div class="tabs">
    <a class="<?php echo $pd === '' ? 'on' : '' ?>" href="?st=<?php echo exo_h($st) ?>">전 문제집</a>
    <?php foreach ($prods as $p): ?>
      <a class="<?php echo $pd === $p['pd_id'] ? 'on' : '' ?>"
         href="?st=<?php echo exo_h($st) ?>&amp;pd=<?php echo urlencode($p['pd_id']) ?>"><?php echo exo_h($p['pd_name']) ?></a>
    <?php endforeach; ?>
  </div>

  <div class="box">
    <h2>신청 목록 <span class="hint">(최근 200건)</span></h2>

    <?php if (!$rows): ?>
      <p class="hint">해당하는 신청이 없습니다.</p>
    <?php else: ?>
    <table class="list">
      <tr>
        <th>#</th><th>문제집</th><th>회원</th><th>과정</th>
        <th class="n">금액</th><th class="n">개월</th><th class="n">월 지급</th>
        <th>상태</th><th>신청 · 승인</th><th>메모(연락처)</th><th>처리</th>
      </tr>
      <?php foreach ($rows as $o): ?>
      <tr>
        <td><?php echo (int)$o['od_id'] ?></td>
        <td>
          <?php echo exo_h($o['pd_name'] ? $o['pd_name'] : $o['pd_id']) ?>
          <?php if ($o['pd_id'] === ''): ?>
            <br><b class="bad">문제집 없음</b>
          <?php endif; ?>
        </td>
        <td class="who">
          <b><?php echo exo_h($o['mb_nick'] ? $o['mb_nick'] : $o['mb_id']) ?></b>
          <small><?php echo exo_h($o['mb_id']) ?><?php echo $o['mb_hp'] ? ' · ' . exo_h($o['mb_hp']) : '' ?></small>
        </td>
        <td><?php echo exo_h($o['pl_name'] ? $o['pl_name'] : '(과정 삭제됨)') ?><br>
            <small><?php echo exo_h($o['od_depositor']) ?></small></td>
        <td class="n"><?php echo number_format((int)$o['od_price']) ?></td>
        <td class="n"><?php echo (int)$o['od_months'] ?></td>
        <td class="n"><?php echo number_format((int)$o['od_quota']) ?></td>
        <td><span class="pill <?php echo exo_h($o['od_status']) ?>"><?php
            echo exo_h(isset($ST_LABEL[$o['od_status']]) ? $ST_LABEL[$o['od_status']] : $o['od_status']) ?></span></td>
        <td><small><?php echo exo_h(substr($o['created_at'], 0, 16)) ?>
            <?php if ($o['paid_at']): ?><br>→ <?php echo exo_h(substr($o['paid_at'], 0, 16)) ?><?php endif; ?>
        </small></td>
        <td class="memo">
          <form method="post" style="margin:0">
            <input type="hidden" name="token" value="">
            <input type="hidden" name="act" value="memo">
            <input type="hidden" name="od_id" value="<?php echo (int)$o['od_id'] ?>">
            <input type="text" name="admin_memo" value="<?php echo exo_h($o['admin_memo']) ?>"
                   onchange="this.form.submit()" title="수정 후 Enter 또는 포커스 이동">
          </form>
        </td>
        <td class="act">
          <?php if ($o['od_status'] === 'pending'): ?>
          <form method="post" style="margin:0 0 4px" onsubmit="return confirm('#<?php echo (int)$o['od_id'] ?> 승인하고 포인트를 지급합니다.');">
            <input type="hidden" name="token" value="">
            <input type="hidden" name="act" value="approve">
            <input type="hidden" name="od_id" value="<?php echo (int)$o['od_id'] ?>">
            <input type="submit" class="btn_submit" value="승인">
          </form>
          <form method="post" style="margin:0" onsubmit="return confirm('#<?php echo (int)$o['od_id'] ?> 취소합니다.');">
            <input type="hidden" name="token" value="">
            <input type="hidden" name="act" value="cancel">
            <input type="hidden" name="od_id" value="<?php echo (int)$o['od_id'] ?>">
            <input type="submit" class="btn_b01" value="취소">
          </form>
          <?php else: ?>
            <small class="hint">—</small>
          <?php endif; ?>
        </td>
      </tr>
      <?php endforeach; ?>
    </table>
    <?php endif; ?>
  </div>

  <div class="box">
    <h2>승인하면 무슨 일이 일어나는가</h2>
    <div class="hint">
      <b>1. 상태 변경</b> — <code>pending → paid</code>. 조건부 UPDATE 라 두 사람이 동시에 눌러도 한 번만 통과한다.<br>
      <b>2. 구독권</b> — <code>ex_entitlement</code> 에 (회원, 문제집) 1행. 이미 있으면 <code>months_paid</code> 를 더한다(연장).<br>
      <b>3. 첫 달 지급</b> — <code>ex_credit_lot</code> 에 월 지급분. 만료는 <b>지급일 + 1개월 − 1일</b> 이다.<br><br>

      <b>포인트는 문제집별이다.</b> SQLD 를 승인해도 다른 문제집 잔액은 늘지 않는다.
      <code>uq_month(mb_id, pd_id, lot_src, lot_period)</code> 가 같은 달 중복 지급을 DB 차원에서 막는다.<br><br>

      ⚠ <b>취소는 이미 지급된 포인트를 회수하지 않는다.</b> 회수가 필요하면
      <b>포인트 지급</b> 화면에서 음수로 조정한다 — 원장에 흔적이 남아야 나중에 설명할 수 있다.<br><br>

      ⚠ <b>결제는 받지 않는다.</b> <code>od_method='manual'</code> 이고 입금 확인은 화면 밖에서 한다.
      PG 를 붙이면 이 화면의 승인이 자동화될 자리다.
    </div>
  </div>

</div>

<?php
require_once './admin.tail.php';
