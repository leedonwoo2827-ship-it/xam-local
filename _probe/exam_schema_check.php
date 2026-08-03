<?php
/**
 * exam_schema_check.php — 스키마 자기점검. **읽기만 한다.** ★ 확인이 끝나면 삭제한다.
 *
 * 배치: /www/exam_schema_check.php   (웹루트. common.php 와 같은 자리)
 * 접근: 최고관리자로 로그인한 상태에서만 동작한다.
 *
 * 왜 만드는가
 *   07-30 마이그레이션 검증 7항목 중 **(3) `uq_month` 가 4컬럼인가** 를 아직 확인하지
 *   못했다. 그 화면(`exam_migrate.php`)은 보안상 지웠고, phpMyAdmin 은 로그인·DB 선택·
 *   SQL 탭을 거쳐야 한다. 이 파일은 열면 바로 답이 나온다.
 *
 * `uq_month` 가 왜 중요한가
 *   `(mb_id, pd_id, lot_src, lot_period)` 4컬럼이어야 한다. `pd_id` 가 빠져 3컬럼이면
 *   **두 문제집을 수강하는 회원의 같은 달 두 번째 포인트 지급이 DB 차원에서 거부된다.**
 *   에러가 나지 않고 조용히 안 들어가므로 나중에 원인을 찾기가 매우 어렵다.
 *
 * ⚠ 이 파일은 SELECT·SHOW 만 한다. UPDATE·ALTER 를 하지 않는다 —
 *   고칠 것이 있으면 무엇을 실행해야 하는지 SQL 을 보여주고 사람이 판단한다.
 */

include_once(__DIR__ . '/common.php');

header('Content-Type: text/html; charset=utf-8');

if (empty($member['mb_id'])) {
    exit('<meta charset="utf-8"><p style="font:14px sans-serif">'
       . '먼저 <a href="' . G5_BBS_URL . '/login.php">최고관리자로 로그인</a>한 뒤 다시 여십시오.</p>');
}
if ($is_admin !== 'super') {
    exit('<meta charset="utf-8"><p style="font:14px sans-serif">최고관리자만 열 수 있습니다.</p>');
}

/** 인덱스 컬럼 목록 (순서대로) */
function sc_index_cols($table, $key)
{
    $out = array();
    $uniq = null;
    $res = sql_query("show index from `$table` where Key_name = '" . sql_real_escape_string($key) . "'", false);
    while ($res && $r = sql_fetch_array($res)) {
        $out[(int)$r['Seq_in_index']] = $r['Column_name'];
        $uniq = ((int)$r['Non_unique'] === 0);
    }
    ksort($out);
    return array('cols' => array_values($out), 'unique' => $uniq);
}

function sc_has_col($table, $col)
{
    $r = sql_fetch("show columns from `$table` like '" . sql_real_escape_string($col) . "'");
    return !empty($r);
}

$checks = array();

/* ── (1) ★ uq_month 4컬럼 ─────────────────────────────────────────────── */
$ix = sc_index_cols('ex_credit_lot', 'uq_month');
$want = array('mb_id', 'pd_id', 'lot_src', 'lot_period');
$checks[] = array(
    'name' => 'uq_month 컬럼 (가장 중요)',
    'ok'   => ($ix['cols'] === $want && $ix['unique'] === true),
    'got'  => $ix['cols'] ? implode(', ', $ix['cols']) . '  · UNIQUE=' . ($ix['unique'] ? 'yes' : 'NO') : '(인덱스가 없다)',
    'want' => implode(', ', $want) . '  · UNIQUE=yes',
    'fix'  => "ALTER TABLE ex_credit_lot DROP INDEX uq_month,\n"
            . "  ADD UNIQUE KEY uq_month (mb_id, pd_id, lot_src, lot_period);",
);

/* ── (2) pd_id 컬럼이 5개 테이블에 있는가 (다품목 전환) ─────────────────── */
$need_pd = array('ex_credit_lot', 'ex_credit_ledger', 'ex_order', 'ex_entitlement', 'ex_qna');
$miss = array();
foreach ($need_pd as $t) if (!sc_has_col($t, 'pd_id')) $miss[] = $t;
$checks[] = array(
    'name' => 'pd_id 컬럼 (다품목)',
    'ok'   => !$miss,
    'got'  => $miss ? '없는 테이블: ' . implode(', ', $miss) : count($need_pd) . ' / ' . count($need_pd),
    'want' => count($need_pd) . ' / ' . count($need_pd),
    'fix'  => 'exam/sql/migrate-001-multipd.sql 을 다시 확인한다.',
);

/* ── (3) pd_id 가 빈 행 (마이그레이션이 채웠어야 한다) ───────────────────── */
$blank = 0;
$detail = array();
foreach ($need_pd as $t) {
    if (!sc_has_col($t, 'pd_id')) continue;
    $r = sql_fetch("select count(*) as c from `$t` where pd_id = '' or pd_id is null");
    $c = (int)$r['c'];
    if ($c > 0) $detail[] = "$t: $c";
    $blank += $c;
}
$checks[] = array(
    'name' => 'pd_id 가 빈 행',
    'ok'   => ($blank === 0),
    'got'  => $blank === 0 ? '0' : implode(' · ', $detail),
    'want' => '0',
    'fix'  => "UPDATE <표> SET pd_id = 'sqld' WHERE pd_id = '';   -- 어느 문제집인지 확인한 뒤",
);

/* ── (4) 문제집별 과정 ─────────────────────────────────────────────────── */
$plans = array();
$res = sql_query("select pd_id, count(*) as c from ex_plan group by pd_id order by pd_id", false);
while ($res && $r = sql_fetch_array($res)) $plans[] = $r['pd_id'] . ' ' . (int)$r['c'];
$checks[] = array(
    'name' => '문제집별 과정 수',
    'ok'   => (count($plans) >= 2),
    'got'  => $plans ? implode(' · ', $plans) : '(없음)',
    'want' => 'sqld 3 · bdae-w 3',
    'fix'  => 'migrate-001-multipd.sql 의 ex_plan INSERT 를 확인한다.',
);

/* ── (5) 고아 주문 (없는 과정을 가리키는 주문) ──────────────────────────── */
$r = sql_fetch("select count(*) as c from ex_order o
                 left join ex_plan p on p.pl_id = o.pl_id
                where p.pl_id is null");
$checks[] = array(
    'name' => '고아 주문',
    'ok'   => ((int)$r['c'] === 0),
    'got'  => (int)$r['c'] . '건',
    'want' => '0건',
    'fix'  => 'ex_order.pl_id 가 가리키는 ex_plan 행이 없다. 수동 확인이 필요하다.',
);

/* ── (6) ex_qna 신규 컬럼 ──────────────────────────────────────────────── */
$need_qna = array('pd_id', 'kind', 'bo_table');
$miss2 = array();
foreach ($need_qna as $c) if (!sc_has_col('ex_qna', $c)) $miss2[] = $c;
$checks[] = array(
    'name' => 'ex_qna 신규 컬럼',
    'ok'   => !$miss2,
    'got'  => $miss2 ? '없음: ' . implode(', ', $miss2) : count($need_qna) . ' / ' . count($need_qna),
    'want' => count($need_qna) . ' / ' . count($need_qna),
    'fix'  => 'migrate-001-multipd.sql 을 확인한다.',
);

/* ── (7) g5_member 조인 (콜레이션) ─────────────────────────────────────── */
$join_ok = true;
$join_msg = '성공';
$r = sql_fetch("select count(*) as c from ex_user_ext e
                 join {$g5['member_table']} m on m.mb_id = e.mb_id");
if ($r === false || $r === null) { $join_ok = false; $join_msg = '실패 — 콜레이션 충돌 가능'; }
else $join_msg = '성공 (' . (int)$r['c'] . '행)';
$checks[] = array(
    'name' => 'g5_member 조인 (utf8mb3 ↔ utf8mb4)',
    'ok'   => $join_ok,
    'got'  => $join_msg,
    'want' => '성공',
    'fix'  => "ex_* 의 mb_id 를 CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci 로 맞춘다.",
);

/* ── (8) 포인트 정합성 (원장 append-only 대조) ──────────────────────────── */
$r = sql_fetch("select (select coalesce(sum(lg_amt),0) from ex_credit_ledger) as ledger_sum,
                       (select coalesce(sum(lot_qty - lot_used),0) from ex_credit_lot) as lot_avail");
$checks[] = array(
    'name' => '포인트 정합성',
    'ok'   => ((int)$r['ledger_sum'] === (int)$r['lot_avail']),
    'got'  => '원장 ' . (int)$r['ledger_sum'] . ' vs 유효 잔액 ' . (int)$r['lot_avail'],
    'want' => '두 값이 같다 (미기록 만료가 있으면 그만큼 차이난다)',
    'fix'  => '/adm/exam_credit_grant.php 상단 설명 참조. lg_ref 로 추적한다.',
);

$fail = 0;
foreach ($checks as $c) if (!$c['ok']) $fail++;
?>
<meta charset="utf-8">
<title>스키마 자기점검</title>
<style>
 body{font:14px/1.7 -apple-system,"Segoe UI",sans-serif;max-width:980px;margin:34px auto;padding:0 18px;color:#1e2637}
 h1{font-size:21px;margin:0 0 6px} .sub{color:#6b7688;margin:0 0 22px;font-size:13px}
 table{width:100%;border-collapse:collapse;font-size:13.5px}
 th,td{text-align:left;padding:10px 12px;border-bottom:1px solid #e6eaf1;vertical-align:top}
 th{background:#f6f8fc;font-size:12.5px;color:#57637a}
 .ok{color:#0a7d4b;font-weight:700} .no{color:#c62828;font-weight:700}
 code{background:#f2f4f8;padding:1px 5px;border-radius:4px;font-size:12.5px}
 pre{background:#f6f8fc;border:1px solid #e6eaf1;border-radius:8px;padding:10px 12px;
     font-size:12.5px;overflow:auto;margin:6px 0 0;white-space:pre-wrap}
 .banner{border-radius:10px;padding:13px 16px;margin:0 0 20px;font-size:13.5px}
 .b-ok{background:#e8f7ef;border:1px solid #a8dcc0;color:#0a5f3a}
 .b-no{background:#fdecea;border:1px solid #f2b8b2;color:#8c1d13}
 .warn{background:#fff8e1;border:1px solid #f6d97a;color:#6b5410;
       border-radius:10px;padding:13px 16px;margin:22px 0 0;font-size:13.5px}
</style>

<h1>스키마 자기점검</h1>
<p class="sub">읽기만 합니다 — <code>SELECT</code>·<code>SHOW</code> 뿐이고 아무것도 바꾸지 않습니다.</p>

<div class="banner <?php echo $fail ? 'b-no' : 'b-ok' ?>">
  <?php if ($fail) { ?>
    <b><?php echo $fail ?>건이 기대와 다릅니다.</b> 아래 <code>고치는 SQL</code> 을 보고 판단하십시오.
    바로 실행하지 말고 무엇을 바꾸는지 먼저 읽으십시오.
  <?php } else { ?>
    <b><?php echo count($checks) ?>개 항목 전부 통과했습니다.</b> 확인이 끝났으면 이 파일을 지우십시오.
  <?php } ?>
</div>

<table>
  <tr><th style="width:22%">항목</th><th style="width:8%">결과</th>
      <th style="width:35%">현재</th><th style="width:35%">기대</th></tr>
<?php foreach ($checks as $c) { ?>
  <tr>
    <td><b><?php echo htmlspecialchars($c['name']) ?></b></td>
    <td class="<?php echo $c['ok'] ? 'ok' : 'no' ?>"><?php echo $c['ok'] ? 'OK' : 'FAIL' ?></td>
    <td><code><?php echo htmlspecialchars($c['got']) ?></code>
      <?php if (!$c['ok']) { ?><pre>-- 고치는 SQL
<?php echo htmlspecialchars($c['fix']) ?></pre><?php } ?></td>
    <td><?php echo htmlspecialchars($c['want']) ?></td>
  </tr>
<?php } ?>
</table>

<div class="warn">
  <b>★ 확인이 끝나면 이 파일(<code>/www/exam_schema_check.php</code>)을 지우십시오.</b><br>
  스키마 구조를 화면에 그대로 내보내는 파일입니다. 최고관리자만 열리지만,
  웹루트에 남겨둘 이유가 없습니다 — <code>exam_migrate.php</code> 를 지운 것과 같은 이유입니다.
</div>
