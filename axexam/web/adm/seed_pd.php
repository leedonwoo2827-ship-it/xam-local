<?php
/**
 * 품목 1행 등록 — phpMyAdmin 없이 `ex_product` 에 pd_id 를 넣는다. **1회용.**
 *
 * ★ 왜 필요한가
 *   임포트(`adm/exam_import.php`)는 `ex_product` 에 그 품목 행이 없으면
 *   "master.sql 을 먼저 실행하십시오" 로 중단한다(`adm/exam_lib/problem.php:100`).
 *   그런데 카페24 호스팅에는 phpMyAdmin 이 없어서 그 한 줄을 넣을 곳이 없다.
 *   FTP 는 있으니, 그누보드의 DB 접속과 관리자 인증을 그대로 빌려 쓴다.
 *
 * ★ 안전
 *   - `adm/` 에 두고 `_common.php` 를 include 한다 → 그누보드 관리자 인증이 그대로 걸린다.
 *     최고관리자로 로그인하지 않으면 아무것도 하지 않는다(새 인증을 만들지 않는다).
 *   - INSERT 뿐이고 `ON DUPLICATE KEY UPDATE` 로 이름만 갱신한다. 문항·회원은 건드리지 않는다.
 *   - `pd_id` 는 `[a-z0-9-]{1,20}` 만 받는다(임포트와 같은 규칙).
 *
 * ★ 쓰는 법
 *   1. 이 파일을 FTP 로 `/www/adm/seed_pd.php` 에 올린다.
 *   2. 최고관리자로 로그인한 브라우저에서 `/adm/seed_pd.php` 를 연다.
 *   3. 값을 확인하고 [등록] 을 누른다.
 *   4. **끝나면 이 파일을 지운다.** 남겨도 관리자만 쓸 수 있지만 둘 이유가 없다.
 */
require_once './_common.php';

/* 그누보드의 최고관리자 게이트 — `g4_import.php` 가 쓰는 것과 같은 패턴이다.
   새 인증 수단을 만들지 않는다(만들면 그게 곧 구멍이 된다). */
if ($is_admin != 'super') {
    alert('최고관리자로 로그인 후 실행해 주십시오.', G5_URL);
}

/* 기본값 — 화면에서 고칠 수 있다. schema.sql 의 ex_product 컬럼과 같은 순서다. */
$def = array(
    'pd_id'      => 'bigdata',
    'pd_name'    => '빅데이터분석기사 필기',
    'pd_open'    => 1,
    'tier'       => 'T1',
    'model_id'   => 'deepseek-v4-flash',
    'provider'   => 'openai_compat',
    'cost_units' => 10,
    'cost_cap'   => '3.0000',
    'pd_sort'    => 20,
);

$done = '';
$err  = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $pd_id   = isset($_POST['pd_id']) ? trim($_POST['pd_id']) : '';
    $pd_name = isset($_POST['pd_name']) ? trim($_POST['pd_name']) : '';
    $sort    = isset($_POST['pd_sort']) ? (int)$_POST['pd_sort'] : 0;

    // 임포트(problem.php:86)와 같은 규칙으로 검사한다 — 여기서 통과한 값이 거기서 막히면 안 된다.
    if (!preg_match('/^[a-z0-9\-]{1,20}$/', $pd_id)) {
        $err = "pd_id 형식이 잘못됐습니다: '" . htmlspecialchars($pd_id) . "' "
             . "(소문자·숫자·하이픈 1~20자)";
    } elseif ($pd_name === '') {
        $err = '품목 이름이 비어 있습니다.';
    } else {
        $sql = "insert into ex_product
                  (pd_id, pd_name, pd_open, tier, model_id, provider,
                   cost_units, cost_cap, pd_sort)
                values
                  ('" . sql_escape_string($pd_id) . "',
                   '" . sql_escape_string($pd_name) . "',
                   " . (int)$def['pd_open'] . ",
                   '" . sql_escape_string($def['tier']) . "',
                   '" . sql_escape_string($def['model_id']) . "',
                   '" . sql_escape_string($def['provider']) . "',
                   " . (int)$def['cost_units'] . ",
                   " . (float)$def['cost_cap'] . ",
                   " . $sort . ")
                on duplicate key update
                  pd_name = values(pd_name),
                  pd_sort = values(pd_sort)";
        sql_query($sql);
        $row = sql_fetch("select * from ex_product
                           where pd_id = '" . sql_escape_string($pd_id) . "'");
        $done = $row
            ? "등록됐습니다 — pd_id={$row['pd_id']} · {$row['pd_name']} · open={$row['pd_open']}"
            : '실행은 됐는데 행을 다시 읽지 못했습니다. DB 권한을 확인하세요.';
    }
}

/* 지금 등록된 품목 — 이미 있는지 눈으로 보고 누른다. */
$rows = array();
$res = sql_query("select pd_id, pd_name, pd_open, pd_sort from ex_product order by pd_sort, pd_id");
while ($r = sql_fetch_array($res)) { $rows[] = $r; }
?><!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>품목 등록 (1회용)</title>
<style>
 body{font:14px/1.7 -apple-system,"Malgun Gothic",sans-serif;max-width:780px;margin:32px auto;padding:0 16px;color:#1b1f19}
 h1{font-size:19px;margin:0 0 4px} .m{color:#666;font-size:13px}
 table{border-collapse:collapse;width:100%;margin:14px 0}
 th,td{border:1px solid #ddd;padding:7px 9px;text-align:left;font-size:13px}
 th{background:#f6f6f2}
 label{display:block;margin:10px 0 3px;font-weight:600;font-size:13px}
 input{width:100%;padding:6px 8px;border:1px solid #ccc;border-radius:4px;font:inherit}
 .ok{background:#e3f1ec;border:1px solid #0f7355;color:#0f7355;padding:9px 11px;border-radius:5px;margin:12px 0}
 .er{background:#f6e7ef;border:1px solid #6b1d4a;color:#6b1d4a;padding:9px 11px;border-radius:5px;margin:12px 0}
 .w{background:#f8f6e6;border:1px solid #6f6112;color:#6f6112;padding:9px 11px;border-radius:5px;margin:12px 0}
 button{margin-top:14px;padding:9px 18px;background:#c41c0b;color:#fff;border:0;border-radius:5px;font:inherit;font-weight:700;cursor:pointer}
</style></head><body>

<h1>품목 등록 <span class="m">(ex_product · 1회용)</span></h1>
<p class="m">임포트는 이 행이 없으면 중단됩니다. 카페24에 phpMyAdmin 이 없어 이 화면으로 대신합니다.</p>

<?php if ($done): ?><div class="ok"><?php echo htmlspecialchars($done) ?></div><?php endif; ?>
<?php if ($err):  ?><div class="er"><?php echo $err ?></div><?php endif; ?>

<h3 style="font-size:15px;margin:18px 0 0">지금 등록된 품목</h3>
<table><tr><th>pd_id</th><th>이름</th><th>공개</th><th>정렬</th></tr>
<?php if (!$rows): ?><tr><td colspan="4" class="m">없습니다.</td></tr><?php endif; ?>
<?php foreach ($rows as $r): ?>
 <tr><td><code><?php echo htmlspecialchars($r['pd_id']) ?></code></td>
     <td><?php echo htmlspecialchars($r['pd_name']) ?></td>
     <td><?php echo (int)$r['pd_open'] ?></td>
     <td><?php echo (int)$r['pd_sort'] ?></td></tr>
<?php endforeach; ?>
</table>

<form method="post">
  <label>pd_id <span class="m">— 빌드의 <code>--pd</code> 와 같아야 합니다</span></label>
  <input name="pd_id" value="<?php echo htmlspecialchars($def['pd_id']) ?>" required>
  <label>품목 이름</label>
  <input name="pd_name" value="<?php echo htmlspecialchars($def['pd_name']) ?>" required>
  <label>정렬 순서</label>
  <input name="pd_sort" value="<?php echo (int)$def['pd_sort'] ?>">
  <button type="submit">등록</button>
</form>

<div class="w" style="margin-top:22px">
  끝나면 <b>이 파일을 FTP 로 지우세요</b> (<code>/adm/seed_pd.php</code>).
  관리자만 쓸 수 있지만 둘 이유가 없습니다.
</div>
</body></html>
