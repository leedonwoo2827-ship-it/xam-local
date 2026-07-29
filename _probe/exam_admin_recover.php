<?php
/**
 * exam_admin_recover.php — 최고관리자 계정 확인 / 비밀번호 재설정.  ★ 사용 후 반드시 삭제.
 *
 * 언제 쓰나: 카페24 자동설치가 만든 그누보드 관리자 계정을 모를 때.
 *            (콘솔 → 계정관리 → 프로그램 자동설치, 자동설치 안내 메일을 먼저 확인할 것)
 *
 * 배치: /www/exam_admin_recover.php   (웹루트 최상위, common.php 와 같은 자리)
 *
 * ⚠⚠ 이 파일은 로그인 없이 비밀번호를 바꾼다. 웹에 열려 있는 동안은
 *     이 URL 을 아는 사람이 관리자가 될 수 있다. 반드시:
 *       1) 아래 $SECRET 을 임의의 긴 문자열로 바꾼다  ← 안 바꾸면 동작하지 않는다
 *       2) ?key=<그 문자열> 을 붙여서 연다
 *       3) 끝나면 즉시 삭제한다
 *
 * 비밀번호는 그누보드의 get_encrypt_string() 으로 만든다 —
 * G5_STRING_ENCRYPT_FUNCTION 설정이 무엇이든 사이트와 같은 방식이 된다.
 */

// ┌──────────────────────────────────────────────────────────────────────┐
// │ 여기를 바꾼다. 예: 'r7Kq2mZx9Lt4Vb8NcE3w'                              │
$SECRET = 'CHANGE-ME';
// └──────────────────────────────────────────────────────────────────────┘

include_once(__DIR__ . '/common.php');
header('Content-Type: text/html; charset=utf-8');
header('X-Robots-Tag: noindex, nofollow');

function h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }

$key = isset($_GET['key']) ? $_GET['key'] : '';
if ($SECRET === 'CHANGE-ME') {
    exit('<meta charset="utf-8"><p style="font:14px sans-serif">'
       . '파일 안의 <code>$SECRET</code> 을 임의의 문자열로 먼저 바꾸십시오.</p>');
}
if (!hash_equals($SECRET, $key)) {
    http_response_code(404);
    exit;   // 키가 틀리면 존재 자체를 알리지 않는다
}

$msg = '';

/* ── 비밀번호 재설정 ─────────────────────────────────────────────────── */
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $target = isset($_POST['mb_id']) ? trim($_POST['mb_id']) : '';
    $newpw  = isset($_POST['newpw']) ? (string)$_POST['newpw'] : '';

    if (strlen($newpw) < 8) {
        $msg = '<div class="err">비밀번호는 8자 이상으로 하십시오.</div>';
    } else {
        // 대상은 관리자 계정으로만 제한한다 — 일반 회원 계정을 여기서 못 바꾸게.
        $row = sql_fetch("select mb_id, mb_level from {$g5['member_table']}
                           where mb_id = '" . sql_real_escape_string($target) . "'");
        if (!$row) {
            $msg = '<div class="err">그런 아이디가 없습니다.</div>';
        } elseif ((int)$row['mb_level'] < 10) {
            $msg = '<div class="err">관리자(mb_level 10) 계정만 이 화면에서 바꿀 수 있습니다.</div>';
        } else {
            $hash = get_encrypt_string($newpw);
            sql_query("update {$g5['member_table']}
                          set mb_password = '" . sql_real_escape_string($hash) . "'
                        where mb_id = '" . sql_real_escape_string($row['mb_id']) . "'", false);
            $msg = '<div class="ok2"><b>변경했습니다.</b> '
                 . h($row['mb_id']) . ' 로 로그인해 보십시오.<br>'
                 . '<b>바로 이 파일을 삭제하십시오.</b></div>';
        }
    }
}

$cf = sql_fetch("select cf_admin from {$g5['config_table']}");
?>
<!doctype html><meta charset="utf-8"><title>admin recover</title>
<style>
 body{font:14px/1.7 ui-monospace,Consolas,monospace;max-width:760px;margin:2rem auto;padding:0 1rem}
 h1{font-size:1.2rem} h2{font-size:1rem;margin:1.8rem 0 .5rem}
 table{border-collapse:collapse;margin:.5rem 0}
 td,th{border:1px solid #ccc;padding:5px 12px;text-align:left}
 th{background:#f4f5f7}
 .warn{background:#fff6e5;border:1px solid #d9901a;padding:.7rem 1rem;margin:1rem 0}
 .err{background:#fdeced;border:1px solid #c22638;padding:.7rem 1rem;margin:1rem 0}
 .ok2{background:#e9f7ef;border:1px solid #0a7f3f;padding:.7rem 1rem;margin:1rem 0}
 input[type=text],input[type=password]{padding:.4rem .6rem;font:inherit;width:260px}
 button{padding:.5rem 1.2rem;font:inherit}
</style>

<h1>최고관리자 계정 복구 <span style="color:#888">— 사용 후 반드시 삭제</span></h1>

<div class="warn">
  이 파일이 서버에 있는 동안은 <b>URL 과 키를 아는 사람이 관리자가 될 수 있다.</b>
  확인이 끝나면 <code>/www/exam_admin_recover.php</code> 를 즉시 지운다.
</div>

<?php echo $msg; ?>

<h2>최고관리자</h2>
<p><code>g5_config.cf_admin</code> = <b><?php echo h($cf ? $cf['cf_admin'] : '(없음)') ?></b></p>

<h2>관리자 계정 목록 (mb_level ≥ 10)</h2>
<table>
  <tr><th>아이디</th><th>이름</th><th>레벨</th><th>이메일</th><th>가입일</th></tr>
<?php
$res = sql_query("select mb_id, mb_name, mb_nick, mb_level, mb_email, mb_datetime
                    from {$g5['member_table']}
                   where mb_level >= 10 order by mb_level desc, mb_id", false);
$n = 0;
while ($r = sql_fetch_array($res)) {
    $n++;
    echo '<tr><td><b>' . h($r['mb_id']) . '</b></td><td>' . h($r['mb_name'] ?: $r['mb_nick'])
       . '</td><td>' . (int)$r['mb_level'] . '</td><td>' . h($r['mb_email'])
       . '</td><td>' . h($r['mb_datetime']) . '</td></tr>';
}
if (!$n) echo '<tr><td colspan="5">관리자 계정이 없습니다.</td></tr>';
?>
</table>
<p style="color:#888">비밀번호는 단방향 해시라 원래 값을 볼 수 없다. 새로 정하는 수밖에 없다.</p>

<h2>비밀번호 재설정</h2>
<form method="post">
  <p>아이디 <input type="text" name="mb_id" value="<?php echo h($cf ? $cf['cf_admin'] : '') ?>" required></p>
  <p>새 비밀번호 <input type="password" name="newpw" minlength="8" required>
     <span style="color:#888">8자 이상</span></p>
  <p><button>변경</button></p>
</form>

<p style="color:#888">
  먼저 확인해 볼 곳: 카페24 콘솔 → <b>계정관리 → 프로그램 자동설치</b>,
  그리고 <b>자동설치 완료 안내 메일</b>. 거기 적혀 있으면 이 파일을 쓸 필요가 없다.
</p>
