<?php
/**
 * exam_install.php — ex_* 스키마 1회 설치기.  ★ 실행 후 반드시 삭제한다.
 *
 * 배치: /www/exam_install.php   (웹루트. common.php 와 같은 자리)
 * 전제: /www/exam/sql/schema.sql, /www/exam/sql/master.sql 이 먼저 올라가 있어야 한다.
 * 접근: **최고관리자로 로그인한 상태**에서만 동작한다.
 *
 * 왜 phpMyAdmin 대신 이걸 쓰나
 *   · 앱이 실제로 쓸 그 DB 연결(그누보드 mysqli 핸들)로 실행된다 →
 *     콜레이션·charset 조건이 런타임과 완전히 동일하다. phpMyAdmin 세션과 다를 수 있다.
 *   · 검증 쿼리 4개를 자동으로 돌려 결과를 화면에 찍는다.
 *   · 절차가 git 에 남아 재현 가능하다.
 *
 * 안전장치
 *   · CREATE TABLE IF NOT EXISTS / INSERT ... ON DUPLICATE KEY UPDATE 라 여러 번 돌려도 안전
 *   · DROP 이나 DELETE 를 하지 않는다. 기존 g5_* 는 건드리지 않는다
 */

include_once(__DIR__ . '/common.php');

header('Content-Type: text/html; charset=utf-8');

/* ── 접근 통제 ─────────────────────────────────────────────────────────── */
if (empty($member['mb_id'])) {
    exit('<meta charset="utf-8"><p style="font:14px sans-serif">'
       . '먼저 <a href="' . G5_BBS_URL . '/login.php">최고관리자로 로그인</a>한 뒤 다시 여십시오.</p>');
}
if ($is_admin !== 'super') {
    exit('<meta charset="utf-8"><p style="font:14px sans-serif">최고관리자만 실행할 수 있습니다.</p>');
}

$SQL_DIR = __DIR__ . '/exam/sql';
$run     = isset($_GET['run']) && $_GET['run'] === '1';

/**
 * SQL 파일을 문장 단위로 쪼갠다.
 * 따옴표 안의 `--` / `;` 를 문장 구분자로 오인하지 않도록 문자 단위로 훑는다.
 * (스토어드 프로시저·DELIMITER 는 쓰지 않으므로 이 정도로 충분하다.)
 */
function ex_split_sql($sql) {
    $out = array(); $buf = ''; $n = strlen($sql);
    $inS = false;   // '홑따옴표' 안
    $inD = false;   // "쌍따옴표" 안
    for ($i = 0; $i < $n; $i++) {
        $c  = $sql[$i];
        $c2 = ($i + 1 < $n) ? $sql[$i + 1] : '';

        if (!$inS && !$inD) {
            if ($c === '-' && $c2 === '-') {                 // -- 줄 주석
                while ($i < $n && $sql[$i] !== "\n") $i++;
                $buf .= "\n"; continue;
            }
            if ($c === '/' && $c2 === '*') {                 // /* 블록 주석 */
                $i += 2;
                while ($i < $n && !($sql[$i] === '*' && ($i + 1 < $n) && $sql[$i + 1] === '/')) $i++;
                $i++; continue;
            }
            if ($c === ';') {                                // 문장 끝
                if (trim($buf) !== '') $out[] = trim($buf);
                $buf = ''; continue;
            }
        }
        if ($c === "'" && !$inD) {
            if ($inS && $c2 === "'") { $buf .= "''"; $i++; continue; }   // '' 이스케이프
            $inS = !$inS;
        } elseif ($c === '"' && !$inS) {
            $inD = !$inD;
        } elseif ($c === '\\' && ($inS || $inD)) {           // 백슬래시 이스케이프
            $buf .= $c . $c2; $i++; continue;
        }
        $buf .= $c;
    }
    if (trim($buf) !== '') $out[] = trim($buf);
    return $out;
}

function h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
?>
<!doctype html><meta charset="utf-8"><title>exam_install</title>
<style>
 body{font:14px/1.7 ui-monospace,Consolas,monospace;max-width:1000px;margin:2rem auto;padding:0 1rem}
 h1{font-size:1.25rem} h2{font-size:1rem;margin:2rem 0 .6rem;border-bottom:1px solid #ddd;padding-bottom:4px}
 table{border-collapse:collapse;margin:.6rem 0;font-size:13px}
 td,th{border:1px solid #ccc;padding:4px 10px;text-align:left}
 th{background:#f4f5f7}
 .ok{color:#0a7f3f;font-weight:700} .bad{color:#c22638;font-weight:700} .dim{color:#888}
 .warn{background:#fff6e5;border:1px solid #d9901a;padding:.7rem 1rem;margin:1rem 0}
 .err{background:#fdeced;border:1px solid #c22638;padding:.7rem 1rem;margin:1rem 0}
 .btn{display:inline-block;padding:.6rem 1.4rem;background:#1f4fd8;color:#fff;text-decoration:none;border-radius:5px}
</style>

<h1>ex_* 스키마 설치기 <span class="dim">— 실행 후 반드시 삭제</span></h1>

<div class="warn">
  이 파일은 DB 구조를 바꾼다. <b>확인이 끝나면 즉시 <code>/www/exam_install.php</code> 를 삭제</b>한다.
</div>

<?php
/* ── SQL 실행 ───────────────────────────────────────────────────────────── */
if ($run) {
    foreach (array('schema.sql', 'master.sql') as $fname) {
        $path = $SQL_DIR . '/' . $fname;
        echo '<h2>' . h($fname) . '</h2>';
        if (!is_readable($path)) {
            echo '<div class="err">파일을 읽을 수 없다: <code>' . h($path) . '</code><br>'
               . 'FileZilla 로 <code>web/exam/sql/</code> 를 <code>/www/exam/sql/</code> 에 먼저 올렸는지 확인한다.</div>';
            continue;
        }
        $stmts = ex_split_sql(file_get_contents($path));
        $ok = $fail = 0;
        echo '<table><tr><th>#</th><th>문장</th><th>결과</th></tr>';
        foreach ($stmts as $i => $s) {
            // G5_DISPLAY_SQL_ERROR 를 끄고(false) 실패를 우리가 센다 —
            // 한 문장이 죽었다고 페이지 전체가 날아가면 원인을 못 본다.
            $r = sql_query($s, false);
            $head = preg_replace('/\s+/', ' ', mb_substr($s, 0, 78));
            if ($r) { $ok++;  $cls = 'ok';  $msg = 'OK'; }
            else    { $fail++; $cls = 'bad'; $msg = sql_error_info(); }
            echo '<tr><td>' . ($i + 1) . '</td><td>' . h($head) . '…</td>'
               . '<td class="' . $cls . '">' . h($msg) . '</td></tr>';
        }
        echo '</table>';
        echo '<p>성공 <b class="ok">' . $ok . '</b> · 실패 <b class="' . ($fail ? 'bad' : 'dim') . '">' . $fail . '</b></p>';
    }

    /* ── 검증 ───────────────────────────────────────────────────────────── */
    echo '<h2>검증 (1) 테이블 15개 · InnoDB · utf8mb4</h2>';
    $res = sql_query("select TABLE_NAME, ENGINE, TABLE_COLLATION
                        from information_schema.TABLES
                       where TABLE_SCHEMA = database() and TABLE_NAME like 'ex\\_%'
                       order by TABLE_NAME", false);
    $cnt = 0; $bad = 0;
    echo '<table><tr><th>테이블</th><th>엔진</th><th>콜레이션</th></tr>';
    while ($r = sql_fetch_array($res)) {
        $cnt++;
        $eng_bad = ($r['ENGINE'] !== 'InnoDB');
        if ($eng_bad) $bad++;
        echo '<tr><td>' . h($r['TABLE_NAME']) . '</td>'
           . '<td class="' . ($eng_bad ? 'bad' : 'ok') . '">' . h($r['ENGINE']) . '</td>'
           . '<td>' . h($r['TABLE_COLLATION']) . '</td></tr>';
    }
    echo '</table>';
    echo '<p>테이블 <b class="' . ($cnt === 15 ? 'ok' : 'bad') . '">' . $cnt . '</b> / 15 · '
       . 'InnoDB 아님 <b class="' . ($bad ? 'bad' : 'dim') . '">' . $bad . '</b></p>';

    echo '<h2>검증 (2) ★ mb_id 계열 콜레이션이 g5_member 와 같은가</h2>';
    $res = sql_query("select TABLE_NAME, COLUMN_NAME, COLLATION_NAME
                        from information_schema.COLUMNS
                       where TABLE_SCHEMA = database()
                         and (TABLE_NAME like 'ex\\_%' or TABLE_NAME = 'g5_member')
                         and COLUMN_NAME in ('mb_id','lg_by','edited_by')
                       order by TABLE_NAME", false);
    $colls = array();
    echo '<table><tr><th>테이블</th><th>컬럼</th><th>콜레이션</th></tr>';
    while ($r = sql_fetch_array($res)) {
        $colls[$r['COLLATION_NAME']] = true;
        echo '<tr><td>' . h($r['TABLE_NAME']) . '</td><td>' . h($r['COLUMN_NAME']) . '</td>'
           . '<td>' . h($r['COLLATION_NAME']) . '</td></tr>';
    }
    echo '</table>';
    echo '<p>서로 다른 콜레이션 종류: <b class="' . (count($colls) === 1 ? 'ok' : 'bad') . '">'
       . count($colls) . '</b> ' . (count($colls) === 1 ? '(1이어야 정상)' : '← 1이 아니면 조인에서 1267 이 난다') . '</p>';

    echo '<h2>검증 (3) ★★ g5_member 실조인 — 에러 없이 숫자가 나와야 한다</h2>';
    $r = sql_fetch("select count(*) as c from ex_user_ext u join g5_member m on m.mb_id = u.mb_id", false);
    if ($r === false || $r === null) {
        echo '<div class="err"><b>조인 실패</b> — ' . h(sql_error_info())
           . '<br>Illegal mix of collations 라면 위 (2)를 확인한다.</div>';
    } else {
        echo '<p class="ok">조인 성공. 결과 ' . (int)$r['c'] . '행 <span class="dim">(0이어도 정상 — 회원이 아직 없다)</span></p>';
    }

    echo '<h2>검증 (4) 이중 지급 차단 제약</h2>';
    $res = sql_query("show index from ex_credit_lot where Key_name = 'uq_month'", false);
    $k = 0; $uniq = null;
    while ($r = sql_fetch_array($res)) { $k++; $uniq = $r['Non_unique']; }
    echo '<p>uq_month 컬럼 <b class="' . ($k === 3 ? 'ok' : 'bad') . '">' . $k . '</b> / 3 · '
       . 'Non_unique=' . h($uniq) . ' <span class="dim">(0 이어야 UNIQUE)</span></p>';

    echo '<h2>마스터 데이터</h2>';
    $res = sql_query("select pd_id, pd_name, tier, model_id, cost_units, cost_cap from ex_product", false);
    echo '<table><tr><th>pd_id</th><th>이름</th><th>tier</th><th>모델</th><th>차감(원)</th><th>원가상한</th></tr>';
    while ($r = sql_fetch_array($res)) {
        echo '<tr><td>' . h($r['pd_id']) . '</td><td>' . h($r['pd_name']) . '</td><td>' . h($r['tier'])
           . '</td><td>' . h($r['model_id']) . '</td><td>' . h($r['cost_units']) . '</td><td>' . h($r['cost_cap']) . '</td></tr>';
    }
    echo '</table>';
    $res = sql_query("select pl_id, pl_name, pl_price, pl_months, pl_quota from ex_plan order by pl_sort", false);
    echo '<table><tr><th>pl_id</th><th>상품</th><th>가격</th><th>개월</th><th>월 지급(원)</th></tr>';
    while ($r = sql_fetch_array($res)) {
        echo '<tr><td>' . h($r['pl_id']) . '</td><td>' . h($r['pl_name']) . '</td><td>' . h($r['pl_price'])
           . '</td><td>' . h($r['pl_months']) . '</td><td>' . h($r['pl_quota']) . '</td></tr>';
    }
    echo '</table>';

    echo '<div class="warn">여기까지 이상이 없으면 <b>이 파일(<code>/www/exam_install.php</code>)을 지운다.</b></div>';

} else {
    /* ── 실행 전 상태 확인 ──────────────────────────────────────────────── */
    echo '<h2>실행 전 확인</h2><table>';
    echo '<tr><th>DB</th><td>' . h(sql_fetch("select database() as d")['d']) . '</td></tr>';
    echo '<tr><th>서버 버전</th><td>' . h(sql_fetch("select version() as v")['v']) . '</td></tr>';
    echo '<tr><th>DB 콜레이션</th><td>' . h(sql_fetch("select @@collation_database as c")['c']) . '</td></tr>';
    echo '<tr><th>sql_mode</th><td>' . h(sql_fetch("select @@sql_mode as m")['m']) . '</td></tr>';
    $mb = sql_fetch("select COLLATION_NAME as c from information_schema.COLUMNS
                      where TABLE_SCHEMA = database() and TABLE_NAME = 'g5_member' and COLUMN_NAME = 'mb_id'");
    echo '<tr><th>g5_member.mb_id</th><td><b>' . h($mb ? $mb['c'] : '?') . '</b>'
       . ' <span class="dim">← ex_* 의 mb_id 가 이것과 같아야 한다</span></td></tr>';
    $ex = sql_fetch("select count(*) as c from information_schema.TABLES
                      where TABLE_SCHEMA = database() and TABLE_NAME like 'ex\\_%'");
    echo '<tr><th>기존 ex_* 테이블</th><td>' . (int)$ex['c'] . '개 <span class="dim">(0이면 최초 설치)</span></td></tr>';
    echo '<tr><th>SQL 파일</th><td>'
       . (is_readable($SQL_DIR . '/schema.sql') ? '<span class="ok">schema.sql OK</span>' : '<span class="bad">schema.sql 없음</span>')
       . ' · '
       . (is_readable($SQL_DIR . '/master.sql') ? '<span class="ok">master.sql OK</span>' : '<span class="bad">master.sql 없음</span>')
       . '<br><span class="dim">' . h($SQL_DIR) . '</span></td></tr>';
    echo '</table>';
    echo '<p><a class="btn" href="?run=1">스키마 설치 실행</a></p>';
    echo '<p class="dim">CREATE TABLE IF NOT EXISTS 라 여러 번 실행해도 안전하다. DROP·DELETE 는 하지 않는다.</p>';
}
