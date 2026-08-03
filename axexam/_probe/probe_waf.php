<?php
/* probe_waf.php — 확인 후 반드시 삭제한다.
 *
 * 목적 2개
 *   1) 지문에 SQL이 든 POST 가 WAF 를 통과하는가         ← 질문 등록(유료 기능)의 생사
 *   2) problems.json 임포트에 필요한 업로드 상한은 얼마인가 ← S4 전제
 *
 * 올린 뒤 https://axexam.mycafe24.com/probe_waf.php 를 열고
 * [전송] 버튼 3개를 각각 눌러본다. 하나라도 406/403 이면 그 경로가 막힌 것이다.
 */

header('X-Robots-Tag: noindex, nofollow');

/* ── POST 수신부 ─────────────────────────────────────────── */
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    header('Content-Type: text/plain; charset=utf-8');
    $q = isset($_POST['q']) ? $_POST['q'] : '';
    echo "POST 수신 OK\n";
    echo "case   : ", (isset($_POST['case']) ? $_POST['case'] : '?'), "\n";
    echo "길이   : ", strlen($q), " bytes\n";
    echo "앞 80자: ", substr($q, 0, 80), "\n";
    exit;
}

/* ── 리소스 한도 ──────────────────────────────────────────── */
$ini = array(
    'upload_max_filesize' => ini_get('upload_max_filesize'),
    'post_max_size'       => ini_get('post_max_size'),
    'max_file_uploads'    => ini_get('max_file_uploads'),
    'max_input_vars'      => ini_get('max_input_vars'),
    'max_execution_time'  => ini_get('max_execution_time'),
    'max_input_time'      => ini_get('max_input_time'),
    'memory_limit'        => ini_get('memory_limit'),
    'default_socket_timeout' => ini_get('default_socket_timeout'),
);

/* 웹루트 밖에 파일을 둘 수 있는가 — API 키 보관 위치 판단용 */
$home    = dirname($_SERVER['DOCUMENT_ROOT']);
$private = $home . '/private';
$can_write_private = is_dir($private) ? is_writable($private) : is_writable($home);

/* ── 테스트 케이스 3개 ────────────────────────────────────── */
$cases = array(
    'A. 전형적 SQLD 지문 (SELECT/JOIN/WHERE)' =>
"SELECT e.ename, d.dname\n"
."  FROM emp e, dept d\n"
." WHERE e.deptno = d.deptno\n"
."   AND e.sal > 3000\n"
." ORDER BY e.ename;",

    'B. WAF 가 가장 싫어하는 조합 (1=1 / UNION ALL / OR)' =>
"SELECT e.ename, d.dname FROM emp e, dept d\n"
." WHERE e.deptno = d.deptno AND e.sal > 3000\n"
."   AND e.ename LIKE 'A%' OR 1=1\n"
." UNION ALL SELECT NULL, NULL FROM dual;",

    'C. DDL/DML + 주석 + 세미콜론 (문제 지문에 실제로 나온다)' =>
"CREATE TABLE 주문 (주문번호 NUMBER PRIMARY KEY, 고객번호 NUMBER);\n"
."-- 아래는 오답 보기\n"
."DELETE FROM 주문 WHERE 1=1; /* 전체 삭제 */\n"
."UPDATE 주문 SET 고객번호 = NULL WHERE 주문번호 IN (SELECT 주문번호 FROM 주문);",
);
?>
<!doctype html>
<meta charset="utf-8">
<title>probe_waf</title>
<style>
 body{font:14px/1.6 ui-monospace,Consolas,monospace;max-width:900px;margin:2rem auto;padding:0 1rem}
 h1{font-size:1.2rem} h2{font-size:1rem;margin-top:2rem}
 table{border-collapse:collapse;margin:1rem 0} td,th{border:1px solid #ccc;padding:.3rem .6rem;text-align:left}
 textarea{width:100%;font:12px/1.5 ui-monospace,Consolas,monospace}
 .warn{background:#fee;border:1px solid #c00;padding:.6rem 1rem;margin:1rem 0}
 button{padding:.4rem 1.2rem;font-size:1rem}
</style>

<h1>probe_waf.php — 확인 후 반드시 삭제</h1>

<div class="warn">
  이 파일은 서버 설정을 노출한다. 확인이 끝나면 <b>즉시 삭제</b>한다.
</div>

<h2>1. 리소스 한도</h2>
<table>
<?php foreach ($ini as $k => $v): ?>
  <tr><th><?php echo $k ?></th><td><?php echo htmlspecialchars($v === '' ? '(빈값)' : $v) ?></td></tr>
<?php endforeach; ?>
  <tr><th>DOCUMENT_ROOT</th><td><?php echo htmlspecialchars($_SERVER['DOCUMENT_ROOT']) ?></td></tr>
  <tr><th>웹루트 상위(<?php echo htmlspecialchars($home) ?>)에 쓰기</th>
      <td><?php echo $can_write_private ? '가능 → API 키를 웹루트 밖에 둘 수 있다'
                                        : '불가 → exam/data/secret.php + .htaccess deny 로 간다' ?></td></tr>
</table>

<p><b>보아야 할 것</b>: <code>post_max_size</code> 와 <code>upload_max_filesize</code> 가
<code>problems.json</code>(SQLD 300문제 ≈ 1MB, 자격증 5종이면 수 MB)보다 큰가.
작으면 <code>--emit-json --pd sqld</code> 로 품목별 분할 업로드한다.</p>

<h2>2. WAF — SQL 이 든 POST 가 통과하는가</h2>

<p>버튼을 각각 눌러 <b>새 탭에서</b> 결과를 본다.
<code>POST 수신 OK</code> 가 나오면 통과, <b>406 / 403 / 빈 화면</b>이면 WAF 가 죽인 것이다.</p>

<?php $i = 0; foreach ($cases as $label => $sql): $i++; ?>
<h3><?php echo htmlspecialchars($label) ?></h3>
<form method="post" target="_blank">
  <input type="hidden" name="case" value="<?php echo $i ?>">
  <textarea name="q" rows="6"><?php echo htmlspecialchars($sql) ?></textarea>
  <p><button>전송</button></p>
</form>
<?php endforeach; ?>

<h2>3. 판정</h2>
<ul>
  <li><b>3개 전부 통과</b> → 질문 등록에 문제 없다. 계획대로 진행.</li>
  <li><b>B 또는 C 만 차단</b> → 카페24 고객센터(1588-3284)에 웹방화벽 예외를 요청한다.
      요청 시 "SQL 자격증 교육 사이트라 학습자 질문 본문에 SQL 구문이 포함된다"고 사유를 밝히고
      <code>/exam/api/qna.php</code> 경로만 예외 처리를 요청하는 게 통과 확률이 높다.</li>
  <li><b>전부 차단</b> → 설계 변경이 필요하다. 클라이언트에서 질문 본문을
      base64 인코딩해 보내고 서버에서 디코드하는 우회가 가능하지만,
      <b>WAF 우회는 최후 수단</b>이고 먼저 고객센터 예외를 시도한다.</li>
</ul>
