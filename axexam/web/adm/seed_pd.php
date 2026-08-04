<?php
/**
 * 품목 관리 — `ex_product` 등록 · 수정 · 숨김 · 삭제. **카페24에 phpMyAdmin 이 없어서 있다.**
 *
 * ── 왜 필요한가 ────────────────────────────────────────────────────────────
 * 임포트(`adm/exam_import.php`)는 `ex_product` 에 그 품목 행이 없으면 "master.sql 을
 * 먼저 실행하십시오" 로 중단한다(`adm/exam_lib/problem.php:100`). 그런데 카페24 호스팅에는
 * phpMyAdmin 이 없어서 그 한 줄을 넣을 곳이 없다. FTP 는 있으니, 그누보드의 DB 접속과
 * 관리자 인증을 그대로 빌려 쓴다.
 *
 * 그리고 실제로 겪은 일: 같은 문제집이 `bdae-w` 와 `bigdata` 두 이름으로 생겨
 * **랜딩에 같은 이름 카드가 두 개** 뜰 상황이 됐다. 등록만 되고 정리할 방법이 없으면
 * 그런 찌꺼기가 계속 쌓인다. 그래서 수정·숨김·삭제를 함께 둔다.
 *
 * ── ★ 삭제의 안전 규칙 ─────────────────────────────────────────────────────
 * `pd_id` 를 참조하는 테이블이 다섯이다: ex_problem · ex_round · ex_entitlement ·
 * ex_order · ex_qna. 그리고 `ex_problem.pr_id` 는 **회원의 응시기록·오답노트**
 * (`ex_attempt_item.pr_id` · `ex_wrong.pr_id`)가 참조한다(schema.sql:81 의 경고).
 *
 * → 그래서 **문항이 0개일 때만 삭제한다.** 문항이 있으면 삭제 대신 [숨기기] 를 쓴다.
 *   숨기면 이용자 화면에서 사라지고(products.php 가 pd_open 을 본다) 회원 기록은 남는다.
 *   문항까지 지우는 것은 회원 오답노트를 끊는 일이라 이 화면에서 하지 않는다.
 *
 * ── 안전 ───────────────────────────────────────────────────────────────────
 * - `adm/` 에 두고 `_common.php` 를 include 한다 → 그누보드 관리자 인증이 그대로 걸린다.
 *   최고관리자가 아니면 아무것도 하지 않는다(새 인증을 만들지 않는다).
 * - `pd_id` 는 `[a-z0-9-]{1,20}` 만 받는다 — 임포트(`problem.php:86`)와 같은 규칙이라
 *   여기서 통과한 값이 거기서 막히지 않는다.
 *
 * ── 쓰는 법 ────────────────────────────────────────────────────────────────
 * FTP 로 `/www/adm/seed_pd.php` 에 올리고, 최고관리자로 로그인한 브라우저에서 연다.
 * 쓰고 나면 지운다 — 관리자만 쓸 수 있지만 둘 이유가 없다.
 */
require_once './_common.php';

/* 그누보드의 최고관리자 게이트 — `g4_import.php` 가 쓰는 것과 같은 패턴이다.
   새 인증 수단을 만들지 않는다(만들면 그게 곧 구멍이 된다). */
if ($is_admin != 'super') {
    alert('최고관리자로 로그인 후 실행해 주십시오.', G5_URL);
}

$PD_RE = '/^[a-z0-9\-]{1,20}$/';
$msg = '';
$err = '';

/* ── 처리 ──────────────────────────────────────────────────────────────── */
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $act   = isset($_POST['act']) ? $_POST['act'] : '';
    $pd_id = isset($_POST['pd_id']) ? trim((string)$_POST['pd_id']) : '';

    if (!preg_match($PD_RE, $pd_id)) {
        $err = "pd_id 형식이 잘못됐습니다: '" . htmlspecialchars($pd_id)
             . "' (소문자·숫자·하이픈 1~20자)";
    } else {
        $pdq = sql_escape_string($pd_id);
        $c0 = sql_fetch("select count(*) as n from ex_problem where pd_id = '$pdq'");
        $n_prob = (int)$c0['n'];

        if ($act === 'save') {
            /* 등록 · 수정 — 같은 pd_id 면 이름·정렬만 갱신한다(UPSERT).
               pd_open 은 여기서 건드리지 않는다 — 숨김/공개는 아래 토글이 담당한다.
               새로 만들 때만 1(공개)로 들어간다. */
            $name = trim((string)$_POST['pd_name']);
            $sort = (int)$_POST['pd_sort'];
            if ($name === '') {
                $err = '품목 이름이 비어 있습니다.';
            } else {
                sql_query("insert into ex_product
                             (pd_id, pd_name, pd_open, tier, model_id, provider,
                              cost_units, cost_cap, pd_sort)
                           values
                             ('$pdq', '" . sql_escape_string($name) . "', 1, 'T1',
                              'deepseek-v4-flash', 'openai_compat', 10, 3.0000, $sort)
                           on duplicate key update
                             pd_name = values(pd_name),
                             pd_sort = values(pd_sort)");
                $msg = "저장했습니다 — $pd_id · $name · 정렬 $sort";
            }
        } elseif ($act === 'hide' || $act === 'show') {
            $to = ($act === 'show') ? 1 : 0;
            sql_query("update ex_product set pd_open = $to where pd_id = '$pdq'");
            $msg = $to
                ? "$pd_id 을 공개했습니다."
                : "$pd_id 을 숨겼습니다. 랜딩 카드와 목록에서 사라집니다"
                  . ($n_prob ? " (문항 {$n_prob}개는 그대로 남습니다)." : ".");
        } elseif ($act === 'delete') {
            /* ★ 문항이 있으면 지우지 않는다. 회원 응시기록·오답노트가 pr_id 를 참조한다. */
            if ($n_prob > 0) {
                $err = "문항이 {$n_prob}개 있어 삭제할 수 없습니다. 회원의 응시기록·오답노트가 "
                     . "이 문항들을 참조하므로 지우면 그 기록이 끊깁니다 — [숨기기] 를 쓰세요.";
            } else {
                sql_query("delete from ex_round   where pd_id = '$pdq'");
                sql_query("delete from ex_product where pd_id = '$pdq'");
                $msg = "$pd_id 을 삭제했습니다 (문항 0개였습니다). ex_round 도 함께 지웠습니다.";
            }
        }
    }
}

/* ── 목록 — 문항·회차·구독 수를 함께 센다. 무엇을 지우는지 알고 눌러야 한다. ── */
$rows = array();
$res = sql_query("select pd_id, pd_name, pd_open, pd_sort from ex_product
                   order by pd_open desc, pd_sort, pd_id");
while ($r = sql_fetch_array($res)) {
    $pdq = sql_escape_string($r['pd_id']);
    $c = sql_fetch("select count(*) as n, count(distinct rd_no) as rd
                      from ex_problem where pd_id = '$pdq'");
    $r['n_prob']  = (int)$c['n'];
    $r['n_round'] = (int)$c['rd'];
    $e = sql_fetch("select count(*) as n from ex_entitlement where pd_id = '$pdq'");
    $r['n_ent'] = (int)$e['n'];
    $rows[] = $r;
}

/* 수정 대상 — 목록의 [고치기] 가 넘긴다. 없으면 새 등록 폼이다. */
$edit = null;
if (isset($_GET['edit'])) {
    foreach ($rows as $r) {
        if ($r['pd_id'] === $_GET['edit']) { $edit = $r; break; }
    }
}
$f_id   = $edit ? $edit['pd_id']   : 'bigdata';
$f_name = $edit ? $edit['pd_name'] : '빅데이터분석기사 필기';
$f_sort = $edit ? (int)$edit['pd_sort'] : 20;
?><!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>품목 관리 (1회용)</title>
<style>
 body{font:14px/1.7 -apple-system,"Malgun Gothic",sans-serif;max-width:940px;margin:32px auto;padding:0 16px;color:#1b1f19}
 h1{font-size:19px;margin:0 0 4px} h3{font-size:15px;margin:22px 0 6px}
 .m{color:#666;font-size:13px}
 table{border-collapse:collapse;width:100%;margin:14px 0}
 th,td{border:1px solid #ddd;padding:7px 9px;text-align:left;font-size:13px;vertical-align:middle}
 th{background:#f6f6f2;white-space:nowrap}
 td.c{text-align:center}
 tr.off td{background:#faf9f5;color:#888}
 label{display:block;margin:10px 0 3px;font-weight:600;font-size:13px}
 input{width:100%;padding:6px 8px;border:1px solid #ccc;border-radius:4px;font:inherit}
 .ok{background:#e3f1ec;border:1px solid #0f7355;color:#0f7355;padding:9px 11px;border-radius:5px;margin:12px 0}
 .er{background:#f6e7ef;border:1px solid #6b1d4a;color:#6b1d4a;padding:9px 11px;border-radius:5px;margin:12px 0}
 .w{background:#f8f6e6;border:1px solid #6f6112;color:#6f6112;padding:9px 11px;border-radius:5px;margin:12px 0}
 button{padding:5px 11px;border:0;border-radius:4px;font:inherit;cursor:pointer;background:#e8e8e0}
 button.p{background:#c41c0b;color:#fff;font-weight:700;padding:9px 18px;margin-top:14px}
 button.d{background:#6b1d4a;color:#fff}
 button:disabled{opacity:.35;cursor:not-allowed}
 form.inline{display:inline}
 a{color:#cd240e}
</style></head><body>

<h1>품목 관리 <span class="m">(ex_product · 1회용)</span></h1>
<p class="m">임포트는 이 행이 없으면 중단됩니다. 카페24에 phpMyAdmin 이 없어 이 화면으로 대신합니다.</p>

<?php if ($msg): ?><div class="ok"><?php echo htmlspecialchars($msg) ?></div><?php endif; ?>
<?php if ($err): ?><div class="er"><?php echo htmlspecialchars($err) ?></div><?php endif; ?>

<h3>지금 등록된 품목</h3>
<table>
  <tr><th>pd_id</th><th>이름</th><th>문항</th><th>회차</th><th>구독</th>
      <th>공개</th><th>정렬</th><th>동작</th></tr>
<?php if (!$rows): ?>
  <tr><td colspan="8" class="m">없습니다. 아래에서 등록하세요.</td></tr>
<?php endif; ?>
<?php foreach ($rows as $r):
    $open = ((int)$r['pd_open'] === 1); ?>
  <tr class="<?php echo $open ? '' : 'off' ?>">
    <td><code><?php echo htmlspecialchars($r['pd_id']) ?></code></td>
    <td><?php echo htmlspecialchars($r['pd_name']) ?></td>
    <td class="c"><?php echo number_format($r['n_prob']) ?></td>
    <td class="c"><?php echo $r['n_round'] ?></td>
    <td class="c"><?php echo $r['n_ent'] ?></td>
    <td class="c"><?php echo $open ? '공개' : '숨김' ?></td>
    <td class="c"><?php echo (int)$r['pd_sort'] ?></td>
    <td style="white-space:nowrap">
      <a href="?edit=<?php echo urlencode($r['pd_id']) ?>"><button type="button">고치기</button></a>
      <form method="post" class="inline">
        <input type="hidden" name="pd_id" value="<?php echo htmlspecialchars($r['pd_id']) ?>">
        <input type="hidden" name="act" value="<?php echo $open ? 'hide' : 'show' ?>">
        <button type="submit"><?php echo $open ? '숨기기' : '공개' ?></button>
      </form>
      <form method="post" class="inline"
            onsubmit="return confirm('<?php echo htmlspecialchars($r['pd_id']) ?> 을 삭제합니다.\n되돌릴 수 없습니다. 계속할까요?')">
        <input type="hidden" name="pd_id" value="<?php echo htmlspecialchars($r['pd_id']) ?>">
        <input type="hidden" name="act" value="delete">
        <button type="submit" class="d"
          <?php echo $r['n_prob']
            ? 'disabled title="문항이 있어 삭제할 수 없습니다 — 숨기기를 쓰세요"' : '' ?>>삭제</button>
      </form>
    </td>
  </tr>
<?php endforeach; ?>
</table>

<p class="m">
  <b>문항</b>이 0 이면 랜딩 카드가 '준비 중' 으로 뜹니다(<code>products.php</code> 가 그렇게
  판정합니다). <b>구독</b>은 <code>ex_entitlement</code> 행 수 — 그 품목을 수강 중인 회원 수입니다.<br>
  <b>삭제는 문항이 0개일 때만</b> 됩니다. 회원의 응시기록·오답노트가 문항(<code>pr_id</code>)을
  참조하므로, 문항이 있으면 <b>[숨기기]</b>를 쓰세요 — 이용자 화면에서 사라지고 기록은 남습니다.
</p>

<h3><?php echo $edit ? '품목 고치기' : '품목 등록' ?></h3>
<form method="post">
  <input type="hidden" name="act" value="save">
  <label>pd_id <span class="m">— 빌드의 <code>--pd</code> 와 같아야 합니다<?php
    echo $edit ? ' (고치기에서는 바꾸지 않습니다 — 바꾸면 새 품목이 됩니다)' : '' ?></span></label>
  <input name="pd_id" value="<?php echo htmlspecialchars($f_id) ?>" required
         <?php echo $edit ? 'readonly style="background:#f4f4f0"' : '' ?>>
  <label>품목 이름</label>
  <input name="pd_name" value="<?php echo htmlspecialchars($f_name) ?>" required>
  <label>정렬 순서 <span class="m">— 작은 값이 앞. 같으면 pd_id 순</span></label>
  <input name="pd_sort" value="<?php echo $f_sort ?>">
  <button type="submit" class="p"><?php echo $edit ? '저장' : '등록' ?></button>
  <?php if ($edit): ?>
    &nbsp; <a href="seed_pd.php">새 등록으로 돌아가기</a>
  <?php endif; ?>
</form>

<div class="w" style="margin-top:22px">
  끝나면 <b>이 파일을 FTP 로 지우세요</b> (<code>/adm/seed_pd.php</code>).
  관리자만 쓸 수 있지만 둘 이유가 없습니다.
</div>
</body></html>
