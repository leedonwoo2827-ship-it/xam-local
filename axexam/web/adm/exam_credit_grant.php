<?php
/**
 * 포인트 지급 · 조정 — 문제집별.
 *
 * 결제를 붙이지 않은 지금, **내부 오픈 기간의 실운영 경로다.**
 * 주문 승인(exam_orders.php)이 정상 경로이고, 이 화면은 그 밖의 모든 경우를 덮는다:
 *   · 이벤트·프로모션 지급
 *   · 주문 없이 무료로 열어주기
 *   · 잘못 지급한 것을 되돌리기(음수 조정)
 *
 * ★ 왜 음수 조정을 lot 삭제로 하지 않는가
 *   원장(ex_credit_ledger)은 append-only 다. lot 을 지우면 "왜 없어졌나"에 답할 수 없다.
 *   조정도 새 행으로 남긴다 — 회계 원칙이고, 민원 대응의 근거가 된다.
 *
 * ★ 음수 조정은 이미 쓴 만큼은 회수하지 못한다.
 *   남은 잔액에서만 뺀다. 다 써버린 회원에게서 억지로 빼면 잔액이 음수가 되고
 *   그 상태를 처리하는 코드가 없다 — 그래서 원리적으로 만들지 않는다.
 */
$sub_menu = '600500';
require_once './_common.php';

auth_check_menu($auth, $sub_menu, 'r');

require_once G5_PATH . '/exam/api/lib/credit.php';

$msg = ''; $err = '';

/* ── 처리 ──────────────────────────────────────────────────────────────── */
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    auth_check_menu($auth, $sub_menu, 'w');
    if (function_exists('check_admin_token')) check_admin_token();
    else                                     check_token();

    $mb_id  = trim(isset($_POST['mb_id']) ? $_POST['mb_id'] : '');
    $pd_id  = trim(isset($_POST['pd_id']) ? $_POST['pd_id'] : '');
    $qty    = (int)(isset($_POST['qty'])  ? $_POST['qty']  : 0);
    $days   = (int)(isset($_POST['days']) ? $_POST['days'] : 30);
    $memo   = trim(isset($_POST['memo'])  ? $_POST['memo']  : '');

    $m = sql_fetch("select mb_id from g5_member where mb_id = '" . sql_real_escape_string($mb_id) . "'");
    $d = sql_fetch("select pd_id, cost_units from ex_product where pd_id = '" . sql_real_escape_string($pd_id) . "'");

    if (!$m)                   $err = '회원 아이디를 찾을 수 없습니다: ' . $mb_id;
    elseif (!$d)               $err = '문제집을 찾을 수 없습니다: ' . $pd_id;
    elseif ($qty === 0)        $err = '수량이 0 입니다.';
    elseif ($days < 1)         $err = '유효기간이 1일 미만입니다.';
    elseif ($memo === '')      $err = '사유를 적어 주십시오. 원장에 남아 나중에 설명할 근거가 됩니다.';
    else {
        // ex_user_ext 가 없으면 만든다 — 회원이 우리 화면에 한 번도 안 들어온 경우
        $ext = sql_fetch("select mb_id from ex_user_ext where mb_id = '" . sql_real_escape_string($mb_id) . "'");
        if (!$ext) {
            sql_query("insert into ex_user_ext (mb_id, created_at)
                            values ('" . sql_real_escape_string($mb_id) . "', '" . G5_TIME_YMDHIS . "')", false);
        }

        if ($qty > 0) {
            $expire = date('Y-m-d', G5_SERVER_TIME + $days * 86400);
            // lot_period = null → uq_month 에 걸리지 않아 몇 번이든 지급된다.
            // (월 지급만 'YYYY-MM' 을 넣는다. migrate-001 §3 주석 참조)
            $lot = ex_credit_grant($mb_id, $pd_id, $qty, 'manual', null, $expire,
                                   $member['mb_id'], $memo);
            if ($lot) {
                $msg = number_format($qty) . '원 지급했습니다 (lot #' . $lot . ', ' . $expire . ' 까지). '
                     . '남은 질문 ' . ex_credit_count($mb_id, $pd_id) . '개.';
            } else {
                $err = '지급에 실패했습니다. 같은 조건으로 이미 지급됐는지 아래 원장을 확인하십시오.';
            }
        } else {
            // 음수 = 회수. 남은 잔액에서만 뺀다.
            $take = -$qty;
            $bal  = ex_credit_balance($mb_id, $pd_id);
            if ($bal < $take) {
                $err = '회수액이 잔액보다 큽니다. 잔액 ' . number_format($bal)
                     . ' · 요청 ' . number_format($take) . '. 이미 사용한 분은 회수할 수 없습니다.';
            } else {
                // 차감과 같은 원자적 조건부 UPDATE 를 쓴다. lg_type 만 adjust 로 남긴다.
                $ref = 'adjust:' . $mb_id . ':' . G5_TIME_YMDHIS;
                if (ex_credit_debit($mb_id, $pd_id, $take, $ref, '관리자 조정: ' . $memo)) {
                    $msg = number_format($take) . '원 회수했습니다. 남은 질문 '
                         . ex_credit_count($mb_id, $pd_id) . '개.';
                } else {
                    $err = '회수에 실패했습니다. 잔액이 방금 변경됐을 수 있습니다.';
                }
            }
        }
    }

    if ($msg) { $_GET['mb'] = $mb_id; $_GET['pd'] = $pd_id; }
}

/* ── 조회 ──────────────────────────────────────────────────────────────── */
$q_mb = isset($_GET['mb']) ? trim($_GET['mb']) : '';
$q_pd = isset($_GET['pd']) ? preg_replace('/[^a-z0-9\-]/', '', $_GET['pd']) : '';

$prods = array();
$res = sql_query("select pd_id, pd_name, cost_units from ex_product order by pd_sort, pd_id", false);
while ($r = sql_fetch_array($res)) $prods[] = $r;

$who = null; $lots = array(); $ledger = array(); $ents = array();
if ($q_mb !== '') {
    $who = sql_fetch("select mb_id, mb_nick, mb_email, mb_hp, mb_datetime
                        from g5_member where mb_id = '" . sql_real_escape_string($q_mb) . "'");
    if ($who) {
        // 조회 전에 정산한다 — 밀린 월 지급이 있으면 여기서 반영돼야 화면이 사실과 맞다
        foreach ($prods as $p) ex_settle($q_mb, $p['pd_id']);

        $w = "l.mb_id = '" . sql_real_escape_string($q_mb) . "'";
        if ($q_pd !== '') $w .= " and l.pd_id = '" . sql_real_escape_string($q_pd) . "'";

        $res = sql_query("select l.*, d.pd_name from ex_credit_lot l
                           left join ex_product d on d.pd_id = l.pd_id
                          where $w order by l.lot_id desc limit 60", false);
        while ($r = sql_fetch_array($res)) $lots[] = $r;

        $w2 = str_replace('l.mb_id', 'g.mb_id', $w);
        $w2 = str_replace('l.pd_id', 'g.pd_id', $w2);
        $res = sql_query("select g.* from ex_credit_ledger g
                          where $w2 order by g.lg_id desc limit 60", false);
        while ($r = sql_fetch_array($res)) $ledger[] = $r;

        $res = sql_query("select e.*, d.pd_name from ex_entitlement e
                           left join ex_product d on d.pd_id = e.pd_id
                          where e.mb_id = '" . sql_real_escape_string($q_mb) . "'
                          order by e.pd_id", false);
        while ($r = sql_fetch_array($res)) $ents[] = $r;
    }
}

$g5['title'] = '포인트 지급';
require_once './admin.head.php';

function exg_h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
?>

<style>
.exgr{max-width:1200px}
.exgr .box{background:#fff;border:1px solid #e3e6ec;border-radius:8px;padding:18px 20px;margin:0 0 16px}
.exgr h2{font-size:15px;margin:0 0 12px;font-weight:700}
.exgr .msg{padding:11px 16px;border-radius:6px;margin:0 0 14px;font-size:14px;line-height:1.6}
.exgr .msg.err{background:#fdeced;border:1px solid #c22638;color:#8c1220}
.exgr .msg.good{background:#e9f7ef;border:1px solid #0a7f3f;color:#075c2d}
.exgr .row{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end}
.exgr .fld{display:flex;flex-direction:column;gap:5px}
.exgr .fld label{font-size:12.5px;font-weight:700;color:#444}
.exgr .fld input,.exgr .fld select{padding:6px 9px;border:1px solid #dde1e8;border-radius:5px;font-size:13px}
.exgr .fld input[type=text]{min-width:150px}
.exgr .fld.wide{flex:1;min-width:240px}
.exgr .fld.wide input{width:100%;box-sizing:border-box}
.exgr table{border-collapse:collapse;width:100%;font-size:12.5px;margin-top:8px}
.exgr th,.exgr td{border:1px solid #e3e6ec;padding:6px 9px;text-align:left}
.exgr th{background:#f7f8fa;font-weight:600;white-space:nowrap}
.exgr td.n{text-align:right;white-space:nowrap}
.exgr .hint{color:#666;font-size:13px;line-height:1.7}
.exgr code{background:#f4f5f7;padding:1px 5px;border-radius:3px;font-family:Consolas,monospace}
.exgr .plus{color:#0a7f3f;font-weight:700}.exgr .minus{color:#c22638;font-weight:700}
.exgr .dead{color:#999;text-decoration:line-through}
.exgr .bal{display:flex;gap:20px;flex-wrap:wrap;font-size:13px;margin-bottom:4px}
.exgr .bal b{font-size:17px}
</style>

<div class="exgr">

<?php if ($msg): ?><div class="msg good"><?php echo exg_h($msg) ?></div><?php endif; ?>
<?php if ($err): ?><div class="msg err"><?php echo exg_h($err) ?></div><?php endif; ?>

  <div class="box">
    <h2>회원 조회</h2>
    <form method="get" class="row">
      <div class="fld"><label>회원 아이디</label>
        <input type="text" name="mb" value="<?php echo exg_h($q_mb) ?>" required></div>
      <div class="fld"><label>문제집</label>
        <select name="pd">
          <option value="">전체</option>
          <?php foreach ($prods as $p): ?>
            <option value="<?php echo exg_h($p['pd_id']) ?>" <?php echo $q_pd === $p['pd_id'] ? 'selected' : '' ?>>
              <?php echo exg_h($p['pd_name']) ?></option>
          <?php endforeach; ?>
        </select></div>
      <div class="fld"><label>&nbsp;</label><input type="submit" class="btn_submit" value="조회"></div>
    </form>
    <?php if ($q_mb !== '' && !$who): ?>
      <p class="hint" style="margin-top:10px;color:#c22638">그런 아이디의 회원이 없습니다.</p>
    <?php endif; ?>
  </div>

<?php if ($who): ?>

  <div class="box">
    <h2><?php echo exg_h($who['mb_nick'] ? $who['mb_nick'] : $who['mb_id']) ?>
      <span class="hint">(<?php echo exg_h($who['mb_id']) ?>
      <?php echo $who['mb_email'] ? ' · ' . exg_h($who['mb_email']) : '' ?>
      <?php echo $who['mb_hp'] ? ' · ' . exg_h($who['mb_hp']) : '' ?>)</span></h2>
    <div class="bal">
      <?php foreach ($prods as $p):
        $bal = ex_credit_balance($who['mb_id'], $p['pd_id']);
        if ($bal <= 0 && $q_pd !== $p['pd_id']) continue; ?>
        <span><?php echo exg_h($p['pd_name']) ?>
          <b><?php echo ex_credit_count($who['mb_id'], $p['pd_id']) ?>개</b>
          <small class="hint">(<?php echo number_format($bal) ?>원)</small></span>
      <?php endforeach; ?>
    </div>

    <?php if ($ents): ?>
      <h2 style="margin-top:18px">구독권 <span class="hint">— 월 지급의 원천</span></h2>
      <table>
        <tr><th>문제집</th><th class="n">월 지급</th><th class="n">결제 개월</th>
            <th class="n">지급한 개월</th><th>다음 지급일</th><th>시작</th></tr>
        <?php foreach ($ents as $e): ?>
        <tr>
          <td><?php echo exg_h($e['pd_name'] ? $e['pd_name'] : $e['pd_id']) ?></td>
          <td class="n"><?php echo number_format((int)$e['monthly_quota']) ?></td>
          <td class="n"><?php echo (int)$e['months_paid'] ?></td>
          <td class="n"><?php echo (int)$e['months_granted'] ?></td>
          <td><?php echo exg_h($e['next_grant_on']) ?></td>
          <td><?php echo exg_h($e['started_on']) ?></td>
        </tr>
        <?php endforeach; ?>
      </table>
      <div class="hint" style="margin-top:6px">
        <b>지급한 개월 &lt; 결제 개월</b> 이고 <b>다음 지급일</b> 이 지났으면 회원이 접속하는 순간 자동 지급된다
        (cron 이 없어 조회 시점에 정산한다). 이 화면을 열 때도 정산이 돌았다.
      </div>
    <?php endif; ?>
  </div>

  <div class="box">
    <h2>지급 · 조정</h2>
    <form method="post" class="row" onsubmit="return confirm('실행합니다. 원장에 기록이 남습니다.');">
      <input type="hidden" name="token" value="">
      <div class="fld"><label>회원</label>
        <input type="text" name="mb_id" value="<?php echo exg_h($who['mb_id']) ?>" readonly></div>
      <div class="fld"><label>문제집</label>
        <select name="pd_id" required>
          <?php foreach ($prods as $p): ?>
            <option value="<?php echo exg_h($p['pd_id']) ?>" <?php echo $q_pd === $p['pd_id'] ? 'selected' : '' ?>>
              <?php echo exg_h($p['pd_name']) ?></option>
          <?php endforeach; ?>
        </select></div>
      <div class="fld"><label>수량(원)</label>
        <input type="number" name="qty" value="1000" step="10" required style="width:110px"></div>
      <div class="fld"><label>유효기간(일)</label>
        <input type="number" name="days" value="30" min="1" max="3650" style="width:90px"></div>
      <div class="fld wide"><label>사유 <span class="hint">— 원장에 남는다</span></label>
        <input type="text" name="memo" maxlength="120" required placeholder="내부 오픈 무료 지급 / 이벤트 / 오지급 회수"></div>
      <div class="fld"><label>&nbsp;</label><input type="submit" class="btn_submit" value="실행"></div>
    </form>
    <div class="hint" style="margin-top:10px">
      단가 기준으로 <code>1,000원 = 질문 100개</code> 다(문제집 설정 <code>cost_units</code>).
      화면에서는 원 단위를 이용자에게 노출하지 않고 개수로만 보여준다.<br>
      <b>음수를 넣으면 회수</b>다. 남은 잔액에서만 빠지고 <b>이미 쓴 분은 회수되지 않는다</b> —
      잔액이 음수가 되는 상태를 만들지 않기 위해서다.
    </div>
  </div>

  <div class="box">
    <h2>포인트 묶음 <span class="hint">(최근 60건)</span></h2>
    <?php if (!$lots): ?><p class="hint">없습니다.</p><?php else: ?>
    <table>
      <tr><th>#</th><th>문제집</th><th>출처</th><th>지급월</th>
          <th class="n">지급</th><th class="n">사용</th><th class="n">남음</th>
          <th>만료</th><th>메모</th><th>생성</th></tr>
      <?php $today = date('Y-m-d'); foreach ($lots as $l):
        $rest = (int)$l['lot_qty'] - (int)$l['lot_used'];
        $dead = ($l['lot_expire'] < $today); ?>
      <tr<?php echo $dead ? ' class="dead"' : '' ?>>
        <td><?php echo (int)$l['lot_id'] ?></td>
        <td><?php echo exg_h($l['pd_name'] ? $l['pd_name'] : $l['pd_id']) ?></td>
        <td><?php echo exg_h($l['lot_src']) ?></td>
        <td><?php echo exg_h($l['lot_period'] === null ? '—' : $l['lot_period']) ?></td>
        <td class="n"><?php echo number_format((int)$l['lot_qty']) ?></td>
        <td class="n"><?php echo number_format((int)$l['lot_used']) ?></td>
        <td class="n"><?php echo number_format($rest) ?></td>
        <td><?php echo exg_h($l['lot_expire']) ?><?php echo $dead ? ' (만료)' : '' ?></td>
        <td><?php echo exg_h($l['lot_note']) ?></td>
        <td><?php echo exg_h(substr($l['created_at'], 0, 16)) ?></td>
      </tr>
      <?php endforeach; ?>
    </table>
    <div class="hint" style="margin-top:6px">
      <b>지급월</b> 이 <code>—</code> 인 것은 월 지급이 아니다(강제 지급·환불).
      <code>uq_month</code> 가 NULL 을 서로 다른 값으로 보므로 몇 번이든 발급된다.
      만료된 줄은 잔액 계산에서 자동으로 빠진다 — 만료 배치가 없는 이유다.
    </div>
    <?php endif; ?>
  </div>

  <div class="box">
    <h2>원장 <span class="hint">(append-only · 최근 60건)</span></h2>
    <?php if (!$ledger): ?><p class="hint">없습니다.</p><?php else: ?>
    <table>
      <tr><th>#</th><th>문제집</th><th>종류</th><th class="n">금액</th><th class="n">잔액</th>
          <th>참조(멱등키)</th><th>처리자</th><th>메모</th><th>시각</th></tr>
      <?php foreach ($ledger as $g): $amt = (int)$g['lg_amt']; ?>
      <tr>
        <td><?php echo (int)$g['lg_id'] ?></td>
        <td><?php echo exg_h($g['pd_id']) ?></td>
        <td><?php echo exg_h($g['lg_type']) ?></td>
        <td class="n <?php echo $amt >= 0 ? 'plus' : 'minus' ?>">
          <?php echo ($amt >= 0 ? '+' : '') . number_format($amt) ?></td>
        <td class="n"><?php echo number_format((int)$g['lg_bal']) ?></td>
        <td><code><?php echo exg_h($g['lg_ref']) ?></code></td>
        <td><?php echo exg_h($g['lg_by']) ?></td>
        <td><?php echo exg_h($g['lg_memo']) ?></td>
        <td><?php echo exg_h(substr($g['created_at'], 0, 16)) ?></td>
      </tr>
      <?php endforeach; ?>
    </table>
    <div class="hint" style="margin-top:6px">
      이 표는 <b>수정·삭제하지 않는다.</b> 정정도 새 행으로 남긴다.
      <code>lg_ref</code> 가 멱등키다 — <code>order:88</code> 이 두 번 있으면 중복 지급이므로 조사 대상이다.
      <code>expire</code> 행은 조회 시점에 lazy 로 기록된다.
    </div>
    <?php endif; ?>
  </div>

<?php endif; ?>

</div>

<?php
require_once './admin.tail.php';
